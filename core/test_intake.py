import json
import re

from django.contrib.auth.models import Group, Permission, User
from django.contrib.messages import get_messages
from django.core.exceptions import FieldDoesNotExist
from django.urls import reverse
from django.utils import timezone

from core.models import AuditLog
from core.testing import PortalTestCase, portal_today
from core.registry import attention_type_name, sub_attention_name
from operations.models import Activity
from organization.models import Beneficiary, Item, Service


def user_named(username):
    return User.objects.get(username=username)


class IntakeCase(PortalTestCase):

    def setUp(self):
        self.login_as("matias.cavieres")

    def register(self, **changes):
        return self.client.post(reverse("core:actividades_create"), self.intake_data(**changes))

    def newest(self):
        return Activity.objects.order_by("-pk").first()

    def person(self, rut):
        return Beneficiary.objects.get(rut=rut)

    def archive(self, obj):
        obj.deleted_at = timezone.now()
        obj.save(update_fields=["deleted_at"])

    def assertSaved(self, response):
        created = self.newest()
        self.assertRedirects(
            response, reverse("core:actividades_detail", args=[created.pk]), fetch_redirect_response=False
        )
        return created

    def assertRejected(self, response, field, text):
        self.assertEqual(response.status_code, 200)
        self.assertIn(field, response.context["form"].errors)
        self.assertContains(response, text)


class RequesterTests(IntakeCase):
    def test_a_rut_with_dots_and_dash_links_the_person(self):
        maria = self.person("11111111-1")
        created = self.assertSaved(self.register(requester="11.111.111-1"))
        self.assertEqual(created.beneficiary, maria)
        self.assertEqual(created.contact_name, "María Pérez")

    def test_a_rut_without_dots_or_dash_links_the_person(self):
        for text in ("111111111", "11111111-1", "11.111.1111", "  11.111.111-1  "):
            with self.subTest(text=text):
                created = self.assertSaved(self.register(requester=text))
                self.assertEqual(created.beneficiary, self.person("11111111-1"))

    def test_a_rut_that_ends_in_k_is_understood(self):
        Beneficiary.objects.create(rut="12345670-K", name="Karen Kast")
        created = self.assertSaved(self.register(requester="12.345.670-k"))
        self.assertEqual(created.beneficiary.name, "Karen Kast")

    def test_the_exact_name_links_the_person_ignoring_case_accents_and_extra_spaces(self):
        for text in ("María Pérez", "maria perez", "  MARÍA    PEREZ ", "María Perez"):
            with self.subTest(text=text):
                created = self.assertSaved(self.register(requester=text))
                self.assertEqual(created.beneficiary, self.person("11111111-1"))
                self.assertEqual(created.contact_name, "María Pérez")

    def test_a_name_that_is_not_in_beneficiaries_is_kept_as_a_written_contact(self):
        created = self.assertSaved(self.register(requester="Rosa Prueba"))
        self.assertIsNone(created.beneficiary)
        self.assertEqual(created.contact_name, "Rosa Prueba")

    def test_extra_spaces_of_a_written_contact_are_cleaned(self):
        created = self.assertSaved(self.register(requester="   Rosa     Prueba   "))
        self.assertEqual(created.contact_name, "Rosa Prueba")

    def test_a_partial_name_does_not_link_anyone(self):
        created = self.assertSaved(self.register(requester="María"))
        self.assertIsNone(created.beneficiary)
        self.assertEqual(created.contact_name, "María")

    def test_a_wrong_check_digit_is_rejected(self):
        before = Activity.objects.count()
        response = self.register(requester="11.111.111-2")
        self.assertRejected(response, "requester", "Escribe un RUT válido")
        self.assertEqual(Activity.objects.count(), before)

    def test_a_valid_rut_that_is_not_registered_is_rejected_with_a_hint_for_the_user(self):
        before = Activity.objects.count()
        response = self.register(requester="12.345.678-5")
        self.assertRejected(response, "requester", "No hay ninguna persona con ese RUT en Beneficiarios.")
        self.assertEqual(Activity.objects.count(), before)
        self.assertRejected(response, "requester", "Pide que la registren en Beneficiarios")

    def test_who_can_register_beneficiaries_is_told_to_do_it(self):
        self.give_perm(user_named("matias.cavieres"), "organization.add_beneficiary")
        response = self.register(requester="12.345.678-5")
        self.assertRejected(response, "requester", "Regístrala primero en Beneficiarios")

    def test_an_archived_person_is_rejected_when_typed_by_rut(self):
        self.archive(self.person("11111111-1"))
        before = Activity.objects.count()
        response = self.register(requester="11.111.111-1")
        self.assertRejected(response, "requester", "archivada")
        self.assertEqual(Activity.objects.count(), before)

    def test_an_archived_person_typed_by_name_is_only_a_written_contact(self):
        self.archive(self.person("11111111-1"))
        created = self.assertSaved(self.register(requester="María Pérez"))
        self.assertIsNone(created.beneficiary)
        self.assertEqual(created.contact_name, "María Pérez")

    def test_two_people_with_the_same_name_ask_for_the_rut(self):
        Beneficiary.objects.create(rut="12345678-5", name="Maria Perez")
        before = Activity.objects.count()
        response = self.register(requester="María Pérez")
        self.assertRejected(response, "requester", "Hay más de una persona con ese nombre")
        self.assertEqual(Activity.objects.count(), before)

    def test_the_rut_picks_the_right_one_when_the_name_is_repeated(self):
        other = Beneficiary.objects.create(rut="12345678-5", name="Maria Perez")
        created = self.assertSaved(self.register(requester="12.345.678-5"))
        self.assertEqual(created.beneficiary, other)

    def test_a_long_name_is_cut_to_the_size_of_the_contact_field(self):
        long_name = "Ana " + "María " * 20 + "Fin"
        self.assertGreater(len(long_name), 100)
        Beneficiary.objects.create(rut="12345678-5", name=long_name)
        created = self.assertSaved(self.register(requester="12345678-5"))
        self.assertEqual(created.contact_name, long_name[:100])
        self.assertEqual(created.beneficiary.name, long_name)

    def test_the_field_does_not_take_more_than_the_contact_can_hold(self):
        response = self.register(requester="Ñ" * 101)
        self.assertEqual(response.status_code, 200)
        self.assertIn("requester", response.context["form"].errors)

    def test_the_requester_is_required(self):
        for text in ("", "   "):
            with self.subTest(text=text):
                response = self.register(requester=text)
                self.assertRejected(response, "requester", "Este campo es obligatorio.")

    def test_the_phone_rule_still_applies(self):
        self.assertRejected(self.register(phone="123"), "phone", "El teléfono debe tener entre 8 y 14 números")
        created = self.assertSaved(self.register(phone="+56 9 1234 5678"))
        self.assertEqual(created.phone, "+56 9 1234 5678")

    def test_the_person_is_only_linked_through_the_requester_field(self):
        juan = self.person("22222222-2")
        created = self.assertSaved(self.register(requester="Rosa Prueba", beneficiary=juan.pk, contact_name="Otro"))
        self.assertIsNone(created.beneficiary)
        self.assertEqual(created.contact_name, "Rosa Prueba")

    def test_the_search_box_lists_the_active_people_to_choose_from(self):
        self.archive(self.person("88888888-8"))
        response = self.client.get(reverse("core:actividades_create"))
        self.assertContains(response, "data-lookup-open")
        self.assertContains(response, '<option value="11111111-1" label="María Pérez')
        self.assertNotContains(response, '<option value="88888888-8"')
        self.assertContains(response, "Buscar por RUT, nombre o dirección")


class AttentionTypeTests(IntakeCase):
    def type_named(self, name):
        return Item.objects.get(name=name, parent_item__isnull=True)

    def test_a_type_with_sub_attentions_asks_for_one(self):
        before = Activity.objects.count()
        response = self.register(attention_type=self.type_named("Atención Social").pk, item="")
        self.assertRejected(response, "item", "Elige una sub atención de este tipo de atención.")
        self.assertEqual(Activity.objects.count(), before)

    def test_the_chosen_sub_attention_is_the_item_of_the_activity(self):
        sub = Item.objects.get(name="Seguimiento Telefónico")
        created = self.assertSaved(self.register(attention_type=sub.parent_item_id, item=sub.pk))
        self.assertEqual(created.item, sub)

    def test_a_type_without_sub_attentions_is_saved_as_the_item_itself(self):
        kind = self.type_named("Coordinación Territorial")
        created = self.assertSaved(self.register(attention_type=kind.pk, item=""))
        self.assertEqual(created.item, kind)

    def test_a_type_whose_sub_attentions_are_all_archived_counts_as_having_none(self):
        social = self.type_named("Atención Social")
        for sub in Item.objects.filter(parent_item=social):
            self.archive(sub)
        created = self.assertSaved(self.register(attention_type=social.pk, item=""))
        self.assertEqual(created.item, social)

    def test_an_archived_sub_attention_is_not_accepted(self):
        sub = Item.objects.get(name="Visita Domiciliaria")
        self.archive(sub)
        response = self.register(attention_type=sub.parent_item_id, item=sub.pk)
        self.assertEqual(response.status_code, 200)
        self.assertIn("item", response.context["form"].errors)

    def test_an_archived_type_is_not_accepted(self):
        kind = self.type_named("Entrega de Ayudas Sociales")
        self.archive(kind)
        response = self.register(attention_type=kind.pk, item="")
        self.assertEqual(response.status_code, 200)
        self.assertIn("attention_type", response.context["form"].errors)

    def test_a_sub_attention_of_a_type_without_sub_attentions_is_rejected(self):
        kind = self.type_named("Entrega de Ayudas Sociales")
        sub = Item.objects.get(name="Visita Domiciliaria")
        response = self.register(attention_type=kind.pk, item=sub.pk)
        self.assertRejected(response, "item", "Esa sub atención no pertenece al tipo de atención elegido.")

    def test_a_sub_attention_of_another_type_with_sub_attentions_is_rejected(self):
        other = Item.objects.create(name="Otro Tipo")
        foreign = Item.objects.create(name="Otra Sub", parent_item=other)
        social = self.type_named("Atención Social")
        response = self.register(attention_type=social.pk, item=foreign.pk)
        self.assertRejected(response, "item", "Esa sub atención no pertenece al tipo de atención elegido.")

    def test_a_sub_attention_cannot_be_sent_as_the_type(self):
        sub = Item.objects.get(name="Visita Domiciliaria")
        response = self.register(attention_type=sub.pk, item=sub.pk)
        self.assertEqual(response.status_code, 200)
        self.assertIn("attention_type", response.context["form"].errors)

    def test_the_type_is_required(self):
        response = self.register(attention_type="", item="")
        self.assertRejected(response, "attention_type", "Este campo es obligatorio.")

    def test_the_form_offers_only_the_types_and_labels_every_sub_attention_with_its_type(self):
        response = self.client.get(reverse("core:actividades_create"))
        form = response.context["form"]
        types = [item.name for item in form.fields["attention_type"].queryset]
        self.assertEqual(types, ["Atención Social", "Coordinación Territorial", "Entrega de Ayudas Sociales"])
        labels = [label for _value, label in form.fields["item"].choices if _value]
        self.assertEqual(labels, ["Atención Social · Seguimiento Telefónico", "Atención Social · Visita Domiciliaria"])
        self.assertContains(response, 'data-depends-on="id_attention_type"')
        self.assertContains(response, 'data-choose-if-options="1"')
        sub = Item.objects.get(name="Visita Domiciliaria")
        self.assertContains(response, f'data-parent="{sub.parent_item_id}"')
        select = re.search(r'<select[^>]*id="id_item"[^>]*>', response.content.decode())
        self.assertIsNotNone(select)
        self.assertNotIn("required", select.group(0))

    def test_the_attention_type_and_sub_attention_are_shown_in_the_list_and_the_ficha(self):
        sub = Item.objects.get(name="Seguimiento Telefónico")
        created = self.assertSaved(self.register(attention_type=sub.parent_item_id, item=sub.pk))
        listing = self.client.get(reverse("core:atencion"))
        labels = [column.label for column in listing.context["columns"]]
        self.assertEqual(labels[:6], ["Identificador", "Fecha", "Contacto", "RUT", "Tipo de atención", "Sub atención"])
        self.assertContains(listing, "Atención Social")
        self.assertContains(listing, "Seguimiento Telefónico")
        detail = self.client.get(reverse("core:actividades_detail", args=[created.pk]))
        self.assertContains(detail, "Seguimiento Telefónico")

    def test_a_type_without_sub_attentions_shows_an_empty_sub_attention_column(self):
        kind = self.type_named("Coordinación Territorial")
        created = self.assertSaved(self.register(attention_type=kind.pk, item=""))
        self.assertEqual(attention_type_name(created), "Coordinación Territorial")
        self.assertEqual(sub_attention_name(created), "")


class FixedProfileTests(IntakeCase):
    def test_the_form_does_not_ask_for_what_it_fills_in_itself(self):
        form = self.client.get(reverse("core:actividades_create")).context["form"]
        for name in ("date", "delegation", "author_officer", "status", "beneficiary", "contact_name"):
            self.assertNotIn(name, form.fields)
        self.assertEqual(
            list(form.fields),
            [
                "requester",
                "phone",
                "attention_type",
                "item",
                "service",
                "request_description",
                "action_taken",
                "requires_visit",
                "added_to_pipeline",
            ],
        )

    def test_the_note_says_what_is_filled_in_and_who_is_the_responsible(self):
        response = self.client.get(reverse("core:actividades_create"))
        self.assertContains(response, "Se completan solos")
        self.assertContains(response, "Delegación Norte")
        self.assertContains(response, "Matías Cavieres")
        self.assertContains(response, "El identificador se asigna al guardar.")

    def test_the_date_is_today_whatever_is_sent(self):
        created = self.assertSaved(self.register(date="2020-01-01"))
        self.assertEqual(created.date, portal_today())

    def test_the_status_starts_as_registered_whatever_is_sent(self):
        created = self.assertSaved(self.register(status="closed"))
        self.assertEqual(created.status, Activity.Status.REGISTERED)

    def test_the_delegation_and_the_officer_are_the_ones_of_the_user(self):
        created = self.assertSaved(self.register())
        self.assertEqual(created.delegation, self.north)
        self.assertEqual(created.author_officer, self.officer("F-1001"))

    def test_forged_delegation_and_officer_are_ignored(self):
        created = self.assertSaved(
            self.register(delegation=self.south.pk, author_officer=self.officer("F-2001").pk)
        )
        self.assertEqual(created.delegation, self.north)
        self.assertEqual(created.author_officer, self.officer("F-1001"))

    def test_each_officer_registers_in_their_own_delegation(self):
        self.client.logout()
        self.login_as("matias.quiroz")
        created = self.assertSaved(self.register())
        self.assertEqual(created.delegation, self.south)
        self.assertEqual(created.author_officer, self.officer("F-2001"))
        form = self.client.get(reverse("core:actividades_create")).context["form"]
        self.assertIn("Delegación Sur", form.note)
        self.assertIn("Matías Quiroz", form.note)

    def test_the_flags_can_be_marked_when_registering(self):
        created = self.assertSaved(self.register(requires_visit="on", added_to_pipeline="on"))
        self.assertTrue(created.requires_visit)
        self.assertTrue(created.added_to_pipeline)
        plain = self.assertSaved(self.register())
        self.assertFalse(plain.requires_visit)
        self.assertFalse(plain.added_to_pipeline)

    def test_the_service_is_optional_and_can_be_chosen(self):
        self.assertSaved(self.register(service=""))
        service = Service.objects.get(name="Vivienda")
        created = self.assertSaved(self.register(service=service.pk))
        self.assertEqual(created.service, service)

    def test_the_action_is_optional(self):
        created = self.assertSaved(self.register(action_taken=""))
        self.assertEqual(created.action_taken, "")

    def test_the_description_is_required_to_register(self):
        before = Activity.objects.count()
        for empty in ("", "   ", "\n\t "):
            response = self.register(request_description=empty)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "la descripción es obligatoria para registrar la atención")
        self.assertEqual(Activity.objects.count(), before)

    def test_the_description_field_says_so_on_the_screen(self):
        response = self.client.get(reverse("core:actividades_create"))
        form = response.context["form"]
        self.assertTrue(form.fields["request_description"].required)
        self.assertEqual(form.fields["request_description"].label, "Descripción de la atención")
        self.assertContains(response, 'placeholder="Describe la solicitud y los antecedentes necesarios."')
        self.assertContains(response, "data-required-message=")

    def test_an_existing_attention_can_still_be_edited_without_a_description(self):
        created = self.assertSaved(self.register())
        field = Activity._meta.get_field("request_description")
        self.assertTrue(field.blank)
        form = self.client.get(reverse("core:actividades_update", args=[created.pk])).context["form"]
        self.assertFalse(form.fields["request_description"].required)


class SuperuserIntakeTests(IntakeCase):

    def setUp(self):
        self.login_as("admin")

    def test_it_chooses_the_delegation_and_the_officer(self):
        form = self.client.get(reverse("core:actividades_create")).context["form"]
        self.assertIn("delegation", form.fields)
        self.assertIn("author_officer", form.fields)
        self.assertTrue(form.fields["delegation"].required)
        self.assertTrue(form.fields["author_officer"].required)
        self.assertNotIn("Delegación Norte", form.note)

    def test_it_saves_with_what_it_chose(self):
        created = self.assertSaved(
            self.register(delegation=self.north.pk, author_officer=self.officer("F-1001").pk)
        )
        self.assertEqual((created.delegation, created.author_officer), (self.north, self.officer("F-1001")))
        self.assertEqual(created.date, portal_today())
        self.assertEqual(created.status, Activity.Status.REGISTERED)

    def test_it_cannot_leave_them_empty(self):
        response = self.register()
        self.assertEqual(response.status_code, 200)
        errors = response.context["form"].errors
        self.assertIn("delegation", errors)
        self.assertIn("author_officer", errors)

    def test_a_user_without_officer_and_without_global_role_cannot_register(self):
        self.client.logout()
        user = self.make_user("sin.funcionario", groups=["Funcionario"])
        self.client.force_login(user)
        before = Activity.objects.count()
        response = self.register(delegation=self.north.pk, author_officer=self.officer("F-1001").pk)
        self.assertNotEqual(response.status_code, 302)
        self.assertEqual(Activity.objects.count(), before)


class IdentifierTests(IntakeCase):
    def test_the_message_names_the_person_and_the_identifier(self):
        created = self.assertSaved(self.register())
        identifier = f"ATN{created.pk:05d}"
        self.assertRegex(identifier, r"^ATN\d{5}$")
        detail = self.client.get(reverse("core:actividades_detail", args=[created.pk]))
        self.assertContains(detail, f"Atención registrada para Rosa Prueba. Identificador: {identifier}.")
        self.assertContains(detail, identifier)

    def test_the_identifier_is_derived_from_the_id_and_is_not_a_database_column(self):
        for name in ("identifier", "code", "identificador", "codigo"):
            with self.subTest(name=name):
                with self.assertRaises(FieldDoesNotExist):
                    Activity._meta.get_field(name)

    def test_every_attention_has_its_own_identifier_in_the_list(self):
        first = self.assertSaved(self.register(requester="Persona Uno"))
        second = self.assertSaved(self.register(requester="Persona Dos"))
        self.assertNotEqual(first.pk, second.pk)
        listing = self.client.get(reverse("core:atencion"))
        self.assertContains(listing, f"ATN{first.pk:05d}")
        self.assertContains(listing, f"ATN{second.pk:05d}")

    def test_the_registration_is_audited(self):
        user = user_named("matias.cavieres")
        created = self.assertSaved(self.register())
        log = AuditLog.objects.get(event="Registro creado", record_id=created.pk, affected_entity="Activity")
        self.assertEqual(log.user, user)

    def test_nothing_is_saved_or_audited_when_the_form_has_mistakes(self):
        before = Activity.objects.count()
        logs = AuditLog.objects.count()
        self.register(requester="11.111.111-2")
        self.assertEqual(Activity.objects.count(), before)
        self.assertEqual(AuditLog.objects.count(), logs)


class IntakeModalTests(IntakeCase):
    def post_modal(self, **changes):
        return self.client.post(reverse("core:actividades_create") + "?modal=1", self.intake_data(**changes))

    def test_the_window_has_the_same_fields_and_the_dependent_list(self):
        response = self.client.get(reverse("core:actividades_create"), {"modal": "1"})
        self.assertEqual(response["X-Modal"], "form")
        self.assertContains(response, "Registrar atención")
        self.assertContains(response, 'data-depends-on="id_attention_type"')
        self.assertContains(response, "data-lookup-open")
        self.assertContains(response, "Se completan solos")
        self.assertNotContains(response, "<html")

    def test_saving_answers_with_the_message_that_includes_the_identifier(self):
        response = self.post_modal()
        self.assertEqual(response["X-Modal"], "saved")
        result = json.loads(response.content)
        created = self.newest()
        self.assertTrue(result["saved"])
        self.assertFalse(result["again"])
        self.assertEqual(result["message"], f"Atención registrada para Rosa Prueba. Identificador: ATN{created.pk:05d}.")

    def test_a_mistake_comes_back_inside_the_window(self):
        before = Activity.objects.count()
        response = self.post_modal(requester="11.111.111-2")
        self.assertEqual(response["X-Modal"], "form")
        self.assertContains(response, "Escribe un RUT válido")
        self.assertContains(response, "is-invalid")
        self.assertEqual(Activity.objects.count(), before)

    def test_save_and_add_another_keeps_the_window_open_for_the_next_attention(self):
        response = self.client.post(
            reverse("core:actividades_create") + "?modal=1", {**self.intake_data(), "_addanother": "1"}
        )
        result = json.loads(response.content)
        self.assertTrue(result["saved"] and result["again"])
        self.assertEqual(result["create_url"], reverse("core:actividades_create"))
        self.assertEqual(list(get_messages(response.wsgi_request)), [])


class IntakePermissionTests(PortalTestCase):
    def test_only_who_can_add_activities_opens_the_form(self):
        url = reverse("core:actividades_create")
        before = Activity.objects.count()
        for username in ("jefatura1", "consulta1", "coordinacion1"):
            with self.subTest(username=username):
                self.client.force_login(user_named(username))
                self.assertEqual(self.client.get(url).status_code, 403)
                self.assertEqual(self.client.get(url, {"modal": "1"}).status_code, 403)
                self.assertEqual(self.client.post(url, self.intake_data()).status_code, 403)
        self.assertEqual(Activity.objects.count(), before)

    def test_the_funcionario_and_the_superuser_can(self):
        url = reverse("core:actividades_create")
        for username in ("matias.cavieres", "matias.quiroz", "admin"):
            with self.subTest(username=username):
                self.client.force_login(user_named(username))
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_anonymous_users_are_sent_to_the_login(self):
        response = self.client.get(reverse("core:actividades_create"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("core:login") + "?next=", response["Location"])
        self.assertEqual(self.client.post(reverse("core:actividades_create"), self.intake_data()).status_code, 302)

    def test_the_role_matrix_decides_it(self):
        group = Group.objects.get(name="Funcionario")
        group.permissions.remove(Permission.objects.get(codename="add_activity", content_type__app_label="operations"))
        self.client.force_login(user_named("matias.cavieres"))
        self.assertEqual(self.client.get(reverse("core:actividades_create")).status_code, 403)


class PrefilledPersonTests(IntakeCase):
    def url(self, value):
        return f"{reverse('core:actividades_create')}?beneficiary={value}"

    def test_the_button_of_a_row_starts_the_form_with_that_person(self):
        maria = self.person("11111111-1")
        form = self.client.get(self.url(maria.pk)).context["form"]
        self.assertEqual(form["requester"].value(), "11111111-1")
        self.assertEqual(form["phone"].value(), "+56911111111")

    def test_the_prefilled_form_links_the_person_when_saved(self):
        maria = self.person("11111111-1")
        form = self.client.get(self.url(maria.pk)).context["form"]
        data = self.intake_data(requester=form["requester"].value(), phone=form["phone"].value())
        created = self.assertSaved(self.client.post(reverse("core:actividades_create"), data))
        self.assertEqual(created.beneficiary, maria)
        self.assertEqual(created.phone, "+56911111111")

    def test_a_person_the_user_never_attended_is_not_filled_in(self):
        ana = self.person("33333333-3")
        form = self.client.get(self.url(ana.pk)).context["form"]
        self.assertFalse(form["requester"].value())
        self.assertFalse(form["phone"].value())

    def test_who_can_see_beneficiaries_gets_any_person(self):
        self.give_perm(user_named("matias.cavieres"), "organization.view_beneficiary")
        ana = self.person("33333333-3")
        form = self.client.get(self.url(ana.pk)).context["form"]
        self.assertEqual(form["requester"].value(), "33333333-3")

    def test_wrong_ids_are_ignored(self):
        for value in ("abc", "0", "999999", "-1", "1;2", ""):
            with self.subTest(value=value):
                response = self.client.get(self.url(value))
                self.assertEqual(response.status_code, 200)
                self.assertFalse(response.context["form"]["requester"].value())

    def test_an_archived_person_is_not_filled_in(self):
        maria = self.person("11111111-1")
        self.archive(maria)
        form = self.client.get(self.url(maria.pk)).context["form"]
        self.assertFalse(form["requester"].value())


class EditStaysTheSameTests(IntakeCase):
    def test_editing_uses_the_full_form(self):
        created = self.assertSaved(self.register())
        form = self.client.get(reverse("core:actividades_update", args=[created.pk])).context["form"]
        for name in ("date", "item", "service", "beneficiary", "contact_name", "phone", "status", "requires_visit"):
            self.assertIn(name, form.fields)
        self.assertNotIn("requester", form.fields)
        self.assertNotIn("attention_type", form.fields)

    def test_the_status_is_changed_by_editing(self):
        created = self.assertSaved(self.register())
        url = reverse("core:actividades_update", args=[created.pk])
        page = self.client.get(url)
        data = self.activity_form_data(created, status=Activity.Status.IN_PROGRESS)
        data["_version"] = page.context["version"]
        response = self.client.post(url, data)
        self.assertRedirects(response, reverse("core:actividades_detail", args=[created.pk]), fetch_redirect_response=False)
        created.refresh_from_db()
        self.assertEqual(created.status, Activity.Status.IN_PROGRESS)
