import re

from django.core.exceptions import PermissionDenied
from django.db.models import Q

from core.admin_utils import NO_DELEGATION_MESSAGE, get_user_delegation
from core.roles import GLOBAL_ROLE, SUPERUSER_ROLE, sort_key

GLOBAL_GROUP = GLOBAL_ROLE

_MISSING = object()

SESSION_DELEGATION = "sgr_delegation"
ALL_DELEGATIONS = "todas"


def request_roles(request):
    value = getattr(request, "_sgr_roles", _MISSING)
    if value is _MISSING:
        user = request.user
        value = sorted(user.groups.values_list("name", flat=True), key=sort_key)
        if user.is_superuser:
            value.insert(0, SUPERUSER_ROLE)
        request._sgr_roles = value
    return value


def has_global_role(user):
    from accounts.models import RoleProfile

    return user.groups.filter(
        Q(role_profile__scope=RoleProfile.Scope.ALL, role_profile__status=RoleProfile.Status.ACTIVE)
        | Q(role_profile__isnull=True, name=GLOBAL_ROLE)
    ).exists()


def is_global_user(request):
    value = getattr(request, "_sgr_is_global", _MISSING)
    if value is _MISSING:
        value = request.user.is_superuser or has_global_role(request.user)
        request._sgr_is_global = value
    return value


def request_officer(request):
    value = getattr(request, "_sgr_officer", _MISSING)
    if value is _MISSING:
        profile = getattr(request.user, "profile", None)
        value = profile.officer if profile is not None else None
        request._sgr_officer = value
    return value


def home_delegation(request):
    officer = request_officer(request)
    if officer is None or officer.delegation_id is None:
        return None
    return officer.delegation


def authorized_delegations(request):
    value = getattr(request, "_sgr_authorized", _MISSING)
    if value is _MISSING:
        from accounts.delegations import extra_delegations
        from organization.models import Delegation

        if is_global_user(request):
            value = list(Delegation.objects.filter(deleted_at__isnull=True).order_by("pk"))
        else:
            found = {delegation.pk: delegation for delegation in extra_delegations(request.user)}
            home = home_delegation(request)
            if home is not None:
                found[home.pk] = home
            value = sorted(found.values(), key=lambda delegation: delegation.pk)
        request._sgr_authorized = value
    return value


def can_choose_delegation(request):
    authorized = authorized_delegations(request)
    return len(authorized) > 1 or (is_global_user(request) and len(authorized) >= 1)


def active_delegation(request):
    value = getattr(request, "_sgr_active", _MISSING)
    if value is _MISSING:
        authorized = authorized_delegations(request)
        by_id = {delegation.pk: delegation for delegation in authorized}
        everything = is_global_user(request)
        raw = request.session.get(SESSION_DELEGATION)
        chosen = None
        valid = raw is None
        if raw == ALL_DELEGATIONS and everything:
            valid = True
        elif isinstance(raw, int) and not isinstance(raw, bool) and raw in by_id:
            chosen, valid = by_id[raw], True
        if not valid:
            request.session.pop(SESSION_DELEGATION, None)
        if chosen is None and not everything:
            home = home_delegation(request)
            chosen = home if home is not None else (authorized[0] if authorized else None)
            if chosen is None:
                raise PermissionDenied(NO_DELEGATION_MESSAGE)
        value = chosen
        request._sgr_active = value
    return value


def request_delegation(request):
    value = getattr(request, "_sgr_delegation", _MISSING)
    if value is _MISSING:
        chosen = active_delegation(request)
        value = chosen if chosen is not None else get_user_delegation(request)
        request._sgr_delegation = value
    return value


def default_delegation(request):
    delegation = request_delegation(request)
    return delegation if delegation is not None else home_delegation(request)


def delegation_choice(request, raw):
    text = str(raw or "").strip()
    if text == ALL_DELEGATIONS:
        return (True, None) if is_global_user(request) else (False, None)
    if re.fullmatch(r"[0-9]{1,18}", text):
        for delegation in authorized_delegations(request):
            if delegation.pk == int(text):
                return True, delegation
    return False, None


def remember_delegation(request, delegation):
    request.session[SESSION_DELEGATION] = delegation.pk if delegation is not None else ALL_DELEGATIONS
    for name in ("_sgr_active", "_sgr_delegation"):
        if hasattr(request, name):
            delattr(request, name)


def delegation_id_of(obj, lookup):
    *steps, last = lookup.split("__")
    value = obj
    for step in steps:
        value = getattr(value, step, None)
        if value is None:
            return None
    return getattr(value, f"{last}_id", None)
