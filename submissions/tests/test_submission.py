from datetime import timedelta
from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from courses.models import Course, Assignment, Problem
from submissions.models import Submission

class SubmissionTest(TestCase):
    def setUp(self):
        prof = User.objects.create(username="prof")
        self.stu = User.objects.create(username="stu")
        c = Course.objects.create(title="C", term="114-1", owner=prof)
        self.open = Assignment.objects.create(course=c, title="HW", description="",
            deadline=timezone.now() + timedelta(days=1))
        self.prob = Problem.objects.create(assignment=self.open, number="1",
            statement="s")

    def test_unique_per_problem_student(self):
        Submission.objects.create(problem=self.prob, student=self.stu, content_markdown="a")
        with self.assertRaises(Exception):
            Submission.objects.create(problem=self.prob, student=self.stu, content_markdown="b")

    def test_locked_when_graded(self):
        s = Submission.objects.create(problem=self.prob, student=self.stu,
            content_markdown="a", status="graded")
        self.assertTrue(s.locked)

    def test_save_draft_content_saves_while_draft(self):
        s = Submission.objects.create(problem=self.prob, student=self.stu, content_markdown="a")
        saved = s.save_draft_content("更新內容")
        self.assertTrue(saved)
        s.refresh_from_db()
        self.assertEqual(s.content_markdown, "更新內容")

    def test_save_draft_content_refuses_after_deadline(self):
        # 模擬:載入 s 後、寫回前,截止時間已過
        s = Submission.objects.create(problem=self.prob, student=self.stu, content_markdown="a")
        Assignment.objects.filter(pk=self.open.pk).update(
            deadline=timezone.now() - timedelta(seconds=1))
        saved = s.save_draft_content("截止後的修改")
        self.assertFalse(saved)
        s.refresh_from_db()
        self.assertEqual(s.content_markdown, "a")

    def test_save_draft_content_refuses_when_concurrently_graded(self):
        # 模擬:載入 s(draft)後、寫回前,批改者把它設成 graded
        s = Submission.objects.create(problem=self.prob, student=self.stu, content_markdown="a")
        Submission.objects.filter(pk=s.pk).update(status="graded")
        saved = s.save_draft_content("遲來的修改")  # s 此時是 stale 的 draft 實例
        self.assertFalse(saved)
        s.refresh_from_db()
        self.assertEqual(s.status, "graded")       # 不可被解鎖
        self.assertEqual(s.content_markdown, "a")  # 內容不可被覆蓋
