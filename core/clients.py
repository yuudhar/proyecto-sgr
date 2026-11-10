"""Perfil Cliente (usuario final): qué es, qué datos son suyos y por dónde puede navegar.

Un Cliente es un beneficiario con cuenta. Ve solo su propio perfil y sus propias atenciones. El filtro se
hace siempre en el servidor, con el usuario autenticado: nunca con un identificador que mande el navegador.
"""

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect
from django.urls import Resolver404, resolve, reverse

from core.roles import CLIENT_ROLE

# Direcciones (nombre dentro de «core») a las que puede entrar un Cliente. Todo lo demás se rechaza.
ALLOWED_URL_NAMES = frozenset(
    {
        "login",
        "logout",
        "profile",
        "profile_photo",
        "portal_home",
        "portal_activities",
        "portal_activity",
    }
)

ALLOWED_PATHS = frozenset({"/accounts/login/", "/accounts/logout/"})

_MISSING = object()


def is_client(user):
    """True si la cuenta es del perfil Cliente. Un superusuario nunca lo es."""
    if user is None or not getattr(user, "is_authenticated", False) or user.is_superuser:
        return False
    value = getattr(user, "_sgr_is_client", _MISSING)
    if value is _MISSING:
        value = user.groups.filter(name=CLIENT_ROLE).exists()
        user._sgr_is_client = value
    return value


def client_beneficiary(user):
    """El beneficiario vinculado a la cuenta, o None si no tiene (o está archivado)."""
    if not is_client(user):
        return None
    account = getattr(user, "profile", None)
    beneficiary = account.beneficiary if account is not None and account.beneficiary_id else None
    if beneficiary is None or beneficiary.deleted_at is not None:
        return None
    return beneficiary


def own_activities(user):
    """Las atenciones del Cliente autenticado. Sin beneficiario vinculado no hay ninguna."""
    from operations.models import Activity

    beneficiary = client_beneficiary(user)
    if beneficiary is None:
        return Activity.objects.none()
    return Activity.objects.filter(beneficiary=beneficiary, deleted_at__isnull=True)


def portal_url():
    return reverse("core:portal_home")


class ClientPortalMiddleware:
    """Encierra al Cliente en su portal: su perfil, su foto y sus atenciones.

    Va después de la autenticación. Cualquier otra dirección (listados, fichas, exportaciones, administración,
    tablero) responde 403 sin mostrar contenido, y queda en la auditoría. El dashboard lo lleva a su portal.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if is_client(user):
            blocked = self.check(request, user)
            if blocked is not None:
                return blocked
        return self.get_response(request)

    def check(self, request, user):
        path = request.path_info
        if path.startswith("/" + settings.STATIC_URL.lstrip("/")) or path in ALLOWED_PATHS:
            return None
        try:
            match = resolve(path)
        except Resolver404:
            return None
        if match.namespace == "core" and match.url_name in ALLOWED_URL_NAMES:
            return None
        if match.namespace == "accounts":
            return None
        if match.url_name == "salud":
            return None
        if request.method in ("GET", "HEAD") and match.namespace == "core" and match.url_name == "dashboard":
            return HttpResponseRedirect(portal_url())
        self.reject(user, path)
        raise PermissionDenied("Tu perfil solo puede ver tu portal, tus datos y tus atenciones.")

    @staticmethod
    def reject(user, path):
        from core.audit import log_event

        log_event(user, "Acceso de cliente rechazado", user, new=f"Dirección pedida: {path[:100]}")
