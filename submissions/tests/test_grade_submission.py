import datetime
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from courses.models import Assignment, Course, Enrollment, Problem
from submissions.models import (
    Grade, GradingNotOpen, InlineComment, Submission, finalize_grade, regrade,
)

CONTENT = "Let $x \\in V$. Then $Tx = \\lambda x$."


class GradeTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.prof = User.objects.create(username="prof")
        cls.ta = User.objects.create(username="ta")
        cls.student = User.objects.create(username="student")
        cls.classmate = User.objects.create(username="classmate")
        cls.outsider = User.objects.create(username="outsider")
        cls.other_ta = User.objects.create(username="other_ta")
        cls.other_prof = User.objects.create(username="other_prof")

        cls.course = Course.objects.create(title="LA", term="115-1", owner=cls.prof)
        cls.other = Course.objects.create(title="Calc", term="115-1", owner=cls.other_prof)
        for user, course, role in [
            (cls.prof, cls.course, "professor"),
            (cls.ta, cls.course, "ta"),
            (cls.student, cls.course, "student"),
            (cls.classmate, cls.course, "student"),
            (cls.other_prof, cls.other, "professor"),
            (cls.other_ta, cls.other, "ta"),
        ]:
            Enrollment.objects.create(user=user, course=course, role=role)

        past = timezone.now() - datetime.timedelta(hours=1)
        future = timezone.now() + datetime.timedelta(days=1)
        closed = Assignment.objects.create(course=cls.course, title="HW1", deadline=past)
        still_open = Assignment.objects.create(course=cls.course, title="HW2", deadline=future)
        cls.problem = Problem.objects.create(assignment=closed, number="1", statement="s")
        cls.future_problem = Problem.objects.create(assignment=still_open, number="1", statement="s")

    def setUp(self):
        self.sub = Submission.objects.create(
            problem=self.problem, student=self.student, content_markdown=CONTENT)

    def post(self, user, data=None, sub=None):
        self.client.logout()
        if user:
            self.client.force_login(user)
        url = reverse("grade_submission", args=[(sub or self.sub).id])
        return self.client.post(url, data if data is not None else {"score": "8"})

    def assert_not_graded(self):
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.status, "draft")
        self.assertFalse(Grade.objects.filter(submission=self.sub).exists())

    def before_deadline_sub(self):
        return Submission.objects.create(
            problem=self.future_problem, student=self.student, content_markdown=CONTENT)


class GradeSubmissionTests(GradeTestBase):
    # ---- authorization ------------------------------------------------ #

    def test_anonymous_redirected(self):
        resp = self.post(None)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/accounts/login/", resp["Location"])
        self.assert_not_graded()

    def test_non_staff_and_other_course_staff_forbidden(self):
        for user in (self.student, self.classmate, self.outsider, self.other_ta, self.other_prof):
            with self.subTest(user=user.username):
                self.assertEqual(self.post(user).status_code, 403)
        self.assert_not_graded()

    def test_non_staff_cannot_view_grading_page(self):
        for user in (self.classmate, self.other_ta):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                resp = self.client.get(reverse("grade_submission", args=[self.sub.id]))
                self.assertEqual(resp.status_code, 403)

    def test_course_ta_and_professor_can_grade(self):
        for user in (self.ta, self.prof):
            with self.subTest(user=user.username):
                Grade.objects.all().delete()
                Submission.objects.filter(pk=self.sub.pk).update(status="draft")
                resp = self.post(user, {"score": "8", "overall_comment": "good"})
                self.assertEqual(resp.status_code, 302)
                grade = Grade.objects.get(submission=self.sub)
                self.assertEqual((grade.score, grade.grader), (8, user))

    # ---- input validation --------------------------------------------- #

    def test_bad_score_is_400(self):
        for data in ({}, {"score": ""}, {"score": "abc"}, {"score": "-1"}, {"score": "1.5"}):
            with self.subTest(data=data):
                self.assertEqual(self.post(self.ta, data).status_code, 400)
        self.assert_not_graded()

    def test_valid_inline_comment_saved(self):
        data = {"score": "8", "body": "why?", "anchor_start": "4", "anchor_end": "12"}
        self.assertEqual(self.post(self.ta, data).status_code, 302)
        c = InlineComment.objects.get(submission=self.sub)
        self.assertEqual((c.anchor_start, c.anchor_end, c.body, c.author),
                         (4, 12, "why?", self.ta))

    def test_bad_inline_comment_is_400(self):
        n = len(CONTENT)
        cases = [
            {"body": "x"},                                              # 沒有位置
            {"body": "x", "anchor_start": "3"},                         # 缺 anchor_end
            {"body": "x", "anchor_start": "5", "anchor_end": "2"},      # start > end
            {"body": "x", "anchor_start": "0", "anchor_end": str(n + 1)},  # 超出內容
            {"body": "x", "anchor_start": "-1", "anchor_end": "2"},     # 負數
            {"body": "x", "anchor_start": "a", "anchor_end": "2"},      # 非整數
        ]
        for extra in cases:
            with self.subTest(data=extra):
                self.assertEqual(self.post(self.ta, {"score": "8", **extra}).status_code, 400)
        self.assert_not_graded()
        self.assertFalse(InlineComment.objects.exists())

    def test_anchor_at_end_of_content_allowed(self):
        n = len(CONTENT)
        data = {"score": "8", "body": "x", "anchor_start": str(n), "anchor_end": str(n)}
        self.assertEqual(self.post(self.ta, data).status_code, 302)

    # ---- deadline -------------------------------------------------------- #

    def test_cannot_grade_before_deadline(self):
        sub = self.before_deadline_sub()
        resp = self.post(self.ta, {"score": "8"}, sub=sub)
        self.assertEqual(resp.status_code, 409)
        sub.refresh_from_db()
        self.assertEqual(sub.status, "draft")          # 學生仍可繼續編輯
        self.assertFalse(Grade.objects.filter(submission=sub).exists())

    def test_staff_can_view_before_deadline(self):
        sub = self.before_deadline_sub()
        self.client.force_login(self.ta)
        resp = self.client.get(reverse("grade_submission", args=[sub.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.context["grading_open"])

    def test_finalize_grade_enforces_deadline_itself(self):
        sub = self.before_deadline_sub()
        with self.assertRaises(GradingNotOpen):
            finalize_grade(sub, 8, "", self.ta)
        sub.refresh_from_db()
        self.assertEqual(sub.status, "draft")

    # ---- regrade ---------------------------------------------------------- #

    def test_regrade_updates_score_and_keeps_lock(self):
        self.assertEqual(self.post(self.ta, {"score": "8", "overall_comment": "ok"}).status_code, 302)
        with self.assertLogs("proofforge.audit", level="INFO") as logs:
            resp = self.post(self.prof, {"score": "3", "overall_comment": "revised"})
        self.assertEqual(resp.status_code, 302)
        grade = Grade.objects.get(submission=self.sub)
        self.assertEqual((grade.score, grade.overall_comment, grade.grader), (3, "revised", self.prof))
        self.assertEqual(Grade.objects.filter(submission=self.sub).count(), 1)
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.status, "graded")
        self.assertIn("score=8->3", logs.output[0])
        self.assertIn(f"previous_grader={self.ta.pk}", logs.output[0])

    def test_regrade_prefills_current_values(self):
        self.post(self.ta, {"score": "8", "overall_comment": "ok"})
        self.client.force_login(self.ta)
        resp = self.client.get(reverse("grade_submission", args=[self.sub.id]))
        self.assertEqual(resp.context["form"].initial, {"score": 8, "overall_comment": "ok"})

    def test_regrade_adds_inline_comment_keeps_old_ones(self):
        self.post(self.ta, {"score": "8", "body": "a", "anchor_start": "0", "anchor_end": "3"})
        self.post(self.ta, {"score": "9", "body": "b", "anchor_start": "4", "anchor_end": "6"})
        self.assertEqual(
            list(InlineComment.objects.filter(submission=self.sub)
                 .order_by("id").values_list("body", flat=True)), ["a", "b"])

    def test_invalid_regrade_is_400_and_keeps_old_grade(self):
        self.post(self.ta, {"score": "8"})
        self.assertEqual(self.post(self.ta, {"score": "-5"}).status_code, 400)
        self.assertEqual(Grade.objects.get(submission=self.sub).score, 8)

    def test_other_course_staff_cannot_regrade(self):
        self.post(self.ta, {"score": "8"})
        for user in (self.other_ta, self.other_prof, self.classmate):
            with self.subTest(user=user.username):
                self.assertEqual(self.post(user, {"score": "0"}).status_code, 403)
        self.assertEqual(Grade.objects.get(submission=self.sub).score, 8)

    # ---- concurrent first grading ---------------------------------------- #

    def test_finalize_grade_is_single_winner(self):
        first = finalize_grade(self.sub, 8, "", self.ta)
        second = finalize_grade(self.sub, 3, "", self.prof)
        self.assertIsNotNone(first)
        self.assertIsNone(second)
        self.assertEqual(Grade.objects.filter(submission=self.sub).count(), 1)

    def test_lost_first_grading_race_is_409(self):
        # 模擬：頁面讀取時還沒有 Grade，但寫入時已被其他人搶先完成
        with patch("submissions.views.finalize_grade", return_value=None):
            resp = self.post(self.prof, {"score": "3"})
        self.assertEqual(resp.status_code, 409)


class GradeDetailTemplateTests(GradeTestBase):
    """grade_detail.html 必須讓批改者看得到狀態與錯誤，而不只是回傳正確的狀態碼。"""

    def page(self, user=None, sub=None):
        self.client.force_login(user or self.ta)
        return self.client.get(reverse("grade_submission", args=[(sub or self.sub).id]))

    def test_before_deadline_form_is_disabled(self):
        sub = self.before_deadline_sub()
        resp = self.page(sub=sub)
        self.assertContains(resp, "作業尚未截止")
        self.assertContains(resp, "<fieldset disabled>", html=False)

    def test_first_grading_page(self):
        resp = self.page()
        self.assertNotContains(resp, "作業尚未截止")
        self.assertNotContains(resp, "<fieldset disabled>", html=False)
        self.assertContains(resp, "送出評分")

    def test_regrade_page_shows_current_grade_and_prefills(self):
        self.post(self.ta, {"score": "8", "overall_comment": "ok",
                            "body": "注意", "anchor_start": "0", "anchor_end": "3"})
        resp = self.page(user=self.prof)
        self.assertContains(resp, "目前分數為 8")
        self.assertContains(resp, 'value="8"')
        self.assertContains(resp, "修改分數")
        self.assertContains(resp, "注意")                      # 既有的行內評論

    def test_validation_errors_are_shown(self):
        resp = self.post(self.ta, {"score": "-1"})
        self.assertContains(resp, "送出的資料有誤", status_code=400)
        self.assertContains(resp, 'value="-1"', status_code=400)  # 保留使用者輸入

    def test_conflict_message_is_shown(self):
        with patch("submissions.views.finalize_grade", return_value=None):
            resp = self.post(self.prof, {"score": "3"})
        self.assertContains(resp, "剛剛已有其他人完成批改", status_code=409)

    def test_content_is_escaped(self):
        Submission.objects.filter(pk=self.sub.pk).update(
            content_markdown="<script>alert(1)</script>")
        resp = self.page()
        self.assertNotContains(resp, "<script>alert(1)</script>")
        self.assertContains(resp, "&lt;script&gt;alert(1)&lt;/script&gt;")

    def test_leading_newline_in_content_survives_html_parsing(self):
        Submission.objects.filter(pk=self.sub.pk).update(content_markdown="\nabc")
        resp = self.page()
        self.assertContains(resp, '<pre id="content">\n\nabc</pre>')
