"""Ayudas de presentación: colores de estado, íconos y formato de fechas y números."""

import re
from decimal import Decimal

from django.utils import timezone
from django.utils.formats import date_format

# Valor guardado en la base -> (tono de color, ícono de Bootstrap Icons).
# Los tonos son ok (verde), warn (ámbar), bad (rojo), info (azul) y neutral (gris).
# El semáforo usa siempre ícono y texto además del color, para no depender solo de él.
TONES = {
    "active": ("ok", "bi-check-circle-fill"),
    "inactive": ("neutral", "bi-dash-circle-fill"),
    "planned": ("info", "bi-calendar-event"),
    "closed": ("neutral", "bi-lock-fill"),
    "registered": ("neutral", "bi-journal-plus"),
    "in_progress": ("info", "bi-hourglass-split"),
    "submitted": ("neutral", "bi-inbox-fill"),
    "fulfilled": ("ok", "bi-check-circle-fill"),
    "pending": ("warn", "bi-clock-history"),
    "approved": ("ok", "bi-patch-check-fill"),
    "rejected": ("bad", "bi-x-octagon-fill"),
    "flagged": ("warn", "bi-flag-fill"),
    "bonus": ("ok", "bi-arrow-up-circle-fill"),
    "penalty": ("bad", "bi-arrow-down-circle-fill"),
    "BONUS": ("ok", "bi-arrow-up-circle-fill"),
    "PENALTY": ("bad", "bi-arrow-down-circle-fill"),
    "NORMAL": ("neutral", "bi-circle"),
    "INTERNAL": ("neutral", "bi-building"),
    "EXTERNAL": ("info", "bi-people-fill"),
    "quantitative": ("info", "bi-123"),
    "qualitative": ("neutral", "bi-chat-square-text"),
    "green": ("ok", "bi-check-circle-fill"),
    "amber": ("warn", "bi-exclamation-triangle-fill"),
    "red": ("bad", "bi-x-octagon-fill"),
}

LIGHT_LABELS = {"green": "Verde", "amber": "Ámbar", "red": "Rojo"}


def tone_for(value):
    """Tono e ícono de un valor guardado; gris sin ícono si no está en la tabla."""
    return TONES.get(value, ("neutral", ""))


def light_for_compliance(compliance, collective_threshold, amber_threshold):
    """Color de semáforo para un porcentaje, con los umbrales del período.

    Verde desde el umbral colectivo, ámbar desde el umbral ámbar y rojo bajo eso.
    """
    if compliance >= collective_threshold:
        return "green"
    if compliance >= amber_threshold:
        return "amber"
    return "red"


def fmt_date(value):
    """Fecha como 06/10/2026."""
    return date_format(value, "d/m/Y") if value else ""


def fmt_datetime(value):
    """Fecha y hora local como 06/10/2026 14:35."""
    if not value:
        return ""
    if timezone.is_aware(value):
        value = timezone.localtime(value)
    return date_format(value, "d/m/Y H:i")


def fmt_number(value):
    """Número con coma decimal y punto para los miles (1.250,5); sin ceros de más."""
    if value is None or value == "":
        return ""
    if isinstance(value, Decimal):
        text = format(value.normalize(), "f")
    else:
        text = str(value)
    negative = text.startswith("-")
    text = text.lstrip("-")
    whole, _, decimals = text.partition(".")
    whole = f"{int(whole):,}".replace(",", ".")
    text = f"{whole},{decimals}" if decimals else whole
    return f"-{text}" if negative else text


ISO_DATE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")


def humanize_dates(text):
    """Cambia las fechas 2026-10-06 de un texto por 06/10/2026.

    Los __str__ de los modelos (Actividad, Período, Meta) escriben la fecha en formato
    ISO; en pantalla se muestran igual que el resto de las fechas.
    """
    return ISO_DATE.sub(r"\3/\2/\1", str(text))


def initial_capital(text):
    """Pone en mayúscula solo la primera letra, sin tocar el resto (RUT sigue siendo RUT)."""
    text = str(text)
    return text[:1].upper() + text[1:]
