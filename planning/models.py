from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

from core.models import BaseModel
from core.uploads import feedback_path
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
        max_digits=5, decimal_places=2, default=120, verbose_name="tope ponderado"
    )
    parameters_version = models.CharField(
        max_length=20, default="1", verbose_name="versión de parámetros"
    )
    compliment_value = models.DecimalField(
        max_digits=5, decimal_places=2, default=10, verbose_name="valor de una felicitación",
        help_text="Puntos porcentuales que suma cada felicitación (en la matriz, 10 %).",
    )
    complaint_value = models.DecimalField(
        max_digits=5, decimal_places=2, default=30, verbose_name="valor de un reclamo",
        help_text="Puntos porcentuales que resta cada reclamo (en las hojas de cada cargo de la matriz, 30 %).",
    )
    compliment_limit = models.PositiveIntegerField(
        default=3, verbose_name="máximo de felicitaciones por persona",
        help_text="Las felicitaciones que pasan de este máximo quedan registradas, pero sin efecto.",
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
    # v26: una meta del cargo la cumple cada funcionario por separado, así que el cálculo automático guarda un
    # indicador por funcionario. Los indicadores anteriores (sin funcionario) valen para quien tenga esa meta.
    officer = models.ForeignKey(
        Officer,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="indicators",
        verbose_name="calculado para",
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


class Absence(BaseModel):
    """RF-047: días en que un funcionario no está disponible (licencia, vacaciones, emergencia…).

    Los días hábiles (lunes a viernes) de la ausencia se descuentan de los días computables del período: la meta
    del funcionario se ajusta con los días efectivos (ver `planning/absences.py`).
    """

    class Kind(models.TextChoices):
        LICENSE = "license", "Licencia"
        VACATION = "vacation", "Vacaciones"
        ADMINISTRATIVE = "administrative", "Día administrativo"
        EMERGENCY = "emergency", "Emergencia"
        COMPENSATORY = "compensatory", "Compensatorio"

    officer = models.ForeignKey(
        Officer, on_delete=models.PROTECT, related_name="absences", verbose_name="funcionario"
    )
    kind = models.CharField(max_length=20, choices=Kind.choices, verbose_name="tipo de ausencia")
    start_date = models.DateField(verbose_name="desde")
    end_date = models.DateField(verbose_name="hasta")
    notes = models.CharField(max_length=255, blank=True, default="", verbose_name="observación")
    registered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        editable=False,
        related_name="registered_absences",
        verbose_name="registrada por",
    )

    class Meta:
        ordering = ("-start_date",)
        verbose_name = "Ausencia"
        verbose_name_plural = "Ausencias"

    @property
    def business_days(self):
        from .pace import weekdays_between

        return weekdays_between(self.start_date, self.end_date) if self.start_date and self.end_date else 0

    def clean(self):
        super().clean()
        if not (self.start_date and self.end_date and self.officer_id):
            return
        if self.end_date < self.start_date:
            raise ValidationError({"end_date": "La fecha «hasta» no puede ser anterior a la fecha «desde»."})
        overlapping = Absence.objects.filter(
            officer_id=self.officer_id,
            deleted_at__isnull=True,
            start_date__lte=self.end_date,
            end_date__gte=self.start_date,
        ).exclude(pk=self.pk)
        if overlapping.exists():
            other = overlapping.first()
            raise ValidationError(
                f"El funcionario ya tiene una ausencia entre el {other.start_date:%d/%m/%Y} y el {other.end_date:%d/%m/%Y}: "
                "las ausencias no pueden traslaparse."
            )

    def __str__(self):
        return f"{self.get_kind_display()} · {self.officer} · {self.start_date:%d/%m/%Y}"


class Feedback(BaseModel):
    """RF-046: felicitación o reclamo formal contra un funcionario, con su respaldo.

    Solo el delegado los registra. Al guardarse genera solo el ajuste (bonificación o penalización) del
    funcionario en el período de la fecha (ver `planning/feedback.py`): no se ingresa a mano.
    """

    class Kind(models.TextChoices):
        COMPLIMENT = "compliment", "Felicitación"
        COMPLAINT = "complaint", "Reclamo"

    class Channel(models.TextChoices):
        EMAIL = "email", "Correo al delegado"
        WHATSAPP = "whatsapp", "WhatsApp al delegado"
        LOGBOOK = "logbook", "Libro de observaciones de la oficina"

    kind = models.CharField(max_length=20, choices=Kind.choices, verbose_name="tipo")
    date = models.DateField(verbose_name="fecha")
    contact_name = models.CharField(max_length=150, verbose_name="nombre de quien escribe")
    contact = models.CharField(
        max_length=100, blank=True, default="", verbose_name="contacto",
        help_text="Teléfono o correo de quien escribe.",
    )
    channel = models.CharField(max_length=20, choices=Channel.choices, verbose_name="medio escrito")
    officer = models.ForeignKey(
        Officer, on_delete=models.PROTECT, related_name="feedbacks", verbose_name="profesional involucrado"
    )
    description = models.TextField(verbose_name="situación")
    support = models.FileField(
        upload_to=feedback_path,
        max_length=255,
        verbose_name="respaldo",
        help_text="Captura del correo o del WhatsApp, o foto del libro de observaciones.",
    )
    period = models.ForeignKey(
        Period, on_delete=models.PROTECT, related_name="feedbacks", editable=False, verbose_name="período"
    )
    effective = models.BooleanField(
        default=True, editable=False, verbose_name="con efecto",
        help_text="Falso cuando la felicitación pasa del máximo del período: queda registrada, pero sin efecto.",
    )
    adjustment = models.OneToOneField(
        Adjustment, on_delete=models.SET_NULL, null=True, blank=True, editable=False,
        related_name="feedback", verbose_name="ajuste generado",
    )
    registered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, editable=False,
        related_name="registered_feedbacks", verbose_name="registrada por",
    )

    class Meta:
        ordering = ("-date", "-pk")
        verbose_name = "Carta"
        verbose_name_plural = "Cartas"

    def clean(self):
        super().clean()
        from . import feedback

        if not self.date:
            return
        period = feedback.period_for(self.date)
        if period is None:
            raise ValidationError({"date": "Esa fecha no está dentro de ningún período."})
        if period.status == Period.Status.CLOSED:
            raise ValidationError({"date": "El período de esa fecha está cerrado: ya no admite cambios."})
        self.period = period
        if self.officer_id and self.officer.status != Officer.Status.ACTIVE:
            raise ValidationError({"officer": "El funcionario no está activo."})

    def save(self, *args, **kwargs):
        from . import feedback

        if self.date and not self.period_id:
            period = feedback.period_for(self.date)
            if period is not None:
                self.period = period
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.get_kind_display()} · {self.officer} · {self.date:%d/%m/%Y}"
