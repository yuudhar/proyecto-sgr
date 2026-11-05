"""RF-030: actividad reciente por funcionario.

Para cada funcionario: la fecha de su último ingreso, los días sin ingreso, la cantidad de registros del período
y el promedio diario (registros ÷ días computables transcurridos del período). Los registros son las actividades
que el funcionario registró como autor, sin contar las archivadas.

Los días de ausencia (RF-047) no cuentan: ni entre los días sin ingreso ni entre los días del promedio diario.
"""
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Count, Max, Q
from django.utils import timezone

from operations.models import Activity
from planning.absences import absence_map
from planning.models import Absence
from planning.pace import pace_of

# Desde cuántos días sin ingreso se marca en alerta.
ALERT_DAYS = 7


@dataclass(frozen=True)
class Recent:
    last_date: date | None
    days_without: int | None
    total: int
    daily_average: Decimal | None

    @property
    def alert(self):
        return self.days_without is None or self.days_without > ALERT_DAYS


def daily_average(total, elapsed_days):
    if not elapsed_days:
        return None
    return (Decimal(total) / Decimal(elapsed_days)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def recent_activity(officer_ids, period, pace=None, today=None):
    """Devuelve {id del funcionario: Recent} para esos funcionarios."""
    today = today or timezone.localdate()
    ids = list(officer_ids)
    in_period = Q()
    if period is not None:
        in_period = Q(date__range=(period.start_date, period.end_date))
    base = Activity.objects.filter(deleted_at__isnull=True, author_officer_id__in=ids, date__lte=today)
    rows = base.values("author_officer_id").annotate(last=Max("date"), total=Count("pk", filter=in_period))
    found = {row["author_officer_id"]: row for row in rows}
    away = absence_map(ids, period, today) if period is not None else {}
    elapsed = pace.elapsed_days if pace is not None else None
    ranges = absence_ranges(ids, today)
    result = {}
    for officer_id in ids:
        days = away.get(officer_id)
        own_elapsed = pace_of(period, pace.today, days).elapsed_days if (pace is not None and days) else elapsed
        row = found.get(officer_id)
        if row is None:
            result[officer_id] = Recent(None, None, 0, daily_average(0, own_elapsed))
            continue
        result[officer_id] = Recent(
            last_date=row["last"],
            days_without=max(0, (today - row["last"]).days - absent_calendar_days(ranges.get(officer_id, ()), row["last"], today)),
            total=row["total"],
            daily_average=daily_average(row["total"], own_elapsed),
        )
    return result


def absence_ranges(officer_ids, today):
    """{id del funcionario: [(desde, hasta)]} de las ausencias que empezaron hasta hoy."""
    found = {}
    rows = Absence.objects.filter(
        officer_id__in=list(officer_ids), deleted_at__isnull=True, start_date__lte=today
    ).values_list("officer_id", "start_date", "end_date")
    for officer_id, start, end in rows:
        found.setdefault(officer_id, []).append((start, end))
    return found


def absent_calendar_days(ranges, last, today):
    """Días corridos de ausencia entre el último ingreso (sin contarlo) y hoy (incluido)."""
    total = 0
    for start, end in ranges:
        first, final = max(start, last + timedelta(days=1)), min(end, today)
        if first <= final:
            total += (final - first).days + 1
    return total


def delegation_recent(recent, pace=None, today=None):
    """Resumen de varios funcionarios (lámina 18): último ingreso más reciente, registros y promedio diario."""
    today = today or timezone.localdate()
    dates = [item.last_date for item in recent.values() if item.last_date is not None]
    last = max(dates) if dates else None
    total = sum(item.total for item in recent.values())
    elapsed = pace.elapsed_days if pace is not None else None
    return Recent(
        last_date=last,
        days_without=(today - last).days if last else None,
        total=total,
        daily_average=daily_average(total, elapsed),
    )
