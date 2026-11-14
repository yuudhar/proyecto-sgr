from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from core import entry_rules, ui
from core.models import BaseModel
from organization.models import (
    Beneficiary,
    Delegation,
    Item,
    Officer,
    OrganizationLeader,
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

    class RequesterKind(models.TextChoices):
        NATURAL = "natural", "Persona natural"
        ORGANIZATION = "organization", "Organización"

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
    organization = models.ForeignKey(
        "organization.CommunityOrganization",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="activities",
        verbose_name="organización",
        help_text="Opcional: la junta de vecinos u organización con la que se relaciona la atención.",
    )
    requester_kind = models.CharField(
        max_length=20,
        choices=RequesterKind.choices,
        default=RequesterKind.NATURAL,
        verbose_name="tipo de solicitante",
        help_text="Si la atención la pide una persona natural o una organización (junta de vecinos u otra).",
    )
    organization_leader = models.ForeignKey(
        OrganizationLeader,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="activities",
        verbose_name="integrante de la directiva",
        help_text="Cuando viene una organización: quién de su directiva (presidente, tesorero…) hace la solicitud.",
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
            "Si queda marcado, se pide la fecha comprometida y el territorio, y la atención se refleja "
            "como compromiso en la agenda colectiva (tubo de trabajo)."
        ),
    )
    commitment = models.OneToOneField(
        "operations.Commitment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        editable=False,
        related_name="origin_activity",
        verbose_name="compromiso en la agenda",
        help_text="El compromiso que se creó en el tubo de trabajo al marcar la atención. Lo asigna el sistema.",
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
        self.check_requester_kind()
        self.check_week_open()
        self.check_daily_limit()

    def check_requester_kind(self):
        """Una atención de organización nombra la organización; si dice quién de la directiva viene, tiene que ser de ella."""
        if self.requester_kind == self.RequesterKind.ORGANIZATION:
            if not self.organization_id:
                raise ValidationError({"organization": "Elige la organización que hace la solicitud."})
            leader = self.organization_leader if self.organization_leader_id else None
            if leader is not None and leader.organization_id != self.organization_id:
                raise ValidationError(
                    {"organization_leader": "Esa persona no es de la directiva de la organización elegida."}
                )
        elif self.organization_leader_id:
            raise ValidationError(
                {"organization_leader": "Solo una atención de organización lleva integrante de la directiva."}
            )

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
    physical = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name="de terreno",
        help_text=(
            "Un compromiso físico (visita a terreno) aparece en la sección Compromisos; "
            "los demás, en la agenda colectiva. Lo define el sistema según la atención."
        ),
    )
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


class QuarterChangeRequest(BaseModel):
    """Solicitud para pasar una atención a otro trimestre: la pide un funcionario y la resuelve Jefatura.

    Al aprobarla, la atención toma la fecha nueva (y con ella cae en el otro período). Desde ese momento la solicitud
    queda como registro y ya no se edita.
    """

    class Mode(models.TextChoices):
        AUTOMATIC = "automatic", "Al siguiente trimestre (automático)"
        MANUAL = "manual", "Elegir la fecha (manual)"

    class Status(models.TextChoices):
        PENDING = "pending", "Pendiente"
        APPROVED = "approved", "Aprobada"
        REJECTED = "rejected", "Rechazada"

    activity = models.ForeignKey(
        Activity, on_delete=models.PROTECT, related_name="quarter_requests", verbose_name="atención"
    )
    delegation = models.ForeignKey(
        Delegation, on_delete=models.PROTECT, related_name="quarter_requests", verbose_name="delegación"
    )
    mode = models.CharField(
        max_length=20,
        choices=Mode.choices,
        default=Mode.AUTOMATIC,
        verbose_name="cómo se cambia",
        help_text=(
            "Automático: la atención pasa al primer día del trimestre siguiente. "
            "Manual: tú eliges la fecha nueva, que tiene que caer en otro trimestre."
        ),
    )
    previous_date = models.DateField(editable=False, verbose_name="fecha actual de la atención")
    new_date = models.DateField(null=True, blank=True, verbose_name="fecha nueva")
    reason = models.TextField(verbose_name="motivo")
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True, verbose_name="estado"
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="quarter_requests",
        verbose_name="solicitada por",
    )
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        editable=False,
        related_name="resolved_quarter_requests",
        verbose_name="resuelta por",
    )
    resolved_at = models.DateTimeField(null=True, blank=True, editable=False, verbose_name="resuelta el")
    resolution_comment = models.TextField(blank=True, verbose_name="respuesta de Jefatura")

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "Solicitud de cambio de trimestre"
        verbose_name_plural = "Solicitudes de cambio de trimestre"

    def __str__(self):
        return f"Cambio de trimestre · {self.activity}"

    @property
    def is_pending(self):
        return self.status == self.Status.PENDING

    @property
    def from_period(self):
        from operations.quarters import period_of

        return period_of(self.previous_date)

    @property
    def to_period(self):
        from operations.quarters import period_of

        return period_of(self.new_date)

    def clean(self):
        super().clean()
        if not self.activity_id:
            return
        if self._state.adding:
            self.check_request()
        elif self.status == self.Status.APPROVED:
            self.check_approval()

    def check_request(self):
        """Al pedirla: la atención no está archivada, no tiene otra solicitud pendiente y la fecha nueva cae en otro
        trimestre (abierto) y no es futura, porque una atención no puede tener fecha futura."""
        from operations.quarters import next_period, period_of

        activity = self.activity
        self.previous_date = activity.date
        if activity.deleted_at is not None:
            raise ValidationError({"activity": "Esa atención está archivada."})
        pending = QuarterChangeRequest.objects.filter(
            activity=activity, status=self.Status.PENDING, deleted_at__isnull=True
        ).exclude(pk=self.pk)
        if pending.exists():
            raise ValidationError({"activity": "Esa atención ya tiene una solicitud de cambio de trimestre pendiente."})
        source = period_of(activity.date)
        if self.mode == self.Mode.AUTOMATIC:
            if source is None:
                raise ValidationError(
                    {"mode": "La fecha de la atención no cae en ningún trimestre: elige la fecha a mano."}
                )
            following = next_period(source)
            if following is None:
                raise ValidationError({"mode": "Todavía no hay un trimestre siguiente creado: pídelo cuando exista."})
            self.new_date = following.start_date
        if self.new_date is None:
            raise ValidationError({"new_date": "Elige la fecha nueva de la atención."})
        if self.new_date > entry_rules.portal_today():
            raise ValidationError(
                {
                    "new_date" if self.mode == self.Mode.MANUAL else "mode": (
                        "La fecha nueva no puede ser futura "
                        f"(sería el {ui.fmt_date(self.new_date)}): una atención no puede tener fecha futura."
                    )
                }
            )
        target = period_of(self.new_date)
        field = "new_date" if self.mode == self.Mode.MANUAL else "mode"
        if target is None:
            raise ValidationError({field: "Esa fecha no cae en ningún trimestre creado."})
        if source is not None and target.pk == source.pk:
            raise ValidationError({field: "Esa fecha está en el mismo trimestre de la atención: elige otro trimestre."})
        if target.status == target.Status.CLOSED:
            raise ValidationError({field: f"El {ui.humanize_dates(target).lower()} ya está cerrado: no se pueden pasar atenciones a él."})

    def check_approval(self):
        """Al aprobarla se vuelve a mirar todo: pasó tiempo desde que se pidió."""
        from operations.quarters import period_of

        activity = self.activity
        if activity.deleted_at is not None:
            raise ValidationError("La atención está archivada: no se puede cambiar su trimestre.")
        if activity.date != self.previous_date:
            raise ValidationError(
                "La atención cambió de fecha después de esta solicitud. Recházala y que se pida de nuevo."
            )
        target = period_of(self.new_date)
        if target is None or target.status == target.Status.CLOSED:
            raise ValidationError("El trimestre de destino ya no está disponible (no existe o está cerrado).")
        limit = settings.DAILY_ENTRY_LIMIT
        if entry_rules.entries_on(activity.author_officer_id, self.new_date, exclude_pk=activity.pk) >= limit:
            raise ValidationError(
                f"El {ui.fmt_date(self.new_date)} el funcionario ya tiene {limit} atenciones: "
                f"el máximo es {limit} por día. No se puede aprobar."
            )

    FOLLOWUP_DATES = ("date", "scheduled_visit_date", "visit_date", "report_delivery_date", "benefit_delivery_date")

    def apply(self):
        """Pasa la atención a su fecha nueva (se llama al aprobar, ya revisado) y mueve con ella lo que cuelga de ella.

        Si la atención ocurrió otro día, su compromiso nace ese día y sus gestiones no pueden ser anteriores:
        * el compromiso enlazado toma la fecha nueva como fecha de solicitud y su fecha comprometida no queda antes;
        * cada gestión con una fecha (de la gestión, de visita o de entrega) anterior a la nueva pasa a la fecha nueva.
        Mover hacia adelante todas las fechas por igual conserva el orden que tenían entre sí.
        Devuelve lo que se movió: ``{"followups": n, "commitment": bool}``.
        """
        activity = self.activity
        new_date = self.new_date
        activity.date = new_date
        activity.save(update_fields=["date", "updated_at"])
        moved = {"followups": 0, "commitment": False}
        for followup in Followup.objects.filter(activity=activity, deleted_at__isnull=True):
            changes = {
                name: new_date
                for name in self.FOLLOWUP_DATES
                if getattr(followup, name) is not None and getattr(followup, name) < new_date
            }
            if changes:
                Followup.objects.filter(pk=followup.pk).update(**changes)
                moved["followups"] += 1
        commitment = activity.commitment if activity.commitment_id else None
        if commitment is not None:
            changes = {}
            if commitment.request_date != new_date:
                changes["request_date"] = new_date
            if commitment.due_date < new_date:
                changes["due_date"] = new_date
            if changes:
                Commitment.objects.filter(pk=commitment.pk).update(**changes)
                moved["commitment"] = True
        return moved
