from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from courses.models import Course, Assignment, Problem

class AssignmentTest(TestCase):
    def test_problem_belongs_to_assignment_ordered(self):
        prof = User.objects.create(username="prof")
        c = Course.objects.create(title="C", term="114-1", owner=prof)
        a = Assignment.objects.create(course=c, title="HW1", description="d",
                                      deadline=timezone.now())
        Problem.objects.create(assignment=a, number=10, statement="證明...")
        Problem.objects.create(assignment=a, number=2, statement="證明...")
        Problem.objects.create(assignment=a, number=1, statement="證明...")
        # 依題號數值排序：2 在 10 前面（不是字串排序）
        numbers = list(a.problems.values_list("number", flat=True))
        self.assertEqual(numbers, [1, 2, 10])
