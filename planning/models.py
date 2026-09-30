
from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from core.models import BaseModel
from organization.models import Item, Position, Officer


class Period(BaseModel):
    class Status(models.TextChoices):
        PLANNED = "planned", "Planificado"
        ACTIVE = "active", "Vigente"
        CLOSED = "closed", "Cerrado"

    start_date = models.DateField(verbose_name="fecha de inicio")
    end_date = models.DateField(verbose_name="fecha de término")
    computable_days = models.PositiveIntegerField(verbose_name="días computables")
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PLANNED,
        verbose_name="estado",
    )
    collective_threshold = models.DecimalField(
        max_digits=5, decimal_places=2, default=80, verbose_name="umbral colectivo"
    )
    amber_threshold = models.DecimalField(
        max_digits=5, decimal_places=2, default=60, verbose_name="umbral ámbar"
    )
    weighted_cap = models.DecimalField(
        max_digits=5, decimal_places=2, default=150, verbose_name="tope ponderado"
    )
    parameters_version = models.CharField(
        max_length=20, default="1", verbose_name="versión de parámetros"
    )

    class Meta:
        ordering = ("-start_date",)
        verbose_name = "Período"
        verbose_name_plural = "Períodos"

    def __str__(self):
        return f"Período {self.start_date} – {self.end_date}"


class Goal(BaseModel):

    target_value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0.01)],
        verbose_name="valor objetivo",
        help_text="Debe ser mayor a 0 (equivale al CHECK del script SQL).",
    )
    unit = models.CharField(max_length=50, verbose_name="unidad")
    weight = models.DecimalField(
        max_digits=5, decimal_places=2, verbose_name="ponderador"
    )
    version = models.PositiveIntegerField(default=1, verbose_name="versión")
    item = models.ForeignKey(
        Item, on_delete=models.PROTECT, related_name="goals", verbose_name="ítem"
    )
    officer = models.ForeignKey(
        Officer,
        on_delete=models.PROTECT,
        related_name="goals",
        null=True,
        blank=True,
        verbose_name="funcionario",
    )
    position = models.ForeignKey(
        Position,
        on_delete=models.PROTECT,
        related_name="goals",
        null=True,
        blank=True,
        verbose_name="cargo",
    )
    period = models.ForeignKey(
        Period, on_delete=models.PROTECT, related_name="goals", verbose_name="período"
    )

    class Meta:
        verbose_name = "Meta"
        verbose_name_plural = "Metas"
        ordering = ("-period__start_date",)

    def __str__(self):
        return f"Meta {self.item} · {self.period}"


class Indicator(BaseModel):
    class StatusLight(models.TextChoices):
        GREEN = "green", "Verde"
        AMBER = "amber", "Ámbar"
        RED = "red", "Rojo"

    progress = models.DecimalField(
        max_digits=10, decimal_places=2, verbose_name="avance"
    )
    compliance = models.DecimalField(
        max_digits=5, decimal_places=2, verbose_name="cumplimiento"
    )
    weighting = models.DecimalField(
        max_digits=5, decimal_places=2, verbose_name="ponderación"
    )
    status_light = models.CharField(
        max_length=20, choices=StatusLight.choices, verbose_name="semáforo"
    )
    calculated_at = models.DateTimeField(
        auto_now_add=True, verbose_name="fecha de cálculo"
    )
    goal = models.ForeignKey(
        Goal, on_delete=models.PROTECT, related_name="indicators", verbose_name="meta"
    )

    class Meta:
        ordering = ("-calculated_at",)
        verbose_name = "Indicador"
        verbose_name_plural = "Indicadores"

    def __str__(self):
        return f"Indicador {self.goal} · {self.get_status_light_display()}"


class Adjustment(BaseModel):
    class Kind(models.TextChoices):
        BONUS = "bonus", "Bonificación"
        PENALTY = "penalty", "Penalización"

    kind = models.CharField(max_length=20, choices=Kind.choices, verbose_name="tipo")
    reason = models.CharField(max_length=255, verbose_name="motivo")
    percentage_value = models.DecimalField(
        max_digits=5, decimal_places=2, verbose_name="valor (%)"
    )
    date = models.DateTimeField(auto_now_add=True, verbose_name="fecha")
    officer = models.ForeignKey(
        Officer, on_delete=models.PROTECT, related_name="adjustments",
        verbose_name="funcionario",
    )
    period = models.ForeignKey(
        Period, on_delete=models.PROTECT, related_name="adjustments",
        verbose_name="período",
    )
    responsible_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="responsible_adjustments",
        verbose_name="usuario responsable",
    )

    class Meta:
        ordering = ("-date",)
        verbose_name = "Ajuste"
        verbose_name_plural = "Ajustes"

    def __str__(self):
        return f"Ajuste {self.get_kind_display()} · {self.officer}"
