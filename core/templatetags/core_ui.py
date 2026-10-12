"""Etiquetas y filtros de plantilla para las pantallas web."""

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django import template
from django.contrib.staticfiles import finders
from django.templatetags.static import static

from core import ui

register = template.Library()

# Escudo oficial de la Municipalidad de La Serena. Las normas gráficas lo definen como el único elemento de
# identificación y piden usarlo siempre igual (sin redibujarlo ni deformarlo), por eso no se incluye una copia hecha
# aquí: se copia el archivo oficial en core/static/core/img/ con uno de estos nombres y las pantallas lo muestran.
ESCUDO_FILES = ("core/img/escudo-la-serena.svg", "core/img/escudo-la-serena.png")


@register.simple_tag
def escudo_url():
    """Dirección del escudo oficial si su archivo ya está en core/static/core/img/; vacío si todavía no."""
    for name in ESCUDO_FILES:
        if finders.find(name):
            return static(name)
    return ""


@register.filter
def fdate(value):
    """Fecha como 06/10/2026."""
    return ui.fmt_date(value)


@register.filter
def fdatetime(value):
    """Fecha y hora local como 06/10/2026 14:35."""
    return ui.fmt_datetime(value)


@register.filter
def fnumber(value):
    """Número con coma decimal y punto de miles."""
    return ui.fmt_number(value)


@register.filter
def hd(value):
    """Texto de un registro con sus fechas como 06/10/2026."""
    return ui.humanize_dates(value)


@register.filter
def tone(value):
    """Tono de color (ok, warn, bad, info, neutral) de un valor guardado."""
    return ui.tone_for(value)[0]


@register.filter
def tone_icon(value):
    """Ícono de Bootstrap Icons de un valor guardado."""
    return ui.tone_for(value)[1]


@register.filter
def light_label(value):
    """Verde, Ámbar o Rojo a partir del valor guardado del semáforo."""
    return ui.LIGHT_LABELS.get(value, "")


def _to_decimal(value, default=None):
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return default


@register.inclusion_tag("core/partials/meter.html")
def meter(value, light="", collective=None, amber=None, label="Cumplimiento", compact=False):
    """Barra de cumplimiento con marcas en los umbrales ámbar y colectivo del período.

    El ancho se limita a 0-100 %, pero el texto muestra el valor real (puede pasar de 100).
    Los valores salen como texto para que el idioma no les cambie el punto por coma
    dentro de los estilos.
    """
    number = _to_decimal(value, Decimal(0)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    width = max(Decimal(0), min(Decimal(100), number))
    marks = []
    for name, mark in (("ámbar", amber), ("colectivo", collective)):
        position = _to_decimal(mark)
        if position is not None and 0 < position <= 100:
            marks.append({"name": name, "left": f"{position:.2f}", "text": ui.fmt_number(position)})
    return {
        "text": f"{ui.fmt_number(number)} %",
        "raw": f"{width:.2f}",  # dentro de 0-100, como pide aria-valuenow; el texto lleva el valor real
        "width": f"{width:.2f}",
        "tone": ui.tone_for(light)[0] if light else "neutral",
        "marks": marks,
        "label": label,
        "compact": compact,
    }
