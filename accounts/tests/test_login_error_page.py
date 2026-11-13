from unittest.mock import patch

from django.test import TestCase

from accounts import services
from accounts.tests.test_login import RecordingProvider

TEMPLATE = "accounts/login_error.html"


class LoginErrorPageTest(TestCase):
    def setUp(self):
        session = self.client.session
        session["oauth_state"] = "expected-state"
        session.save()

    def _callback(self, params, provider=None):
        params = {"state": "expected-state", **params}
        with patch("accounts.views.get_provider", return_value=provider or RecordingProvider()):
            return self.client.get("/accounts/callback/", params)

    def _set_next(self, url):
        session = self.client.session
        session["oauth_next"] = url
        session.save()

    def assertErrorPage(self, response, status, retry=True):
        self.assertEqual(response.status_code, status)
        self.assertTemplateUsed(response, TEMPLATE)
        if retry:
            self.assertContains(response, 'href="/accounts/login/"', status_code=status)
        else:
            self.assertNotContains(response, 'href="/accounts/login/', status_code=status)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_invalid_state_renders_error_page(self):
        self.assertErrorPage(self._callback({"code": "c", "state": "attacker"}), 400)

    def test_missing_state_renders_error_page(self):
        session = self.client.session
        del session["oauth_state"]
        session.save()

        self.assertErrorPage(self._callback({"code": "c"}), 400)

    def test_provider_denied_authorization_renders_error_page(self):
        response = self._callback({"error": "access_denied"})

        self.assertErrorPage(response, 400)
        self.assertNotContains(response, "access_denied", status_code=400)

    def test_missing_code_renders_error_page(self):
        self.assertErrorPage(self._callback({}), 400)

    def test_provider_failure_renders_error_page_without_details(self):
        response = self._callback({"code": "c"}, provider=RecordingProvider(exchange_error=True))

        self.assertErrorPage(response, 502)
        self.assertNotContains(response, "upstream details", status_code=502)

    def test_account_conflict_renders_error_page_without_details(self):
        with patch(
            "accounts.views.link_or_create_user",
            side_effect=services.AccountLinkConflict("private conflict"),
        ):
            response = self._callback({"code": "c"})

        self.assertErrorPage(response, 409, retry=False)
        self.assertNotContains(response, "private conflict", status_code=409)

    def test_each_error_has_its_own_message(self):
        bad_state = self._callback({"code": "c", "state": "attacker"}).content
        session = self.client.session
        session["oauth_state"] = "expected-state"
        session.save()
        provider_down = self._callback(
            {"code": "c"}, provider=RecordingProvider(exchange_error=True)
        ).content

        self.assertNotEqual(bad_state, provider_down)

    def test_error_page_extends_base_layout(self):
        response = self._callback({"code": "c", "state": "attacker"})

        self.assertTemplateUsed(response, "base.html")

    def test_page_title_shows_error_title(self):
        response = self._callback({"code": "c", "state": "attacker"})

        self.assertContains(response, "<title>登入驗證失敗 - ProofForge</title>", status_code=400)

    def test_retry_link_keeps_next_destination(self):
        self._set_next("/courses/1/")

        response = self._callback({"code": "c", "state": "attacker"})

        self.assertContains(response, 'href="/accounts/login/?next=/courses/1/"', status_code=400)

    def test_retry_link_drops_external_next(self):
        self._set_next("https://evil.com/")

        response = self._callback({"code": "c", "state": "attacker"})

        self.assertContains(response, 'href="/accounts/login/"', status_code=400)
        self.assertNotContains(response, "evil.com", status_code=400)
