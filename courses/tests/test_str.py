from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from courses.models import Assignment, Course, Problem
from submissions.models import Grade, InlineComment, Submission


class ModelStrTest(TestCase):
    def test_admin_list_labels_identify_the_row(self):
        prof = User.objects.create(username="u-T001")
        student = User.objects.create(username="u-S001")
        course = Course.objects.create(title="線代", term="114-1", owner=prof)
        assignment = Assignment.objects.create(
            course=course, title="作業一", deadline=timezone.now())
        problem = Problem.objects.create(assignment=assignment, number=1, statement="s")
        sub = Submission.objects.create(problem=problem, student=student)

        self.assertEqual(str(assignment), "作業一 (線代)")
        self.assertEqual(str(problem), "1 (作業一)")
        self.assertEqual(str(sub), "1 / u-S001 (draft)")
        self.assertEqual(
            str(Grade.objects.create(submission=sub, score=90, grader=prof)),
            "1 / u-S001 (draft) = 90")
        self.assertEqual(
            str(InlineComment.objects.create(
                submission=sub, anchor_start=1, anchor_end=5, body="b", author=prof)),
            "1 / u-S001 (draft) [1-5]")
