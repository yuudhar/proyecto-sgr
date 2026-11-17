"""Organigrama y calendario de una organización comunitaria (v52).

El organigrama sale de su directiva: presidente arriba; secretario y tesorero en el segundo nivel; directivos y otros
cargos en el tercero. Cada persona muestra qué actividad suya viene después, para ver quién hace qué y cuándo.
"""
from django.utils import timezone

from .models import OrganizationEvent, OrganizationLeader

Role = OrganizationLeader.Role


def leaders_of(organization):
    return [leader for leader in organization.leaders.all() if leader.deleted_at is None]


def events_of(organization):
    return list(
        OrganizationEvent.objects.filter(organization=organization, deleted_at__isnull=True)
        .select_related("responsible")
        .order_by("start_date", "end_date", "title")
    )


def next_event(events, leader, today):
    """La próxima actividad planificada que lidera esa persona (o la que está en curso), o None."""
    for event in events:
        if event.responsible_id == leader.pk and event.status == OrganizationEvent.Status.PLANNED and event.end_date >= today:
            return event
    return None


def build(organization, today=None):
    today = today or timezone.localdate()
    leaders = leaders_of(organization)
    events = events_of(organization)

    def node(leader):
        led = [event for event in events if event.responsible_id == leader.pk]
        return {"leader": leader, "next": next_event(events, leader, today), "events": len(led)}

    def holder(role):
        found = next((leader for leader in leaders if leader.role == role), None)
        return node(found) if found else None

    others = sorted(
        (leader for leader in leaders if leader.role in (Role.DIRECTOR, Role.OTHER)), key=lambda leader: leader.name
    )
    counts = {value: 0 for value, _ in OrganizationEvent.Status.choices}
    for event in events:
        counts[event.status] += 1
    return {
        "president": holder(Role.PRESIDENT),
        "secretary": holder(Role.SECRETARY),
        "treasurer": holder(Role.TREASURER),
        "others": [node(leader) for leader in others],
        "has_leaders": bool(leaders),
        "events": events,
        "counts": counts,
        "unassigned": sum(1 for event in events if event.responsible_id is None),
        "today": today,
    }
