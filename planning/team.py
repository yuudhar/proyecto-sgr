"""RF-048: puntaje de equipo (regla 10: equilibrado, juntos suman más que de forma individual).

Un equipo es la delegación (o el grupo de un cargo). El método, por cada ítem del equipo:

1. Se suman las metas ajustadas por ausencias (RF-047) y el avance válido de todos sus integrantes.
2. El cumplimiento del equipo en ese ítem es el avance sumado ÷ la meta sumada × 100, con el mismo tope del
   período (120 %) que el individual. Así lo que una persona logra de más compensa lo que a otra le falta, pero sin
   pasar del tope.
3. El aporte ponderado del ítem es el ponderador promedio de los integrantes × el cumplimiento del equipo ÷ 100.

El puntaje del equipo es la suma de esos aportes, llevada a base 100 (los ponderadores de un funcionario suman 100).
El aporte de cada persona es su parte del avance de cada ítem, así que los aportes suman el puntaje del equipo.
Los ajustes (felicitaciones y reclamos) son de la persona aludida y no entran al equipo.
"""
from decimal import ROUND_HALF_UP, Decimal

from core import ui

HUNDRED = Decimal(100)
CENTS = Decimal("0.01")


def money(value):
    return value.quantize(CENTS, rounding=ROUND_HALF_UP)


def team_score(summaries, period):
    """Puntaje de un equipo a partir de los resúmenes de sus funcionarios (`core.results.officer_summary`)."""
    items = {}
    for summary in summaries:
        for line in summary["lines"]:
            key = (line["goal"].item_id, line["unit"])
            row = items.setdefault(
                key,
                {"item": line["item"], "unit": line["unit"], "target": Decimal(0), "progress": Decimal(0), "weights": [], "people": {}},
            )
            progress = line["indicator"].progress if line["indicator"] is not None else Decimal(0)
            row["target"] += line["adjusted_target"]
            row["progress"] += progress
            row["weights"].append(line["weight"])
            row["people"][summary["officer"].pk] = row["people"].get(summary["officer"].pk, Decimal(0)) + progress

    cap = Decimal(period.weighted_cap)
    lines = []
    for row in sorted(items.values(), key=lambda each: each["item"].name):
        weight = sum(row["weights"], Decimal(0)) / len(row["weights"])
        percent = row["progress"] * HUNDRED / row["target"] if row["target"] else Decimal(0)
        compliance = min(percent, cap)
        lines.append({**row, "weight": weight, "percent": money(percent), "compliance": money(compliance),
                      "capped": percent > cap, "factor": (compliance / percent) if percent else Decimal(0)})

    total_weight = sum((line["weight"] for line in lines), Decimal(0))
    scale = HUNDRED / total_weight if total_weight else Decimal(0)
    exact = Decimal(0)
    for line in lines:
        value = line["weight"] * line["compliance"] / HUNDRED * scale
        exact += value
        line["weighted"] = money(value)

    contributions = {summary["officer"].pk: Decimal(0) for summary in summaries}
    for line in lines:
        if not line["target"]:
            continue
        for officer_id, progress in line["people"].items():
            contributions[officer_id] += line["weight"] * scale * (progress / line["target"]) * line["factor"]

    score = money(exact) if lines else None
    individual = [summary["weighted_total"] for summary in summaries if summary["weighted_total"] is not None]
    average = money(sum(individual, Decimal(0)) / len(individual)) if individual else None
    members = [
        {"officer": summary["officer"], "contribution": money(contributions[summary["officer"].pk])}
        for summary in summaries
        if summary["lines"]
    ]
    return {
        "lines": lines,
        "score": score,
        "individual_average": average,
        "difference": money(score - average) if score is not None and average is not None else None,
        "light": ui.light_for_compliance(score, period.collective_threshold, period.amber_threshold) if score is not None else "",
        "members": members,
        "people": len(summaries),
    }
