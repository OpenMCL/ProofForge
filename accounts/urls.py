from django.urls import path
from accounts import views
from django.conf import settings

urlpatterns = [
    path("login/", views.login_start, name="login"),
    path("callback/", views.oauth_callback, name="oauth_callback"),
    path("logout/", views.logout_view, name="logout"),
]

if settings.ENABLE_MOCK_OAUTH:
    urlpatterns.append(
        path("mock-authorize/", views.mock_authorize, name="mock_authorize")
    )