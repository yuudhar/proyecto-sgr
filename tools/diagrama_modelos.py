#!/usr/bin/env python3
"""Genera `docs/DIAGRAMA_MODELOS.md`: el diagrama entidad-relación (Mermaid `erDiagram`) de los modelos del proyecto.

Las entidades, los campos y las relaciones salen de `django.apps.apps.get_models()`, así que el diagrama no se
desactualiza a mano. Las multiplicidades se deducen del campo (`null=True` → «cero o uno»; `ForeignKey` → «uno a
muchos»; `OneToOneField` → «uno a uno»; `ManyToManyField` → «muchos a muchos») y después se **revisan a mano**: lo
que la base de datos no puede expresar (reglas entre dos campos, relaciones excluyentes) está en `REVISION_MANUAL`
y aparece en la tabla «Revisión manual» del documento.

Uso (desde la raíz del repositorio, con el entorno virtual activo):

    python tools/diagrama_modelos.py              # escribe docs/DIAGRAMA_MODELOS.md
    python tools/diagrama_modelos.py --verificar  # no escribe; falla si el documento está desactualizado
"""
import argparse
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DESTINO = RAIZ / "docs" / "DIAGRAMA_MODELOS.md"

APLICACIONES = ("organization", "operations", "evidence", "planning", "accounts", "core")
# Modelos de Django que sí aparecen porque los modelos propios apuntan a ellos.
MODELOS_DJANGO = ("auth.User", "auth.Group")
# Campos que se omiten del diagrama para no repetirlos en las 25 entidades (existen en todos los modelos propios).
CAMPOS_COMUNES = ("created_at", "updated_at")
CAMPOS_OCULTOS = ("password",)  # datos sensibles de User: no hacen falta para entender el modelo

TIPOS = {
    "AutoField": "int",
    "BigAutoField": "int",
    "CharField": "string",
    "TextField": "text",
    "BooleanField": "bool",
    "DateField": "date",
    "DateTimeField": "datetime",
    "DecimalField": "decimal",
    "PositiveIntegerField": "int",
    "PositiveSmallIntegerField": "int",
    "IntegerField": "int",
    "FileField": "file",
    "ImageField": "file",
    "EmailField": "string",
}

# Multiplicidad (notación Mermaid) por tipo de relación: (lado padre)--(lado hijo), padre = modelo apuntado.
MULTIPLICIDAD = {
    ("fk", False): "||--o{",  # cada hijo tiene exactamente un padre; un padre tiene cero o muchos hijos
    ("fk", True): "|o--o{",  # el padre es opcional
    ("o2o", False): "||--o|",  # cada hijo tiene exactamente un padre; el padre tiene cero o un hijo
    ("o2o", True): "|o--o|",
    ("m2m", False): "}o--o{",
    ("m2m", True): "}o--o{",
}

# Revisión manual: «Modelo.campo» -> comentario sobre lo que el diagrama no puede decir por sí solo.
REVISION_MANUAL = {
    "Activity.beneficiary": "Una atención es de una persona (beneficiario) o de una organización: al menos una de las dos.",
    "Activity.organization": "Ver Activity.beneficiary: persona u organización, no es obligatorio tener ambas.",
    "Activity.delegation": "Debe ser la misma delegación del funcionario autor (validación del modelo); se guarda para filtrar rápido.",
    "Activity.commitment": "Una atención puede originar un compromiso de la agenda; cada compromiso nace de, como máximo, una atención.",
    "Followup.activity": "Hasta tres gestiones por atención, numeradas 1, 2 y 3 (restricción única atención + número).",
    "Commitment.territory": "El territorio debe pertenecer a la misma delegación del compromiso (validación del modelo).",
    "Evidence.author_officer": "Es quien sube el archivo; normalmente el mismo funcionario que registró la atención.",
    "Validation.evidence": "Una evidencia puede revisarse varias veces; la decisión de cada revisión (aprobada, observada o rechazada) actualiza su estado de revisión.",
    "Validation.reviewer_officer": "Opcional: queda vacío si el revisor ya no existe como funcionario.",
    "Goal.officer": "Una meta es personal (funcionario) o del cargo (position): una u otra, no ambas.",
    "Goal.position": "Ver Goal.officer: meta del cargo, la reciben todos los funcionarios activos de ese cargo.",
    "Indicator.officer": "El indicador se guarda por meta y por funcionario; cada recálculo que cambia el valor agrega uno nuevo.",
    "Feedback.adjustment": "El ajuste (bonificación o penalización) lo genera el sistema al registrar la felicitación o el reclamo.",
    "Feedback.period": "Se deduce de la fecha del registro; un período cerrado ya no admite cambios.",
    "PositionItem.position": "PositionItem es la tabla intermedia (con ponderación y vigencia) entre Position e Item: relación muchos a muchos.",
    "PositionItem.item": "Ver PositionItem.position.",
    "Item.parent_item": "Relación consigo mismo: tipo de atención (padre) y sub-atención (hijo). Solo hay dos niveles.",
    "Territory.delegation": "El nombre del territorio es único dentro de cada delegación (restricción única nombre + delegación).",
    "Officer.delegation": "Define el ámbito (organización A o B) que ve el funcionario y su cuenta.",
    "UserProfile.user": "Cada cuenta tiene un perfil; el perfil enlaza la cuenta con su funcionario o con su beneficiario.",
    "UserProfile.officer": "Cuentas de personal: un funcionario, una cuenta. Vacío en cuentas técnicas y de clientes.",
    "UserProfile.beneficiary": "Solo cuentas del perfil Cliente. Un perfil es de un funcionario o de un beneficiario, nunca de ambos.",
    "UserRoleDelegation.delegation": "Delegaciones adicionales en las que una cuenta ejerce un rol; sin delegación vale para todas.",
    "UserRoleDelegation.user": "Una cuenta puede ejercer el mismo rol en varias delegaciones (restricción única usuario + rol + delegación).",
    "RoleProfile.group": "Ficha del rol (descripción y alcance) para cada grupo de Django.",
    "AuditLog.user": "Quién hizo el cambio; el registro de auditoría no se borra ni se archiva.",
}


def preparar_django():
    sys.path.insert(0, str(RAIZ))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sgr_project.settings")
    import django

    django.setup()
    import core.registry  # noqa: F401  (completa el registro de CRUD; no afecta a los modelos)


def modelos():
    from django.apps import apps

    elegidos = []
    for etiqueta in APLICACIONES:
        elegidos += sorted(apps.get_app_config(etiqueta).get_models(), key=lambda m: m.__name__)
    elegidos += [apps.get_model(nombre) for nombre in MODELOS_DJANGO]
    nombres = [m.__name__ for m in elegidos]
    assert len(nombres) == len(set(nombres)), "Hay dos modelos con el mismo nombre: el diagrama los confundiría."
    return elegidos


def tipo_de(campo):
    if campo.is_relation:
        return "int"
    return TIPOS.get(type(campo).__name__, type(campo).__name__.replace("Field", "").lower())


def entidad(modelo):
    lineas = [f"    {modelo.__name__} {{"]
    for campo in modelo._meta.concrete_fields:
        if campo.name in CAMPOS_COMUNES + CAMPOS_OCULTOS:
            continue
        marcas = []
        if campo.primary_key:
            marcas.append("PK")
        if campo.is_relation:
            marcas.append("FK")
        if campo.unique and not campo.primary_key:
            marcas.append("UK")
        nombre = campo.name + ("_id" if campo.is_relation else "")
        extra = ", ".join(marcas)
        comentario = ' "opcional"' if campo.null and campo.is_relation else ""
        if campo.name == "deleted_at":
            comentario = ' "archivado"'
        lineas.append(f"        {tipo_de(campo)} {nombre}{(' ' + extra) if extra else ''}{comentario}")
    lineas.append("    }")
    return lineas


def relaciones(conjunto):
    filas = []
    for modelo in conjunto:
        for campo in modelo._meta.get_fields():
            if not campo.is_relation or campo.auto_created or not campo.concrete and not campo.many_to_many:
                continue
            destino = campo.related_model
            if destino not in conjunto:
                continue
            if campo.many_to_many:
                tipo = "m2m"
            elif campo.one_to_one:
                tipo = "o2o"
            else:
                tipo = "fk"
            filas.append((destino.__name__, modelo.__name__, campo.name, tipo, bool(campo.null)))
    return sorted(filas)


def generar():
    preparar_django()
    conjunto = modelos()
    lineas = ["erDiagram"]
    for modelo in conjunto:
        lineas += entidad(modelo)
    lineas.append("")
    detalle = []
    for padre, hijo, campo, tipo, opcional in relaciones(conjunto):
        lineas.append(f'    {padre} {MULTIPLICIDAD[(tipo, opcional)]} {hijo} : "{campo}"')
        nota = REVISION_MANUAL.get(f"{hijo}.{campo}", "")
        detalle.append((hijo, campo, padre, tipo, opcional, nota))
    huerfanas = sorted(set(REVISION_MANUAL) - {f"{h}.{c}" for h, c, *_ in detalle})
    assert not huerfanas, f"REVISION_MANUAL menciona relaciones que ya no existen: {huerfanas}"

    lectura = {
        ("fk", False): "muchos → uno (obligatoria)",
        ("fk", True): "muchos → uno (opcional)",
        ("o2o", False): "uno → uno (obligatoria)",
        ("o2o", True): "uno → uno (opcional)",
        ("m2m", False): "muchos ↔ muchos",
        ("m2m", True): "muchos ↔ muchos",
    }
    cuerpo = [
        "# Diagrama de modelos",
        "",
        "Diagrama entidad-relación del proyecto SGR. **Está generado** por `tools/diagrama_modelos.py` a partir de los "
        "modelos que Django tiene registrados (`apps.get_models()`); no se edita a mano. Para regenerarlo:",
        "",
        "```bash",
        "python tools/diagrama_modelos.py            # escribe este documento",
        "python tools/diagrama_modelos.py --verificar  # falla si está desactualizado",
        "```",
        "",
        "GitHub, GitLab y la mayoría de los editores de Markdown dibujan el bloque `mermaid` de abajo. Todas las "
        "entidades propias tienen además `created_at` y `updated_at` (no se dibujan) y `deleted_at`: una fecha en ese "
        "campo significa que el registro está **archivado** (borrado lógico). `User` y `Group` son los modelos de "
        "autenticación de Django, que los modelos propios enlazan.",
        "",
        "Lectura de las líneas: `||` = exactamente uno, `|o` = cero o uno, `o{` = cero o muchos. En cada relación el "
        "modelo de la izquierda es el **apuntado** por la clave foránea, y la etiqueta es el nombre del campo.",
        "",
        "```mermaid",
        *lineas,
        "```",
        "",
        "## Revisión manual de las multiplicidades",
        "",
        "La multiplicidad sale del tipo de campo, pero hay reglas que un diagrama no muestra (relaciones excluyentes, "
        "valores que deben coincidir entre dos campos, límites). Esta tabla recoge las que se revisaron a mano y lo "
        "que aclara cada una; las relaciones que no tienen comentario se leen tal como están dibujadas.",
        "",
        "| Relación (campo) | Apunta a | Multiplicidad | Comentario de la revisión |",
        "| --- | --- | --- | --- |",
    ]
    for hijo, campo, padre, tipo, opcional, nota in detalle:
        cuerpo.append(f"| `{hijo}.{campo}` | `{padre}` | {lectura[(tipo, opcional)]} | {nota or '—'} |")
    cuerpo.append("")
    return "\n".join(cuerpo)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--verificar", action="store_true", help="No escribe: falla si el documento está desactualizado.")
    parser.add_argument("--salida", default=str(DESTINO), help="Archivo de salida (por defecto docs/DIAGRAMA_MODELOS.md).")
    args = parser.parse_args()
    texto = generar()
    salida = Path(args.salida)
    if args.verificar:
        if not salida.exists() or salida.read_text(encoding="utf-8") != texto:
            sys.exit(f"{salida} está desactualizado: ejecuta python tools/diagrama_modelos.py")
        print(f"{salida} está al día.")
        return
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(texto, encoding="utf-8")
    print(f"Escrito {salida} ({len(texto.splitlines())} líneas).")


if __name__ == "__main__":
    main()
