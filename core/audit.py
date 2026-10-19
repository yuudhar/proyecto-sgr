from core import ui
from core.models import AuditLog

IGNORED_FIELDS = {"id", "created_at", "updated_at", "deleted_at", "password", "last_login"}

MAX_VALUE_LENGTH = 120


def log_event(user, event, obj, previous="", new=""):
    return AuditLog.objects.create(
        event=event,
        affected_entity=obj.__class__.__name__,
        record_id=obj.pk,
        previous_value=previous or None,
        new_value=new or None,
        user=user,
    )


def log_export(user, source, rows, summary=""):
    AuditLog.objects.create(
        event="Listado exportado a Excel",
        affected_entity=source if isinstance(source, str) else source.__name__,
        record_id=0,
        new_value=f"{rows} {'fila' if rows == 1 else 'filas'}. {summary}"[: MAX_VALUE_LENGTH * 4],
        user=user,
    )


def describe(field, value):
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
