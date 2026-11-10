"""Recuperación de contraseña por correo, con un enlace firmado de un solo uso.

Se apoya en lo que trae Django en vez de inventar algo propio:

- El enlace lleva un token de ``default_token_generator``. El token depende de la contraseña actual de la cuenta, de
  su último ingreso y de su correo: en cuanto la persona cambia la contraseña, el mismo enlace deja de servir. Y
  caduca solo con ``PASSWORD_RESET_TIMEOUT``.
- La contraseña nueva pasa por los validadores de ``AUTH_PASSWORD_VALIDATORS``.
- Este módulo solo agrega lo del SGR: el tope de envíos por hora, la auditoría y el texto de la duración.
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

SENT_EVENT = "Enlace de recuperación enviado"
RESET_EVENT = "Contraseña restablecida con enlace"


def sent_last_hour(user):
    """Cuántos enlaces se mandaron a esa cuenta en la última hora (según la auditoría)."""
    from core.models import AuditLog

    since = timezone.now() - timedelta(hours=1)
    return AuditLog.objects.filter(user=user, event=SENT_EVENT, date__gte=since).count()


def over_the_limit(user):
    return sent_last_hour(user) >= settings.RECOVERY_MAX_REQUESTS


def describe_duration(seconds):
    """«1 hora», «2 horas», «30 minutos» o «45 segundos», según lo que alcance en unidades enteras."""
    for size, singular, plural in ((3600, "hora", "horas"), (60, "minuto", "minutos")):
        if seconds % size == 0:
            amount = seconds // size
            return f"{amount} {singular if amount == 1 else plural}"
    return f"{seconds} segundos"


def link_duration():
    return describe_duration(settings.PASSWORD_RESET_TIMEOUT)
