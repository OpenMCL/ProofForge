from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase
from courses.models import Course, Enrollment
from courses.permissions import require_course_role

class RequireRoleTest(TestCase):
    def setUp(self):
        self.rf = RequestFactory()
        self.prof = User.objects.create(username="prof")
        self.ta = User.objects.create(username="ta")
        self.stu = User.objects.create(username="stu")
        self.course = Course.objects.create(title="C", term="114-1", owner=self.prof)
        Enrollment.objects.create(user=self.prof, course=self.course, role="professor")
        Enrollment.objects.create(user=self.ta, course=self.course, role="ta")
        Enrollment.objects.create(user=self.stu, course=self.course, role="student")

        @require_course_role("professor", "ta")
        def view(request, course_id):
            from django.http import HttpResponse
            return HttpResponse("ok")
        self.view = view

    def _call(self, user):
        req = self.rf.get("/")
        req.user = user
        return self.view(req, course_id=self.course.id)

    def test_ta_allowed(self):
        self.assertEqual(self._call(self.ta).status_code, 200)

    def test_professor_allowed(self):
        self.assertEqual(self._call(self.prof).status_code, 200)

    def test_student_forbidden(self):
        self.assertEqual(self._call(self.stu).status_code, 403)
