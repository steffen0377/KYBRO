from django.urls import path

from . import views

app_name = "lager"

urlpatterns = [
    path("", views.UebersichtView.as_view(), name="uebersicht"),
    path("wareneingang/", views.WareneingangView.as_view(), name="wareneingang"),
    path("korrektur/", views.KorrekturView.as_view(), name="korrektur"),
    path("seriennummern/einlagern/", views.SeriellEinlagernView.as_view(), name="seriell_einlagern"),
    path("seriennummern/<int:pk>/defekt/", views.SerieDefektView.as_view(), name="serie_defekt"),
    path("seriennummern/<int:pk>/entfernen/", views.SerieEntfernenView.as_view(), name="serie_entfernen"),
]
