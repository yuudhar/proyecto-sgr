"""Formularios de las pantallas web.

CrudForm es el formulario base de todos los mantenedores: aplica el estilo de
Bootstrap, valida los formatos (RUT, teléfono, correo...) con las reglas de core/rules.py
y acota las listas desplegables igual que el Admin (formfield_for_foreignkey en
core/admin_mixins.py): quien trabaja en una delegación (la suya o la que eligió en la franja de arriba) solo elige
registros de esa delegación.
"""

import re
from decimal import Decimal

from django import forms
from django.contrib.auth import password_validation
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.contrib.auth.models import Group, Permission, User
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils import timezone
from django.utils.html import format_html, format_html_join

from accounts.delegations import stored_delegation_ids
from accounts.models import RoleProfile, UserProfile, group_is_global, role_details
from core import ui
from core.access import default_delegation, request_delegation, request_officer
from core.models import BaseModel
from core.roles import MODULE_LABELS, SYSTEM_GROUPS, managed_permissions, permission_key
from core.rules import collapse_spaces, get_rule
from core.search import plain_letter, word_pattern
from core.widgets import ColorWidget, DelegationsWidget, DependentSelect, LookupWidget, PermissionMatrixWidget, RolesWidget
from evidence.models import Validation
from organization.models import Beneficiary, Delegation, Item, Officer
from planning.models import Goal, Period


def password_help():
    """Lista de requisitos de una contraseña nueva: los mismos que revisan los validadores de settings.py."""
    rules = (
        "No puede parecerse a tus otros datos personales.",
        "Debe tener al menos 8 caracteres.",
        "No puede ser una contraseña de uso común.",
        "No puede ser solo de números.",
    )
    return format_html("<ul>{}</ul>", format_html_join("", "<li>{}</li>", ((rule,) for rule in rules)))


class BootstrapFormMixin:
    """Agrega las clases de Bootstrap a los campos y marca los que traen errores."""

    def style_fields(self):
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxSelectMultiple):
                continue  # sus casillas ya traen las clases de Bootstrap (ver core/widgets.py)
            if isinstance(widget, (forms.CheckboxInput, forms.RadioSelect)):
                css = "form-check-input"
            elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
                css = "form-select"
            else:
                css = "form-control"
            widget.attrs["class"] = f"{widget.attrs.get('class', '')} {css}".strip()
            if isinstance(field, forms.DecimalField) and field.max_digits:
                # El número más grande que cabe en la columna: así lo avisa la validación de la página y no Django.
                places = field.decimal_places or 0
                widget.attrs.setdefault("max", str(Decimal(10) ** (field.max_digits - places) - Decimal(1).scaleb(-places)))
            if isinstance(widget, forms.Textarea):
                widget.attrs.pop("cols", None)
                if str(widget.attrs.get("rows", "10")) == "10":  # 10 es el valor por defecto de Django
                    widget.attrs["rows"] = 4

    def polish_choices(self):
        """Textos en español para la opción vacía y fechas legibles en los nombres."""
        for field in self.fields.values():
            blank = "Selecciona una opción" if field.required else "Sin selección"
            if isinstance(field, forms.ModelChoiceField):
                if field.empty_label is not None:
                    field.empty_label = blank
                field.label_from_instance = ui.humanize_dates
            elif isinstance(field, forms.ChoiceField) and field.choices and field.choices[0][0] == "":
                field.choices = [("", blank), *list(field.choices)[1:]]

    def mark_invalid(self, name):
        """Marca el campo como inválido (una sola vez) para que la página lo pinte y lo avise."""
        if name in self.fields:
            attrs = self.fields[name].widget.attrs
            if "is-invalid" not in attrs.get("class", "").split():
                attrs["class"] = f"{attrs.get('class', '')} is-invalid".strip()

    def add_error(self, field, error):
        super().add_error(field, error)
        # También se marcan los errores que una vista agrega después de validar (un código vencido, por ejemplo).
        if self.is_bound and field:
            self.mark_invalid(field)

    def full_clean(self):
        super().full_clean()
        if self.is_bound:
            for name in self.errors:
                self.mark_invalid(name)


class PortalAuthenticationForm(BootstrapFormMixin, AuthenticationForm):
    """Formulario de inicio de sesión con el estilo de las pantallas."""

    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": (
            "El usuario, el correo o la contraseña no son correctos. "
            "Revisa que estén bien escritos: se distingue entre mayúsculas y minúsculas en la contraseña "
            "y en el usuario."
        ),
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Se ingresa con el usuario o con el correo (accounts/backends.py); un correo puede ser más largo que un usuario.
        self.fields["username"].label = "Usuario o correo"
        self.fields["username"].max_length = 254
        self.fields["username"].widget.attrs.update(
            {"autofocus": True, "autocomplete": "username", "maxlength": "254"}
        )
        self.fields["password"].label = "Contraseña"
        self.fields["password"].widget.attrs.update({"autocomplete": "current-password"})
        self.style_fields()


class CrudForm(BootstrapFormMixin, forms.ModelForm):
    """Formulario base de los mantenedores (ver core/crud.py)."""

    note = ""  # línea de texto bajo los campos (el ingreso de atención avisa qué se completa solo)

    def __init__(self, *args, request=None, crud=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.request = request
        self.crud = crud
        self.hide_archived_choices()
        self.polish_choices()
        if crud is not None and crud.delegation_lookup:
            # La delegación en la que trabaja la persona: solo el superusuario que ve todas queda sin límite.
            delegation = request_delegation(request)
            if delegation is not None:
                self.limit_to_delegation(delegation)
        if crud is not None:
            for name, text in crud.labels.items():
                if name in self.fields:
                    self.fields[name].label = text
            for name, text in crud.help_texts.items():
                if name in self.fields:
                    self.fields[name].help_text = text
            if self.instance.pk:
                # Se piden al crear; al editar se muestran pero ya no se pueden cambiar.
                for name in crud.readonly_on_edit:
                    if name in self.fields:
                        self.fields[name].disabled = True
        self.customize_fields()
        self.apply_rules()
        self.use_date_inputs()
        self.style_fields()

    def customize_fields(self):
        """Gancho: un formulario puede cambiar aquí sus campos antes de que se les dé estilo."""

    def apply_rules(self):
        """Pasa a cada campo con regla de formato los atributos data-* que lee core/js/validation.js."""
        if self.crud is None:
            return
        for name, rule_name in self.crud.rules.items():
            if name in self.fields:
                self.fields[name].widget.attrs.update(get_rule(rule_name).attrs())

    def clean(self):
        """Aplica las reglas de formato: arregla el texto (espacios, puntos del RUT) o marca el error."""
        cleaned = super().clean()
        if self.crud is None:
            return cleaned
        for name, rule_name in self.crud.rules.items():
            field = self.fields.get(name)
            value = cleaned.get(name)
            if field is None or field.disabled or not value or not isinstance(value, str):
                continue
            fixed, error = get_rule(rule_name).apply(value)
            if error:
                self.add_error(name, error)
            else:
                cleaned[name] = fixed
        self.check_unique_names(cleaned)
        self.crud.validate_form(self, cleaned)
        return cleaned

    def check_unique_names(self, cleaned):
        """Los campos de crud.unique_names no pueden repetirse sin distinguir mayúsculas ni espacios de más.

        La base de datos solo detecta el repetido exacto: «Norte» y «norte» entrarían los dos. Aquí se comparan
        sin mayúsculas (casefold, que también entiende la Ñ y las tildes) y contra todos los registros, también
        los archivados, porque restaurar un repetido rompería la regla. Una entrada como ("name", "delegation")
        pide que el nombre sea único solo dentro de la misma delegación; si el campo de alcance no está en el
        formulario se toma del registro (el tipo de atención no tiene tipo padre).
        """
        for spec in self.crud.unique_names:
            name, *scope = (spec,) if isinstance(spec, str) else spec
            value = cleaned.get(name)
            if name not in self.fields or not value or not isinstance(value, str) or self.has_error(name):
                continue
            filters = {}
            for field_name in scope:
                if field_name in self.fields:
                    if self.has_error(field_name):
                        break  # el alcance está mal escrito: ese error se muestra primero
                    filters[field_name] = cleaned.get(field_name)
                else:
                    filters[field_name] = getattr(self.instance, field_name)
            else:
                model = self._meta.model
                soft = issubclass(model, BaseModel)
                others = model._default_manager.filter(**filters)
                if self.instance.pk:
                    others = others.exclude(pk=self.instance.pk)
                wanted = " ".join(value.split()).casefold()
                for other_name, deleted_at in others.values_list(name, "deleted_at" if soft else name):
                    if " ".join(str(other_name).split()).casefold() == wanted:
                        label = str(self.fields[name].label or name).lower()
                        self.add_error(name, self.crud.duplicate_message(label, soft and deleted_at is not None))
                        break

    def use_date_inputs(self):
        """Los campos de fecha usan el selector de fecha del navegador."""
        for field in self.fields.values():
            if isinstance(field, forms.DateField) and not isinstance(
                field, forms.DateTimeField
            ):
                field.widget = forms.DateInput(
                    attrs={"type": "date"}, format="%Y-%m-%d"
                )

    def current_value(self, name):
        """Valor actual (pk) de una clave foránea del registro que se edita."""
        return getattr(self.instance, f"{name}_id", None)

    def allowed(self, queryset, name):
        """Registros no archivados, más el que ya tiene guardado el objeto."""
        condition = Q(deleted_at__isnull=True)
        current = self.current_value(name)
        if current is not None:
            condition |= Q(pk=current)
        return queryset.filter(condition)

    def hide_archived_choices(self):
        """Las listas desplegables no ofrecen registros archivados."""
        for name, field in self.fields.items():
            if isinstance(field, forms.ModelChoiceField):
                model = field.queryset.model
                if issubclass(model, BaseModel):
                    field.queryset = self.allowed(model._default_manager.all(), name)

    def limit_to_delegation(self, delegation):
        """Acota las listas a la delegación en la que trabaja el usuario (misma regla del Admin)."""
        from evidence.models import Evidence
        from operations.models import Activity
        from organization.models import Delegation, Officer, Territory

        for name, field in self.fields.items():
            if name == "delegation":
                field.queryset = Delegation.objects.filter(pk=delegation.pk)
                field.disabled = True
                self.initial["delegation"] = delegation.pk
            elif name.endswith("officer"):
                field.queryset = self.allowed(
                    Officer.objects.filter(delegation=delegation), name
                )
            elif name == "territory":
                field.queryset = self.allowed(
                    Territory.objects.filter(delegation=delegation), name
                )
            elif name == "activity":
                field.queryset = self.allowed(
                    Activity.objects.filter(delegation=delegation), name
                )
            elif name == "evidence":
                field.queryset = self.allowed(
                    Evidence.objects.filter(activity__delegation=delegation), name
                )


class DelegationForm(CrudForm):
    """Delegación: nombre, dirección, comuna, encargado (se elige de los funcionarios o se escribe), color y estado.

    La dirección y la comuna se piden siempre (A1: «Código, nombre, dirección, comuna y estado»); en la base
    pueden estar vacías porque las delegaciones anteriores a la v8 no las tenían.
    """

    def customize_fields(self):
        for name in ("address", "commune"):
            if name in self.fields:
                self.fields[name].required = True
        officers = (
            Officer.objects.filter(deleted_at__isnull=True, status=Officer.Status.ACTIVE)
            .select_related("delegation", "position")
            .order_by("name")
        )
        options = [(officer.name, f"{officer.position} · {officer.delegation}") for officer in officers]
        self.fields["managers"].widget = LookupWidget(options=options)
        self.fields["color"].widget = ColorWidget()


class RoleForm(CrudForm):
    """Rol (perfil): nombre, descripción, alcance autorizado, estado y la matriz de permisos.

    La matriz tiene una fila por módulo y una columna por acción. Los perfiles del sistema (los que crea
    seed_roles) no cambian de nombre, de alcance ni de estado: las reglas de acceso y las cuentas de prueba
    cuentan con ellos («Coordinación» ve todas las delegaciones). Para crear, editar o eliminar en un módulo el
    perfil también debe poder verlo, si no, la pantalla a la que lo lleva al guardar le respondería 403. Los
    permisos que el perfil tenga y la matriz no muestre se conservan al guardar.

    La descripción, el alcance y el estado no son columnas del grupo de Django: se guardan en su ficha
    (accounts.RoleProfile) cuando el mantenedor termina de guardar el rol (RoleCrud.after_save).
    """

    description = forms.CharField(
        label="Descripción",
        max_length=255,
        widget=forms.Textarea(attrs={"rows": 2}),
        help_text="Qué puede hacer quien tenga este rol. Se muestra al asignarlo a un usuario.",
    )
    scope = forms.ChoiceField(
        label="Alcance autorizado",
        choices=RoleProfile.Scope.choices,
        initial=RoleProfile.Scope.OWN,
        help_text=(
            "Hasta dónde llega el rol: «Su delegación» (la de su funcionario) o «Todas las delegaciones». "
            "Los permisos de abajo dicen qué puede hacer dentro de ese alcance."
        ),
    )
    status = forms.ChoiceField(
        label="Estado",
        choices=RoleProfile.Status.choices,
        initial=RoleProfile.Status.ACTIVE,
        help_text="Un rol inactivo no se ofrece al asignar perfiles a un usuario.",
    )
    permissions = forms.ModelMultipleChoiceField(
        queryset=managed_permissions(),
        required=False,
        label="Permisos",
        widget=PermissionMatrixWidget,
        help_text="Marca lo que puede hacer el perfil en cada módulo. Para crear, editar o eliminar también necesita «Ver».",
    )

    def customize_fields(self):
        if self.instance.pk and self.instance.name in SYSTEM_GROUPS:
            name = self.fields["name"]
            name.disabled = True
            name.help_text = "Es un perfil del sistema: las reglas de acceso lo buscan por su nombre y no se puede cambiar."
            for key, text in (
                ("scope", "Es un perfil del sistema: su alcance viene de fábrica y no se puede cambiar."),
                ("status", "Es un perfil del sistema: siempre está activo."),
            ):
                self.fields[key].disabled = True
                self.fields[key].help_text = text
        if self.instance.pk:
            self.initial["permissions"] = list(self.instance.permissions.values_list("pk", flat=True))
            details = role_details(self.instance)
            self.initial["description"] = details.description
            self.initial["scope"] = details.scope
            self.initial["status"] = details.status
        self.order_fields(["name", "description", "scope", "status", "permissions"])

    def clean_permissions(self):
        chosen = self.cleaned_data["permissions"]
        if not self.instance.pk:
            return chosen
        managed = list(managed_permissions().values_list("pk", flat=True))
        kept = self.instance.permissions.exclude(pk__in=managed).values_list("pk", flat=True)
        return Permission.objects.filter(Q(pk__in=[permission.pk for permission in chosen]) | Q(pk__in=list(kept)))

    def clean(self):
        cleaned = super().clean()
        chosen = cleaned.get("permissions")
        if chosen is not None:
            actions = {}
            for permission in chosen:
                key, action = permission_key(permission)
                actions.setdefault(key, set()).add(action)
            missing = [MODULE_LABELS[key] for key, found in actions.items() if key in MODULE_LABELS and "view" not in found]
            if missing:
                self.add_error(
                    "permissions",
                    f"Falta «Ver» en: {', '.join(sorted(missing))}. "
                    "Para crear, editar o eliminar en un módulo el perfil también tiene que poder verlo.",
                )
        self.check_scope_and_status(cleaned)
        return cleaned

    def check_scope_and_status(self, cleaned):
        """No se desactiva un rol que tiene usuarios ni se le quita el alcance a quien lo necesita.

        - Desactivar: el rol sigue asignado a esos usuarios; primero hay que cambiárselo (igual que para eliminarlo).
        - Pasar de «Todas las delegaciones» a «Su delegación»: un usuario sin funcionario solo puede existir si algún
          rol o su condición de Super Usuario le da todas las delegaciones; si no, quedaría sin delegación y
          todas las pantallas le responderían 403.
        """
        if not self.instance.pk:
            return
        before = role_details(self.instance)
        scope, status = cleaned.get("scope"), cleaned.get("status")
        users = self.instance.user_set.all()
        if status == RoleProfile.Status.INACTIVE and before.status == RoleProfile.Status.ACTIVE and users.exists():
            total = users.count()
            self.add_error(
                "status",
                f"Lo {'tiene' if total == 1 else 'tienen'} asignado {total} {'usuario' if total == 1 else 'usuarios'}. "
                "Cámbiales el rol desde Control de usuarios antes de desactivarlo.",
            )
        if scope == RoleProfile.Scope.OWN and before.scope == RoleProfile.Scope.ALL:
            other_global = Group.objects.filter(
                role_profile__scope=RoleProfile.Scope.ALL, role_profile__status=RoleProfile.Status.ACTIVE
            ).exclude(pk=self.instance.pk)
            stranded = (
                users.filter(is_superuser=False)
                .filter(Q(profile__isnull=True) | Q(profile__officer__isnull=True))
                .exclude(groups__in=other_global)
                .order_by("username")
            )
            names = list(stranded.values_list("username", flat=True)[:6])
            if names:
                shown = ", ".join(names[:5]) + (" y otros" if len(names) > 5 else "")
                self.add_error(
                    "scope",
                    f"No se puede limitar a «Su delegación»: {shown} no tiene funcionario y se quedaría sin delegación. "
                    "Asígnale un funcionario o cámbiale el rol desde Control de usuarios.",
                )


class ItemForm(CrudForm):
    """Ítem, tipo de atención o sub atención: el ítem padre solo puede ser un tipo (un ítem sin padre).

    Las reglas entre campos (no ser su propio padre, no cambiar el tipo de un ítem en uso) las revisa
    ItemRules en core/registry.py.
    """

    def customize_fields(self):
        if "description" in self.fields:
            self.fields["description"].widget = forms.Textarea(attrs={"rows": 2})
        field = self.fields.get("parent_item")
        if field is None:
            return
        types = Item.objects.filter(parent_item__isnull=True)
        current = self.current_value("parent_item")
        condition = Q(deleted_at__isnull=True)
        if current is not None:
            condition |= Q(pk=current)  # el tipo que ya tiene se sigue viendo aunque se haya archivado
        field.queryset = types.filter(condition).order_by("name")
        if self.instance.pk:
            field.queryset = field.queryset.exclude(pk=self.instance.pk)


class SubAttentionForm(ItemForm):
    """Sub atención: siempre pertenece a un Tipo de Atención activo."""

    def customize_fields(self):
        super().customize_fields()
        field = self.fields["parent_item"]
        field.required = True
        field.empty_label = "Selecciona un tipo de atención"


# Cuántas personas se ofrecen como sugerencia en el campo del solicitante. Es solo una ayuda para escribir:
# quien atiende puede escribir cualquier RUT o nombre, y el servidor lo busca en todo el catálogo.
LOOKUP_LIMIT = 2000

# Un RUT bien escrito que no está en Beneficiarios. A quien puede registrar beneficiarios se le dice que lo haga;
# a quien no puede (por ejemplo un Funcionario) se le dice que pida que lo registren.
UNKNOWN_RUT = "No hay ninguna persona con ese RUT en Beneficiarios."
UNKNOWN_RUT_CAN_REGISTER = " Regístrala primero en Beneficiarios o escribe su nombre."
UNKNOWN_RUT_CANNOT_REGISTER = " Pide que la registren en Beneficiarios o escribe su nombre."


def fold(text):
    """El texto sin mayúsculas, tildes ni espacios de más: «  María  PÉREZ » y «maria perez» quedan iguales."""
    return "".join(plain_letter(char) for char in collapse_spaces(text))


def looks_like_rut(text):
    """True si el texto son números, puntos y guiones (con la K del dígito verificador al final), como un RUT."""
    return re.fullmatch(r"[0-9][0-9.\-]*[0-9kK]", text) is not None and sum(char.isdigit() for char in text) >= 7


def find_beneficiary(text):
    """Busca a la persona que escribió quien atiende: por RUT (con o sin puntos y guion) o por su nombre completo.

    Devuelve (beneficiario, mensaje de error). Hay tres resultados posibles:
      - la persona está en Beneficiarios: (beneficiario, "");
      - el texto es un nombre que no está: (None, ""). Es un contacto escrito a mano y la atención se guarda
        con ese nombre, sin beneficiario;
      - no se puede decidir: (None, "motivo"). Un RUT mal escrito, un RUT que no está registrado o un nombre que
        tienen varias personas. Con un RUT no se adivina: no se guarda la atención a nombre de otra persona.
    """
    text = collapse_spaces(text)
    if looks_like_rut(text):
        rut, error = get_rule("rut").apply(text)
        if error:
            return None, error
        person = Beneficiary._default_manager.filter(rut=rut).first()
        if person is None:
            return None, UNKNOWN_RUT
        if person.deleted_at is not None:
            return None, "Esa persona está archivada en Beneficiarios. Restáurala para registrar su atención."
        return person, ""

    wanted = fold(text)
    first_word = text.split()[0] if text else ""
    candidates = Beneficiary.objects.filter(deleted_at__isnull=True, name__iregex=word_pattern(first_word))
    matches = [person for person in candidates if fold(person.name) == wanted]
    if len(matches) > 1:
        return None, "Hay más de una persona con ese nombre. Escribe su RUT para elegir a la correcta."
    return (matches[0] if matches else None), ""


class ActivityIntakeForm(CrudForm):
    """Ingreso de atención (Clase 8): lo que se pide al registrar una atención nueva.

    Se pide solo lo que quien atiende sabe en ese momento: quién es la persona (RUT o nombre), el tipo y la sub
    atención, y lo que pidió. Lo demás se completa solo y no se puede cambiar desde aquí: la fecha es la de hoy, la
    delegación es en la que trabaja quien atiende (la de su funcionario o la que eligió en la franja de arriba), el
    responsable es su funcionario y el estado parte en «Registrada». Si trabaja en una delegación que no es la de su
    funcionario, el responsable se elige entre los funcionarios de esa delegación, porque una actividad exige que el
    responsable sea de la misma delegación. El identificador (ATN00012) sale del id al guardar. Editar una atención
    usa el formulario completo de siempre.

    El solicitante se escribe en un solo campo: si es el RUT de alguien que está en Beneficiarios, o su nombre exacto,
    la atención queda vinculada a esa persona; si es un nombre que no está, se guarda como contacto escrito a mano.
    El Tipo de atención y la Sub atención son dos listas: la segunda solo ofrece las del tipo elegido y, si el tipo no
    tiene sub atenciones, la atención se guarda con el tipo mismo (el modelo guarda un solo ítem).
    """

    requester = forms.CharField(label="Solicitante (RUT o nombre)", max_length=100)
    attention_type = forms.ModelChoiceField(label="Tipo de atención", queryset=Item.objects.none())

    def customize_fields(self):
        self.person = None
        self.type_choices = Item.objects.filter(parent_item__isnull=True, deleted_at__isnull=True).order_by("name")
        self.fields["attention_type"].queryset = self.type_choices
        self.fields["attention_type"].empty_label = "Selecciona un tipo de atención"
        self.fields["requester"].help_text = (
            "Escribe el RUT (con o sin puntos y guion) o el nombre. Si la persona está en Beneficiarios, "
            "la atención queda vinculada a ella."
        )
        self.set_up_requester()
        self.set_up_sub_attention()
        self.set_up_description()
        self.set_up_profile()

    def set_up_description(self):
        """La descripción es obligatoria al registrar. En la base de datos sigue siendo opcional (editar una atención
        existente no la exige), así que esta regla vive solo en este formulario."""
        field = self.fields["request_description"]
        field.required = True
        field.label = "Descripción de la atención"
        field.widget.attrs["placeholder"] = "Describe la solicitud y los antecedentes necesarios."
        message = "Describe la solicitud: la descripción es obligatoria para registrar la atención."
        field.error_messages["required"] = message  # el mismo texto en el servidor y en el navegador
        field.widget.attrs["data-required-message"] = message

    def set_up_requester(self):
        people = Beneficiary.objects.filter(deleted_at__isnull=True).order_by("name")[:LOOKUP_LIMIT]
        options = [(person.rut, f"{person.name} · {person.address}" if person.address else person.name) for person in people]
        field = self.fields["requester"]
        field.widget = LookupWidget(options=options, search_label="Buscar por RUT, nombre o dirección")
        field.widget.attrs.update(
            {"autocomplete": "off", "maxlength": str(field.max_length), "placeholder": "Ej.: 11.111.111-1 o María Pérez"}
        )
        if self.instance.pk:
            field.initial = self.instance.contact_name

    def set_up_sub_attention(self):
        field = self.fields["item"]
        field.label = "Sub atención"
        field.required = False  # se exige solo si el tipo elegido tiene sub atenciones (ver check_attention)
        field.empty_label = "Selecciona una sub atención"
        field.help_text = "Es obligatoria cuando el tipo de atención tiene sub atenciones."
        field.label_from_instance = lambda item: f"{item.parent_item} · {item.name}"
        field.widget = DependentSelect(
            depends_on="id_attention_type",
            parent_attr="parent_item_id",
            empty_parent="Primero elige un tipo de atención",
            empty_children="Este tipo no tiene sub atenciones",
            cleared_message="Se limpió la sub atención porque no pertenece al tipo de atención elegido.",
            choose_if_options=True,
        )
        field.queryset = (
            Item.objects.filter(parent_item__isnull=False, deleted_at__isnull=True)
            .select_related("parent_item")
            .order_by("parent_item__name", "name")
        )

    def set_up_profile(self):
        """Perfil fijo: la delegación es el contexto en que trabaja quien atiende y la fecha es la de hoy.

        La delegación es la activa (A2: «La delegación debe completarse a partir del contexto autorizado del usuario»):
        la de su funcionario o la que eligió en la franja de arriba. El responsable es su funcionario cuando este es
        de esa delegación; si no, se elige uno de la delegación (el modelo exige que coincidan).
        """
        today = timezone.localdate()
        officer = request_officer(self.request)
        delegation = default_delegation(self.request)
        if delegation is not None:
            self.fields.pop("delegation", None)
            self.instance.delegation = delegation
        own = officer if officer is not None and (delegation is None or officer.delegation_id == delegation.pk) else None
        if own is not None:
            self.fields.pop("author_officer", None)
            self.instance.author_officer = own
        for name in ("delegation", "author_officer"):
            # El superusuario sin funcionario que ve todas elige la delegación y el funcionario; quien trabaja en otra
            # delegación elige solo el responsable (la lista ya trae únicamente los funcionarios de esa delegación).
            if name in self.fields:
                self.fields[name].required = True
        if "author_officer" in self.fields and delegation is not None:
            self.fields["author_officer"].help_text = f"Funcionario de {delegation} que realiza la atención."
        filled = [f"fecha de hoy ({ui.fmt_date(today)})"]
        if delegation is not None:
            filled.append(str(delegation))
        if own is not None:
            filled.append(f"responsable {own.name}")
        listing = filled[0] if len(filled) == 1 else f"{', '.join(filled[:-1])} y {filled[-1]}"
        self.note = f"Se completan solos: {listing}. El identificador se asigna al guardar."
        self.instance.date = today

    def clean(self):
        cleaned = super().clean()
        self.check_requester(cleaned)
        self.check_attention(cleaned)
        return cleaned

    def check_requester(self, cleaned):
        text = cleaned.get("requester")
        if not text or self.has_error("requester"):
            return
        person, error = find_beneficiary(text)
        if error:
            if error == UNKNOWN_RUT:
                user = getattr(self.request, "user", None)
                can_register = user is not None and user.has_perm("organization.add_beneficiary")
                error += UNKNOWN_RUT_CAN_REGISTER if can_register else UNKNOWN_RUT_CANNOT_REGISTER
            self.add_error("requester", error)
            return
        self.person = person
        # Con la persona encontrada se guarda su nombre; si no, lo que escribió quien atiende.
        self.instance.beneficiary = person
        name = person.name if person is not None else collapse_spaces(text)
        self.instance.contact_name = name[: self._meta.model._meta.get_field("contact_name").max_length]

    def check_attention(self, cleaned):
        kind = cleaned.get("attention_type")
        sub = cleaned.get("item")
        if kind is None or self.has_error("attention_type"):
            return
        if sub is not None and sub.parent_item_id != kind.pk:
            self.add_error("item", "Esa sub atención no pertenece al tipo de atención elegido.")
        elif sub is None:
            if Item.objects.filter(parent_item=kind, deleted_at__isnull=True).exists():
                self.add_error("item", "Elige una sub atención de este tipo de atención.")
            else:
                cleaned["item"] = kind  # un tipo sin sub atenciones se registra con el tipo mismo


def delegation_label(delegation):
    """«DEL02 · Nombre» (el código sale del id, igual que en el mantenedor de Delegaciones)."""
    from core.crud import registry

    return f"{registry.get('delegaciones').code_of(delegation)} · {delegation.name}"


class UserForm(CrudForm):
    """Usuario del sistema: cuenta, perfiles, funcionario (que define su delegación) y contraseña.

    La contraseña se pide al crear; al editar, dejarla en blanco la conserva. El superusuario no
    puede quitarse a sí mismo el acceso ni los permisos, para no quedar fuera del sistema.

    Las delegaciones adicionales (tabla Usuario_Rol_Delegacion) son las otras delegaciones, además de la de su
    funcionario, entre las que la persona puede elegir en la franja de arriba (A2).
    """

    officer = forms.ModelChoiceField(
        queryset=Officer.objects.none(),
        required=False,
        label="Funcionario",
        help_text=(
            "Define la delegación del usuario. Solo el Super Usuario y los perfiles con alcance sobre todas las "
            "delegaciones (como Coordinación) pueden quedar sin funcionario."
        ),
    )
    extra_delegations = forms.ModelMultipleChoiceField(
        queryset=Delegation.objects.none(),
        required=False,
        label="Delegaciones adicionales",
        widget=DelegationsWidget,
        help_text=(
            "Además de la de su funcionario, la persona podrá elegir estas delegaciones en la franja de arriba. "
            "Con una elegida, ve y registra solo lo de esa delegación. No hace falta marcarlas para quienes ven "
            "todas las delegaciones."
        ),
    )
    password1 = forms.CharField(
        label="Contraseña",
        required=False,
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )
    password2 = forms.CharField(
        label="Repite la contraseña",
        required=False,
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password", "data-match": "id_password1"}),
    )

    def customize_fields(self):
        creating = not self.instance.pk
        # Solo se ofrecen los roles activos, más los que el usuario ya tiene.
        groups = self.fields["groups"]
        offered = Q(role_profile__status=RoleProfile.Status.ACTIVE) | Q(role_profile__isnull=True)
        if not creating:
            offered |= Q(pk__in=self.instance.groups.values("pk"))
        groups.queryset = Group.objects.filter(offered).select_related("role_profile").order_by("pk")
        # Al cambiar el widget hay que pasarle las opciones del campo; si no, queda sin casillas.
        groups.widget = RolesWidget()
        groups.widget.choices = groups.choices
        for name in ("password1", "password2"):
            self.fields[name].required = creating
        # Con el correo la persona recupera su contraseña (accounts/recovery.py): sin él no podría. Al crear
        # es obligatorio; al editar solo si la cuenta ya tenía uno, para no bloquear cuentas antiguas sin correo.
        self.fields["email"].required = creating or bool(self.instance.email)
        if creating:
            self.fields["password1"].help_text = password_help()
        else:
            self.fields["password1"].help_text = "Déjala en blanco para conservar la contraseña actual."

        # Funcionarios activos que todavía no tienen usuario (más el que ya tiene este).
        taken = UserProfile.objects.filter(officer__isnull=False)
        if not creating:
            taken = taken.exclude(user=self.instance)
        officers = Officer.objects.filter(deleted_at__isnull=True, status=Officer.Status.ACTIVE)
        officers = officers.exclude(pk__in=taken.values("officer_id")).select_related("delegation")
        field = self.fields["officer"]
        field.queryset = officers.order_by("delegation__name", "name")
        field.label_from_instance = lambda officer: f"{officer.name} · {officer.delegation}"
        field.empty_label = "Sin funcionario"
        profile = getattr(self.instance, "profile", None) if not creating else None
        if profile is not None:
            self.initial["officer"] = profile.officer_id

        # Delegaciones que se pueden agregar: las activas, más las que el usuario ya tiene guardadas (para poder quitarlas).
        stored = stored_delegation_ids(self.instance) if not creating else set()
        offered = Delegation.objects.filter(
            Q(deleted_at__isnull=True, status=Delegation.Status.ACTIVE) | Q(pk__in=stored)
        )
        field = self.fields["extra_delegations"]
        field.queryset = offered.order_by("pk")
        field.label_from_instance = delegation_label
        if stored:
            self.initial["extra_delegations"] = sorted(stored)
        self.order_fields(
            [
                "username",
                "first_name",
                "last_name",
                "email",
                "password1",
                "password2",
                "groups",
                "officer",
                "extra_delegations",
            ]
        )

    def check_extra_delegations(self, cleaned, sees_everything):
        """Las delegaciones adicionales solo tienen sentido para quien no ve todas; la propia no se repite."""
        extras = list(cleaned.get("extra_delegations") or [])
        if not extras:
            return
        if sees_everything:
            self.add_error(
                "extra_delegations",
                "Este usuario ya ve todas las delegaciones (por ser Super Usuario o por su perfil): "
                "no necesita delegaciones adicionales. Desmárcalas.",
            )
            return
        officer = cleaned.get("officer")
        if officer is not None:
            # La delegación de su funcionario ya es suya: marcarla de nuevo no cambia nada, así que no se guarda dos veces.
            cleaned["extra_delegations"] = [d for d in extras if d.pk != officer.delegation_id]

    def _post_clean(self):
        # Con el usuario ya armado con lo escrito (nombre de usuario, nombre, correo), para que la regla de
        # "no parecerse a sus datos personales" compare con los datos nuevos.
        super()._post_clean()
        password = self.cleaned_data.get("password1") or ""
        if password and not self.has_error("password2"):
            try:
                password_validation.validate_password(password, user=self.instance)
            except ValidationError as error:
                self.add_error("password1", error.messages)

    def clean(self):
        cleaned = super().clean()
        username = cleaned.get("username")
        if username:
            same = User.objects.filter(username__iexact=username)
            if self.instance.pk:
                same = same.exclude(pk=self.instance.pk)
            if same.exists():
                self.add_error("username", "Ya existe un usuario con ese nombre, aunque cambien las mayúsculas.")

        email = cleaned.get("email")
        # Solo se revisa si el correo es nuevo o cambió: una cuenta antigua con un correo repetido se puede seguir editando.
        if email and (not self.instance.pk or email.lower() != (self.instance.email or "").lower()):
            same = User.objects.filter(email__iexact=email)
            if self.instance.pk:
                same = same.exclude(pk=self.instance.pk)
            if same.exists():
                self.add_error(
                    "email",
                    "Ese correo ya lo usa otro usuario. Cada cuenta necesita uno distinto "
                    "para poder recuperar su contraseña.",
                )

        password = cleaned.get("password1") or ""
        repeated = cleaned.get("password2") or ""
        if (password or repeated) and password != repeated:
            self.add_error("password2", "Las dos contraseñas deben ser iguales.")

        groups = cleaned.get("groups") or []
        sees_everything = bool(cleaned.get("is_superuser")) or any(group_is_global(group) for group in groups)
        if not cleaned.get("is_superuser"):
            if not groups:
                self.add_error("groups", "Elige al menos un perfil, o marca Super Usuario.")
            if not cleaned.get("officer") and not sees_everything:
                self.add_error(
                    "officer",
                    "Elige el funcionario: sin él, el usuario no tiene delegación. "
                    "Solo el Super Usuario y los perfiles con alcance sobre todas las delegaciones "
                    "(como Coordinación) pueden quedar sin funcionario.",
                )
        self.check_extra_delegations(cleaned, sees_everything)

        if self.instance.pk and self.request is not None and self.instance.pk == self.request.user.pk:
            if "is_active" in cleaned and not cleaned["is_active"]:
                self.add_error("is_active", "No puedes desactivar tu propia cuenta.")
            if self.instance.is_superuser and "is_superuser" in cleaned and not cleaned["is_superuser"]:
                self.add_error("is_superuser", "No puedes quitarte a ti mismo el perfil de Super Usuario.")
        return cleaned


class PortalPasswordChangeForm(BootstrapFormMixin, PasswordChangeForm):
    """Cambio de contraseña de quien tiene la sesión iniciada (pantalla Mi perfil)."""

    error_messages = {
        **PasswordChangeForm.error_messages,
        "password_mismatch": "Las dos contraseñas nuevas no son iguales.",
        "password_incorrect": "La contraseña actual no es correcta.",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["old_password"].label = "Contraseña actual"
        self.fields["new_password1"].label = "Contraseña nueva"
        self.fields["new_password1"].help_text = password_help()
        self.fields["new_password2"].label = "Repite la contraseña nueva"
        self.fields["new_password2"].help_text = ""
        self.fields["new_password2"].widget.attrs["data-match"] = "id_new_password1"
        self.fields["old_password"].widget.attrs.pop("autofocus", None)
        self.style_fields()

    def validate_password_for_user(self, user, password_field_name="new_password2"):
        # El aviso de una contraseña débil va en el campo de la contraseña nueva, no en el de repetirla.
        super().validate_password_for_user(user, "new_password1")


class PeriodForm(CrudForm):
    """Período: fechas con sentido, umbrales entre 0 y 100 y un solo período vigente a la vez."""

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get("start_date")
        end = cleaned.get("end_date")
        if start and end:
            if end < start:
                self.add_error("end_date", "La fecha de término no puede ser anterior a la de inicio.")
            else:
                days = cleaned.get("computable_days")
                calendar_days = (end - start).days + 1
                if days is not None and not 1 <= days <= calendar_days:
                    self.add_error(
                        "computable_days",
                        f"Los días computables van de 1 a {calendar_days}, los días del período.",
                    )
        collective = cleaned.get("collective_threshold")
        amber = cleaned.get("amber_threshold")
        if collective is not None and not 0 < collective <= 100:
            self.add_error("collective_threshold", "El umbral colectivo debe ser mayor que 0 y como máximo 100.")
            collective = None
        if amber is not None and not 0 <= amber <= 100:
            self.add_error("amber_threshold", "El umbral ámbar debe estar entre 0 y 100.")
            amber = None
        if collective is not None and amber is not None and amber >= collective:
            self.add_error("amber_threshold", "El umbral ámbar debe ser menor que el umbral colectivo.")
        cap = cleaned.get("weighted_cap")
        if cap is not None and cap <= 0:
            self.add_error("weighted_cap", "El tope ponderado debe ser mayor que 0.")
        if cleaned.get("status") == Period.Status.ACTIVE:
            # El tablero y los informes toman "el período vigente": tiene que ser uno solo.
            others = Period.objects.filter(deleted_at__isnull=True, status=Period.Status.ACTIVE)
            if self.instance.pk:
                others = others.exclude(pk=self.instance.pk)
            if others.exists():
                self.add_error("status", "Ya hay un período vigente. Ciérralo antes de dejar este como vigente.")
        return cleaned


class GoalForm(CrudForm):
    """Meta: se asigna a un funcionario o a un cargo, con ponderador válido y sin repetirse."""

    def clean(self):
        cleaned = super().clean()
        officer = cleaned.get("officer")
        position = cleaned.get("position")
        assigned = bool(officer) != bool(position)
        if officer and position:
            self.add_error("position", "Elige un funcionario o un cargo, no los dos.")
        elif not officer and not position:
            self.add_error("officer", "Elige un funcionario o un cargo para asignar la meta.")
        weight = cleaned.get("weight")
        if weight is not None and not 0 < weight <= 100:
            self.add_error("weight", "El ponderador debe ser mayor que 0 y como máximo 100.")
        version = cleaned.get("version")
        if version is not None and version < 1:
            self.add_error("version", "La versión parte en 1.")
        item = cleaned.get("item")
        period = cleaned.get("period")
        if assigned and item and period:
            same = Goal.objects.filter(
                deleted_at__isnull=True, item=item, period=period, officer=officer, position=position
            )
            if self.instance.pk:
                same = same.exclude(pk=self.instance.pk)
            if same.exists():
                self.add_error(
                    "item",
                    "Ya existe una meta de este ítem para ese funcionario o cargo en el período. "
                    "Edita la existente y sube su versión.",
                )
        return cleaned


class IndicatorForm(CrudForm):
    """Indicador: el avance, el cumplimiento y la ponderación no pueden ser negativos."""

    def clean(self):
        cleaned = super().clean()
        for name in ("progress", "compliance", "weighting"):
            value = cleaned.get(name)
            if value is not None and value < 0:
                self.add_error(name, "No puede ser negativo.")
        return cleaned


class AdjustmentForm(CrudForm):
    """Ajuste: el valor es un porcentaje mayor que 0 y de hasta 100."""

    def clean_percentage_value(self):
        value = self.cleaned_data["percentage_value"]
        if not 0 < value <= 100:
            raise forms.ValidationError("El valor debe ser mayor que 0 y como máximo 100.")
        return value


class ValidationForm(BootstrapFormMixin, forms.ModelForm):
    """Formulario para revisar una evidencia: decisión, resultado y observación.

    La evidencia y el funcionario verificador no se piden aquí: los define la vista.
    Solo el superusuario, que no tiene un funcionario propio, elige quién revisa.
    """

    reviewer_officer = forms.ModelChoiceField(
        queryset=Officer.objects.none(),
        label="Funcionario verificador",
    )

    class Meta:
        model = Validation
        fields = ("decision", "result", "notes")
        widgets = {
            "decision": forms.RadioSelect,
            "notes": forms.Textarea(attrs={"rows": 4}),
        }
        help_texts = {
            "result": "Resumen corto de la revisión, por ejemplo «Evidencia conforme».",
            "notes": "Obligatoria al observar o rechazar: explica qué debe corregirse.",
        }

    def __init__(self, *args, reviewers=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Orden de lectura: aprobar, observar y rechazar; sin opción en blanco.
        order = [Validation.Decision.APPROVED, Validation.Decision.FLAGGED, Validation.Decision.REJECTED]
        labels = dict(Validation.Decision.choices)
        self.fields["decision"].choices = [(value, labels[value]) for value in order]
        self.fields["result"].required = True
        if reviewers is None:
            del self.fields["reviewer_officer"]
        else:
            self.fields["reviewer_officer"].queryset = reviewers
        self.polish_choices()
        self.style_fields()

    def clean(self):
        cleaned = super().clean()
        decision = cleaned.get("decision")
        needs_reason = decision in (Validation.Decision.FLAGGED, Validation.Decision.REJECTED)
        if needs_reason and not (cleaned.get("notes") or "").strip():
            self.add_error("notes", "Escribe el motivo para que el funcionario pueda corregirlo.")
        return cleaned
