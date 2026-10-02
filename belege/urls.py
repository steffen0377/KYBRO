from django.urls import path

from . import views

app_name = "belege"

urlpatterns = [
    # Angebote
    path("angebote/", views.AngebotListeView.as_view(), name="angebote_liste"),
    path("angebote/neu/", views.AngebotFormularView.as_view(neu=True), name="angebote_neu"),
    path("angebote/<int:pk>/", views.AngebotDetailView.as_view(), name="angebote_ansehen"),
    path("angebote/<int:pk>/pdf/", views.AngebotPdfView.as_view(), name="angebote_pdf"),
    path("angebote/<int:pk>/bearbeiten/", views.AngebotFormularView.as_view(neu=False), name="angebote_bearbeiten"),
    path("angebote/<int:pk>/status/", views.AngebotStatusView.as_view(), name="angebote_status"),
    path("angebote/<int:pk>/auftrag/", views.AngebotZuAuftragView.as_view(), name="angebote_zu_auftrag"),
    path("angebote/<int:pk>/rechnung/", views.AngebotZuRechnungView.as_view(), name="angebote_zu_rechnung"),
    path("angebote/<int:pk>/loeschen/", views.AngebotLoeschenView.as_view(), name="angebote_loeschen"),
    # Aufträge
    path("auftraege/", views.AuftragListeView.as_view(), name="auftraege_liste"),
    path("auftraege/<int:pk>/", views.AuftragDetailView.as_view(), name="auftraege_ansehen"),
    path("auftraege/<int:pk>/pdf/", views.AuftragPdfView.as_view(), name="auftraege_pdf"),
    path("auftraege/<int:pk>/status/", views.AuftragStatusView.as_view(), name="auftraege_status"),
    path("auftraege/<int:pk>/rechnung/", views.AuftragZuRechnungView.as_view(), name="auftraege_zu_rechnung"),
    path("auftraege/<int:pk>/loeschen/", views.AuftragLoeschenView.as_view(), name="auftraege_loeschen"),
    # Rechnungen
    path("rechnungen/", views.RechnungListeView.as_view(), name="rechnungen_liste"),
    path("rechnungen/neu/", views.RechnungFormularView.as_view(neu=True), name="rechnungen_neu"),
    path("rechnungen/<int:pk>/", views.RechnungDetailView.as_view(), name="rechnungen_ansehen"),
    path("rechnungen/<int:pk>/pdf/", views.RechnungPdfView.as_view(), name="rechnungen_pdf"),
    path("rechnungen/<int:pk>/bearbeiten/", views.RechnungFormularView.as_view(neu=False), name="rechnungen_bearbeiten"),
    path("rechnungen/<int:pk>/status/", views.RechnungStatusView.as_view(), name="rechnungen_status"),
    path("rechnungen/<int:pk>/loeschen/", views.RechnungLoeschenView.as_view(), name="rechnungen_loeschen"),
    path("rechnungen/<int:pk>/seriennummern/", views.RechnungSeriennummernView.as_view(), name="rechnungen_seriennummern"),
]
