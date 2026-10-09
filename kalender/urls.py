from django.urls import path

from . import views

app_name = "kalender"

urlpatterns = [
    path("", views.MonatView.as_view(), name="monat"),
    path("termin/neu/", views.TerminNeuView.as_view(), name="termin_neu"),
    path("termin/<int:pk>/", views.TerminBearbeitenView.as_view(), name="termin_bearbeiten"),
    path("termin/<int:pk>/loeschen/", views.TerminLoeschenView.as_view(), name="termin_loeschen"),
    path("verwalten/", views.KalenderListeView.as_view(), name="kalender_liste"),
    path("verwalten/neu/", views.KalenderNeuView.as_view(), name="kalender_neu"),
    path("verwalten/<int:pk>/", views.KalenderBearbeitenView.as_view(), name="kalender_bearbeiten"),
    path("verwalten/<int:pk>/loeschen/", views.KalenderLoeschenView.as_view(), name="kalender_loeschen"),
    path("abo/", views.AboView.as_view(), name="abo"),
    path("feed/<str:schluessel>/<str:kalender>.ics", views.FeedView.as_view(), name="feed"),
]
