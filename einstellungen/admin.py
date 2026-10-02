from django.contrib import admin

from .models import Firma, Nummernkreis, Formulareinstellung

admin.site.register(Firma)
admin.site.register(Nummernkreis)


@admin.register(Formulareinstellung)
class FormulareinstellungAdmin(admin.ModelAdmin):
    list_display = ("bereich", "schluessel", "wert")
    list_filter = ("bereich",)
