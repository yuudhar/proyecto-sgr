"""Gráficos sin librerías: anillo (donut) y barras horizontales hechos con SVG y CSS.

Cada gráfico lleva su leyenda con los números escritos, así se entiende sin ver colores y lo leen los lectores de
pantalla. Aquí solo se calculan las medidas; el dibujo está en core/templates/core/partials/chart_*.html.
"""
from decimal import ROUND_HALF_UP, Decimal

from core import ui

CIRCLE = Decimal("100")  # el círculo mide 100 unidades (r = 15,9155), así el largo de cada arco es su porcentaje
TONES = ("ok", "warn", "bad", "info", "neutral")


def _tone(value):
    return value if value in TONES else "neutral"


def _percent(part, whole):
    return (Decimal(part) * 100 / Decimal(whole)) if whole else Decimal(0)


def donut(items, title, center="en total"):
    """items: [{"label": "Aprobadas", "value": 3, "tone": "ok"}, ...] → medidas del anillo y su leyenda."""
    clean = [
        {"label": str(item["label"]), "value": max(0, int(item["value"] or 0)), "tone": _tone(item.get("tone"))}
        for item in items
    ]
    total = sum(item["value"] for item in clean)
    segments, used = [], Decimal(0)
    for item in clean:
        share = _percent(item["value"], total)
        segments.append(
            {
                **item,
                "percent": ui.fmt_number(share.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)),
                "length": f"{share:.3f}",
                "rest": f"{CIRCLE - share:.3f}",
                "offset": f"{-used:.3f}",
                "draw": item["value"] > 0,
            }
        )
        used += share
    summary = ", ".join(f"{item['label']}: {item['value']}" for item in clean)
    return {
        "title": title,
        "center": center,
        "total": total,
        "segments": segments,
        "summary": f"{title}. Total {total}. {summary}." if total else f"{title}. Sin datos.",
    }


def bars(items, title, unit="", maximum=None):
    """items: [{"label": "Ana", "value": 82.5, "tone": "ok"}, ...] → barras horizontales con su valor escrito."""
    values = [Decimal(str(item["value"] or 0)) for item in items]
    top = Decimal(str(maximum)) if maximum else max(values, default=Decimal(0))
    rows = []
    for item, value in zip(items, values):
        width = min(CIRCLE, _percent(value, top)) if top else Decimal(0)
        rows.append(
            {
                "label": str(item["label"]),
                "tone": _tone(item.get("tone")),
                "width": f"{width:.2f}",
                "text": f"{ui.fmt_number(value.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP))}{unit}",
            }
        )
    return {"title": title, "rows": rows}


def columns(items, title, unit=""):
    """items: [{"label": "28/10", "value": 3}, ...] → columnas verticales (una por día, por ejemplo)."""
    values = [max(0, int(item["value"] or 0)) for item in items]
    top = max(values, default=0)
    step, height = 18, 40
    cols = []
    for index, (item, value) in enumerate(zip(items, values)):
        bar = Decimal(height) * value / top if top else Decimal(0)
        cols.append(
            {
                "label": str(item["label"]),
                "value": value,
                "x": index * step + 3,
                "y": f"{Decimal(height) - bar:.2f}",
                "height": f"{bar:.2f}",
                "mid": index * step + 3 + 6,
                "show_label": index % 2 == 0 or len(items) <= 8,
            }
        )
    total = sum(values)
    return {
        "title": title,
        "cols": cols,
        "width": max(1, len(items)) * step + 6,
        "height": height,
        "total": total,
        "unit": unit,
        "summary": f"{title}. Total {total}. "
        + ", ".join(f"{item['label']}: {value}" for item, value in zip(items, values))
        + ".",
    }
