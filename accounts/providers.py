from abc import ABC, abstractmethod
from dataclasses import dataclass
from urllib.parse import urlencode


@dataclass(frozen=True)
class OAuthIdentity:
    subject: str
    identifier: str
    display_name: str = ""
    email: str = ""
    student_id: str | None = None

    def __post_init__(self):
        for field_name in ("subject", "identifier", "display_name", "email", "student_id"):
            value = getattr(self, field_name)
            if isinstance(value, str):
                object.__setattr__(self, field_name, value.strip())
        if not self.subject:
            raise ValueError("subject is required")
        if not self.identifier:
            raise ValueError("identifier is required")


class OAuthProviderError(Exception):
    pass


class OAuthProvider(ABC):
    @abstractmethod
    def get_authorize_url(self, state, redirect_uri):
        raise NotImplementedError

    @abstractmethod
    def exchange_code(self, code, redirect_uri):
        raise NotImplementedError

    @abstractmethod
    def fetch_identity(self, token):
        raise NotImplementedError


class MockProvider(OAuthProvider):
    _registry = {}

    def register(self, code, userinfo):
        if not isinstance(userinfo, OAuthIdentity):
            raise TypeError("userinfo must be an OAuthIdentity")
        MockProvider._registry[f"token-{code}"] = userinfo

    def get_authorize_url(self, state, redirect_uri):
        query = urlencode({"state": state, "redirect_uri": redirect_uri})
        return f"/accounts/mock-authorize/?{query}"

    def exchange_code(self, code, redirect_uri):
        return f"token-{code}"

    def fetch_identity(self, token):
        return MockProvider._registry[token]
