from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django import template
from django.contrib.staticfiles import finders
from django.templatetags.static import static

from core import charts, ui

register = template.Library()

ESCUDO_FILES = ("core/img/escudo-la-serena.svg", "core/img/escudo-la-serena.png")


@register.simple_tag
def escudo_url():
    for name in ESCUDO_FILES:
        if finders.find(name):
            return static(name)
    return ""


@register.filter
def fdate(value):
    return ui.fmt_date(value)


@register.filter
def fdatetime(value):
    return ui.fmt_datetime(value)


@register.filter
def fnumber(value):
    return ui.fmt_number(value)


@register.filter
def hd(value):
    return ui.humanize_dates(value)


@register.filter
def tone(value):
    return ui.tone_for(value)[0]


@register.filter
def tone_icon(value):
    return ui.tone_for(value)[1]


@register.filter
def light_label(value):
    return ui.LIGHT_LABELS.get(value, "")


def _to_decimal(value, default=None):
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return default


@register.inclusion_tag("core/partials/meter.html")
def meter(value, light="", collective=None, amber=None, label="Cumplimiento", compact=False):
    number = _to_decimal(value, Decimal(0)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    width = max(Decimal(0), min(Decimal(100), number))
    marks = []
    for name, mark in (("ámbar", amber), ("colectivo", collective)):
        position = _to_decimal(mark)
        if position is not None and 0 < position <= 100:
            marks.append({"name": name, "left": f"{position:.2f}", "text": ui.fmt_number(position)})
    return {
        "text": f"{ui.fmt_number(number)} %",
        "raw": f"{width:.2f}",
        "width": f"{width:.2f}",
        "tone": ui.tone_for(light)[0] if light else "neutral",
        "marks": marks,
        "label": label,
        "compact": compact,
    }


@register.inclusion_tag("core/partials/chart_donut.html")
def donut_chart(items, title, center="en total"):
    """{% donut_chart items "Título" "texto del centro" %} con items = [{label, value, tone}]."""
    return charts.donut(items, title, center)


@register.inclusion_tag("core/partials/chart_bars.html")
def bar_chart(items, title, unit="", maximum=None):
    """{% bar_chart items "Título" " %" 100 %} con items = [{label, value, tone}]."""
    return charts.bars(items, title, unit, maximum)


@register.inclusion_tag("core/partials/chart_columns.html")
def column_chart(items, title, unit=""):
    """{% column_chart items "Título" %} con items = [{label, value}]."""
    return charts.columns(items, title, unit)


# Versiones que reciben el gráfico ya armado en la vista (core.charts.donut / bars / columns).
@register.inclusion_tag("core/partials/chart_donut.html")
def show_donut(chart):
    return chart


@register.inclusion_tag("core/partials/chart_bars.html")
def show_bars(chart):
    return chart


@register.inclusion_tag("core/partials/chart_columns.html")
def show_columns(chart):
    return chart
