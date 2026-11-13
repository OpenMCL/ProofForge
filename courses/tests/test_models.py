from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone
from courses.models import Assignment, Course, Enrollment, Problem
from courses.permissions import get_role

class EnrollmentTest(TestCase):
    def setUp(self):
        self.prof = User.objects.create(username="prof")
        self.stu = User.objects.create(username="stu")
        self.course = Course.objects.create(title="實分析", term="114-1", owner=self.prof)

    def test_get_role_returns_enrolled_role(self):
        Enrollment.objects.create(user=self.stu, course=self.course, role="student")
        self.assertEqual(get_role(self.stu, self.course), "student")

    def test_get_role_none_when_not_enrolled(self):
        self.assertIsNone(get_role(self.stu, self.course))

    def test_enrollment_unique_per_user_course(self):
        Enrollment.objects.create(user=self.stu, course=self.course, role="student")
        with self.assertRaises(Exception):
            Enrollment.objects.create(user=self.stu, course=self.course, role="ta")



class ProblemNumberUniqueTest(TestCase):
    def setUp(self):
        prof = User.objects.create(username="prof")
        course = Course.objects.create(title="C", term="115-1", owner=prof)
        self.hw1 = Assignment.objects.create(course=course, title="HW1", deadline=timezone.now())
        self.hw2 = Assignment.objects.create(course=course, title="HW2", deadline=timezone.now())
        Problem.objects.create(assignment=self.hw1, number=1, statement="s")

    def test_same_assignment_same_number_rejected_by_db(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Problem.objects.create(assignment=self.hw1, number=1, statement="s")

    def test_other_assignment_same_number_allowed(self):
        Problem.objects.create(assignment=self.hw2, number=1, statement="s")
        self.assertEqual(Problem.objects.filter(number=1).count(), 2)
