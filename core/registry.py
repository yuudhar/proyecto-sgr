from pathlib import Path

from django.contrib import messages
from django.contrib.auth.models import Group, User
from django.db.models import Count, Q
from django.urls import reverse
from django.utils import timezone

from accounts.delegations import listed_extra_delegations, stored_delegation_ids, sync_extra_delegations
from accounts.models import RoleDetails, RoleProfile, UserProfile, group_is_global, role_details
from core.access import active_delegation, default_delegation, request_delegation, request_officer
from core import ui, uploads
from core.audit import log_event
from core.commitments import DEADLINE_LABELS, deadline_of, deadline_text, history_of, record_status
from core.crud import CODE_COLUMN, Canvas, Cell, Col, Crud, Related, is_id, registry
from core.forms import (
    ActivityEditForm,
    ActivityIntakeForm,
    AbsenceForm,
    FeedbackForm,
    AdjustmentForm,
    CommitmentForm,
    DelegationForm,
    EvidenceForm,
    FollowupForm,
    GoalForm,
    IndicatorForm,
    ItemForm,
    LeaderForm,
    QuarterRequestForm,
    QuarterResolveForm,
    OfficerForm,
    PeriodForm,
    PositionForm,
    PositionItemForm,
    RoleForm,
    SubAttentionForm,
    UserForm,
    split_person_name,
)
from core.models import AuditLog
from core.activity_stats import recent_activity
from core.results import current_period, officer_summary, weight_problems, weights_state
from core.photos import change_photo, photo_url_of, remove_photo
from core.roles import (
    ACTIONS,
    PERMISSION_MODULES,
    SUPERUSER_ROLE,
    SYSTEM_GROUPS,
    permission_key,
    permission_text,
    sort_key,
)
from evidence.models import Evidence, Validation
from operations import pipeline
from operations.models import Activity, Commitment, Followup, ManagementType, QuarterChangeRequest
from organization.models import (
    Beneficiary,
    CommunityOrganization,
    Delegation,
    Item,
    Officer,
    OrganizationLeader,
    Position,
    PositionItem,
    Service,
    Territory,
)
from planning import feedback as feedback_rules
from planning.calculation import IndicatorIndex
from planning.models import Absence, Adjustment, Feedback, Goal, Indicator, Period
from planning.pace import pace_of


def count_text(total, one, many):
    return f"{total} {one if total == 1 else many}"


def own_officer_defaults(request, *fields):
    officer = request_officer(request)
    initial = {}
    if officer is not None:
        delegation = request_delegation(request)
        if delegation is None or delegation.pk == officer.delegation_id:
            for name in fields:
                initial[name] = officer.pk
    return initial


def visible_activity(request, pk):
    if not is_id(pk):
        return None
    return (
        registry.get("actividades")
        .get_queryset(request)
        .select_related("delegation")
        .filter(pk=pk)
        .first()
    )


def visible_beneficiary(request, pk):
    if not is_id(pk):
        return None
    person = Beneficiary.objects.filter(pk=pk, deleted_at__isnull=True).first()
    if person is None:
        return None
    if registry.get("beneficiarios").has_perm(request.user, "view"):
        return person
    seen = registry.get("actividades").get_queryset(request).filter(beneficiary=person).exists()
    return person if seen else None


def attention_type_name(activity):
    item = activity.item
    return (item.parent_item or item).name


def sub_attention_name(activity):
    item = activity.item
    return item.name if item.parent_item_id else ""


SCORING = {"scores": "Puntúa", "no_score": "No puntúa"}


def scoring_state(activity):
    return "scores" if activity.counts_for_score else "no_score"


@registry.register
class ActivityCrud(Crud):
    model = Activity
    slug = "actividades"
    icon = "bi-clipboard-check"
    title = "Atención"
    title_plural = "Atenciones"
    list_title = "Atención"
    gender = "f"
    description = "Atenciones y gestiones que cada funcionario registra en terreno."
    list_redirect = "core:atencion"
    code_prefix = "ATN"
    code_digits = 5
    code_label = "Identificador"
    list_display = (
        Col(CODE_COLUMN),
        "date",
        Col("contact_name", "Contacto", link=True),
        Col("attention_type", "Tipo de atención"),
        Col("sub_attention", "Sub atención"),
        "author_officer",
        "delegation",
        "status",
        "requires_visit",
        Col("scoring", "Puntaje", kind="badge", sort=False),
    )
    computed = {"attention_type": attention_type_name, "sub_attention": sub_attention_name, "scoring": scoring_state}
    computed_choices = {"scoring": SCORING}
    search_fields = (
        "contact_name",
        "phone",
        "request_description",
        "beneficiary__name",
        "beneficiary__rut",
        "organization__name",
        "organization_leader__name",
    )
    list_filters = (
        "delegation",
        "status",
        "requester_kind",
        "counts_for_score",
        "requires_visit",
        "added_to_pipeline",
        "item",
        "author_officer",
    )
    select_related = (
        "delegation", "item", "item__parent_item", "author_officer", "beneficiary", "service", "organization_leader",
    )
    form_fields = (
        "date",
        "item",
        "service",
        "requester_kind",
        "beneficiary",
        "organization",
        "organization_leader",
        "contact_name",
        "phone",
        "request_description",
        "action_taken",
        "status",
        "requires_visit",
        "added_to_pipeline",
        "due_date",
        "territory",
        "requester_is_delegate",
        "delegation",
        "author_officer",
    )
    create_form_base = ActivityIntakeForm
    create_fields = (
        "requester_kind",
        "requester",
        "organization",
        "organization_leader",
        "phone",
        "attention_type",
        "item",
        "service",
        "request_description",
        "action_taken",
        "requires_visit",
        "added_to_pipeline",
        "due_date",
        "territory",
        "requester_is_delegate",
        "delegation",
        "author_officer",
    )
    create_heading = "Registrar atención"
    create_save_label = "Registrar atención"
    full_width = ("requester", "request_description", "action_taken")
    help_texts = {
        "requires_visit": "Si es algo físico (visita a terreno), la atención pasa sola a Compromisos: se pide la fecha comprometida y el territorio.",
        "added_to_pipeline": "Marca la atención para seguirla en el tubo de trabajo: se pide la fecha comprometida y el territorio.",
    }
    rules = {"phone": "phone", "requester": "label", "contact_name": "label"}
    form_base = ActivityEditForm
    delegation_lookup = "delegation"
    related = (
        Related("gestiones", "activity", "Gestiones de atención"),
        Related("evidencias", "activity", "Evidencias"),
        Related("cambios-trimestre", "activity", "Cambios de trimestre"),
    )

    @property
    def new_label(self):
        return "Registrar atención"

    def initial_values(self, request):
        person = visible_beneficiary(request, request.GET.get("beneficiary", ""))
        if person is None:
            return {}
        return {"requester": person.rut, "phone": person.phone or ""}

    def say(self, kind, obj):
        if kind == "created":
            who = f" para {obj.contact_name}" if obj.contact_name else ""
            return f"Atención registrada{who}. Identificador: {self.code_of(obj)}."
        return super().say(kind, obj)

    def after_save(self, request, obj, form, creating):
        # Una atención que requiere visita (algo físico) crea su compromiso en Compromisos; la que solo ingresa al
        # tubo de trabajo, en la agenda colectiva.
        if not form.wants_pipeline():
            return
        commitment = pipeline.create_commitment(obj, form.cleaned_data["due_date"], form.cleaned_data["territory"])
        record_status(request.user, commitment, None, commitment.status)
        log_event(request.user, "Registro creado", commitment, new=str(commitment))
        section = "Compromisos" if commitment.physical else "la Agenda colectiva"
        messages.info(
            request,
            f"Se creó el compromiso en {section} para el {ui.fmt_date(commitment.due_date)} "
            f"({commitment.territory}).",
        )


@registry.register
class FollowupCrud(Crud):
    model = Followup
    slug = "gestiones"
    icon = "bi-chat-left-text"
    gender = "f"
    description = "Hasta tres gestiones de seguimiento por cada actividad."
    list_display = (
        Col("activity", "Actividad", link=True, sort=False),
        Col("sequence_number", "Gestión N°"),
        "management_type",
        "date",
        "result",
    )
    search_fields = ("result", "activity__contact_name", "activity__beneficiary__name")
    list_filters = ("management_type",)
    select_related = ("activity", "management_type")
    form_fields = (
        "activity",
        "sequence_number",
        "management_type",
        "date",
        "result",
        "scheduled_visit_date",
        "visit_date",
        "report_delivery_date",
        "benefit_delivery_date",
    )
    full_width = ("result",)
    rules = {"result": "label"}
    form_base = FollowupForm
    delegation_lookup = "activity__delegation"

    def initial_values(self, request):
        initial = {"date": timezone.localdate()}
        activity = visible_activity(request, request.GET.get("activity", ""))
        if activity is not None:
            initial["activity"] = activity.pk
        return initial


@registry.register
class CommitmentCrud(Crud):
    model = Commitment
    slug = "agenda"
    icon = "bi-calendar-check"
    deletable = True
    title = "Compromiso"
    title_plural = "Compromisos"
    list_title = "Agenda colectiva"
    description = "Compromisos con vecinos, organizaciones y la propia municipalidad."
    queryset_filter = {"physical": False}
    list_display = (
        Col("requester", "Solicitante", link=True),
        "territory",
        "responsible_officer",
        "due_date",
        Col("deadline", "Plazo", kind="badge", sort=False),
        "status",
        "requester_type",
    )
    computed = {"deadline": deadline_of}
    computed_choices = {"deadline": DEADLINE_LABELS}
    search_fields = ("requester", "territory__name", "description")
    list_filters = ("delegation", "status", "requester_type")
    select_related = ("territory", "territory__delegation", "delegation", "responsible_officer")
    form_fields = (
        "requester",
        "requester_type",
        "source",
        "request_date",
        "description",
        "territory",
        "due_date",
        "support",
        "status",
        "notes",
        "responsible_officer",
        "delegation",
    )
    full_width = ("description", "notes")
    rules = {"requester": "label", "source": "label", "support": "label"}
    form_base = CommitmentForm
    delegation_lookup = "delegation"
    detail_panel = "core/crud/commitment_history.html"

    def panel_context(self, request, obj):
        return {"history": history_of(obj)}

    def extra_detail(self, obj):
        state = deadline_of(obj)
        tone, icon = ui.tone_for(state)
        return [
            ("Plazo", Cell(kind="badge", text=DEADLINE_LABELS[state], tone=tone, icon=icon)),
            ("Detalle del plazo", Cell(text=deadline_text(obj))),
        ]

    def after_save(self, request, obj, form, creating):
        # RF-018: cada estado queda en el historial, con quién lo cambió y cuándo.
        previous = None if creating else form.initial.get("status")
        if creating or previous != obj.status:
            record_status(request.user, obj, previous, obj.status)

    def initial_values(self, request):
        initial = {"request_date": timezone.localdate()}
        initial.update(own_officer_defaults(request, "responsible_officer"))
        delegation = default_delegation(request)
        if delegation is not None:
            initial["delegation"] = delegation.pk
        return initial


def compromisos_title(commitment):
    text = (commitment.description or "").strip()
    if not text:
        return f"Compromiso de {commitment.requester}"
    return text if len(text) <= 90 else text[:87].rstrip() + "…"


def compromisos_kpis(queryset):
    """Indicadores de la vista canvas de Compromisos, sobre el conjunto ya filtrado."""
    total = queryset.count()
    counts = {row["status"]: row["total"] for row in queryset.order_by().values("status").annotate(total=Count("pk"))}
    done = counts.get(Commitment.Status.FULFILLED.value, 0)
    rate = f"{round(done * 100 / total, 1):.1f}".replace(".", ",") if total else "0,0"
    return [
        {"label": "Compromisos", "value": total, "hint": "De atenciones con visita a terreno", "tone": "bad"},
        {"label": "Realizados", "value": done, "hint": f"Tasa de resolución: {rate} %", "tone": "ok"},
        {
            "label": "En proceso activo",
            "value": counts.get(Commitment.Status.IN_PROGRESS.value, 0),
            "hint": "En ejecución con su responsable",
            "tone": "warn",
        },
        {
            "label": "Pendientes / alerta",
            "value": counts.get(Commitment.Status.PENDING.value, 0),
            "hint": "Esperando gestión",
            "tone": "bad",
        },
    ]


def compromisos_plazo(commitment):
    state = deadline_of(commitment)
    return f"{ui.fmt_date(commitment.due_date)} · {DEADLINE_LABELS[state]}"


@registry.register
class FieldCommitmentCrud(CommitmentCrud):
    """Compromisos de terreno: lo físico (visitas) que nace de una atención. Comparte modelo y permisos con la agenda."""

    slug = "compromisos"
    icon = "bi-geo-alt"
    code_prefix = "COM"
    code_digits = 5
    list_title = "Compromisos"
    description = (
        "Lo físico: las atenciones que requieren visita a terreno llegan solas aquí y se siguen por estado."
    )
    queryset_filter = {"physical": True}
    related = ()
    canvas = Canvas(
        group_by="status",
        title=compromisos_title,
        lines=(
            ("Solicitante", lambda c: c.requester),
            ("Apoyo", lambda c: c.support or ""),
            ("Territorio", lambda c: str(c.territory)),
            ("Responsable", lambda c: c.responsible_officer.name),
            ("Plazo", compromisos_plazo),
            ("Origen", lambda c: c.source or ""),
        ),
        tones={"submitted": "neutral", "pending": "bad", "in_progress": "warn", "fulfilled": "ok"},
        movable=True,
        moves=lambda c: [(value, label) for value, label in Commitment.next_choices(c.status)],
        move_labels={"pending": "A Pendiente", "in_progress": "A Proceso", "fulfilled": "Realizar"},
        kpis=compromisos_kpis,
        empty="Sin compromisos",
    )

    def prepare_object(self, request, obj, creating, form):
        super().prepare_object(request, obj, creating, form)
        if creating:
            obj.physical = True

    def after_move(self, request, obj, previous):
        record_status(request.user, obj, previous, obj.status)


def trimestre_text(period):
    if period is None:
        return "Sin trimestre"
    return f"{ui.fmt_date(period.start_date)} al {ui.fmt_date(period.end_date)}"


def trimestre_title(request_):
    activity = request_.activity
    return f"{activity.item.name} · {activity.contact_name or 'sin contacto'}" if activity.item_id else str(activity)


def trimestre_kpis(queryset):
    counts = {row["status"]: row["total"] for row in queryset.order_by().values("status").annotate(total=Count("pk"))}
    Status = QuarterChangeRequest.Status
    return [
        {"label": "Solicitudes", "value": sum(counts.values()), "hint": "Cambios de trimestre pedidos", "tone": "bad"},
        {"label": "Pendientes", "value": counts.get(Status.PENDING.value, 0), "hint": "Esperando a Jefatura", "tone": "warn"},
        {"label": "Aprobadas", "value": counts.get(Status.APPROVED.value, 0), "hint": "La atención ya cambió de fecha", "tone": "ok"},
        {"label": "Rechazadas", "value": counts.get(Status.REJECTED.value, 0), "hint": "La atención conserva su fecha", "tone": "bad"},
    ]


@registry.register
class QuarterChangeRequestCrud(Crud):
    model = QuarterChangeRequest
    slug = "cambios-trimestre"
    icon = "bi-calendar2-range"
    gender = "f"
    archivable = False
    code_prefix = "TRI"
    code_digits = 5
    title = "Solicitud de cambio de trimestre"
    title_plural = "Cambios de trimestre"
    list_title = "Cambios de trimestre"
    description = (
        "El funcionario pide pasar una atención a otro trimestre (por ejemplo, una de diciembre a enero) y Jefatura "
        "la aprueba o la rechaza. Al aprobar, la atención toma la fecha nueva."
    )
    canvas = Canvas(
        group_by="status",
        title=trimestre_title,
        lines=(
            ("Fecha actual", lambda r: f"{ui.fmt_date(r.previous_date)} · {trimestre_text(r.from_period)}"),
            ("Fecha nueva", lambda r: f"{ui.fmt_date(r.new_date)} · {trimestre_text(r.to_period)}"),
            ("Cómo", lambda r: r.get_mode_display()),
            ("Pide", lambda r: r.requested_by.get_full_name() or r.requested_by.username),
            ("Motivo", lambda r: r.reason if len(r.reason) <= 90 else r.reason[:87].rstrip() + "…"),
            ("Respuesta", lambda r: r.resolution_comment),
        ),
        tones={"pending": "warn", "approved": "ok", "rejected": "bad"},
        kpis=trimestre_kpis,
        empty="Sin solicitudes",
    )
    delegation_lookup = "delegation"
    list_display = (
        Col("activity", "Atención", link=True),
        "previous_date",
        "new_date",
        "mode",
        "status",
        Col("requested_by", "Pide"),
        Col("resolved_by", "Resuelve"),
    )
    search_fields = ("activity__contact_name", "activity__item__name", "reason", "requested_by__username")
    list_filters = ("status", "mode", "delegation")
    select_related = ("activity", "activity__item", "delegation", "requested_by", "resolved_by")
    form_base = QuarterResolveForm
    create_form_base = QuarterRequestForm
    form_fields = ("status", "resolution_comment")
    create_fields = ("activity", "mode", "new_date", "reason")
    create_heading = "Pedir cambio de trimestre"
    create_save_label = "Enviar solicitud"
    create_add_another = False
    full_width = ("reason", "resolution_comment")
    rules = {"reason": "text", "resolution_comment": "text"}
    help_texts = {"activity": "Una atención de tu delegación."}

    @property
    def new_label(self):
        return "Pedir cambio de trimestre"

    def can_change_object(self, request, obj):
        # Resolverla es cosa de una sola vez: aprobada o rechazada, la solicitud queda como registro.
        return super().can_change_object(request, obj) and obj.is_pending

    def validate_form(self, form, cleaned):
        if "status" not in form.fields:
            return
        rejected = cleaned.get("status") == QuarterChangeRequest.Status.REJECTED
        if rejected and not form.has_error("resolution_comment") and not (cleaned.get("resolution_comment") or "").strip():
            form.add_error("resolution_comment", "Explica por qué se rechaza la solicitud.")

    def prepare_object(self, request, obj, creating, form):
        super().prepare_object(request, obj, creating, form)
        if creating:
            obj.requested_by = request.user
            obj.delegation = obj.activity.delegation
        elif obj.status != QuarterChangeRequest.Status.PENDING and obj.resolved_by_id is None:
            obj.resolved_by = request.user
            obj.resolved_at = timezone.now()

    def after_save(self, request, obj, form, creating):
        if creating or form.initial.get("status") != QuarterChangeRequest.Status.PENDING.value:
            return
        if obj.status != QuarterChangeRequest.Status.APPROVED:
            return
        activity = obj.activity
        old = activity.date
        obj.apply()
        log_event(
            request.user,
            "Cambio de trimestre aprobado",
            activity,
            previous=f"Fecha: {ui.fmt_date(old)}",
            new=f"Fecha: {ui.fmt_date(obj.new_date)}",
        )

    def extra_detail(self, obj):
        return [
            ("Trimestre actual", Cell(text=trimestre_text(obj.from_period))),
            ("Trimestre de destino", Cell(text=trimestre_text(obj.to_period))),
        ]


@registry.register
class EvidenceCrud(Crud):
    model = Evidence
    slug = "evidencias"
    icon = "bi-file-earmark-check"
    gender = "f"
    description = "Archivos que respaldan cada actividad y su estado de revisión."
    list_display = (
        Col("unique_code", "Código", link=True),
        Col("activity", "Actividad", sort=False),
        "author_officer",
        "review_status",
        "uploaded_at",
    )
    search_fields = ("unique_code", "file_link", "activity__contact_name")
    list_filters = ("review_status",)
    select_related = ("activity", "author_officer")
    form_base = EvidenceForm
    form_fields = ("activity", "unique_code", "file_link", "author_officer")
    full_width = ("file_link",)
    readonly_on_edit = ("unique_code",)
    rules = {"unique_code": "code"}
    help_texts = {
        "unique_code": "Se asignó sola al subir la evidencia y no se puede cambiar.",
    }
    delegation_lookup = "activity__delegation"
    related = (
        Related(
            "validaciones",
            "evidence",
            "Validaciones",
            columns=("decision", "reviewer_officer", "result", "date"),
        ),
    )

    def initial_values(self, request):
        initial = own_officer_defaults(request, "author_officer")
        activity = visible_activity(request, request.GET.get("activity", ""))
        if activity is not None:
            initial["activity"] = activity.pk
        return initial

    def prepare_object(self, request, obj, creating, form):
        super().prepare_object(request, obj, creating, form)
        if "file_link" in form.changed_data:
            obj.metadata = uploads.describe_file(form.cleaned_data["file_link"])
        if not creating and obj.review_status != Evidence.ReviewStatus.PENDING:
            if {"file_link", "activity"} & set(form.changed_data):
                obj.review_status = Evidence.ReviewStatus.PENDING
                messages.info(
                    request, "La evidencia cambió, así que quedó pendiente de una nueva revisión."
                )

    def make_cell(self, obj, column):
        if column.path == "file_link":
            name = obj.file_link.name if obj.file_link else ""
            if not name:
                return Cell(text="")
            if not obj.file_link.storage.exists(name):
                return Cell(text=f"{Path(name).name} (el archivo no está en el sistema)")
            return Cell(
                kind="file",
                text=Path(name).name,
                url=reverse("core:evidence_file", args=[obj.pk]),
                preview=uploads.is_image(name),
            )
        if column.path == "metadata" and obj.metadata:
            return Cell(text=" · ".join(obj.metadata.splitlines()))
        return super().make_cell(obj, column)

    def extra_actions(self, request, obj):
        officer = request_officer(request)
        own = officer is not None and obj.author_officer_id == officer.pk
        if obj.deleted_at is None and not own and request.user.has_perm("evidence.add_validation"):
            return [
                (
                    "Validar evidencia",
                    reverse("core:validate_evidence", args=[obj.pk]),
                    "bi-patch-check",
                )
            ]
        return []


@registry.register
class ValidationCrud(Crud):
    model = Validation
    slug = "validaciones"
    icon = "bi-patch-check"
    gender = "f"
    description = "Historial de revisiones de las evidencias. Se agregan desde Validar evidencias."
    allow_add = False
    allow_change = False
    archivable = False
    list_display = (
        Col("evidence", "Evidencia", link=True, sort=False),
        "decision",
        "reviewer_officer",
        "result",
        "date",
    )
    search_fields = ("evidence__unique_code", "result", "notes")
    list_filters = ("decision",)
    select_related = ("evidence", "reviewer_officer")
    delegation_lookup = "evidence__activity__delegation"


@registry.register
class PeriodCrud(Crud):
    model = Period
    slug = "periodos"
    icon = "bi-calendar-range"
    title = "Período"
    description = "Ventanas de medición con sus umbrales de semáforo."
    list_display = (
        Col("__str__", "Período", link=True, sort="start_date"),
        "status",
        "computable_days",
        Col("collective_threshold", "Umbral colectivo", kind="percent"),
        Col("amber_threshold", "Umbral ámbar", kind="percent"),
        Col("weighted_cap", "Tope ponderado", kind="percent"),
    )
    list_filters = ("status",)
    rules = {"parameters_version": "version"}
    bounds = {
        "computable_days": {"min": "1"},
        "collective_threshold": {"min": "0.01", "max": "100"},
        "amber_threshold": {"min": "0", "max": "100"},
        "weighted_cap": {"min": "0.01"},
        "compliment_value": {"min": "0.01", "max": "100"},
        "complaint_value": {"min": "0.01", "max": "100"},
        "compliment_limit": {"min": "1"},
    }
    form_base = PeriodForm
    form_fields = (
        "start_date",
        "end_date",
        "computable_days",
        "status",
        "collective_threshold",
        "amber_threshold",
        "weighted_cap",
        "compliment_value",
        "complaint_value",
        "compliment_limit",
        "parameters_version",
    )
    related = (Related("metas", "period", "Metas del período"),)


@registry.register
class GoalCrud(Crud):
    model = Goal
    slug = "metas"
    icon = "bi-bullseye"
    gender = "f"
    description = "Objetivos por funcionario o por cargo dentro de un período."
    list_display = (
        Col("item", "Ítem", link=True),
        "officer",
        "position",
        Col("period", "Período", sort="period__start_date"),
        Col("target_value", "Objetivo"),
        "unit",
        "weight",
    )
    search_fields = ("item__name", "officer__name", "position__name")
    list_filters = ("period", "position")
    select_related = ("item", "officer", "position", "period")
    form_base = GoalForm
    rules = {"unit": "label"}
    bounds = {
        "target_value": {"min": "0.01"},
        "weight": {"min": "0.01", "max": "100"},
        "version": {"min": "1"},
    }
    form_fields = (
        "item",
        "period",
        "officer",
        "position",
        "target_value",
        "unit",
        "weight",
        "version",
    )
    help_texts = {
        "target_value": "Debe ser mayor a 0.",
        "officer": "Elige un funcionario o un cargo para asignar la meta.",
        "weight": "Los ponderadores de cada funcionario en el período deben sumar 100 %.",
    }

    def after_save(self, request, obj, form, creating):
        # RF-006: no se impide guardar (las metas se crean de a una), pero se avisa si la suma no llega o pasa de 100 %.
        problems = weight_problems(obj)
        for officer, total, state in problems[:3]:
            verb = "no llegan a" if state == "under" else "superan"
            messages.warning(
                request,
                f"Ponderadores de {officer.name} en este período: suman {ui.fmt_number(total)} % y {verb} 100 %. "
                "Ajusta las metas para que sumen 100 %.",
            )
        if len(problems) > 3:
            messages.warning(request, f"Otros {len(problems) - 3} funcionarios también tienen ponderadores que no suman 100 %.")

    def extra_detail(self, obj):
        problems = {officer.pk: (total, state) for officer, total, state in weight_problems(obj)}
        from core.results import officer_weights
        from planning.calculation import officers_of

        officers = officers_of(obj)
        if obj.officer_id:
            total = officer_weights(obj.period, obj.officer)
            text = f"{ui.fmt_number(total)} %" + ("" if weights_state(total) == "ok" else " (deben sumar 100 %)")
            return [("Suma de ponderadores del funcionario", Cell(text=text))]
        if not officers:
            return []
        bad = len(problems)
        text = "Todos suman 100 %" if not bad else f"{bad} de {len(officers)} funcionarios no suman 100 %"
        return [("Ponderadores de los funcionarios del cargo", Cell(text=text))]
    related = (
        Related(
            "indicadores",
            "goal",
            "Indicadores",
            columns=("progress", "compliance", "weighting", "status_light", "calculated_at"),
        ),
    )


@registry.register
class IndicatorCrud(Crud):
    model = Indicator
    slug = "indicadores"
    icon = "bi-speedometer2"
    description = "Avance y cumplimiento de cada meta, con su semáforo."
    list_display = (
        Col("goal", "Meta", link=True, sort=False),
        Col("goal__officer", "Funcionario", sort=False),
        Col("goal__position", "Cargo", sort=False),
        "progress",
        Col("compliance", "Cumplimiento", kind="percent"),
        "weighting",
        "status_light",
        "calculated_at",
    )
    list_filters = ("status_light",)
    select_related = (
        "goal",
        "goal__item",
        "goal__period",
        "goal__officer",
        "goal__position",
    )
    search_fields = ("goal__item__name", "goal__officer__name")
    form_base = IndicatorForm
    form_fields = ("goal", "progress", "compliance", "weighting")
    bounds = {"progress": {"min": "0"}, "compliance": {"min": "0"}, "weighting": {"min": "0"}}
    help_texts = {
        "compliance": "Porcentaje de cumplimiento de la meta. El semáforo se calcula solo con los umbrales del período.",
    }

    def get_queryset(self, request, include_archived=False):
        qs = super().get_queryset(request, include_archived)
        delegation = active_delegation(request)
        if delegation is None:
            return qs
        return qs.filter(
            Q(goal__officer__delegation=delegation) | Q(goal__officer__isnull=True)
        )

    def prepare_object(self, request, obj, creating, form):
        super().prepare_object(request, obj, creating, form)
        period = obj.goal.period
        obj.status_light = ui.light_for_compliance(
            obj.compliance, period.collective_threshold, period.amber_threshold
        )


@registry.register
class AdjustmentCrud(Crud):
    model = Adjustment
    slug = "ajustes"
    icon = "bi-plus-slash-minus"
    description = "Bonificaciones y penalizaciones sobre el resultado de un funcionario."
    list_display = (
        Col("officer", "Funcionario", link=True),
        "kind",
        Col("percentage_value", "Valor", kind="percent"),
        Col("period", "Período", sort="period__start_date"),
        "responsible_user",
        "date",
    )
    search_fields = ("officer__name", "reason")
    list_filters = ("kind", "period")
    select_related = ("officer", "period", "responsible_user")
    form_base = AdjustmentForm
    form_fields = ("officer", "kind", "percentage_value", "period", "reason")
    rules = {"reason": "label"}
    bounds = {"percentage_value": {"min": "0.01", "max": "100"}}
    full_width = ("reason",)

    def prepare_object(self, request, obj, creating, form):
        super().prepare_object(request, obj, creating, form)
        if creating:
            obj.responsible_user = request.user


def feedback_effect(feedback):
    return feedback_rules.effect_text(feedback)


def feedback_alert(feedback):
    return feedback_rules.hr_alert(feedback)


def cartas_kpis(queryset):
    """Indicadores de la vista canvas de Cartas, sobre el conjunto ya filtrado."""
    total = queryset.count()
    compliments = queryset.filter(kind=Feedback.Kind.COMPLIMENT).count()
    complaints = total - compliments

    def share(part):
        return f"{round(part * 100 / total)} % del total" if total else "Sin cartas"

    return [
        {"label": "Cartas", "value": total, "hint": "Felicitaciones y reclamos", "tone": "neutral"},
        {"label": "Felicitaciones", "value": compliments, "hint": share(compliments), "tone": "ok"},
        {"label": "Reclamos", "value": complaints, "hint": share(complaints), "tone": "bad"},
    ]


@registry.register
class FeedbackCrud(Crud):
    model = Feedback
    slug = "cartas"
    icon = "bi-envelope-paper"
    gender = "f"
    code_prefix = "CAR"
    code_digits = 5
    description = (
        "Cartas de felicitación (suman) y de reclamo (restan) contra un funcionario, con su respaldo. "
        "Solo el delegado las registra y el ajuste se genera solo."
    )
    canvas = Canvas(
        group_by="kind",
        title=lambda letter: str(letter.officer),
        lines=(
            ("Fecha", lambda letter: ui.fmt_date(letter.date)),
            ("Escribe", lambda letter: letter.contact_name),
            ("Medio", lambda letter: letter.get_channel_display()),
            ("Efecto", lambda letter: feedback_effect(letter)),
            ("Aviso", lambda letter: feedback_alert(letter)),
            ("Respaldo", lambda letter: "Con archivo" if letter.support else ""),
        ),
        tones={"compliment": "ok", "complaint": "bad"},
        kpis=lambda qs: cartas_kpis(qs),
        empty="Sin cartas",
    )
    delegation_lookup = "officer__delegation"
    list_display = (
        Col("date", "Fecha", link=True),
        "kind",
        Col("officer", "Profesional involucrado"),
        "channel",
        "contact_name",
        Col("support", "Respaldo", sort=False),
        Col("effect", "Efecto", sort=False),
        Col("hr_alert", "Aviso", sort=False),
    )
    computed = {"effect": feedback_effect, "hr_alert": feedback_alert}
    search_fields = ("officer__name", "contact_name", "description")
    list_filters = ("kind", "channel", "officer")
    select_related = ("officer", "period", "registered_by")
    form_base = FeedbackForm
    form_fields = ("kind", "date", "officer", "channel", "contact_name", "contact", "description", "support")
    full_width = ("description", "support")
    rules = {"contact_name": "person_name", "contact": "label", "description": "text"}
    help_texts = {
        "kind": "Una felicitación suma al funcionario; un reclamo resta. El ajuste se genera solo al guardar.",
        "officer": "El profesional involucrado, de tu delegación.",
        "description": "La situación que se felicita o se reclama (un reclamo debe ser por mala atención del funcionario).",
    }

    def prepare_object(self, request, obj, creating, form):
        super().prepare_object(request, obj, creating, form)
        if creating:
            obj.registered_by = request.user

    def make_cell(self, obj, column):
        if column.path == "support":
            name = obj.support.name if obj.support else ""
            if not name:
                return Cell(text="")
            if not obj.support.storage.exists(name):
                return Cell(text=f"{Path(name).name} (el archivo no está en el sistema)")
            return Cell(
                kind="file",
                text=Path(name).name,
                url=reverse("core:feedback_file", args=[obj.pk]),
                preview=uploads.is_image(name),
            )
        return super().make_cell(obj, column)


@registry.register
class AbsenceCrud(Crud):
    model = Absence
    slug = "ausencias"
    icon = "bi-calendar-x"
    gender = "f"
    description = (
        "Días en que un funcionario no está disponible. Sus días hábiles se descuentan de los días computables "
        "y la meta del funcionario se ajusta."
    )
    delegation_lookup = "officer__delegation"
    list_display = (
        Col("officer", "Funcionario", link=True),
        "kind",
        "start_date",
        "end_date",
        Col("business_days", "Días hábiles", kind="number", sort=False),
        "notes",
    )
    computed = {"business_days": lambda absence: absence.business_days}
    search_fields = ("officer__name", "notes")
    list_filters = ("kind", "officer")
    select_related = ("officer", "registered_by")
    form_base = AbsenceForm
    form_fields = ("officer", "kind", "start_date", "end_date", "notes")
    rules = {"notes": "label"}
    full_width = ("notes",)
    help_texts = {
        "end_date": "Último día de la ausencia. Cuentan los días de lunes a viernes entre «desde» y «hasta».",
        "notes": "Opcional: licencia médica, feriado legal u otro dato que ayude a entender la ausencia.",
    }

    def prepare_object(self, request, obj, creating, form):
        super().prepare_object(request, obj, creating, form)
        if creating:
            obj.registered_by = request.user


@registry.register
class DelegationCrud(Crud):
    model = Delegation
    slug = "delegaciones"
    icon = "bi-building"
    gender = "f"
    description = "Sectores en que se organiza el trabajo en terreno."
    code_prefix = "DEL"
    list_display = (
        Col(CODE_COLUMN),
        Col("name", "Nombre", link=True),
        "address",
        "commune",
        "managers",
        "scope",
        Col("color", "Color", kind="color", sort=False),
        "status",
    )
    search_fields = ("name", "address", "commune", "scope", "managers")
    list_filters = ("status",)
    unique_names = ("name",)
    form_base = DelegationForm
    form_fields = ("name", "address", "commune", "managers", "scope", "color", "status")
    show_id = True
    labels = {"managers": "Encargado"}
    help_texts = {
        "commune": "Comuna donde queda la delegación, por ejemplo La Serena.",
        "managers": "Persona a cargo de la delegación: elígela con la lupa o escribe su nombre.",
        "color": "Identifica a la delegación en el menú y en las fichas. Escribe #RRGGBB o usa el selector.",
    }
    rules = {
        "name": "label",
        "color": "hex_color",
        "address": "label",
        "commune": "commune",
        "managers": "person_name",
        "scope": "label",
    }
    full_width = ("address",)
    related = (
        Related("funcionarios", "delegation", "Funcionarios"),
        Related("territorios", "delegation", "Territorios"),
    )

    def initial_values(self, request):
        return {"commune": "La Serena"}

    def archive_blockers(self, obj):
        reasons = []
        officers = obj.officers.filter(deleted_at__isnull=True).count()
        if officers:
            reasons.append(f"Tiene {count_text(officers, 'funcionario activo', 'funcionarios activos')}.")
        territories = obj.territories.filter(deleted_at__isnull=True).count()
        if territories:
            reasons.append(f"Tiene {count_text(territories, 'territorio activo', 'territorios activos')}.")
        if reasons:
            reasons.append("Archívalos o pásalos a otra delegación antes.")
        return reasons


@registry.register
class TerritoryCrud(Crud):
    model = Territory
    slug = "territorios"
    icon = "bi-geo-alt"
    deletable = True
    description = "Territorios de cada delegación."
    list_display = ("name", "delegation")
    search_fields = ("name", "delegation__name")
    list_filters = ("delegation",)
    select_related = ("delegation",)
    form_fields = ("name", "delegation")
    rules = {"name": "label"}
    unique_names = (("name", "delegation"),)
    delegation_lookup = "delegation"
    related = (
        Related("agenda", "territory", "Agenda colectiva"),
        Related("compromisos", "territory", "Compromisos"),
    )


def officer_access_text(officer):
    account = getattr(officer, "user_profile", None)
    return account.user.get_username() if account is not None else "Sin acceso"


@registry.register
class OfficerCrud(Crud):
    model = Officer
    slug = "funcionarios"
    icon = "bi-person-vcard"
    description = "Personas que registran actividades y responden por metas."
    list_display = ("name", "institutional_id", "delegation", "position", Col("access", "Acceso", sort=False), "status")
    computed = {"access": officer_access_text}
    search_fields = ("name", "institutional_id", "delegation__name")
    list_filters = ("delegation", "position", "status")
    select_related = ("delegation", "position", "user_profile__user")
    form_base = OfficerForm
    form_fields = ("institutional_id", "name", "status", "delegation", "position")
    rules = {
        "institutional_id": "code",
        "name": "person_name",
        "username": "username",
        "email": "email",
        "password1": "password",
    }
    delegation_lookup = "delegation"
    related = (Related("metas", "officer", "Metas"),)
    detail_panel = "core/crud/officer_sheet.html"

    def panel_context(self, request, obj):
        """RF-008: ficha personal con las metas del período, el avance, el cumplimiento y el aporte ponderado."""
        if not request.user.has_perm("planning.view_indicator"):
            return {}
        periods = list(Period.objects.filter(deleted_at__isnull=True).order_by("-start_date"))
        chosen = request.GET.get("periodo", "")
        period = next((each for each in periods if str(each.pk) == chosen), None) or current_period()
        if period is None:
            return {}
        goals = list(Goal.objects.filter(deleted_at__isnull=True, period=period).select_related("item"))
        pace = pace_of(period)
        sheet = officer_summary(obj, period, goals, IndicatorIndex([goal.pk for goal in goals]), pace)
        return {
            "sheet": sheet,
            "period": period,
            "periods": periods,
            "pace": sheet["pace"],
            "recent": recent_activity([obj.pk], period, pace)[obj.pk],
        }

    def extra_detail(self, obj):
        account = getattr(obj, "user_profile", None)
        if account is None:
            text = "Sin acceso. Se puede crear desde «Editar»."
        else:
            text = f"Ingresa como «{account.user.get_username()}». Su perfil y su contraseña se cambian en Control de usuarios."
        return [("Acceso al sistema", Cell(text=text))]

    def after_save(self, request, obj, form, creating):
        if "username" not in form.fields or not form.wants_access():
            return
        data = form.cleaned_data
        first, last = split_person_name(obj.name)
        user = User(username=data["username"], first_name=first, last_name=last, email=data["email"], is_active=True)
        user.set_password(data["password1"])
        user.save()
        user.groups.set(data["groups"])
        UserProfile.objects.update_or_create(
            user=user, defaults={"officer": obj, "status": UserProfile.Status.ACTIVE}
        )
        log_event(
            request.user,
            "Acceso creado junto con el funcionario" if creating else "Acceso creado para un funcionario existente",
            user,
            new=f"usuario={user.username}, funcionario={obj.name}, perfiles={roles_text(User.objects.get(pk=user.pk))}",
        )
        messages.info(request, f"También quedó creado el acceso «{user.username}» para {obj.name}.")


@registry.register
class PositionCrud(Crud):
    model = Position
    slug = "cargos"
    icon = "bi-person-badge"
    deletable = True
    state_filter = True
    description = "Cargos con su período de vigencia."
    list_display = (Col("name", "Nombre", link=True), "valid_from", "valid_until")
    search_fields = ("name",)
    form_fields = ("name", "valid_from", "valid_until")
    rules = {"name": "label"}
    form_base = PositionForm
    unique_names = (("name", "valid_from"),)
    related = (Related("items-de-cargo", "position", "Ítems del cargo"),)


@registry.register
class PositionItemCrud(Crud):
    model = PositionItem
    slug = "items-de-cargo"
    icon = "bi-diagram-3"
    description = "Ponderación de cada ítem para cada cargo, con bonificaciones y penalizaciones."
    list_display = (
        Col("position", "Cargo", link=True),
        "item",
        "kind",
        "weight",
        "max_cap",
        "valid_from",
        "valid_until",
    )
    search_fields = ("position__name", "item__name")
    list_filters = ("position", "kind")
    select_related = ("position", "item")
    form_fields = ("position", "item", "kind", "weight", "max_cap", "valid_from", "valid_until")
    form_base = PositionItemForm
    bounds = {"weight": {"min": "0.01", "max": "100"}, "max_cap": {"min": "0.01"}}
    help_texts = {"max_cap": "Obligatorio en bonificaciones y penalizaciones."}


@registry.register
class ServiceCrud(Crud):
    model = Service
    slug = "servicios"
    icon = "bi-card-checklist"
    deletable = True
    list_title = "Catálogo de servicios"
    description = "Servicios municipales que se pueden asociar a una actividad."
    list_display = (Col("name", "Nombre", link=True), "status")
    search_fields = ("name",)
    list_filters = ("status",)
    form_fields = ("name", "status")
    rules = {"name": "label"}
    unique_names = ("name",)


ITEM_STATES = {"active": "Activo", "inactive": "Inactivo"}


def item_state(item):
    return "active" if item.deleted_at is None else "inactive"


def item_class(item):
    return "Sub atención" if item.parent_item_id else "Tipo de atención"


class ItemRules:

    def archive_blockers(self, obj):
        reasons = []
        subs = obj.sub_items.filter(deleted_at__isnull=True).count()
        if subs:
            reasons.append(f"Tiene {count_text(subs, 'sub atención activa', 'sub atenciones activas')}.")
        goals = Goal.objects.filter(item=obj, deleted_at__isnull=True).count()
        if goals:
            reasons.append(f"Tiene {count_text(goals, 'meta activa', 'metas activas')}.")
        position_items = PositionItem.objects.filter(item=obj, deleted_at__isnull=True).count()
        if position_items:
            reasons.append(f"Está en {count_text(position_items, 'ítem de cargo', 'ítems de cargo')}.")
        if reasons:
            reasons.append("Archívalas o retíralas antes de archivar este ítem.")
        return reasons

    def restore_blockers(self, obj):
        parent = obj.parent_item
        if parent is not None and parent.deleted_at is not None:
            return [f"Su tipo de atención «{parent.name}» está archivado: restáuralo primero."]
        return []

    def validate_form(self, form, cleaned):
        if "parent_item" not in form.fields or form.has_error("parent_item"):
            return
        instance = form.instance
        parent = cleaned.get("parent_item")
        if parent is not None:
            if instance.pk and parent.pk == instance.pk:
                form.add_error("parent_item", "Un ítem no puede ser su propio padre.")
                return
            if parent.parent_item_id is not None:
                form.add_error(
                    "parent_item",
                    "El padre tiene que ser un tipo de atención (un ítem sin padre), no otra sub atención.",
                )
                return
        if not instance.pk:
            return
        changes_parent = (parent.pk if parent is not None else None) != instance.parent_item_id
        if not changes_parent:
            return
        if parent is not None and instance.parent_item_id is None and instance.sub_items.exists():
            form.add_error(
                "parent_item",
                "Este tipo de atención tiene sub atenciones: no puede pasar a ser sub atención de otro tipo.",
            )
            return
        used = instance.activities.count()
        if used:
            form.add_error(
                "parent_item",
                f"Este ítem ya tiene {count_text(used, 'atención registrada', 'atenciones registradas')}: "
                "cambiarle el tipo alteraría su historial.",
            )


class ItemColumns:

    gender = "m"
    state_filter = True
    computed = {"state": item_state, "item_class": item_class}
    computed_choices = {"state": ITEM_STATES}
    search_fields = ("name", "description", "parent_item__name")
    select_related = ("parent_item",)
    unique_names = (("name", "parent_item"),)
    rules = {"name": "label", "description": "label"}
    form_fields = ("name", "description", "parent_item", "calculation_type", "scores")
    full_width = ("description",)
    help_texts = {
        "name": "Se distingue de los demás aunque cambien las mayúsculas.",
        "description": "Qué mide o qué atiende. Es opcional.",
    }

    def extra_detail(self, obj):
        state = item_state(obj)
        tone, icon = ui.tone_for(state)
        pairs = [
            ("Clase", Cell(text=item_class(obj))),
            ("Estado", Cell(kind="badge", text=ITEM_STATES[state], tone=tone, icon=icon)),
        ]
        if obj.parent_item_id is None:
            total = obj.sub_items.filter(deleted_at__isnull=True).count()
            pairs.append(("Sub atenciones activas", Cell(kind="number", text=ui.fmt_number(total))))
        return pairs


@registry.register
class ItemCrud(ItemRules, ItemColumns, Crud):
    model = Item
    slug = "items"
    icon = "bi-tags"
    title = "Ítem"
    title_plural = "Ítems"
    list_title = "Ítems y metas"
    description = "Todos los ítems que se miden en las metas: tipos de atención y sus sub atenciones."
    search_fields = ("name", "description")
    code_prefix = "IT"
    code_digits = 3
    list_display = (
        Col(CODE_COLUMN),
        Col("name", "Nombre", link=True),
        "description",
        Col("item_class", "Clase", sort=False),
        Col("parent_item", "Tipo asociado", sort="parent_item__name"),
        "calculation_type",
        Col("scores", "Otorga punto", kind="bool"),
        Col("state", "Estado", kind="badge", sort=False),
    )
    list_filters = ("parent_item", "calculation_type", "scores")
    form_base = ItemForm
    labels = {"parent_item": "Ítem padre (tipo de atención)"}
    help_texts = {
        "name": "Se distingue de los demás aunque cambien las mayúsculas.",
        "description": "Qué mide o qué atiende. Es opcional.",
        "parent_item": "Déjalo vacío si es un tipo de atención; elige un tipo si es una sub atención.",
    }
    related = (
        Related("items", "parent_item", "Sub atenciones", columns=(CODE_COLUMN, "name", "calculation_type", "state")),
        Related("metas", "item", "Metas del ítem"),
    )

    def filter_choices(self, request, name, model_field):
        if name == "parent_item":
            types = Item.objects.filter(parent_item__isnull=True, deleted_at__isnull=True).order_by("name")
            return [(item.pk, item.name) for item in types]
        return None


@registry.register
class AttentionTypeCrud(ItemRules, ItemColumns, Crud):

    model = Item
    slug = "tipos-de-atencion"
    icon = "bi-diagram-2"
    title = "Tipo de Atención"
    title_plural = "Tipos de Atención"
    list_title = "Tipos de Atención"
    description = "Clases de atención que se ofrecen a los vecinos. Cada una puede tener sus sub atenciones."
    code_prefix = "TA"
    code_digits = 3
    list_display = (
        Col(CODE_COLUMN),
        Col("name", "Nombre", link=True),
        "description",
        "calculation_type",
        Col("sub_total", "Sub atenciones activas", kind="number", sort=False),
        Col("scores", "Otorga punto", kind="bool"),
        Col("state", "Estado", kind="badge", sort=False),
    )
    computed = {**ItemColumns.computed, "sub_total": lambda item: item.sub_total}
    search_fields = ("name", "description")
    list_filters = ("calculation_type", "scores")
    select_related = ()
    form_base = ItemForm
    form_fields = ("name", "description", "calculation_type", "scores")
    help_texts = {
        "name": "Se distingue de los demás tipos aunque cambien las mayúsculas.",
        "description": "Qué atiende este tipo de atención. Es opcional.",
    }
    related = (
        Related("sub-atenciones", "parent_item", "Sub atenciones", columns=(CODE_COLUMN, "name", "calculation_type", "state")),
    )

    def get_queryset(self, request, include_archived=False):
        qs = super().get_queryset(request, include_archived).filter(parent_item__isnull=True)
        return qs.annotate(sub_total=Count("sub_items", filter=Q(sub_items__deleted_at__isnull=True)))


@registry.register
class SubAttentionCrud(ItemRules, ItemColumns, Crud):

    model = Item
    slug = "sub-atenciones"
    icon = "bi-diagram-3"
    title = "Sub Atención"
    title_plural = "Sub Atenciones"
    list_title = "Sub Atención"
    description = "Atenciones concretas de cada tipo. Cada una pertenece a un Tipo de Atención."
    gender = "f"
    code_prefix = "SA"
    code_digits = 3
    list_display = (
        Col(CODE_COLUMN),
        Col("name", "Nombre", link=True),
        Col("parent_item", "Tipo de Atención asociado", sort="parent_item__name"),
        "calculation_type",
        Col("scores", "Otorga punto", kind="bool"),
        Col("state", "Estado", kind="badge", sort=False),
    )
    list_filters = ("parent_item", "calculation_type", "scores")
    form_base = SubAttentionForm
    form_fields = ("name", "parent_item", "calculation_type", "scores")
    detail_exclude = ("description",)
    search_fields = ("name", "parent_item__name")
    labels = {"parent_item": "Tipo de Atención asociado"}
    help_texts = {
        "name": "Se distingue de las demás sub atenciones del mismo tipo aunque cambien las mayúsculas.",
        "parent_item": "Solo se ofrecen los tipos de atención activos.",
    }

    def get_queryset(self, request, include_archived=False):
        return super().get_queryset(request, include_archived).filter(parent_item__isnull=False)

    def filter_choices(self, request, name, model_field):
        if name == "parent_item":
            types = Item.objects.filter(parent_item__isnull=True, deleted_at__isnull=True).order_by("name")
            return [(item.pk, item.name) for item in types]
        return None


@registry.register
class ManagementTypeCrud(Crud):
    model = ManagementType
    slug = "tipos-de-gestion"
    icon = "bi-signpost-split"
    deletable = True
    state_filter = True
    description = "Tipos de gestión que se usan en el seguimiento de una actividad."
    list_display = (Col("name", "Nombre", link=True),)
    search_fields = ("name",)
    form_fields = ("name",)
    rules = {"name": "label"}
    unique_names = ("name",)


@registry.register
class CommunityOrganizationCrud(Crud):
    model = CommunityOrganization
    slug = "organizaciones"
    icon = "bi-houses"
    gender = "f"
    deletable = True
    state_filter = True
    description = "Juntas de vecinos y otras organizaciones comunitarias. Es un catálogo compartido entre delegaciones."
    list_display = (
        Col("name", "Nombre", link=True),
        "territory",
        "active_members",
        "registry_number",
        "verified",
    )
    search_fields = ("name", "legal_address", "territory_text")
    list_filters = ("territory", "verified")
    select_related = ("territory",)
    form_fields = (
        "name",
        "legal_address",
        "territory",
        "active_members",
        "constitution_date",
        "registry_number",
        "registration_date",
        "directory_number",
        "verified",
    )
    full_width = ("name", "legal_address")
    rules = {"name": "label", "legal_address": "label"}
    bounds = {"active_members": {"min": "0"}, "registry_number": {"min": "1"}, "directory_number": {"min": "0"}}
    related = (Related("directivas", "organization", "Directiva"),)


def leader_role_text(leader):
    return leader.role_text()


@registry.register
class OrganizationLeaderCrud(Crud):
    model = OrganizationLeader
    slug = "directivas"
    icon = "bi-person-badge"
    deletable = True
    state_filter = True
    description = (
        "Presidente, secretario, tesorero y demás integrantes de la directiva de cada organización. "
        "Son registros propios: no se crean como beneficiarios."
    )
    list_display = (
        Col("name", "Nombre", link=True),
        "rut",
        Col("role_text", "Cargo", sort=False),
        "organization",
        "email",
    )
    computed = {"role_text": leader_role_text}
    search_fields = ("name", "rut", "email", "organization__name")
    list_filters = ("role", "organization")
    select_related = ("organization",)
    form_base = LeaderForm
    form_fields = ("organization", "role", "role_detail", "name", "rut", "email")
    rules = {"name": "person_name", "rut": "rut", "email": "email", "role_detail": "label"}
    help_texts = {"rut": "Con o sin puntos; se guarda como 12345678-5."}

    def restore_blockers(self, obj):
        if obj.organization.deleted_at is not None:
            return [f"Su organización «{obj.organization.name}» está archivada: restáurala primero."]
        others = OrganizationLeader.objects.filter(organization=obj.organization, deleted_at__isnull=True).exclude(pk=obj.pk)
        reasons = []
        if others.filter(rut=obj.rut).exists():
            reasons.append("Esa persona ya está en la directiva de la organización con otro registro.")
        if obj.role in OrganizationLeader.SINGLE_ROLES and others.filter(role=obj.role).exists():
            reasons.append(f"La organización ya tiene {OrganizationLeader.Role(obj.role).label.lower()}.")
        return reasons

    def validate_form(self, form, cleaned):
        role = cleaned.get("role")
        if role != OrganizationLeader.Role.OTHER:
            cleaned["role_detail"] = ""
        elif "role_detail" in form.fields and not form.has_error("role_detail") and not cleaned.get("role_detail"):
            form.add_error("role_detail", "Escribe cuál es el cargo.")
        organization = cleaned.get("organization")
        if organization is None or form.has_error("organization"):
            return
        others = OrganizationLeader.objects.filter(organization=organization, deleted_at__isnull=True)
        if form.instance.pk:
            others = others.exclude(pk=form.instance.pk)
        rut = cleaned.get("rut")
        if rut and not form.has_error("rut") and others.filter(rut=rut).exists():
            form.add_error("rut", "Esa persona ya está en la directiva de esta organización.")
        if role in OrganizationLeader.SINGLE_ROLES and not form.has_error("role"):
            holder = others.filter(role=role).first()
            if holder is not None:
                label = OrganizationLeader.Role(role).label.lower()
                form.add_error(
                    "role",
                    f"Esta organización ya tiene {label}: {holder.name}. Cámbiale el cargo o archívalo antes.",
                )


@registry.register
class BeneficiaryCrud(Crud):
    model = Beneficiary
    slug = "beneficiarios"
    icon = "bi-person-lines-fill"
    deletable = True
    state_filter = True
    description = "Personas atendidas. Es un catálogo compartido entre delegaciones."
    list_display = (Col("name", "Nombre", link=True), "rut", "phone", "address")
    search_fields = ("name", "rut", "address")
    form_fields = ("rut", "name", "phone", "address")
    rules = {"rut": "rut", "name": "person_name", "phone": "phone", "address": "label"}
    help_texts = {"rut": "Con o sin puntos; se guarda como 12345678-5."}
    related = (Related("actividades", "beneficiary", "Actividades"),)


def roles_text(user):
    names = sorted((group.name for group in user.groups.all()), key=sort_key)
    if user.is_superuser:
        names.insert(0, SUPERUSER_ROLE)
    return ", ".join(names)


def profile_of(user):
    return getattr(user, "profile", None)


def officer_of(user):
    profile = getattr(user, "profile", None)
    return profile.officer if profile is not None else None


def full_name_text(user):
    officer = officer_of(user)
    return user.get_full_name() or (officer.name if officer else "")


def sees_everything(user):
    return user.is_superuser or any(group_is_global(group) for group in user.groups.all())


def delegation_text(user):
    officer = officer_of(user)
    extras = listed_extra_delegations(user)
    if officer is not None:
        text = str(officer.delegation)
        others = [delegation for delegation in extras if delegation.pk != officer.delegation_id]
        return f"{text} y {len(others)} más" if others else text
    if sees_everything(user):
        return "Todas las delegaciones"
    return ", ".join(delegation.name for delegation in extras)


def authorized_text(user):
    if sees_everything(user):
        return "Todas las delegaciones"
    found = {delegation.pk: delegation for delegation in listed_extra_delegations(user)}
    officer = officer_of(user)
    if officer is not None:
        found[officer.delegation_id] = officer.delegation
    code_of = registry.get("delegaciones").code_of
    return ", ".join(f"{code_of(found[key])} · {found[key].name}" for key in sorted(found))


@registry.register
class UserCrud(Crud):

    model = User
    slug = "usuarios"
    icon = "bi-people"
    title = "Usuario"
    title_plural = "Usuarios"
    list_title = "Control de usuarios"
    description = "Cuentas del sistema con su perfil y su delegación."
    archive_lookup = "profile__deleted_at"
    archived_label = "Usuarios eliminados"
    archived_banner = (
        "Este usuario está eliminado: no puede ingresar ni aparece en el listado de usuarios. "
        "Solo el Super Usuario lo ve aquí y puede restaurarlo."
    )
    archive_note = (
        "El usuario deja de aparecer en el listado y no podrá ingresar. No se borra de la base de datos: pasa a "
        "«Usuarios eliminados» y el Super Usuario puede restaurarlo cuando haga falta. Su historial se conserva."
    )
    ordering = ("-date_joined", "-pk")
    list_display = (
        Col("username", "Usuario", link=True),
        Col("full_name", "Nombre", sort="first_name"),
        "email",
        Col("roles", "Perfiles", sort=False),
        Col("delegation_name", "Delegación", sort="profile__officer__delegation__name"),
        "is_active",
        "last_login",
    )
    computed = {"roles": roles_text, "full_name": full_name_text, "delegation_name": delegation_text}
    select_related = ("profile", "profile__officer", "profile__officer__delegation", "profile__beneficiary")
    prefetch_related = ("groups__role_profile", "role_delegations__delegation")
    search_fields = (
        "username",
        "first_name",
        "last_name",
        "email",
        "groups__name",
        "profile__officer__name",
        "profile__officer__delegation__name",
    )
    search_distinct = True
    list_filters = ("is_active", "groups")
    form_base = UserForm
    form_fields = (
        "username",
        "first_name",
        "last_name",
        "email",
        "groups",
        "is_active",
        "is_staff",
        "is_superuser",
    )
    detail_exclude = ("password",)
    labels = {
        "username": "Usuario",
        "first_name": "Nombre",
        "last_name": "Apellido",
        "email": "Correo",
        "groups": "Perfil",
        "is_active": "Activo",
        "is_staff": "Acceso al panel de administración",
        "is_superuser": "Super Usuario",
        "last_login": "Último ingreso",
        "date_joined": "Cuenta creada el",
    }
    help_texts = {
        "username": "Con este nombre ingresa al sistema. Letras, números y . _ @ + -",
        "email": "Con este correo la persona recupera su contraseña. No puede repetirse entre usuarios.",
        "first_name": "Déjalo en blanco si eliges un funcionario: se usa el nombre del funcionario.",
        "groups": "El perfil define qué puede abrir y hacer el usuario.",
        "is_active": "Desmárcala para impedir que ingrese, sin perder su historial.",
        "is_staff": "Permite entrar al panel de administración de Django (/admin/).",
        "is_superuser": "Acceso completo a todo el sistema. Úsalo solo en cuentas técnicas.",
    }
    rules = {
        "username": "username",
        "email": "email",
        "first_name": "person_name",
        "last_name": "person_name",
        "password1": "password",
    }

    def can_archive(self, user):
        return user.is_superuser and super().can_archive(user)

    def can_see_archived(self, request):
        return request.user.is_superuser

    def get_queryset(self, request, include_archived=False):
        return super().get_queryset(request, include_archived=include_archived and request.user.is_superuser)

    def archived_at(self, obj):
        profile = getattr(obj, "profile", None)
        return profile.deleted_at if profile else None

    def set_archived(self, obj, when):
        profile, _ = UserProfile.objects.get_or_create(user=obj)
        profile.deleted_at = when
        fields = ["deleted_at", "updated_at"]
        if when is not None:
            profile.status = UserProfile.Status.INACTIVE
            fields.append("status")
            if obj.is_active:
                obj.is_active = False
                obj.save(update_fields=["is_active"])
        profile.save(update_fields=fields)
        obj.profile = profile

    def archive_guard(self, request, obj):
        if obj.pk == request.user.pk:
            return ["No puedes eliminar tu propia cuenta."]
        return []

    def say(self, kind, obj):
        name = obj.get_username()
        if kind == "archived":
            return f"Usuario «{name}» eliminado. Lo encuentras en Usuarios eliminados."
        if kind == "restored":
            return (
                f"Usuario «{name}» restaurado. Sigue inactivo: actívalo en Editar cuando deba volver a ingresar."
            )
        return super().say(kind, obj)

    def extra_detail(self, obj):
        officer = officer_of(obj)
        photo = photo_url_of(obj)
        return [
            ("Foto de perfil", Cell(kind="avatar", text="Foto de perfil", url=photo) if photo else Cell()),
            ("Perfiles", Cell(text=roles_text(obj))),
            ("Funcionario", Cell(text=str(officer) if officer else "")),
            ("Beneficiario", Cell(text=str(profile_of(obj).beneficiary) if profile_of(obj) and profile_of(obj).beneficiary_id else "")),
            ("Delegación", Cell(text=str(officer.delegation) if officer else "")),
            ("Delegaciones autorizadas", Cell(text=authorized_text(obj))),
            ("Cargo", Cell(text=str(officer.position) if officer else "")),
        ]

    def record_meta(self, obj):
        text = f"Cuenta creada el {ui.fmt_datetime(obj.date_joined)}."
        text += f" Último ingreso el {ui.fmt_datetime(obj.last_login)}." if obj.last_login else " Todavía no ha ingresado."
        if self.archived_at(obj):
            text += f" Eliminado el {ui.fmt_datetime(self.archived_at(obj))}."
        return text

    def prepare_object(self, request, obj, creating, form):
        if not creating:
            profile = getattr(obj, "profile", None)
            form.before_roles = roles_text(obj)
            form.before_officer = str(profile.officer) if profile and profile.officer else ""
            form.before_beneficiary = str(profile.beneficiary) if profile and profile.beneficiary else ""
            form.before_delegations = stored_delegation_ids(obj)
        password = form.cleaned_data.get("password1")
        if password:
            obj.set_password(password)

    def after_save(self, request, obj, form, creating):
        officer = form.cleaned_data.get("officer")
        beneficiary = form.cleaned_data.get("beneficiary")
        UserProfile.objects.update_or_create(
            user=obj,
            defaults={
                "officer": officer,
                "beneficiary": beneficiary,
                "status": UserProfile.Status.ACTIVE if obj.is_active else UserProfile.Status.INACTIVE,
            },
        )
        obj = User.objects.get(pk=obj.pk)
        self.save_photo(request, obj, form)
        self.save_extra_delegations(request, obj, form, creating)
        if not creating:
            roles, officer_name = roles_text(obj), str(officer) if officer else ""
            beneficiary_name = str(beneficiary) if beneficiary else ""
            if (roles, officer_name, beneficiary_name) != (form.before_roles, form.before_officer, form.before_beneficiary):
                log_event(
                    request.user,
                    "Perfil o funcionario modificado",
                    obj,
                    previous=(
                        f"Perfiles: {form.before_roles or '(ninguno)'}; Funcionario: {form.before_officer or '(ninguno)'}"
                        + (f"; Beneficiario: {form.before_beneficiary}" if form.before_beneficiary else "")
                    ),
                    new=(
                        f"Perfiles: {roles or '(ninguno)'}; Funcionario: {officer_name or '(ninguno)'}"
                        + (f"; Beneficiario: {beneficiary_name}" if beneficiary_name else "")
                    ),
                )
            if form.cleaned_data.get("password1"):
                log_event(request.user, "Contraseña restablecida", obj)

    def save_photo(self, request, obj, form):
        """La foto la puede cambiar o quitar quien edita al usuario (la persona también la cambia en Mi perfil)."""
        uploaded = form.cleaned_data.get("photo")
        if uploaded:
            change_photo(request.user, obj, uploaded)
        elif form.cleaned_data.get("remove_photo"):
            remove_photo(request.user, obj)

    def save_extra_delegations(self, request, obj, form, creating):
        if "extra_delegations" not in form.cleaned_data:
            return
        selected = list(form.cleaned_data["extra_delegations"] or [])
        before = set() if creating else form.before_delegations
        sync_extra_delegations(obj, selected)
        now = {delegation.pk for delegation in selected}
        if now == before:
            return
        names = {delegation.pk: delegation for delegation in Delegation.objects.filter(pk__in=now | before)}
        code_of = registry.get("delegaciones").code_of

        def text(ids):
            return ", ".join(f"{code_of(names[key])} · {names[key].name}" for key in sorted(ids)) or "(ninguna)"

        log_event(
            request.user,
            "Delegaciones autorizadas modificadas",
            obj,
            previous=f"Delegaciones adicionales: {text(before)}",
            new=f"Delegaciones adicionales: {text(now)}",
        )


ROLE_SCOPES = dict(RoleProfile.Scope.choices)
ROLE_STATES = dict(RoleProfile.Status.choices)


def role_scope(group):
    return ROLE_SCOPES[role_details(group).scope]


def role_description(group):
    return role_details(group).description


def role_status(group):
    return role_details(group).status


@registry.register
class RoleCrud(Crud):

    model = Group
    slug = "roles"
    icon = "bi-shield-check"
    title = "Rol"
    title_plural = "Roles"
    list_title = "Roles y permisos"
    description = "Perfiles del sistema y lo que puede hacer cada uno: ver, crear, editar y eliminar por módulo."
    code_prefix = "ROL"
    code_digits = 2
    archivable = False
    deletable = True
    ordering = ("name",)
    list_display = (
        Col(CODE_COLUMN),
        Col("name", "Rol", link=True),
        Col("scope", "Alcance", sort="role_profile__scope"),
        Col("status", "Estado", kind="badge", sort="role_profile__status"),
        Col("user_total", "Usuarios", kind="number", sort="user_total"),
        Col("permission_total", "Permisos", kind="number", sort="permission_total"),
    )
    computed = {
        "scope": role_scope,
        "status": role_status,
        "user_total": lambda group: group.user_total,
        "permission_total": lambda group: group.permission_total,
    }
    computed_choices = {"status": ROLE_STATES}
    search_fields = ("name", "role_profile__description")
    list_filters = ("role_profile__status", "role_profile__scope")
    select_related = ("role_profile",)
    form_base = RoleForm
    form_fields = ("name", "permissions")
    full_width = ("description", "permissions")
    unique_names = ("name",)
    rules = {"name": "label", "description": "label"}
    labels = {"name": "Nombre del rol", "permissions": "Permisos"}
    help_texts = {"name": "Se distingue de los demás roles aunque cambien las mayúsculas."}
    detail_panel = "core/crud/role_permissions.html"
    related = (
        Related(
            "usuarios",
            "groups",
            "Usuarios con este rol",
            columns=("username", "full_name", "delegation_name", "is_active"),
        ),
    )

    def get_queryset(self, request, include_archived=False):
        qs = super().get_queryset(request, include_archived)
        return qs.annotate(
            user_total=Count("user", distinct=True),
            permission_total=Count("permissions", distinct=True),
        )

    def duplicate_message(self, label, archived):
        return "Ya existe un rol con ese nombre, aunque cambien las mayúsculas o los espacios."

    def delete_blockers(self, obj):
        if obj.name in SYSTEM_GROUPS:
            return ["Es un perfil del sistema: las reglas de acceso lo buscan por su nombre y no se puede eliminar."]
        users = obj.user_set.count()
        if users:
            return [
                f"Lo tienen asignado {count_text(users, 'usuario', 'usuarios')}. "
                "Cámbiales el rol desde Control de usuarios antes de eliminarlo."
            ]
        return []

    def extra_detail(self, obj):
        details = role_details(obj)
        tone, icon = ui.tone_for(details.status)
        return [
            ("Descripción", Cell(text=details.description)),
            ("Alcance autorizado", Cell(text=ROLE_SCOPES[details.scope])),
            ("Estado", Cell(kind="badge", text=ROLE_STATES[details.status], tone=tone, icon=icon)),
            ("Tipo de rol", Cell(text="Perfil del sistema" if obj.name in SYSTEM_GROUPS else "Rol propio")),
        ]

    def record_meta(self, obj):
        return "Los roles no se archivan: se eliminan solo si ningún usuario los tiene."

    def panel_context(self, request, obj):
        granted = {}
        for permission in obj.permissions.select_related("content_type"):
            key, action = permission_key(permission)
            granted.setdefault(key, set()).add(action)
        sections = []
        for title, modules in PERMISSION_MODULES:
            rows = []
            for label, key in modules:
                actions = granted.get(key, set())
                rows.append(
                    {
                        "label": label,
                        "cells": [
                            {"label": text, "granted": prefix in actions} for prefix, text in ACTIONS
                        ],
                    }
                )
            sections.append({"title": title, "rows": rows})
        return {
            "actions": [text for _prefix, text in ACTIONS],
            "sections": sections,
            "total": sum(len(actions) for actions in granted.values()),
        }

    def prepare_object(self, request, obj, creating, form):
        form.before_permissions = set() if creating else {permission_text(p) for p in obj.permissions.select_related("content_type")}
        form.before_details = None if creating else role_details(obj)

    @staticmethod
    def details_text(details):
        return (
            f"Descripción: {details.description or '(vacía)'}; Alcance: {ROLE_SCOPES[details.scope]}; "
            f"Estado: {ROLE_STATES[details.status]}"
        )

    def after_save(self, request, obj, form, creating):
        data = form.cleaned_data
        profile, _created = RoleProfile.objects.update_or_create(
            group=obj,
            defaults={"description": data["description"], "scope": data["scope"], "status": data["status"]},
        )
        before = form.before_details
        now = RoleDetails(profile.description, profile.scope, profile.status)
        if before is not None and before != now:
            log_event(
                request.user,
                "Datos del rol modificados",
                obj,
                previous=self.details_text(before),
                new=self.details_text(now),
            )
        after = {permission_text(p) for p in obj.permissions.select_related("content_type")}
        before = form.before_permissions
        if after != before:
            added, removed = sorted(after - before), sorted(before - after)
            log_event(
                request.user,
                "Permisos del rol modificados",
                obj,
                previous="Quitados: " + ("; ".join(removed) if removed else "(ninguno)"),
                new="Agregados: " + ("; ".join(added) if added else "(ninguno)"),
            )


@registry.register
class AuditLogCrud(Crud):
    model = AuditLog
    slug = "auditoria"
    icon = "bi-shield-check"
    gender = "f"
    title = "Registro de auditoría"
    title_plural = "Registros de auditoría"
    list_title = "Auditoría"
    description = "Eventos que quedaron registrados en el sistema. Solo consulta."
    allow_add = False
    allow_change = False
    archivable = False
    list_display = (
        "date",
        Col("event", "Evento", link=True),
        "affected_entity",
        Col("record_id", "Registro N°", kind="text"),
        "user",
    )
    search_fields = ("event", "affected_entity", "user__username")
    select_related = ("user",)
