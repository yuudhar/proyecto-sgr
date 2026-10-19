"""Menú lateral: solo muestra lo que el usuario tiene permiso de abrir.

Arriba van "Atención" y "Dashboard"; después, los grupos (Operación, Resultados y
Administración). Cada entrada apunta a un mantenedor (por su slug en core/registry.py)
o a una pantalla especial (por el nombre de su ruta). Las entradas sin permiso no se
dibujan y los grupos que quedan vacíos tampoco.
"""

from dataclasses import dataclass, field

from django.urls import reverse

from core.crud import registry


@dataclass
class MenuItem:
    label: str
    url: str
    icon: str
    description: str = ""
    active: bool = False


@dataclass
class MenuGroup:
    label: str
    icon: str
    key: str = ""  # sirve para el id del bloque que se abre y se cierra
    sections: list = field(default_factory=list)  # lista de (título de sección, [MenuItem])
    active: bool = False  # contiene la pantalla actual
    start_open: bool = True  # se muestra abierto al entrar, aunque no tenga la pantalla actual

    @property
    def items(self):
        return [item for _, items in self.sections for item in items]

    @property
    def open(self):
        return self.active or self.start_open


def crud_entry(slug, label=None):
    """Entrada de un mantenedor; se muestra si el usuario puede ver ese modelo."""

    def build(user):
        crud = registry.get(slug)
        if not crud.has_perm(user, "view"):
            return None
        return MenuItem(label or crud.list_title, crud.url("list"), crud.icon, crud.description)

    return build


def page_entry(route, label, icon, perm):
    """Entrada de una pantalla especial; se muestra si el usuario tiene el permiso."""

    def build(user):
        if not user.has_perm(perm):
            return None
        return MenuItem(label, reverse(f"core:{route}"), icon)

    return build


def admin_site_entry(user):
    if not user.is_staff:
        return None
    return MenuItem(
        "Panel de administración",
        reverse("admin:index"),
        "bi-gear-wide-connected",
        "Usuarios, grupos y permisos, y el resto de los datos en el Django Admin.",
    )


def dashboard_entry(user):
    return MenuItem("Dashboard", reverse("core:dashboard"), "bi-speedometer2")


def hub_item():
    """Portada de Administración, que reúne todo lo que el usuario puede administrar."""
    return MenuItem(
        "Resumen",
        reverse("core:administration"),
        "bi-grid-1x2",
        "Todo lo que puedes administrar, en una sola pantalla.",
    )


# Entradas de arriba, sin grupo.
TOP = [
    page_entry("atencion", "Atención", "bi-headset", "operations.view_activity"),
    dashboard_entry,
]

# (clave, nombre del grupo, ícono, abierto al entrar, [(título de sección, [entradas])])
MENU = [
    (
        "operacion",
        "Operación",
        "bi-clipboard-check",
        True,
        [
            (
                "",
                [
                    crud_entry("gestiones"),
                    crud_entry("agenda", "Agenda colectiva"),
                    crud_entry("evidencias"),
                    page_entry("validate_list", "Validar evidencias", "bi-patch-check", "evidence.add_validation"),
                ],
            )
        ],
    ),
    (
        "resultados",
        "Resultados",
        "bi-graph-up-arrow",
        True,
        [
            (
                "",
                [
                    page_entry("delegation_board", "Tablero de delegación", "bi-columns-gap", "planning.view_indicator"),
                    page_entry("reports", "Informes", "bi-file-earmark-bar-graph", "planning.view_indicator"),
                    crud_entry("indicadores"),
                ],
            )
        ],
    ),
    (
        "administracion",
        "Administración",
        "bi-sliders",
        False,
        [
            (
                "Organización",
                [
                    crud_entry("delegaciones"),
                    crud_entry("funcionarios"),
                    crud_entry("territorios"),
                    crud_entry("cargos"),
                    crud_entry("items-de-cargo"),
                ],
            ),
            (
                "Planificación",
                [
                    crud_entry("periodos"),
                    crud_entry("metas"),
                    crud_entry("ajustes"),
                ],
            ),
            (
                "Catálogos",
                [
                    crud_entry("servicios"),
                    crud_entry("items"),
                    crud_entry("tipos-de-atencion"),
                    crud_entry("sub-atenciones"),
                    crud_entry("tipos-de-gestion"),
                    crud_entry("beneficiarios"),
                ],
            ),
            (
                "Sistema",
                [
                    crud_entry("usuarios", "Control de usuarios"),
                    crud_entry("roles"),
                    crud_entry("auditoria"),
                    admin_site_entry,
                ],
            ),
        ],
    ),
]


def visible_entries(user):
    """Las entradas de arriba y los grupos del menú, solo con lo que el usuario puede abrir."""
    top = [item for item in (build(user) for build in TOP) if item]
    groups = []
    for key, label, icon, start_open, sections in MENU:
        group = MenuGroup(label=label, icon=icon, key=key, start_open=start_open)
        for title, builders in sections:
            items = [item for item in (build(user) for build in builders) if item]
            if items:
                group.sections.append((title, items))
        if group.sections:
            if key == "administracion":
                group.sections.insert(0, ("", [hub_item()]))
            groups.append(group)
    return top, groups


def build_menu(request):
    """Menú del usuario con la entrada actual marcada (la de dirección más específica)."""
    top, groups = visible_entries(request.user)
    path = request.path

    current = None
    candidates = [(item, None) for item in top]
    for group in groups:
        candidates.extend((item, group) for item in group.items)
    for item, group in candidates:
        matches = path.startswith(item.url)
        if matches and (current is None or len(item.url) > len(current[0].url)):
            current = (item, group)

    if current is not None:
        current[0].active = True
        if current[1] is not None:
            current[1].active = True
    return top, groups
