from django.conf import settings
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
from core.clients import client_beneficiary, is_client
from core.colors import DEFAULT_COLOR, palette
from core.crud import registry
from core.menus import build_menu, client_menu
from core.roles import CLIENT_ROLE, role_info

def _read_text(name):
    try:
        return (settings.BASE_DIR / name).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


# Cambia en cada entrega (VERSION) y en cada despliegue (COMMIT): el navegador no reutiliza CSS ni JS viejos.
ASSET_VERSION = "-".join(filter(None, (_read_text("VERSION"), _read_text("COMMIT")))) or "dev"


def assets(request):
    return {"asset_version": ASSET_VERSION}


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


ORDINAL_TRIMESTRE = {1: "1.er", 2: "2.º", 3: "3.er", 4: "4.º"}


def quarter_scope(request):
    """El trimestre en que está hoy la persona: el de su delegación activa (o el general, si ve todas)."""
    from core import entry_rules
    from planning import periods

    try:
        delegation = active_delegation(request)
    except PermissionDenied:
        delegation = None
    today = entry_rules.portal_today()
    period = periods.containing(today, delegation)
    if period is None:
        return {"label": "Sin trimestre vigente", "range": "", "title": f"Hoy ({today:%d/%m/%Y}) no cae en ningún trimestre creado."}
    start, end = period.start_date, period.end_date
    if (end - start).days > 100:
        label = f"Período {start.year}" if start.year == end.year else f"Período {start.year}–{end.year}"
    else:
        label = f"{ORDINAL_TRIMESTRE[(start.month - 1) // 3 + 1]} trimestre {start.year}"
    where = f"de la {period.delegation.name}" if period.delegation_id else "general (todas las delegaciones)"
    return {
        "label": label,
        "range": f"{start:%d/%m} al {end:%d/%m/%Y}",
        "title": f"Trimestre {where}: del {start:%d/%m/%Y} al {end:%d/%m/%Y} ({period.get_status_display().lower()}).",
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

    if is_client(user):
        top, groups = client_menu(request)
        return {
            **context,
            "menu_top": top,
            "menu_groups": groups,
            "me": user,
            "me_name": user.get_full_name() or user.get_username(),
            "me_officer": None,
            "me_photo_url": photo_url(user),
            "me_delegation": None,
            "me_roles": [role_info(CLIENT_ROLE)],
            "me_scope": {},
            "is_client": True,
            "home_url": reverse("core:portal_home"),
            "client_beneficiary": client_beneficiary(user),
        }

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
            "me_quarter": quarter_scope(request),
            "is_client": False,
            "home_url": reverse("core:dashboard"),
        }
    )
    return context
