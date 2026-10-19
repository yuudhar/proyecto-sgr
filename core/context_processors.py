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
    account = getattr(user, "profile", None)
    if account is None or not account.photo:
        return ""
    return f"{reverse('core:profile_photo', args=[user.pk])}?v={int(account.updated_at.timestamp())}"


def delegation_scope(request):
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
        "all": everything,
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
            "me_delegation": home_delegation(request),
            "me_roles": roles,
            "me_scope": delegation_scope(request),
        }
    )
    return context
