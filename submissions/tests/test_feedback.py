from datetime import timedelta
from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from accounts.models import Profile
from courses.models import Course, Enrollment, Assignment, Problem
from submissions.models import Submission, InlineComment, finalize_grade

class FeedbackTest(TestCase):
    def setUp(self):
        prof = User.objects.create_user("prof", password="x")
        self.stu = User.objects.create_user("stu", password="x")
        Profile.objects.create(user=self.stu, student_id="B1")
        c = Course.objects.create(title="C", term="114-1", owner=prof)
        Enrollment.objects.create(user=self.stu, course=c, role="student")
        a = Assignment.objects.create(course=c, title="HW", description="",
            deadline=timezone.now() - timedelta(days=1))
        self.prob = Problem.objects.create(assignment=a, number="1", statement="s")
        self.sub = Submission.objects.create(problem=self.prob, student=self.stu,
            content_markdown="證明")
        InlineComment.objects.create(submission=self.sub, anchor_start=0, anchor_end=1,
            body="注意這步", author=prof)
        finalize_grade(self.sub, score=88, overall_comment="整體不錯", grader=prof)

    def test_student_sees_score_and_comments(self):
        self.client.force_login(self.stu)
        resp = self.client.get(f"/problems/{self.prob.id}/feedback/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "88")
        self.assertContains(resp, "整體不錯")
        self.assertContains(resp, "注意這步")

    def test_other_student_forbidden(self):
        other = User.objects.create_user("other", password="x")
        Profile.objects.create(user=other, student_id="B2")
        c = self.prob.assignment.course
        Enrollment.objects.create(user=other, course=c, role="student")
        self.client.force_login(other)
        resp = self.client.get(f"/problems/{self.prob.id}/feedback/")
        # other 沒有自己的 submission → 顯示尚未繳交/批改,但看不到別人的
        self.assertNotContains(resp, "整體不錯")
