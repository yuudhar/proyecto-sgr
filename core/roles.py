from django.db.models import Q

SUPERUSER_ROLE = "Super Usuario"

GLOBAL_ROLE = "Coordinación"

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
    icon, description = ROLES.get(name, ("bi-person", ""))
    return {"label": name, "icon": icon, "description": description}


def sort_key(name):
    names = list(ROLES)
    return (names.index(name), name) if name in names else (len(names), name)


SYSTEM_GROUPS = tuple(name for name in ROLES if name != SUPERUSER_ROLE)

ACTIONS = (
    ("view", "Ver"),
    ("add", "Crear"),
    ("change", "Editar"),
    ("delete", "Eliminar"),
)

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
    from django.contrib.auth.models import Permission

    condition = Q()
    for _section, modules in PERMISSION_MODULES:
        for _label, key in modules:
            app_label, model = key.split(".")
            codenames = [f"{prefix}_{model}" for prefix, _text in ACTIONS]
            condition |= Q(content_type__app_label=app_label, content_type__model=model, codename__in=codenames)
    return Permission.objects.filter(condition).select_related("content_type")


def permission_key(permission):
    action = permission.codename.split("_", 1)[0]
    return f"{permission.content_type.app_label}.{permission.content_type.model}", action


def permission_text(permission):
    key, action = permission_key(permission)
    return f"{ACTION_LABELS.get(action, action)} · {MODULE_LABELS.get(key, key)}"
