"""URL-Konfiguration von KYBRO. Jede App bringt ihre eigenen URLs mit."""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("konto/", include("accounts.urls")),
    path("", include("core.urls")),
]
