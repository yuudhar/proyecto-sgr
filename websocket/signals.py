"""Avisos de cambio de datos para las pantallas de resumen (dashboard, tablero y validar).

Cada vez que alguien guarda, archiva, restaura o elimina un dato que esas pantallas muestran
(atenciones, gestiones, compromisos, evidencias, validaciones, metas, indicadores, ajustes,
períodos y funcionarios), se publica un aviso al grupo de su delegación. Se usan señales de Django
y no solo los mantenedores, para que también cuenten los cambios que hacen la pantalla de validar,
el cálculo de indicadores o el Django Admin.

El aviso se publica con transaction.on_commit: si la transacción se deshace, no se avisa.
No se detectan los cambios masivos que no pasan por save()/delete() (QuerySet.update y similares).
"""

from django.apps import apps
from django.db import transaction
from django.db.models.signals import post_delete, post_save, pre_save

from core.access import delegation_id_of

from .services import ALL, publish_live_changed

# Modelo → camino hasta su delegación (None = dato general: avisa a todas las delegaciones).
LIVE_MODELS = {
    "operations.Activity": "delegation",
    "operations.Followup": "activity__delegation",
    "operations.Commitment": "delegation",
    "evidence.Evidence": "activity__delegation",
    "evidence.Validation": "evidence__activity__delegation",
    "planning.Goal": "officer__delegation",
    "planning.Indicator": "officer__delegation",
    "planning.Adjustment": "officer__delegation",
    "planning.Period": None,
    "organization.Officer": "delegation",
}

_lookups = {}


def delegation_of(instance, lookup):
    if not lookup:
        return ALL
    found = delegation_id_of(instance, lookup)
    return ALL if found is None else found


def remember_previous_delegation(sender, instance, raw=False, **kwargs):
    """Antes de guardar: si el dato cambia de delegación, también hay que avisar a la anterior."""
    instance._live_previous = None
    lookup = _lookups[sender]
    if raw or not lookup or instance.pk is None:
        return
    instance._live_previous = (
        sender._base_manager.filter(pk=instance.pk).values_list(lookup, flat=True).first()
    )


def announce(sender, instance, targets):
    label = sender._meta.label_lower
    transaction.on_commit(lambda: publish_live_changed(label, *targets))


def data_saved(sender, instance, raw=False, **kwargs):
    if raw:
        return
    targets = [delegation_of(instance, _lookups[sender])]
    previous = getattr(instance, "_live_previous", None)
    if previous is not None:
        targets.append(previous)
    announce(sender, instance, targets)


def data_deleted(sender, instance, **kwargs):
    announce(sender, instance, [delegation_of(instance, _lookups[sender])])


for label, lookup in LIVE_MODELS.items():
    model = apps.get_model(label)
    _lookups[model] = lookup
    pre_save.connect(remember_previous_delegation, sender=model, dispatch_uid=f"live-pre-{label}")
    post_save.connect(data_saved, sender=model, dispatch_uid=f"live-save-{label}")
    post_delete.connect(data_deleted, sender=model, dispatch_uid=f"live-del-{label}")
