from django.apps import AppConfig
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

class AccountsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'accounts'

    def ready(self):
        from accounts.provider_loader import get_provider
        from accounts.providers import MockProvider
        if isinstance(get_provider(), MockProvider) and not settings.ENABLE_MOCK_OAUTH:
            raise ImproperlyConfigured(
                "MockProvider loaded without ENABLE_MOCK_OAUTH; refusing to start."
            )