from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from accounts.models import Profile
from courses.models import Course, Enrollment, Assignment, Problem

class AssignmentViewTest(TestCase):
    def setUp(self):
        self.ta = User.objects.create_user("ta", password="x")
        Profile.objects.create(user=self.ta, student_id="G1")
        self.course = Course.objects.create(title="C", term="114-1", owner=self.ta)
        Enrollment.objects.create(user=self.ta, course=self.course, role="ta")

    def test_ta_creates_assignment_then_problem(self):
        self.client.force_login(self.ta)
        r1 = self.client.post(f"/courses/{self.course.id}/assignments/new/",
            {"title": "HW1", "description": "d", "deadline": "2026-09-01 23:59"})
        self.assertEqual(r1.status_code, 302)
        a = Assignment.objects.get(title="HW1")
        r2 = self.client.post(
            f"/courses/{self.course.id}/assignments/{a.id}/problems/new/",
            {"number": "1", "statement": "證明 $a^2$"})
        self.assertEqual(r2.status_code, 302)
        self.assertEqual(Problem.objects.filter(assignment=a).count(), 1)

    def test_student_forbidden(self):
        stu = User.objects.create_user("stu", password="x")
        Profile.objects.create(user=stu, student_id="B1")
        Enrollment.objects.create(user=stu, course=self.course, role="student")
        self.client.force_login(stu)
        r = self.client.post(f"/courses/{self.course.id}/assignments/new/",
            {"title": "X", "description": "", "deadline": "2026-09-01 23:59"})
        self.assertEqual(r.status_code, 403)

    def test_student_cannot_get_problem_create(self):
        stu = User.objects.create_user("problem-stu", password="x")
        Profile.objects.create(user=stu, student_id="B2")
        Enrollment.objects.create(user=stu, course=self.course, role="student")
        assignment = Assignment.objects.create(
            course=self.course, title="HW", deadline=timezone.now()
        )
        self.client.force_login(stu)
        response = self.client.get(
            f"/courses/{self.course.id}/assignments/{assignment.id}/problems/new/"
        )
        self.assertEqual(response.status_code, 403)
