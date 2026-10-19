from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone, translation
from django.utils.cache import add_never_cache_headers


class PortalLocaleMiddleware:

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

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        path = request.path_info
        if not path.startswith("/admin/") and not path.startswith(settings.STATIC_URL):
            add_never_cache_headers(response)
        return response
