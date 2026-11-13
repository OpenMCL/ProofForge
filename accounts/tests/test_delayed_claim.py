import datetime

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Profile
from accounts.providers import OAuthIdentity
from accounts.services import get_or_create_placeholder, link_or_create_user
from courses.models import Assignment, Course, Enrollment, Problem
from courses.roster import import_roster
from submissions.models import Submission

SID = "113201001"


def identity(sub="stu01", sid=None):
    return OAuthIdentity(subject=sub, identifier=sub, display_name="學生", student_id=sid)


class DelayedClaimTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.prof = User.objects.create(username="prof")
        cls.course_a = Course.objects.create(title="LA", term="115-1", owner=cls.prof)
        cls.course_b = Course.objects.create(title="Calc", term="115-1", owner=cls.prof)

    def enroll_placeholder(self, *courses, sid=SID):
        # 使用真正的匯入流程建立佔位帳號
        for course in courses:
            import_roster(course, [{"student_id": sid, "name": "學生"}])
        return Profile.objects.get(student_id=sid).user

    # ---- 既有路徑不受影響 ------------------------------------------------ #

    def test_first_login_with_student_id_claims_placeholder(self):
        placeholder = self.enroll_placeholder(self.course_a)
        user = link_or_create_user(identity(sid=SID))
        self.assertEqual(user, placeholder)                 # 直接綁定佔位帳號本身
        self.assertEqual(user.profile.oauth_sub, "stu01")

    def test_first_login_without_student_id_creates_account(self):
        self.enroll_placeholder(self.course_a)
        user = link_or_create_user(identity())
        self.assertIsNone(user.profile.student_id)
        self.assertFalse(user.enrollments.exists())         # 帳號分裂的起點

    # ---- 情況一：沒有人使用這個學號 ------------------------------------- #

    def test_later_login_attaches_student_id(self):
        user = link_or_create_user(identity())
        with self.assertLogs("proofforge.audit", "INFO") as logs:
            again = link_or_create_user(identity(sid=SID))
        self.assertEqual(again, user)
        user.profile.refresh_from_db()
        self.assertEqual(user.profile.student_id, SID)
        self.assertIn("attach student_id", logs.output[0])

    def test_roster_after_attach_enrolls_real_account(self):
        user = link_or_create_user(identity())
        link_or_create_user(identity(sid=SID))
        import_roster(self.course_a, [{"student_id": SID, "name": "學生"}])
        self.assertTrue(user.enrollments.filter(course=self.course_a).exists())
        self.assertEqual(User.objects.filter(username=f"u-{SID}").count(), 0)

    # ---- 情況二：認領佔位帳號 ---------------------------------------------- #

    def test_split_account_is_merged_on_later_login(self):
        placeholder = self.enroll_placeholder(self.course_a, self.course_b)
        user = link_or_create_user(identity())               # 第一次：拒絕提供學號
        self.assertNotEqual(user, placeholder)

        with self.assertLogs("proofforge.audit", "INFO") as logs:
            again = link_or_create_user(identity(sid=SID))   # 第二次：同意提供
        self.assertEqual(again, user)
        self.assertFalse(User.objects.filter(pk=placeholder.pk).exists())
        user.profile.refresh_from_db()
        self.assertEqual(user.profile.student_id, SID)
        self.assertEqual(
            set(user.enrollments.values_list("course__title", "role")),
            {("LA", "student"), ("Calc", "student")})
        self.assertIn(f"placeholder={placeholder.pk}", logs.output[0])
        self.assertIn("moved=2 skipped=0", logs.output[0])

    def test_existing_role_wins_on_same_course(self):
        placeholder = self.enroll_placeholder(self.course_a, self.course_b)
        user = link_or_create_user(identity())
        Enrollment.objects.create(user=user, course=self.course_a, role="ta")
        link_or_create_user(identity(sid=SID))
        self.assertEqual(Enrollment.objects.get(user=user, course=self.course_a).role, "ta")
        self.assertEqual(Enrollment.objects.get(user=user, course=self.course_b).role, "student")
        self.assertFalse(User.objects.filter(pk=placeholder.pk).exists())

    def test_claim_is_idempotent(self):
        self.enroll_placeholder(self.course_a)
        user = link_or_create_user(identity())
        link_or_create_user(identity(sid=SID))
        before = list(user.enrollments.values_list("course_id", "role"))
        self.assertEqual(link_or_create_user(identity(sid=SID)), user)
        self.assertEqual(list(user.enrollments.values_list("course_id", "role")), before)

    def test_claim_aborted_if_placeholder_has_submission(self):
        placeholder = self.enroll_placeholder(self.course_a)
        assignment = Assignment.objects.create(
            course=self.course_a, title="HW", deadline=timezone.now() + datetime.timedelta(days=1))
        problem = Problem.objects.create(assignment=assignment, number="1", statement="s")
        Submission.objects.create(problem=problem, student=placeholder, content_markdown="x")

        user = link_or_create_user(identity())
        with self.assertLogs("proofforge.audit", "ERROR") as logs:
            link_or_create_user(identity(sid=SID))
        self.assertTrue(User.objects.filter(pk=placeholder.pk).exists())
        self.assertTrue(Submission.objects.filter(student=placeholder).exists())
        user.profile.refresh_from_db()
        self.assertIsNone(user.profile.student_id)
        self.assertIn("claim aborted", logs.output[0])

    # ---- 情況三：學號屬於已綁定的帳號 ------------------------------------- #

    def test_student_id_owned_by_linked_account_is_left_alone(self):
        owner = link_or_create_user(identity(sub="owner", sid=SID))
        user = link_or_create_user(identity(sub="someone"))
        with self.assertLogs("proofforge.audit", "WARNING") as logs:
            again = link_or_create_user(identity(sub="someone", sid=SID))
        self.assertEqual(again, user)                        # 照常登入自己的帳號
        user.profile.refresh_from_db()
        self.assertIsNone(user.profile.student_id)
        owner.profile.refresh_from_db()
        self.assertEqual(owner.profile.student_id, SID)
        self.assertIn("already linked", logs.output[0])

    def test_stored_student_id_is_never_overwritten(self):
        user = link_or_create_user(identity(sid=SID))
        with self.assertLogs("proofforge.audit", "WARNING"):
            link_or_create_user(identity(sid="999999999"))
        user.profile.refresh_from_db()
        self.assertEqual(user.profile.student_id, SID)


class DashboardHintTests(TestCase):
    def get(self, user):
        self.client.force_login(user)
        return self.client.get(reverse("dashboard")).context["needs_student_id"]

    def test_hint_for_account_without_student_id_or_courses(self):
        user = link_or_create_user(identity())
        self.assertTrue(self.get(user))

    def test_no_hint_when_student_id_known(self):
        user = link_or_create_user(identity(sid=SID))
        self.assertFalse(self.get(user))

    def test_no_hint_for_staff_with_courses(self):
        user = link_or_create_user(identity(sub="prof01"))
        course = Course.objects.create(title="LA", term="115-1", owner=user)
        Enrollment.objects.create(user=user, course=course, role="professor")
        self.assertFalse(self.get(user))
