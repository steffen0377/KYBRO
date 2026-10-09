from django.urls import path

from kalender.views_einstellungen import CalDavView

from . import views

app_name = "einstellungen"

urlpatterns = [
    path("", views.FirmaView.as_view(), name="firma"),
    path("briefbogen/", views.BriefbogenListeView.as_view(), name="briefbogen"),
    path("briefbogen/neu/", views.BriefbogenNeuView.as_view(), name="briefbogen_neu"),
    path("briefbogen/vorschau/", views.BriefbogenVorschauView.as_view(), name="briefbogen_vorschau"),
    path("briefbogen/<int:pk>/", views.BriefbogenBearbeitenView.as_view(), name="briefbogen_bearbeiten"),
    path("briefbogen/<int:pk>/loeschen/", views.BriefbogenLoeschenView.as_view(), name="briefbogen_loeschen"),
    path("nummernkreise/", views.NummernkreiseView.as_view(), name="nummernkreise"),
    path("mail/", views.MailView.as_view(), name="mail"),
    path("formulare/", views.FormulareView.as_view(), name="formulare"),
    path("kalender/", CalDavView.as_view(), name="kalender"),
    path("lizenzen/", views.LizenzListeView.as_view(), name="lizenzen"),
    path("lizenzen/neu/", views.LizenzNeuView.as_view(), name="lizenz_neu"),
    path("lizenzen/<int:pk>/", views.LizenzBearbeitenView.as_view(), name="lizenz_bearbeiten"),
    path("lizenzen/<int:pk>/loeschen/", views.LizenzLoeschenView.as_view(), name="lizenz_loeschen"),
    path("live/", views.LiveAktivierenView.as_view(), name="live"),
    path("anmeldung/", views.AnmeldungView.as_view(), name="anmeldung"),
]
