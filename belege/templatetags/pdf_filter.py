from django import template

from belege import pdf

register = template.Library()
register.filter("geld", pdf.geld)
register.filter("menge_text", pdf.menge_text)
