"""RF-047: ausencias y meta ajustada.

Regla elegida por el cliente: los días hábiles (lunes a viernes) de las ausencias del funcionario dentro del período
se descuentan de los días computables, y la meta baja en esa proporción:

    días efectivos = días computables − días hábiles de ausencia
    meta ajustada  = meta × días efectivos ÷ días computables

Todos los tipos de ausencia (licencia, vacaciones, día administrativo, emergencia y compensatorio) descuentan igual.
El ritmo esperado al día (`planning/pace.py`) y el cumplimiento usan esos días efectivos.
"""
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from .models import Absence
from .pace import weekdays_between

CENTS = Decimal("0.01")


@dataclass(frozen=True)
class AbsenceDays:
    """Días hábiles de ausencia de un funcionario en un período: todos y los ya transcurridos a una fecha."""

    total: int = 0
    elapsed: int = 0

    def __bool__(self):
        return self.total > 0


NONE = AbsenceDays()


def clipped_days(start, end, window_start, window_end):
    start, end = max(start, window_start), min(end, window_end)
    return weekdays_between(start, end) if start <= end else 0


def absence_map(officer_ids, period, today=None):
    """{id del funcionario: AbsenceDays} con una sola consulta."""
    ids = list(officer_ids)
    result = {officer_id: NONE for officer_id in ids}
    if not ids or period is None:
        return result
    rows = Absence.objects.filter(
        officer_id__in=ids,
        deleted_at__isnull=True,
        start_date__lte=period.end_date,
        end_date__gte=period.start_date,
    ).values_list("officer_id", "start_date", "end_date")
    totals, elapsed = {}, {}
    for officer_id, start, end in rows:
        totals[officer_id] = totals.get(officer_id, 0) + clipped_days(start, end, period.start_date, period.end_date)
        if today is not None:
            until = min(today, period.end_date)
            elapsed[officer_id] = elapsed.get(officer_id, 0) + clipped_days(start, end, period.start_date, until)
    for officer_id in totals:
        result[officer_id] = AbsenceDays(totals[officer_id], elapsed.get(officer_id, 0))
    return result


def kind_breakdown(officer_ids, period):
    """{id del funcionario: {tipo: días hábiles}} dentro del período, para el bloque «Ausencias del equipo»."""
    ids = list(officer_ids)
    result = {officer_id: {kind: 0 for kind in Absence.Kind.values} for officer_id in ids}
    if not ids or period is None:
        return result
    rows = Absence.objects.filter(
        officer_id__in=ids, deleted_at__isnull=True, start_date__lte=period.end_date, end_date__gte=period.start_date
    ).values_list("officer_id", "kind", "start_date", "end_date")
    for officer_id, kind, start, end in rows:
        result[officer_id][kind] += clipped_days(start, end, period.start_date, period.end_date)
    return result


def absence_days(officer_id, period, today=None):
    return absence_map([officer_id], period, today)[officer_id]


def effective_days(period, days):
    """Días computables del período menos los días hábiles de ausencia (nunca menos de 0)."""
    return max(0, int(period.computable_days) - days.total)


def adjusted_target(target, period, days):
    """Meta ajustada con los días efectivos (RF-047). Sin ausencias es la meta original."""
    target = Decimal(target)
    if not days or not period.computable_days:
        return target
    factor = Decimal(effective_days(period, days)) / Decimal(period.computable_days)
    return (target * factor).quantize(CENTS, rounding=ROUND_HALF_UP)
