import json
from datetime import timedelta
from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.utils import timezone
from accounts.models import Profile
from courses.models import Course, Enrollment, Assignment, Problem
from submissions.models import Submission, finalize_grade

class AutosaveTest(TestCase):
    def setUp(self):
        prof = User.objects.create_user("prof", password="x")
        self.stu = User.objects.create_user("stu", password="x")
        Profile.objects.create(user=self.stu, student_id="B001")
        c = Course.objects.create(title="C", term="114-1", owner=prof)
        Enrollment.objects.create(user=self.stu, course=c, role="student")
        a = Assignment.objects.create(course=c, title="HW", description="",
            deadline=timezone.now() + timedelta(days=1))
        self.prob = Problem.objects.create(assignment=a, number="1", statement="s")
        closed = Assignment.objects.create(course=c, title="HW0", description="",
            deadline=timezone.now() - timedelta(days=1))
        self.closed_prob = Problem.objects.create(assignment=closed, number="1",
            statement="s")

    def test_autosave_creates_submission(self):
        self.client.force_login(self.stu)
        resp = self.client.post(f"/problems/{self.prob.id}/autosave/",
            data=json.dumps({"content": "證明..."}), content_type="application/json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"saved": True})
        self.assertEqual(Submission.objects.get(problem=self.prob,
            student=self.stu).content_markdown, "證明...")

    def test_autosave_rejected_when_graded(self):
        Submission.objects.create(problem=self.prob, student=self.stu,
            content_markdown="x", status="graded")
        self.client.force_login(self.stu)
        resp = self.client.post(f"/problems/{self.prob.id}/autosave/",
            data=json.dumps({"content": "改"}), content_type="application/json")
        self.assertEqual(resp.status_code, 409)

    def test_autosave_rejected_after_graded_past_deadline(self):
        sub = Submission.objects.create(problem=self.closed_prob, student=self.stu,
            content_markdown="x")
        finalize_grade(sub, score=80, overall_comment="", grader=self.stu)
        self.client.force_login(self.stu)
        resp = self.client.post(f"/problems/{self.closed_prob.id}/autosave/",
            data=json.dumps({"content": "改"}), content_type="application/json")
        self.assertEqual(resp.status_code, 409)

    def test_autosave_rejected_after_deadline(self):
        sub = Submission.objects.create(problem=self.closed_prob, student=self.stu,
            content_markdown="原稿")
        self.client.force_login(self.stu)
        resp = self.client.post(f"/problems/{self.closed_prob.id}/autosave/",
            data=json.dumps({"content": "截止後修改"}), content_type="application/json")
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json(), {"error": "locked"})
        sub.refresh_from_db()
        self.assertEqual(sub.content_markdown, "原稿")
        self.assertEqual(sub.status, "draft")

    def test_autosave_after_deadline_creates_no_submission(self):
        self.client.force_login(self.stu)
        resp = self.client.post(f"/problems/{self.closed_prob.id}/autosave/",
            data=json.dumps({"content": "新繳交"}), content_type="application/json")
        self.assertEqual(resp.status_code, 409)
        self.assertFalse(Submission.objects.filter(problem=self.closed_prob).exists())

    def test_non_member_forbidden(self):
        other = User.objects.create_user("other", password="x")
        self.client.force_login(other)
        resp = self.client.post(f"/problems/{self.prob.id}/autosave/",
            data=json.dumps({"content": "x"}), content_type="application/json")
        self.assertEqual(resp.status_code, 403)

    def test_autosave_passes_with_csrf_enforced(self):
        # 模擬真實瀏覽器:editor GET 必須種下 csrftoken cookie,
        # editor.js 才能在 autosave POST 帶上 X-CSRFToken header。
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.stu)
        get_resp = csrf_client.get(f"/problems/{self.prob.id}/edit/")
        self.assertEqual(get_resp.status_code, 200)
        token = csrf_client.cookies.get("csrftoken")
        self.assertIsNotNone(token)
        resp = csrf_client.post(f"/problems/{self.prob.id}/autosave/",
            data=json.dumps({"content": "x"}), content_type="application/json",
            HTTP_X_CSRFTOKEN=token.value)
        self.assertEqual(resp.status_code, 200)

    def test_autosave_non_member_returns_json(self):
        other = User.objects.create_user("other2", password="x")
        self.client.force_login(other)
        resp = self.client.post(f"/problems/{self.prob.id}/autosave/",
            data=json.dumps({"content": "x"}), content_type="application/json")
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["error"], "forbidden")


class EditorGetTest(TestCase):
    def setUp(self):
        prof = User.objects.create_user("prof2", password="x")
        self.stu = User.objects.create_user("stu2", password="x")
        Profile.objects.create(user=self.stu, student_id="B002")
        c = Course.objects.create(title="C2", term="114-1", owner=prof)
        Enrollment.objects.create(user=self.stu, course=c, role="student")
        a = Assignment.objects.create(course=c, title="HW2", description="",
            deadline=timezone.now() + timedelta(days=7))
        self.prob = Problem.objects.create(assignment=a, number="1", statement="s")

    def test_editor_get_student_sees_existing_content(self):
        Submission.objects.create(problem=self.prob, student=self.stu,
            content_markdown="已知條件如下")
        self.client.force_login(self.stu)
        resp = self.client.get(f"/problems/{self.prob.id}/edit/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "已知條件如下")

    def test_editor_editable_before_deadline(self):
        self.client.force_login(self.stu)
        resp = self.client.get(f"/problems/{self.prob.id}/edit/")
        self.assertNotContains(resp, "readonly")

    def test_editor_readonly_after_deadline(self):
        Assignment.objects.filter(pk=self.prob.assignment_id).update(
            deadline=timezone.now() - timedelta(days=1))
        self.client.force_login(self.stu)
        resp = self.client.get(f"/problems/{self.prob.id}/edit/")
        self.assertContains(resp, 'height:400px" readonly>')

    def test_editor_get_non_member_forbidden(self):
        other = User.objects.create_user("outsider", password="x")
        self.client.force_login(other)
        resp = self.client.get(f"/problems/{self.prob.id}/edit/")
        self.assertEqual(resp.status_code, 403)
