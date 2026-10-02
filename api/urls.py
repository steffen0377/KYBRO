from django.urls import path

from . import auth, views

app_name = "api"

urlpatterns = [
    path("auth/", auth.anmelden, name="auth"),
    path("auftraege/", views.auftraege, name="auftraege"),
    path("auftraege/rechnung/", views.auftrag_zu_rechnung, name="auftrag_zu_rechnung"),
    path("kunden/", views.kunden, name="kunden"),
    path("artikel/", views.artikel_liste, name="artikel"),
]
