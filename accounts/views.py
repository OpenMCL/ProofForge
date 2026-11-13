import secrets
import logging
from urllib.parse import urlencode

from django.contrib.auth import login, logout
from django.http import Http404
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from django.shortcuts import redirect, render
from django.urls import reverse

from accounts.provider_loader import get_provider
from accounts.providers import MockProvider, OAuthIdentity, OAuthProviderError
from accounts.services import AccountLinkConflict, link_or_create_user
from django.conf import settings

logger = logging.getLogger(__name__)

def _callback_uri(request):
    return settings.OAUTH_REDIRECT_URI or request.build_absolute_uri(reverse("oauth_callback"))

def _safe_next_url(request, url):
    """只接受本站的網址,避免登入流程被用來轉址到外部網站。"""
    if url and url_has_allowed_host_and_scheme(
        url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return url
    return None

def _login_error(request, status, title, message, retry=True, next_url=None):
    # 訊息一律是固定文字,不帶入 provider 或例外的細節,避免洩漏內部資訊。
    # next_url 讓「重新登入」回到原本要去的頁面,同樣只接受本站網址。
    return render(
        request,
        "accounts/login_error.html",
        {
            "title": title,
            "message": message,
            "retry": retry,
            "next_url": _safe_next_url(request, next_url),
        },
        status=status,
    )

def login_start(request):
    state = secrets.token_urlsafe(32)
    request.session["oauth_state"] = state
    next_url = _safe_next_url(request, request.GET.get("next"))
    if next_url:
        request.session["oauth_next"] = next_url
    else:
        request.session.pop("oauth_next", None)
    return redirect(get_provider().get_authorize_url(state, _callback_uri(request)))

def mock_authorize(request):
    """開發用的假 IdP 授權頁:輸入學號即視為通過授權,以學號為 code 回到 callback。

    安全限制:僅在開發模式(ENABLE_MOCK_OAUTH=True)且使用 mock provider 時可用。任何 ENABLE_MOCK_OAUTH=False
    的部署都回 404,避免對外公開時有人用任意學號(含老師/助教)登入既有帳號。
    """
    if not (settings.ENABLE_MOCK_OAUTH and isinstance(get_provider(), MockProvider)):
        raise Http404()
    error = ""
    if request.method == "POST":
        sid = request.POST.get("student_id", "").strip()
        if not sid:
            error = "請輸入學號"
        else:
            # 直接開這頁(沒走 login_start)時 session 裡沒有 state,補一個,
            # 讓開發流程跟正式流程走同一條 callback 驗證路徑。
            state = request.POST.get("state") or secrets.token_urlsafe(16)
            request.session["oauth_state"] = state
            MockProvider().register(
                sid,
                OAuthIdentity(
                    subject=sid,
                    identifier=sid,
                    student_id=sid,
                    display_name=request.POST.get("name", "").strip(),
                ),
            )
            query = urlencode({"code": sid, "state": state})
            return redirect(f"{reverse('oauth_callback')}?{query}")
    return render(request, "accounts/mock_authorize.html", {
        "state": request.POST.get("state") or request.GET.get("state", ""),
        "student_id": request.POST.get("student_id", "").strip(),
        "name": request.POST.get("name", "").strip(),
        "error": error,
    })

def oauth_callback(request):
    expected = request.session.pop("oauth_state", None)
    next_url = request.session.pop("oauth_next", None)
    if not expected or request.GET.get("state") != expected:
        return _login_error(
            request, 400, "登入驗證失敗", "登入請求已失效,或不是由本站發起。請重新登入。",
            next_url=next_url,
        )
    if request.GET.get("error"):
        return _login_error(
            request, 400, "未完成授權", "您沒有完成學校端的授權。請重新登入。",
            next_url=next_url,
        )
    code = request.GET.get("code")
    if not code:
        return _login_error(
            request, 400, "授權資料不完整", "學校端回傳的資料缺少授權碼。請重新登入。",
            next_url=next_url,
        )

    provider = get_provider()
    try:
        token = provider.exchange_code(code, _callback_uri(request))
        identity = provider.fetch_identity(token)
    except (OAuthProviderError, ValueError):
        logger.warning("OAuth identity retrieval failed", exc_info=True)
        return _login_error(
            request, 502, "無法完成學校登入", "學校登入服務暫時無法使用或回應異常。請稍後再試。",
            next_url=next_url,
        )

    try:
        user = link_or_create_user(identity)
    except AccountLinkConflict:
        logger.warning("OAuth account link conflict", exc_info=True)
        return _login_error(
            request, 409, "帳號衝突", "此學校帳號與系統中既有的帳號衝突,無法自動登入。請聯絡管理員。",
            retry=False,
        )

    login(request, user)
    return redirect(_safe_next_url(request, next_url) or "/")

@require_POST
def logout_view(request):
    logout(request)
    return redirect("/")
