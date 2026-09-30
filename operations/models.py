
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from core.models import BaseModel
from organization.models import (
    Beneficiary,
    Delegation,
    Item,
    Officer,
    Service,
    Territory,
)


class ManagementType(BaseModel):

    name = models.CharField(max_length=80, unique=True, verbose_name="nombre")

    class Meta:
        verbose_name = "Tipo de gestión"
        verbose_name_plural = "Tipos de gestión"
        ordering = ("name",)

    def __str__(self):
        return self.name


class Activity(BaseModel):
    class Status(models.TextChoices):
        REGISTERED = "registered", "Registrada"
        IN_PROGRESS = "in_progress", "En proceso"
        CLOSED = "closed", "Cerrada"

    date = models.DateField(verbose_name="fecha")
    request_description = models.TextField(
        blank=True, verbose_name="solicitud / problema"
    )
    action_taken = models.TextField(blank=True, verbose_name="acción")
    contact_name = models.CharField(
        max_length=100, blank=True, verbose_name="contacto"
    )
    phone = models.CharField(max_length=20, blank=True, verbose_name="teléfono")
    beneficiary = models.ForeignKey(
        Beneficiary,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="activities",
        verbose_name="beneficiario",
    )
    status = models.CharField(
        max_length=30, choices=Status.choices, default=Status.REGISTERED,
        verbose_name="estado",
    )
    requires_visit = models.BooleanField(
        default=False, verbose_name="requiere visita"
    )
    added_to_pipeline = models.BooleanField(
        default=False,
        verbose_name="ingresa al tubo de trabajo",
        help_text=(
            "Si queda marcado, la actividad se refleja como Commitment "
            "en la agenda colectiva (tubo de trabajo)."
        ),
    )
    item = models.ForeignKey(
        Item, on_delete=models.PROTECT, related_name="activities", verbose_name="ítem"
    )
    service = models.ForeignKey(
        Service,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="activities",
        verbose_name="servicio",
    )
    delegation = models.ForeignKey(
        Delegation, on_delete=models.PROTECT, related_name="activities",
        verbose_name="delegación",
    )
    author_officer = models.ForeignKey(
        Officer,
        on_delete=models.PROTECT,
        related_name="authored_activities",
        verbose_name="funcionario autor",
    )

    class Meta:
        ordering = ("-date",)
        verbose_name = "Actividad"
        verbose_name_plural = "Actividades"

    def clean(self):
        super().clean()
        if (
            self.author_officer_id
            and self.delegation_id
            and self.author_officer.delegation_id != self.delegation_id
        ):
            raise ValidationError(
                {
                    "delegation": (
                        "La delegación debe coincidir con la delegación del "
                        "funcionario que registra la actividad."
                    )
                }
            )

    def __str__(self):
        return f"Actividad {self.date} · {self.contact_name or self.pk}"


class Followup(BaseModel):

    sequence_number = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(3)],
        verbose_name="número de gestión",
        help_text="1ra, 2da o 3ra gestión sobre la misma actividad.",
    )
    management_type = models.ForeignKey(
        ManagementType,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="followups",
        verbose_name="tipo de gestión",
    )
    date = models.DateField(verbose_name="fecha")
    result = models.CharField(max_length=255, verbose_name="resultado")
    scheduled_visit_date = models.DateField(
        null=True, blank=True, verbose_name="fecha programada de visita"
    )
    visit_date = models.DateField(null=True, blank=True, verbose_name="fecha de visita")
    report_delivery_date = models.DateField(
        null=True, blank=True, verbose_name="fecha de entrega de informe"
    )
    benefit_delivery_date = models.DateField(
        null=True, blank=True, verbose_name="fecha de entrega de beneficio"
    )
    activity = models.ForeignKey(
        Activity, on_delete=models.PROTECT, related_name="followups",
        verbose_name="actividad",
    )

    class Meta:
        verbose_name = "Gestión de atención"
        verbose_name_plural = "Gestiones de atención"
        ordering = ("-date",)
        constraints = [
            models.UniqueConstraint(
                fields=("activity", "sequence_number"), name="uq_activity_followup"
            )
        ]

    def __str__(self):
        return f"Gestión {self.sequence_number} · {self.activity}"


class Commitment(BaseModel):
    class RequesterType(models.TextChoices):
        INTERNAL = "INTERNAL", "Interno"
        EXTERNAL = "EXTERNAL", "Externo"

    class Status(models.TextChoices):
        SUBMITTED = "submitted", "Ingresado"
        IN_PROGRESS = "in_progress", "En proceso"
        FULFILLED = "fulfilled", "Cumplido"

    source = models.CharField(
        max_length=100, blank=True, null=True, verbose_name="origen"
    )
    request_date = models.DateField(
        null=True, blank=True, verbose_name="fecha de solicitud"
    )
    description = models.TextField(blank=True, null=True, verbose_name="descripción")
    requester = models.CharField(max_length=100, verbose_name="solicitante")
    requester_type = models.CharField(
        max_length=10,
        choices=RequesterType.choices,
        default=RequesterType.EXTERNAL,
        verbose_name="tipo de solicitante",
    )
    territory = models.ForeignKey(
        Territory, on_delete=models.PROTECT, related_name="commitments",
        verbose_name="territorio",
    )
    due_date = models.DateField(verbose_name="fecha comprometida")
    support = models.CharField(
        max_length=100, blank=True, null=True, verbose_name="apoyo"
    )
    status = models.CharField(
        max_length=30, choices=Status.choices, default=Status.SUBMITTED,
        verbose_name="estado",
    )
    notes = models.TextField(blank=True, null=True, verbose_name="observación")
    responsible_officer = models.ForeignKey(
        Officer, on_delete=models.PROTECT, related_name="responsible_commitments",
        verbose_name="funcionario responsable",
    )
    delegation = models.ForeignKey(
        Delegation, on_delete=models.PROTECT, related_name="commitments",
        verbose_name="delegación",
    )

    class Meta:
        ordering = ("-due_date",)
        verbose_name = "Compromiso"
        verbose_name_plural = "Compromisos"

    def clean(self):
        super().clean()
        if (
            self.territory_id
            and self.delegation_id
            and self.territory.delegation_id != self.delegation_id
        ):
            raise ValidationError(
                {
                    "territory": (
                        "El territorio debe pertenecer a la delegación "
                        "seleccionada."
                    )
                }
            )

    def __str__(self):
        return f"Compromiso {self.requester} · {self.territory}"
