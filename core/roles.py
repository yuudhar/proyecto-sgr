"""Perfiles (roles) del sistema: nombre, ícono y qué puede hacer cada uno.

Los perfiles son los grupos de Django que crea seed_roles; el superusuario no es un
grupo y aparece como "Super Usuario". Los textos resumen lo que dan los permisos de
accounts/management/commands/seed_roles.py.

También define la matriz de permisos del mantenedor de Roles: qué módulos se muestran, con
qué acciones (Ver, Crear, Editar, Eliminar) y cómo se leen esos permisos en la pantalla.
"""

from django.db.models import Q

SUPERUSER_ROLE = "Super Usuario"

# El único perfil del sistema que ve todas las delegaciones. Los demás perfiles (y los que se creen desde la
# pantalla de Roles, salvo que se les dé ese alcance) ven solo la delegación de su funcionario.
GLOBAL_ROLE = "Coordinación"

# nombre -> (ícono de Bootstrap Icons, qué puede hacer)
ROLES = {
    SUPERUSER_ROLE: (
        "bi-shield-lock",
        "Acceso completo: administra usuarios, delegaciones y todos los datos.",
    ),
    "Coordinación": (
        "bi-diagram-3",
        "Define períodos, metas y ajustes, y consulta todas las delegaciones.",
    ),
    "Jefatura": (
        "bi-person-badge",
        "Consulta la gestión de su delegación y actualiza los compromisos.",
    ),
    "Funcionario": (
        "bi-person-workspace",
        "Registra atenciones, gestiones, evidencias y compromisos de su delegación.",
    ),
    "Verificador": (
        "bi-patch-check",
        "Revisa las evidencias de su delegación y registra la validación.",
    ),
    "Consulta": (
        "bi-eye",
        "Solo consulta la información de su delegación.",
    ),
}


def role_info(name):
    """Datos para mostrar un perfil. Un grupo que no está en la lista sale con un ícono genérico."""
    icon, description = ROLES.get(name, ("bi-person", ""))
    return {"label": name, "icon": icon, "description": description}


def sort_key(name):
    """Orden de los perfiles: primero los conocidos, en el orden de la lista; luego el resto."""
    names = list(ROLES)
    return (names.index(name), name) if name in names else (len(names), name)


# Los perfiles que crea seed_roles. Las reglas de acceso usan sus nombres ("Coordinación" ve todas las
# delegaciones), así que un perfil del sistema no se puede renombrar ni eliminar.
SYSTEM_GROUPS = tuple(name for name in ROLES if name != SUPERUSER_ROLE)

# Acciones de la matriz de permisos: (prefijo del permiso de Django, texto de la columna).
ACTIONS = (
    ("view", "Ver"),
    ("add", "Crear"),
    ("change", "Editar"),
    ("delete", "Eliminar"),
)

# Módulos de la matriz, agrupados como el menú: (título de la sección, [(nombre del módulo, "app.modelo")]).
PERMISSION_MODULES = (
    (
        "Operación",
        (
            ("Actividades y atenciones", "operations.activity"),
            ("Gestiones de atención", "operations.followup"),
            ("Agenda colectiva", "operations.commitment"),
            ("Evidencias", "evidence.evidence"),
            ("Validaciones", "evidence.validation"),
        ),
    ),
    (
        "Resultados y planificación",
        (
            ("Períodos", "planning.period"),
            ("Metas", "planning.goal"),
            ("Indicadores", "planning.indicator"),
            ("Ajustes", "planning.adjustment"),
        ),
    ),
    (
        "Organización",
        (
            ("Delegaciones", "organization.delegation"),
            ("Funcionarios", "organization.officer"),
            ("Territorios", "organization.territory"),
            ("Cargos", "organization.position"),
            ("Ítems de cargo", "organization.positionitem"),
        ),
    ),
    (
        "Catálogos",
        (
            ("Ítems, tipos y sub atenciones", "organization.item"),
            ("Servicios", "organization.service"),
            ("Tipos de gestión", "operations.managementtype"),
            ("Beneficiarios", "organization.beneficiary"),
        ),
    ),
    (
        "Sistema",
        (
            ("Usuarios", "auth.user"),
            ("Roles y permisos", "auth.group"),
            ("Auditoría", "core.auditlog"),
        ),
    ),
)

ACTION_LABELS = dict(ACTIONS)
MODULE_LABELS = {key: label for _section, modules in PERMISSION_MODULES for label, key in modules}


def managed_permissions():
    """Los permisos que muestra la matriz: cada acción de cada módulo que exista en la base de datos.

    Los demás permisos que pudiera tener un perfil (de una app que se agregue después, por ejemplo) no
    se muestran, pero tampoco se pierden al guardar el perfil (ver RoleForm en core/forms.py).
    """
    from django.contrib.auth.models import Permission

    condition = Q()
    for _section, modules in PERMISSION_MODULES:
        for _label, key in modules:
            app_label, model = key.split(".")
            codenames = [f"{prefix}_{model}" for prefix, _text in ACTIONS]
            condition |= Q(content_type__app_label=app_label, content_type__model=model, codename__in=codenames)
    return Permission.objects.filter(condition).select_related("content_type")


def permission_key(permission):
    """("app.modelo", "acción") de un permiso, por ejemplo ("organization.item", "view")."""
    action = permission.codename.split("_", 1)[0]
    return f"{permission.content_type.app_label}.{permission.content_type.model}", action


def permission_text(permission):
    """El permiso como se lee en pantalla: "Ver Períodos", "Eliminar Ítems, tipos y sub atenciones"."""
    key, action = permission_key(permission)
    return f"{ACTION_LABELS.get(action, action)} · {MODULE_LABELS.get(key, key)}"
