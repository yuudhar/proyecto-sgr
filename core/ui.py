import re
from decimal import Decimal

from django.utils import timezone
from django.utils.formats import date_format

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
    "overdue": ("bad", "bi-exclamation-octagon-fill"),
    "due_soon": ("warn", "bi-hourglass-split"),
    "on_time": ("neutral", "bi-calendar-check"),
    "done_on_time": ("ok", "bi-check-circle-fill"),
    "done_late": ("warn", "bi-check-circle"),
    "green": ("ok", "bi-check-circle-fill"),
    "amber": ("warn", "bi-exclamation-triangle-fill"),
    "red": ("bad", "bi-x-octagon-fill"),
}

LIGHT_LABELS = {"green": "Verde", "amber": "Ámbar", "red": "Rojo"}


def tone_for(value):
    return TONES.get(value, ("neutral", ""))


def light_for_compliance(compliance, collective_threshold, amber_threshold):
    if compliance >= collective_threshold:
        return "green"
    if compliance >= amber_threshold:
        return "amber"
    return "red"


def fmt_date(value):
    return date_format(value, "d/m/Y") if value else ""


def fmt_datetime(value):
    if not value:
        return ""
    if timezone.is_aware(value):
        value = timezone.localtime(value)
    return date_format(value, "d/m/Y H:i")


def fmt_number(value):
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
    return ISO_DATE.sub(r"\3/\2/\1", str(text))


def initial_capital(text):
    text = str(text)
    return text[:1].upper() + text[1:]
