"""Tubo de cartas (v51): alta desde una atención y paso automático a «Vencido».

Cada atención que se registra deja una actividad en «Ingresado» con una fecha comprometida por defecto: el último día
del trimestre de la atención (el de su delegación o, si no tiene, el general). Una actividad que sigue «Ingresado» o «Pendiente» cuando pasa su fecha
comprometida queda «Vencido»; si después se mueve la fecha hacia adelante, vuelve a «Pendiente».
"""
from datetime import timedelta

from django.utils import timezone

from planning import periods

from .models import TubeItem

DEFAULT_DAYS = 15  # solo si no hay un trimestre definido para esa fecha


def default_due_date(day, delegation=None):
    """El último día del trimestre que contiene la fecha para esa delegación; sin trimestre, `DEFAULT_DAYS` días después."""
    period = periods.containing(day, delegation)
    if period is not None:
        return period.end_date
    return day + timedelta(days=DEFAULT_DAYS)


def requester_of(activity):
    """Quién pide: el contacto de la atención o, si no hay, la organización o el beneficiario ligados a ella."""
    if activity.contact_name:
        return activity.contact_name
    if activity.organization_id:
        return activity.organization.name
    if activity.beneficiary_id:
        return str(activity.beneficiary)
    return ""


def title_for(activity):
    item = activity.item.name if activity.item_id else "Atención"
    return f"{item} · {requester_of(activity) or 'sin contacto'}"[:200]


def status_for(activity):
    """Estado inicial según cómo va la atención: cerrada = realizada; en proceso = pendiente; recién registrada = ingresada."""
    if activity.status == "closed":
        return TubeItem.Status.FULFILLED
    if activity.status == "in_progress":
        return TubeItem.Status.PENDING
    return TubeItem.Status.SUBMITTED


def due_date_for(activity):
    """La fecha del compromiso enlazado si la atención ya tiene uno; si no, el fin del trimestre de la atención."""
    commitment = getattr(activity, "commitment", None)
    if commitment is not None and commitment.due_date >= activity.date:
        return commitment.due_date
    return default_due_date(activity.date, activity.delegation)


def create_for_activity(activity):
    """Deja la atención en el tubo de cartas. Si ya tiene su actividad, no crea otra y devuelve la que hay."""
    existing = TubeItem._base_manager.filter(activity=activity).first()
    if existing is not None:
        return existing
    return TubeItem.objects.create(
        title=title_for(activity),
        description=activity.request_description or "",
        requester=requester_of(activity)[:100],
        entered_date=activity.date,
        due_date=due_date_for(activity),
        status=status_for(activity),
        responsible_officer=activity.author_officer,
        delegation=activity.delegation,
        activity=activity,
    )


def follow_activity(activity):
    """Cuando la atención se cierra, su actividad del tubo queda «Realizado». Devuelve la actividad si cambió."""
    item = TubeItem.objects.filter(activity=activity).first()
    if item is None or item.status == TubeItem.Status.FULFILLED or activity.status != "closed":
        return None
    item.previous_label = item.get_status_display()
    item.status = TubeItem.Status.FULFILLED
    item.save(update_fields=["status", "updated_at"])
    return item


def sync_overdue(today=None, queryset=None):
    """Pone «Vencido» a lo que pasó su fecha sin realizarse y devuelve a «Pendiente» lo que ya tiene fecha futura.

    Devuelve cuántas actividades pasaron a vencidas y cuántas volvieron a pendientes.
    """
    today = today or timezone.localdate()
    queryset = TubeItem.objects.all() if queryset is None else queryset
    live = queryset.filter(deleted_at__isnull=True)
    now = timezone.now()
    overdue = live.filter(
        due_date__lt=today, status__in=(TubeItem.Status.SUBMITTED, TubeItem.Status.PENDING)
    ).update(status=TubeItem.Status.OVERDUE, updated_at=now)
    back = live.filter(due_date__gte=today, status=TubeItem.Status.OVERDUE).update(
        status=TubeItem.Status.PENDING, updated_at=now
    )
    return overdue, back


def load_sample(delegation, count, today=None):
    """Datos de ejemplo coherentes: pasa al tubo las atenciones más recientes de la delegación que aún no están en él.

    Cada actividad sale de su atención (título, solicitante, descripción, funcionario, fecha, compromiso enlazado) y su
    estado sigue el de la atención; «Vencido» lo calcula el sistema por la fecha. Es seguro repetirlo.
    Devuelve cuántas actividades creó.
    """
    from operations.models import Activity

    existing = TubeItem._base_manager.filter(delegation=delegation).count()
    missing = max(0, count - existing)
    if not missing:
        return 0
    activities = (
        Activity.objects.filter(delegation=delegation, deleted_at__isnull=True, tube_item__isnull=True)
        .select_related("item", "author_officer", "organization", "beneficiary", "commitment")
        .order_by("-date", "-pk")[:missing]
    )
    created = 0
    for activity in activities:
        create_for_activity(activity)
        created += 1
    sync_overdue(today, TubeItem.objects.filter(delegation=delegation))
    return created
