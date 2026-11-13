from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from courses.models import Course, Assignment, Problem
from submissions.models import Submission, InlineComment, Grade, finalize_grade

class GradeTest(TestCase):
    def setUp(self):
        self.prof = User.objects.create(username="prof")
        self.stu = User.objects.create(username="stu")
        c = Course.objects.create(title="C", term="114-1", owner=self.prof)
        a = Assignment.objects.create(course=c, title="HW", description="",
            deadline=timezone.now())
        p = Problem.objects.create(assignment=a, number="1", statement="s")
        self.sub = Submission.objects.create(problem=p, student=self.stu, content_markdown="x")

    def test_inline_comment_anchor(self):
        ic = InlineComment.objects.create(submission=self.sub, anchor_start=0,
            anchor_end=3, body="這步跳了", author=self.prof)
        self.assertEqual((ic.anchor_start, ic.anchor_end), (0, 3))

    def test_finalize_grade_locks_submission(self):
        g = finalize_grade(self.sub, score=85, overall_comment="不錯", grader=self.prof)
        self.sub.refresh_from_db()
        self.assertEqual(g.score, 85)
        self.assertTrue(self.sub.locked)

    def test_finalize_grade_duplicate_returns_none_not_error(self):
        finalize_grade(self.sub, score=90, overall_comment="一", grader=self.prof)
        self.sub.status = "draft"  # 模擬第二個 grader 手上仍是 draft 的 stale 物件
        g2 = finalize_grade(self.sub, score=10, overall_comment="二", grader=self.prof)
        self.assertIsNone(g2)  # 乾淨略過,不可拋 IntegrityError
        self.assertEqual(Grade.objects.filter(submission=self.sub).count(), 1)
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.grade.score, 90)  # 保留第一次的分數

    def test_finalize_grade_duplicate_leaves_no_extra_inline_comment(self):
        finalize_grade(self.sub, score=90, overall_comment="一", grader=self.prof,
            inline_comment={"anchor_start": 0, "anchor_end": 2, "body": "好"})
        self.sub.status = "draft"  # 模擬第二個 grader 的 stale 物件
        g2 = finalize_grade(self.sub, score=10, overall_comment="二", grader=self.prof,
            inline_comment={"anchor_start": 0, "anchor_end": 1, "body": "多餘評論"})
        self.assertIsNone(g2)
        self.assertEqual(InlineComment.objects.filter(submission=self.sub).count(), 1)
