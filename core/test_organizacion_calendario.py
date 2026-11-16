"""Versión 51: organizaciones con inicio y fin de actividades, descripción y su directiva a la vista."""
from datetime import date

from django.urls import reverse

from core.testing import PortalTestCase
from organization.models import CommunityOrganization, OrganizationLeader

ROLE = OrganizationLeader.Role


class OrganizationCalendarTests(PortalTestCase):

    def setUp(self):
        self.login_as("admin")
        self.organization = CommunityOrganization.objects.get(registry_number=1001)

    def form(self, **changes):
        data = {
            "name": "Club de Adulto Mayor Nuevo",
            "legal_address": "Los Aromos 123",
            "territory": self.organization.territory_id or "",
            "description": "Talleres de manualidades y gimnasia para adultos mayores del sector.",
            "start_date": "2026-03-01",
            "end_date": "2026-12-15",
            "active_members": 40,
            "constitution_date": "",
            "registry_number": 7777,
            "registration_date": "",
            "directory_number": "",
        }
        data.update(changes)
        return data

    def test_an_organization_is_created_with_its_dates_and_description(self):
        response = self.client.post(reverse("core:organizaciones_create"), self.form())
        self.assertEqual(response.status_code, 302)
        created = CommunityOrganization.objects.get(registry_number=7777)
        self.assertEqual(created.start_date, date(2026, 3, 1))
        self.assertEqual(created.end_date, date(2026, 12, 15))
        self.assertIn("gimnasia", created.description)

    def test_the_end_cannot_be_before_the_start(self):
        before = CommunityOrganization.objects.count()
        response = self.client.post(reverse("core:organizaciones_create"), self.form(end_date="2026-02-01"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("end_date", response.context["form"].errors)
        self.assertEqual(CommunityOrganization.objects.count(), before)

    def test_the_dates_and_the_description_are_optional(self):
        response = self.client.post(
            reverse("core:organizaciones_create"),
            self.form(start_date="", end_date="", description="", registry_number=7778),
        )
        self.assertEqual(response.status_code, 302)
        created = CommunityOrganization.objects.get(registry_number=7778)
        self.assertIsNone(created.start_date)
        self.assertIsNone(created.end_date)

    def test_the_model_also_refuses_an_end_before_the_start(self):
        from django.core.exceptions import ValidationError

        organization = CommunityOrganization(
            name="Fuera de Orden", registry_number=7779, start_date=date(2026, 5, 1), end_date=date(2026, 4, 1)
        )
        with self.assertRaises(ValidationError):
            organization.full_clean()

    def test_the_list_shows_the_president_and_the_treasurer(self):
        response = self.client.get(reverse("core:organizaciones_list"), {"q": self.organization.name})
        self.assertContains(response, "Presidente")
        self.assertContains(response, "Tesorero")
        president = self.organization.leaders.get(role=ROLE.PRESIDENT)
        treasurer = self.organization.leaders.get(role=ROLE.TREASURER)
        self.assertContains(response, f"{president.name} · {president.rut}")
        self.assertContains(response, f"{treasurer.name} · {treasurer.rut}")

    def test_the_page_shows_the_directiva_with_name_and_rut(self):
        response = self.client.get(reverse("core:organizaciones_detail", args=[self.organization.pk]))
        for role in (ROLE.PRESIDENT, ROLE.SECRETARY, ROLE.TREASURER):
            leader = self.organization.leaders.get(role=role)
            self.assertContains(response, f"{leader.name} · {leader.rut}")

    def test_an_organization_without_directiva_shows_a_dash(self):
        empty = CommunityOrganization.objects.create(name="Sin Directiva Visible", registry_number=7780)
        response = self.client.get(reverse("core:organizaciones_detail", args=[empty.pk]))
        self.assertContains(response, "Presidente")
        self.assertContains(response, "—")

    def test_an_archived_leader_is_not_shown_as_president(self):
        from django.utils import timezone

        empty = CommunityOrganization.objects.create(name="Con Presidente Archivado", registry_number=7781)
        leader = OrganizationLeader.objects.create(
            organization=empty, role=ROLE.PRESIDENT, rut="12345678-5", name="Ex Presidente"
        )
        OrganizationLeader.objects.filter(pk=leader.pk).update(deleted_at=timezone.now())
        response = self.client.get(reverse("core:organizaciones_detail", args=[empty.pk]))
        self.assertNotContains(response, "Ex Presidente")

    def test_the_description_can_be_searched(self):
        CommunityOrganization.objects.filter(pk=self.organization.pk).update(description="Cuenta con un taller de telar mapuche.")
        response = self.client.get(reverse("core:organizaciones_list"), {"q": "telar"})
        self.assertEqual([row.obj.pk for row in response.context["rows"]], [self.organization.pk])
