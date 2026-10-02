from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class BenutzerAdmin(UserAdmin):
    """Django-Admin für Notfälle und Wartung. Die tägliche Benutzerverwaltung
    läuft über die Oberfläche unter "Einstellungen"."""

    list_display = ("username", "first_name", "last_name", "is_superuser", "is_active", "auth_source")
    list_filter = ("is_superuser", "is_active", "auth_source", "groups")
    fieldsets = UserAdmin.fieldsets + (("Anmeldung", {"fields": ("auth_source",)}),)
