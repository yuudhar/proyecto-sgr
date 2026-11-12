"""Versión 39: directiva de las organizaciones y tipo de solicitante (persona natural u organización) en la atención."""
from django.urls import reverse

from core.testing import PortalTestCase
from operations.models import Activity
from organization.models import Beneficiary, CommunityOrganization, OrganizationLeader

ROLE = OrganizationLeader.Role


def make_organization(number, name="Junta de Prueba"):
    return CommunityOrganization.objects.create(name=f"{name} {number}", registry_number=number)


def make_leader(organization, role, rut, name="Persona de Prueba", **changes):
    return OrganizationLeader.objects.create(organization=organization, role=role, rut=rut, name=name, **changes)


class LeaderBase(PortalTestCase):

    def setUp(self):
        self.admin = self.login_as("admin")
        self.organization = CommunityOrganization.objects.get(registry_number=1001)
        self.empty = make_organization(7001)

    def form(self, organization=None, **changes):
        data = {
            "organization": (organization or self.empty).pk,
            "role": ROLE.DIRECTOR,
            "role_detail": "",
            "name": "Elena Fuentes Ruiz",
            "rut": "17.283.946-0",
            "email": "",
        }
        data.update(changes)
        return data


class DirectivaTests(LeaderBase):
    """La directiva es un registro propio de cada organización: cargo, nombre, RUT y correo."""

    def test_the_menu_lists_directivas_next_to_organizaciones(self):
        response = self.client.get(reverse("core:directivas_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Directivas de organizaciones")
        self.assertContains(response, reverse("core:directivas_list"))

    def test_a_member_is_created_with_the_rut_normalized(self):
        response = self.client.post(reverse("core:directivas_create"), self.form(role=ROLE.PRESIDENT))
        self.assertEqual(response.status_code, 302)
        leader = OrganizationLeader.objects.get(organization=self.empty)
        self.assertEqual(leader.rut, "17283946-0")
        self.assertEqual(leader.role, ROLE.PRESIDENT)

    def test_the_demo_organization_comes_with_its_directiva(self):
        roles = set(self.organization.leaders.values_list("role", flat=True))
        self.assertTrue({ROLE.PRESIDENT, ROLE.SECRETARY, ROLE.TREASURER} <= roles)

    def test_the_organization_page_shows_the_directiva_and_a_link_to_add(self):
        response = self.client.get(reverse("core:organizaciones_detail", args=[self.organization.pk]))
        self.assertContains(response, "Directiva")
        self.assertContains(response, "Gloria Tapia Soto")
        self.assertContains(response, f"{reverse('core:directivas_create')}?organization={self.organization.pk}")

    def test_the_link_to_add_comes_with_the_organization_chosen(self):
        response = self.client.get(reverse("core:directivas_create"), {"organization": self.empty.pk})
        self.assertEqual(response.context["form"].initial["organization"], str(self.empty.pk))

    def test_a_second_president_in_the_same_organization_is_refused(self):
        make_leader(self.empty, ROLE.PRESIDENT, "12345678-5", "Primera Presidenta")
        response = self.client.post(reverse("core:directivas_create"), self.form(role=ROLE.PRESIDENT))
        self.assertEqual(response.status_code, 200)
        self.assertIn("role", response.context["form"].errors)
        self.assertContains(response, "Primera Presidenta")
        self.assertEqual(self.empty.leaders.count(), 1)

    def test_the_same_cargo_can_be_held_in_another_organization(self):
        make_leader(self.empty, ROLE.PRESIDENT, "12345678-5")
        other = make_organization(7002)
        response = self.client.post(reverse("core:directivas_create"), self.form(other, role=ROLE.PRESIDENT))
        self.assertEqual(response.status_code, 302)

    def test_several_directivos_are_allowed(self):
        make_leader(self.empty, ROLE.DIRECTOR, "12345678-5")
        response = self.client.post(reverse("core:directivas_create"), self.form(role=ROLE.DIRECTOR))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.empty.leaders.count(), 2)

    def test_the_same_rut_twice_in_one_organization_is_refused(self):
        make_leader(self.empty, ROLE.DIRECTOR, "17283946-0")
        response = self.client.post(reverse("core:directivas_create"), self.form(role=ROLE.TREASURER))
        self.assertEqual(response.status_code, 200)
        self.assertIn("rut", response.context["form"].errors)

    def test_a_person_can_be_in_the_directiva_of_two_organizations(self):
        make_leader(self.empty, ROLE.DIRECTOR, "17283946-0")
        other = make_organization(7003)
        response = self.client.post(reverse("core:directivas_create"), self.form(other, role=ROLE.TREASURER))
        self.assertEqual(response.status_code, 302)

    def test_otro_cargo_asks_for_its_detail_and_the_other_cargos_drop_it(self):
        refused = self.client.post(reverse("core:directivas_create"), self.form(role=ROLE.OTHER))
        self.assertEqual(refused.status_code, 200)
        self.assertIn("role_detail", refused.context["form"].errors)
        self.client.post(reverse("core:directivas_create"), self.form(role=ROLE.OTHER, role_detail="Delegado de calle"))
        self.assertEqual(OrganizationLeader.objects.get(organization=self.empty).role_text(), "Delegado de calle")
        other = make_organization(7004)
        self.client.post(reverse("core:directivas_create"), self.form(other, role=ROLE.DIRECTOR, role_detail="Sobrante"))
        self.assertEqual(OrganizationLeader.objects.get(organization=other).role_detail, "")

    def test_the_name_and_the_email_are_checked(self):
        bad_name = self.client.post(reverse("core:directivas_create"), self.form(name="Pedro <b>"))
        self.assertIn("name", bad_name.context["form"].errors)
        bad_email = self.client.post(reverse("core:directivas_create"), self.form(email="sin-arroba"))
        self.assertIn("email", bad_email.context["form"].errors)
        bad_rut = self.client.post(reverse("core:directivas_create"), self.form(rut="12345678-9"))
        self.assertIn("rut", bad_rut.context["form"].errors)

    def test_an_archived_president_frees_the_cargo_and_cannot_come_back_while_it_is_taken(self):
        old = make_leader(self.empty, ROLE.PRESIDENT, "12345678-5", "Presidente Antiguo")
        self.client.post(reverse("core:directivas_archive", args=[old.pk]))
        old.refresh_from_db()
        self.assertIsNotNone(old.deleted_at)
        response = self.client.post(reverse("core:directivas_create"), self.form(role=ROLE.PRESIDENT))
        self.assertEqual(response.status_code, 302)
        self.client.post(reverse("core:directivas_restore", args=[old.pk]))
        old.refresh_from_db()
        self.assertIsNotNone(old.deleted_at)

    def test_a_member_is_not_a_beneficiary(self):
        before = Beneficiary.objects.count()
        self.client.post(reverse("core:directivas_create"), self.form(role=ROLE.PRESIDENT))
        self.assertEqual(Beneficiary.objects.count(), before)
        self.assertFalse(Beneficiary.objects.filter(rut="17283946-0").exists())

    def test_the_list_filters_by_cargo_and_organization(self):
        response = self.client.get(reverse("core:directivas_list"), {"role": ROLE.TREASURER})
        names = [row.cells[0].text for row in response.context["rows"]]
        self.assertIn("Marta Silva Araya", names)
        self.assertNotIn("Gloria Tapia Soto", names)

    def test_the_form_shows_the_detail_only_for_otro_cargo(self):
        response = self.client.get(reverse("core:directivas_create"))
        self.assertContains(response, 'data-show-if="id_role:other"')

    def test_a_user_without_permission_gets_403_and_one_who_can_only_view_cannot_create(self):
        consulta = self.login_as("consulta1")
        self.assertEqual(self.client.get(reverse("core:directivas_list")).status_code, 403)
        self.give_perm(consulta, "organization.view_organizationleader")
        consulta = type(consulta).objects.get(pk=consulta.pk)
        self.client.force_login(consulta)
        self.assertEqual(self.client.get(reverse("core:directivas_list")).status_code, 200)
        self.assertEqual(self.client.get(reverse("core:directivas_create")).status_code, 403)

    def test_the_roles_screen_lists_the_module(self):
        response = self.client.get(reverse("core:roles_create"))
        self.assertContains(response, "Directivas de organizaciones")


class SolicitanteTests(PortalTestCase):
    """En la atención se elige si pide una persona natural o una organización y, en ese caso, quién de su directiva."""

    def setUp(self):
        self.login_as("matias.cavieres")
        self.organization = CommunityOrganization.objects.get(registry_number=1001)
        self.president = self.organization.leaders.get(role=ROLE.PRESIDENT)
        self.treasurer = self.organization.leaders.get(role=ROLE.TREASURER)
        self.other = make_organization(7100, "Otra Junta")
        self.stranger = make_leader(self.other, ROLE.PRESIDENT, "15975328-K", "Persona de Otra Junta")

    def register(self, **changes):
        return self.client.post(reverse("core:actividades_create"), self.intake_data(**changes))

    def newest(self):
        return Activity.objects.order_by("-pk").first()

    def org_data(self, **changes):
        data = {
            "requester_kind": "organization",
            "requester": "",
            "organization": self.organization.pk,
            "organization_leader": self.president.pk,
            "phone": "+56 9 1234 5678",
        }
        data.update(changes)
        return data

    def test_without_the_kind_the_attention_is_a_natural_person_as_before(self):
        response = self.register(requester="11.111.111-1")
        self.assertEqual(response.status_code, 302)
        activity = self.newest()
        self.assertEqual(activity.requester_kind, Activity.RequesterKind.NATURAL)
        self.assertEqual(activity.beneficiary.rut, "11111111-1")
        self.assertIsNone(activity.organization_leader)

    def test_an_organization_comes_with_the_person_of_its_directiva(self):
        response = self.register(**self.org_data())
        self.assertEqual(response.status_code, 302)
        activity = self.newest()
        self.assertEqual(activity.requester_kind, Activity.RequesterKind.ORGANIZATION)
        self.assertEqual(activity.organization, self.organization)
        self.assertEqual(activity.organization_leader, self.president)
        self.assertEqual(activity.contact_name, self.president.name)
        self.assertIsNone(activity.beneficiary)

    def test_without_naming_who_comes_the_contact_is_the_organization(self):
        self.register(**self.org_data(organization_leader=""))
        activity = self.newest()
        self.assertIsNone(activity.organization_leader)
        self.assertEqual(activity.contact_name, self.organization.name[:100])

    def test_an_organization_attention_does_not_ask_for_the_rut_or_the_name(self):
        before = Activity.objects.count()
        response = self.register(**self.org_data(requester=""))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Activity.objects.count(), before + 1)

    def test_an_organization_attention_without_organization_is_refused(self):
        before = Activity.objects.count()
        response = self.register(**self.org_data(organization="", organization_leader=""))
        self.assertEqual(response.status_code, 200)
        self.assertIn("organization", response.context["form"].errors)
        self.assertEqual(Activity.objects.count(), before)

    def test_a_person_of_another_organization_is_refused(self):
        before = Activity.objects.count()
        response = self.register(**self.org_data(organization_leader=self.stranger.pk))
        self.assertEqual(response.status_code, 200)
        self.assertIn("organization_leader", response.context["form"].errors)
        self.assertEqual(Activity.objects.count(), before)

    def test_an_archived_member_is_not_offered(self):
        self.treasurer.deleted_at = self.treasurer.created_at
        self.treasurer.save()
        response = self.client.get(reverse("core:actividades_create"))
        self.assertNotContains(response, self.treasurer.name)
        self.assertContains(response, self.president.name)

    def test_a_natural_person_keeps_the_organization_but_drops_the_leader(self):
        response = self.register(
            requester="11.111.111-1", organization=self.organization.pk, organization_leader=self.president.pk
        )
        self.assertEqual(response.status_code, 302)
        activity = self.newest()
        self.assertIsNone(activity.organization_leader)
        self.assertEqual(activity.organization, self.organization)
        self.assertEqual(activity.beneficiary.rut, "11111111-1")

    def test_a_natural_person_still_needs_the_rut_or_the_name(self):
        before = Activity.objects.count()
        response = self.register(requester="")
        self.assertEqual(response.status_code, 200)
        self.assertIn("requester", response.context["form"].errors)
        self.assertEqual(Activity.objects.count(), before)

    def test_an_unknown_rut_is_still_refused_for_a_natural_person(self):
        response = self.register(requester="9.999.999-3")
        self.assertEqual(response.status_code, 200)
        self.assertIn("requester", response.context["form"].errors)

    def test_the_form_shows_each_group_of_fields_only_for_its_kind(self):
        response = self.client.get(reverse("core:actividades_create"))
        self.assertContains(response, 'data-show-if="id_requester_kind:natural"')
        self.assertContains(response, 'data-show-if="id_requester_kind:organization"')
        self.assertContains(response, 'data-required-if="id_requester_kind:organization"')
        self.assertContains(response, 'data-depends-on="id_organization"')
        self.assertContains(response, f'data-parent="{self.organization.pk}"')
        self.assertContains(response, f"{self.president.name} · Presidente")

    def test_the_script_knows_how_to_show_a_field_by_the_selected_kind(self):
        from pathlib import Path

        text = Path("core/static/core/js/widgets.js").read_text(encoding="utf-8")
        self.assertIn("setUpShowIf", text)
        self.assertIn("dataset.showIf", text)
        self.assertIn("setUpRequiredIf", text)

    def test_a_dependent_list_is_prepared_only_once_even_if_the_script_loads_twice(self):
        from pathlib import Path

        text = Path("core/static/core/js/widgets.js").read_text(encoding="utf-8")
        self.assertIn("dataset.dependentReady", text)

    def test_the_attention_page_names_the_kind_and_the_person(self):
        self.register(**self.org_data(organization_leader=self.treasurer.pk))
        activity = self.newest()
        response = self.client.get(reverse("core:actividades_detail", args=[activity.pk]))
        self.assertContains(response, "Organización")
        self.assertContains(response, self.treasurer.name)

    def test_the_list_filters_by_kind(self):
        self.register(**self.org_data())
        organization_one = self.newest()
        response = self.client.get(reverse("core:atencion"), {"requester_kind": "organization"})
        self.assertEqual({row.obj.requester_kind for row in response.context["rows"]}, {"organization"})
        self.assertIn(organization_one.pk, [row.obj.pk for row in response.context["rows"]])

    def test_an_organization_attention_scores_only_with_the_phone(self):
        self.register(**self.org_data(phone=""))
        self.assertFalse(self.newest().counts_for_score)
        self.register(**self.org_data())
        self.assertTrue(self.newest().counts_for_score)

    def test_editing_can_move_an_attention_to_an_organization(self):
        self.register(requester="11.111.111-1")
        activity = self.newest()
        data = self.activity_form_data(
            activity,
            requester_kind="organization",
            organization=self.organization.pk,
            organization_leader=self.treasurer.pk,
            beneficiary="",
        )
        response = self.client.post(reverse("core:actividades_update", args=[activity.pk]), data)
        self.assertEqual(response.status_code, 302)
        activity.refresh_from_db()
        self.assertEqual(activity.requester_kind, Activity.RequesterKind.ORGANIZATION)
        self.assertEqual(activity.organization_leader, self.treasurer)
        self.assertEqual(activity.contact_name, self.treasurer.name)
        self.assertIsNone(activity.beneficiary)

    def test_editing_back_to_a_natural_person_drops_the_leader(self):
        self.register(**self.org_data())
        activity = self.newest()
        person = Beneficiary.objects.get(rut="11111111-1")
        data = self.activity_form_data(
            activity, requester_kind="natural", beneficiary=person.pk, contact_name=person.name, organization_leader=""
        )
        response = self.client.post(reverse("core:actividades_update", args=[activity.pk]), data)
        self.assertEqual(response.status_code, 302)
        activity.refresh_from_db()
        self.assertEqual(activity.requester_kind, Activity.RequesterKind.NATURAL)
        self.assertIsNone(activity.organization_leader)
        self.assertEqual(activity.beneficiary, person)

    def test_editing_a_natural_attention_keeps_its_optional_organization(self):
        self.register(requester="11.111.111-1")
        activity = self.newest()
        data = self.activity_form_data(
            activity, request_description="Texto corregido.", organization=self.organization.pk
        )
        self.client.post(reverse("core:actividades_update", args=[activity.pk]), data)
        activity.refresh_from_db()
        self.assertEqual(activity.organization, self.organization)
        self.assertEqual(activity.requester_kind, Activity.RequesterKind.NATURAL)

    def test_the_model_refuses_a_leader_that_is_not_of_the_organization(self):
        from django.core.exceptions import ValidationError

        activity = Activity.objects.first()
        activity.requester_kind = "organization"
        activity.organization = self.organization
        activity.organization_leader = self.stranger
        with self.assertRaises(ValidationError) as caught:
            activity.check_requester_kind()
        self.assertIn("organization_leader", caught.exception.message_dict)

    def test_the_old_attentions_of_an_organization_without_person_become_organization(self):
        import importlib

        migration = importlib.import_module("operations.migrations.0007_tipo_de_solicitante_v39")
        activity = Activity.objects.filter(beneficiary__isnull=False).first()
        Activity.objects.filter(pk=activity.pk).update(beneficiary=None, organization=self.organization)
        from django.apps import apps

        migration.organizaciones_como_solicitante(apps, None)
        activity.refresh_from_db()
        self.assertEqual(activity.requester_kind, Activity.RequesterKind.ORGANIZATION)
