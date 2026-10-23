"""RF-026: meta esperada al día.

Regla de la guía (RN-007): meta esperada al día = días computables transcurridos / días computables
totales x 100. Tratamiento de las fechas extremas que usa el sistema:

* Un día es computable si es de lunes a viernes.
* El día de hoy ya cuenta como transcurrido (el primer día del período aporta 1 día y el último completa 100 %).
* Antes del inicio el esperado es 0 %; después del término, o con el período cerrado, es 100 %: nunca pasa de 100 %.
* El total de días que se muestra es el que el período declara en «días computables» (así se descuentan feriados);
  el porcentaje se calcula sobre los días hábiles del calendario del período y se reparte sobre ese total.
"""
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from django.utils import timezone

HUNDRED = Decimal(100)


def weekdays_between(start, end):
    """Cantidad de días de lunes a viernes entre dos fechas, ambas incluidas."""
    if end < start:
        return 0
    days = (end - start).days + 1
    full_weeks, extra = divmod(days, 7)
    total = full_weeks * 5
    first = start.weekday()
    for offset in range(extra):
        if (first + offset) % 7 < 5:
            total += 1
    return total


@dataclass(frozen=True)
class Pace:
    today: date
    start: date
    end: date
    total_days: int
    elapsed_days: int
    expected_percent: Decimal
    daily_percent: Decimal
    stage: str  # "not_started" | "running" | "finished"

    @property
    def remaining_days(self):
        return max(0, self.total_days - self.elapsed_days)

    @property
    def stage_label(self):
        return {
            "not_started": "Aún no comienza",
            "running": "En curso",
            "finished": "Terminado",
        }[self.stage]

    def expected_for(self, target):
        """Avance acumulado que se espera hoy para una meta con ese valor objetivo."""
        if target is None:
            return None
        return (Decimal(target) * self.expected_percent / HUNDRED).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

    def difference(self, achieved_percent):
        """Puntos porcentuales de diferencia entre lo logrado y lo esperado al día."""
        if achieved_percent is None:
            return None
        return Decimal(achieved_percent) - self.expected_percent

    def standing(self, achieved_percent, amber_threshold):
        """Compara el avance logrado con lo esperado (RN-008): al día, algo atrasado o muy atrasado."""
        if achieved_percent is None:
            return ""
        achieved = Decimal(achieved_percent)
        if achieved >= self.expected_percent:
            return "green"
        if achieved >= self.expected_percent * Decimal(amber_threshold) / HUNDRED:
            return "amber"
        return "red"


def pace_of(period, today=None):
    today = today or timezone.localdate()
    calendar_days = weekdays_between(period.start_date, period.end_date)
    total_days = period.computable_days or calendar_days

    if today < period.start_date:
        stage, elapsed_calendar = "not_started", 0
    elif today > period.end_date or period.status == "closed":
        stage, elapsed_calendar = "finished", calendar_days
    else:
        stage = "running"
        elapsed_calendar = weekdays_between(period.start_date, min(today, period.end_date))

    if calendar_days:
        ratio = Decimal(elapsed_calendar) / Decimal(calendar_days)
    else:
        ratio = Decimal(1) if stage == "finished" else Decimal(0)
    ratio = min(Decimal(1), ratio)

    expected = (ratio * HUNDRED).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    elapsed_days = min(total_days, int((ratio * total_days).quantize(Decimal(1), rounding=ROUND_HALF_UP)))
    daily = (HUNDRED / Decimal(total_days)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if total_days else Decimal(0)
    return Pace(
        today=today,
        start=period.start_date,
        end=period.end_date,
        total_days=total_days,
        elapsed_days=elapsed_days,
        expected_percent=expected,
        daily_percent=daily,
        stage=stage,
    )

