from pathlib import Path

from django.contrib import messages
from django.contrib.auth.models import Group, User
from django.db.models import Count, Q
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify

from accounts.delegations import listed_extra_delegations, stored_delegation_ids, sync_extra_delegations
from accounts.models import RoleDetails, RoleProfile, UserProfile, group_is_global, role_details
from core.access import active_delegation, default_delegation, request_delegation, request_officer
from core import ui, uploads
from core.audit import log_event
from core.crud import CODE_COLUMN, Cell, Col, Crud, Related, is_id, registry
from core.forms import (
    ActivityEditForm,
    ActivityIntakeForm,
    AdjustmentForm,
    CommitmentForm,
    DelegationForm,
    EvidenceForm,
    FollowupForm,
    GoalForm,
    IndicatorForm,
    ItemForm,
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
from operations.models import Activity, Commitment, Followup, ManagementType
from organization.models import (
    Beneficiary,
    Delegation,
    Item,
    Officer,
    Position,
    PositionItem,
    Service,
    Territory,
)
from planning.models import Adjustment, Goal, Indicator, Period


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
    )
    computed = {"attention_type": attention_type_name, "sub_attention": sub_attention_name}
    search_fields = (
        "contact_name",
        "phone",
        "request_description",
        "beneficiary__name",
        "beneficiary__rut",
    )
    list_filters = ("delegation", "status", "requires_visit", "added_to_pipeline", "item")
    select_related = ("delegation", "item", "item__parent_item", "author_officer", "beneficiary", "service")
    form_fields = (
        "date",
        "item",
        "service",
        "beneficiary",
        "contact_name",
        "phone",
        "request_description",
        "action_taken",
        "status",
        "requires_visit",
        "added_to_pipeline",
        "delegation",
        "author_officer",
    )
    create_form_base = ActivityIntakeForm
    create_fields = (
        "requester",
        "phone",
        "attention_type",
        "item",
        "service",
        "request_description",
        "action_taken",
        "requires_visit",
        "added_to_pipeline",
        "delegation",
        "author_officer",
    )
    create_heading = "Registrar atención"
    create_save_label = "Registrar atención"
    full_width = ("requester", "request_description", "action_taken")
    help_texts = {
        "added_to_pipeline": "Marca la actividad para seguirla en el tubo de trabajo.",
    }
    rules = {"phone": "phone", "requester": "label", "contact_name": "label"}
    form_base = ActivityEditForm
    delegation_lookup = "delegation"
    related = (
        Related("gestiones", "activity", "Gestiones de atención"),
        Related("evidencias", "activity", "Evidencias"),
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
    bounds = {"sequence_number": {"min": "1", "max": "3"}}
    form_base = FollowupForm
    delegation_lookup = "activity__delegation"

    def initial_values(self, request):
        initial = {"date": timezone.localdate()}
        activity = visible_activity(request, request.GET.get("activity", ""))
        if activity is not None:
            used = set(activity.followups.values_list("sequence_number", flat=True))
            free = [n for n in (1, 2, 3) if n not in used]
            if free:
                initial["sequence_number"] = free[0]
        return initial


@registry.register
class CommitmentCrud(Crud):
    model = Commitment
    slug = "agenda"
    icon = "bi-calendar-check"
    title = "Compromiso"
    title_plural = "Compromisos"
    list_title = "Agenda colectiva"
    description = "Compromisos con vecinos, organizaciones y la propia municipalidad."
    list_display = (
        Col("requester", "Solicitante", link=True),
        "territory",
        "responsible_officer",
        "due_date",
        "status",
        "requester_type",
    )
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

    def initial_values(self, request):
        initial = {"request_date": timezone.localdate()}
        initial.update(own_officer_defaults(request, "responsible_officer"))
        delegation = default_delegation(request)
        if delegation is not None:
            initial["delegation"] = delegation.pk
        return initial


def suggest_evidence_code(request, activity):
    delegation = activity.delegation if activity is not None else default_delegation(request)
    if delegation is None:
        return ""
    name = delegation.name
    if name.lower().startswith("delegación "):
        name = name[len("delegación "):]
    prefix = f"EVD-{slugify(name).upper()}-"
    numbers = [
        int(code[len(prefix):])
        for code in Evidence._default_manager.filter(unique_code__startswith=prefix)
        .values_list("unique_code", flat=True)
        if is_id(code[len(prefix):])
    ]
    return f"{prefix}{max(numbers, default=0) + 1:04d}"


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
        "unique_code": "Identifica la evidencia y no se puede cambiar después de crearla.",
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
        initial["unique_code"] = suggest_evidence_code(request, activity)
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
    }
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
    description = "Territorios de cada delegación."
    list_display = ("name", "delegation")
    search_fields = ("name", "delegation__name")
    list_filters = ("delegation",)
    select_related = ("delegation",)
    form_fields = ("name", "delegation")
    rules = {"name": "label"}
    unique_names = (("name", "delegation"),)
    delegation_lookup = "delegation"
    related = (Related("agenda", "territory", "Compromisos"),)


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
    form_fields = ("name", "description", "parent_item", "calculation_type")
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
    code_prefix = "IT"
    code_digits = 3
    list_display = (
        Col(CODE_COLUMN),
        Col("name", "Nombre", link=True),
        "description",
        Col("item_class", "Clase", sort=False),
        Col("parent_item", "Tipo asociado", sort="parent_item__name"),
        "calculation_type",
        Col("state", "Estado", kind="badge", sort=False),
    )
    list_filters = ("parent_item", "calculation_type")
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
        Col("state", "Estado", kind="badge", sort=False),
    )
    computed = {**ItemColumns.computed, "sub_total": lambda item: item.sub_total}
    search_fields = ("name", "description")
    list_filters = ("calculation_type",)
    select_related = ()
    form_base = ItemForm
    form_fields = ("name", "description", "calculation_type")
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
        Col("state", "Estado", kind="badge", sort=False),
    )
    list_filters = ("parent_item", "calculation_type")
    form_base = SubAttentionForm
    form_fields = ("name", "parent_item", "calculation_type")
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
    description = "Tipos de gestión que se usan en el seguimiento de una actividad."
    list_display = (Col("name", "Nombre", link=True),)
    search_fields = ("name",)
    form_fields = ("name",)
    rules = {"name": "label"}
    unique_names = ("name",)


@registry.register
class BeneficiaryCrud(Crud):
    model = Beneficiary
    slug = "beneficiarios"
    icon = "bi-person-lines-fill"
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
    archivable = False
    ordering = ("username",)
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
    select_related = ("profile", "profile__officer", "profile__officer__delegation")
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

    def extra_detail(self, obj):
        officer = officer_of(obj)
        return [
            ("Perfiles", Cell(text=roles_text(obj))),
            ("Funcionario", Cell(text=str(officer) if officer else "")),
            ("Delegación", Cell(text=str(officer.delegation) if officer else "")),
            ("Delegaciones autorizadas", Cell(text=authorized_text(obj))),
            ("Cargo", Cell(text=str(officer.position) if officer else "")),
        ]

    def record_meta(self, obj):
        text = f"Cuenta creada el {ui.fmt_datetime(obj.date_joined)}."
        if obj.last_login:
            return f"{text} Último ingreso el {ui.fmt_datetime(obj.last_login)}."
        return f"{text} Todavía no ha ingresado."

    def prepare_object(self, request, obj, creating, form):
        if not creating:
            profile = getattr(obj, "profile", None)
            form.before_roles = roles_text(obj)
            form.before_officer = str(profile.officer) if profile and profile.officer else ""
            form.before_delegations = stored_delegation_ids(obj)
        password = form.cleaned_data.get("password1")
        if password:
            obj.set_password(password)

    def after_save(self, request, obj, form, creating):
        officer = form.cleaned_data.get("officer")
        UserProfile.objects.update_or_create(
            user=obj,
            defaults={
                "officer": officer,
                "status": UserProfile.Status.ACTIVE if obj.is_active else UserProfile.Status.INACTIVE,
            },
        )
        obj = User.objects.get(pk=obj.pk)
        self.save_extra_delegations(request, obj, form, creating)
        if not creating:
            roles, officer_name = roles_text(obj), str(officer) if officer else ""
            if (roles, officer_name) != (form.before_roles, form.before_officer):
                log_event(
                    request.user,
                    "Perfil o funcionario modificado",
                    obj,
                    previous=f"Perfiles: {form.before_roles or '(ninguno)'}; Funcionario: {form.before_officer or '(ninguno)'}",
                    new=f"Perfiles: {roles or '(ninguno)'}; Funcionario: {officer_name or '(ninguno)'}",
                )
            if form.cleaned_data.get("password1"):
                log_event(request.user, "Contraseña restablecida", obj)

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
