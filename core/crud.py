"""Motor de las pantallas de gestión (listado, ficha, formulario y archivo).

Cada modelo se describe una sola vez con una clase Crud (ver core/registry.py),
parecido a un ModelAdmin pero con pantallas propias en Bootstrap. Las reglas de
acceso son las mismas del Django Admin:

- cada acción pide el permiso del modelo (view, add, change y delete);
- quien no es superusuario ni de Coordinación solo ve registros de su delegación;
- «Eliminar» pide el permiso delete del modelo: los registros con historia se archivan con deleted_at
  (y se pueden restaurar) y los que no la tienen (los perfiles) se borran de verdad, con confirmación;
- antes de archivar o eliminar se revisan las relaciones: un registro en uso no se toca;
- las listas desplegables de los formularios se acotan a la delegación.

Todos los listados traen búsqueda por palabras (core/search.py), filtros, orden,
paginador y el botón para exportar lo que se ve a Excel (core/export.py).
"""

import inspect
import re
from dataclasses import dataclass, replace

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import FieldDoesNotExist, ObjectDoesNotExist, PermissionDenied
from django.core.paginator import Paginator
from django.db import models, transaction
from django.forms import modelform_factory
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import path, reverse
from django.utils import timezone
from django.views import View

from core import export, ui
from core.audit import changed_fields, log_event, log_export
from core.access import active_delegation, delegation_id_of, request_delegation
from core.colors import HEX_COLOR
from core.forms import CrudForm
from core.models import BaseModel
from core.search import word_pattern

PAGE_SIZE = 20  # filas por página si la persona no eligió otra cosa
PAGE_SIZES = (10, 20, 50)  # opciones del selector «Filas por página»
SESSION_PAGE_SIZE = "page_size"  # clave de request.session donde queda lo que eligió
RELATED_LIMIT = 25  # filas que muestra cada tabla de registros relacionados en una ficha
SEARCH_WORDS = 10  # palabras de la búsqueda que se usan; el resto se ignora
CODE_COLUMN = "__code__"  # columna del código del registro (DEL01, ROL02...); se calcula con su id
STATE_FILTER = "estado"  # nombre del filtro Activo / Inactivo de los mantenedores con state_filter
STATE_ACTIVE = "activo"
STATE_INACTIVE = "inactivo"
MAX_CODE_NUMBER_DIGITS = 9  # un número más largo no es un código: no se busca como id


def is_id(text):
    """True si el texto es un número escrito solo con dígitos 0-9 (un id válido en la URL)."""
    return re.fullmatch(r"[0-9]+", str(text)) is not None


def number_in_code(word, prefix):
    """El número de un código escrito en la búsqueda ("del02", "DEL2" -> 2); None si la palabra no es un código.

    Sirve para encontrar un registro por su código aunque el código no se guarde: se calcula con el id.
    """
    if not prefix:
        return None
    found = re.fullmatch(rf"{re.escape(prefix)}0*([0-9]{{1,{MAX_CODE_NUMBER_DIGITS}}})", word.strip(), re.IGNORECASE)
    return int(found.group(1)) if found else None


def version_of(obj):
    """Marca de la última modificación de un registro.

    El formulario de edición la lleva escondida; si al guardar ya no coincide, alguien
    más modificó el registro mientras se editaba. Un modelo sin updated_at (los usuarios
    de Django) no la lleva y no revisa esto.
    """
    stamp = getattr(obj, "updated_at", None)
    return stamp.isoformat() if stamp else ""


# ---------------------------------------------------------------------------
# Datos que se pasan a las plantillas
# ---------------------------------------------------------------------------


@dataclass
class Cell:
    """Un valor ya formateado para mostrarlo en una tabla o en una ficha."""

    kind: str = "text"  # text, badge, bool, number, color
    text: str = ""
    tone: str = ""
    icon: str = ""
    color: str = ""  # solo en kind="color": un #RRGGBB ya validado
    link: bool = False
    together: bool = False  # una sola palabra corta (un código, un RUT): no se parte en dos líneas


@dataclass
class Row:
    """Una fila de tabla: el objeto, sus celdas y los enlaces de sus acciones."""

    obj: object
    cells: list
    detail_url: str
    edit_url: str = ""
    archive_url: str = ""
    restore_url: str = ""
    delete_url: str = ""
    archived: bool = False
    archive_blocked: str = ""  # por qué no se puede archivar (vacío si se puede)
    delete_blocked: str = ""  # por qué no se puede eliminar (vacío si se puede)


@dataclass
class Column:
    """Columna ya resuelta: etiqueta, tipo y la clave con que se puede ordenar."""

    path: str
    label: str
    kind: str
    sort_key: str = ""
    link: bool = False
    sort_url: str = ""
    sort_dir: str = ""  # "asc" o "desc" si la lista está ordenada por esta columna


@dataclass
class FilterSpec:
    """Un filtro del listado: nombre, opciones y valor elegido."""

    name: str
    label: str
    options: list
    selected: str = ""


@dataclass
class Related:
    """Tabla de registros relacionados que se muestra en la ficha de un objeto."""

    crud: str  # slug del Crud relacionado
    field: str  # campo del modelo relacionado que apunta al objeto de la ficha
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


# ---------------------------------------------------------------------------
# Columnas
# ---------------------------------------------------------------------------


class Col:
    """Columna del listado: un campo del modelo o una ruta como "item__name".

    kind puede ser text, badge, bool, date, datetime, number, percent, color o code; si no se
    indica, se deduce del campo. sort=False desactiva el orden por esa columna.
    La ruta CODE_COLUMN es la columna del código del registro (ver Crud.code_prefix).
    """

    def __init__(self, path, label=None, sort=None, kind=None, link=False):
        self.path = path
        self.label = label
        self.sort = sort
        self.kind = kind
        self.link = link


def field_for_path(model, path_):
    """Último campo de una ruta como "activity__delegation"; None si no es un campo."""
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
    """Valor de una ruta como "author_officer__name" (None si algún paso es nulo o no existe).

    Si un paso es un método sin parámetros ("get_full_name"), se llama.
    """
    if path_ == "__str__":
        return str(obj)
    value = obj
    for part in path_.split("__"):
        if value is None:
            return None
        try:
            value = getattr(value, part)
        except ObjectDoesNotExist:  # una relación uno a uno que no existe (un usuario sin perfil)
            return None
        if inspect.ismethod(value):
            value = value()
    return value


# ---------------------------------------------------------------------------
# Descripción de un mantenedor
# ---------------------------------------------------------------------------


class Crud:
    """Describe las pantallas de un modelo. Se subclasea en core/registry.py."""

    model = None
    slug = ""
    icon = "bi-folder2"

    # Textos. Si no se indican, salen del nombre del modelo.
    title = None
    title_plural = None
    list_title = None
    description = ""
    gender = "m"  # "m" o "f": para decir "creado" o "creada"

    # Listado (el orden por defecto es el del modelo)
    list_display = ()
    search_fields = ()
    search_distinct = False  # True si alguna búsqueda cruza una relación de varios (un grupo, por ejemplo)
    list_filters = ()
    select_related = ()
    prefetch_related = ()
    ordering = ()  # orden por defecto del listado, si no se quiere el del modelo
    computed = {}  # nombre de columna -> función que calcula su valor a partir del registro
    computed_choices = {}  # columna calculada que se muestra como insignia -> {valor: texto}
    state_filter = False  # agrega el filtro «Estado» (Activo / Inactivo) según deleted_at, como en los diseños

    # Código del registro (DEL01, ROL02...): no es una columna, se calcula con el id y se puede buscar.
    code_prefix = ""
    code_digits = 2
    code_label = "Código"

    # Formulario
    form_base = CrudForm  # se cambia en un mantenedor que necesite reglas propias
    form_fields = ()
    # Un formulario de alta distinto del de edición (el ingreso de atención pide menos datos que su edición).
    create_fields = None
    create_form_base = None
    create_heading = ""
    create_save_label = "Guardar"
    create_add_another = True  # ofrece «Guardar y agregar otro» al crear
    unique_names = ()  # campos de texto que no pueden repetirse sin distinguir mayúsculas; ("name", "delegation") = dentro de la misma delegación
    full_width = ()  # campos que ocupan todo el ancho del formulario
    readonly_on_edit = ()  # campos que se piden al crear y después ya no se pueden cambiar
    help_texts = {}
    show_id = False  # el formulario muestra el id del registro arriba (solo lectura)
    rules = {}  # campo -> nombre de la regla de formato de core/rules.py (RUT, teléfono, correo...)
    labels = {}  # campo -> etiqueta, cuando debe decir otra cosa que el nombre del campo en el modelo
    detail_exclude = ()  # campos del modelo que la ficha no muestra

    # Permisos y alcance
    delegation_lookup = None  # ruta hacia la delegación, como en el Admin
    allow_add = True
    allow_change = True
    archivable = True  # «Eliminar» archiva el registro (borrado lógico): necesita el permiso delete del modelo
    deletable = False  # «Eliminar» borra de verdad (un modelo sin historia, como los perfiles); también pide delete

    # Ficha: tablas de registros relacionados y, si hace falta, un bloque propio debajo de los datos
    related = ()
    detail_panel = ""  # plantilla que se agrega a la ficha; sus datos salen de panel_context

    def __init__(self):
        meta = self.model._meta
        self.title = self.title or ui.initial_capital(meta.verbose_name)
        self.title_plural = self.title_plural or ui.initial_capital(meta.verbose_name_plural)
        self.list_title = self.list_title or self.title_plural
        # Los modelos que heredan de BaseModel se archivan; los demás (los usuarios) no.
        self.soft_delete = issubclass(self.model, BaseModel)
        self.columns = self.resolve_columns(self.list_display)
        self._form_class = None
        self._create_form_class = None

    def label_of(self, model_field, fallback=""):
        """Etiqueta de un campo: la de `labels` si se indicó, y si no la del modelo."""
        if model_field is not None and model_field.name in self.labels:
            return self.labels[model_field.name]
        if model_field is not None:
            return ui.initial_capital(model_field.verbose_name)
        return fallback

    # -- columnas ---------------------------------------------------------

    def resolve_columns(self, specs):
        columns = []
        for spec in specs:
            col = spec if isinstance(spec, Col) else Col(spec)
            if col.path == CODE_COLUMN:
                # El código sale del id: ordenar por código es ordenar por id.
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

    # -- direcciones ------------------------------------------------------

    def route_name(self, action):
        """Nombre de la ruta dentro de core/urls.py, como "actividades_list"."""
        return f"{self.slug.replace('-', '_')}_{action}"

    def url(self, action, pk=None):
        name = f"core:{self.route_name(action)}"
        if pk is None:
            return reverse(name)
        return reverse(name, args=[pk])

    # -- permisos ---------------------------------------------------------

    def perm(self, action):
        meta = self.model._meta
        return f"{meta.app_label}.{action}_{meta.model_name}"

    def has_perm(self, user, action):
        return user.has_perm(self.perm(action))

    def can_add(self, user):
        return self.allow_add and self.has_perm(user, "add")

    def can_archive(self, user):
        """Archivar y restaurar son parte de «Eliminar»: piden el permiso delete del modelo, no el de editar."""
        return self.archivable and self.has_perm(user, "delete")

    def can_delete(self, user):
        """Borrar de verdad (solo los mantenedores con deletable) también pide el permiso delete."""
        return self.deletable and self.has_perm(user, "delete")

    def in_own_delegation(self, request, obj):
        """True si el registro es de la delegación en la que trabaja el usuario.

        Es la delegación activa (la que eligió en la franja de arriba o, si no eligió, la de su funcionario). El
        superusuario y los mantenedores sin delegación no se limitan. Lanza PermissionDenied si el usuario no
        tiene delegación, con el mismo mensaje que usa el Admin.
        """
        if request.user.is_superuser or not self.delegation_lookup:
            return True
        delegation = request_delegation(request)
        return delegation_id_of(obj, self.delegation_lookup) == delegation.pk

    def can_change_object(self, request, obj):
        """Misma regla que has_change_permission del Admin.

        Además del permiso del modelo, quien no es superusuario solo puede
        modificar registros de su propia delegación. Lanza PermissionDenied si el
        usuario no tiene funcionario (y por lo tanto delegación).
        """
        if not self.allow_change or not self.has_perm(request.user, "change"):
            return False
        return self.in_own_delegation(request, obj)

    def can_archive_object(self, request, obj):
        """Permiso delete del modelo y, además, que el registro sea de la delegación del usuario."""
        return self.can_archive(request.user) and self.in_own_delegation(request, obj)

    def can_delete_object(self, request, obj):
        return self.can_delete(request.user) and self.in_own_delegation(request, obj)

    def can_edit(self, request, obj):
        """Igual que can_change_object, pero responde False en vez de lanzar PermissionDenied.

        Sirve para decidir qué botones mostrar sin romper la pantalla.
        """
        try:
            return self.can_change_object(request, obj)
        except PermissionDenied:
            return False

    def can_archive_here(self, request, obj):
        """can_archive_object sin lanzar PermissionDenied: decide si se muestra el botón Archivar o Restaurar."""
        try:
            return self.can_archive_object(request, obj)
        except PermissionDenied:
            return False

    def can_delete_here(self, request, obj):
        """can_delete_object sin lanzar PermissionDenied: decide si se muestra el botón Eliminar."""
        try:
            return self.can_delete_object(request, obj)
        except PermissionDenied:
            return False

    # -- integridad: qué impide archivar, restaurar o eliminar ------------

    def archive_blockers(self, obj):
        """Motivos (textos) por los que el registro no se puede archivar; una lista vacía si se puede.

        Se redefine en cada mantenedor que tiene registros que dependen de otros (un tipo de atención con
        sub atenciones activas, por ejemplo). Lo revisa el servidor al archivar y la pantalla lo avisa antes.
        """
        return []

    def restore_blockers(self, obj):
        """Motivos por los que un registro archivado no se puede restaurar todavía."""
        return []

    def delete_blockers(self, obj):
        """Motivos por los que el registro no se puede eliminar de verdad (un perfil del sistema, uno con usuarios)."""
        return []

    def duplicate_message(self, label, archived):
        """Frase cuando el nombre ya existe sin distinguir mayúsculas; archived dice si el que existe está archivado."""
        if archived:
            return (
                f"Ya existe un registro con ese {label}, pero está archivado. "
                "Restáuralo desde el listado (Incluir archivados) en vez de crearlo otra vez."
            )
        return f"Ya existe un registro con ese {label}, aunque cambien las mayúsculas o los espacios."

    def validate_form(self, form, cleaned):
        """Reglas de negocio entre campos de un formulario de este mantenedor; se agregan con form.add_error."""

    def filter_choices(self, request, name, model_field):
        """Opciones de un filtro del listado, como lista de (valor, texto); None usa las de siempre.

        Sirve para mostrar solo una parte de los registros (en Sub Atención el filtro ofrece solo tipos).
        """
        return None

    def panel_context(self, request, obj):
        """Datos de la plantilla detail_panel de la ficha."""
        return {}

    # -- código -----------------------------------------------------------

    def code_of(self, obj):
        """Código del registro con su prefijo y su id (DEL02, ROL01...); vacío si el mantenedor no los usa."""
        if not self.code_prefix or obj.pk is None:
            return ""
        return f"{self.code_prefix}{obj.pk:0{self.code_digits}d}"

    # -- consultas --------------------------------------------------------

    def get_queryset(self, request, include_archived=False):
        """Registros que el usuario puede ver (misma regla de get_queryset del Admin)."""
        qs = self.model._default_manager.all()
        if self.select_related:
            qs = qs.select_related(*self.select_related)
        if self.prefetch_related:
            qs = qs.prefetch_related(*self.prefetch_related)
        if self.soft_delete and not include_archived:
            qs = qs.filter(deleted_at__isnull=True)
        if self.delegation_lookup:
            # Solo quien ve todas las delegaciones y no eligió una en la franja de arriba recibe todos los registros.
            delegation = active_delegation(request)
            if delegation is not None:
                qs = qs.filter(**{self.delegation_lookup: delegation})
        return qs

    def is_archived(self, obj):
        return self.soft_delete and obj.deleted_at is not None

    def apply_search(self, qs, text):
        """Busca cada palabra en alguno de los search_fields.

        Todas las palabras deben aparecer (en el mismo campo o en distintos). No importan las
        mayúsculas ni las tildes ("nunez" encuentra a "Núñez") y un RUT se encuentra se escriba
        con o sin puntos y guion; ver core/search.py. Si el mantenedor tiene códigos, "DEL02" encuentra
        el registro con ese código.

        Solo se usan las primeras SEARCH_WORDS palabras: cada una agrega condiciones a la
        consulta y un texto larguísimo la dejaría demasiado grande para la base de datos.
        """
        words = text.split()[:SEARCH_WORDS]
        for word in words:
            pattern = word_pattern(word)
            condition = models.Q()
            for name in self.search_fields:
                condition |= models.Q(**{f"{name}__iregex": pattern})
            number = number_in_code(word, self.code_prefix)
            if number is not None:
                condition |= models.Q(pk=number)  # el código no se guarda: "DEL02" busca el registro de id 2
            qs = qs.filter(condition)
        if words and self.search_distinct:
            qs = qs.distinct()
        return qs

    def filter_field(self, name):
        """Campo de un filtro. Puede ser una ruta, como «role_profile__status» (el estado en la ficha de un rol)."""
        found = field_for_path(self.model, name)
        if found is None:
            raise FieldDoesNotExist(f"{self.model.__name__} no tiene el campo «{name}» para filtrar.")
        return found

    def build_filters(self, request):
        """Filtros del listado con sus opciones; ignora valores que no sean opciones válidas."""
        specs = []
        for name in self.list_filters:
            if name == "delegation" and self.delegation_lookup and active_delegation(request) is not None:
                continue  # con una delegación activa todo el listado es de ella: el filtro no tendría qué elegir
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
                # El estado sale de deleted_at: Activo es no archivado e Inactivo es archivado.
                qs = qs.filter(deleted_at__isnull=spec.selected == STATE_ACTIVE)
                continue
            model_field = self.filter_field(spec.name)
            value = spec.selected
            if isinstance(model_field, models.BooleanField):
                value = value == "1"
            qs = qs.filter(**{spec.name: value})
        return qs

    def scope_summary(self, request):
        """«Delegación: DEL02 · Delegación Norte» si el listado se limita a una delegación; vacío si trae todas."""
        if not self.delegation_lookup:
            return ""
        delegation = active_delegation(request)
        if delegation is None:
            return ""
        return f"Delegación: {registry.get('delegaciones').code_of(delegation)} · {delegation.name}"

    def filter_summary(self, text, filters, archived):
        """Texto con la búsqueda y los filtros aplicados, para el encabezado del archivo de Excel."""
        parts = []
        if text:
            parts.append(f"Búsqueda: «{text}»")
        for spec in filters:
            if spec.selected:
                parts.append(f"{spec.label}: {dict(spec.options)[spec.selected]}")
        if archived:
            parts.append("incluye archivados")
        return "; ".join(parts) if parts else "Sin filtros"

    # -- celdas y filas ---------------------------------------------------

    def raw_value(self, obj, path_):
        """Valor de una columna: el código, el calculado si la columna es de `computed`, y si no, el del modelo."""
        if path_ == CODE_COLUMN:
            return self.code_of(obj)
        if path_ in self.computed:
            return self.computed[path_](obj)
        return get_raw(obj, path_)

    def badge_label(self, column, raw):
        """Texto de una insignia: el de las opciones del campo del modelo o, en una columna calculada, el de computed_choices."""
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
            # Solo un #RRGGBB exacto llega a la muestra de color; cualquier otro valor se muestra como texto.
            return Cell(kind="color", text=text, color=text if HEX_COLOR.fullmatch(text) else "")
        if isinstance(raw, str) and column.path != "__str__":
            return Cell(text=raw)  # texto escrito por el usuario: se muestra tal cual
        # El nombre de un registro (Actividad, Período, Meta) lleva la fecha en formato ISO.
        return Cell(text=ui.humanize_dates(raw))

    def make_row(self, request, obj, columns=None, actions=True):
        columns = columns or self.columns
        cells = [self.make_cell(obj, c) for c in columns]
        for column, cell in zip(columns, cells, strict=True):
            cell.link = column.link
            # La columna que lleva el enlace nunca queda vacía: si el campo no tiene
            # texto (un contacto sin nombre, por ejemplo) se muestra el nombre del registro.
            if column.link and not cell.text:
                cell.text = ui.humanize_dates(obj)
            # Un texto corto (una fecha, un RUT, "Delegación Norte") o un nombre con enlace no se parte en dos líneas.
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
            # Archivar, restaurar y eliminar piden el permiso delete del modelo; los botones solo salen si se tiene.
            if self.can_archive_here(request, obj):
                if row.archived:
                    row.restore_url = self.url("restore", obj.pk)
                else:
                    row.archive_url = self.url("archive", obj.pk)
                    row.archive_blocked = " ".join(self.archive_blockers(obj))
            if self.can_delete_here(request, obj):
                row.delete_url = self.url("delete", obj.pk)
                row.delete_blocked = " ".join(self.delete_blockers(obj))
        return row

    def detail_cells(self, obj):
        """Pares (etiqueta, celda) para la ficha: los campos del modelo en su orden.

        Cada valor se muestra igual que en el listado cuando el modelo lo tiene como columna.
        """
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
        """Pares (etiqueta, celda) que se agregan al final de la ficha. Se redefine por modelo."""
        return []

    def record_meta(self, obj):
        """Línea de abajo de la ficha: cuándo se creó, se cambió o se archivó el registro."""
        text = (
            f"Creado el {ui.fmt_datetime(obj.created_at)}. "
            f"Última actualización el {ui.fmt_datetime(obj.updated_at)}."
        )
        if obj.deleted_at:
            text += f" Archivado el {ui.fmt_datetime(obj.deleted_at)}."
        return text

    # -- exportación a Excel ----------------------------------------------

    def export_value(self, obj, column):
        """Valor de una celda para Excel: números y fechas conservan su tipo; el resto sale como texto."""
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

    # -- formularios ------------------------------------------------------

    @property
    def form_class(self):
        if self._form_class is None:
            self._form_class = modelform_factory(
                self.model, form=self.form_base, fields=list(self.form_fields)
            )
        return self._form_class

    def form_class_for(self, creating):
        """Formulario de alta si el mantenedor tiene uno propio (el ingreso de atención) y, si no, el de siempre."""
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
        """Valores iniciales al crear. Acepta ?campo=id para claves foráneas.

        Así, desde la ficha de una actividad se abre el formulario de gestión con la
        actividad ya elegida. El formulario igual valida que el usuario pueda usarla.
        """
        initial = {}
        for name in self.create_fields or self.form_fields:
            value = request.GET.get(name, "")
            # Un campo del formulario que no es del modelo (el solicitante del ingreso de atención) no se llena así.
            model_field = field_for_path(self.model, name)
            if is_id(value) and model_field is not None and model_field.is_relation:
                initial[name] = value
        return initial

    def initial_values(self, request):
        """Valores iniciales propios de cada modelo; se redefine en core/registry.py."""
        return {}

    def extra_actions(self, request, obj):
        """Botones extra en la ficha: lista de (texto, url, ícono). Se redefine por modelo."""
        return []

    def prepare_object(self, request, obj, creating, form):
        """Último ajuste antes de guardar; la delegación nunca la decide el formulario.

        Es la delegación en la que trabaja la persona (la del selector de la franja de arriba). Solo el superusuario
        que no eligió ninguna puede elegirla en el formulario.
        """
        if self.delegation_lookup and hasattr(obj, "delegation_id"):
            delegation = request_delegation(request)
            if delegation is not None:
                obj.delegation = delegation

    def after_save(self, request, obj, form, creating):
        """Trabajo extra justo después de guardar, dentro de la misma transacción."""

    # -- textos -----------------------------------------------------------

    @property
    def new_label(self):
        """Texto de los botones para crear: "Nueva actividad", "Nuevo servicio"."""
        return f"{'Nueva' if self.gender == 'f' else 'Nuevo'} {self.title.lower()}"

    def say(self, kind, obj):
        """Frase de confirmación en femenino o masculino: "Servicio «Vivienda» creado."."""
        words = {
            "created": ("creado", "creada"),
            "updated": ("actualizado", "actualizada"),
            "archived": ("archivado", "archivada"),
            "restored": ("restaurado", "restaurada"),
            "deleted": ("eliminado", "eliminada"),
        }
        word = words[kind][1 if self.gender == "f" else 0]
        name = ui.humanize_dates(obj)
        # Si el nombre del registro ya empieza con el del tipo ("Actividad 2026-10-06 · ..."),
        # se omite para no repetirlo en la frase.
        if name.lower().startswith(self.title.split()[0].lower()):
            return f"{self.title} {word}."
        return f"{self.title} «{name}» {word}."


# ---------------------------------------------------------------------------
# Registro de mantenedores
# ---------------------------------------------------------------------------


class Registry:
    """Guarda los Crud por slug y arma sus direcciones."""

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


# ---------------------------------------------------------------------------
# Vistas
# ---------------------------------------------------------------------------


class CrudView(LoginRequiredMixin, View):
    """Base de las vistas: exige sesión iniciada y el permiso del modelo."""

    crud = None
    action = "view"  # permiso que pide la vista: view, add o change

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not self.crud.has_perm(request.user, self.action):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get_object(self, request, pk):
        """Busca el registro solo entre los que el usuario puede ver (404 si no)."""
        queryset = self.crud.get_queryset(request, include_archived=True)
        return get_object_or_404(queryset, pk=pk)

    def breadcrumbs(self, *extra):
        # Cada elemento es (texto, dirección); el texto ya viene listo para mostrarse.
        trail = [("Inicio", reverse("core:dashboard"))]
        if self.crud.has_perm(self.request.user, "view"):
            trail.append((self.crud.list_title, self.crud.url("list")))
        trail.extend(extra)
        return trail


def query_string(request, drop=(), **updates):
    """Parámetros actuales de la URL con cambios, para armar enlaces de orden y páginas."""
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
    """Filas por página de los listados: las que la persona eligió en esta sesión, o PAGE_SIZE.

    La elección se guarda en request.session (ver set_page_size en core/views.py). Aquí se revisa
    otra vez contra PAGE_SIZES por si la sesión trajera otro valor.
    """
    size = request.session.get(SESSION_PAGE_SIZE)
    return size if size in PAGE_SIZES else PAGE_SIZE


class CrudListView(CrudView):
    """Listado con búsqueda, filtros, orden, paginador y descarga a Excel (?formato=xlsx)."""

    template_name = "core/crud/list.html"
    columns = None  # otro conjunto de columnas distinto del mantenedor (lo usa Atención)
    export_title = ""  # título y nombre del Excel si no son los del mantenedor
    export_slug = ""

    def get_columns(self, request):
        return self.columns if self.columns is not None else self.crud.columns

    def extra_context(self, request):
        """Datos que una pantalla basada en este listado agrega a la plantilla."""
        return {}

    def get(self, request):
        crud = self.crud
        columns = self.get_columns(request)
        filters = crud.build_filters(request)
        # Con el filtro Estado en «Inactivo» se listan los archivados, igual que con «Incluir archivados».
        state = next((spec.selected for spec in filters if spec.name == STATE_FILTER), "")
        archived = crud.soft_delete and (request.GET.get("archivados") == "1" or state == STATE_INACTIVE)
        qs = crud.get_queryset(request, include_archived=archived)

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
        """Descarga en Excel lo mismo que muestra el listado (con su búsqueda, filtros y orden)."""
        crud = self.crud
        scope = crud.scope_summary(request)  # el archivo dice de qué delegación son las filas
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
            "archive_blocked": " ".join(crud.archive_blockers(obj)) if can_archive and not archived else "",
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
                # Si la columna con enlace no viene en esta tabla, se enlaza la primera.
                if row.cells and not any(cell.link for cell in row.cells):
                    row.cells[0].link = True
            block = RelatedBlock(title=rel.title, columns=columns, rows=rows, total=total)
            if not self.crud.is_archived(obj) and related_crud.can_add(request.user):
                block.add_url = f"{related_crud.url('create')}?{rel.field}={obj.pk}"
                block.add_label = f"Agregar {related_crud.title.lower()}"
            blocks.append(block)
        return blocks


class CrudFormView(CrudView):
    """Parte común de crear y editar.

    Con ?modal=1 el formulario se pide desde la ventana modal de la pantalla (core/static/core/js/crud-modal.js):
    se responde solo con el contenido de la ventana y, al guardar, con un JSON en vez de una redirección.
    La cabecera X-Modal le dice al navegador qué llegó: "form" (el formulario) o "saved" (se guardó).
    Sin JavaScript (o abriendo el enlace en otra pestaña) todo sigue funcionando como páginas normales.
    """

    def in_modal(self, request):
        return request.GET.get("modal") == "1"

    def make_form(self, request, instance=None, data=None, initial=None):
        form_class = self.crud.form_class_for(creating=instance is None)
        return form_class(
            data=data, instance=instance, initial=initial, request=request, crud=self.crud
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
            "archive_blocked": " ".join(crud.archive_blockers(obj)) if can_archive else "",
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
        """Avisa que se guardó y decide a dónde ir: a la ficha, o a un formulario nuevo si se pidió "agregar otro"."""
        again = "_addanother" in request.POST and self.crud.can_add(request.user)
        if self.in_modal(request):
            # La ventana modal no cambia de página. Con "agregar otro" el aviso se muestra dentro de la
            # ventana; si no, la página se recarga y el aviso sale arriba, como siempre.
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

    def save(self, request, form, creating):
        obj = form.save(commit=False)
        # Copia del registro como está guardado ahora, para dejar en la auditoría qué cambió.
        before = None if creating else self.crud.model._default_manager.get(pk=obj.pk)
        self.crud.prepare_object(request, obj, creating, form)
        with transaction.atomic():
            obj.save()
            form.save_m2m()
            self.crud.after_save(request, obj, form, creating)
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
            obj = self.save(request, form, creating=True)
            return self.finish(request, obj, self.crud.say("created", obj))
        return self.render_form(request, form, None)


class ChangeObjectMixin:
    """Carga un registro visible para el usuario y comprueba que pueda modificarlo."""

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
            # Otra persona guardó el registro después de que se abrió este formulario.
            # Se avisa y se muestra lo que escribió esta persona; si guarda otra vez, se
            # conservan sus datos (el formulario ya trae la marca nueva).
            form.is_valid()
            form.add_error(
                None,
                "Otra persona modificó este registro mientras lo editabas. "
                "Revisa los datos y, si quieres conservar los tuyos, vuelve a guardar.",
            )
            return self.render_form(request, form, obj)
        if form.is_valid():
            obj = self.save(request, form, creating=False)
            return self.finish(request, obj, self.crud.say("updated", obj))
        return self.render_form(request, form, obj)


class ArchiveObjectMixin:
    """Carga un registro visible para el usuario y comprueba que pueda archivarlo o restaurarlo.

    Archivar y restaurar son parte de «Eliminar»: piden el permiso delete del modelo (no el de editar) y,
    como todo, solo se alcanzan los registros de la propia delegación (404 si es de otra).
    """

    action = "delete"

    def load(self, request, pk):
        obj = self.get_object(request, pk)
        if not self.crud.can_archive_object(request, obj):
            raise PermissionDenied
        return obj

    def blocked_text(self, verb, obj, reasons):
        """Frase de por qué no se pudo: «No se puede archivar el tipo de atención «Social»: tiene 2 sub atenciones activas.»"""
        return f"No se puede {verb} {self.crud.title.lower()} «{ui.humanize_dates(obj)}»: {' '.join(reasons)}"


class CrudArchiveView(ArchiveObjectMixin, CrudView):
    """Archiva un registro (borrado lógico). GET muestra la confirmación; POST archiva.

    Si el registro está en uso (el mantenedor lo dice con archive_blockers), la confirmación muestra el motivo
    y no ofrece archivar; y si alguien envía el formulario igual, el servidor lo rechaza.
    """

    def get(self, request, pk):
        obj = self.load(request, pk)
        if obj.deleted_at is not None:
            messages.info(request, "Este registro ya estaba archivado.")
            return redirect(self.crud.url("detail", obj.pk))
        context = {
            "crud": self.crud,
            "obj": obj,
            "obj_name": ui.humanize_dates(obj),
            "blockers": self.crud.archive_blockers(obj),
            "cancel_url": self.crud.url("detail", obj.pk),
            "breadcrumbs": self.breadcrumbs(
                (ui.humanize_dates(obj), self.crud.url("detail", obj.pk)), ("Archivar", None)
            ),
        }
        return render(request, "core/crud/archive_confirm.html", context)

    def post(self, request, pk):
        obj = self.load(request, pk)
        if obj.deleted_at is None:
            reasons = self.crud.archive_blockers(obj)
            if reasons:
                messages.error(request, self.blocked_text("archivar", obj, reasons))
                return redirect(self.crud.url("detail", obj.pk))
            obj.deleted_at = timezone.now()
            with transaction.atomic():
                obj.save(update_fields=["deleted_at", "updated_at"])
                log_event(
                    request.user,
                    "Registro archivado",
                    obj,
                    previous="deleted_at=None",
                    new=f"deleted_at={obj.deleted_at.isoformat()}",
                )
            messages.success(request, self.crud.say("archived", obj))
        return redirect(self.crud.url("list"))


class CrudRestoreView(CrudArchiveView):
    """Restaura un registro archivado. Solo acepta POST."""

    http_method_names = ["post", "options"]

    def post(self, request, pk):
        obj = self.load(request, pk)
        if obj.deleted_at is not None:
            reasons = self.crud.restore_blockers(obj)
            if reasons:
                messages.error(request, self.blocked_text("restaurar", obj, reasons))
                return redirect(self.crud.url("detail", obj.pk))
            previous = f"deleted_at={obj.deleted_at.isoformat()}"
            obj.deleted_at = None
            with transaction.atomic():
                obj.save(update_fields=["deleted_at", "updated_at"])
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
    """Elimina de verdad un registro (solo en los mantenedores con deletable, como los perfiles).

    GET pide la confirmación y POST elimina. Pide el permiso delete del modelo y se niega si el registro está
    en uso (delete_blockers). La eliminación queda en la auditoría, y si la base de datos la rechaza porque
    otros registros dependen de este, no queda nada anotado ni se avisa un éxito falso.
    """

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
                obj.delete()
        except models.ProtectedError:
            messages.error(
                request,
                f"No se puede eliminar {self.crud.title.lower()} «{name}»: otros registros dependen de él.",
            )
            return redirect(self.crud.url("detail", obj.pk))
        messages.success(request, text)
        return redirect(self.crud.url("list"))
