from django.contrib.auth.models import User
from django.test import TestCase
from courses.models import Course, Enrollment


class DashboardViewTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("student1", password="x")
        self.course = Course.objects.create(title="線性代數", term="114-1", owner=self.user)
        Enrollment.objects.create(user=self.user, course=self.course, role="student")

        self.user_no_course = User.objects.create_user("student2", password="x")

    def test_enrolled_user_sees_course_title(self):
        self.client.force_login(self.user)
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "線性代數")

    def test_no_enrollments_shows_empty_state(self):
        self.client.force_login(self.user_no_course)
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "你目前沒有加入任何課程")

    def test_anonymous_redirects_to_login(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/accounts/", resp["Location"])