"""Datos que todas las plantillas necesitan: menú, usuario, delegación y perfiles."""

from django.core.exceptions import PermissionDenied
from django.urls import reverse

from core.access import (
    ALL_DELEGATIONS,
    active_delegation,
    authorized_delegations,
    can_choose_delegation,
    home_delegation,
    is_global_user,
    request_officer,
    request_roles,
)
from core.colors import DEFAULT_COLOR, palette
from core.crud import registry
from core.menus import build_menu
from core.roles import role_info

ALL_LABEL = "Todas las delegaciones"
NO_DELEGATION_LABEL = "Sin delegación asignada"


def photo_url(user):
    """Dirección de la foto de perfil, o vacío si la persona no subió una. El número de versión evita ver la foto vieja."""
    account = getattr(user, "profile", None)
    if account is None or not account.photo:
        return ""
    return f"{reverse('core:profile_photo', args=[user.pk])}?v={int(account.updated_at.timestamp())}"


def delegation_scope(request):
    """La delegación en la que trabaja la persona, lista para la franja de arriba y la barra lateral.

    Devuelve un diccionario con el código y el nombre de la delegación activa (o «Todas las delegaciones»), si la
    persona puede elegir otra (A2: el selector muestra solo las autorizadas), las opciones del selector y los colores.
    Nunca lanza PermissionDenied: las pantallas de error también la usan y una persona sin delegación asignada
    solo ve «Sin delegación asignada».
    """
    code_of = registry.get("delegaciones").code_of
    everything = is_global_user(request)
    try:
        active = active_delegation(request)
        assigned = True
    except PermissionDenied:
        active, assigned = None, False
    options = []
    selected = ""
    if assigned:
        selected = str(active.pk) if active is not None else ALL_DELEGATIONS
        authorized = authorized_delegations(request)
        if everything:
            options.append({"value": ALL_DELEGATIONS, "label": ALL_LABEL, "selected": active is None})
        for delegation in authorized:
            options.append(
                {
                    "value": str(delegation.pk),
                    "label": f"{code_of(delegation)} · {delegation.name}",
                    "selected": active is not None and delegation.pk == active.pk,
                }
            )
    choose = assigned and can_choose_delegation(request)

    if not assigned and not everything:
        name = NO_DELEGATION_LABEL
    else:
        name = active.name if active is not None else ALL_LABEL

    if everything and active is not None:
        note = "Con acceso a todas las delegaciones"
    elif choose:
        note = f"Autorizado en {len(options)} delegaciones"
    else:
        note = ""

    return {
        "code": code_of(active) if active is not None else "",
        "name": name,
        "all": everything,  # tiene autorizadas todas las delegaciones (aunque mire solo una)
        "viewing_all": assigned and active is None,
        "assigned": assigned,
        "choose": choose,
        "selected": selected,
        "options": options,
        "note": note,
        **palette(active.color if active is not None else DEFAULT_COLOR),
    }


def portal(request):
    context = {
        "brand_name": "SGR",
        "brand_subtitle": "Sistema de Gestión de Resultados",
        "institution": "Ilustre Municipalidad de La Serena",
    }
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return context

    top, groups = build_menu(request)
    officer = request_officer(request)
    roles = [role_info(name) for name in request_roles(request)]
    context.update(
        {
            "menu_top": top,
            "menu_groups": groups,
            "me": user,
            "me_name": user.get_full_name() or user.get_username(),
            "me_officer": officer,
            "me_photo_url": photo_url(user),
            # La delegación de su funcionario (la «propia»): puede no ser en la que trabaja ahora (me_scope).
            "me_delegation": home_delegation(request),
            "me_roles": roles,
            # Delegación en la que trabaja la persona: se muestra en la franja de arriba (código y nombre, con el
            # selector si tiene más de una autorizada) y en la barra lateral (nombre y colores). El código (DEL01)
            # sale del id, igual que en el mantenedor de Delegaciones.
            "me_scope": delegation_scope(request),
        }
    )
    return context
