import datetime
from unittest import mock

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Profile
from courses.models import Assignment, Course, Enrollment, Problem


class CourseViewTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.prof = User.objects.create(username="prof")
        cls.other_prof = User.objects.create(username="other_prof")
        cls.ta = User.objects.create(username="ta")
        cls.student = User.objects.create(username="student")
        cls.outsider = User.objects.create(username="outsider")

        cls.course = Course.objects.create(title="LA", term="115-1", owner=cls.prof)
        cls.other = Course.objects.create(title="Calc", term="115-1", owner=cls.other_prof)
        Enrollment.objects.create(user=cls.prof, course=cls.course, role="professor")
        Enrollment.objects.create(user=cls.other_prof, course=cls.other, role="professor")
        Enrollment.objects.create(user=cls.ta, course=cls.course, role="ta")
        Enrollment.objects.create(user=cls.student, course=cls.course, role="student")
        Profile.objects.create(user=cls.prof, can_create_course=True)
        Profile.objects.create(user=cls.student, student_id="113201001")

        cls.assignment = Assignment.objects.create(
            course=cls.course, title="HW1", deadline=timezone.now())
        cls.other_assignment = Assignment.objects.create(
            course=cls.other, title="HW1", deadline=timezone.now())

    def as_user(self, user):
        self.client.logout()
        if user:
            self.client.force_login(user)


# --------------------------------------------------------------------------- #
# add_ta
# --------------------------------------------------------------------------- #
class AddTaTests(CourseViewTestBase):
    def post(self, user, sid="113201999", course=None):
        self.as_user(user)
        url = reverse("add_ta", args=[(course or self.course).id])
        return self.client.post(url, {"student_id": sid})

    def test_non_professors_cannot_add_ta(self):
        for user in (self.ta, self.student, self.outsider, self.other_prof):
            with self.subTest(user=user.username):
                self.assertEqual(self.post(user).status_code, 403)
        self.assertFalse(Profile.objects.filter(student_id="113201999").exists())

    def test_anonymous_redirected_to_login(self):
        resp = self.post(None)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/accounts/login/", resp["Location"])
        self.assertFalse(Profile.objects.filter(student_id="113201999").exists())

    def test_professor_adds_new_ta_as_placeholder(self):
        self.assertEqual(self.post(self.prof).status_code, 302)
        profile = Profile.objects.get(student_id="113201999")
        self.assertFalse(profile.user.has_usable_password())
        self.assertFalse(profile.oauth_sub)
        self.assertEqual(
            Enrollment.objects.get(user=profile.user, course=self.course).role, "ta")

    def test_professor_promotes_enrolled_student(self):
        self.post(self.prof, sid="113201001")
        self.assertEqual(
            Enrollment.objects.get(user=self.student, course=self.course).role, "ta")

    def test_cannot_demote_professor(self):
        Profile.objects.filter(user=self.prof).update(student_id="900000001")
        self.post(self.prof, sid="900000001")
        self.assertEqual(
            Enrollment.objects.get(user=self.prof, course=self.course).role, "professor")

    def test_invalid_student_id_rejected(self):
        for bad in ("", "   ", "../x", "a" * 21):
            with self.subTest(sid=bad):
                self.assertEqual(self.post(self.prof, sid=bad).status_code, 400)
        self.assertFalse(User.objects.filter(username__startswith="u-").exists())

    def test_missing_field_is_400_not_500(self):
        self.as_user(self.prof)
        resp = self.client.post(reverse("add_ta", args=[self.course.id]), {})
        self.assertEqual(resp.status_code, 400)


# --------------------------------------------------------------------------- #
# course_create
# --------------------------------------------------------------------------- #
class CourseCreateTests(CourseViewTestBase):
    def test_requires_can_create_course(self):
        for user in (self.student, self.outsider):
            with self.subTest(user=user.username):
                self.as_user(user)
                resp = self.client.post(reverse("course_create"), {"title": "X", "term": "115-1"})
                self.assertEqual(resp.status_code, 403)

    def test_creator_becomes_owner_and_professor(self):
        self.as_user(self.prof)
        resp = self.client.post(reverse("course_create"), {"title": "New", "term": "115-1"})
        self.assertEqual(resp.status_code, 302)
        course = Course.objects.get(title="New")
        self.assertEqual(course.owner, self.prof)
        self.assertEqual(Enrollment.objects.get(user=self.prof, course=course).role, "professor")

    def test_invalid_input_is_400_and_creates_nothing(self):
        self.as_user(self.prof)
        before = Course.objects.count()
        for data in ({}, {"title": "X"}, {"title": "", "term": "115-1"},
                     {"title": "a" * 201, "term": "115-1"}):
            with self.subTest(data=data):
                self.assertEqual(self.client.post(reverse("course_create"), data).status_code, 400)
        self.assertEqual(Course.objects.count(), before)


# --------------------------------------------------------------------------- #
# assignment_create / problem_create
# --------------------------------------------------------------------------- #
class AssignmentCreateTests(CourseViewTestBase):
    def url(self, course=None):
        return reverse("assignment_create", args=[(course or self.course).id])

    def test_outsiders_and_students_forbidden(self):
        for user in (self.student, self.outsider, self.other_prof):
            with self.subTest(user=user.username):
                self.as_user(user)
                resp = self.client.post(self.url(), {"title": "HW", "deadline": "2026-10-01T23:59"})
                self.assertEqual(resp.status_code, 403)

    def test_datetime_local_input_becomes_taipei_aware(self):
        self.as_user(self.ta)
        resp = self.client.post(self.url(), {"title": "HW2", "deadline": "2026-10-01T23:59"})
        self.assertEqual(resp.status_code, 302)
        deadline = Assignment.objects.get(title="HW2").deadline
        self.assertTrue(timezone.is_aware(deadline))
        self.assertEqual(deadline, datetime.datetime(2026, 10, 1, 15, 59, tzinfo=datetime.timezone.utc))

    def test_bad_deadline_is_400(self):
        self.as_user(self.ta)
        for data in ({"title": "HW"}, {"title": "HW", "deadline": "tomorrow"},
                     {"title": "HW", "deadline": "2026-10-01T23:59+08:00"}):
            with self.subTest(data=data):
                resp = self.client.post(self.url(), data)
                self.assertIn(resp.status_code, (302, 400))
                self.assertNotEqual(resp.status_code, 500)
        self.assertFalse(Assignment.objects.filter(title="HW", deadline__isnull=True).exists())

    def test_form_page_has_labels_and_context(self):
        self.as_user(self.prof)
        resp = self.client.get(self.url())
        self.assertEqual(resp.status_code, 200)
        for text in ('<label for="assignment-title">', 'id="assignment-title"',
                     '<label for="assignment-description">', 'id="assignment-description"',
                     '<label for="assignment-deadline">', 'id="assignment-deadline"',
                     'type="datetime-local"', "標題", "說明", "截止時間", str(self.course),
                     reverse("course_detail", args=[self.course.id])):
            self.assertContains(resp, text)
        self.assertNotContains(resp, "None")

    def test_invalid_post_shows_errors_and_keeps_input(self):
        self.as_user(self.prof)
        before = Assignment.objects.count()
        resp = self.client.post(self.url(), {"title": "HW9", "description": "第九次作業",
                                             "deadline": "tomorrow"})
        self.assertEqual(resp.status_code, 400)
        self.assertContains(resp, "截止時間：", status_code=400)
        self.assertContains(resp, 'value="HW9"', status_code=400)
        self.assertContains(resp, "第九次作業", status_code=400)
        self.assertContains(resp, 'value="tomorrow"', status_code=400)
        self.assertEqual(Assignment.objects.count(), before)


class ProblemCreateTests(CourseViewTestBase):
    def url(self, assignment, course=None):
        return reverse("problem_create", args=[(course or self.course).id, assignment.id])

    def test_assignment_from_other_course_is_404(self):
        self.as_user(self.prof)
        resp = self.client.post(self.url(self.other_assignment), {"number": "1", "statement": "s"})
        self.assertEqual(resp.status_code, 404)
        self.assertFalse(Problem.objects.exists())

    def test_creates_problem(self):
        self.as_user(self.prof)
        resp = self.client.post(self.url(self.assignment), {"number": "1", "statement": "s"})
        self.assertEqual(resp.status_code, 302)
        problem = Problem.objects.get()
        self.assertEqual((problem.number, problem.statement), (1, "s"))

    def test_form_page_has_labels_and_context(self):
        self.as_user(self.prof)
        resp = self.client.get(self.url(self.assignment))
        self.assertEqual(resp.status_code, 200)
        for text in ('for="problem-number"', 'for="problem-statement"',
                     "題號", "題目內容", str(self.course), self.assignment.title,
                     reverse("course_detail", args=[self.course.id])):
            self.assertContains(resp, text)
        self.assertNotContains(resp, "None")

    def test_invalid_post_shows_errors_and_keeps_input(self):
        self.as_user(self.prof)
        resp = self.client.post(self.url(self.assignment),
                                {"number": "", "statement": "證明 X"})
        self.assertEqual(resp.status_code, 400)
        self.assertContains(resp, "題號：", status_code=400)
        self.assertContains(resp, "證明 X", status_code=400)
        self.assertFalse(Problem.objects.exists())

    def test_duplicate_number_in_same_assignment_is_400(self):
        Problem.objects.create(assignment=self.assignment, number=1, statement="舊題")
        self.as_user(self.prof)
        resp = self.client.post(self.url(self.assignment), {"number": "1", "statement": "新題內容"})
        self.assertEqual(resp.status_code, 400)
        self.assertContains(resp, "這份作業已經有第 1 題", status_code=400)
        self.assertContains(resp, "新題內容", status_code=400)
        self.assertEqual(Problem.objects.filter(assignment=self.assignment).count(), 1)

    def test_same_number_in_another_assignment_is_ok(self):
        Problem.objects.create(assignment=self.assignment, number=1, statement="s")
        hw2 = Assignment.objects.create(course=self.course, title="HW2", deadline=timezone.now())
        self.as_user(self.prof)
        resp = self.client.post(self.url(hw2), {"number": "1", "statement": "s"})
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Problem.objects.filter(assignment=hw2, number=1).exists())

    def test_race_hitting_db_constraint_is_400_not_500(self):
        """兩人同時建立同題號：表單檢查都通過，第二筆被 DB 約束擋下。"""
        from courses.forms import ProblemForm
        Problem.objects.create(assignment=self.assignment, number=1, statement="s")
        self.as_user(self.prof)
        with mock.patch.object(ProblemForm, "clean_number",
                               lambda form: form.cleaned_data["number"]):
            resp = self.client.post(self.url(self.assignment), {"number": "1", "statement": "s"})
        self.assertEqual(resp.status_code, 400)
        self.assertContains(resp, "這份作業已經有第 1 題", status_code=400)
        self.assertEqual(Problem.objects.filter(assignment=self.assignment).count(), 1)

    def test_form_page_lists_existing_numbers(self):
        for n in (2, 1):
            Problem.objects.create(assignment=self.assignment, number=n, statement="s")
        self.as_user(self.prof)
        resp = self.client.get(self.url(self.assignment))
        self.assertContains(resp, "這份作業已有題號：1、2")

    def test_non_numeric_or_non_positive_number_is_400(self):
        self.as_user(self.prof)
        for number in ("2(a)", "abc", "0", "-1", "1.5"):
            with self.subTest(number=number):
                resp = self.client.post(self.url(self.assignment),
                                        {"number": number, "statement": "s"})
                self.assertEqual(resp.status_code, 400)
        self.assertFalse(Problem.objects.exists())


# --------------------------------------------------------------------------- #
# roster_import
# --------------------------------------------------------------------------- #
class RosterImportTests(CourseViewTestBase):
    def upload(self, content: bytes, user=None, name="roster.csv"):
        self.as_user(user or self.prof)
        f = SimpleUploadedFile(name, content, content_type="text/csv")
        return self.client.post(reverse("roster_import", args=[self.course.id]), {"file": f})

    def enrolled_sids(self):
        return set(
            Profile.objects.filter(user__enrollments__course=self.course,
                                   user__enrollments__role="student")
            .values_list("student_id", flat=True))

    def test_students_and_outsiders_forbidden(self):
        for user in (self.student, self.outsider, self.other_prof):
            with self.subTest(user=user.username):
                resp = self.upload(b"student_id,name\n113209999,X\n", user=user)
                self.assertEqual(resp.status_code, 403)
        self.assertFalse(Profile.objects.filter(student_id="113209999").exists())

    def test_utf8_with_bom_from_excel(self):
        resp = self.upload("student_id,name\n113201002,王小明\n".encode("utf-8-sig"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("113201002", self.enrolled_sids())

    def test_big5_cp950_from_excel(self):
        resp = self.upload("student_id,name\n113201003,陳大文\n".encode("cp950"))
        self.assertEqual(resp.status_code, 302)
        user = Profile.objects.get(student_id="113201003").user
        self.assertEqual(user.first_name, "陳大文")
        self.assertFalse(user.has_usable_password())

    def test_missing_file_is_400(self):
        self.as_user(self.prof)
        resp = self.client.post(reverse("roster_import", args=[self.course.id]), {})
        self.assertEqual(resp.status_code, 400)

    def test_undecodable_file_is_400(self):
        resp = self.upload(b"\xff\xfe\x00\x81\x82garbage")
        self.assertEqual(resp.status_code, 400)

    def test_oversized_file_is_400(self):
        resp = self.upload(b"student_id,name\n" + b"113201004,x\n" * 200_000)
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(Profile.objects.filter(student_id="113201004").exists())

    def test_wrong_header_reported_once(self):
        resp = self.upload("學號,姓名\n113201005,X\n".encode("utf-8"))
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(len(resp.context["errors"]), 1)

    def test_invalid_and_duplicate_rows(self):
        content = ("student_id,name\n"
                   "113201006,A\n"
                   "113201006,A again\n"
                   "../etc,B\n"
                   ",C\n").encode("utf-8")
        resp = self.upload(content)
        self.assertEqual(resp.status_code, 200)       # 部分成功：顯示錯誤清單
        self.assertEqual(len(resp.context["errors"]), 3)
        self.assertEqual(Profile.objects.filter(student_id="113201006").count(), 1)
        self.assertFalse(Profile.objects.filter(student_id="../etc").exists())

    def test_existing_ta_not_demoted_by_roster(self):
        Profile.objects.create(user=self.ta, student_id="113201007")
        self.upload(b"student_id,name\n113201007,T\n")
        self.assertEqual(Enrollment.objects.get(user=self.ta, course=self.course).role, "ta")


# --------------------------------------------------------------------------- #
# roster_add（名單頁表格內單筆加入）
# --------------------------------------------------------------------------- #
class RosterAddTests(CourseViewTestBase):
    def url(self, course=None):
        return reverse("roster_add", args=[(course or self.course).id])

    def roster_url(self):
        return reverse("roster_import", args=[self.course.id])

    def test_prof_and_ta_add_new_student_as_placeholder(self):
        for i, user in enumerate((self.prof, self.ta)):
            sid = f"11320900{i}"
            with self.subTest(user=user.username):
                self.as_user(user)
                resp = self.client.post(self.url(), {"student_id": sid, "name": "新同學"})
                self.assertRedirects(resp, self.roster_url(), fetch_redirect_response=False)
                placeholder = Profile.objects.get(student_id=sid).user
                self.assertEqual(placeholder.username, f"u-{sid}")
                self.assertEqual(placeholder.first_name, "新同學")
                self.assertEqual(
                    Enrollment.objects.get(user=placeholder, course=self.course).role, "student")
                page = self.client.get(self.roster_url())
                self.assertContains(page, f"已加入 {sid}")
                self.assertContains(page, sid)

    def test_strips_whitespace(self):
        self.as_user(self.prof)
        self.client.post(self.url(), {"student_id": "  113209100 ", "name": " 甲 "})
        self.assertEqual(Profile.objects.get(student_id="113209100").user.first_name, "甲")

    def test_existing_member_role_unchanged(self):
        Profile.objects.create(user=self.ta, student_id="113209200")
        self.as_user(self.prof)
        before = Enrollment.objects.count()
        for sid in ("113201001", "113209200"):  # 本課學生、本課助教
            with self.subTest(sid=sid):
                resp = self.client.post(self.url(), {"student_id": sid}, follow=True)
                self.assertContains(resp, f"{sid} 已在名單中，未變更")
        self.assertEqual(Enrollment.objects.count(), before)
        self.assertEqual(Enrollment.objects.get(user=self.ta, course=self.course).role, "ta")

    def test_existing_account_is_reused(self):
        other = User.objects.create(username="logged-in")
        Profile.objects.create(user=other, student_id="113209300", oauth_sub="sub-1")
        self.as_user(self.prof)
        users_before = User.objects.count()
        self.client.post(self.url(), {"student_id": "113209300"})
        self.assertEqual(User.objects.count(), users_before)
        self.assertEqual(Enrollment.objects.get(user=other, course=self.course).role, "student")

    def test_invalid_student_id_is_400_and_keeps_input(self):
        self.as_user(self.prof)
        before = Enrollment.objects.count()
        for sid in ("", "a b", "x" * 21):
            with self.subTest(sid=sid):
                resp = self.client.post(self.url(), {"student_id": sid, "name": "保留我"})
                self.assertEqual(resp.status_code, 400)
                self.assertContains(resp, "學號：", status_code=400)
                self.assertContains(resp, 'value="保留我"', status_code=400)
                self.assertContains(resp, 'id="roster-add-form"', status_code=400)
        self.assertEqual(Enrollment.objects.count(), before)

    def test_forbidden_roles(self):
        for user in (self.student, self.outsider, self.other_prof):
            with self.subTest(user=user.username):
                self.as_user(user)
                resp = self.client.post(self.url(), {"student_id": "113209400"})
                self.assertEqual(resp.status_code, 403)
        self.assertFalse(Profile.objects.filter(student_id="113209400").exists())

    def test_anonymous_redirected_to_login(self):
        self.as_user(None)
        resp = self.client.post(self.url(), {"student_id": "113209400"})
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(resp["Location"].startswith("/accounts/login/"))

    def test_get_not_allowed(self):
        self.as_user(self.prof)
        self.assertEqual(self.client.get(self.url()).status_code, 405)

    def test_roster_page_has_inline_add_row(self):
        self.as_user(self.ta)
        resp = self.client.get(self.roster_url())
        for text in ('id="roster-add-form"', f'action="{self.url()}"', 'form="roster-add-form"',
                     'for="add-student-id"', 'for="add-name"', ">加入</button>"):
            self.assertContains(resp, text)
        self.assertNotContains(resp, "None")
