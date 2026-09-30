
from django.core.exceptions import ValidationError
from django.db import models

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

    class Meta:
        ordering = ("name",)
        verbose_name = "Delegación"
        verbose_name_plural = "Delegaciones"

    def __str__(self):
        return self.name


class Position(BaseModel):

    name = models.CharField(max_length=100, verbose_name="nombre")
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
    calculation_type = models.CharField(
        max_length=20,
        choices=CalculationType.choices,
        default=CalculationType.QUANTITATIVE,
        verbose_name="tipo de cálculo",
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

    class Meta:
        ordering = ("delegation__name", "name")
        verbose_name = "Funcionario"
        verbose_name_plural = "Funcionarios"

    def __str__(self):
        return self.name


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
