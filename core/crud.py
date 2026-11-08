import inspect
import re
from dataclasses import dataclass, replace

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import FieldDoesNotExist, ObjectDoesNotExist, PermissionDenied
from django.core.paginator import Paginator
from django.db import IntegrityError, models, transaction
from django.forms import modelform_factory
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import path, reverse
from django.utils import timezone
from django.views import View
from django.views.generic import RedirectView

from core import export, ui
from core.audit import changed_fields, log_event, log_export
from core.access import active_delegation, delegation_id_of, request_delegation
from core.colors import HEX_COLOR
from core.forms import CrudForm
from core.models import AuditLog, BaseModel
from core.search import word_pattern
from websocket.services import notify_crud_change

PAGE_SIZE = 15
PAGE_SIZES = (5, 15, 30)
SESSION_PAGE_SIZE = "page_size"
RELATED_LIMIT = 25
SEARCH_WORDS = 10
CODE_COLUMN = "__code__"
STATE_FILTER = "estado"
STATE_ACTIVE = "activo"
STATE_INACTIVE = "inactivo"
ONLY_ARCHIVED = "solo"
MAX_CODE_NUMBER_DIGITS = 9


def is_id(text):
    return re.fullmatch(r"[0-9]+", str(text)) is not None


def number_in_code(word, prefix):
    if not prefix:
        return None
    found = re.fullmatch(rf"{re.escape(prefix)}0*([0-9]{{1,{MAX_CODE_NUMBER_DIGITS}}})", word.strip(), re.IGNORECASE)
    return int(found.group(1)) if found else None


def version_of(obj):
    stamp = getattr(obj, "updated_at", None)
    return stamp.isoformat() if stamp else ""


class StaleRecord(Exception):
    """El registro cambió mientras se editaba (RF-034, RNF-003)."""


CONFLICT_TEXT = (
    "Otra persona modificó este registro mientras lo editabas{who}. "
    "Revisa los datos y, si quieres conservar los tuyos, vuelve a guardar."
)
DUPLICATE_TEXT = (
    "Otra persona acaba de guardar un dato que choca con el tuyo (por ejemplo, el mismo código o un nombre repetido). "
    "Revisa los datos y vuelve a guardar."
)
MAX_CHANGE_TEXT = 300


def last_change_text(obj):
    """Quién y cuándo hizo el último cambio de un registro, y qué cambió, según la auditoría."""
    entry = (
        AuditLog.objects.filter(affected_entity=obj.__class__.__name__, record_id=obj.pk, deleted_at__isnull=True)
        .select_related("user")
        .order_by("-date", "-pk")
        .first()
    )
    if entry is None:
        return ""
    who = entry.user.get_full_name() or entry.user.get_username()
    text = f": {who} hizo «{entry.event}» el {ui.fmt_datetime(entry.date)}"
    if entry.event == "Registro modificado" and entry.previous_value and entry.new_value:
        before = entry.previous_value.split("; ")
        after = entry.new_value.split("; ")
        pairs = [f"{b.split(': ', 1)[0]}: {b.split(': ', 1)[-1]} → {a.split(': ', 1)[-1]}" for b, a in zip(before, after)]
        detail = "; ".join(pairs)
        if len(detail) > MAX_CHANGE_TEXT:
            detail = detail[: MAX_CHANGE_TEXT - 3] + "..."
        text += f" ({detail})"
    return text


def conflict_message(obj):
    return CONFLICT_TEXT.format(who=last_change_text(obj))


@dataclass
class Cell:

    kind: str = "text"
    text: str = ""
    tone: str = ""
    icon: str = ""
    color: str = ""
    link: bool = False
    url: str = ""
    preview: bool = False
    together: bool = False


@dataclass
class Row:

    obj: object
    cells: list
    detail_url: str
    edit_url: str = ""
    archive_url: str = ""
    restore_url: str = ""
    delete_url: str = ""
    archived: bool = False
    archive_blocked: str = ""
    delete_blocked: str = ""


@dataclass
class Column:

    path: str
    label: str
    kind: str
    sort_key: str = ""
    link: bool = False
    sort_url: str = ""
    sort_dir: str = ""


@dataclass
class FilterSpec:

    name: str
    label: str
    options: list
    selected: str = ""


@dataclass
class Related:

    crud: str
    field: str
    title: str
    columns: tuple = ()


@dataclass
class RelatedBlock:
    title: str
    columns: list
    rows: list
    total: int
    add_url: str = ""
    add_label: str = ""


class Col:

    def __init__(self, path, label=None, sort=None, kind=None, link=False):
        self.path = path
        self.label = label
        self.sort = sort
        self.kind = kind
        self.link = link


def field_for_path(model, path_):
    current = model
    found = None
    for part in path_.split("__"):
        try:
            found = current._meta.get_field(part)
        except FieldDoesNotExist:
            return None
        if found.is_relation:
            current = found.related_model
    return found


def detect_kind(model_field):
    if model_field is None:
        return "text"
    if isinstance(model_field, models.BooleanField):
        return "bool"
    if model_field.choices:
        return "badge"
    if isinstance(model_field, models.DateTimeField):
        return "datetime"
    if isinstance(model_field, models.DateField):
        return "date"
    if isinstance(model_field, (models.DecimalField, models.IntegerField)):
        return "number"
    return "text"


def get_raw(obj, path_):
    if path_ == "__str__":
        return str(obj)
    value = obj
    for part in path_.split("__"):
        if value is None:
            return None
        try:
            value = getattr(value, part)
        except ObjectDoesNotExist:
            return None
        if inspect.ismethod(value):
            value = value()
    return value


class Crud:

    model = None
    slug = ""
    icon = "bi-folder2"

    title = None
    title_plural = None
    list_title = None
    description = ""
    gender = "m"

    list_display = ()
    search_fields = ()
    search_distinct = False
    list_filters = ()
    select_related = ()
    prefetch_related = ()
    ordering = ()
    computed = {}
    computed_choices = {}
    state_filter = False

    code_prefix = ""
    code_digits = 2
    code_label = "Código"

    form_base = CrudForm
    form_fields = ()
    create_fields = None
    create_form_base = None
    create_heading = ""
    create_save_label = "Guardar"
    create_add_another = True
    unique_names = ()
    full_width = ()
    readonly_on_edit = ()
    help_texts = {}
    show_id = False
    rules = {}
    bounds = {}
    labels = {}
    detail_exclude = ()

    delegation_lookup = None
    allow_add = True
    allow_change = True
    archivable = True
    deletable = False
    # Dónde vive la marca de «archivado». Casi todos los modelos la tienen en su propio campo deleted_at;
    # los que no heredan de BaseModel (los usuarios de Django) la guardan en otra tabla relacionada.
    archive_lookup = "deleted_at"
    archived_label = ""
    archived_banner = ""
    archive_note = ""

    related = ()
    detail_panel = ""
    list_redirect = ""

    def __init__(self):
        meta = self.model._meta
        self.title = self.title or ui.initial_capital(meta.verbose_name)
        self.title_plural = self.title_plural or ui.initial_capital(meta.verbose_name_plural)
        self.list_title = self.list_title or self.title_plural
        self.soft_delete = issubclass(self.model, BaseModel) or self.archive_lookup != "deleted_at"
        self.columns = self.resolve_columns(self.list_display)
        self._form_class = None
        self._create_form_class = None

    def label_of(self, model_field, fallback=""):
        if model_field is not None and model_field.name in self.labels:
            return self.labels[model_field.name]
        if model_field is not None:
            return ui.initial_capital(model_field.verbose_name)
        return fallback


    def resolve_columns(self, specs):
        columns = []
        for spec in specs:
            col = spec if isinstance(spec, Col) else Col(spec)
            if col.path == CODE_COLUMN:
                columns.append(
                    Column(
                        path=CODE_COLUMN,
                        label=col.label or self.code_label,
                        kind="code",
                        sort_key="" if col.sort is False else "pk",
                        link=col.link,
                    )
                )
                continue
            found = field_for_path(self.model, col.path)
            if col.label:
                label = col.label
            elif found is not None and "__" not in col.path:
                label = self.label_of(found)
            elif found is not None:
                label = ui.initial_capital(found.verbose_name)
            else:
                label = col.path
            if col.sort is False:
                sort_key = ""
            elif isinstance(col.sort, str):
                sort_key = col.sort
            else:
                sort_key = col.path if found is not None else ""
            columns.append(
                Column(
                    path=col.path,
                    label=label,
                    kind=col.kind or detect_kind(found),
                    sort_key=sort_key,
                    link=col.link,
                )
            )
        if columns and not any(c.link for c in columns):
            columns[0].link = True
        return columns


    def route_name(self, action):
        return f"{self.slug.replace('-', '_')}_{action}"

    def url(self, action, pk=None):
        if action == "list" and self.list_redirect:
            return reverse(self.list_redirect)
        name = f"core:{self.route_name(action)}"
        if pk is None:
            return reverse(name)
        return reverse(name, args=[pk])


    def perm(self, action):
        meta = self.model._meta
        return f"{meta.app_label}.{action}_{meta.model_name}"

    def has_perm(self, user, action):
        return user.has_perm(self.perm(action))

    def can_add(self, user):
        return self.allow_add and self.has_perm(user, "add")

    def can_archive(self, user):
        return self.archivable and self.has_perm(user, "delete")

    def can_delete(self, user):
        return self.deletable and self.has_perm(user, "delete")

    def in_own_delegation(self, request, obj):
        if request.user.is_superuser or not self.delegation_lookup:
            return True
        delegation = request_delegation(request)
        return delegation_id_of(obj, self.delegation_lookup) == delegation.pk

    def can_change_object(self, request, obj):
        if not self.allow_change or not self.has_perm(request.user, "change"):
            return False
        return self.in_own_delegation(request, obj)

    def can_archive_object(self, request, obj):
        return self.can_archive(request.user) and self.in_own_delegation(request, obj)

    def can_delete_object(self, request, obj):
        return self.can_delete(request.user) and self.in_own_delegation(request, obj)

    def can_edit(self, request, obj):
        try:
            return self.can_change_object(request, obj)
        except PermissionDenied:
            return False

    def can_archive_here(self, request, obj):
        try:
            return self.can_archive_object(request, obj)
        except PermissionDenied:
            return False

    def can_delete_here(self, request, obj):
        try:
            return self.can_delete_object(request, obj)
        except PermissionDenied:
            return False


    def archive_blockers(self, obj):
        return []

    def can_see_archived(self, request):
        return True

    def archive_guard(self, request, obj):
        return []

    def archive_problems(self, request, obj):
        return [*self.archive_blockers(obj), *self.archive_guard(request, obj)]

    def restore_blockers(self, obj):
        return []

    def delete_blockers(self, obj):
        reasons = []
        for relation in self.model._meta.related_objects:
            if relation.many_to_many or relation.on_delete not in (models.PROTECT, models.RESTRICT, models.CASCADE):
                continue
            total = relation.related_model._base_manager.filter(**{relation.field.name: obj}).count()
            if total:
                meta = relation.related_model._meta
                name = str(meta.verbose_name if total == 1 else meta.verbose_name_plural).lower()
                reasons.append(f"Está en uso en {total} {name}.")
        if reasons:
            reasons.append("Cámbialos o elimínalos antes de eliminar este registro.")
        return reasons

    def duplicate_message(self, label, archived):
        if archived:
            return (
                f"Ya existe un registro con ese {label}, pero está archivado. "
                "Restáuralo desde el listado (Incluir archivados) en vez de crearlo otra vez."
            )
        return f"Ya existe un registro con ese {label}, aunque cambien las mayúsculas o los espacios."

    def validate_form(self, form, cleaned):
        pass

    def filter_choices(self, request, name, model_field):
        return None

    def panel_context(self, request, obj):
        return {}


    def code_of(self, obj):
        if not self.code_prefix or obj.pk is None:
            return ""
        return f"{self.code_prefix}{obj.pk:0{self.code_digits}d}"


    def get_queryset(self, request, include_archived=False):
        qs = self.model._default_manager.all()
        if self.select_related:
            qs = qs.select_related(*self.select_related)
        if self.prefetch_related:
            qs = qs.prefetch_related(*self.prefetch_related)
        if self.soft_delete and not include_archived:
            qs = qs.filter(**{f"{self.archive_lookup}__isnull": True})
        if self.delegation_lookup:
            delegation = active_delegation(request)
            if delegation is not None:
                qs = qs.filter(**{self.delegation_lookup: delegation})
        return qs

    def archived_at(self, obj):
        return getattr(obj, "deleted_at", None) if self.soft_delete else None

    def set_archived(self, obj, when):
        obj.deleted_at = when
        obj.save(update_fields=["deleted_at", "updated_at"])

    def is_archived(self, obj):
        return self.archived_at(obj) is not None

    def apply_search(self, qs, text):
        words = text.split()[:SEARCH_WORDS]
        for word in words:
            pattern = word_pattern(word)
            condition = models.Q()
            for name in self.search_fields:
                condition |= models.Q(**{f"{name}__iregex": pattern})
            number = number_in_code(word, self.code_prefix)
            if number is not None:
                condition |= models.Q(pk=number)
            qs = qs.filter(condition)
        if words and self.search_distinct:
            qs = qs.distinct()
        return qs

    def filter_field(self, name):
        found = field_for_path(self.model, name)
        if found is None:
            raise FieldDoesNotExist(f"{self.model.__name__} no tiene el campo «{name}» para filtrar.")
        return found

    def build_filters(self, request):
        specs = []
        for name in self.list_filters:
            if name == "delegation" and self.delegation_lookup and active_delegation(request) is not None:
                continue
            model_field = self.filter_field(name)
            options = self.filter_choices(request, name, model_field)
            if options is not None:
                options = [(str(value), str(label)) for value, label in options]
            elif model_field.choices:
                options = [(str(v), str(label)) for v, label in model_field.flatchoices]
            elif isinstance(model_field, models.BooleanField):
                options = [("1", "Sí"), ("0", "No")]
            elif model_field.is_relation and (model_field.many_to_one or model_field.many_to_many):
                related = model_field.related_model._default_manager.all()
                if issubclass(related.model, BaseModel):
                    related = related.filter(deleted_at__isnull=True)
                options = [(str(o.pk), str(o)) for o in related]
            else:
                continue
            selected = request.GET.get(name, "")
            if selected not in {value for value, _ in options}:
                selected = ""
            specs.append(
                FilterSpec(
                    name=name,
                    label=self.label_of(model_field),
                    options=options,
                    selected=selected,
                )
            )
        if self.state_filter and self.soft_delete:
            selected = request.GET.get(STATE_FILTER, "")
            specs.append(
                FilterSpec(
                    name=STATE_FILTER,
                    label="Estado",
                    options=[(STATE_ACTIVE, "Activo"), (STATE_INACTIVE, "Inactivo")],
                    selected=selected if selected in (STATE_ACTIVE, STATE_INACTIVE) else "",
                )
            )
        return specs

    def apply_filters(self, qs, specs):
        for spec in specs:
            if not spec.selected:
                continue
            if spec.name == STATE_FILTER:
                qs = qs.filter(**{f"{self.archive_lookup}__isnull": spec.selected == STATE_ACTIVE})
                continue
            model_field = self.filter_field(spec.name)
            value = spec.selected
            if isinstance(model_field, models.BooleanField):
                value = value == "1"
            qs = qs.filter(**{spec.name: value})
        return qs

    def scope_summary(self, request):
        if not self.delegation_lookup:
            return ""
        delegation = active_delegation(request)
        if delegation is None:
            return ""
        return f"Delegación: {registry.get('delegaciones').code_of(delegation)} · {delegation.name}"

    def filter_summary(self, text, filters, archived):
        parts = []
        if text:
            parts.append(f"Búsqueda: «{text}»")
        for spec in filters:
            if spec.selected:
                parts.append(f"{spec.label}: {dict(spec.options)[spec.selected]}")
        if archived:
            parts.append("incluye archivados")
        return "; ".join(parts) if parts else "Sin filtros"


    def raw_value(self, obj, path_):
        if path_ == CODE_COLUMN:
            return self.code_of(obj)
        if path_ in self.computed:
            return self.computed[path_](obj)
        return get_raw(obj, path_)

    def badge_label(self, column, raw):
        model_field = field_for_path(self.model, column.path)
        if model_field is not None:
            return str(dict(model_field.flatchoices).get(raw, raw))
        return str(self.computed_choices.get(column.path, {}).get(raw, raw))

    def make_cell(self, obj, column):
        raw = self.raw_value(obj, column.path)
        if raw is None or raw == "":
            return Cell(text="")
        kind = column.kind
        if kind == "bool":
            return Cell(kind="bool", text="Sí" if raw else "No", tone="ok" if raw else "neutral")
        if kind == "badge":
            tone, icon = ui.tone_for(raw)
            return Cell(kind="badge", text=self.badge_label(column, raw), tone=tone, icon=icon)
        if kind == "code":
            return Cell(kind="code", text=str(raw), together=True)
        if kind == "date":
            return Cell(text=ui.fmt_date(raw))
        if kind == "datetime":
            return Cell(text=ui.fmt_datetime(raw))
        if kind == "number":
            return Cell(kind="number", text=ui.fmt_number(raw))
        if kind == "percent":
            return Cell(kind="number", text=f"{ui.fmt_number(raw)} %")
        if kind == "color":
            text = str(raw)
            return Cell(kind="color", text=text, color=text if HEX_COLOR.fullmatch(text) else "")
        if isinstance(raw, str) and column.path != "__str__":
            return Cell(text=raw)
        return Cell(text=ui.humanize_dates(raw))

    def make_row(self, request, obj, columns=None, actions=True):
        columns = columns or self.columns
        cells = [self.make_cell(obj, c) for c in columns]
        for column, cell in zip(columns, cells, strict=True):
            cell.link = column.link
            if column.link and not cell.text:
                cell.text = ui.humanize_dates(obj)
            cell.together = cell.kind == "text" and (
                len(cell.text) <= 18 or (column.link and len(cell.text) <= 26)
            )
        row = Row(
            obj=obj,
            cells=cells,
            detail_url=self.url("detail", obj.pk),
            archived=self.is_archived(obj),
        )
        if actions:
            if not row.archived and self.can_edit(request, obj):
                row.edit_url = self.url("update", obj.pk)
            if self.can_archive_here(request, obj):
                if row.archived:
                    row.restore_url = self.url("restore", obj.pk)
                else:
                    row.archive_url = self.url("archive", obj.pk)
                    row.archive_blocked = " ".join(self.archive_problems(request, obj))
            if self.can_delete_here(request, obj):
                row.delete_url = self.url("delete", obj.pk)
                row.delete_blocked = " ".join(self.delete_blockers(obj))
        return row

    def detail_cells(self, obj):
        listed = {column.path: column for column in self.columns}
        skip = {"id", "created_at", "updated_at", "deleted_at", *self.detail_exclude}
        pairs = []
        if self.code_prefix:
            pairs.append((self.code_label, Cell(kind="code", text=self.code_of(obj), together=True)))
        for model_field in self.model._meta.concrete_fields:
            if model_field.name in skip:
                continue
            label = self.label_of(model_field)
            kind = listed[model_field.name].kind if model_field.name in listed else detect_kind(model_field)
            column = Column(path=model_field.name, label=label, kind=kind)
            pairs.append((label, self.make_cell(obj, column)))
        pairs.extend(self.extra_detail(obj))
        return pairs

    def extra_detail(self, obj):
        return []

    def record_meta(self, obj):
        text = (
            f"Creado el {ui.fmt_datetime(obj.created_at)}. "
            f"Última actualización el {ui.fmt_datetime(obj.updated_at)}."
        )
        if self.archived_at(obj):
            text += f" Archivado el {ui.fmt_datetime(self.archived_at(obj))}."
        return text


    def export_value(self, obj, column):
        raw = self.raw_value(obj, column.path)
        if raw is None or raw == "":
            return ""
        kind = column.kind
        if kind == "bool":
            return "Sí" if raw else "No"
        if kind == "badge":
            return self.badge_label(column, raw)
        if kind == "code":
            return str(raw)
        if kind in ("number", "percent", "date", "datetime"):
            return raw
        if isinstance(raw, str) and column.path != "__str__":
            return raw
        return ui.humanize_dates(raw)


    @property
    def form_class(self):
        if self._form_class is None:
            self._form_class = modelform_factory(
                self.model, form=self.form_base, fields=list(self.form_fields)
            )
        return self._form_class

    def form_class_for(self, creating):
        if not creating or self.create_form_base is None:
            return self.form_class
        if self._create_form_class is None:
            self._create_form_class = modelform_factory(
                self.model,
                form=self.create_form_base,
                fields=list(self.create_fields or self.form_fields),
            )
        return self._create_form_class

    def initial_for(self, request):
        initial = {}
        for name in self.create_fields or self.form_fields:
            value = request.GET.get(name, "")
            model_field = field_for_path(self.model, name)
            if is_id(value) and model_field is not None and model_field.is_relation:
                initial[name] = value
        return initial

    def initial_values(self, request):
        return {}

    def extra_actions(self, request, obj):
        return []

    def prepare_object(self, request, obj, creating, form):
        if self.delegation_lookup and hasattr(obj, "delegation_id"):
            delegation = request_delegation(request)
            if delegation is not None:
                obj.delegation = delegation

    def after_save(self, request, obj, form, creating):
        pass


    @property
    def new_label(self):
        return f"{'Nueva' if self.gender == 'f' else 'Nuevo'} {self.title.lower()}"

    def say(self, kind, obj):
        words = {
            "created": ("creado", "creada"),
            "updated": ("actualizado", "actualizada"),
            "archived": ("archivado", "archivada"),
            "restored": ("restaurado", "restaurada"),
            "deleted": ("eliminado", "eliminada"),
        }
        word = words[kind][1 if self.gender == "f" else 0]
        name = ui.humanize_dates(obj)
        if name.lower().startswith(self.title.split()[0].lower()):
            return f"{self.title} {word}."
        return f"{self.title} «{name}» {word}."


class Registry:

    def __init__(self):
        self._by_slug = {}

    def register(self, crud_class):
        crud = crud_class()
        self._by_slug[crud.slug] = crud
        return crud_class

    def get(self, slug):
        return self._by_slug[slug]

    def all(self):
        return list(self._by_slug.values())

    def urls(self):
        patterns = []
        for crud in self.all():
            slug = crud.slug
            if crud.list_redirect:
                patterns.append(
                    path(
                        f"{slug}/",
                        RedirectView.as_view(pattern_name=crud.list_redirect, query_string=True),
                        name=crud.route_name("list"),
                    )
                )
            else:
                patterns.append(
                    path(f"{slug}/", CrudListView.as_view(crud=crud), name=crud.route_name("list"))
                )
            if crud.allow_add:
                patterns.append(
                    path(
                        f"{slug}/nuevo/",
                        CrudCreateView.as_view(crud=crud),
                        name=crud.route_name("create"),
                    )
                )
            patterns.append(
                path(
                    f"{slug}/<int:pk>/",
                    CrudDetailView.as_view(crud=crud),
                    name=crud.route_name("detail"),
                )
            )
            if crud.allow_change:
                patterns.append(
                    path(
                        f"{slug}/<int:pk>/editar/",
                        CrudUpdateView.as_view(crud=crud),
                        name=crud.route_name("update"),
                    )
                )
            if crud.archivable:
                patterns.append(
                    path(
                        f"{slug}/<int:pk>/archivar/",
                        CrudArchiveView.as_view(crud=crud),
                        name=crud.route_name("archive"),
                    )
                )
                patterns.append(
                    path(
                        f"{slug}/<int:pk>/restaurar/",
                        CrudRestoreView.as_view(crud=crud),
                        name=crud.route_name("restore"),
                    )
                )
            if crud.deletable:
                patterns.append(
                    path(
                        f"{slug}/<int:pk>/eliminar/",
                        CrudDeleteView.as_view(crud=crud),
                        name=crud.route_name("delete"),
                    )
                )
        return patterns


registry = Registry()


class CrudView(LoginRequiredMixin, View):

    crud = None
    action = "view"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not self.crud.has_perm(request.user, self.action):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get_object(self, request, pk):
        queryset = self.crud.get_queryset(request, include_archived=True)
        return get_object_or_404(queryset, pk=pk)

    def breadcrumbs(self, *extra):
        trail = [("Inicio", reverse("core:dashboard"))]
        if self.crud.has_perm(self.request.user, "view"):
            trail.append((self.crud.list_title, self.crud.url("list")))
        trail.extend(extra)
        return trail


def query_string(request, drop=(), **updates):
    params = request.GET.copy()
    for key in drop:
        params.pop(key, None)
    for key, value in updates.items():
        if value in (None, ""):
            params.pop(key, None)
        else:
            params[key] = value
    encoded = params.urlencode()
    return f"?{encoded}" if encoded else "?"


def page_size_of(request):
    size = request.session.get(SESSION_PAGE_SIZE)
    return size if size in PAGE_SIZES else PAGE_SIZE


class CrudListView(CrudView):

    template_name = "core/crud/list.html"
    columns = None
    export_title = ""
    export_slug = ""

    def get_columns(self, request):
        return self.columns if self.columns is not None else self.crud.columns

    def extra_context(self, request):
        return {}

    def get(self, request):
        crud = self.crud
        columns = self.get_columns(request)
        filters = crud.build_filters(request)
        state = next((spec.selected for spec in filters if spec.name == STATE_FILTER), "")
        mode = request.GET.get("archivados", "")
        if mode not in ("1", ONLY_ARCHIVED) or not crud.soft_delete or not crud.can_see_archived(request):
            mode = ""
        archived = crud.soft_delete and (bool(mode) or state == STATE_INACTIVE)
        only_archived = mode == ONLY_ARCHIVED
        qs = crud.get_queryset(request, include_archived=archived)
        if only_archived:
            qs = qs.filter(**{f"{crud.archive_lookup}__isnull": False})

        text = request.GET.get("q", "").strip()
        qs = crud.apply_search(qs, text)
        qs = crud.apply_filters(qs, filters)

        sort = request.GET.get("orden", "")
        direction = "desc" if request.GET.get("dir") == "desc" else "asc"
        sortable = {c.sort_key for c in columns if c.sort_key}
        if sort in sortable:
            qs = qs.order_by(("-" if direction == "desc" else "") + sort, "pk")
        else:
            sort = ""
            qs = qs.order_by(*(crud.ordering or crud.model._meta.ordering), "pk")

        if request.GET.get("formato") == "xlsx":
            return self.download(request, qs, columns, crud.filter_summary(text, filters, archived))

        page_size = page_size_of(request)
        paginator = Paginator(qs, page_size)
        page = paginator.get_page(request.GET.get("page"))

        shown = []
        for col in columns:
            current = replace(col)
            if col.sort_key:
                if sort == col.sort_key:
                    current.sort_dir = direction
                    next_dir = "asc" if direction == "desc" else "desc"
                else:
                    next_dir = "asc"
                current.sort_url = query_string(
                    request, drop=("page",), orden=col.sort_key, dir=next_dir
                )
            shown.append(current)

        rows = [crud.make_row(request, obj, columns=columns) for obj in page.object_list]
        any_actions = any(r.edit_url or r.archive_url or r.restore_url or r.delete_url for r in rows)

        context = {
            "crud": crud,
            "columns": shown,
            "rows": rows,
            "any_actions": any_actions,
            "page": page,
            "page_range": list(
                paginator.get_elided_page_range(page.number, on_each_side=2, on_ends=1)
            ),
            "ellipsis": paginator.ELLIPSIS,
            "page_query": query_string(request, drop=("page",)),
            "page_sizes": PAGE_SIZES,
            "page_size": page_size,
            "page_size_next": request.path + query_string(request, drop=("page",)).rstrip("?"),
            "archived_url": query_string(
                request, drop=("page",), archivados="" if archived else "1"
            ),
            "trash_url": query_string(request, drop=("page",), archivados="" if only_archived else ONLY_ARCHIVED),
            "only_archived": only_archived,
            "archived_mode": mode,
            "can_see_archived": crud.can_see_archived(request),
            "export_url": query_string(request, drop=("page",), formato="xlsx"),
            "filters": filters,
            "q": text,
            "sort": sort,
            "direction": direction,
            "archived": archived,
            "has_filters": bool(text or archived or any(f.selected for f in filters)),
            "can_add": crud.can_add(request.user),
            "create_url": crud.url("create") if crud.can_add(request.user) else "",
            "breadcrumbs": self.breadcrumbs(),
        }
        context.update(self.extra_context(request))
        return render(request, self.template_name, context)

    def download(self, request, qs, columns, summary):
        crud = self.crud
        scope = crud.scope_summary(request)
        if scope:
            summary = f"{scope}. {summary}"
        total = qs.count()
        objects = list(qs[: export.EXPORT_LIMIT])
        content = export.build_workbook(
            title=self.export_title or crud.list_title,
            headers=[c.label for c in columns],
            kinds=[c.kind for c in columns],
            rows=[[crud.export_value(obj, c) for c in columns] for obj in objects],
            summary=summary,
            user=request.user,
            total=total,
        )
        log_export(request.user, crud.model, len(objects), summary)
        response = HttpResponse(content, content_type=export.CONTENT_TYPE)
        response["Content-Disposition"] = f'attachment; filename="{export.file_name(self.export_slug or crud.slug)}"'
        return response


class CrudDetailView(CrudView):
    def get(self, request, pk):
        crud = self.crud
        obj = self.get_object(request, pk)
        blocks = self.related_blocks(request, obj)
        can_edit = crud.can_edit(request, obj)
        archived = crud.is_archived(obj)
        can_archive = crud.can_archive_here(request, obj)
        can_delete = crud.can_delete_here(request, obj)
        context = {
            "crud": crud,
            "obj": obj,
            "pairs": crud.detail_cells(obj),
            "blocks": blocks,
            "archived": archived,
            "can_edit": can_edit and not archived,
            "can_archive": can_archive,
            "can_delete": can_delete,
            "edit_url": crud.url("update", obj.pk) if crud.allow_change else "",
            "archive_url": crud.url("archive", obj.pk) if crud.archivable else "",
            "restore_url": crud.url("restore", obj.pk) if crud.archivable else "",
            "delete_url": crud.url("delete", obj.pk) if crud.deletable else "",
            "archive_blocked": " ".join(crud.archive_problems(request, obj)) if can_archive and not archived else "",
            "delete_blocked": " ".join(crud.delete_blockers(obj)) if can_delete else "",
            "panel_template": crud.detail_panel,
            "panel": crud.panel_context(request, obj) if crud.detail_panel else {},
            "record_meta": crud.record_meta(obj),
            "obj_name": ui.humanize_dates(obj),
            "breadcrumbs": self.breadcrumbs((ui.humanize_dates(obj), None)),
            "extra_actions": crud.extra_actions(request, obj),
        }
        return render(request, "core/crud/detail.html", context)

    def related_blocks(self, request, obj):
        blocks = []
        for rel in self.crud.related:
            related_crud = registry.get(rel.crud)
            if not related_crud.has_perm(request.user, "view"):
                continue
            try:
                qs = related_crud.get_queryset(request).filter(**{rel.field: obj})
            except PermissionDenied:
                continue
            total = qs.count()
            paths = rel.columns or [c.path for c in related_crud.columns if c.path != rel.field]
            columns = [c for c in related_crud.columns if c.path in paths]
            qs = qs.order_by(*related_crud.model._meta.ordering, "pk")
            rows = [
                related_crud.make_row(request, o, columns=columns, actions=False)
                for o in qs[:RELATED_LIMIT]
            ]
            for row in rows:
                if row.cells and not any(cell.link for cell in row.cells):
                    row.cells[0].link = True
            block = RelatedBlock(title=rel.title, columns=columns, rows=rows, total=total)
            if not self.crud.is_archived(obj) and related_crud.can_add(request.user):
                block.add_url = f"{related_crud.url('create')}?{rel.field}={obj.pk}"
                block.add_label = f"Agregar {related_crud.title.lower()}"
            blocks.append(block)
        return blocks


class CrudFormView(CrudView):

    def in_modal(self, request):
        return request.GET.get("modal") == "1"

    def make_form(self, request, instance=None, data=None, initial=None):
        form_class = self.crud.form_class_for(creating=instance is None)
        return form_class(
            data=data,
            files=request.FILES if data is not None else None,
            instance=instance,
            initial=initial,
            request=request,
            crud=self.crud,
        )

    def render_form(self, request, form, obj):
        crud = self.crud
        creating = obj is None
        can_archive = not creating and crud.can_archive_here(request, obj)
        can_delete = not creating and crud.can_delete_here(request, obj)
        context = {
            "crud": crud,
            "form": form,
            "obj": obj,
            "creating": creating,
            "heading": (crud.create_heading or crud.new_label) if creating else f"Editar {crud.title.lower()}",
            "save_label": crud.create_save_label if creating else "Guardar",
            "obj_name": "" if creating else ui.humanize_dates(obj),
            "has_checks": any(f.widget_type == "checkbox" for f in form),
            "version": "" if creating else version_of(obj),
            "cancel_url": crud.url("list") if creating else crud.url("detail", obj.pk),
            "can_add_another": crud.can_add(request.user) and (crud.create_add_another or not creating),
            "archive_url": crud.url("archive", obj.pk) if can_archive else "",
            "archive_blocked": " ".join(crud.archive_problems(request, obj)) if can_archive else "",
            "delete_url": crud.url("delete", obj.pk) if can_delete else "",
            "delete_blocked": " ".join(crud.delete_blockers(obj)) if can_delete else "",
            "breadcrumbs": self.breadcrumbs(
                ("Nuevo" if creating else ui.humanize_dates(obj), None)
            ),
        }
        if self.in_modal(request):
            response = render(request, "core/crud/form_modal.html", context)
            response["X-Modal"] = "form"
            return response
        return render(request, "core/crud/form.html", context)

    def finish(self, request, obj, text):
        again = "_addanother" in request.POST and self.crud.can_add(request.user)
        if self.in_modal(request):
            if not again:
                messages.success(request, text)
            response = JsonResponse(
                {"saved": True, "again": again, "message": text, "create_url": self.crud.url("create") if again else ""}
            )
            response["X-Modal"] = "saved"
            return response
        messages.success(request, text)
        if again:
            return redirect(self.crud.url("create"))
        return redirect(self.crud.url("detail", obj.pk))

    def save(self, request, form, creating, opened=""):
        obj = form.save(commit=False)
        self.crud.prepare_object(request, obj, creating, form)
        with transaction.atomic():
            before = None
            if not creating:
                # El registro se bloquea y se vuelve a comparar su versión dentro de la transacción: si dos personas
                # guardan a la vez, la segunda ve el aviso en vez de pisar el cambio de la primera (RNF-003).
                before = self.crud.model._default_manager.select_for_update().get(pk=obj.pk)
                if opened and opened != version_of(before):
                    raise StaleRecord(before)
            obj.save()
            form.save_m2m()
            self.crud.after_save(request, obj, form, creating)
            notify_crud_change(self.crud, obj, before)
            if creating:
                log_event(request.user, "Registro creado", obj, new=str(obj))
            else:
                changes = changed_fields(before, obj)
                if changes:
                    log_event(
                        request.user,
                        "Registro modificado",
                        obj,
                        previous="; ".join(f"{label}: {old}" for label, old, _ in changes),
                        new="; ".join(f"{label}: {new}" for label, _, new in changes),
                    )
        return obj


class CrudCreateView(CrudFormView):
    action = "add"

    def get(self, request):
        initial = self.crud.initial_for(request)
        initial.update(self.crud.initial_values(request))
        return self.render_form(request, self.make_form(request, initial=initial), None)

    def post(self, request):
        form = self.make_form(request, data=request.POST)
        if form.is_valid():
            try:
                obj = self.save(request, form, creating=True)
            except IntegrityError:
                form.add_error(None, DUPLICATE_TEXT)
                return self.render_form(request, form, None)
            return self.finish(request, obj, self.crud.say("created", obj))
        return self.render_form(request, form, None)


class ChangeObjectMixin:

    action = "change"

    def load(self, request, pk):
        obj = self.get_object(request, pk)
        if not self.crud.can_change_object(request, obj):
            raise PermissionDenied
        return obj


class CrudUpdateView(ChangeObjectMixin, CrudFormView):

    def get(self, request, pk):
        obj = self.load(request, pk)
        if self.crud.is_archived(obj):
            messages.warning(request, "Este registro está archivado. Restáuralo para editarlo.")
            return redirect(self.crud.url("detail", obj.pk))
        return self.render_form(request, self.make_form(request, instance=obj), obj)

    def post(self, request, pk):
        obj = self.load(request, pk)
        if self.crud.is_archived(obj):
            raise PermissionDenied
        form = self.make_form(request, instance=obj, data=request.POST)
        opened = request.POST.get("_version", "")
        if opened and opened != version_of(obj):
            form.is_valid()
            form.add_error(None, conflict_message(obj))
            return self.render_form(request, form, obj)
        if form.is_valid():
            try:
                obj = self.save(request, form, creating=False, opened=opened)
            except StaleRecord as stale:
                current = stale.args[0]
                form.add_error(None, conflict_message(current))
                return self.render_form(request, form, current)
            except IntegrityError:
                form.add_error(None, DUPLICATE_TEXT)
                return self.render_form(request, form, obj)
            return self.finish(request, obj, self.crud.say("updated", obj))
        return self.render_form(request, form, obj)


class ArchiveObjectMixin:

    action = "delete"

    def load(self, request, pk):
        obj = self.get_object(request, pk)
        if not self.crud.can_archive_object(request, obj):
            raise PermissionDenied
        return obj

    def blocked_text(self, verb, obj, reasons):
        return f"No se puede {verb} {self.crud.title.lower()} «{ui.humanize_dates(obj)}»: {' '.join(reasons)}"


class CrudArchiveView(ArchiveObjectMixin, CrudView):

    def get(self, request, pk):
        obj = self.load(request, pk)
        if self.crud.is_archived(obj):
            messages.info(request, "Este registro ya estaba archivado.")
            return redirect(self.crud.url("detail", obj.pk))
        context = {
            "crud": self.crud,
            "obj": obj,
            "obj_name": ui.humanize_dates(obj),
            "blockers": self.crud.archive_problems(request, obj),
            "cancel_url": self.crud.url("detail", obj.pk),
            "breadcrumbs": self.breadcrumbs(
                (ui.humanize_dates(obj), self.crud.url("detail", obj.pk)), ("Archivar", None)
            ),
        }
        return render(request, "core/crud/archive_confirm.html", context)

    def post(self, request, pk):
        obj = self.load(request, pk)
        if not self.crud.is_archived(obj):
            reasons = self.crud.archive_problems(request, obj)
            if reasons:
                messages.error(request, self.blocked_text("archivar", obj, reasons))
                return redirect(self.crud.url("detail", obj.pk))
            when = timezone.now()
            with transaction.atomic():
                self.crud.set_archived(obj, when)
                notify_crud_change(self.crud, obj)
                log_event(
                    request.user,
                    "Registro archivado",
                    obj,
                    previous="deleted_at=None",
                    new=f"deleted_at={when.isoformat()}",
                )
            messages.success(request, self.crud.say("archived", obj))
        return redirect(self.crud.url("list"))


class CrudRestoreView(CrudArchiveView):

    http_method_names = ["post", "options"]

    def post(self, request, pk):
        obj = self.load(request, pk)
        if self.crud.is_archived(obj):
            reasons = self.crud.restore_blockers(obj)
            if reasons:
                messages.error(request, self.blocked_text("restaurar", obj, reasons))
                return redirect(self.crud.url("detail", obj.pk))
            previous = f"deleted_at={self.crud.archived_at(obj).isoformat()}"
            with transaction.atomic():
                self.crud.set_archived(obj, None)
                notify_crud_change(self.crud, obj)
                log_event(
                    request.user,
                    "Registro restaurado",
                    obj,
                    previous=previous,
                    new="deleted_at=None",
                )
            messages.success(request, self.crud.say("restored", obj))
        return redirect(self.crud.url("detail", obj.pk))


class CrudDeleteView(CrudView):

    action = "delete"

    def load(self, request, pk):
        obj = self.get_object(request, pk)
        if not self.crud.can_delete_object(request, obj):
            raise PermissionDenied
        return obj

    def get(self, request, pk):
        obj = self.load(request, pk)
        context = {
            "crud": self.crud,
            "obj": obj,
            "obj_name": ui.humanize_dates(obj),
            "blockers": self.crud.delete_blockers(obj),
            "cancel_url": self.crud.url("detail", obj.pk),
            "breadcrumbs": self.breadcrumbs(
                (ui.humanize_dates(obj), self.crud.url("detail", obj.pk)), ("Eliminar", None)
            ),
        }
        return render(request, "core/crud/delete_confirm.html", context)

    def post(self, request, pk):
        obj = self.load(request, pk)
        name = ui.humanize_dates(obj)
        reasons = self.crud.delete_blockers(obj)
        if reasons:
            messages.error(
                request, f"No se puede eliminar {self.crud.title.lower()} «{name}»: {' '.join(reasons)}"
            )
            return redirect(self.crud.url("detail", obj.pk))
        text = self.crud.say("deleted", obj)
        try:
            with transaction.atomic():
                log_event(request.user, "Registro eliminado", obj, previous=name)
                notify_crud_change(self.crud, obj)
                obj.delete()
        except models.ProtectedError:
            messages.error(
                request,
                f"No se puede eliminar {self.crud.title.lower()} «{name}»: otros registros dependen de él.",
            )
            return redirect(self.crud.url("detail", obj.pk))
        messages.success(request, text)
        return redirect(self.crud.url("list"))
