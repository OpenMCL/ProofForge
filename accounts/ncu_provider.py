"""NCU Portal (第四代) OAuth 2.0 provider.

依據官方文件實作 Authorization Code Grant：
    https://portal.ncu.edu.tw/about/howto
    https://github.com/ncucc/portal4g-doc

設計決定（詳見各方法註解）：
- subject 使用 ``identifier``（Portal 帳號）而不是 ``id``。Portal 的 64 位元 id
  是每個應用系統各自不同的值，而且官方文件記載 Portal 3g → 4g 移轉時 id 會改變、
  identifier 不變。以 id 綁定帳號，會在 Portal 升級或重新註冊 client 時讓所有
  使用者失去原本的帳號。
- ``studentId`` 與 ``email`` 使用者可以拒絕授權，因此都是可選的。
- 只傳遞 ``emailVerified`` 為 True 的 email，避免下游以未驗證的 email 比對帳號。
- 帶有 ``delegator``（委託登入）的回應一律拒絕，直到語意確認為止。
- 所有外部失敗都轉換成 ``OAuthProviderError``；``oauth_callback`` 只捕捉它與
  ``ValueError``，漏掉任何一種都會讓使用者看到 500。
- 不記錄 token 或任何個人資料。
"""

from urllib.parse import urlencode

import requests
from django.conf import settings

from accounts.providers import OAuthIdentity, OAuthProvider, OAuthProviderError

DEFAULT_BASE_URL = "https://portal.ncu.edu.tw"


class NCUPortalProvider(OAuthProvider):
    AUTHORIZE_PATH = "/oauth2/authorization"
    TOKEN_PATH = "/oauth2/token"
    USERINFO_PATH = "/apis/oauth/v1/info"

    # 資料最小化：只申請實際需要的 scope。Portal 另外提供身分證字號、生日、
    # 手機等 scope，本系統不需要，不要加入。
    # 註冊 client 時務必在 Portal 上將 identifier 設為必要欄位，
    # 使用者就只能選擇不登入，而不能拒絕提供帳號。
    SCOPES = ("identifier", "chinese-name", "student-id", "email")

    # userinfo 回應的欄位名稱（官方文件 OAuthAuthorizedData）
    FIELD_IDENTIFIER = "identifier"
    FIELD_NAME = "chineseName"
    FIELD_STUDENT_ID = "studentId"
    FIELD_EMAIL = "email"
    FIELD_EMAIL_VERIFIED = "emailVerified"
    FIELD_DELEGATOR = "delegator"

    TIMEOUT = 10  # 秒；requests 預設沒有逾時

    def __init__(self):
        self.client_id = getattr(settings, "NCU_OAUTH_CLIENT_ID", None)
        self.client_secret = getattr(settings, "NCU_OAUTH_CLIENT_SECRET", None)
        if not self.client_id or not self.client_secret:
            # provider_loader 會把它包成 ImproperlyConfigured；
            # accounts.apps.ready() 在啟動時呼叫 get_provider()，
            # 因此缺少 credentials 時服務會直接拒絕啟動。
            raise ValueError("NCU OAuth client credentials are not configured")

        # 官方文件：測試階段可將主機換成測試主機
        base = getattr(settings, "NCU_PORTAL_BASE_URL", None) or DEFAULT_BASE_URL
        if not base.startswith("https://"):
            raise ValueError("NCU_PORTAL_BASE_URL must use https")
        self.base_url = base.rstrip("/")

    # ------------------------------------------------------------------ #
    # OAuthProvider interface
    # ------------------------------------------------------------------ #

    def get_authorize_url(self, state, redirect_uri):
        query = urlencode({
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "scope": " ".join(self.SCOPES),  # 官方文件：以空白分隔
            "state": state,
        })
        return f"{self.base_url}{self.AUTHORIZE_PATH}?{query}"

    def exchange_code(self, code, redirect_uri):
        try:
            resp = requests.post(
                f"{self.base_url}{self.TOKEN_PATH}",
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                },
                auth=(self.client_id, self.client_secret),  # Basic Auth（文件要求）
                headers={"Accept": "application/json"},     # 文件要求
                timeout=self.TIMEOUT,
            )
            resp.raise_for_status()
            payload = resp.json()
        except (requests.RequestException, ValueError) as exc:
            raise OAuthProviderError("token exchange failed") from exc

        if not isinstance(payload, dict):
            raise OAuthProviderError("token response is not a JSON object")
        # 官方 PHP 範例會檢查 body 內的 error 欄位，即使 HTTP 狀態碼為 200
        if payload.get("error"):
            raise OAuthProviderError("token endpoint returned an error")

        token = payload.get("access_token")
        if not isinstance(token, str) or not token:
            raise OAuthProviderError("token endpoint returned no access token")
        return token

    def fetch_identity(self, token):
        try:
            resp = requests.get(
                f"{self.base_url}{self.USERINFO_PATH}",
                headers={
                    "Authorization": f"Bearer {token}",  # 官方範例：Bearer header
                    "Accept": "application/json",
                },
                timeout=self.TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
        except (requests.RequestException, ValueError) as exc:
            raise OAuthProviderError("userinfo request failed") from exc

        if not isinstance(data, dict):
            raise OAuthProviderError("userinfo response is not a JSON object")

        # 委託登入：語意未在文件中說明。在評分系統中，代理他人登入可能讓
        # 被委託者以老師身分操作成績，因此在確認之前一律拒絕。
        if data.get(self.FIELD_DELEGATOR):
            raise OAuthProviderError("delegated logins are not supported")

        identifier = self._scalar(data, self.FIELD_IDENTIFIER)
        email = self._scalar(data, self.FIELD_EMAIL)
        if data.get(self.FIELD_EMAIL_VERIFIED) is not True:
            email = ""

        # identifier 為空時，OAuthIdentity.__post_init__ 會拋出 ValueError，
        # oauth_callback 回傳 502，而不是建立識別碼為空字串的帳號。
        return OAuthIdentity(
            subject=identifier,
            identifier=identifier,
            display_name=self._scalar(data, self.FIELD_NAME),
            email=email,
            student_id=self._scalar(data, self.FIELD_STUDENT_ID) or None,
        )

    # ------------------------------------------------------------------ #
    # helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _scalar(data, key):
        """取出字串或整數欄位並轉為去除空白的字串；其他型別一律視為缺值。

        bool 是 int 的子類別，必須明確排除，否則 True 會變成 "True"。
        """
        value = data.get(key)
        if isinstance(value, bool) or not isinstance(value, (str, int)):
            return ""
        return str(value).strip()
