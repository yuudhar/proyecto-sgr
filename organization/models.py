import re

from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import IntegrityError, models, transaction

from core.models import BaseModel


class Delegation(BaseModel):

    class Status(models.TextChoices):
        ACTIVE = "active", "Activa"
        INACTIVE = "inactive", "Inactiva"

    name = models.CharField(max_length=100, unique=True, verbose_name="nombre")
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.ACTIVE,
        verbose_name="estado",
    )
    managers = models.CharField(
        max_length=255, blank=True, null=True, verbose_name="responsables"
    )
    scope = models.CharField(
        max_length=100, blank=True, null=True, verbose_name="ámbito"
    )
    address = models.CharField(
        max_length=200,
        blank=True,
        default="",
        verbose_name="dirección",
        help_text="Calle y número de la oficina de la delegación.",
    )
    commune = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="comuna",
    )
    color = models.CharField(
        max_length=7,
        default="#920000",
        validators=[
            RegexValidator(
                r"^#[0-9A-Fa-f]{6}\Z",
                "Escribe el color como #RRGGBB, por ejemplo #920000.",
            )
        ],
        verbose_name="color",
        help_text="Formato #RRGGBB. Identifica a la delegación en las pantallas.",
    )

    class Meta:
        ordering = ("name",)
        verbose_name = "Delegación"
        verbose_name_plural = "Delegaciones"

    def __str__(self):
        return self.name


class Position(BaseModel):

    name = models.CharField(max_length=100, verbose_name="nombre")
    description = models.TextField(
        max_length=500,
        blank=True,
        default="",
        verbose_name="descripción del cargo",
        help_text="Qué hace este cargo, tal como lo dice el descriptor de funciones.",
    )
    valid_from = models.DateField(verbose_name="vigencia desde")
    valid_until = models.DateField(
        null=True, blank=True, verbose_name="vigencia hasta"
    )

    class Meta:
        ordering = ("name",)
        verbose_name = "Cargo"
        verbose_name_plural = "Cargos"

    def __str__(self):
        return self.name


class PositionFunction(BaseModel):
    """Función de un cargo según el descriptor de funciones (RF-050); se muestra en la ficha personal."""

    MAX_LENGTH = 600

    position = models.ForeignKey(
        Position,
        on_delete=models.PROTECT,
        related_name="functions",
        verbose_name="cargo",
    )
    group = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="agrupación",
        help_text="Opcional. Título bajo el que se agrupan varias funciones, por ejemplo «Atención de casos».",
    )
    order = models.PositiveSmallIntegerField(
        default=1,
        verbose_name="orden",
        help_text="Posición de la función dentro de su cargo (1, 2, 3…).",
    )
    text = models.TextField(max_length=MAX_LENGTH, verbose_name="función")

    class Meta:
        ordering = ("position__name", "order", "id")
        verbose_name = "Función de cargo"
        verbose_name_plural = "Funciones de cargos"

    def __str__(self):
        return f"{self.position} · {self.order}. {self.text[:60]}"


class Item(BaseModel):

    class CalculationType(models.TextChoices):
        QUANTITATIVE = "quantitative", "Cuantitativo"
        QUALITATIVE = "qualitative", "Cualitativo"

    parent_item = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="sub_items",
        verbose_name="ítem padre (tipo de atención)",
    )
    name = models.CharField(max_length=150, verbose_name="nombre")
    description = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="descripción",
    )
    calculation_type = models.CharField(
        max_length=20,
        choices=CalculationType.choices,
        default=CalculationType.QUANTITATIVE,
        verbose_name="tipo de cálculo",
    )
    scores = models.BooleanField(
        default=True,
        verbose_name="otorga punto",
        help_text=(
            "Si está desmarcado, las gestiones de este ítem no suman al avance (por ejemplo las gestiones previas: "
            "enviar correos, coordinar o invitar; el punto lo da realizar la acción)."
        ),
    )

    class Meta:
        ordering = ("name",)
        verbose_name = "Ítem"
        verbose_name_plural = "Ítems"

    def __str__(self):
        return self.name


class Service(BaseModel):

    class Status(models.TextChoices):
        ACTIVE = "active", "Activo"
        INACTIVE = "inactive", "Inactivo"

    name = models.CharField(max_length=100, verbose_name="nombre")
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.ACTIVE,
        verbose_name="estado",
    )

    class Meta:
        ordering = ("name",)
        verbose_name = "Servicio"
        verbose_name_plural = "Servicios"

    def __str__(self):
        return self.name


class Beneficiary(BaseModel):

    rut = models.CharField(max_length=12, unique=True, verbose_name="RUT")
    name = models.CharField(max_length=150, verbose_name="nombre")
    phone = models.CharField(
        max_length=20, blank=True, null=True, verbose_name="teléfono"
    )
    address = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="dirección",
        help_text="Calle y número de la vivienda (ej.: Los Aromos 1234).",
    )

    class Meta:
        ordering = ("name",)
        verbose_name = "Beneficiario"
        verbose_name_plural = "Beneficiarios"

    def __str__(self):
        return f"{self.name} ({self.rut})"


class Territory(BaseModel):

    name = models.CharField(max_length=100, verbose_name="nombre")
    delegation = models.ForeignKey(
        Delegation,
        on_delete=models.PROTECT,
        related_name="territories",
        verbose_name="delegación",
    )

    class Meta:
        ordering = ("delegation__name", "name")
        verbose_name = "Territorio"
        verbose_name_plural = "Territorios"
        constraints = [
            models.UniqueConstraint(
                fields=("name", "delegation"), name="uq_territory_delegation"
            )
        ]

    def __str__(self):
        return f"{self.name} · {self.delegation}"


class CommunityOrganization(BaseModel):
    """RF-049: junta de vecinos u otra organización comunitaria (base entregada por el cliente, «sin verificar»)."""

    name = models.CharField(max_length=255, verbose_name="nombre")
    legal_address = models.CharField(max_length=255, blank=True, default="", verbose_name="domicilio legal")
    territory = models.ForeignKey(
        Territory,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="organizations",
        verbose_name="territorio",
    )
    territory_text = models.CharField(
        max_length=100, blank=True, default="", verbose_name="territorio según la base",
        help_text="El territorio tal como venía en la base importada.",
    )
    active_members = models.PositiveIntegerField(null=True, blank=True, verbose_name="socios activos")
    constitution_date = models.DateField(null=True, blank=True, verbose_name="fecha de constitución")
    registry_number = models.PositiveIntegerField(unique=True, verbose_name="N.º de registro")
    registration_date = models.DateField(null=True, blank=True, verbose_name="fecha de inscripción")
    directory_number = models.PositiveIntegerField(null=True, blank=True, verbose_name="N.º de directorio")
    verified = models.BooleanField(
        default=False,
        verbose_name="verificada",
        help_text="La base entregada viene «sin verificar»: se marca cuando se confirman sus datos.",
    )

    class Meta:
        ordering = ("name",)
        verbose_name = "Organización"
        verbose_name_plural = "Organizaciones"

    def __str__(self):
        return self.name


class OrganizationLeader(BaseModel):
    """Integrante de la directiva de una organización comunitaria (registro propio, no es un Beneficiario)."""

    class Role(models.TextChoices):
        PRESIDENT = "president", "Presidente"
        SECRETARY = "secretary", "Secretario"
        TREASURER = "treasurer", "Tesorero"
        DIRECTOR = "director", "Directivo"
        OTHER = "other", "Otro cargo"

    # Los cargos que solo puede ocupar una persona por organización.
    SINGLE_ROLES = (Role.PRESIDENT, Role.SECRETARY, Role.TREASURER)

    organization = models.ForeignKey(
        CommunityOrganization,
        on_delete=models.PROTECT,
        related_name="leaders",
        verbose_name="organización",
    )
    role = models.CharField(
        max_length=20, choices=Role.choices, default=Role.DIRECTOR, verbose_name="cargo en la directiva"
    )
    role_detail = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="detalle del cargo",
        help_text="Solo para «Otro cargo»: por ejemplo, Director suplente o Delegado de calle.",
    )
    name = models.CharField(max_length=150, verbose_name="nombre")
    rut = models.CharField(max_length=12, verbose_name="RUT")
    email = models.CharField(max_length=254, blank=True, default="", verbose_name="correo")

    class Meta:
        ordering = ("organization__name", "name")
        verbose_name = "Integrante de directiva"
        verbose_name_plural = "Directivas de organizaciones"

    def __str__(self):
        return f"{self.name} · {self.role_text()}"

    @property
    def choice_label(self):
        return f"{self.name} · {self.role_text()}"

    def role_text(self):
        if self.role == self.Role.OTHER and self.role_detail:
            return self.role_detail
        return self.get_role_display()


class Officer(BaseModel):

    class Status(models.TextChoices):
        ACTIVE = "active", "Activo"
        INACTIVE = "inactive", "Inactivo"

    institutional_id = models.CharField(
        max_length=20, unique=True, verbose_name="identificador institucional"
    )
    name = models.CharField(max_length=150, verbose_name="nombre")
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.ACTIVE,
        verbose_name="estado",
    )
    delegation = models.ForeignKey(
        Delegation,
        on_delete=models.PROTECT,
        related_name="officers",
        verbose_name="delegación",
    )
    position = models.ForeignKey(
        Position,
        on_delete=models.PROTECT,
        related_name="officers",
        verbose_name="cargo",
    )

    ID_FORMAT = re.compile(r"F-([0-9]{4})")
    ID_ATTEMPTS = 5

    class Meta:
        ordering = ("delegation__name", "name")
        verbose_name = "Funcionario"
        verbose_name_plural = "Funcionarios"

    def __str__(self):
        return self.name

    @classmethod
    def id_numbers(cls, queryset):
        numbers = []
        for value in queryset.values_list("institutional_id", flat=True):
            match = cls.ID_FORMAT.fullmatch(value)
            if match:
                numbers.append(int(match.group(1)))
        return numbers

    def next_institutional_id(self):
        everyone = type(self)._base_manager.all()
        taken = self.id_numbers(everyone)
        own = self.id_numbers(everyone.filter(delegation_id=self.delegation_id))
        block = max((number // 1000 for number in own), default=None)
        if block is None:
            block = max((number // 1000 for number in taken), default=0) + 1
        number = block * 1000 + max((n % 1000 for n in taken if n // 1000 == block), default=0) + 1
        while number in taken:
            number += 1
        return f"F-{number}"

    def save(self, *args, **kwargs):
        if self.institutional_id:
            return super().save(*args, **kwargs)
        for attempt in range(self.ID_ATTEMPTS):
            self.institutional_id = self.next_institutional_id()
            try:
                with transaction.atomic():
                    return super().save(*args, **kwargs)
            except IntegrityError:
                if attempt == self.ID_ATTEMPTS - 1:
                    self.institutional_id = ""
                    raise


class PositionItem(BaseModel):

    class Kind(models.TextChoices):
        NORMAL = "NORMAL", "Normal"
        BONUS = "BONUS", "Bonificación"
        PENALTY = "PENALTY", "Penalización"

    position = models.ForeignKey(
        Position,
        on_delete=models.PROTECT,
        related_name="position_items",
        verbose_name="cargo",
    )
    item = models.ForeignKey(
        Item, on_delete=models.PROTECT, related_name="position_items",
        verbose_name="ítem",
    )
    weight = models.DecimalField(
        max_digits=5, decimal_places=2, verbose_name="ponderador"
    )
    valid_from = models.DateField(verbose_name="vigencia desde")
    valid_until = models.DateField(
        null=True, blank=True, verbose_name="vigencia hasta"
    )
    kind = models.CharField(
        max_length=20, choices=Kind.choices, default=Kind.NORMAL,
        verbose_name="tipo",
    )
    max_cap = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="tope máximo",
    )

    class Meta:
        verbose_name = "Ítem de cargo"
        verbose_name_plural = "Ítems de cargo"
        ordering = ("position__name", "item__name")

    def clean(self):
        super().clean()
        if self.kind != self.Kind.NORMAL and self.max_cap is None:
            raise ValidationError(
                {
                    "max_cap": (
                        "Las bonificaciones y penalizaciones deben definir "
                        "un tope máximo."
                    )
                }
            )

    def __str__(self):
        return f"{self.position} · {self.item} ({self.get_kind_display()})"
