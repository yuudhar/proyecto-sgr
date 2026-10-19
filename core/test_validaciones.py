"""Pruebas de las validaciones de la v14: contraseñas, textos, números y fechas, en el servidor y en el navegador.

Qué cubren:
  - La política de contraseñas (accounts/validators.py) y su regla gemela para el navegador (core/rules.py).
  - Que ningún campo de texto de ningún formulario quede sin regla: rechazan < y > y respetan el largo máximo.
  - Los cuadros de varias líneas: regla «text», saltos de línea y largo máximo de 2000.
  - Rangos de números (ponderadores, umbrales, tope máximo, número de gestión) y fechas con sentido.
  - Que el navegador reciba los mismos límites (atributos min, max, maxlength y data-*).
  - Que las expresiones regulares de Python y de JavaScript den el mismo veredicto (con Node, si está instalado).
"""

import json
import re
import shutil
import subprocess
import unittest
from datetime import timedelta
from zoneinfo import ZoneInfo

from django import forms
from django.conf import settings
from django.contrib.auth import password_validation
from django.contrib.auth.models import User
from django.contrib.sessions.backends.db import SessionStore
from django.core.exceptions import ValidationError
from django.test import RequestFactory, SimpleTestCase
from django.urls import reverse
from django.utils import timezone

import core.registry  # noqa: F401  (registra los mantenedores)
from accounts.forms import RecoveryPasswordForm
from accounts.validators import PasswordPolicyValidator
from core import rules
from core.crud import registry
from core.forms import LONG_TEXT_MAX, PortalPasswordChangeForm, ValidationForm
from core.test_users import NEW_PASSWORD, UserTestCase
from core.testing import PASSWORD, PortalTestCase
from evidence.models import Evidence, Validation
from operations.models import Activity, Commitment, Followup, ManagementType
from organization.models import Item, Position, PositionItem, Territory
from planning.models import Goal, Period


def portal_today():
    """El día en la hora de Chile, la que usan las pantallas (de noche en Chile ya es «mañana» en UTC)."""
    with timezone.override(ZoneInfo(settings.PORTAL_TIME_ZONE)):
        return timezone.localdate()


def input_tag(html, field):
    """La etiqueta <input>, <textarea> o <select> del campo, tal como la recibe el navegador."""
    found = re.search(rf'<(?:input|textarea|select)\b[^>]*\bid="id_{field}"[^>]*>', html)
    assert found, f"No hay un campo id_{field} en la página"
    return found.group(0)


# -- Contraseñas --------------------------------------------------------------------------------------------------


class PasswordPolicyValidatorTests(SimpleTestCase):
    """accounts/validators.py: largo máximo y variedad de caracteres, con mensajes que dicen qué falta."""

    def messages(self, password):
        try:
            password_validation.validate_password(password)
        except ValidationError as error:
            return error.messages
        return []

    def test_the_demo_password_complies_with_the_policy(self):
        self.assertEqual(self.messages(PASSWORD), [])

    def test_the_example_weak_password_is_rejected(self):
        text = " ".join(self.messages("admin12345"))
        self.assertIn("mayúscula", text)
        self.assertIn("símbolo", text)

    def test_each_missing_requirement_has_its_own_message(self):
        cases = {
            "HOLA123!": "Le falta una letra minúscula.",
            "hola123!": "Le falta una letra mayúscula.",
            "Holahola!": "Le falta un número.",
            "Zorro1234": "Le falta un símbolo",
        }
        for password, expected in cases.items():
            with self.subTest(password=password):
                found = self.messages(password)
                self.assertTrue(any(expected in message for message in found), found)
                self.assertEqual(len(found), 1, found)  # dice solo lo que falta, no todo

    def test_a_password_with_several_gaps_lists_all_of_them(self):
        found = self.messages("abcdefghij")
        for expected in ("mayúscula", "número", "símbolo"):
            self.assertTrue(any(expected in message for message in found), (expected, found))
        self.assertFalse(any("minúscula" in message for message in found))

    def test_the_length_limit_is_128_characters(self):
        self.assertEqual(self.messages("Aa1!" + "x" * 124), [])  # 128
        found = self.messages("Aa1!" + "x" * 125)  # 129
        self.assertTrue(any("demasiado larga" in message and "129" in message for message in found), found)

    def test_a_short_password_is_still_stopped_by_the_minimum_length_validator(self):
        found = self.messages("Aa1!")
        self.assertTrue(any("8 characters" in message or "8 caracteres" in message for message in found), found)

    def test_a_space_is_not_a_symbol_but_accented_letters_count_as_letters(self):
        self.assertTrue(any("símbolo" in message for message in self.messages("Hola 12345")))
        self.assertEqual(self.messages("Contraseña1!"), [])
        self.assertEqual(self.messages("ÑandúÁrbol9#"), [])

    def test_the_other_validators_are_still_active(self):
        names = [item["NAME"].rsplit(".", 1)[1] for item in settings.AUTH_PASSWORD_VALIDATORS]
        for expected in (
            "UserAttributeSimilarityValidator",
            "MinimumLengthValidator",
            "CommonPasswordValidator",
            "NumericPasswordValidator",
            "PasswordPolicyValidator",
        ):
            self.assertIn(expected, names)
        self.assertTrue(any("común" in message or "common" in message.lower() for message in self.messages("Password1!")))
        self.assertTrue(self.messages("12345678"))

    def test_the_help_text_names_the_requirements(self):
        text = PasswordPolicyValidator().get_help_text()
        for expected in ("128", "minúscula", "mayúscula", "número", "símbolo"):
            self.assertIn(expected, text)


class PasswordRuleTests(SimpleTestCase):
    """La regla «password» del navegador dice lo mismo que el validador del servidor."""

    SAMPLES = (
        "Hola123!", "admin12345", "HOLA123!", "hola123!", "Holahola!", "Hola1234", "Hola 1234", "Aa1!", "Aa1!xxxx",
        "Contraseña1!", "ÑandúÁrbol9#", "Aa1!" + "x" * 124, "Aa1!" + "x" * 125, "abcdefghij", "12345678", "        ",
        "Clave Segura 2026 +", "ClaveSegura#2026", "sin-mayuscula-1", "SIN-MINUSCULA-1",
    )

    def test_it_accepts_and_rejects_the_same_passwords_as_the_server_policy(self):
        rule = rules.get_rule("password")
        for password in self.SAMPLES:
            with self.subTest(password=password[:20]):
                try:
                    PasswordPolicyValidator().validate(password)
                    policy_ok = len(password) >= 8
                except ValidationError:
                    policy_ok = False
                self.assertEqual(rule.apply(password)[1] is None, policy_ok)

    def test_it_does_not_touch_what_was_typed_and_only_warns_in_the_browser(self):
        rule = rules.get_rule("password")
        self.assertEqual(rule.apply("  Hola 123!  ")[0], "  Hola 123!  ")  # los espacios son parte de la clave
        self.assertFalse(rule.server)
        attrs = rule.attrs()
        self.assertEqual(attrs["data-rule"], "password")
        self.assertEqual(attrs["data-normalize"], "none")
        self.assertIn("128", attrs["data-message"])


class PasswordFormsTests(UserTestCase):
    """Los tres formularios que piden una contraseña nueva aplican la política."""

    def test_the_user_form_says_exactly_what_is_missing(self):
        self.login_as("admin")
        response = self.create(password1="Clavesinsimbolo1", password2="Clavesinsimbolo1")
        self.assertEqual(response.status_code, 200)
        found = response.context["form"].errors["password1"]
        self.assertEqual(len(found), 1, found)
        self.assertIn("símbolo", found[0])
        self.assertFalse(User.objects.filter(username="ana.torres").exists())

    def test_the_user_form_rejects_the_example_password(self):
        self.login_as("admin")
        response = self.create(password1="admin12345", password2="admin12345")
        self.assertEqual(response.status_code, 200)
        self.assertIn("password1", response.context["form"].errors)
        self.assertFalse(User.objects.filter(username="ana.torres").exists())

    def test_the_user_form_accepts_a_password_that_complies(self):
        self.login_as("admin")
        self.assertEqual(self.create().status_code, 302)
        self.assertTrue(User.objects.get(username="ana.torres").check_password(NEW_PASSWORD))

    def test_the_demo_password_is_accepted_by_the_user_form(self):
        self.login_as("admin")
        self.assertEqual(self.create(password1=PASSWORD, password2=PASSWORD).status_code, 302)

    def test_a_password_too_long_is_rejected_by_the_user_form(self):
        self.login_as("admin")
        long = "Aa1!" + "x" * 125
        response = self.create(password1=long, password2=long)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(any("larga" in message for message in response.context["form"].errors["password1"]))

    def test_editing_a_user_with_the_password_blank_keeps_it_and_does_not_complain(self):
        self.login_as("admin")
        user = User.objects.get(username="matias.quiroz")
        response = self.client.post(self.update_url(user), self.edit_data(user, first_name="Matías"))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.get(pk=user.pk).check_password(PASSWORD))

    def test_the_profile_form_applies_the_same_policy(self):
        user = self.login_as("matias.cavieres")
        url = reverse("core:profile")
        weak = {"old_password": PASSWORD, "new_password1": "Sinsimbolo123", "new_password2": "Sinsimbolo123"}
        response = self.client.post(url, weak)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(any("símbolo" in message for message in response.context["form"].errors["new_password1"]))
        self.assertTrue(User.objects.get(pk=user.pk).check_password(PASSWORD))
        good = {"old_password": PASSWORD, "new_password1": "Otra#Clave2026", "new_password2": "Otra#Clave2026"}
        self.assertEqual(self.client.post(url, good).status_code, 302)
        self.assertTrue(User.objects.get(pk=user.pk).check_password("Otra#Clave2026"))

    def test_the_recovery_form_applies_the_same_policy(self):
        user = User.objects.get(username="matias.cavieres")
        weak = RecoveryPasswordForm(user, {"new_password1": "SINMINUSCULA1!", "new_password2": "SINMINUSCULA1!"})
        self.assertFalse(weak.is_valid())
        self.assertTrue(any("minúscula" in message for message in weak.errors["new_password1"]))
        good = RecoveryPasswordForm(user, {"new_password1": "Recuperada#2026", "new_password2": "Recuperada#2026"})
        self.assertTrue(good.is_valid(), good.errors)

    def test_the_three_password_fields_carry_the_rule_for_the_browser(self):
        self.login_as("admin")
        page = self.client.get(reverse("core:usuarios_create")).content.decode()
        self.assertIn('data-rule="password"', input_tag(page, "password1"))
        self.assertNotIn("data-rule", input_tag(page, "password2"))  # la repetición solo se compara con la primera
        self.login_as("matias.cavieres")
        page = self.client.get(reverse("core:profile")).content.decode()
        self.assertIn('data-rule="password"', input_tag(page, "new_password1"))
        user = User.objects.get(username="matias.cavieres")
        field = RecoveryPasswordForm(user).fields["new_password1"]
        self.assertEqual(field.widget.attrs["data-rule"], "password")

    def test_the_help_lists_the_new_requirements(self):
        self.login_as("admin")
        page = self.client.get(reverse("core:usuarios_create")).content.decode()
        for expected in ("No puede pasar de 128 caracteres.", "una minúscula, una mayúscula, un número y un símbolo"):
            self.assertIn(expected, page)
        self.assertIn("Debe tener al menos 8 caracteres.", page)

    def test_accounts_created_before_the_policy_can_still_log_in(self):
        weak = User.objects.create_user("antigua", password="clave123")  # creada por consola, saltándose el formulario
        self.assertTrue(self.client.login(username=weak.username, password="clave123"))


# -- Textos -----------------------------------------------------------------------------------------------------


class FormFactory:
    """Arma formularios de los mantenedores igual que lo hace la vista, con el Super Usuario."""

    def make_request(self):
        request = RequestFactory().get("/")
        request.user = User.objects.get(username="admin")
        request.session = SessionStore()
        return request

    def form_for(self, slug, data, creating=True, instance=None):
        crud = registry.get(slug)
        form_class = crud.form_class_for(creating)
        return form_class(data, request=self.make_request(), crud=crud, instance=instance)

    def rule_for(self, slug, field, creating=True):
        form = self.form_for(slug, None, creating)
        return rules.get_rule(form.effective_rules()[field])


# (mantenedor, campo, ¿al crear?, texto válido). Son los campos de texto que antes no tenían regla.
TEXT_FIELDS = (
    ("actividades", "requester", True, "Junta de Vecinos N°5 (Las Rosas)"),
    ("actividades", "contact_name", False, "Rosa Prueba"),
    ("actividades", "request_description", True, "Solicita ayuda.\nTiene dos hijos."),
    ("actividades", "action_taken", True, "Se derivó a Ayuda Social."),
    ("gestiones", "result", True, "Se agenda visita domiciliaria."),
    ("agenda", "requester", True, "Club deportivo Los Pinos"),
    ("agenda", "source", True, "Oficio N° 123"),
    ("agenda", "description", True, "Arreglo de luminarias.\nSector norte."),
    ("agenda", "support", True, "Camión aljibe"),
    ("agenda", "notes", True, "Coordinar con la dirección de obras."),
    ("metas", "unit", True, "atenciones"),
    ("ajustes", "reason", True, "Bonificación por desempeño"),
    ("delegaciones", "name", True, "Delegación Centro"),
    ("delegaciones", "managers", True, "Diego Fuentes"),
    ("delegaciones", "scope", True, "Sector centro"),
    ("territorios", "name", True, "Población Los Pinos"),
    ("cargos", "name", True, "Encargado de Terreno"),
    ("servicios", "name", True, "Ayuda Técnica Especial"),
    ("tipos-de-gestion", "name", True, "Llamado telefónico"),
    ("beneficiarios", "address", True, "Av. del Mar 789, depto. 12"),
)


class TextFieldsTests(FormFactory, PortalTestCase):
    """Todos los campos de texto rechazan < y >, y aceptan texto normal."""

    def test_every_text_field_rejects_angle_brackets_with_the_message_of_its_rule(self):
        for slug, field, creating, _valid in TEXT_FIELDS:
            with self.subTest(slug=slug, field=field):
                form = self.form_for(slug, {field: "<b>hola</b>"}, creating)
                self.assertFalse(form.is_valid())
                self.assertEqual(form.errors.get(field), [self.rule_for(slug, field, creating).message])

    def test_every_text_field_rejects_control_characters(self):
        for slug, field, creating, _valid in TEXT_FIELDS:
            with self.subTest(slug=slug, field=field):
                form = self.form_for(slug, {field: "hola\x07mundo"}, creating)
                self.assertFalse(form.is_valid())
                self.assertIn(field, form.errors)

    def test_every_text_field_accepts_normal_text(self):
        for slug, field, creating, valid in TEXT_FIELDS:
            with self.subTest(slug=slug, field=field):
                form = self.form_for(slug, {field: valid}, creating)
                form.is_valid()
                self.assertNotIn(field, form.errors, form.errors.get(field))

    def test_single_line_fields_collapse_extra_spaces_and_multi_line_fields_keep_their_lines(self):
        form = self.form_for("territorios", {"name": "  Población   Los   Pinos "})
        form.is_valid()
        self.assertEqual(form.cleaned_data["name"], "Población Los Pinos")
        form = self.form_for("agenda", {"description": "Línea uno.\r\n\r\nLínea tres.  "})
        form.is_valid()
        self.assertEqual(form.cleaned_data["description"], "Línea uno.\n\nLínea tres.")

    def test_a_manager_is_a_person_name(self):
        form = self.form_for("delegaciones", {"managers": "Diego 123"})
        form.is_valid()
        self.assertEqual(form.errors["managers"], [rules.get_rule("person_name").message])

    def test_no_text_field_of_any_form_is_left_without_a_rule(self):
        """Protege a los mantenedores futuros: un campo de texto nuevo sin regla hace fallar esta prueba."""
        exempt = {("usuarios", "password2"), ("funcionarios", "password2")}  # la repetición de la contraseña solo se compara con la primera
        for crud in registry.all():
            for creating in (True, False) if crud.create_form_base else (True,):
                form = self.form_for(crud.slug, None, creating)
                covered = form.effective_rules()
                for name, field in form.fields.items():
                    plain_text = isinstance(field, forms.CharField) and not isinstance(field, forms.ChoiceField)
                    if plain_text and name not in covered and (crud.slug, name) not in exempt:
                        self.fail(f"{crud.slug}: el campo «{name}» no tiene regla de formato")

    def test_every_text_field_tells_the_browser_its_maximum_length(self):
        for crud in registry.all():
            for creating in (True, False) if crud.create_form_base else (True,):
                form = self.form_for(crud.slug, None, creating)
                for name, field in form.fields.items():
                    if isinstance(field, forms.CharField) and not isinstance(field, forms.ChoiceField) and field.max_length:
                        with self.subTest(slug=crud.slug, field=name):
                            self.assertEqual(field.widget.attrs.get("maxlength"), str(field.max_length))

    def test_the_rule_attributes_reach_the_rendered_page(self):
        self.login_as("admin")
        for url, expected in (
            ("core:agenda_create", {"requester": "label", "source": "label", "support": "label", "description": "text", "notes": "text"}),
                        ("core:delegaciones_create", {"name": "label", "managers": "person_name", "scope": "label"}),
            ("core:ajustes_create", {"reason": "label"}),
            ("core:metas_create", {"unit": "label"}),
            ("core:actividades_create", {"requester": "label", "request_description": "text", "action_taken": "text"}),
        ):
            page = self.client.get(reverse(url)).content.decode()
            for field, rule_name in expected.items():
                with self.subTest(url=url, field=field):
                    self.assertIn(f'data-rule="{rule_name}"', input_tag(page, field))


class LongTextTests(FormFactory, PortalTestCase):
    """Cuadros de varias líneas: regla «text», saltos de línea y largo máximo."""

    def test_a_long_text_box_has_a_limit_in_the_server_and_in_the_browser(self):
        form = self.form_for("agenda", None)
        field = form.fields["description"]
        self.assertEqual(field.max_length, LONG_TEXT_MAX)
        self.assertEqual(field.widget.attrs["maxlength"], str(LONG_TEXT_MAX))
        self.assertEqual(field.widget.attrs["data-rule"], "text")

    def test_the_limit_is_2000_characters(self):
        for size, valid in ((LONG_TEXT_MAX, True), (LONG_TEXT_MAX + 1, False)):
            with self.subTest(size=size):
                form = self.form_for("agenda", {"description": "a" * size})
                form.is_valid()
                self.assertEqual("description" not in form.errors, valid)

    def test_line_breaks_count_as_one_character_like_in_the_browser(self):
        text = "a\r\n" * 900  # 900 líneas: el navegador lo cuenta como 1.800 caracteres y el servidor lo recibe con 2.700
        form = self.form_for("agenda", {"description": text})
        form.is_valid()
        self.assertNotIn("description", form.errors)
        self.assertEqual(form.cleaned_data["description"], ("a\n" * 900).strip())

    def test_the_intake_saves_a_multi_line_description_with_plain_line_breaks(self):
        self.login_as("matias.cavieres")
        response = self.client.post(
            reverse("core:actividades_create"),
            self.intake_data(request_description="Primera línea.\r\nSegunda línea.", action_taken="Se llamó.\r\n"),
        )
        self.assertEqual(response.status_code, 302)
        saved = Activity.objects.get(contact_name="Rosa Prueba")
        self.assertEqual(saved.request_description, "Primera línea.\nSegunda línea.")
        self.assertEqual(saved.action_taken, "Se llamó.")

    def test_the_intake_rejects_angle_brackets_and_a_text_too_long(self):
        self.login_as("matias.cavieres")
        url = reverse("core:actividades_create")
        for field, value in (
            ("request_description", "<script>alert(1)</script>"),
            ("action_taken", "ver <b>esto</b>"),
            ("request_description", "x" * (LONG_TEXT_MAX + 1)),
            ("requester", "Rosa <Prueba>"),
        ):
            with self.subTest(field=field, value=value[:15]):
                response = self.client.post(url, self.intake_data(**{field: value}))
                self.assertEqual(response.status_code, 200)
                self.assertIn(field, response.context["form"].errors)
        self.assertFalse(Activity.objects.filter(contact_name__startswith="Rosa").exists())

    def test_the_activity_edit_form_applies_the_same_rules(self):
        self.login_as("admin")
        activity = self.activity("María Pérez")
        url = reverse("core:actividades_update", args=[activity.pk])
        for field, value in (("contact_name", "<i>María</i>"), ("action_taken", "<b>x</b>"), ("request_description", "<")):
            with self.subTest(field=field):
                response = self.client.post(url, self.activity_form_data(activity, **{field: value}))
                self.assertEqual(response.status_code, 200)
                self.assertIn(field, response.context["form"].errors)

    def test_the_evidence_and_commitment_text_boxes_have_the_limit_on_the_page(self):
        self.login_as("admin")
        for url, fields in (("core:agenda_create", ("description", "notes")),):
            page = self.client.get(reverse(url)).content.decode()
            for field in fields:
                with self.subTest(url=url, field=field):
                    self.assertIn(f'maxlength="{LONG_TEXT_MAX}"', input_tag(page, field))

    def test_the_review_form_validates_its_texts(self):
        base = {"decision": Validation.Decision.APPROVED, "result": "Evidencia conforme", "notes": ""}
        self.assertTrue(ValidationForm(base).is_valid())
        for field, value in (("result", "<b>ok</b>"), ("notes", "revisar <b>esto</b>"), ("notes", "x" * (LONG_TEXT_MAX + 1))):
            with self.subTest(field=field):
                form = ValidationForm({**base, field: value})
                self.assertFalse(form.is_valid())
                self.assertIn(field, form.errors)
        form = ValidationForm({**base, "decision": Validation.Decision.FLAGGED, "notes": "Falta la firma.\r\nVolver a subir."})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["notes"], "Falta la firma.\nVolver a subir.")
        form = ValidationForm()
        self.assertEqual(form.fields["notes"].widget.attrs["data-rule"], "text")
        self.assertEqual(form.fields["notes"].widget.attrs["maxlength"], str(LONG_TEXT_MAX))
        self.assertEqual(form.fields["result"].widget.attrs["data-rule"], "label")


# -- Números ---------------------------------------------------------------------------------------------------


class NumberRangesTests(FormFactory, PortalTestCase):
    """Rangos de los números: el servidor los exige y el navegador los recibe como min y max."""

    def setUp(self):
        self.login_as("admin")
        self.position = Position.objects.create(name="Cargo de límites", valid_from=portal_today() - timedelta(days=60))
        self.item = Item.objects.create(name="Ítem de límites")

    def position_item_data(self, **changes):
        data = {
            "position": self.position.pk,
            "item": self.item.pk,
            "kind": PositionItem.Kind.NORMAL,
            "weight": "50",
            "max_cap": "",
            "valid_from": (portal_today() - timedelta(days=30)).isoformat(),
            "valid_until": "",
        }
        data.update(changes)
        return data

    def post_position_item(self, **changes):
        return self.client.post(reverse("core:items_de_cargo_create"), self.position_item_data(**changes))

    def test_a_position_item_weight_goes_above_zero_up_to_100(self):
        for weight in ("0", "-5", "100.01", "250"):
            with self.subTest(weight=weight):
                response = self.post_position_item(weight=weight)
                self.assertEqual(response.status_code, 200)
                self.assertIn("weight", response.context["form"].errors)
        self.assertFalse(PositionItem.objects.filter(position=self.position).exists())
        for weight in ("0.01", "100"):
            with self.subTest(weight=weight):
                PositionItem.objects.filter(position=self.position).delete()
                self.assertEqual(self.post_position_item(weight=weight).status_code, 302)

    def test_the_maximum_cap_of_a_position_item_is_positive(self):
        for cap in ("0", "-1"):
            with self.subTest(cap=cap):
                response = self.post_position_item(kind=PositionItem.Kind.BONUS, max_cap=cap)
                self.assertEqual(response.status_code, 200)
                self.assertIn("max_cap", response.context["form"].errors)
        self.assertEqual(self.post_position_item(kind=PositionItem.Kind.BONUS, max_cap="15").status_code, 302)

    def test_bonus_and_penalty_still_need_a_cap(self):
        response = self.post_position_item(kind=PositionItem.Kind.PENALTY, max_cap="")
        self.assertEqual(response.status_code, 200)
        self.assertIn("max_cap", response.context["form"].errors)

    def test_the_followup_number_goes_from_1_to_3(self):
        activity = self.activity("María Pérez")
        base = {
            "activity": activity.pk,
            "management_type": ManagementType.objects.first().pk,
            "date": activity.date.isoformat(),
            "result": "Se llamó por teléfono.",
        }
        for number in ("0", "-1", "4"):
            with self.subTest(number=number):
                response = self.client.post(reverse("core:gestiones_create"), {**base, "sequence_number": number})
                self.assertEqual(response.status_code, 200)
                self.assertIn("sequence_number", response.context["form"].errors)

    def test_the_goal_target_must_be_above_zero(self):
        goal = Goal.objects.filter(officer__isnull=False).first()
        post = {
            "item": goal.item_id,
            "period": goal.period_id,
            "officer": goal.officer_id,
            "position": "",
            "unit": goal.unit,
            "weight": str(goal.weight),
            "version": str(goal.version),
        }
        url = reverse("core:metas_update", args=[goal.pk])
        for target in ("0", "-2", "0.001"):
            with self.subTest(target=target):
                response = self.client.post(url, {**post, "target_value": target})
                self.assertEqual(response.status_code, 200)
                self.assertIn("target_value", response.context["form"].errors)
        response = self.client.post(url, {**post, "target_value": "0.01"})
        self.assertEqual(response.status_code, 302, response.context["form"].errors if response.context else "")

    def test_the_numbers_reach_the_browser_with_their_limits(self):
        expected = {
            "core:items_de_cargo_create": {"weight": ('min="0.01"', 'max="100"'), "max_cap": ('min="0.01"',)},
            "core:gestiones_create": {"sequence_number": ('min="1"', 'max="3"')},
            "core:periodos_create": {
                "computable_days": ('min="1"',),
                "collective_threshold": ('min="0.01"', 'max="100"'),
                "amber_threshold": ('min="0"', 'max="100"'),
                "weighted_cap": ('min="0.01"',),
            },
            "core:metas_create": {
                "target_value": ('min="0.01"',),
                "weight": ('min="0.01"', 'max="100"'),
                "version": ('min="1"',),
            },
            "core:indicadores_create": {"progress": ('min="0"',), "compliance": ('min="0"',), "weighting": ('min="0"',)},
            "core:ajustes_create": {"percentage_value": ('min="0.01"', 'max="100"')},
        }
        for url, fields in expected.items():
            page = self.client.get(reverse(url)).content.decode()
            for field, attrs in fields.items():
                tag = input_tag(page, field)
                for attr in attrs:
                    with self.subTest(url=url, field=field, attr=attr):
                        self.assertIn(attr, tag)

    def test_the_limits_in_the_browser_match_the_server_for_the_edit_forms_too(self):
        goal = Goal.objects.filter(officer__isnull=False).first()
        page = self.client.get(reverse("core:metas_update", args=[goal.pk])).content.decode()
        self.assertIn('min="1"', input_tag(page, "version"))
        self.assertIn('max="100"', input_tag(page, "weight"))


# -- Fechas ----------------------------------------------------------------------------------------------------


class DateRulesTests(FormFactory, PortalTestCase):
    """Fechas con sentido entre sí y con la fecha de la atención, en el servidor y en el navegador."""

    def setUp(self):
        self.login_as("admin")
        self.today = portal_today()
        self.activity_ = self.activity("María Pérez")

    def day(self, days):
        return (self.today + timedelta(days=days)).isoformat()

    # Compromisos
    def commitment_data(self, **changes):
        data = {
            "requester": "Junta de vecinos",
            "requester_type": Commitment.RequesterType.values[0],
            "source": "",
            "request_date": self.day(-5),
            "description": "Arreglo de luminarias.",
            "territory": Territory.objects.filter(delegation=self.south).first().pk,
            "due_date": self.day(10),
            "support": "",
            "status": Commitment.Status.values[0],
            "notes": "",
            "responsible_officer": self.officer("F-1003").pk if self.officer("F-1003").delegation_id == self.south.pk else self.south.officers.first().pk,
            "delegation": self.south.pk,
        }
        data.update(changes)
        return data

    def test_a_commitment_due_date_is_not_before_its_request_date(self):
        response = self.client.post(reverse("core:agenda_create"), self.commitment_data(due_date=self.day(-6)))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["form"].errors["due_date"],
            ["La fecha comprometida no puede ser anterior a la fecha de solicitud."],
        )
        self.assertFalse(Commitment.objects.filter(requester="Junta de vecinos").exists())

    def test_a_commitment_can_be_due_the_same_day_it_was_requested(self):
        data = self.commitment_data(request_date=self.day(0), due_date=self.day(0))
        self.assertEqual(self.client.post(reverse("core:agenda_create"), data).status_code, 302)

    def test_a_commitment_cannot_be_requested_in_the_future(self):
        response = self.client.post(reverse("core:agenda_create"), self.commitment_data(request_date=self.day(1)))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["form"].errors["request_date"], ["La fecha de solicitud no puede ser futura."])

    def test_an_overdue_commitment_can_still_be_registered(self):
        data = self.commitment_data(request_date=self.day(-30), due_date=self.day(-5))
        self.assertEqual(self.client.post(reverse("core:agenda_create"), data).status_code, 302)

    def test_the_commitment_page_gives_the_browser_its_date_limits(self):
        page = self.client.get(reverse("core:agenda_create")).content.decode()
        request_tag, due_tag = input_tag(page, "request_date"), input_tag(page, "due_date")
        self.assertIn(f'max="{self.today.isoformat()}"', request_tag)
        self.assertIn("data-max-message", request_tag)
        self.assertIn('data-not-before="id_request_date"', due_tag)
        self.assertIn("data-not-before-message", due_tag)

    # Cargos e ítems de cargo
    def test_the_validity_of_a_position_ends_after_it_starts(self):
        data = {"name": "Cargo con vigencia", "valid_from": self.day(-10), "valid_until": self.day(-11)}
        response = self.client.post(reverse("core:cargos_create"), data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["form"].errors["valid_until"],
            ["La vigencia hasta no puede ser anterior a la vigencia desde."],
        )
        self.assertEqual(
            self.client.post(reverse("core:cargos_create"), {**data, "valid_until": self.day(-10)}).status_code, 302
        )

    def test_the_validity_of_a_position_item_ends_after_it_starts(self):
        position = Position.objects.create(name="Cargo para ítem", valid_from=self.today - timedelta(days=90))
        item = Item.objects.create(name="Ítem con vigencia")
        data = {
            "position": position.pk, "item": item.pk, "kind": PositionItem.Kind.NORMAL, "weight": "40", "max_cap": "",
            "valid_from": self.day(-10), "valid_until": self.day(-20),
        }
        response = self.client.post(reverse("core:items_de_cargo_create"), data)
        self.assertEqual(response.status_code, 200)
        self.assertIn("valid_until", response.context["form"].errors)

    def test_the_validity_fields_carry_the_comparison_for_the_browser(self):
        for url in ("core:cargos_create", "core:items_de_cargo_create", "core:periodos_create"):
            page = self.client.get(reverse(url)).content.decode()
            end, start = ("end_date", "start_date") if "periodos" in url else ("valid_until", "valid_from")
            with self.subTest(url=url):
                self.assertIn(f'data-not-before="id_{start}"', input_tag(page, end))

    # Actividad
    def test_an_activity_cannot_be_dated_in_the_future(self):
        activity = self.activity_
        url = reverse("core:actividades_update", args=[activity.pk])
        response = self.client.post(url, self.activity_form_data(activity, date=self.day(1)))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["form"].errors["date"], ["La fecha de la atención no puede ser futura."])
        self.assertEqual(self.client.post(url, self.activity_form_data(activity, date=self.day(0))).status_code, 302)

    def test_the_activity_edit_page_gives_the_browser_its_limit(self):
        page = self.client.get(reverse("core:actividades_update", args=[self.activity_.pk])).content.decode()
        tag = input_tag(page, "date")
        self.assertIn(f'max="{self.today.isoformat()}"', tag)
        self.assertIn("data-max-message", tag)

    def test_the_demo_activities_are_not_in_the_future(self):
        self.assertFalse(Activity.objects.filter(date__gt=self.today).exists())

    # Gestiones
    def followup_data(self, **changes):
        data = {
            "activity": self.activity_.pk,
            "sequence_number": 3,
            "management_type": ManagementType.objects.first().pk,
            "date": self.activity_.date.isoformat(),
            "result": "Se llamó por teléfono.",
        }
        data.update(changes)
        return data

    def assertFollowupRejected(self, field, **changes):
        before = Followup.objects.count()
        response = self.client.post(reverse("core:gestiones_create"), self.followup_data(**changes))
        self.assertEqual(response.status_code, 200, changes)
        self.assertIn(field, response.context["form"].errors, changes)
        self.assertEqual(Followup.objects.count(), before)
        return response.context["form"].errors[field]

    def test_a_valid_followup_is_saved(self):
        data = self.followup_data(
            scheduled_visit_date=self.day(3), visit_date=self.day(-1), report_delivery_date=self.day(0),
            benefit_delivery_date=self.day(0),
        )
        data["date"] = (self.activity_.date + timedelta(days=1)).isoformat()
        self.assertEqual(self.client.post(reverse("core:gestiones_create"), data).status_code, 302)

    def test_a_followup_is_not_dated_before_its_activity_or_in_the_future(self):
        before = (self.activity_.date - timedelta(days=1)).isoformat()
        errors = self.assertFollowupRejected("date", date=before)
        self.assertIn("fecha de la atención", errors[0])
        self.assertEqual(self.assertFollowupRejected("date", date=self.day(1)), ["La fecha de la gestión no puede ser futura."])

    def test_no_followup_date_is_before_the_activity(self):
        before = (self.activity_.date - timedelta(days=1)).isoformat()
        for field in ("scheduled_visit_date", "visit_date", "report_delivery_date", "benefit_delivery_date"):
            with self.subTest(field=field):
                errors = self.assertFollowupRejected(field, **{field: before})
                self.assertIn("anterior a la fecha de la atención", errors[0])

    def test_what_already_happened_is_not_in_the_future_but_a_scheduled_visit_can_be(self):
        for field in ("visit_date", "report_delivery_date", "benefit_delivery_date"):
            with self.subTest(field=field):
                self.assertIn("futura", self.assertFollowupRejected(field, **{field: self.day(1)})[0])
        self.assertEqual(
            self.client.post(reverse("core:gestiones_create"), self.followup_data(scheduled_visit_date=self.day(5))).status_code,
            302,
        )

    def test_the_report_and_the_benefit_are_not_delivered_before_the_visit(self):
        visit = self.day(-1)
        for field in ("report_delivery_date", "benefit_delivery_date"):
            with self.subTest(field=field):
                errors = self.assertFollowupRejected(field, visit_date=visit, **{field: self.day(-2)})
                self.assertIn("anterior a la fecha de la visita", errors[0])

    def test_the_followup_page_gives_the_browser_its_date_limits(self):
        page = self.client.get(reverse("core:gestiones_create")).content.decode()
        for field in ("date", "visit_date", "report_delivery_date", "benefit_delivery_date"):
            with self.subTest(field=field):
                self.assertIn(f'max="{self.today.isoformat()}"', input_tag(page, field))
        self.assertNotIn("max=", input_tag(page, "scheduled_visit_date"))
        for field in ("report_delivery_date", "benefit_delivery_date"):
            self.assertIn('data-not-before="id_visit_date"', input_tag(page, field))


# -- El navegador ---------------------------------------------------------------------------------------------


class BrowserScriptTests(SimpleTestCase):
    """validation.js entiende lo que el servidor le entrega."""

    def script(self):
        path = settings.BASE_DIR / "core" / "static" / "core" / "js" / "validation.js"
        return path.read_text(encoding="utf-8")

    def test_the_script_checks_date_limits_and_comparisons_between_fields(self):
        text = self.script()
        for expected in ("field.dataset.notBefore", "field.dataset.notBeforeMessage", "field.dataset.maxMessage", 'field.type === "date"'):
            self.assertIn(expected, text)

    def test_the_script_knows_the_new_arrangements(self):
        text = self.script()
        for name in ("lines", "none"):
            self.assertRegex(text, rf"(?m)^  {name}:")

    @unittest.skipUnless(shutil.which("node"), "Node.js no está instalado: la paridad Python/JavaScript se comprueba donde haya Node")
    def test_the_patterns_give_the_same_verdict_in_python_and_in_javascript(self):
        samples = {
            "label": ["Visita N°5", "<b>", "a>b", "línea\nsalto", "tab\taquí", "", "Ñandú", "x" * 300],
            "text": ["Línea uno.\nLínea dos.", "con <etiqueta>", "tab\taquí", "campana\x07", "\r\n\r\n", "ñ"],
            "password": list(PasswordRuleTests.SAMPLES),
            "person_name": ["Diego Fuentes", "Ana 2", "O'Higgins", "María-José", ""],
            "hex_color": ["#920000", "#92000", "920000", "#GGGGGG"],
        }
        payload = {name: {"pattern": rules.get_rule(name).pattern, "samples": values} for name, values in samples.items()}
        script = (
            "const data = JSON.parse(require('fs').readFileSync(0, 'utf8'));"
            "const out = {};"
            "for (const [name, item] of Object.entries(data)) {"
            "  const re = new RegExp(`^(?:${item.pattern})$`);"
            "  out[name] = item.samples.map((s) => re.test(s));"
            "}"
            "console.log(JSON.stringify(out));"
        )
        done = subprocess.run(["node", "-e", script], input=json.dumps(payload), capture_output=True, text=True, timeout=30)
        self.assertEqual(done.returncode, 0, done.stderr)
        verdicts = json.loads(done.stdout)
        for name, values in samples.items():
            expected = [re.fullmatch(rules.get_rule(name).pattern, value) is not None for value in values]
            with self.subTest(rule=name):
                self.assertEqual(verdicts[name], expected)
