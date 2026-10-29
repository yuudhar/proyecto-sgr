import re
from decimal import Decimal
from pathlib import Path

from django import forms
from django.conf import settings
from django.contrib.auth import password_validation
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.contrib.auth.models import Group, Permission, User
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile
from django.core.validators import MaxLengthValidator, MinValueValidator
from django.db.models import Q
from django.utils import timezone
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe

from accounts.delegations import stored_delegation_ids
from accounts.models import RoleProfile, UserProfile, group_is_global, role_details
from core import ui, uploads
from core.access import default_delegation, request_delegation, request_officer
from core.photos import photo_url_of
from core.models import BaseModel
from core.roles import MODULE_LABELS, SYSTEM_GROUPS, managed_permissions, permission_key
from core.rules import collapse_spaces, get_rule, normalize_lines
from core.search import plain_letter, word_pattern
from core.widgets import ColorWidget, DelegationsWidget, DependentSelect, LookupWidget, PermissionMatrixWidget, RolesWidget
from evidence.models import Validation
from operations.models import Commitment
from organization.models import Beneficiary, Delegation, Item, Officer
from planning.models import Goal, Period


LONG_TEXT_MAX = 2000


def password_help():
    rules = (
        "No puede parecerse a tus otros datos personales.",
        "Debe tener al menos 8 caracteres.",
        "No puede pasar de 128 caracteres.",
        "Debe llevar una minúscula, una mayúscula, un número y un símbolo (por ejemplo ! # $ %).",
        "No puede ser una contraseña de uso común.",
        "No puede ser solo de números.",
    )
    return format_html("<ul>{}</ul>", format_html_join("", "<li>{}</li>", ((rule,) for rule in rules)))


class BootstrapFormMixin:

    def style_fields(self):
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxSelectMultiple):
                continue
            if isinstance(widget, (forms.CheckboxInput, forms.RadioSelect)):
                css = "form-check-input"
            elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
                css = "form-select"
            else:
                css = "form-control"
            widget.attrs["class"] = f"{widget.attrs.get('class', '')} {css}".strip()
            if isinstance(field, forms.DecimalField) and field.max_digits:
                places = field.decimal_places or 0
                widget.attrs.setdefault("max", str(Decimal(10) ** (field.max_digits - places) - Decimal(1).scaleb(-places)))
            if isinstance(widget, forms.Textarea):
                widget.attrs.pop("cols", None)
                if str(widget.attrs.get("rows", "10")) == "10":
                    widget.attrs["rows"] = 4

    @staticmethod
    def is_long_text(field):
        return isinstance(field, forms.CharField) and isinstance(field.widget, forms.Textarea)

    def set_text_limits(self):
        for field in self.fields.values():
            if not isinstance(field, forms.CharField):
                continue
            if self.is_long_text(field) and field.max_length is None:
                field.max_length = LONG_TEXT_MAX
                field.validators.append(MaxLengthValidator(LONG_TEXT_MAX))
                original = field.to_python
                field.to_python = lambda value, original=original: normalize_lines(original(value))
            if field.max_length:
                field.widget.attrs.setdefault("maxlength", str(field.max_length))

    def polish_choices(self):
        for field in self.fields.values():
            blank = "Selecciona una opción" if field.required else "Sin selección"
            if isinstance(field, forms.ModelChoiceField):
                if field.empty_label is not None:
                    field.empty_label = blank
                field.label_from_instance = ui.humanize_dates
            elif isinstance(field, forms.ChoiceField) and field.choices and field.choices[0][0] == "":
                field.choices = [("", blank), *list(field.choices)[1:]]

    def mark_invalid(self, name):
        if name in self.fields:
            attrs = self.fields[name].widget.attrs
            if "is-invalid" not in attrs.get("class", "").split():
                attrs["class"] = f"{attrs.get('class', '')} is-invalid".strip()

    def add_error(self, field, error):
        super().add_error(field, error)
        if self.is_bound and field:
            self.mark_invalid(field)

    def full_clean(self):
        super().full_clean()
        if self.is_bound:
            for name in self.errors:
                self.mark_invalid(name)


class PortalAuthenticationForm(BootstrapFormMixin, AuthenticationForm):

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
        self.fields["username"].label = "Usuario o correo"
        self.fields["username"].max_length = 254
        self.fields["username"].widget.attrs.update(
            {"autofocus": True, "autocomplete": "username", "maxlength": "254"}
        )
        self.fields["password"].label = "Contraseña"
        self.fields["password"].widget.attrs.update({"autocomplete": "current-password"})
        self.style_fields()


class CrudForm(BootstrapFormMixin, forms.ModelForm):

    note = ""

    def __init__(self, *args, request=None, crud=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.request = request
        self.crud = crud
        self.hide_archived_choices()
        self.polish_choices()
        if crud is not None and crud.delegation_lookup:
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
                for name in crud.readonly_on_edit:
                    if name in self.fields:
                        self.fields[name].disabled = True
        self.customize_fields()
        self.set_text_limits()
        self.apply_rules()
        self.use_date_inputs()
        self.apply_bounds()
        self.style_fields()

    def customize_fields(self):
        pass

    def effective_rules(self):
        rules = dict(self.crud.rules) if self.crud is not None else {}
        for name, field in self.fields.items():
            if name not in rules and self.is_long_text(field):
                rules[name] = "text"
        return rules

    def apply_rules(self):
        for name, rule_name in self.effective_rules().items():
            if name in self.fields:
                self.fields[name].widget.attrs.update(get_rule(rule_name).attrs())

    def bounds(self):
        return {}

    def apply_bounds(self):
        merged = {}
        if self.crud is not None:
            for name, attrs in self.crud.bounds.items():
                merged[name] = dict(attrs)
        for name, attrs in self.bounds().items():
            merged.setdefault(name, {}).update(attrs)
        for name, attrs in merged.items():
            if name in self.fields:
                self.fields[name].widget.attrs.update(attrs)

    def clean(self):
        cleaned = super().clean()
        if self.crud is None:
            return cleaned
        for name, rule_name in self.effective_rules().items():
            field = self.fields.get(name)
            value = cleaned.get(name)
            rule = get_rule(rule_name)
            if field is None or field.disabled or not rule.server or not value or not isinstance(value, str):
                continue
            fixed, error = rule.apply(value)
            if error:
                self.add_error(name, error)
            else:
                cleaned[name] = fixed
        self.check_unique_names(cleaned)
        self.crud.validate_form(self, cleaned)
        return cleaned

    def check_unique_names(self, cleaned):
        for spec in self.crud.unique_names:
            name, *scope = (spec,) if isinstance(spec, str) else spec
            value = cleaned.get(name)
            if name not in self.fields or not value or not isinstance(value, str) or self.has_error(name):
                continue
            filters = {}
            for field_name in scope:
                if field_name in self.fields:
                    if self.has_error(field_name):
                        break
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

    def not_before(self, name, other, message):
        return {name: {"data-not-before": f"id_{other}", "data-not-before-message": message}}

    def check_not_before(self, cleaned, name, other, message):
        value, start = cleaned.get(name), cleaned.get(other)
        if value and start and value < start:
            self.add_error(name, message)

    @staticmethod
    def until_today(message):
        return {"max": timezone.localdate().isoformat(), "data-max-message": message}

    def check_not_future(self, cleaned, name, message):
        value = cleaned.get(name)
        if value and value > timezone.localdate():
            self.add_error(name, message)

    def check_not_before_day(self, cleaned, name, day, label):
        value = cleaned.get(name)
        if value and day and value < day:
            self.add_error(name, f"{label} no puede ser anterior a la fecha de la atención ({ui.fmt_date(day)}).")

    def use_date_inputs(self):
        for field in self.fields.values():
            if isinstance(field, forms.DateField) and not isinstance(
                field, forms.DateTimeField
            ):
                field.widget = forms.DateInput(
                    attrs={"type": "date"}, format="%Y-%m-%d"
                )

    def current_value(self, name):
        return getattr(self.instance, f"{name}_id", None)

    def allowed(self, queryset, name):
        condition = Q(deleted_at__isnull=True)
        current = self.current_value(name)
        if current is not None:
            condition |= Q(pk=current)
        return queryset.filter(condition)

    def hide_archived_choices(self):
        for name, field in self.fields.items():
            if isinstance(field, forms.ModelChoiceField):
                model = field.queryset.model
                if issubclass(model, BaseModel):
                    field.queryset = self.allowed(model._default_manager.all(), name)

    def limit_to_delegation(self, delegation):
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
            condition |= Q(pk=current)
        field.queryset = types.filter(condition).order_by("name")
        if self.instance.pk:
            field.queryset = field.queryset.exclude(pk=self.instance.pk)


class SubAttentionForm(ItemForm):

    def customize_fields(self):
        super().customize_fields()
        field = self.fields["parent_item"]
        field.required = True
        field.empty_label = "Selecciona un tipo de atención"


LOOKUP_LIMIT = 2000

UNKNOWN_RUT = "No hay ninguna persona con ese RUT en Beneficiarios."
UNKNOWN_RUT_CAN_REGISTER = " Regístrala primero en Beneficiarios o escribe su nombre."
UNKNOWN_RUT_CANNOT_REGISTER = " Pide que la registren en Beneficiarios o escribe su nombre."


def fold(text):
    return "".join(plain_letter(char) for char in collapse_spaces(text))


def looks_like_rut(text):
    return re.fullmatch(r"[0-9][0-9.\-]*[0-9kK]", text) is not None and sum(char.isdigit() for char in text) >= 7


def find_beneficiary(text):
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


class EvidenceForm(CrudForm):

    def customize_fields(self):
        field = self.fields["file_link"]
        field.label = "Archivo"
        field.widget = forms.FileInput(
            attrs={
                "accept": ",".join(f".{ext}" for ext in uploads.EVIDENCE_TYPES),
                "data-max-mb": settings.EVIDENCE_MAX_MB,
                "data-accept-label": uploads.accepted_text(uploads.EVIDENCE_TYPES),
            }
        )
        base = f"{uploads.accepted_text(uploads.EVIDENCE_TYPES)}, de hasta {settings.EVIDENCE_MAX_MB} MB."
        current = self.instance.file_link.name if self.instance.pk and self.instance.file_link else ""
        if current:
            name = Path(current).name
            field.help_text = f"Archivo actual: {name}. Sube otro solo si quieres reemplazarlo. {base}"
        else:
            field.help_text = base

    def clean_file_link(self):
        uploaded = self.cleaned_data.get("file_link")
        if isinstance(uploaded, UploadedFile):
            uploads.check_upload(uploaded, uploads.EVIDENCE_TYPES, settings.EVIDENCE_MAX_MB)
        return uploaded


class ActivityIntakeForm(CrudForm):

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
        field = self.fields["request_description"]
        field.required = True
        field.label = "Descripción de la atención"
        field.widget.attrs["placeholder"] = "Describe la solicitud y los antecedentes necesarios."
        message = "Describe la solicitud: la descripción es obligatoria para registrar la atención."
        field.error_messages["required"] = message
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
        field.required = False
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
                cleaned["item"] = kind


def delegation_label(delegation):
    from core.crud import registry

    return f"{registry.get('delegaciones').code_of(delegation)} · {delegation.name}"


class CurrentPhotoInput(forms.FileInput):
    """Campo para subir una foto que, si la persona ya tiene una, la muestra encima."""

    current_url = ""

    def render(self, name, value, attrs=None, renderer=None):
        html = super().render(name, value, attrs, renderer)
        if not self.current_url:
            return html
        current = format_html(
            '<div class="photo-current"><img class="avatar avatar-lg" src="{}" alt="Foto de perfil actual"></div>',
            self.current_url,
        )
        return mark_safe(f"{current}{html}")


class UserForm(CrudForm):

    officer = forms.ModelChoiceField(
        queryset=Officer.objects.none(),
        required=False,
        label="Funcionario",
        help_text=(
            "Define la delegación y el nombre del usuario. Solo el Super Usuario y los perfiles con alcance sobre "
            "todas las delegaciones (como Coordinación) pueden quedar sin funcionario. Para una persona nueva, "
            "créala en Funcionarios: ahí mismo puedes darle su acceso."
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
    photo = forms.ImageField(
        label="Foto de perfil",
        required=False,
        widget=CurrentPhotoInput(
            attrs={
                "accept": ".png,.jpg,.jpeg",
                "data-max-mb": settings.PHOTO_MAX_MB,
                "data-accept-label": "PNG o JPG",
            }
        ),
        error_messages={"invalid_image": "El archivo no es una imagen válida. Revisa que no esté dañado."},
    )
    remove_photo = forms.BooleanField(label="Quitar la foto actual", required=False)

    def clean_photo(self):
        uploaded = self.cleaned_data.get("photo")
        if isinstance(uploaded, UploadedFile):
            uploads.check_upload(uploaded, uploads.PHOTO_TYPES, settings.PHOTO_MAX_MB)
        return uploaded

    def customize_fields(self):
        creating = not self.instance.pk
        current = photo_url_of(self.instance) if not creating else ""
        self.fields["photo"].widget.current_url = current
        self.fields["photo"].help_text = (
            f"PNG o JPG de hasta {settings.PHOTO_MAX_MB} MB."
            + (" Sube otra solo si quieres reemplazar la actual." if current else "")
        )
        if not current:
            del self.fields["remove_photo"]
        groups = self.fields["groups"]
        offered = Q(role_profile__status=RoleProfile.Status.ACTIVE) | Q(role_profile__isnull=True)
        if not creating:
            offered |= Q(pk__in=self.instance.groups.values("pk"))
        groups.queryset = Group.objects.filter(offered).select_related("role_profile").order_by("pk")
        groups.widget = RolesWidget()
        groups.widget.choices = groups.choices
        for name in ("password1", "password2"):
            self.fields[name].required = creating
        self.fields["email"].required = creating or bool(self.instance.email)
        if creating:
            self.fields["password1"].help_text = password_help()
        else:
            self.fields["password1"].help_text = "Déjala en blanco para conservar la contraseña actual."

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
                "photo",
                "remove_photo",
            ]
        )

    def check_extra_delegations(self, cleaned, sees_everything):
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
            cleaned["extra_delegations"] = [d for d in extras if d.pk != officer.delegation_id]

    def _post_clean(self):
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

        if cleaned.get("photo") and cleaned.get("remove_photo"):
            self.add_error("remove_photo", "Sube una foto nueva o marca quitarla, no las dos cosas.")

        officer = cleaned.get("officer")
        if officer is not None:
            if not cleaned.get("first_name"):
                cleaned["first_name"], last = split_person_name(officer.name)
                if not cleaned.get("last_name"):
                    cleaned["last_name"] = last
        elif not self.instance.pk and not cleaned.get("first_name") and not self.has_error("first_name"):
            self.add_error("first_name", "Escribe el nombre: esta cuenta no tiene un funcionario de donde tomarlo.")

        if self.instance.pk and self.request is not None and self.instance.pk == self.request.user.pk:
            if "is_active" in cleaned and not cleaned["is_active"]:
                self.add_error("is_active", "No puedes desactivar tu propia cuenta.")
            if self.instance.is_superuser and "is_superuser" in cleaned and not cleaned["is_superuser"]:
                self.add_error("is_superuser", "No puedes quitarte a ti mismo el perfil de Super Usuario.")
        return cleaned


class OfficerForm(CrudForm):

    section_field = "username"
    section_title = "Acceso al sistema (opcional)"
    section_text = (
        "Llénalo si esta persona va a ingresar al sistema; así no hace falta crear después un usuario aparte. "
        "Déjalo en blanco si solo necesitas registrarla como funcionario."
    )

    username = forms.CharField(label="Usuario", required=False, max_length=150)
    email = forms.EmailField(label="Correo", required=False, max_length=254)
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
    groups = forms.ModelMultipleChoiceField(
        queryset=Group.objects.none(), required=False, label="Perfil", widget=RolesWidget
    )

    ACCESS_FIELDS = ("username", "email", "password1", "password2", "groups")

    def customize_fields(self):
        if self.instance.pk:
            identifier = self.fields["institutional_id"]
            identifier.required = False
            identifier.disabled = True
            identifier.help_text = "Se generó solo al crear al funcionario y no se puede cambiar."
        else:
            del self.fields["institutional_id"]
        allowed = (
            self.request is not None
            and not officer_has_account(self.instance)
            and registry_can_add_user(self.request.user)
        )
        if not allowed:
            for name in self.ACCESS_FIELDS:
                del self.fields[name]
            self.section_field = ""
            return
        offered = Q(role_profile__status=RoleProfile.Status.ACTIVE) | Q(role_profile__isnull=True)
        groups = self.fields["groups"]
        groups.queryset = Group.objects.filter(offered).select_related("role_profile").order_by("pk")
        groups.widget = RolesWidget()
        groups.widget.choices = groups.choices
        self.fields["username"].help_text = "Con este nombre ingresa al sistema. Letras, números y . _ @ + -"
        self.fields["email"].help_text = "Con este correo la persona recupera su contraseña."
        self.fields["password1"].help_text = password_help()
        self.fields["username"].widget.attrs.update(get_rule("username").attrs())
        self.fields["email"].widget.attrs.update(get_rule("email").attrs())
        self.fields["password1"].widget.attrs.update(get_rule("password").attrs())

    def wants_access(self):
        data = self.cleaned_data
        return any(data.get(name) for name in self.ACCESS_FIELDS if name in self.fields)

    def clean(self):
        cleaned = super().clean()
        if "username" not in self.fields or not self.wants_access():
            return cleaned
        if cleaned.get("status") and cleaned["status"] != Officer.Status.ACTIVE:
            self.add_error("status", "Un funcionario inactivo no puede tener acceso: déjalo activo o borra los datos de acceso.")
        for name, message in (
            ("username", "Escribe el usuario con que va a ingresar."),
            ("email", "Escribe el correo: con él la persona recupera su contraseña."),
            ("password1", "Escribe una contraseña para el primer ingreso."),
            ("groups", "Elige al menos un perfil."),
        ):
            if not cleaned.get(name) and not self.has_error(name):
                self.add_error(name, message)
        username = cleaned.get("username")
        if username and User.objects.filter(username__iexact=username).exists():
            self.add_error("username", "Ya existe un usuario con ese nombre, aunque cambien las mayúsculas.")
        email = cleaned.get("email")
        if email and User.objects.filter(email__iexact=email).exists():
            self.add_error("email", "Ese correo ya lo usa otro usuario. Cada cuenta necesita uno distinto.")
        password = cleaned.get("password1") or ""
        if password and password != (cleaned.get("password2") or ""):
            self.add_error("password2", "Las dos contraseñas deben ser iguales.")
        elif password and not self.has_error("password1"):
            first, last = split_person_name(cleaned.get("name") or "")
            try:
                password_validation.validate_password(
                    password, user=User(username=username or "", first_name=first, last_name=last, email=email or "")
                )
            except ValidationError as error:
                self.add_error("password1", error.messages)
        return cleaned


def officer_has_account(officer):
    return bool(officer.pk) and UserProfile.objects.filter(officer_id=officer.pk).exists()


def registry_can_add_user(user):
    return user.has_perm("auth.add_user")


def split_person_name(name):
    words = (name or "").split()
    if len(words) <= 1:
        return (name or "").strip(), ""
    cut = 2 if len(words) >= 4 else 1
    return " ".join(words[:cut])[:150], " ".join(words[cut:])[:150]


class ProfilePhotoForm(BootstrapFormMixin, forms.Form):

    photo = forms.ImageField(
        label="Foto de perfil",
        widget=forms.FileInput(
            attrs={
                "accept": ".png,.jpg,.jpeg",
                "data-max-mb": settings.PHOTO_MAX_MB,
                "data-accept-label": "PNG o JPG",
            }
        ),
        error_messages={
            "required": "Elige una imagen para tu foto.",
            "invalid_image": "El archivo no es una imagen válida. Revisa que no esté dañado.",
        },
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["photo"].help_text = f"PNG o JPG de hasta {settings.PHOTO_MAX_MB} MB."
        self.style_fields()

    def clean_photo(self):
        uploaded = self.cleaned_data["photo"]
        return uploads.check_upload(uploaded, uploads.PHOTO_TYPES, settings.PHOTO_MAX_MB)


class PortalPasswordChangeForm(BootstrapFormMixin, PasswordChangeForm):

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
        self.fields["new_password1"].widget.attrs.update(get_rule("password").attrs())
        self.fields["new_password2"].label = "Repite la contraseña nueva"
        self.fields["new_password2"].help_text = ""
        self.fields["new_password2"].widget.attrs["data-match"] = "id_new_password1"
        self.fields["old_password"].widget.attrs.pop("autofocus", None)
        self.style_fields()

    def validate_password_for_user(self, user, password_field_name="new_password2"):
        super().validate_password_for_user(user, "new_password1")


class PeriodForm(CrudForm):

    def bounds(self):
        return self.not_before("end_date", "start_date", "La fecha de término no puede ser anterior a la de inicio.")

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
            others = Period.objects.filter(deleted_at__isnull=True, status=Period.Status.ACTIVE)
            if self.instance.pk:
                others = others.exclude(pk=self.instance.pk)
            if others.exists():
                self.add_error("status", "Ya hay un período vigente. Ciérralo antes de dejar este como vigente.")
        return cleaned


class GoalForm(CrudForm):

    MIN_TARGET = Decimal("0.01")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        field = self.fields.get("target_value")
        if field is not None:
            field.validators = [v for v in field.validators if not isinstance(v, MinValueValidator)]

    def _get_validation_exclusions(self):
        return super()._get_validation_exclusions() | {"target_value"}

    def clean(self):
        cleaned = super().clean()
        target = cleaned.get("target_value")
        if target is not None and target < self.MIN_TARGET:
            self.add_error("target_value", "El valor objetivo debe ser mayor que 0 (como mínimo 0,01).")
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

    def clean(self):
        cleaned = super().clean()
        for name in ("progress", "compliance", "weighting"):
            value = cleaned.get(name)
            if value is not None and value < 0:
                self.add_error(name, "No puede ser negativo.")
        return cleaned


class AdjustmentForm(CrudForm):

    def clean_percentage_value(self):
        value = self.cleaned_data["percentage_value"]
        if not 0 < value <= 100:
            raise forms.ValidationError("El valor debe ser mayor que 0 y como máximo 100.")
        return value


class ActivityEditForm(CrudForm):

    DATE_MESSAGE = "La fecha de la atención no puede ser futura."

    def bounds(self):
        return {"date": self.until_today(self.DATE_MESSAGE)}

    def clean(self):
        cleaned = super().clean()
        self.check_not_future(cleaned, "date", self.DATE_MESSAGE)
        return cleaned


class CommitmentForm(CrudForm):

    REQUEST_MESSAGE = "La fecha de solicitud no puede ser futura."
    DUE_MESSAGE = "La fecha comprometida no puede ser anterior a la fecha de solicitud."

    def customize_fields(self):
        # RF-018: al editar, el estado solo ofrece los estados a los que se puede pasar desde el actual.
        field = self.fields.get("status")
        if field is None or not self.instance.pk or self.instance.status not in Commitment.TRANSITIONS:
            return
        current = self.instance.status
        field.choices = Commitment.next_choices(current)
        reachable = ", ".join(
            f"«{label}»" for value, label in field.choices if value != current
        )
        field.error_messages["invalid_choice"] = (
            f"Un compromiso «{self.instance.get_status_display()}» solo puede pasar a: {reachable}."
        )

    def bounds(self):
        return {
            "request_date": self.until_today(self.REQUEST_MESSAGE),
            **self.not_before("due_date", "request_date", self.DUE_MESSAGE),
        }

    def clean(self):
        cleaned = super().clean()
        self.check_not_future(cleaned, "request_date", self.REQUEST_MESSAGE)
        self.check_not_before(cleaned, "due_date", "request_date", self.DUE_MESSAGE)
        return cleaned


class FollowupForm(CrudForm):

    TODAY = {
        "date": "La fecha de la gestión no puede ser futura.",
        "visit_date": "La fecha de la visita no puede ser futura: para una visita futura usa la fecha programada.",
        "report_delivery_date": "La fecha de entrega del informe no puede ser futura.",
        "benefit_delivery_date": "La fecha de entrega del beneficio no puede ser futura.",
    }
    AFTER_VISIT = {
        "report_delivery_date": "La entrega del informe no puede ser anterior a la fecha de la visita.",
        "benefit_delivery_date": "La entrega del beneficio no puede ser anterior a la fecha de la visita.",
    }
    LABELS = {
        "date": "La fecha de la gestión",
        "scheduled_visit_date": "La visita programada",
        "visit_date": "La fecha de la visita",
        "report_delivery_date": "La entrega del informe",
        "benefit_delivery_date": "La entrega del beneficio",
    }

    def bounds(self):
        found = {name: self.until_today(message) for name, message in self.TODAY.items()}
        for name, message in self.AFTER_VISIT.items():
            found[name].update(self.not_before(name, "visit_date", message)[name])
        return found

    def clean(self):
        cleaned = super().clean()
        for name, message in self.TODAY.items():
            self.check_not_future(cleaned, name, message)
        for name, message in self.AFTER_VISIT.items():
            self.check_not_before(cleaned, name, "visit_date", message)
        activity = cleaned.get("activity")
        if activity is not None:
            for name, label in self.LABELS.items():
                self.check_not_before_day(cleaned, name, activity.date, label)
        return cleaned


class PositionForm(CrudForm):

    MESSAGE = "La vigencia hasta no puede ser anterior a la vigencia desde."

    def bounds(self):
        return self.not_before("valid_until", "valid_from", self.MESSAGE)

    def clean(self):
        cleaned = super().clean()
        self.check_not_before(cleaned, "valid_until", "valid_from", self.MESSAGE)
        return cleaned


class PositionItemForm(PositionForm):

    def clean(self):
        cleaned = super().clean()
        weight = cleaned.get("weight")
        if weight is not None and not 0 < weight <= 100:
            self.add_error("weight", "El ponderador debe ser mayor que 0 y como máximo 100.")
        cap = cleaned.get("max_cap")
        if cap is not None and cap <= 0:
            self.add_error("max_cap", "El tope máximo debe ser mayor que 0.")
        return cleaned


class ValidationForm(BootstrapFormMixin, forms.ModelForm):

    TEXT_RULES = {"result": "label", "notes": "text"}

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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        order = [Validation.Decision.APPROVED, Validation.Decision.FLAGGED, Validation.Decision.REJECTED]
        labels = dict(Validation.Decision.choices)
        self.fields["decision"].choices = [(value, labels[value]) for value in order]
        self.fields["result"].required = True
        self.set_text_limits()
        for name, rule_name in self.TEXT_RULES.items():
            self.fields[name].widget.attrs.update(get_rule(rule_name).attrs())
        self.polish_choices()
        self.style_fields()

    def clean(self):
        cleaned = super().clean()
        for name, rule_name in self.TEXT_RULES.items():
            value = cleaned.get(name)
            if not value or not isinstance(value, str):
                continue
            fixed, error = get_rule(rule_name).apply(value)
            if error:
                self.add_error(name, error)
            else:
                cleaned[name] = fixed
        decision = cleaned.get("decision")
        needs_reason = decision in (Validation.Decision.FLAGGED, Validation.Decision.REJECTED)
        if needs_reason and not (cleaned.get("notes") or "").strip():
            self.add_error("notes", "Escribe el motivo para que el funcionario pueda corregirlo.")
        return cleaned
