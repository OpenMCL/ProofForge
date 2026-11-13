from unittest.mock import patch

from django.test import TestCase

from accounts.tests.test_login import RecordingProvider


class LoginNextTest(TestCase):
    def _start(self, params):
        with patch("accounts.views.get_provider", return_value=RecordingProvider()):
            self.client.get("/accounts/login/", params)
        return self.client.session["oauth_state"]

    def _callback(self, state):
        with patch("accounts.views.get_provider", return_value=RecordingProvider()):
            return self.client.get("/accounts/callback/", {"code": "c", "state": state})

    def test_redirects_to_next_after_login(self):
        response = self._callback(self._start({"next": "/courses/1/"}))

        self.assertRedirects(response, "/courses/1/", fetch_redirect_response=False)

    def test_external_next_falls_back_to_home(self):
        response = self._callback(self._start({"next": "https://evil.com/"}))

        self.assertRedirects(response, "/", fetch_redirect_response=False)

    def test_protocol_relative_next_falls_back_to_home(self):
        response = self._callback(self._start({"next": "//evil.com/"}))

        self.assertRedirects(response, "/", fetch_redirect_response=False)

    def test_without_next_redirects_home(self):
        response = self._callback(self._start({}))

        self.assertRedirects(response, "/", fetch_redirect_response=False)

    def test_stale_next_is_cleared_by_new_login_start(self):
        self._start({"next": "/courses/1/"})

        response = self._callback(self._start({}))

        self.assertRedirects(response, "/", fetch_redirect_response=False)

    def test_login_required_page_round_trip(self):
        response = self.client.get("/courses/new/")

        self.assertRedirects(
            response, "/accounts/login/?next=/courses/new/", fetch_redirect_response=False
        )
