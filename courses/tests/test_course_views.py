from datetime import timedelta
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from accounts.models import Profile
from courses.models import Assignment, Course, Enrollment, Problem

class CourseCreateTest(TestCase):
    def _user(self, can_create):
        u = User.objects.create_user("prof", password="x")
        Profile.objects.create(user=u, student_id="T1", can_create_course=can_create)
        return u

    def test_forbidden_without_flag(self):
        self.client.force_login(self._user(False))
        resp = self.client.post("/courses/new/", {"title": "C", "term": "114-1"})
        self.assertEqual(resp.status_code, 403)

    def test_creates_course_and_professor_enrollment(self):
        u = self._user(True)
        self.client.force_login(u)
        resp = self.client.post("/courses/new/", {"title": "C", "term": "114-1"})
        self.assertEqual(resp.status_code, 302)
        course = Course.objects.get(title="C")
        self.assertTrue(Enrollment.objects.filter(
            user=u, course=course, role="professor").exists())


class CourseDetailRosterLinkTest(TestCase):
    def setUp(self):
        self.prof = User.objects.create_user("detail-prof", password="x")
        self.ta = User.objects.create_user("detail-ta", password="x")
        self.student = User.objects.create_user("detail-student", password="x")
        self.course = Course.objects.create(title="C", term="114-1", owner=self.prof)
        Enrollment.objects.create(user=self.prof, course=self.course, role="professor")
        Enrollment.objects.create(user=self.ta, course=self.course, role="ta")
        Enrollment.objects.create(user=self.student, course=self.course, role="student")

    def test_professor_sees_roster_import_link(self):
        self.client.force_login(self.prof)
        response = self.client.get(f"/courses/{self.course.id}/")
        self.assertContains(response, "學生名單")
        self.assertContains(response, f"/courses/{self.course.id}/roster/")

    def test_ta_sees_roster_import_link(self):
        self.client.force_login(self.ta)
        response = self.client.get(f"/courses/{self.course.id}/")
        self.assertContains(response, "學生名單")

    def test_student_does_not_see_roster_import_link(self):
        self.client.force_login(self.student)
        response = self.client.get(f"/courses/{self.course.id}/")
        self.assertNotContains(response, "學生名單")


class CourseDetailAddTALinkTest(TestCase):
    def setUp(self):
        self.prof = User.objects.create_user("add-ta-prof", password="x")
        self.ta = User.objects.create_user("add-ta-ta", password="x")
        self.student = User.objects.create_user("add-ta-student", password="x")
        self.course = Course.objects.create(title="C", term="114-1", owner=self.prof)
        Enrollment.objects.create(user=self.prof, course=self.course, role="professor")
        Enrollment.objects.create(user=self.ta, course=self.course, role="ta")
        Enrollment.objects.create(user=self.student, course=self.course, role="student")

    def test_professor_sees_add_ta_link(self):
        self.client.force_login(self.prof)
        response = self.client.get(f"/courses/{self.course.id}/")
        self.assertContains(response, "新增助教")
        self.assertContains(response, f"/courses/{self.course.id}/add-ta/")

    def test_ta_does_not_see_add_ta_link(self):
        self.client.force_login(self.ta)
        response = self.client.get(f"/courses/{self.course.id}/")
        self.assertNotContains(response, "新增助教")

    def test_student_does_not_see_add_ta_link(self):
        self.client.force_login(self.student)
        response = self.client.get(f"/courses/{self.course.id}/")
        self.assertNotContains(response, "新增助教")
class CourseDetailAssignmentCreateLinkTest(TestCase):
    def setUp(self):
        self.prof = User.objects.create_user("assignment-link-prof", password="x")
        self.ta = User.objects.create_user("assignment-link-ta", password="x")
        self.student = User.objects.create_user("assignment-link-student", password="x")
        self.course = Course.objects.create(title="C", term="114-1", owner=self.prof)
        Enrollment.objects.create(user=self.prof, course=self.course, role="professor")
        Enrollment.objects.create(user=self.ta, course=self.course, role="ta")
        Enrollment.objects.create(user=self.student, course=self.course, role="student")

    def test_professor_sees_assignment_create_link(self):
        self.client.force_login(self.prof)
        response = self.client.get(f"/courses/{self.course.id}/")
        self.assertContains(response, f"/courses/{self.course.id}/assignments/new/")

    def test_ta_sees_assignment_create_link(self):
        self.client.force_login(self.ta)
        response = self.client.get(f"/courses/{self.course.id}/")
        self.assertContains(response, f"/courses/{self.course.id}/assignments/new/")

    def test_student_does_not_see_assignment_create_link(self):
        self.client.force_login(self.student)
        response = self.client.get(f"/courses/{self.course.id}/")
        self.assertNotContains(response, f"/courses/{self.course.id}/assignments/new/")


class CourseDetailProblemCreateLinkTest(TestCase):
    def setUp(self):
        self.prof = User.objects.create_user("problem-prof", password="x")
        self.ta = User.objects.create_user("problem-ta", password="x")
        self.student = User.objects.create_user("problem-student", password="x")
        self.course = Course.objects.create(title="C", term="114-1", owner=self.prof)
        Enrollment.objects.create(user=self.prof, course=self.course, role="professor")
        Enrollment.objects.create(user=self.ta, course=self.course, role="ta")
        Enrollment.objects.create(user=self.student, course=self.course, role="student")
        self.assignment = Assignment.objects.create(
            course=self.course,
            title="HW1",
            deadline="2026-09-01T23:59:00+08:00",
        )
        self.problem_create_url = (
            f"/courses/{self.course.id}/assignments/"
            f"{self.assignment.id}/problems/new/"
        )

    def test_professor_and_ta_see_problem_create_link(self):
        for user in (self.prof, self.ta):
            with self.subTest(role=user.enrollments.get(course=self.course).role):
                self.client.force_login(user)
                response = self.client.get(f"/courses/{self.course.id}/")
                self.assertContains(response, self.problem_create_url)
                self.assertContains(response, "建立題目")

    def test_student_does_not_see_problem_create_link(self):
        self.client.force_login(self.student)
        response = self.client.get(f"/courses/{self.course.id}/")
        self.assertNotContains(response, self.problem_create_url)
        self.assertNotContains(response, "建立題目")


class CourseDetailSubmissionLinkTest(TestCase):
    def setUp(self):
        self.prof = User.objects.create_user("submission-link-prof", password="x")
        self.ta = User.objects.create_user("submission-link-ta", password="x")
        self.student = User.objects.create_user("submission-link-student", password="x")
        self.course = Course.objects.create(
            title="C", term="114-1", owner=self.prof
        )
        Enrollment.objects.create(
            user=self.prof, course=self.course, role="professor"
        )
        Enrollment.objects.create(user=self.ta, course=self.course, role="ta")
        Enrollment.objects.create(
            user=self.student, course=self.course, role="student"
        )
        assignment = Assignment.objects.create(
            course=self.course,
            title="HW",
            description="",
            deadline=timezone.now() + timedelta(days=1),
        )
        self.problem = Problem.objects.create(
            assignment=assignment,
            number="1",
            statement="Prove it",
        )

    def test_professor_sees_problem_submission_link(self):
        self.client.force_login(self.prof)
        response = self.client.get(f"/courses/{self.course.id}/")
        self.assertContains(response, "查看提交")
        self.assertContains(response, f"/problems/{self.problem.id}/submissions/")

    def test_ta_sees_problem_submission_link(self):
        self.client.force_login(self.ta)
        response = self.client.get(f"/courses/{self.course.id}/")
        self.assertContains(response, "查看提交")
        self.assertContains(response, f"/problems/{self.problem.id}/submissions/")

    def test_student_does_not_see_problem_submission_link(self):
        self.client.force_login(self.student)
        response = self.client.get(f"/courses/{self.course.id}/")
        self.assertNotContains(response, "查看提交")
        self.assertNotContains(response, f"/problems/{self.problem.id}/submissions/")


class CourseDetailEditorLinkTest(TestCase):
    def setUp(self):
        self.prof = User.objects.create_user("editor-link-prof", password="x")
        self.ta = User.objects.create_user("editor-link-ta", password="x")
        self.student = User.objects.create_user("editor-link-student", password="x")
        self.course = Course.objects.create(title="C", term="114-1", owner=self.prof)
        Enrollment.objects.create(user=self.prof, course=self.course, role="professor")
        Enrollment.objects.create(user=self.ta, course=self.course, role="ta")
        Enrollment.objects.create(user=self.student, course=self.course, role="student")
        assignment = Assignment.objects.create(
            course=self.course,
            title="HW",
            description="",
            deadline=timezone.now() + timedelta(days=1),
        )
        self.problem = Problem.objects.create(
            assignment=assignment,
            number="1",
            statement="Prove it",
        )

    def test_student_sees_problem_number_and_editor_link(self):
        self.client.force_login(self.student)
        response = self.client.get(f"/courses/{self.course.id}/")
        self.assertContains(response, self.problem.number)
        self.assertContains(response, "開始作答")
        self.assertContains(response, reverse("editor", args=[self.problem.id]))

    def test_professor_sees_problem_number_without_editor_link(self):
        self.client.force_login(self.prof)
        response = self.client.get(f"/courses/{self.course.id}/")
        self.assertContains(response, self.problem.number)
        self.assertNotContains(response, "開始作答")
        self.assertNotContains(response, reverse("editor", args=[self.problem.id]))

    def test_ta_sees_problem_number_without_editor_link(self):
        self.client.force_login(self.ta)
        response = self.client.get(f"/courses/{self.course.id}/")
        self.assertContains(response, self.problem.number)
        self.assertNotContains(response, "開始作答")
        self.assertNotContains(response, reverse("editor", args=[self.problem.id]))


class CourseDetailHomeLinkTest(TestCase):
    def test_every_role_sees_home_link(self):
        prof = User.objects.create_user("home-prof", password="x")
        course = Course.objects.create(title="C", term="115-1", owner=prof)
        for role in ("professor", "ta", "student"):
            user = prof if role == "professor" else User.objects.create_user(f"home-{role}", password="x")
            if role != "professor":
                Enrollment.objects.create(user=user, course=course, role=role)
            else:
                Enrollment.objects.create(user=prof, course=course, role="professor")
            with self.subTest(role=role):
                self.client.force_login(user)
                response = self.client.get(f"/courses/{course.id}/")
                self.assertContains(response, f'<a href="{reverse("dashboard")}">回到首頁</a>',
                                    count=1, html=True)

    def test_home_link_comes_from_base_on_other_pages(self):
        prof = User.objects.create_user("home-prof2", password="x")
        Profile.objects.create(user=prof, student_id="T2", can_create_course=True)
        self.client.force_login(prof)
        for url in (reverse("dashboard"), reverse("course_create")):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertContains(response, f'<a href="{reverse("dashboard")}">回到首頁</a>',
                                    count=1, html=True)

    def test_anonymous_login_error_page_has_no_home_link(self):
        response = self.client.get(reverse("oauth_callback"))
        self.assertNotContains(response, "回到首頁", status_code=400)


class CourseDetailDeadlineTest(TestCase):
    def test_deadline_shown_after_title_in_taipei_time(self):
        import datetime
        prof = User.objects.create_user("dl-prof", password="x")
        student = User.objects.create_user("dl-stu", password="x")
        course = Course.objects.create(title="C", term="115-1", owner=prof)
        Enrollment.objects.create(user=prof, course=course, role="professor")
        Enrollment.objects.create(user=student, course=course, role="student")
        # 2026-12-01 15:59 UTC = 2026-12-01 23:59 台北
        Assignment.objects.create(
            course=course, title="HW1",
            deadline=datetime.datetime(2026, 12, 1, 15, 59, tzinfo=datetime.timezone.utc))
        for user in (prof, student):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                response = self.client.get(f"/courses/{course.id}/")
                self.assertContains(response, "<p>HW1（截止：2026-12-01 23:59）")
