from django.urls import path

from . import views

app_name = "einstellungen"

urlpatterns = [
    path("", views.FirmaView.as_view(), name="firma"),
    path("nummernkreise/", views.NummernkreiseView.as_view(), name="nummernkreise"),
    path("mail/", views.MailView.as_view(), name="mail"),
    path("formulare/", views.FormulareView.as_view(), name="formulare"),
    path("lizenzen/", views.LizenzListeView.as_view(), name="lizenzen"),
    path("lizenzen/neu/", views.LizenzNeuView.as_view(), name="lizenz_neu"),
    path("lizenzen/<int:pk>/", views.LizenzBearbeitenView.as_view(), name="lizenz_bearbeiten"),
    path("lizenzen/<int:pk>/loeschen/", views.LizenzLoeschenView.as_view(), name="lizenz_loeschen"),
    path("live/", views.LiveAktivierenView.as_view(), name="live"),
    path("anmeldung/", views.AnmeldungView.as_view(), name="anmeldung"),
]
