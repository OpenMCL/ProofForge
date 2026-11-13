import io
from django.contrib.auth.models import User
from django.test import TestCase
from accounts.models import Profile
from accounts.providers import OAuthIdentity
from accounts.services import link_or_create_user
from courses.models import Course, Enrollment
from courses.roster import import_roster, parse_roster_csv


class NoSelfServiceProfessorTest(TestCase):
    """can_create_course 只能由 admin/後端設定,任何應用層建帳號的路徑都不得給予。"""

    def test_oauth_login_cannot_grant_course_creation(self):
        user = link_or_create_user(
            OAuthIdentity(
                subject="sub-1",
                identifier="T900",
                student_id="T900",
                display_name="冒充者",
            )
        )
        self.assertFalse(user.profile.can_create_course)

    def test_roster_import_creates_students_only(self):
        prof = User.objects.create_user("prof", password="x")
        Profile.objects.create(user=prof, student_id="T1", can_create_course=True)
        course = Course.objects.create(title="C", term="114-1", owner=prof)
        rows, _ = parse_roster_csv("student_id,name\nS900,學生\n")
        import_roster(course, rows)
        profile = Profile.objects.get(student_id="S900")
        self.assertFalse(profile.can_create_course)
        self.assertEqual(
            Enrollment.objects.get(user=profile.user, course=course).role, "student")

    def test_add_ta_cannot_grant_course_creation(self):
        prof = User.objects.create_user("prof2", password="x")
        Profile.objects.create(user=prof, student_id="T2", can_create_course=True)
        course = Course.objects.create(title="C", term="114-1", owner=prof)
        Enrollment.objects.create(user=prof, course=course, role="professor")
        self.client.force_login(prof)
        self.client.post(f"/courses/{course.id}/add-ta/", {"student_id": "G900"})
        profile = Profile.objects.get(student_id="G900")
        self.assertFalse(profile.can_create_course)
        self.assertEqual(
            Enrollment.objects.get(user=profile.user, course=course).role, "ta")

    def test_user_without_flag_cannot_create_course(self):
        user = User.objects.create_user("nobody", password="x")
        Profile.objects.create(user=user, student_id="S901")
        self.client.force_login(user)
        resp = self.client.post("/courses/new/", {"title": "偷開的課", "term": "114-1"})
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(Course.objects.filter(title="偷開的課").exists())
