from django.apps import AppConfig


class PlanningConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "planning"
    verbose_name = "Planificación"

    def ready(self):
        from . import signals  # noqa: F401  (conecta el recálculo automático de indicadores)
