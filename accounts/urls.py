from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("anmelden/", views.AnmeldeView.as_view(), name="login"),
    path("anmelden/logo/", views.anmeldelogo, name="login_logo"),
    # Seit Django 5 nur noch per POST, damit ein fremder Link niemanden abmeldet.
    path("abmelden/", auth_views.LogoutView.as_view(), name="logout"),
    # Benutzer
    path("benutzer/", views.BenutzerListView.as_view(), name="benutzer_liste"),
    path("benutzer/neu/", views.BenutzerCreateView.as_view(), name="benutzer_neu"),
    path("benutzer/<int:pk>/", views.BenutzerUpdateView.as_view(), name="benutzer_bearbeiten"),
    path(
        "benutzer/<int:pk>/deaktivieren/",
        views.BenutzerDeaktivierenView.as_view(),
        name="benutzer_deaktivieren",
    ),
    # Gruppen und Rechte
    path("gruppen/", views.GruppeListView.as_view(), name="gruppe_liste"),
    path("gruppen/neu/", views.GruppeCreateView.as_view(), name="gruppe_neu"),
    path("gruppen/<int:pk>/", views.GruppeUpdateView.as_view(), name="gruppe_bearbeiten"),
    path("gruppen/<int:pk>/loeschen/", views.GruppeLoeschenView.as_view(), name="gruppe_loeschen"),
]
