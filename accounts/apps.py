from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"
    verbose_name = "Cuentas y perfiles"

    def ready(self):
        from . import signals  # noqa: F401  (conecta la creación de la ficha de cada rol)
