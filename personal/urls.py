from django.urls import path

from . import views

app_name = "personal"

urlpatterns = [
    path("", views.MitarbeiterListView.as_view(), name="mitarbeiter_liste"),
    path("neu/", views.MitarbeiterCreateView.as_view(), name="mitarbeiter_neu"),
    path("<int:pk>/", views.MitarbeiterDetailView.as_view(), name="mitarbeiter_detail"),
    path("<int:pk>/bearbeiten/", views.MitarbeiterUpdateView.as_view(), name="mitarbeiter_bearbeiten"),
    path("<int:pk>/loeschen/", views.MitarbeiterLoeschenView.as_view(), name="mitarbeiter_loeschen"),
    path("<int:mitarbeiter_pk>/vertrag/neu/", views.VertragCreateView.as_view(), name="vertrag_neu"),
    path("vertrag/<int:pk>/", views.VertragUpdateView.as_view(), name="vertrag_bearbeiten"),
    path("vertrag/<int:pk>/loeschen/", views.VertragLoeschenView.as_view(), name="vertrag_loeschen"),
    path("<int:mitarbeiter_pk>/urlaubsjahr/<int:jahr>/", views.UrlaubsjahrView.as_view(), name="urlaubsjahr"),
    path("anwesenheit/", views.AnwesenheitView.as_view(), name="anwesenheit"),
    path("urlaub/", views.UrlaubListView.as_view(), name="urlaub_liste"),
    path("urlaub/neu/", views.UrlaubNeuView.as_view(), name="urlaub_neu"),
    path("urlaub/<int:pk>/entscheiden/", views.UrlaubEntscheidenView.as_view(), name="urlaub_entscheiden"),
    path("meine-zeiten/", views.MeineZeitenView.as_view(), name="meine_zeiten"),
    path("meine-zeiten/urlaub/", views.MeinUrlaubNeuView.as_view(), name="mein_urlaub_neu"),
    path("meine-zeiten/urlaub/<int:pk>/zurueckziehen/", views.MeinUrlaubStornierenView.as_view(), name="mein_urlaub_stornieren"),
]
