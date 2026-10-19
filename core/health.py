from pathlib import Path

from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET


def _leer(nombre):
    ruta = Path(settings.BASE_DIR) / nombre
    try:
        return ruta.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


@never_cache
@require_GET
def salud(request):
    estado = {"servicio": "ok", "base_de_datos": "ok", "cache": "ok"}
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        estado["base_de_datos"] = "error"
    try:
        cache.set("sgr:salud", "ok", 10)
        if cache.get("sgr:salud") != "ok":
            estado["cache"] = "error"
    except Exception:
        estado["cache"] = "error"
    estado["version"] = _leer("VERSION") or "sin definir"
    estado["commit"] = _leer("COMMIT") or "sin definir"
    estado["entorno"] = "desarrollo" if settings.DEBUG else "producción"
    ok = all(estado[k] == "ok" for k in ("servicio", "base_de_datos", "cache"))
    return JsonResponse(estado, status=200 if ok else 503, json_dumps_params={"ensure_ascii": False})
