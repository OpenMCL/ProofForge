from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from accounts.models import Profile
from accounts import services
from accounts.providers import OAuthIdentity, OAuthProvider, OAuthProviderError


class RecordingProvider(OAuthProvider):
    def __init__(self, exchange_error=False):
        self.authorize_call = None
        self.exchange_call = None
        self.exchange_error = exchange_error

    def get_authorize_url(self, state, redirect_uri):
        self.authorize_call = (state, redirect_uri)
        return "/provider/authorize/"

    def exchange_code(self, code, redirect_uri):
        self.exchange_call = (code, redirect_uri)
        if self.exchange_error:
            raise OAuthProviderError("upstream details must stay private")
        return "token"

    def fetch_identity(self, token):
        return OAuthIdentity(subject="subject-1", identifier="person-1")

class LinkUserTest(TestCase):
    def test_links_existing_profile_by_subject(self):
        user = User.objects.create(username="existing")
        Profile.objects.create(user=user, oauth_sub="subject-1")

        result = services.link_or_create_user(
            OAuthIdentity(subject="subject-1", identifier="faculty")
        )

        self.assertEqual(result.pk, user.pk)

    def test_links_unbound_existing_profile_by_student_id(self):
        user = User.objects.create(username="placeholder")
        profile = Profile.objects.create(user=user, student_id="B001")

        result = services.link_or_create_user(
            OAuthIdentity(
                subject="subject-1", identifier="B001", student_id="B001"
            )
        )

        self.assertEqual(result.pk, user.pk)
        profile.refresh_from_db()
        self.assertEqual(profile.oauth_sub, "subject-1")

    def test_creates_faculty_without_student_id(self):
        result = services.link_or_create_user(
            OAuthIdentity(
                subject="faculty-1",
                identifier="teacher",
                display_name="Teacher Name",
                email="teacher@example.test",
            )
        )

        self.assertIsNone(result.profile.student_id)
        self.assertEqual(result.username, "teacher")
        self.assertEqual(result.first_name, "Teacher Name")
        self.assertEqual(result.email, "teacher@example.test")

    def test_rejects_student_id_bound_to_another_subject(self):
        user = User.objects.create(username="existing")
        Profile.objects.create(
            user=user, student_id="B001", oauth_sub="original-subject"
        )

        with self.assertRaises(services.AccountLinkConflict):
            services.link_or_create_user(
                OAuthIdentity(
                    subject="attacker-subject",
                    identifier="B001",
                    student_id="B001",
                )
            )

    def test_username_collision_creates_distinct_internal_username(self):
        User.objects.create(username="teacher")

        result = services.link_or_create_user(
            OAuthIdentity(subject="faculty-1", identifier="teacher")
        )

        self.assertNotEqual(result.username, "teacher")
        self.assertTrue(result.username.startswith("oauth-"))

    def test_new_oauth_account_has_unusable_password(self):
        result = services.link_or_create_user(
            OAuthIdentity(subject="faculty-2", identifier="teacher2")
        )
        self.assertFalse(result.has_usable_password())

from accounts.providers import MockProvider

class LoginFlowTest(TestCase):
    def test_callback_logs_in_and_creates_user(self):
        MockProvider().register("code123",
            OAuthIdentity(
                subject="s1", identifier="B001", student_id="B001",
                display_name="小明"))
        session = self.client.session
        session["oauth_state"] = "st"
        session.save()
        resp = self.client.get("/accounts/callback/", {"code": "code123", "state": "st"})
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(User.objects.filter(profile__student_id="B001").exists())

    @override_settings(ENABLE_MOCK_OAUTH=True)
    def test_login_start_lands_on_existing_page(self):
        # 點登入後一路 follow,不可掉到 404(dev/mock 模式下 mock-authorize 必須存在)
        resp = self.client.get("/accounts/login/", follow=True)
        self.assertEqual(resp.status_code, 200)

    @override_settings(ENABLE_MOCK_OAUTH=True)
    def test_mock_authorize_completes_login_with_student_id(self):
        resp = self.client.post("/accounts/mock-authorize/",
            {"student_id": "B777", "name": "測試生"}, follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(User.objects.filter(profile__student_id="B777").exists())
        self.assertIn("_auth_user_id", self.client.session)

    def test_mock_authorize_disabled_outside_dev(self):
        with self.settings(ENABLE_MOCK_OAUTH=False):
            get_resp = self.client.get("/accounts/mock-authorize/")
            self.assertEqual(get_resp.status_code, 404)
            post_resp = self.client.post("/accounts/mock-authorize/", {"student_id": "B777"})
            self.assertEqual(post_resp.status_code, 404)
            self.assertFalse(User.objects.filter(profile__student_id="B777").exists())

    def test_logout_requires_post(self):
        user = User.objects.create(username="logout-user")
        self.client.force_login(user)
        resp = self.client.get(reverse("logout"))
        self.assertEqual(resp.status_code, 405)
        self.assertIn("_auth_user_id", self.client.session)      # GET 不會登出
        resp = self.client.post(reverse("logout"))
        self.assertEqual(resp.status_code, 302)
        self.assertNotIn("_auth_user_id", self.client.session)   # POST 才會登出

@override_settings(OAUTH_REDIRECT_URI=None)
class GenericOAuthViewTest(TestCase):
    def _set_state(self, value="expected-state"):
        session = self.client.session
        session["oauth_state"] = value
        session.save()

    def test_login_start_passes_absolute_callback_uri(self):
        provider = RecordingProvider()
        with patch("accounts.views.get_provider", return_value=provider):
            response = self.client.get("/accounts/login/")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            provider.authorize_call[1],
            "http://testserver/accounts/callback/",
        )

    def test_callback_passes_same_callback_uri_to_exchange(self):
        self._set_state()
        provider = RecordingProvider()
        with patch("accounts.views.get_provider", return_value=provider):
            response = self.client.get(
                "/accounts/callback/",
                {"code": "code-1", "state": "expected-state"},
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            provider.exchange_call,
            ("code-1", "http://testserver/accounts/callback/"),
        )

    def test_callback_rejects_missing_code(self):
        self._set_state()
        response = self.client.get(
            "/accounts/callback/", {"state": "expected-state"}
        )

        self.assertEqual(response.status_code, 400)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_callback_rejects_provider_oauth_error(self):
        self._set_state()
        response = self.client.get(
            "/accounts/callback/",
            {"state": "expected-state", "error": "access_denied"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_callback_returns_bad_gateway_for_provider_error(self):
        self._set_state()
        provider = RecordingProvider(exchange_error=True)
        with (
            patch("accounts.views.get_provider", return_value=provider),
            self.assertLogs("accounts.views", "WARNING") as logs,
        ):
            response = self.client.get(
                "/accounts/callback/",
                {"code": "code-1", "state": "expected-state"},
            )

        self.assertEqual(response.status_code, 502)
        self.assertNotContains(response, "upstream details", status_code=502)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertIn("OAuth identity retrieval failed", logs.output[0])

    def test_callback_returns_conflict_for_account_link_conflict(self):
        self._set_state()
        provider = RecordingProvider()
        with (
            patch("accounts.views.get_provider", return_value=provider),
            patch(
                "accounts.views.link_or_create_user",
                side_effect=services.AccountLinkConflict("private conflict"),
            ),
        ):
            response = self.client.get(
                "/accounts/callback/",
                {"code": "code-1", "state": "expected-state"},
            )

        self.assertEqual(response.status_code, 409)
        self.assertNotContains(response, "private conflict", status_code=409)
        self.assertNotIn("_auth_user_id", self.client.session)


class OAuthStateTest(TestCase):
    """state 必須每次隨機、存在 session、回來時比對,否則授權流程沒有 CSRF 保護。"""

    def _register(self):
        MockProvider().register(
            "c1",
            OAuthIdentity(
                subject="s1", identifier="B001", student_id="B001",
                display_name="小明"),
        )

    def _set_state(self, value):
        session = self.client.session
        session["oauth_state"] = value
        session.save()

    @override_settings(ENABLE_MOCK_OAUTH=True)
    def test_login_start_stores_random_state_in_session(self):
        resp = self.client.get("/accounts/login/")
        state = self.client.session["oauth_state"]
        self.assertGreater(len(state), 20)
        self.assertIn(f"state={state}", resp.url)

    @override_settings(ENABLE_MOCK_OAUTH=True)
    def test_each_login_start_uses_a_different_state(self):
        self.client.get("/accounts/login/")
        first = self.client.session["oauth_state"]
        self.client.get("/accounts/login/")
        self.assertNotEqual(first, self.client.session["oauth_state"])

    def test_callback_rejects_mismatched_state(self):
        self._register()
        self._set_state("the-real-state")
        resp = self.client.get("/accounts/callback/", {"code": "c1", "state": "attacker"})
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(User.objects.filter(profile__student_id="B001").exists())
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_callback_rejects_missing_state(self):
        self._register()
        self._set_state("the-real-state")
        resp = self.client.get("/accounts/callback/", {"code": "c1"})
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(User.objects.filter(profile__student_id="B001").exists())

    def test_callback_rejects_reused_state(self):
        self._register()
        self._set_state("one-shot")
        first = self.client.get("/accounts/callback/", {"code": "c1", "state": "one-shot"})
        self.assertEqual(first.status_code, 302)
        self.client.logout()
        replay = self.client.get("/accounts/callback/", {"code": "c1", "state": "one-shot"})
        self.assertEqual(replay.status_code, 400)

    @override_settings(ENABLE_MOCK_OAUTH=True)
    def test_full_mock_flow_from_login_start_passes_state_through(self):
        self.client.get("/accounts/login/")
        state = self.client.session["oauth_state"]
        resp = self.client.post("/accounts/mock-authorize/",
            {"student_id": "B555", "name": "測試生", "state": state}, follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("_auth_user_id", self.client.session)
