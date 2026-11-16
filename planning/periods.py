"""Períodos (trimestres) por delegación (v51).

Un período sin delegación rige para todas; uno con delegación rige solo para esa. Cuando una fecha cae en los dos, manda
el de la delegación. Si no se dice la delegación, solo cuentan los períodos generales.
"""
from django.db.models import F, Q

from .models import Period


def scoped(delegation=None):
    """Los períodos no archivados que rigen para una delegación: los suyos y los generales."""
    periods = Period.objects.filter(deleted_at__isnull=True)
    if delegation is None:
        return periods.filter(delegation__isnull=True)
    return periods.filter(Q(delegation=delegation) | Q(delegation__isnull=True))


def containing(day, delegation=None):
    """El período que rige para la delegación y contiene esa fecha, o None. El de la delegación gana al general."""
    if day is None:
        return None
    return (
        scoped(delegation)
        .filter(start_date__lte=day, end_date__gte=day)
        .order_by(F("delegation").asc(nulls_last=True), "-start_date")
        .first()
    )


def following(period):
    """El primer período que empieza después de que termina el indicado y rige para la misma delegación, o None."""
    if period is None:
        return None
    return (
        scoped(period.delegation)
        .filter(start_date__gt=period.end_date)
        .order_by("start_date", F("delegation").asc(nulls_last=True))
        .first()
    )


def visible(request_delegation):
    """Los períodos que se muestran en un selector: sin delegación elegida, todos; con una, los suyos y los generales."""
    if request_delegation is None:
        return Period.objects.filter(deleted_at__isnull=True)
    return scoped(request_delegation)
