"""Trimestres (períodos) de una atención: en cuál cae una fecha y cuál es el siguiente.

Una atención pertenece al trimestre cuyo período contiene su fecha: para pasarla a otro trimestre hay que cambiarle la
fecha (lo hace una solicitud de cambio de trimestre aprobada por Jefatura). Desde la v51 los trimestres pueden ser de
una delegación: para una atención rige el de su delegación y, si no hay, el general.
"""
from planning import periods


def period_of(day, delegation=None):
    """El período vigente (no archivado) que contiene esa fecha para esa delegación, o None."""
    return periods.containing(day, delegation)


def next_period(period):
    """El primer período no archivado que empieza después de que termina el indicado, o None."""
    return periods.following(period)
