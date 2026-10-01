
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from core.models import BaseModel
from organization.models import Officer


class UserProfile(BaseModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Activo"
        INACTIVE = "inactive", "Inactivo"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
        verbose_name="usuario",
    )
    officer = models.OneToOneField(
        Officer,
        on_delete=models.PROTECT,
        related_name="user_profile",
        null=True,
        blank=True,
        verbose_name="funcionario",
        help_text=(
            "Vacío solo para cuentas técnicas (superusuario) sin un "
            "funcionario asociado en terreno."
        ),
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.ACTIVE,
        verbose_name="estado",
    )

    class Meta:
        verbose_name = "Perfil de usuario"
        verbose_name_plural = "Perfiles de usuario"

    def clean(self):
        super().clean()
        if self.officer_id and self.officer.status != Officer.Status.ACTIVE:
            raise ValidationError(
                {
                    "officer": (
                        "No se puede vincular un usuario del sistema a un "
                        "funcionario que no está activo."
                    )
                }
            )

    def __str__(self):
        return f"{self.user.get_username()} · {self.officer or 'sin funcionario'}"
