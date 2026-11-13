from django.contrib.auth.models import AnonymousUser, User
from django.template.loader import render_to_string
from django.test import RequestFactory, TestCase


class BaseTemplateTest(TestCase):
    def setUp(self):
        self.request = RequestFactory().get("/")

    def test_authenticated_user_sees_logout_form(self):
        self.request.user = User.objects.create_user("student")

        html = render_to_string("base.html", request=self.request)

        # 登出必須是帶 CSRF token 的 POST 表單，不能是 GET 連結
        self.assertIn('action="/accounts/logout/"', html)
        self.assertIn('method="post"', html)
        self.assertIn("csrfmiddlewaretoken", html)
        self.assertNotIn('href="/accounts/logout/"', html)
        self.assertIn("登出", html)

    def test_anonymous_user_does_not_see_logout_form(self):
        self.request.user = AnonymousUser()

        html = render_to_string("base.html", request=self.request)

        self.assertNotIn('action="/accounts/logout/"', html)
        self.assertNotIn("登出", html)