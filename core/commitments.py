"""Agenda colectiva: historial de estados (RF-018) y resumen colectivo (RF-021)."""
from collections import Counter
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.db.models import Count
from django.utils import timezone

from core.audit import log_event
from core.models import AuditLog
from operations.models import Commitment
from organization.models import Officer

STATUS_EVENT = "Estado de compromiso"
STATUS_ORDER = (
    Commitment.Status.SUBMITTED,
    Commitment.Status.PENDING,
    Commitment.Status.IN_PROGRESS,
    Commitment.Status.FULFILLED,
)
HUNDRED = Decimal(100)


def status_label(value):
    return dict(Commitment.Status.choices).get(value, value or "")


def record_status(user, commitment, previous, new):
    """Deja en la auditoría el cambio de estado (o el estado inicial, si no había uno anterior)."""
    log_event(user, STATUS_EVENT, commitment, previous=status_label(previous), new=status_label(new))


def history_of(commitment):
    entries = AuditLog.objects.filter(
        affected_entity=Commitment.__name__,
        record_id=commitment.pk,
        event=STATUS_EVENT,
        deleted_at__isnull=True,
    ).select_related("user").order_by("date", "pk")
    return [
        {
            "date": entry.date,
            "user": entry.user.get_full_name() or entry.user.get_username(),
            "previous": entry.previous_value or "",
            "new": entry.new_value or "",
        }
        for entry in entries
    ]


def percent(part, total):
    if not total:
        return None
    return (Decimal(part) * HUNDRED / Decimal(total)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def summary_row(label, counts, officer=None, deadlines=None):
    total = sum(counts.values())
    done = counts.get(Commitment.Status.FULFILLED, 0)
    deadlines = deadlines or {}
    return {
        "label": label,
        "officer": officer,
        "counts": [counts.get(status, 0) for status in STATUS_ORDER],
        "total": total,
        "done_percent": percent(done, total),
        "todo_percent": percent(total - done, total),
        "overdue": deadlines.get("overdue", 0),
        "due_soon": deadlines.get("due_soon", 0),
        "late": deadlines.get("done_late", 0),
    }


def collective_summary(commitments, officers, today=None):
    """Totales de compromisos por funcionario y estado, con % realizado y % por realizar (RF-021).

    `commitments` ya viene filtrado por alcance, delegación y período; `officers` son los funcionarios que
    se listan aunque todavía no tengan compromisos.
    """
    per_officer = {}
    for row in commitments.values("responsible_officer", "status").annotate(total=Count("pk")):
        per_officer.setdefault(row["responsible_officer"], {})[row["status"]] = row["total"]

    deadlines = deadline_counts(commitments, today)
    rows = [
        summary_row(officer.name, per_officer.get(officer.pk, {}), officer, deadlines.get(officer.pk))
        for officer in officers
    ]
    listed = {officer.pk for officer in officers}
    for officer_id, counts in per_officer.items():
        if officer_id not in listed:
            other = Officer.objects.filter(pk=officer_id).first()
            rows.append(
                summary_row(other.name if other else "Sin funcionario", counts, other, deadlines.get(officer_id))
            )

    totals, total_deadlines = {}, Counter()
    for counts in per_officer.values():
        for status, total in counts.items():
            totals[status] = totals.get(status, 0) + total
    for counts in deadlines.values():
        total_deadlines.update(counts)
    return rows, summary_row("Total", totals, deadlines=total_deadlines)


# --- RF-019: plazos -------------------------------------------------------------------------------------------------

# Cuántos días antes de la fecha comprometida un compromiso abierto pasa a «Por vencer».
DUE_SOON_DAYS = getattr(settings, "SGR_DIAS_POR_VENCER", 7)

DEADLINE_LABELS = {
    "overdue": "Vencido",
    "due_soon": "Por vencer",
    "on_time": "En plazo",
    "done_on_time": "Realizado en plazo",
    "done_late": "Realizado fuera de plazo",
}


def fulfilled_dates(commitment_ids):
    """Fecha en que cada compromiso quedó «Realizado», según el historial de estados (la última vez, si se reabrió)."""
    found = {}
    entries = AuditLog.objects.filter(
        affected_entity=Commitment.__name__,
        event=STATUS_EVENT,
        new_value=status_label(Commitment.Status.FULFILLED),
        record_id__in=list(commitment_ids),
        deleted_at__isnull=True,
    ).order_by("date", "pk")
    for entry in entries:
        found[entry.record_id] = timezone.localtime(entry.date).date()
    return found


def realized_on(commitment, dates=None):
    """Fecha de realización; si el compromiso es anterior al historial, se usa la de su última modificación."""
    dates = dates if dates is not None else fulfilled_dates([commitment.pk])
    return dates.get(commitment.pk) or timezone.localtime(commitment.updated_at).date()


def deadline_state(due_date, status, today, done_on=None):
    """Estado del plazo de un compromiso: vencido, por vencer, en plazo, o realizado en plazo / fuera de plazo."""
    if status == Commitment.Status.FULFILLED:
        return "done_late" if done_on is not None and done_on > due_date else "done_on_time"
    if due_date < today:
        return "overdue"
    if due_date <= today + timedelta(days=DUE_SOON_DAYS):
        return "due_soon"
    return "on_time"


def deadline_of(commitment, today=None):
    today = today or timezone.localdate()
    done_on = realized_on(commitment) if commitment.status == Commitment.Status.FULFILLED else None
    return deadline_state(commitment.due_date, commitment.status, today, done_on)


def deadline_text(commitment, today=None):
    """Frase para la ficha: «Vence en 3 días (25/10/2026)», «Realizado el 12/10/2026, 2 días después…»."""
    from core import ui

    today = today or timezone.localdate()
    state = deadline_of(commitment, today)
    due = ui.fmt_date(commitment.due_date)
    if state in ("done_on_time", "done_late"):
        done_on = realized_on(commitment)
        late = (done_on - commitment.due_date).days
        base = f"Realizado el {ui.fmt_date(done_on)}"
        if state == "done_late":
            return f"{base}, {late} día{'s' if late != 1 else ''} después de la fecha comprometida ({due})."
        return f"{base}, dentro del plazo ({due})."
    days = (commitment.due_date - today).days
    if state == "overdue":
        late = -days
        return f"Vencido hace {late} día{'s' if late != 1 else ''} (era para el {due})."
    if days == 0:
        return f"Vence hoy ({due})."
    when = f"Vence en {days} día{'s' if days != 1 else ''} ({due})."
    return when if state == "due_soon" else f"En plazo: {when[0].lower()}{when[1:]}"


def deadline_counts(commitments, today=None):
    """Cuenta los plazos de los compromisos de cada funcionario: {id del funcionario: Counter({estado: cantidad})}."""
    today = today or timezone.localdate()
    rows = list(commitments.values("pk", "due_date", "status", "responsible_officer_id", "updated_at"))
    done_ids = [row["pk"] for row in rows if row["status"] == Commitment.Status.FULFILLED]
    dates = fulfilled_dates(done_ids) if done_ids else {}
    counts = {}
    for row in rows:
        done_on = None
        if row["status"] == Commitment.Status.FULFILLED:
            done_on = dates.get(row["pk"]) or timezone.localtime(row["updated_at"]).date()
        state = deadline_state(row["due_date"], row["status"], today, done_on)
        counts.setdefault(row["responsible_officer_id"], Counter())[state] += 1
    return counts
