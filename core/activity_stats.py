"""RF-030: actividad reciente por funcionario.

Para cada funcionario: la fecha de su último ingreso, los días sin ingreso, la cantidad de registros del período
y el promedio diario (registros ÷ días computables transcurridos del período). Los registros son las actividades
que el funcionario registró como autor, sin contar las archivadas.
"""
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Count, Max, Q
from django.utils import timezone

from operations.models import Activity

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
    elapsed = pace.elapsed_days if pace is not None else None
    result = {}
    for officer_id in ids:
        row = found.get(officer_id)
        if row is None:
            result[officer_id] = Recent(None, None, 0, daily_average(0, elapsed))
            continue
        result[officer_id] = Recent(
            last_date=row["last"],
            days_without=(today - row["last"]).days,
            total=row["total"],
            daily_average=daily_average(row["total"], elapsed),
        )
    return result


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
