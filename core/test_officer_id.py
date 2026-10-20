from unittest import mock

from django.urls import reverse
from django.utils import timezone

from core.testing import PortalTestCase
from organization.models import Delegation, Officer, Position


class OfficerIdentifierTests(PortalTestCase):
    def new_officer(self, delegation, name="Persona Nueva"):
        return Officer.objects.create(
            name=name,
            status=Officer.Status.ACTIVE,
            delegation=delegation,
            position=Position.objects.first(),
        )

    def post_data(self, **changes):
        data = {
            "name": "Camila Rojas Vera",
            "status": Officer.Status.ACTIVE,
            "delegation": self.north.pk,
            "position": Position.objects.first().pk,
        }
        data.update(changes)
        return data

    def test_the_identifier_continues_the_block_of_the_delegation(self):
        north = self.new_officer(self.north, "Nuevo Norte")
        south = self.new_officer(self.south, "Nuevo Sur")
        self.assertEqual(north.institutional_id, "F-1007")
        self.assertEqual(south.institutional_id, "F-2006")
        self.assertEqual(self.new_officer(self.north, "Otro Norte").institutional_id, "F-1008")

    def test_archived_officers_keep_their_identifier_reserved(self):
        first = self.new_officer(self.north, "Primero")
        Officer.objects.filter(pk=first.pk).update(deleted_at=timezone.now())
        second = self.new_officer(self.north, "Segundo")
        self.assertNotEqual(first.institutional_id, second.institutional_id)
        self.assertEqual(second.institutional_id, "F-1008")

    def test_a_new_delegation_starts_its_own_block(self):
        other = Delegation.objects.create(name="Delegación Centro")
        self.assertEqual(self.new_officer(other, "Alguien Centro").institutional_id, "F-3001")

    def test_an_identifier_given_in_code_is_respected_and_not_changed_on_save(self):
        officer = Officer.objects.create(
            institutional_id="F-9500",
            name="Con Id Propio",
            status=Officer.Status.ACTIVE,
            delegation=self.north,
            position=Position.objects.first(),
        )
        officer.name = "Con Id Propio Editado"
        officer.save()
        officer.refresh_from_db()
        self.assertEqual(officer.institutional_id, "F-9500")

    def test_a_collision_is_retried_with_the_next_number(self):
        with mock.patch.object(Officer, "next_institutional_id", side_effect=["F-1001", "F-1100"]):
            officer = self.new_officer(self.north, "Con Choque")
        self.assertEqual(officer.institutional_id, "F-1100")

    def test_the_creation_form_has_no_identifier_field_and_the_edit_form_shows_it_read_only(self):
        self.login_as("admin")
        creation = self.client.get(reverse("core:funcionarios_create")).context["form"]
        self.assertNotIn("institutional_id", creation.fields)
        officer = self.officer("F-1002")
        edition = self.client.get(reverse("core:funcionarios_update", args=[officer.pk])).context["form"]
        field = edition.fields["institutional_id"]
        self.assertTrue(field.disabled)
        self.assertEqual(edition["institutional_id"].value(), "F-1002")

    def test_the_identifier_shows_in_the_list_and_can_be_searched(self):
        self.login_as("admin")
        response = self.client.get(reverse("core:funcionarios_list"), {"q": "F-1005"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["page"].paginator.count, 1)
        self.assertContains(response, "F-1005")
        self.assertContains(response, "Consulta Delegación Norte")

    def test_the_detail_shows_the_identifier(self):
        self.login_as("admin")
        officer = self.officer("F-1005")
        self.assertContains(self.client.get(reverse("core:funcionarios_detail", args=[officer.pk])), "F-1005")

    def test_creating_an_officer_from_the_form_assigns_the_identifier(self):
        self.login_as("admin")
        response = self.client.post(reverse("core:funcionarios_create"), self.post_data(institutional_id="F-7777"))
        self.assertEqual(response.status_code, 302)
        created = Officer.objects.get(name="Camila Rojas Vera")
        self.assertEqual(created.institutional_id, "F-1007")

    def test_editing_never_changes_the_identifier(self):
        self.login_as("admin")
        officer = self.officer("F-1002")
        response = self.client.post(
            reverse("core:funcionarios_update", args=[officer.pk]),
            self.post_data(name="Nombre Cambiado", institutional_id="F-7777", delegation=officer.delegation_id, position=officer.position_id),
        )
        self.assertEqual(response.status_code, 302)
        officer.refresh_from_db()
        self.assertEqual((officer.name, officer.institutional_id), ("Nombre Cambiado", "F-1002"))
