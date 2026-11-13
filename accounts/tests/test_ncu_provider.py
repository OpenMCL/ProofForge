from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlsplit

import requests
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, override_settings

from accounts.ncu_provider import NCUPortalProvider
from accounts.provider_loader import get_provider
from accounts.providers import OAuthProviderError

CREDS = {"NCU_OAUTH_CLIENT_ID": "cid", "NCU_OAUTH_CLIENT_SECRET": "secret"}
PROVIDER_PATH = "accounts.ncu_provider.NCUPortalProvider"


def fake_response(json_data=None, status=200, json_error=False):
    resp = MagicMock()
    if json_error:
        resp.json.side_effect = ValueError("not json")
    else:
        resp.json.return_value = json_data
    resp.raise_for_status.side_effect = (
        requests.HTTPError(str(status)) if status >= 400 else None
    )
    return resp


STUDENT = {
    "id": 1234567890123,
    "identifier": "113201001",
    "chineseName": "王小明",
    "studentId": "113201001",
    "email": "a@ncu.edu.tw",
    "emailVerified": True,
}


@override_settings(**CREDS)
class ConfigurationTests(SimpleTestCase):
    @override_settings(NCU_OAUTH_CLIENT_SECRET="")
    def test_missing_credentials_rejected(self):
        with self.assertRaises(ValueError):
            NCUPortalProvider()

    @override_settings(NCU_OAUTH_CLIENT_SECRET="", OAUTH_PROVIDER_CLASS=PROVIDER_PATH)
    def test_loader_turns_missing_credentials_into_improperly_configured(self):
        with self.assertRaises(ImproperlyConfigured):
            get_provider()

    @override_settings(OAUTH_PROVIDER_CLASS=PROVIDER_PATH)
    def test_loader_accepts_provider(self):
        self.assertIsInstance(get_provider(), NCUPortalProvider)

    @override_settings(NCU_PORTAL_BASE_URL="http://portal-test.example")
    def test_plain_http_base_url_rejected(self):
        with self.assertRaises(ValueError):
            NCUPortalProvider()

    @override_settings(NCU_PORTAL_BASE_URL="https://portal-test.example/")
    def test_test_host_override(self):
        url = NCUPortalProvider().get_authorize_url("s", "https://app/cb")
        self.assertTrue(url.startswith("https://portal-test.example/oauth2/authorization?"))


@override_settings(**CREDS)
class AuthorizeUrlTests(SimpleTestCase):
    def test_authorize_url_parameters(self):
        url = NCUPortalProvider().get_authorize_url("st", "https://app/accounts/callback/")
        parts = urlsplit(url)
        q = {k: v[0] for k, v in parse_qs(parts.query).items()}
        self.assertEqual(parts.netloc, "portal.ncu.edu.tw")
        self.assertEqual(parts.path, "/oauth2/authorization")
        self.assertEqual(q["response_type"], "code")
        self.assertEqual(q["client_id"], "cid")
        self.assertEqual(q["state"], "st")
        self.assertEqual(q["redirect_uri"], "https://app/accounts/callback/")
        self.assertEqual(q["scope"].split(" "), ["identifier", "chinese-name", "student-id", "email"])


@override_settings(**CREDS)
class ExchangeCodeTests(SimpleTestCase):
    def setUp(self):
        self.p = NCUPortalProvider()

    @patch("accounts.ncu_provider.requests.post")
    def test_success_uses_basic_auth_and_accept_header(self, mock_post):
        mock_post.return_value = fake_response({"access_token": "tok"})
        self.assertEqual(self.p.exchange_code("c", "https://app/cb"), "tok")
        kwargs = mock_post.call_args.kwargs
        self.assertEqual(kwargs["auth"], ("cid", "secret"))
        self.assertEqual(kwargs["headers"]["Accept"], "application/json")
        self.assertEqual(kwargs["data"]["redirect_uri"], "https://app/cb")
        self.assertIn("timeout", kwargs)

    @patch("accounts.ncu_provider.requests.post")
    def test_error_in_body_with_200(self, mock_post):
        mock_post.return_value = fake_response({"error": "invalid_grant"})
        with self.assertRaises(OAuthProviderError):
            self.p.exchange_code("c", "https://app/cb")

    @patch("accounts.ncu_provider.requests.post")
    def test_http_error(self, mock_post):
        mock_post.return_value = fake_response({"error": "x"}, status=400)
        with self.assertRaises(OAuthProviderError):
            self.p.exchange_code("c", "https://app/cb")

    @patch("accounts.ncu_provider.requests.post")
    def test_timeout(self, mock_post):
        mock_post.side_effect = requests.Timeout()
        with self.assertRaises(OAuthProviderError):
            self.p.exchange_code("c", "https://app/cb")

    @patch("accounts.ncu_provider.requests.post")
    def test_non_json(self, mock_post):
        mock_post.return_value = fake_response(json_error=True)
        with self.assertRaises(OAuthProviderError):
            self.p.exchange_code("c", "https://app/cb")

    @patch("accounts.ncu_provider.requests.post")
    def test_missing_or_bad_token(self, mock_post):
        for body in ({}, {"access_token": ""}, {"access_token": 123}, ["tok"]):
            mock_post.return_value = fake_response(body)
            with self.subTest(body=body), self.assertRaises(OAuthProviderError):
                self.p.exchange_code("c", "https://app/cb")


@override_settings(**CREDS)
class FetchIdentityTests(SimpleTestCase):
    def setUp(self):
        self.p = NCUPortalProvider()

    def fetch(self, mock_get, body, **kw):
        mock_get.return_value = fake_response(body, **kw)
        return self.p.fetch_identity("tok")

    @patch("accounts.ncu_provider.requests.get")
    def test_student_mapping_uses_identifier_not_id(self, mock_get):
        identity = self.fetch(mock_get, STUDENT)
        self.assertEqual(identity.subject, "113201001")
        self.assertEqual(identity.identifier, "113201001")
        self.assertEqual(identity.display_name, "王小明")
        self.assertEqual(identity.student_id, "113201001")
        self.assertEqual(identity.email, "a@ncu.edu.tw")
        self.assertEqual(mock_get.call_args.kwargs["headers"]["Authorization"], "Bearer tok")

    @patch("accounts.ncu_provider.requests.get")
    def test_numeric_student_id_becomes_string(self, mock_get):
        identity = self.fetch(mock_get, {**STUDENT, "studentId": 113201001})
        self.assertEqual(identity.student_id, "113201001")

    @patch("accounts.ncu_provider.requests.get")
    def test_declined_optional_scopes(self, mock_get):
        identity = self.fetch(mock_get, {"id": 1, "identifier": "113201001"})
        self.assertIsNone(identity.student_id)
        self.assertEqual(identity.email, "")
        self.assertEqual(identity.display_name, "")

    @patch("accounts.ncu_provider.requests.get")
    def test_unverified_email_dropped(self, mock_get):
        for flag in (False, None, "true", 1):
            with self.subTest(flag=flag):
                identity = self.fetch(mock_get, {**STUDENT, "emailVerified": flag})
                self.assertEqual(identity.email, "")

    @patch("accounts.ncu_provider.requests.get")
    def test_delegated_login_rejected(self, mock_get):
        body = {**STUDENT, "delegator": {"identifier": "prof01", "chineseName": "X", "delegateId": 7}}
        with self.assertRaises(OAuthProviderError):
            self.fetch(mock_get, body)

    @patch("accounts.ncu_provider.requests.get")
    def test_null_delegator_allowed(self, mock_get):
        self.assertEqual(self.fetch(mock_get, {**STUDENT, "delegator": None}).subject, "113201001")

    @patch("accounts.ncu_provider.requests.get")
    def test_missing_or_malformed_identifier(self, mock_get):
        for bad in (None, "", "   ", {"x": 1}, ["a"], True):
            with self.subTest(identifier=bad), self.assertRaises(ValueError):
                self.fetch(mock_get, {**STUDENT, "identifier": bad})

    @patch("accounts.ncu_provider.requests.get")
    def test_non_object_response(self, mock_get):
        for body in (["x"], "x", None):
            with self.subTest(body=body), self.assertRaises(OAuthProviderError):
                self.fetch(mock_get, body)

    @patch("accounts.ncu_provider.requests.get")
    def test_network_and_http_errors(self, mock_get):
        mock_get.side_effect = requests.ConnectionError()
        with self.assertRaises(OAuthProviderError):
            self.p.fetch_identity("tok")
        mock_get.side_effect = None
        with self.assertRaises(OAuthProviderError):
            self.fetch(mock_get, {}, status=401)
        with self.assertRaises(OAuthProviderError):
            self.fetch(mock_get, None, json_error=True)
