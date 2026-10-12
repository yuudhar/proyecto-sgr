"""Middleware de las pantallas web."""

from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone, translation
from django.utils.cache import add_never_cache_headers


class PortalLocaleMiddleware:
    """Deja las pantallas web en español y con la hora de Chile.

    Solo actúa fuera de /admin/: el Django Admin sigue con el idioma y la
    zona horaria de settings.py.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path_info.startswith("/admin/"):
            return self.get_response(request)
        with translation.override(settings.PORTAL_LANGUAGE), timezone.override(
            ZoneInfo(settings.PORTAL_TIME_ZONE)
        ):
            return self.get_response(request)


class PortalNoCacheMiddleware:
    """Pide al navegador que no guarde las pantallas web.

    Muestran datos de la sesión iniciada: así, después de cerrar sesión, el botón
    «Atrás» no vuelve a mostrar una pantalla con datos. No toca /admin/ (que ya lo
    hace por su cuenta) ni los archivos estáticos.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        path = request.path_info
        if not path.startswith("/admin/") and not path.startswith(settings.STATIC_URL):
            add_never_cache_headers(response)
        return response
