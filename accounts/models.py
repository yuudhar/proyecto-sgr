
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
    # Foto opcional (PNG o JPG de hasta 2 MB). Guarda la ruta dentro de la carpeta de archivos del sistema.
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
    """Lo propio de un rol que el grupo de Django no guarda: descripción, alcance autorizado y estado.

    Es a los grupos lo que UserProfile es a los usuarios: una ficha 1 a 1 que completa la tabla de Django sin
    tocarla. El nombre y los permisos siguen en el grupo; aquí van los tres datos que pide el mantenedor de
    Roles (A1: «Nombre, descripción, permisos y alcance autorizado») y el estado que muestra su listado.

    - alcance: «Todas las delegaciones» o «Su delegación» (la del funcionario del usuario). Lo leen las reglas
      de acceso (core/access.py) en vez de buscar el perfil por su nombre.
    - estado: un rol inactivo no se ofrece al asignar perfiles a un usuario y no da alcance sobre otras
      delegaciones. Un perfil del sistema no se desactiva.
    """

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
    """Delegación en la que un usuario ejerce un rol: la tabla Usuario_Rol_Delegacion de tu diagrama.

    Una fila dice «este usuario, con este rol, también trabaja en esta delegación». Sirve para los usuarios
    que atienden en más de una: la delegación de su funcionario sigue siendo la de siempre y estas filas le
    suman las otras. Con ellas, el selector de la franja de arriba (A2: «el selector debe mostrar únicamente
    las autorizadas») ofrece solo las delegaciones que le corresponden. Se editan desde Control de usuarios,
    que escribe una fila por cada rol del usuario y cada delegación adicional elegida.

    La columna de la delegación acepta NULL, como en tu tabla, pero aquí siempre se guarda una delegación: que
    un rol alcance «todas» lo decide el alcance del rol (RoleProfile.scope), no una fila sin delegación.
    Los permisos no dependen de estas filas: siguen viniendo de los roles (grupos de Django).
    """

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
        # Una fila de un rol que el usuario no tiene no daría acceso a nada: mejor avisarlo que dejarla muda.
        if self.user_id and self.role_id and not self.user.groups.filter(pk=self.role_id).exists():
            raise ValidationError(
                {"role": "El usuario no tiene este rol. Asígnaselo primero desde Control de usuarios."}
            )

    def __str__(self):
        return f"{self.user.get_username()} · {self.role.name} · {self.delegation or 'sin delegación'}"


def role_defaults(name):
    """Valores de la ficha de un rol nuevo.

    Un perfil del sistema trae su descripción de siempre (core/roles.py) y «Coordinación» ve todas las
    delegaciones; cualquier otro rol parte sin descripción, con alcance sobre su delegación y activo.
    """
    description = ROLES[name][1] if name in ROLES else ""
    scope = RoleProfile.Scope.ALL if name == GLOBAL_ROLE else RoleProfile.Scope.OWN
    return {"description": description, "scope": scope, "status": RoleProfile.Status.ACTIVE}


RoleDetails = namedtuple("RoleDetails", "description scope status")


def role_details(group):
    """Descripción, alcance y estado de un rol, leídos de su ficha.

    Un grupo que todavía no tiene ficha (se creó por fuera del mantenedor) se lee con los valores de siempre,
    sin escribir nada: así un listado o una comprobación de acceso nunca modifican la base de datos.
    """
    try:
        profile = group.role_profile
    except RoleProfile.DoesNotExist:
        values = role_defaults(group.name)
        return RoleDetails(values["description"], values["scope"], values["status"])
    return RoleDetails(profile.description, profile.scope, profile.status)


def group_is_global(group):
    """True si el rol está activo y da alcance sobre todas las delegaciones."""
    details = role_details(group)
    return details.scope == RoleProfile.Scope.ALL and details.status == RoleProfile.Status.ACTIVE
