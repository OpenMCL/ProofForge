from urllib.parse import parse_qs, urlparse

from django.contrib.auth.models import AnonymousUser, User
from django.template.loader import render_to_string
from django.test import RequestFactory, TestCase, override_settings

MOCK = "accounts/mock_authorize.html"


@override_settings(ENABLE_MOCK_OAUTH=True, OAUTH_PROVIDER_CLASS="accounts.providers.MockProvider")
class MockAuthorizePageTest(TestCase):
    def test_form_fields_are_labelled_and_student_id_is_required(self):
        response = self.client.get("/accounts/mock-authorize/", {"state": "s1"})

        self.assertTemplateUsed(response, MOCK)
        self.assertContains(response, '<label for="student_id">')
        self.assertContains(response, '<label for="name">')
        self.assertRegex(response.content.decode(), r'<input[^>]*id="student_id"[^>]*required')
        self.assertContains(response, 'name="state" value="s1"')

    def test_page_title_names_mock_login(self):
        response = self.client.get("/accounts/mock-authorize/")

        self.assertContains(response, "<title>開發登入 - ProofForge</title>")

    def test_no_error_shown_on_first_visit(self):
        response = self.client.get("/accounts/mock-authorize/")

        self.assertNotContains(response, "請輸入學號")

    def test_blank_student_id_shows_error_and_keeps_input(self):
        response = self.client.post(
            "/accounts/mock-authorize/",
            {"student_id": "   ", "name": "小明", "state": "s1"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, MOCK)
        self.assertContains(response, "請輸入學號")
        self.assertContains(response, 'value="小明"')
        self.assertContains(response, 'name="state" value="s1"')
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_missing_student_id_field_shows_error(self):
        response = self.client.post("/accounts/mock-authorize/", {"state": "s1"})

        self.assertContains(response, "請輸入學號")

    def test_user_input_is_escaped(self):
        response = self.client.post(
            "/accounts/mock-authorize/",
            {"student_id": "", "name": '"><script>alert(1)</script>', "state": "s1"},
        )

        self.assertNotContains(response, "<script>alert(1)</script>")

    def test_redirect_url_encodes_student_id_and_state(self):
        response = self.client.post(
            "/accounts/mock-authorize/",
            {"student_id": "a&state=evil", "state": "s1"},
        )

        query = parse_qs(urlparse(response.url).query)
        self.assertEqual(query["code"], ["a&state=evil"])
        self.assertEqual(query["state"], ["s1"])
        self.assertEqual(urlparse(response.url).path, "/accounts/callback/")

    def test_encoded_student_id_still_completes_login(self):
        response = self.client.post(
            "/accounts/mock-authorize/",
            {"student_id": "B 1&2", "state": "s1"},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("_auth_user_id", self.client.session)


class BaseLayoutTest(TestCase):
    def render(self, user):
        request = RequestFactory().get("/")
        request.user = user
        return render_to_string("base.html", request=request)

    def test_shows_display_name_of_logged_in_user(self):
        user = User.objects.create_user("B11201001", first_name="王小明")

        self.assertIn("王小明", self.render(user))

    def test_falls_back_to_username_without_display_name(self):
        user = User.objects.create_user("B11201001")

        self.assertIn("B11201001", self.render(user))

    def test_display_name_is_escaped(self):
        user = User.objects.create_user("u1", first_name="<script>alert(1)</script>")

        html = self.render(user)

        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_anonymous_user_sees_no_name(self):
        self.assertNotIn("current-user", self.render(AnonymousUser()))

    def test_default_title(self):
        self.assertIn("<title>ProofForge</title>", self.render(AnonymousUser()))
