from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from core import entry_rules
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
    requester_is_delegate = models.BooleanField(
        default=False,
        verbose_name="el solicitante es el delegado",
        help_text="Una gestión pedida por el delegado es «otra gestión»: queda registrada, pero no suma puntaje.",
    )
    counts_for_score = models.BooleanField(
        default=True, db_index=True, editable=False, verbose_name="puntúa"
    )
    no_score_reason = models.CharField(
        max_length=120, blank=True, default="", editable=False, verbose_name="motivo por el que no puntúa"
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

    REASON_DELEGATE = "El solicitante es el delegado (otra gestión)"
    REASON_NO_CONTACT = "Falta el nombre o el teléfono del usuario"
    REASON_ITEM = "El ítem no otorga punto (gestión previa)"

    def score_reason(self):
        """Motivo por el que la actividad no suma puntaje, o «» si puede sumar (RF-039, RF-040 y RF-043)."""
        if self.requester_is_delegate:
            return self.REASON_DELEGATE
        beneficiary = self.beneficiary if self.beneficiary_id else None
        name = (self.contact_name or "").strip() or (beneficiary.name.strip() if beneficiary else "")
        phone = (self.phone or "").strip() or ((beneficiary.phone or "").strip() if beneficiary else "")
        if not name or not phone:
            return self.REASON_NO_CONTACT
        if self.item_id:
            item = self.item
            parent = item.parent_item if item.parent_item_id else None
            if not item.scores or (parent is not None and not parent.scores):
                return self.REASON_ITEM
        return ""

    def refresh_scoring(self):
        reason = self.score_reason()
        self.counts_for_score = not reason
        self.no_score_reason = reason

    def save(self, *args, **kwargs):
        self.refresh_scoring()
        update_fields = kwargs.get("update_fields")
        if update_fields is not None:
            kwargs["update_fields"] = {*update_fields, "counts_for_score", "no_score_reason"}
        super().save(*args, **kwargs)

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
        self.check_week_open()
        self.check_daily_limit()

    def check_daily_limit(self):
        """RF-041: un funcionario no puede ingresar más de DAILY_ENTRY_LIMIT atenciones con la misma fecha."""
        if not self.author_officer_id or not self.date:
            return
        limit = settings.DAILY_ENTRY_LIMIT
        if entry_rules.entries_on(self.author_officer_id, self.date, exclude_pk=self.pk) >= limit:
            raise ValidationError(
                f"Ya hay {limit} atenciones registradas con esta fecha: el máximo es {limit} por día. "
                "Hay que ingresar todos los días y no dejar un día para llenar la matriz."
            )

    def check_week_open(self):
        """RF-042: las atenciones de una semana se ingresan hasta el lunes siguiente.

        Se revisa al crear una atención y al cambiarle la fecha; editar otros datos de una atención antigua no se bloquea.
        """
        if not self.date:
            return
        if self.pk is not None:
            before = Activity.objects.filter(pk=self.pk).values_list("date", flat=True).first()
            if before == self.date:
                return
        if entry_rules.is_week_closed(self.date):
            raise ValidationError(entry_rules.closed_message(self.date))

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
        PENDING = "pending", "Pendiente"
        IN_PROGRESS = "in_progress", "En proceso"
        FULFILLED = "fulfilled", "Realizado"

    # RF-018: a qué estados se puede pasar desde cada uno. «Ingresado» es solo el estado inicial; un compromiso
    # «Realizado» solo se puede reabrir a «En proceso» (el cambio queda en el historial).
    TRANSITIONS = {
        "submitted": ("pending", "in_progress", "fulfilled"),
        "pending": ("in_progress", "fulfilled"),
        "in_progress": ("pending", "fulfilled"),
        "fulfilled": ("in_progress",),
    }

    @classmethod
    def can_move(cls, current, new):
        return current == new or new in cls.TRANSITIONS.get(current, ())

    @classmethod
    def next_choices(cls, current):
        """Opciones válidas para un compromiso que hoy está en ese estado: el actual y los que se pueden alcanzar."""
        return [(value, label) for value, label in cls.Status.choices if cls.can_move(current, value)]

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
