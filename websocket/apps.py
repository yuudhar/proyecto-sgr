from django.apps import AppConfig


class WebsocketConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "websocket"
    verbose_name = "Tiempo real"

    def ready(self):
        from . import signals  # noqa: F401  (conecta los avisos de cambio de datos)
