"""Publicación de eventos en tiempo real (Clase 11).

La vista valida y guarda; este módulo solo publica en la capa de canales. El Consumer
distribuye y JavaScript presenta. Así cada pieza tiene una sola responsabilidad.
Los avisos no llevan datos: cada navegador vuelve a pedir su pantalla por HTTP.
"""

import logging
from types import SimpleNamespace

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.core.exceptions import PermissionDenied
from django.db import transaction

from core.access import active_delegation, authorized_delegations, delegation_id_of, is_global_user

logger = logging.getLogger(__name__)

ALL = "all"


def crud_group(slug, delegation_id):
    return f"crud_{slug}_d{delegation_id}"


def live_group(delegation_id):
    """Grupo de avisos de cambios de datos (para el dashboard y otras pantallas de resumen)."""
    return "live_all" if delegation_id == ALL else f"live_d{delegation_id}"


def socket_request(scope):
    """Un «request» mínimo con el usuario y la sesión de la conexión WebSocket.

    Sirve para reutilizar las mismas reglas de delegación activa que usan las páginas HTTP.
    """
    return SimpleNamespace(user=scope["user"], session=scope["session"])


def crud_groups_for(scope, crud):
    """Grupos a los que puede suscribirse esta conexión para un mantenedor, según su delegación."""
    groups = [crud_group(crud.slug, ALL)]
    if crud.delegation_lookup:
        request = socket_request(scope)
        try:
            active = active_delegation(request)
        except PermissionDenied:
            return []
        if active is not None:
            groups.append(crud_group(crud.slug, active.pk))
        elif is_global_user(request):
            groups.extend(crud_group(crud.slug, delegation.pk) for delegation in authorized_delegations(request))
    return groups


def crud_delegation_of(crud, obj):
    if not crud.delegation_lookup or obj is None:
        return ALL
    found = delegation_id_of(obj, crud.delegation_lookup)
    return ALL if found is None else found


def publish_crud_changed(crud, *delegation_ids):
    layer = get_channel_layer()
    if layer is None:
        return
    for delegation_id in dict.fromkeys(delegation_ids):
        try:
            async_to_sync(layer.group_send)(
                crud_group(crud.slug, delegation_id),
                {"type": "crud_event", "payload": {"type": "crud_changed", "slug": crud.slug}},
            )
        except Exception:
            logger.exception("No se pudo avisar el cambio de %s por WebSocket", crud.slug)


def notify_crud_change(crud, obj, before=None):
    """Avisa un cambio solo cuando la transacción ya se confirmó (transaction.on_commit).

    Si hay un rollback el aviso se descarta; si no hay transacción, se publica de inmediato.
    El grupo se calcula ahora, antes de que el registro pueda borrarse o cambiar de delegación.
    """
    targets = [crud_delegation_of(crud, obj)]
    if before is not None:
        targets.append(crud_delegation_of(crud, before))
    transaction.on_commit(lambda: publish_crud_changed(crud, *targets))


def live_groups_for(scope):
    """Grupos de «cambió algo» que escucha esta conexión, según su delegación (igual que los listados)."""
    groups = [live_group(ALL)]
    request = socket_request(scope)
    try:
        active = active_delegation(request)
    except PermissionDenied:
        return groups
    if active is not None:
        groups.append(live_group(active.pk))
    elif is_global_user(request):
        groups.extend(live_group(delegation.pk) for delegation in authorized_delegations(request))
    return groups


def publish_live_changed(label, *delegation_ids):
    """Avisa que cambió un dato. No lleva datos: cada navegador vuelve a pedir su pantalla por HTTP."""
    layer = get_channel_layer()
    if layer is None:
        return
    for delegation_id in dict.fromkeys(delegation_ids):
        try:
            async_to_sync(layer.group_send)(
                live_group(delegation_id),
                {"type": "live_event", "payload": {"type": "live_changed", "model": label}},
            )
        except Exception:
            logger.exception("No se pudo avisar el cambio de %s por WebSocket", label)
