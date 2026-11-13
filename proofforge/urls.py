from django.conf import settings
from django.contrib import admin
from django.urls import include, path

from core_health.views import healthz
from courses.views import dashboard

urlpatterns = [
    path("healthz/", healthz),
    path("accounts/", include("accounts.urls")),
    path("courses/", include("courses.urls")),
    path("", include("submissions.urls")),
    path("", dashboard, name="dashboard"),
]

if settings.ENABLE_ADMIN:
    urlpatterns.insert(0, path("admin/", admin.site.urls))
