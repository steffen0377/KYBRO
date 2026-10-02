from django.contrib.auth import views as auth_views
from django.urls import path

from .forms import AnmeldeForm

app_name = "accounts"

urlpatterns = [
    path(
        "anmelden/",
        auth_views.LoginView.as_view(
            template_name="accounts/login.html",
            authentication_form=AnmeldeForm,
            redirect_authenticated_user=True,
        ),
        name="login",
    ),
    # Seit Django 5 nur noch per POST, damit ein fremder Link niemanden abmeldet.
    path("abmelden/", auth_views.LogoutView.as_view(), name="logout"),
]
