"""Resolve the OAuth provider configured for this deployment."""

import inspect

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils.module_loading import import_string

from accounts.providers import OAuthProvider


def get_provider():
    provider_path = settings.OAUTH_PROVIDER_CLASS
    try:
        provider_class = import_string(provider_path)
    except (ImportError, AttributeError) as exc:
        raise ImproperlyConfigured(
            f"Cannot import OAuth provider {provider_path!r}"
        ) from exc

    if not inspect.isclass(provider_class) or not issubclass(
        provider_class, OAuthProvider
    ):
        raise ImproperlyConfigured(
            f"Configured OAuth provider {provider_path!r} must extend OAuthProvider"
        )
    if inspect.isabstract(provider_class):
        raise ImproperlyConfigured(
            f"Configured OAuth provider {provider_path!r} is abstract"
        )

    try:
        return provider_class()
    except Exception as exc:
        raise ImproperlyConfigured(
            f"Could not initialize OAuth provider {provider_path!r}"
        ) from exc
