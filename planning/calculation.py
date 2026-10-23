"""RF-022, RF-023, RF-024 y RF-014: cálculo automático de los indicadores.

Reglas de la guía (RN-003 a RN-005 y RN-009) y de la línea base académica (guía 13.1):

* **Avance** (RF-022): cantidad de actividades **válidas** del funcionario, en el ítem de la meta (o en una de sus
  sub atenciones) y dentro de las fechas del período. Una actividad es válida (RF-014) solo si tiene una
  evidencia **aprobada**: una evidencia pendiente, rechazada o eliminada no suma.
* **Cumplimiento** (RF-023): avance ÷ meta × 100, con tope en el «tope ponderado» del período (150 % al inicio).
* **Cumplimiento ponderado** (RF-024): ponderador de la meta × cumplimiento ÷ 100.
* **Semáforo**: el de siempre: verde desde el umbral colectivo del período, ámbar desde el umbral ámbar, rojo bajo eso.

Cada cálculo se guarda como un indicador nuevo, **solo si cambió** respecto del último del mismo funcionario y meta:
así la tabla conserva el historial sin llenarse de filas iguales. Una meta del cargo la cumple cada funcionario por
separado, por eso el indicador lleva el funcionario para el que se calculó.
"""
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Q

from core import ui
from operations.models import Activity
from organization.models import Officer

from .models import Goal, Indicator, Period

HUNDRED = Decimal(100)
CENTS = Decimal("0.01")

_state = threading.local()


@contextmanager
def suspended():
    """Pausa el recálculo automático (por ejemplo, mientras se cargan los datos de prueba)."""
    previous = getattr(_state, "suspended", False)
    _state.suspended = True
    try:
        yield
    finally:
        _state.suspended = previous


def is_suspended():
    return getattr(_state, "suspended", False)


@dataclass(frozen=True)
class Result:
    progress: Decimal
    compliance: Decimal
    weighting: Decimal
    light: str
    uncapped: Decimal


def officers_of(goal):
    """Funcionarios para los que se calcula una meta: el de una meta personal o todos los del cargo."""
    if goal.officer_id:
        officer = goal.officer
        return [officer] if officer.deleted_at is None else []
    if goal.position_id:
        return list(
            Officer.objects.filter(
                position_id=goal.position_id, status=Officer.Status.ACTIVE, deleted_at__isnull=True
            ).select_related("delegation")
        )
    return []


def valid_activities(goal, officer):
    """Actividades que cuentan para el avance: del funcionario, del ítem, del período y con evidencia aprobada."""
    from evidence.models import Evidence

    period = goal.period
    return (
        Activity.objects.filter(
            deleted_at__isnull=True,
            author_officer=officer,
            date__range=(period.start_date, period.end_date),
        )
        .filter(Q(item_id=goal.item_id) | Q(item__parent_item_id=goal.item_id))
        .filter(
            evidence_records__review_status=Evidence.ReviewStatus.APPROVED,
            evidence_records__deleted_at__isnull=True,
        )
        .distinct()
    )


def money(value):
    return value.quantize(CENTS, rounding=ROUND_HALF_UP)


def compute(goal, officer):
    period = goal.period
    progress = Decimal(valid_activities(goal, officer).count())
    target = Decimal(goal.target_value)
    uncapped = money(progress * HUNDRED / target) if target > 0 else Decimal(0)
    compliance = min(uncapped, Decimal(period.weighted_cap))
    weighting = money(Decimal(goal.weight) * compliance / HUNDRED)
    light = ui.light_for_compliance(compliance, period.collective_threshold, period.amber_threshold)
    return Result(progress=money(progress), compliance=compliance, weighting=weighting, light=light, uncapped=uncapped)


def calculable(goal, force=False):
    period = goal.period
    if goal.deleted_at is not None or period.deleted_at is not None:
        return False
    return force or period.status != Period.Status.CLOSED  # un período cerrado ya no cambia (RN-013)


def save_if_changed(goal, officer, result=None):
    """Guarda el cálculo como un indicador nuevo si cambió. Devuelve el indicador creado o None."""
    result = result or compute(goal, officer)
    last = (
        Indicator.objects.filter(goal=goal, officer=officer, deleted_at__isnull=True)
        .order_by("-calculated_at", "-pk")
        .first()
    )
    if (
        last is not None
        and last.progress == result.progress
        and last.compliance == result.compliance
        and last.weighting == result.weighting
        and last.status_light == result.light
    ):
        return None
    return Indicator.objects.create(
        goal=goal,
        officer=officer,
        progress=result.progress,
        compliance=result.compliance,
        weighting=result.weighting,
        status_light=result.light,
    )


def recalculate_goal(goal, officers=None, force=False):
    if not calculable(goal, force):
        return 0
    created = 0
    for officer in officers if officers is not None else officers_of(goal):
        created += save_if_changed(goal, officer) is not None
    return created


def recalculate_period(period, force=False):
    if period.deleted_at is not None or (period.status == Period.Status.CLOSED and not force):
        return 0
    goals = Goal.objects.filter(period=period, deleted_at__isnull=True).select_related("period", "officer", "item")
    return sum(recalculate_goal(goal, force=force) for goal in goals)


def recalculate_all(include_closed=False, period=None):
    periods = Period.objects.filter(deleted_at__isnull=True)
    if period is not None:
        periods = periods.filter(pk=period.pk)
    if not include_closed:
        periods = periods.exclude(status=Period.Status.CLOSED)
    return sum(recalculate_period(each, force=include_closed) for each in periods)


def recalculate_for(officer_id, item_ids, on_date):
    """Recalcula las metas de un funcionario que una actividad (de ese ítem y fecha) puede haber cambiado."""
    officer = Officer.objects.filter(pk=officer_id, deleted_at__isnull=True).first()
    if officer is None or not item_ids:
        return 0
    goals = (
        Goal.objects.filter(
            deleted_at__isnull=True,
            item_id__in=item_ids,
            period__start_date__lte=on_date,
            period__end_date__gte=on_date,
        )
        .filter(Q(officer_id=officer.pk) | Q(officer__isnull=True, position_id=officer.position_id))
        .select_related("period", "officer", "item")
    )
    return sum(recalculate_goal(goal, [officer]) for goal in goals)


class IndicatorIndex:
    """Último indicador de cada meta y funcionario, para mostrarlo en las pantallas."""

    def __init__(self, goal_ids):
        self.latest = {}
        rows = Indicator.objects.filter(goal_id__in=list(goal_ids), deleted_at__isnull=True).order_by(
            "goal_id", "officer_id", "-calculated_at", "-pk"
        )
        for indicator in rows:
            self.latest.setdefault((indicator.goal_id, indicator.officer_id), indicator)

    def of(self, goal, officer=None):
        """El indicador de esa meta para ese funcionario; si no hay uno propio, el general (sin funcionario)."""
        own = self.latest.get((goal.pk, officer.pk)) if officer is not None else None
        general = self.latest.get((goal.pk, None))
        found = [candidate for candidate in (own, general) if candidate is not None]
        if not found:
            return None
        return max(found, key=lambda each: (each.calculated_at, each.pk))

    def effective(self):
        """Un indicador por meta y funcionario, sin repetir el general cuando ya hay uno de cada funcionario."""
        goals_with_officers = {goal_id for (goal_id, officer_id) in self.latest if officer_id is not None}
        return [
            indicator
            for (goal_id, officer_id), indicator in self.latest.items()
            if officer_id is not None or goal_id not in goals_with_officers
        ]
