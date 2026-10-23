"""Agenda colectiva: historial de estados (RF-018) y resumen colectivo (RF-021)."""
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Count

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


def summary_row(label, counts, officer=None):
    total = sum(counts.values())
    done = counts.get(Commitment.Status.FULFILLED, 0)
    return {
        "label": label,
        "officer": officer,
        "counts": [counts.get(status, 0) for status in STATUS_ORDER],
        "total": total,
        "done_percent": percent(done, total),
        "todo_percent": percent(total - done, total),
    }


def collective_summary(commitments, officers):
    """Totales de compromisos por funcionario y estado, con % realizado y % por realizar (RF-021).

    `commitments` ya viene filtrado por alcance, delegación y período; `officers` son los funcionarios que
    se listan aunque todavía no tengan compromisos.
    """
    per_officer = {}
    for row in commitments.values("responsible_officer", "status").annotate(total=Count("pk")):
        per_officer.setdefault(row["responsible_officer"], {})[row["status"]] = row["total"]

    rows = [
        summary_row(officer.name, per_officer.get(officer.pk, {}), officer)
        for officer in officers
    ]
    listed = {officer.pk for officer in officers}
    for officer_id, counts in per_officer.items():
        if officer_id not in listed:
            other = Officer.objects.filter(pk=officer_id).first()
            rows.append(summary_row(other.name if other else "Sin funcionario", counts, other))

    totals = {}
    for counts in per_officer.values():
        for status, total in counts.items():
            totals[status] = totals.get(status, 0) + total
    return rows, summary_row("Total", totals)
