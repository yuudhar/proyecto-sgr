"""Foto de perfil de otra persona: la cambia o la quita quien edita a ese usuario (por ejemplo, el administrador).

La propia persona sigue cambiando la suya desde «Mi perfil» (core/views.py). Aquí el archivo anterior se borra
recién cuando la transacción se confirma, para no perder la foto si el guardado se deshace.
"""

from django.db import transaction
from django.urls import reverse

from accounts.models import UserProfile
from core.audit import log_event


def photo_url_of(user):
    """Dirección de la foto de un usuario, o texto vacío si no tiene."""
    account = UserProfile.objects.filter(user=user).first()
    if account is None or not account.photo:
        return ""
    return f"{reverse('core:profile_photo', args=[user.pk])}?v={int(account.updated_at.timestamp())}"


def _delete_later(storage, name):
    if name:
        transaction.on_commit(lambda: storage.delete(name))


def change_photo(actor, user, uploaded):
    account = UserProfile.objects.get_or_create(user=user)[0]
    old = account.photo.name if account.photo else ""
    account.photo = uploaded
    account.save(update_fields=["photo", "updated_at"])
    if old and old != account.photo.name:
        _delete_later(account.photo.storage, old)
    log_event(actor, "Foto de perfil cambiada", user)


def remove_photo(actor, user):
    """Quita la foto. Devuelve False si la persona no tenía una."""
    account = UserProfile.objects.filter(user=user).first()
    if account is None or not account.photo:
        return False
    old = account.photo.name
    storage = account.photo.storage
    account.photo = None
    account.save(update_fields=["photo", "updated_at"])
    _delete_later(storage, old)
    log_event(actor, "Foto de perfil quitada", user)
    return True
