"""Reglas de acceso de las pantallas web: roles, delegación y funcionario.

Son las mismas reglas del Django Admin (core/admin_mixins.py): el superusuario
y los roles con alcance sobre todas las delegaciones (el de fábrica es Coordinación)
las ven todas; el resto solo ve la delegación de su funcionario. Los resultados se guardan en el request para no
repetir consultas dentro de una misma petición.

Desde la v9 la persona puede trabajar en más de una delegación (A2: «Cuando el perfil permita varias delegaciones, el
selector debe mostrar únicamente las autorizadas»). Cuál es la delegación activa se guarda en la sesión (Clase 6:
estado temporal de quien tiene la sesión iniciada) y se vuelve a comprobar en el servidor en cada petición (Clase 7:
ocultar un botón no es control de acceso): una delegación que ya no está autorizada se olvida sola.
"""

import re

from django.core.exceptions import PermissionDenied
from django.db.models import Q

from core.admin_utils import NO_DELEGATION_MESSAGE, get_user_delegation
from core.roles import GLOBAL_ROLE, SUPERUSER_ROLE, sort_key

GLOBAL_GROUP = GLOBAL_ROLE

_MISSING = object()

# Delegación elegida en el selector de la franja de arriba: el id de la delegación, o ALL_DELEGATIONS.
SESSION_DELEGATION = "sgr_delegation"
ALL_DELEGATIONS = "todas"


def request_roles(request):
    """Nombres de los perfiles del usuario ("Super Usuario" primero si lo es), ya ordenados."""
    value = getattr(request, "_sgr_roles", _MISSING)
    if value is _MISSING:
        user = request.user
        value = sorted(user.groups.values_list("name", flat=True), key=sort_key)
        if user.is_superuser:
            value.insert(0, SUPERUSER_ROLE)
        request._sgr_roles = value
    return value


def has_global_role(user):
    """True si alguno de los roles del usuario está activo y da alcance sobre todas las delegaciones.

    El alcance sale de la ficha del rol (accounts.RoleProfile), que se edita en el mantenedor de Roles.
    Un grupo que todavía no tiene ficha se reconoce como siempre, por su nombre: «Coordinación».
    """
    from accounts.models import RoleProfile

    return user.groups.filter(
        Q(role_profile__scope=RoleProfile.Scope.ALL, role_profile__status=RoleProfile.Status.ACTIVE)
        | Q(role_profile__isnull=True, name=GLOBAL_ROLE)
    ).exists()


def is_global_user(request):
    """True si el usuario puede ver todas las delegaciones (superusuario o un rol con ese alcance, como Coordinación).

    Es lo que la persona tiene autorizado, no lo que está mirando ahora: quien puede ver todas elige en la franja de
    arriba si trabaja con todas o con una (ver active_delegation).
    """
    value = getattr(request, "_sgr_is_global", _MISSING)
    if value is _MISSING:
        value = request.user.is_superuser or has_global_role(request.user)
        request._sgr_is_global = value
    return value


def request_officer(request):
    """Funcionario vinculado al usuario, o None si no tiene."""
    value = getattr(request, "_sgr_officer", _MISSING)
    if value is _MISSING:
        profile = getattr(request.user, "profile", None)
        value = profile.officer if profile is not None else None
        request._sgr_officer = value
    return value


def home_delegation(request):
    """Delegación de su funcionario, o None si no tiene funcionario."""
    officer = request_officer(request)
    if officer is None or officer.delegation_id is None:
        return None
    return officer.delegation


def authorized_delegations(request):
    """Delegaciones entre las que la persona puede elegir en la franja de arriba, en el orden de sus códigos.

    Quien ve todas, las ve todas (las que no están archivadas). El resto, la de su funcionario más las que se le
    agregaron en Control de usuarios (tabla Usuario_Rol_Delegacion, ver accounts/delegations.py).
    """
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
    """True si hay algo que elegir: más de una delegación autorizada, o «Todas» además de una."""
    authorized = authorized_delegations(request)
    return len(authorized) > 1 or (is_global_user(request) and len(authorized) >= 1)


def active_delegation(request):
    """Delegación en la que trabaja la persona ahora (la del selector o, si no eligió, la suya); None si ve todas.

    Solo quien tiene autorizadas todas las delegaciones puede quedar en None. Para el resto siempre hay una: la de
    su funcionario o, si no tiene funcionario, la primera que se le agregó. Lanza PermissionDenied si no tiene
    ninguna (el mismo mensaje que usa el Admin).

    Lo guardado en la sesión se revisa cada vez contra lo que hoy está autorizado: si a la persona le quitaron la
    delegación (o se archivó) mientras tenía la sesión abierta, vuelve a la suya sin que haga nada.
    """
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
    """Delegación en la que la persona actúa: donde puede cambiar registros y la que ve fija en los formularios.

    Es la delegación activa. Quien ve todas y no eligió una (Coordinación, el superusuario) conserva la regla de
    siempre: la de su funcionario, y None para el superusuario. Lanza PermissionDenied si no tiene delegación
    (la misma regla y el mismo mensaje que usa el Admin).
    """
    value = getattr(request, "_sgr_delegation", _MISSING)
    if value is _MISSING:
        chosen = active_delegation(request)
        value = chosen if chosen is not None else get_user_delegation(request)
        request._sgr_delegation = value
    return value


def default_delegation(request):
    """Delegación con la que parte algo nuevo: en la que trabaja la persona o, si ve todas y no eligió una, la de su
    funcionario. None si no hay ninguna (el superusuario sin funcionario que ve todas)."""
    delegation = request_delegation(request)
    return delegation if delegation is not None else home_delegation(request)


def delegation_choice(request, raw):
    """Lo que se pidió en el selector: (True, delegación) si está autorizado, (True, None) para «todas» si puede verlas
    todas, y (False, None) en cualquier otro caso, incluso si alguien envía un id a mano."""
    text = str(raw or "").strip()
    if text == ALL_DELEGATIONS:
        return (True, None) if is_global_user(request) else (False, None)
    if re.fullmatch(r"[0-9]{1,18}", text):
        for delegation in authorized_delegations(request):
            if delegation.pk == int(text):
                return True, delegation
    return False, None


def remember_delegation(request, delegation):
    """Guarda en la sesión la delegación elegida (None = todas) y olvida lo que este request ya había calculado."""
    request.session[SESSION_DELEGATION] = delegation.pk if delegation is not None else ALL_DELEGATIONS
    for name in ("_sgr_active", "_sgr_delegation"):
        if hasattr(request, name):
            delattr(request, name)


def delegation_id_of(obj, lookup):
    """Id de la delegación de un objeto según un lookup como "activity__delegation".

    Recorre los pasos intermedios y en el último lee solo el id, para no cargar
    la delegación completa por cada fila de un listado.
    """
    *steps, last = lookup.split("__")
    value = obj
    for step in steps:
        value = getattr(value, step, None)
        if value is None:
            return None
    return getattr(value, f"{last}_id", None)
