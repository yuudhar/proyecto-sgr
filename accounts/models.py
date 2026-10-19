from collections import namedtuple

from django.conf import settings
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db import models

from core.models import BaseModel
from core.roles import GLOBAL_ROLE, ROLES
from core.uploads import photo_path
from organization.models import Delegation, Officer


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
    photo = models.FileField(
        upload_to=photo_path,
        max_length=255,
        null=True,
        blank=True,
        verbose_name="foto de perfil",
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


class RoleProfile(BaseModel):

    class Scope(models.TextChoices):
        OWN = "own", "Su delegación"
        ALL = "all", "Todas las delegaciones"

    class Status(models.TextChoices):
        ACTIVE = "active", "Activo"
        INACTIVE = "inactive", "Inactivo"

    group = models.OneToOneField(
        Group,
        on_delete=models.CASCADE,
        related_name="role_profile",
        verbose_name="rol",
    )
    description = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="descripción",
    )
    scope = models.CharField(
        max_length=10,
        choices=Scope.choices,
        default=Scope.OWN,
        verbose_name="alcance autorizado",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
        verbose_name="estado",
    )

    class Meta:
        verbose_name = "Ficha de rol"
        verbose_name_plural = "Fichas de roles"

    def __str__(self):
        return f"{self.group.name} · {self.get_scope_display()}"


class UserRoleDelegation(BaseModel):

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="role_delegations",
        verbose_name="usuario",
    )
    role = models.ForeignKey(
        Group,
        on_delete=models.CASCADE,
        related_name="user_delegations",
        verbose_name="rol",
    )
    delegation = models.ForeignKey(
        Delegation,
        on_delete=models.CASCADE,
        null=True,
        blank=False,
        related_name="user_roles",
        verbose_name="delegación",
    )

    class Meta:
        verbose_name = "Usuario, rol y delegación"
        verbose_name_plural = "Usuarios, roles y delegaciones"
        ordering = ("user_id", "role_id", "delegation_id")
        constraints = [
            models.UniqueConstraint(
                fields=("user", "role", "delegation"),
                name="uq_usuario_rol_delegacion",
            )
        ]

    def clean(self):
        super().clean()
        if self.user_id and self.role_id and not self.user.groups.filter(pk=self.role_id).exists():
            raise ValidationError(
                {"role": "El usuario no tiene este rol. Asígnaselo primero desde Control de usuarios."}
            )

    def __str__(self):
        return f"{self.user.get_username()} · {self.role.name} · {self.delegation or 'sin delegación'}"


def role_defaults(name):
    description = ROLES[name][1] if name in ROLES else ""
    scope = RoleProfile.Scope.ALL if name == GLOBAL_ROLE else RoleProfile.Scope.OWN
    return {"description": description, "scope": scope, "status": RoleProfile.Status.ACTIVE}


RoleDetails = namedtuple("RoleDetails", "description scope status")


def role_details(group):
    try:
        profile = group.role_profile
    except RoleProfile.DoesNotExist:
        values = role_defaults(group.name)
        return RoleDetails(values["description"], values["scope"], values["status"])
    return RoleDetails(profile.description, profile.scope, profile.status)


def group_is_global(group):
    details = role_details(group)
    return details.scope == RoleProfile.Scope.ALL and details.status == RoleProfile.Status.ACTIVE
