from django.db.models import Q

from accounts.models import RoleProfile, UserRoleDelegation, role_details
from organization.models import Delegation


def effective_rows(user):
    return UserRoleDelegation.objects.filter(
        user=user,
        deleted_at__isnull=True,
        delegation__isnull=False,
        delegation__deleted_at__isnull=True,
        delegation__status=Delegation.Status.ACTIVE,
        role__in=user.groups.all(),
    ).filter(Q(role__role_profile__status=RoleProfile.Status.ACTIVE) | Q(role__role_profile__isnull=True))


def extra_delegations(user):
    ids = effective_rows(user).values("delegation_id")
    return Delegation.objects.filter(pk__in=ids, deleted_at__isnull=True).order_by("pk")


def listed_extra_delegations(user):
    held = {group.pk: group for group in user.groups.all()}
    found = {}
    for row in user.role_delegations.all():
        delegation = row.delegation
        if row.deleted_at is not None or delegation is None or row.role_id not in held:
            continue
        if delegation.deleted_at is not None or delegation.status != Delegation.Status.ACTIVE:
            continue
        if role_details(held[row.role_id]).status != RoleProfile.Status.ACTIVE:
            continue
        found[delegation.pk] = delegation
    return [found[key] for key in sorted(found)]


def stored_delegation_ids(user):
    return set(
        UserRoleDelegation.objects.filter(user=user, deleted_at__isnull=True, delegation__isnull=False)
        .values_list("delegation_id", flat=True)
        .distinct()
    )


def sync_extra_delegations(user, delegations):
    delegation_ids = {delegation.pk for delegation in delegations}
    role_ids = set(user.groups.values_list("pk", flat=True))
    wanted = {(role_id, delegation_id) for role_id in role_ids for delegation_id in delegation_ids}
    existing = {(row.role_id, row.delegation_id): row for row in UserRoleDelegation.objects.filter(user=user)}
    added = removed = 0
    for key, row in existing.items():
        if key not in wanted:
            row.delete()
            removed += 1
        elif row.deleted_at is not None:
            row.deleted_at = None
            row.save(update_fields=["deleted_at", "updated_at"])
            added += 1
    for role_id, delegation_id in sorted(wanted - set(existing)):
        UserRoleDelegation.objects.create(user=user, role_id=role_id, delegation_id=delegation_id)
        added += 1
    return added, removed
