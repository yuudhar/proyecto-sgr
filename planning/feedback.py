"""RF-046: efecto de las felicitaciones y los reclamos sobre el resultado de un funcionario.

Reglas de la matriz (hoja RECLAMOS y hojas de cada cargo):

* Cada **felicitación** suma el valor del período (10 %) y se cuentan hasta un máximo por persona (3): las que pasan
  del máximo quedan registradas **sin efecto**.
* Cada **reclamo** resta el valor del período (30 %, el de las hojas de cada cargo).
* Un reclamo en **más de dos períodos seguidos** (trimestres) se informa a Recursos Humanos: aquí se muestra como aviso.

El ajuste (bonificación o penalización) lo genera este módulo al guardar o eliminar el registro: no se ingresa a mano.
Los valores y el máximo se configuran en cada período.
"""
from decimal import Decimal

from .models import Adjustment, Feedback, Period

HR_ALERT_PERIODS = 3  # más de dos períodos seguidos con reclamos


def period_for(day):
    """El período (no archivado) que incluye esa fecha, o None."""
    return (
        Period.objects.filter(deleted_at__isnull=True, start_date__lte=day, end_date__gte=day)
        .order_by("-start_date")
        .first()
    )


def value_of(feedback, period=None):
    period = period or feedback.period
    return period.compliment_value if feedback.kind == Feedback.Kind.COMPLIMENT else period.complaint_value


def reason_of(feedback):
    text = " ".join(feedback.description.split())
    return f"{feedback.get_kind_display()}: {text}"[:255]


def sync(officer_id, period_id):
    """Deja los ajustes de un funcionario en un período al día con sus felicitaciones y reclamos.

    Las felicitaciones se ordenan por fecha: las primeras (hasta el máximo del período) tienen efecto.
    """
    period = Period.objects.filter(pk=period_id).first()
    if period is None:
        return
    rows = Feedback.objects.filter(officer_id=officer_id, period_id=period_id).select_related("adjustment")
    used = 0
    for feedback in rows.order_by("date", "pk"):
        archived = feedback.deleted_at is not None
        effective = True
        if not archived and feedback.kind == Feedback.Kind.COMPLIMENT:
            effective = used < period.compliment_limit
            used += 1
        adjustment = feedback.adjustment
        if archived or not effective:
            if adjustment is not None and adjustment.deleted_at is None:
                Adjustment.objects.filter(pk=adjustment.pk).update(deleted_at=_now())
            if not archived:
                Feedback.objects.filter(pk=feedback.pk).update(effective=False)
            continue
        kind = Adjustment.Kind.BONUS if feedback.kind == Feedback.Kind.COMPLIMENT else Adjustment.Kind.PENALTY
        fields = {
            "kind": kind,
            "reason": reason_of(feedback),
            "percentage_value": value_of(feedback, period),
            "officer_id": officer_id,
            "period_id": period_id,
            "responsible_user_id": feedback.registered_by_id,
            "deleted_at": None,
        }
        if adjustment is None:
            adjustment = Adjustment.objects.create(**fields)
            Feedback.objects.filter(pk=feedback.pk).update(adjustment=adjustment, effective=True)
        else:
            Adjustment.objects.filter(pk=adjustment.pk).update(**fields)
            Feedback.objects.filter(pk=feedback.pk).update(effective=True)


def discard(adjustment_id):
    """Archiva el ajuste de un registro que se eliminó."""
    Adjustment.objects.filter(pk=adjustment_id, deleted_at__isnull=True).update(deleted_at=_now())


def _now():
    from django.utils import timezone

    return timezone.now()


def net_by_officer(period, officer_ids=None):
    """Suma de los ajustes de cada funcionario en el período (bonificaciones menos penalizaciones), en puntos porcentuales."""
    rows = Adjustment.objects.filter(deleted_at__isnull=True, period=period)
    if officer_ids is not None:
        rows = rows.filter(officer_id__in=list(officer_ids))
    net = {}
    for adjustment in rows:
        sign = 1 if adjustment.kind == Adjustment.Kind.BONUS else -1
        net[adjustment.officer_id] = net.get(adjustment.officer_id, Decimal(0)) + sign * adjustment.percentage_value
    return net


def complaint_streak(officer_id, period):
    """Cuántos períodos seguidos, hasta éste, tienen al menos un reclamo del funcionario."""
    periods = list(
        Period.objects.filter(deleted_at__isnull=True, start_date__lte=period.start_date).order_by("-start_date")
    )
    with_complaints = set(
        Feedback.objects.filter(
            officer_id=officer_id, kind=Feedback.Kind.COMPLAINT, deleted_at__isnull=True
        ).values_list("period_id", flat=True)
    )
    streak = 0
    for each in periods:
        if each.pk not in with_complaints:
            break
        streak += 1
    return streak


def hr_alert(feedback):
    """Aviso para informar a Recursos Humanos: el funcionario tiene reclamos en más de dos períodos seguidos."""
    if feedback.kind != Feedback.Kind.COMPLAINT or feedback.deleted_at is not None:
        return ""
    streak = complaint_streak(feedback.officer_id, feedback.period)
    if streak >= HR_ALERT_PERIODS:
        return f"Reclamos en {streak} períodos seguidos: informar a Recursos Humanos."
    return ""


def effect_text(feedback):
    """Lo que hace el registro sobre el resultado del funcionario, para el listado."""
    if feedback.deleted_at is not None:
        return "Archivado: sin efecto"
    if not feedback.effective:
        return f"Sin efecto: pasa del máximo de {feedback.period.compliment_limit} felicitaciones del período"
    value = f"{value_of(feedback):f}"
    if "." in value:
        value = value.rstrip("0").rstrip(".")
    value = value.replace(".", ",")
    return f"Suma {value} %" if feedback.kind == Feedback.Kind.COMPLIMENT else f"Resta {value} %"
