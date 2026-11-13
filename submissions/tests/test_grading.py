from datetime import timedelta
from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from accounts.models import Profile
from courses.models import Course, Enrollment, Assignment, Problem
from submissions.models import Submission, InlineComment

class GradingViewTest(TestCase):
    def setUp(self):
        self.ta = User.objects.create_user("ta", password="x")
        Profile.objects.create(user=self.ta, student_id="G1")
        self.stu = User.objects.create_user("stu", password="x")
        Profile.objects.create(user=self.stu, student_id="B1")
        c = Course.objects.create(title="C", term="114-1", owner=self.ta)
        Enrollment.objects.create(user=self.ta, course=c, role="ta")
        Enrollment.objects.create(user=self.stu, course=c, role="student")
        a = Assignment.objects.create(course=c, title="HW", description="",
            deadline=timezone.now() - timedelta(days=1))
        self.prob = Problem.objects.create(assignment=a, number="1", statement="s")
        self.sub = Submission.objects.create(problem=self.prob, student=self.stu,
            content_markdown="證明內容")

    def test_ta_grades_with_inline_comment_and_locks(self):
        self.client.force_login(self.ta)
        resp = self.client.post(f"/submissions/{self.sub.id}/grade/", {
            "score": "90", "overall_comment": "很好",
            "anchor_start": "0", "anchor_end": "2", "body": "這裡很棒"})
        self.assertEqual(resp.status_code, 302)
        self.sub.refresh_from_db()
        self.assertTrue(self.sub.locked)
        self.assertEqual(self.sub.grade.score, 90)
        self.assertEqual(InlineComment.objects.filter(submission=self.sub).count(), 1)

    def test_student_cannot_grade(self):
        self.client.force_login(self.stu)
        resp = self.client.post(f"/submissions/{self.sub.id}/grade/",
            {"score": "10", "overall_comment": ""})
        self.assertEqual(resp.status_code, 403)

    def test_student_cannot_list_submissions(self):
        self.client.force_login(self.stu)
        resp = self.client.get(f"/problems/{self.prob.id}/submissions/")
        self.assertEqual(resp.status_code, 403)

    def test_regrade_updates_score_and_keeps_lock(self):
        from submissions.models import Grade
        self.client.force_login(self.ta)
        # First grade
        self.client.post(f"/submissions/{self.sub.id}/grade/",
            {"score": "90", "overall_comment": "ok"})
        self.sub.refresh_from_db()
        self.assertTrue(self.sub.locked)
        # Second POST — 修改分數（regrade），仍只有一筆 Grade，submission 維持鎖定
        resp = self.client.post(f"/submissions/{self.sub.id}/grade/",
            {"score": "50", "overall_comment": "changed"})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Grade.objects.filter(submission=self.sub).count(), 1)
        grade = Grade.objects.get(submission=self.sub)
        self.assertEqual((grade.score, grade.overall_comment), (50, "changed"))
        self.sub.refresh_from_db()
        self.assertTrue(self.sub.locked)

    def test_outsider_cannot_list_submissions(self):
        outsider = User.objects.create_user("outsider1", password="x")
        self.client.force_login(outsider)
        resp = self.client.get(f"/problems/{self.prob.id}/submissions/")
        self.assertEqual(resp.status_code, 403)

    def test_outsider_cannot_grade(self):
        outsider = User.objects.create_user("outsider2", password="x")
        self.client.force_login(outsider)
        resp = self.client.get(f"/submissions/{self.sub.id}/grade/")
        self.assertEqual(resp.status_code, 403)
