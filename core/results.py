"""Cálculos para mostrar resultados: promedios, semáforo, líneas de metas y totales ponderados de un funcionario.

Los usan el dashboard, el tablero de delegación, los informes, la vista por cargos y la ficha personal, para que
todas las pantallas muestren los mismos números.
"""
from decimal import ROUND_HALF_UP, Decimal

from core import ui

HUNDRED = Decimal(100)


def current_period():
    from planning.models import Period

    periods = Period.objects.filter(deleted_at__isnull=True).order_by("-start_date")
    return periods.filter(status=Period.Status.ACTIVE).first() or periods.first()


def team_goals(summaries):
    """Cifras logradas por el equipo: por ítem y unidad, la suma de los objetivos y del avance de sus funcionarios."""
    teams = {}
    for summary in summaries:
        for line in summary["lines"]:
            key = (line["item"].name, line["unit"])
            row = teams.setdefault(key, {"item": line["item"], "unit": line["unit"], "target": Decimal(0), "progress": Decimal(0)})
            row["target"] += line["goal"].target_value
            if line["indicator"] is not None:
                row["progress"] += line["indicator"].progress
    rows = []
    for row in sorted(teams.values(), key=lambda each: each["item"].name):
        row["percent"] = rounded(row["progress"] * HUNDRED / row["target"]) if row["target"] else None
        rows.append(row)
    return rows


def mean(values):
    values = list(values)
    if not values:
        return None
    return sum(values, Decimal(0)) / len(values)


def rounded(value):
    if value is None:
        return None
    return value.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def light_of(value, period):
    if value is None:
        return ""
    return ui.light_for_compliance(value, period.collective_threshold, period.amber_threshold)


def goals_of(officer, goals):
    return [
        goal
        for goal in goals
        if goal.officer_id == officer.pk
        or (goal.officer_id is None and goal.position_id == officer.position_id)
    ]


def goal_lines(goals, index, pace=None, officer=None):
    lines = []
    for goal in goals:
        indicator = index.of(goal, officer)
        lines.append(
            {
                "goal": goal,
                "item": goal.item,
                "target": ui.fmt_number(goal.target_value),
                "expected": ui.fmt_number(pace.expected_for(goal.target_value)) if pace else "",
                "unit": goal.unit,
                "scope": "Meta personal" if goal.officer_id else "Meta del cargo",
                "weight": goal.weight,
                "indicator": indicator,
                "progress": ui.fmt_number(indicator.progress) if indicator else "",
                "compliance": indicator.compliance if indicator else None,
                "weighted": indicator.weighting if indicator else None,
                "light": indicator.status_light if indicator else "",
            }
        )
    return lines


WEIGHT_STATES = {
    "ok": "Los ponderadores suman 100 %",
    "under": "Los ponderadores suman menos de 100 %",
    "over": "Los ponderadores suman más de 100 %",
}


def weights_state(total):
    """RF-006: los ponderadores aplicables a un funcionario en un período deben sumar 100 %."""
    if total is None:
        return ""
    if total == HUNDRED:
        return "ok"
    return "under" if total < HUNDRED else "over"


def officer_summary(officer, period, goals, index, pace=None):
    """Metas del funcionario con su avance, cumplimiento, ponderador y aporte ponderado (RF-008)."""
    own = goals_of(officer, goals)
    lines = goal_lines(own, index, pace, officer)
    compliances = [line["compliance"] for line in lines if line["compliance"] is not None]
    exact = mean(compliances)
    weights = sum((line["weight"] for line in lines), Decimal(0)) if lines else None
    weighted = [line["weighted"] for line in lines if line["weighted"] is not None]
    state = weights_state(weights)
    return {
        "officer": officer,
        "lines": lines,
        "goal_total": len(own),
        "exact_average": exact,
        "average": rounded(exact),
        "light": light_of(exact, period),
        "weights_total": weights,
        "weights_state": state,
        "weights_text": WEIGHT_STATES.get(state, ""),
        "weighted_total": sum(weighted, Decimal(0)) if weighted else None,
    }


def officer_weights(period, officer):
    """Suma de los ponderadores de las metas de un funcionario en un período (personales y del cargo)."""
    from django.db.models import Q
    from planning.models import Goal

    goals = Goal.objects.filter(deleted_at__isnull=True, period=period).filter(
        Q(officer=officer) | Q(officer__isnull=True, position_id=officer.position_id)
    )
    total = sum((goal.weight for goal in goals), Decimal(0))
    return total if goals else None


def weight_problems(goal):
    """Funcionarios afectados por una meta cuyos ponderadores del período no suman 100 % (RF-006)."""
    from planning.calculation import officers_of

    problems = []
    for officer in officers_of(goal):
        total = officer_weights(goal.period, officer)
        state = weights_state(total)
        if state and state != "ok":
            problems.append((officer, total, state))
    return problems
