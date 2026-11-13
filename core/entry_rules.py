"""RF-041 y RF-042: reglas de ingreso de atenciones (límite diario y cierre semanal).

* La **semana** va de lunes a domingo: una fecha pertenece a la semana que la contiene.
* Las atenciones de una semana se pueden ingresar hasta el **lunes siguiente** (inclusive). Desde el martes ya no se
  ingresan las de la semana pasada: no se acumulan gestiones (regla 4 del cliente).
* La fecha de hoy es la de la zona del portal (Santiago), la misma que usa el sistema dentro de una petición.
* El límite diario (`settings.DAILY_ENTRY_LIMIT`, 7) se cuenta por la fecha de la atención.
"""
import calendar
from datetime import date, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone

from core import ui


def portal_today():
    """La fecha de hoy en la zona del portal (Santiago)."""
    return timezone.localtime(timezone.now(), ZoneInfo(settings.PORTAL_TIME_ZONE)).date()


def months_back(day, months):
    """El mismo día de hace `months` meses (el último del mes si ese día no existe: 29 de febrero, 31, etc.)."""
    year, month = divmod(day.year * 12 + day.month - 1 - months, 12)
    month += 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def earliest_date(today=None):
    """La fecha más antigua que se acepta al ingresar compromisos, gestiones, cartas y ausencias (`BACKDATE_MONTHS`)."""
    return months_back(today or portal_today(), settings.BACKDATE_MONTHS)


def week_start(day):
    return day - timedelta(days=day.weekday())


def week_end(day):
    return week_start(day) + timedelta(days=6)


def last_entry_day(day):
    """Último día en que se pueden ingresar las atenciones de la semana de `day`: el lunes siguiente."""
    return week_end(day) + timedelta(days=1)


def is_week_closed(day, today=None):
    return (today or portal_today()) > last_entry_day(day)


def week_text(day):
    return f"{ui.fmt_date(week_start(day))} al {ui.fmt_date(week_end(day))}"


def closed_message(day):
    return (
        f"La semana del {week_text(day)} ya cerró: se podía ingresar hasta el lunes {ui.fmt_date(last_entry_day(day))}. "
        "Desde el martes no se ingresan las atenciones de la semana pasada."
    )


def entries_on(officer_id, day, exclude_pk=None):
    """Atenciones de un funcionario con esa fecha, sin las archivadas (y sin la indicada)."""
    from operations.models import Activity

    found = Activity.objects.filter(author_officer_id=officer_id, date=day, deleted_at__isnull=True)
    if exclude_pk is not None:
        found = found.exclude(pk=exclude_pk)
    return found.count()


def daily_state(officer_id, day=None):
    """(llevadas, máximo) del día: «Hoy llevas 4 de 7»."""
    return entries_on(officer_id, day or portal_today()), settings.DAILY_ENTRY_LIMIT


def week_notice(day=None):
    day = day or portal_today()
    return (
        f"La semana del {week_text(day)} se puede ingresar hasta el lunes {ui.fmt_date(last_entry_day(day))}."
    )
