import re

from django.conf import settings
from django.test import SimpleTestCase
from django.urls import reverse

from core import rules
from core.models import AuditLog
from core.testing import PortalTestCase
from organization.models import Beneficiary, Delegation, Officer


class RuleTests(SimpleTestCase):
    def apply(self, name, text):
        return rules.get_rule(name).apply(text)

    def assertAccepted(self, name, text, becomes=None):
        value, error = self.apply(name, text)
        self.assertIsNone(error, f"{name} debería aceptar {text!r}")
        self.assertEqual(value, text if becomes is None else becomes)

    def assertRejected(self, name, text):
        _, error = self.apply(name, text)
        self.assertEqual(error, rules.get_rule(name).message, f"{name} debería rechazar {text!r}")


    def test_check_digit_follows_modulo_11(self):
        self.assertEqual(rules.rut_check_digit("12345678"), "5")
        self.assertEqual(rules.rut_check_digit("11111111"), "1")
        self.assertEqual(rules.rut_check_digit("10000013"), "K")
        self.assertEqual(rules.rut_check_digit("0"), "0")

    def test_rut_is_kept_without_dots_and_with_dash(self):
        for written in ("12.345.678-5", "12345678-5", "123456785", " 12 345 678 - 5 "):
            self.assertAccepted("rut", written, "12345678-5")
        self.assertAccepted("rut", "10.000.013-k", "10000013-K")
        self.assertAccepted("rut", "1.234.567-4", "1234567-4")

    def test_rut_with_wrong_digit_or_shape_is_rejected(self):
        for written in ("12.345.678-9", "12345678", "1234567", "abc", "", "12.345.678-55"):
            self.assertRejected("rut", written)

    def test_only_a_dashed_rut_with_a_bad_digit_counts_as_a_typo(self):
        self.assertTrue(rules.rut_with_wrong_digit("11.111.111-2"))
        self.assertFalse(rules.rut_with_wrong_digit("11.111.111-1"))
        self.assertFalse(rules.rut_with_wrong_digit("11111111"))
        self.assertFalse(rules.rut_with_wrong_digit("María"))


    def test_phone_accepts_spaces_and_a_plus_but_no_other_signs(self):
        for written in ("+56 9 1234 5678", "912345678", "22 2345678"):
            self.assertAccepted("phone", written)
        self.assertAccepted("phone", "  9  1234 5678 ", "9 1234 5678")
        for written in ("12-34", "12345", "+56-9-1234-5678", "+56 9 1234 5678 9012 3456", "abcdefgh"):
            self.assertRejected("phone", written)

    def test_email_needs_user_domain_and_extension(self):
        self.assertAccepted("email", "nombre@dominio.cl")
        self.assertAccepted("email", "A.B+c@sub.dominio.com")
        self.assertAccepted("email", " nombre@dominio.cl ", "nombre@dominio.cl")
        for written in ("nombre@", "no-es-correo", "a@b", "a b@c.cl"):
            self.assertRejected("email", written)

    def test_person_name_allows_letters_and_a_few_signs(self):
        self.assertAccepted("person_name", "María José O'Higgins-Pérez Jr.")
        self.assertAccepted("person_name", "ñandú")
        self.assertAccepted("person_name", "  Ana   María ", "Ana María")
        for written in ("Pedro 123", "<b>x</b>", "-Pedro", "Ana2"):
            self.assertRejected("person_name", written)

    def test_free_text_cannot_carry_angle_brackets_or_control_characters(self):
        self.assertAccepted("label", "Texto normal, con tildes y ñ")
        for written in ("<script>", "a>b", "ok\x01"):
            self.assertRejected("label", written)


    def test_username_needs_three_characters_without_spaces(self):
        for written in ("matias.cavieres", "usuario_1@x.cl", "Matias"):
            self.assertAccepted("username", written)
        for written in ("ab", "a b", "-abc"):
            self.assertRejected("username", written)

    def test_code_has_no_spaces(self):
        for written in ("EVD-NORTE-0001", "ab", "F-1001"):
            self.assertAccepted("code", written)
        for written in ("A", "a b", ".ab", "x" * 51):
            self.assertRejected("code", written)

    def test_hex_color_is_written_in_capitals(self):
        self.assertAccepted("hex_color", "#920000")
        self.assertAccepted("hex_color", "#2e7d5b", "#2E7D5B")
        self.assertAccepted("hex_color", " #1d4e89 ", "#1D4E89")
        for written in ("#92000", "920000", "#GGGGGG", "rojo"):
            self.assertRejected("hex_color", written)

    def test_version_is_short_and_simple(self):
        for written in ("1", "2.1", "2026-A"):
            self.assertAccepted("version", written)
        for written in ("v 2", "-1", "x" * 21):
            self.assertRejected("version", written)


    def test_attributes_for_the_browser_repeat_the_rule(self):
        rule = rules.get_rule("rut")
        attrs = rule.attrs()
        self.assertEqual(attrs["data-rule"], "rut")
        self.assertEqual(attrs["data-pattern"], rule.pattern)
        self.assertEqual(attrs["data-message"], rule.message)
        self.assertEqual(attrs["data-normalize"], "rut")
        self.assertEqual(attrs["data-check"], "rut")
        self.assertNotIn("data-check", rules.get_rule("phone").attrs())

    def test_every_rule_uses_a_known_normalizer_and_check(self):
        for rule in rules.RULES.values():
            self.assertIn(rule.normalizer, rules.NORMALIZERS, rule.name)
            if rule.check:
                self.assertIn(rule.check, rules.CHECKS, rule.name)

    def test_the_javascript_knows_every_normalizer_and_check(self):
        script = (settings.BASE_DIR / "core" / "static" / "core" / "js" / "validation.js").read_text(
            encoding="utf-8"
        )
        for table, names in (("NORMALIZERS", rules.NORMALIZERS), ("CHECKS", rules.CHECKS)):
            body = re.search(rf"const {table} = \{{(.*?)\n\}};", script, re.S)
            self.assertIsNotNone(body, table)
            for name in names:
                self.assertRegex(body.group(1), rf"(?m)^  {name}:", f"{table}.{name} falta en validation.js")


class FormRuleTests(PortalTestCase):

    def post_beneficiary(self, **changes):
        data = {"rut": "12.345.678-5", "name": "Pedro Pérez", "phone": "", "address": ""}
        data.update(changes)
        return self.client.post(reverse("core:beneficiarios_create"), data)

    def test_form_pages_carry_the_rule_attributes(self):
        self.login_as("admin")
        response = self.client.get(reverse("core:beneficiarios_create"))
        self.assertContains(response, 'data-rule="rut"')
        self.assertContains(response, 'data-check="rut"')
        self.assertContains(response, 'data-rule="phone"')
        self.assertContains(response, 'data-rule="person_name"')
        self.assertContains(response, "data-validate")

    def test_messy_text_is_fixed_before_saving(self):
        self.login_as("admin")
        response = self.post_beneficiary(
            rut=" 12.345.678-5 ", name="  Pedro   Pérez ", phone="+56  9 1234 5678"
        )
        self.assertEqual(response.status_code, 302)
        saved = Beneficiary.objects.get(rut="12345678-5")
        self.assertEqual(saved.name, "Pedro Pérez")
        self.assertEqual(saved.phone, "+56 9 1234 5678")

    def test_bad_values_show_their_message_and_save_nothing(self):
        self.login_as("admin")
        before = Beneficiary.objects.count()
        response = self.post_beneficiary(rut="11.111.111-2", name="Pedro 123", phone="12-34")
        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        self.assertEqual(form.errors["rut"], [rules.get_rule("rut").message])
        self.assertEqual(form.errors["name"], [rules.get_rule("person_name").message])
        self.assertEqual(form.errors["phone"], [rules.get_rule("phone").message])
        self.assertEqual(Beneficiary.objects.count(), before)

    def test_blank_required_fields_are_reported(self):
        self.login_as("admin")
        response = self.post_beneficiary(rut="", name="")
        self.assertEqual(response.status_code, 200)
        self.assertIn("rut", response.context["form"].errors)
        self.assertIn("name", response.context["form"].errors)

    def test_a_rut_written_differently_is_still_a_duplicate(self):
        self.login_as("admin")
        before = Beneficiary.objects.count()
        response = self.post_beneficiary(rut="11.111.111-1", name="Otra Persona")
        self.assertEqual(response.status_code, 200)
        self.assertIn("rut", response.context["form"].errors)
        self.assertEqual(Beneficiary.objects.count(), before)

    def test_officer_code_and_name_follow_their_rules(self):
        self.login_as("admin")
        data = {
            "institutional_id": "F 3001",
            "name": "Ana 2",
            "status": Officer.Status.ACTIVE,
            "delegation": self.north.pk,
            "position": self.officer("F-1001").position_id,
        }
        response = self.client.post(reverse("core:funcionarios_create"), data)
        self.assertEqual(response.status_code, 200)
        self.assertIn("institutional_id", response.context["form"].errors)
        self.assertIn("name", response.context["form"].errors)
        data.update(institutional_id="F-3001", name="Ana Torres")
        response = self.client.post(reverse("core:funcionarios_create"), data)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Officer.objects.filter(institutional_id="F-3001", name="Ana Torres").exists())

    def test_text_with_angle_brackets_is_still_stored_as_text_and_shown_escaped(self):
        self.login_as("admin")
        Beneficiary.objects.create(rut="12345678-5", name="Pedro Pérez", address="<b>Calle 1</b>")
        response = self.client.get(reverse("core:beneficiarios_list"))
        self.assertNotContains(response, "<b>Calle 1</b>")
        self.assertContains(response, "&lt;b&gt;Calle 1&lt;/b&gt;")


class DelegationFormTests(PortalTestCase):
    def update_url(self):
        return reverse("core:delegaciones_update", args=[self.north.pk])

    def delegation_data(self, **changes):
        data = {
            "name": self.north.name,
            "address": self.north.address,
            "commune": self.north.commune,
            "managers": self.north.managers,
            "color": self.north.color,
            "scope": self.north.scope,
            "status": self.north.status,
        }
        data.update(changes)
        return data

    def test_form_shows_id_name_manager_with_lookup_and_color_picker(self):
        self.login_as("admin")
        response = self.client.get(self.update_url())
        self.assertContains(response, "Id delegación")
        self.assertContains(response, "Encargado")
        self.assertContains(response, 'data-lookup-open')
        self.assertContains(response, 'type="color"')
        self.assertContains(response, 'data-rule="hex_color"')
        self.assertContains(response, 'value="Diego Fuentes"')
        self.assertContains(response, "Coordinador de Terreno · Delegación Norte")

    def test_form_has_the_four_buttons(self):
        self.login_as("admin")
        response = self.client.get(self.update_url())
        for text in ("Guardar", "Guardar y agregar otro", "Eliminar", "Cancelar"):
            self.assertContains(response, text)

    def test_color_must_be_a_hex_code_and_is_stored_in_capitals(self):
        self.login_as("admin")
        response = self.client.post(self.update_url(), self.delegation_data(color="rojo"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("color", response.context["form"].errors)
        self.north.refresh_from_db()
        self.assertEqual(self.north.color, "#1D4E89")

        response = self.client.post(self.update_url(), self.delegation_data(color="#2e7d5b"))
        self.assertEqual(response.status_code, 302)
        self.north.refresh_from_db()
        self.assertEqual(self.north.color, "#2E7D5B")

    def test_saving_without_changes_leaves_no_audit_entry(self):
        self.login_as("admin")
        response = self.client.post(self.update_url(), self.delegation_data())
        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            AuditLog.objects.filter(event="Registro modificado", record_id=self.north.pk).exists()
        )

    def test_the_manager_can_be_any_text(self):
        self.login_as("admin")
        response = self.client.post(self.update_url(), self.delegation_data(managers="Persona de afuera"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Delegation.objects.get(pk=self.north.pk).managers, "Persona de afuera")

    def test_new_delegation_gets_the_default_color_when_the_field_is_left_as_is(self):
        self.login_as("admin")
        response = self.client.get(reverse("core:delegaciones_create"))
        self.assertContains(response, "#920000")
        response = self.client.post(
            reverse("core:delegaciones_create"),
            {
                "name": "Delegación Centro",
                "address": "Av. del Mar 1500",
                "commune": "La Serena",
                "managers": "",
                "color": "#920000",
                "scope": "",
                "status": "active",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Delegation.objects.get(name="Delegación Centro").color, "#920000")
