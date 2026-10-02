from django.urls import path

from . import views

app_name = "stammdaten"

urlpatterns = [
    path("kategorien/", views.KategorieListView.as_view(), name="kategorien_liste"),
    path("kategorien/neu/", views.KategorieCreateView.as_view(), name="kategorien_neu"),
    path("kategorien/<int:pk>/", views.KategorieUpdateView.as_view(), name="kategorien_bearbeiten"),
    path("kategorien/<int:pk>/loeschen/", views.KategorieLoeschenView.as_view(), name="kategorien_loeschen"),
    path("artikel/", views.ArtikelListView.as_view(), name="artikel_liste"),
    path("artikel/neu/", views.ArtikelCreateView.as_view(), name="artikel_neu"),
    path("artikel/<int:pk>/", views.ArtikelUpdateView.as_view(), name="artikel_bearbeiten"),
    path("artikel/<int:pk>/deaktivieren/", views.ArtikelDeaktivierenView.as_view(), name="artikel_deaktivieren"),
    path("kunden/", views.KundeListView.as_view(), name="kunden_liste"),
    path("kunden/neu/", views.KundeCreateView.as_view(), name="kunden_neu"),
    path("kunden/<int:pk>/", views.KundeUpdateView.as_view(), name="kunden_bearbeiten"),
    path("kunden/<int:pk>/loeschen/", views.KundeLoeschenView.as_view(), name="kunden_loeschen"),
    path(
        "kunden/<int:pk>/rechnung/<int:rechnung_pk>/bezahlt/",
        views.RechnungBezahltView.as_view(),
        name="kunden_rechnung_bezahlt",
    ),
    path("lieferanten/", views.LieferantListView.as_view(), name="lieferanten_liste"),
    path("lieferanten/neu/", views.LieferantCreateView.as_view(), name="lieferanten_neu"),
    path("lieferanten/<int:pk>/", views.LieferantUpdateView.as_view(), name="lieferanten_bearbeiten"),
    path("lieferanten/<int:pk>/loeschen/", views.LieferantLoeschenView.as_view(), name="lieferanten_loeschen"),
]
