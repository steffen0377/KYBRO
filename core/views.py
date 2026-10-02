from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = "core/dashboard.html"
    extra_context = {"seitentitel": "Dashboard"}


class LiveSucheMixin:
    """Liefert bei ``?ajax=1`` nur das Tabellen-Fragment (für die Live-Suche).

    Die View braucht ``template_name`` (volle Seite) und ``fragment_template_name``.
    """

    fragment_template_name: str | None = None

    def get_template_names(self):
        if self.request.GET.get("ajax") and self.fragment_template_name:
            return [self.fragment_template_name]
        return super().get_template_names()
