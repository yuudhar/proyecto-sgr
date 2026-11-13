"""Trimestres (períodos) de una atención: en cuál cae una fecha y cuál es el siguiente.

Una atención pertenece al trimestre cuyo período contiene su fecha: para pasarla a otro trimestre hay que cambiarle la
fecha (lo hace una solicitud de cambio de trimestre aprobada por Jefatura).
"""
from planning.models import Period


def period_of(day):
    """El período vigente (no archivado) que contiene esa fecha, o None."""
    if day is None:
        return None
    return (
        Period.objects.filter(deleted_at__isnull=True, start_date__lte=day, end_date__gte=day)
        .order_by("-start_date")
        .first()
    )


def next_period(period):
    """El primer período no archivado que empieza después de que termina el indicado, o None."""
    if period is None:
        return None
    return Period.objects.filter(deleted_at__isnull=True, start_date__gt=period.end_date).order_by("start_date").first()
