from urllib.parse import parse_qs, urlparse

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, override_settings

from accounts import provider_loader, providers


class BrokenProvider(providers.OAuthProvider):
    def __init__(self):
        raise RuntimeError("construction failed")

    def get_authorize_url(self, state, redirect_uri):
        return ""

    def exchange_code(self, code, redirect_uri):
        return ""

    def fetch_identity(self, token):
        raise AssertionError("not used")


class OAuthIdentityContractTest(SimpleTestCase):
    def test_identity_strips_all_string_fields(self):
        identity = providers.OAuthIdentity(
            subject=" subject ",
            identifier=" person ",
            display_name=" Name ",
            email=" person@example.test ",
            student_id=" B001 ",
        )

        self.assertEqual(identity.subject, "subject")
        self.assertEqual(identity.identifier, "person")
        self.assertEqual(identity.display_name, "Name")
        self.assertEqual(identity.email, "person@example.test")
        self.assertEqual(identity.student_id, "B001")

    def test_identity_requires_subject(self):
        with self.assertRaisesRegex(ValueError, "subject"):
            providers.OAuthIdentity(subject=" ", identifier="person")

    def test_identity_requires_identifier(self):
        with self.assertRaisesRegex(ValueError, "identifier"):
            providers.OAuthIdentity(subject="subject", identifier=" ")


class MockProviderTest(SimpleTestCase):
    def test_authorize_url_contains_state_and_redirect_uri(self):
        url = providers.MockProvider().get_authorize_url(
            "xyz", "https://app.test/accounts/callback/"
        )

        query = parse_qs(urlparse(url).query)
        self.assertEqual(query["state"], ["xyz"])
        self.assertIn("redirect_uri", query)
        self.assertEqual(
            query["redirect_uri"], ["https://app.test/accounts/callback/"]
        )

    def test_register_requires_normalized_identity(self):
        with self.assertRaises(TypeError):
            providers.MockProvider().register("c1", {"sub": "s-1"})

    def test_exchange_and_identity_roundtrip(self):
        identity = providers.OAuthIdentity(
            subject="s-1", identifier="B001", student_id="B001"
        )
        provider = providers.MockProvider()
        provider.register("c1", identity)

        token = provider.exchange_code("c1", "https://app.test/callback/")

        self.assertEqual(provider.fetch_identity(token), identity)


class ProviderLoaderTest(SimpleTestCase):
    @override_settings(OAUTH_PROVIDER_CLASS="accounts.providers.MockProvider")
    def test_loader_returns_configured_provider(self):
        self.assertIsInstance(provider_loader.get_provider(), providers.MockProvider)

    @override_settings(OAUTH_PROVIDER_CLASS="missing.module.Provider")
    def test_loader_rejects_missing_class(self):
        with self.assertRaises(ImproperlyConfigured):
            provider_loader.get_provider()

    @override_settings(OAUTH_PROVIDER_CLASS="accounts.providers.OAuthIdentity")
    def test_loader_rejects_non_provider_class(self):
        with self.assertRaises(ImproperlyConfigured):
            provider_loader.get_provider()

    @override_settings(OAUTH_PROVIDER_CLASS="accounts.providers.OAuthProvider")
    def test_loader_rejects_abstract_provider(self):
        with self.assertRaises(ImproperlyConfigured):
            provider_loader.get_provider()

    @override_settings(
        OAUTH_PROVIDER_CLASS="accounts.tests.test_providers.BrokenProvider"
    )
    def test_loader_wraps_construction_failure(self):
        with self.assertRaises(ImproperlyConfigured):
            provider_loader.get_provider()
