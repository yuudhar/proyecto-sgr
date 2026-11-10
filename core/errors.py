"""Páginas de error del portal.

403, 404 y 500 las resuelve Django con ``templates/403.html``, ``404.html`` y ``500.html``. El 400 pasa por aquí para
asegurar dos cosas: que la respuesta siempre salga con código 400 y que nunca lleve el texto de la excepción
(un host no permitido, un cuerpo demasiado grande o un formulario mal armado traen datos técnicos).
"""

import logging

from django.http import HttpResponseBadRequest
from django.views.defaults import bad_request as django_bad_request

logger = logging.getLogger(__name__)

# Respaldo mínimo: solo se usa si la plantilla del portal no se puede dibujar (por ejemplo, con un encabezado Host que
# Django rechazó antes de preparar la sesión). Sigue siendo un 400, sin detalles técnicos.
FALLBACK_PAGE = """<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Solicitud inválida · SGR</title>
  <style>
    body { margin: 0; font-family: Arial, "Liberation Sans", Helvetica, sans-serif; color: #26221f; background: #f3f2ef; }
    main { max-width: 38rem; margin: 4rem auto; padding: 0 1.5rem; text-align: center; }
    h1 { color: #920000; }
    a { color: #920000; font-weight: 600; }
  </style>
</head>
<body>
  <main>
    <h1>No pudimos procesar la solicitud</h1>
    <p>Algo de lo enviado no es válido. Vuelve al inicio e inténtalo de nuevo.</p>
    <p><a href="/">Volver al inicio</a></p>
  </main>
</body>
</html>
"""


def bad_request(request, exception, template_name="400.html"):
    try:
        return django_bad_request(request, exception, template_name=template_name)
    except Exception:
        logger.exception("No se pudo dibujar la pantalla 400; se usa la página mínima")
        return HttpResponseBadRequest(FALLBACK_PAGE)
