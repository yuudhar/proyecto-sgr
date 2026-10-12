"""Registro de auditoría de las acciones que se hacen desde las pantallas web."""

from core import ui
from core.models import AuditLog

# Campos que se llenan solos o que tienen su propio evento (archivar, restaurar).
# La contraseña de un usuario nunca se copia a la auditoría, ni siquiera cifrada.
IGNORED_FIELDS = {"id", "created_at", "updated_at", "deleted_at", "password", "last_login"}

MAX_VALUE_LENGTH = 120


def log_event(user, event, obj, previous="", new=""):
    """Guarda un evento sobre un registro: quién, qué pasó y cómo quedó.

    affected_entity lleva el nombre de la clase del modelo ("Activity", "Evidence").
    Devuelve el registro de auditoría creado (su id sirve para reconocer un evento más adelante).
    """
    return AuditLog.objects.create(
        event=event,
        affected_entity=obj.__class__.__name__,
        record_id=obj.pk,
        previous_value=previous or None,
        new_value=new or None,
        user=user,
    )


def log_export(user, source, rows, summary=""):
    """Deja anotado que alguien descargó un listado: de qué, cuántas filas y con qué filtros.

    source es el modelo del listado (o un nombre, como "Informe"). No hay un registro
    puntual, así que el número de registro queda en 0.
    """
    AuditLog.objects.create(
        event="Listado exportado a Excel",
        affected_entity=source if isinstance(source, str) else source.__name__,
        record_id=0,
        new_value=f"{rows} {'fila' if rows == 1 else 'filas'}. {summary}"[: MAX_VALUE_LENGTH * 4],
        user=user,
    )


def describe(field, value):
    """Texto de un valor guardado tal como se lee en pantalla ("Pendiente", "Delegación Norte")."""
    if value is None or value == "":
        return "(vacío)"
    if field.is_relation:
        related = field.related_model._default_manager.filter(pk=value).first()
        return str(related) if related is not None else str(value)
    if field.choices:
        return str(dict(field.flatchoices).get(value, value))
    if isinstance(value, bool):
        return "sí" if value else "no"
    text = str(value)
    if len(text) > MAX_VALUE_LENGTH:
        text = text[: MAX_VALUE_LENGTH - 3] + "..."
    return text


def changed_fields(before, after):
    """Compara dos copias del mismo registro y lista lo que cambió.

    Devuelve tuplas (nombre del campo, valor anterior, valor nuevo), con los valores
    ya escritos como texto.
    """
    changes = []
    for field in after._meta.concrete_fields:
        if field.name in IGNORED_FIELDS:
            continue
        old = field.value_from_object(before)
        new = field.value_from_object(after)
        if old != new:
            label = ui.initial_capital(field.verbose_name)
            changes.append((label, describe(field, old), describe(field, new)))
    return changes
