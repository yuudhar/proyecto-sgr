"""Versión 52: eventos de cada organización (qué harán, cuándo y quién los lidera) y su organigrama."""
from datetime import date, timedelta

from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from core.testing import PortalTestCase
from organization import chart
from organization.models import CommunityOrganization, OrganizationEvent, OrganizationLeader

ROLE = OrganizationLeader.Role
STATUS = OrganizationEvent.Status


class EventBase(PortalTestCase):

    def setUp(self):
        self.login_as("admin")
        OrganizationEvent.objects.all().delete()
        self.organization = CommunityOrganization.objects.get(registry_number=1001)
        self.president = self.organization.leaders.get(role=ROLE.PRESIDENT)
        self.treasurer = self.organization.leaders.get(role=ROLE.TREASURER)
        self.other = CommunityOrganization.objects.create(name="Otra Organización de Prueba", registry_number=7790)
        self.stranger = OrganizationLeader.objects.get_or_create(
            organization=self.other, role=ROLE.PRESIDENT, defaults={"rut": "12345678-5", "name": "Presidente de Otra"}
        )[0]

    def make(self, **changes):
        values = {
            "organization": self.organization,
            "title": "Asamblea general",
            "description": "Rendir cuenta del año en la sede.",
            "start_date": date(2031, 5, 10),
            "end_date": date(2031, 5, 10),
            "responsible": self.president,
        }
        values.update(changes)
        return OrganizationEvent.objects.create(**values)

    def form(self, **changes):
        data = {
            "organization": self.organization.pk,
            "title": "Operativo de limpieza",
            "description": "Limpieza de pasajes con los vecinos.",
            "start_date": "2031-06-01",
            "end_date": "2031-06-02",
            "responsible": self.president.pk,
            "status": STATUS.PLANNED,
        }
        data.update(changes)
        return data


class EventRulesTests(EventBase):

    def test_an_event_keeps_what_they_will_do_when_and_who_leads_it(self):
        event = self.make()
        self.assertEqual(event.responsible, self.president)
        self.assertEqual(event.status, STATUS.PLANNED)
        self.assertIn("Asamblea general", str(event))

    def test_the_end_cannot_be_before_the_start(self):
        event = OrganizationEvent(
            organization=self.organization, title="Al revés", start_date=date(2031, 5, 10), end_date=date(2031, 5, 9)
        )
        with self.assertRaises(ValidationError) as caught:
            event.full_clean()
        self.assertIn("end_date", caught.exception.message_dict)

    def test_the_responsible_must_belong_to_the_directiva_of_the_organization(self):
        stranger = self.stranger
        event = OrganizationEvent(
            organization=self.organization, title="Mal responsable", start_date=date(2031, 5, 1),
            end_date=date(2031, 5, 1), responsible=stranger,
        )
        with self.assertRaises(ValidationError) as caught:
            event.full_clean()
        self.assertIn("responsible", caught.exception.message_dict)

    def test_the_event_must_fall_inside_the_activity_dates_of_the_organization(self):
        CommunityOrganization.objects.filter(pk=self.organization.pk).update(
            start_date=date(2031, 3, 1), end_date=date(2031, 9, 30)
        )
        self.organization.refresh_from_db()
        early = OrganizationEvent(organization=self.organization, title="Antes", start_date=date(2031, 2, 1), end_date=date(2031, 2, 2))
        late = OrganizationEvent(organization=self.organization, title="Después", start_date=date(2031, 9, 29), end_date=date(2031, 10, 2))
        fine = OrganizationEvent(organization=self.organization, title="Dentro", start_date=date(2031, 4, 1), end_date=date(2031, 4, 2))
        with self.assertRaises(ValidationError) as caught:
            early.full_clean()
        self.assertIn("start_date", caught.exception.message_dict)
        with self.assertRaises(ValidationError) as caught:
            late.full_clean()
        self.assertIn("end_date", caught.exception.message_dict)
        fine.full_clean()

    def test_the_responsible_is_optional(self):
        self.make(responsible=None)
        self.assertEqual(OrganizationEvent.objects.filter(responsible__isnull=True).count(), 1)


class EventScreenTests(EventBase):

    def test_the_menu_and_the_list_open(self):
        self.make()
        response = self.client.get(reverse("core:eventos_de_organizaciones_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Asamblea general")
        self.assertContains(response, "Eventos de organizaciones")

    def test_an_event_is_created_from_the_form(self):
        response = self.client.post(reverse("core:eventos_de_organizaciones_create"), self.form())
        self.assertEqual(response.status_code, 302)
        event = OrganizationEvent.objects.get(title="Operativo de limpieza")
        self.assertEqual(event.organization, self.organization)
        self.assertEqual(event.responsible, self.president)
        self.assertEqual(event.end_date, date(2031, 6, 2))

    def test_the_form_refuses_an_end_before_the_start(self):
        before = OrganizationEvent.objects.count()
        response = self.client.post(reverse("core:eventos_de_organizaciones_create"), self.form(end_date="2031-05-01"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("end_date", response.context["form"].errors)
        self.assertEqual(OrganizationEvent.objects.count(), before)

    def test_the_form_refuses_a_responsible_from_another_organization(self):
        stranger = self.stranger
        before = OrganizationEvent.objects.count()
        response = self.client.post(reverse("core:eventos_de_organizaciones_create"), self.form(responsible=stranger.pk))
        self.assertEqual(response.status_code, 200)
        self.assertIn("responsible", response.context["form"].errors)
        self.assertEqual(OrganizationEvent.objects.count(), before)

    def test_the_form_starts_with_the_organization_it_comes_from(self):
        response = self.client.get(reverse("core:eventos_de_organizaciones_create"), {"organization": self.organization.pk})
        self.assertEqual(str(response.context["form"].initial["organization"]), str(self.organization.pk))

    def test_the_status_can_be_changed_to_done_or_suspended(self):
        event = self.make()
        for status in (STATUS.DONE, STATUS.SUSPENDED):
            response = self.client.post(
                reverse("core:eventos_de_organizaciones_update", args=[event.pk]), self.form(title=event.title, status=status)
            )
            self.assertEqual(response.status_code, 302)
            event.refresh_from_db()
            self.assertEqual(event.status, status)

    def test_the_list_can_be_filtered_by_organization_and_searched_by_detail(self):
        self.make()
        self.make(organization=self.other, title="Bingo de otra", description="Fondos para el techo", responsible=None)
        url = reverse("core:eventos_de_organizaciones_list")
        only = self.client.get(url, {"organization": self.organization.pk})
        self.assertContains(only, "Asamblea general")
        self.assertNotContains(only, "Bingo de otra")
        found = self.client.get(url, {"q": "techo"})
        self.assertContains(found, "Bingo de otra")

    def test_an_event_is_archived_and_restored(self):
        event = self.make()
        self.client.post(reverse("core:eventos_de_organizaciones_archive", args=[event.pk]))
        event.refresh_from_db()
        self.assertIsNotNone(event.deleted_at)
        self.client.post(reverse("core:eventos_de_organizaciones_restore", args=[event.pk]))
        event.refresh_from_db()
        self.assertIsNone(event.deleted_at)

    def test_a_reader_sees_the_events_but_cannot_add_them(self):
        self.make()
        reader = self.make_user("lector_eventos", groups=("Consulta",))
        for label in ("organization.view_organizationevent", "organization.view_communityorganization"):
            self.give_perm(reader, label)
        self.client.force_login(reader)
        self.assertEqual(self.client.get(reverse("core:eventos_de_organizaciones_list")).status_code, 200)
        self.assertEqual(self.client.get(reverse("core:eventos_de_organizaciones_create")).status_code, 403)
        page = self.client.get(reverse("core:organizaciones_detail", args=[self.organization.pk]))
        self.assertContains(page, "Calendario de actividades")
        self.assertNotContains(page, "Agregar evento")

    def test_who_cannot_see_events_does_not_get_them_in_the_page_of_the_organization(self):
        self.make(title="Evento reservado")
        user = self.make_user("solo_organizaciones", groups=("Consulta",))
        self.give_perm(user, "organization.view_communityorganization")
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse("core:eventos_de_organizaciones_list")).status_code, 403)
        page = self.client.get(reverse("core:organizaciones_detail", args=[self.organization.pk]))
        self.assertEqual(page.status_code, 200)
        self.assertNotContains(page, "Evento reservado")
        self.assertNotContains(page, "Calendario de actividades")


class OrgChartTests(EventBase):

    def test_the_chart_places_each_role_and_the_rest_of_the_directiva(self):
        built = chart.build(self.organization)
        self.assertEqual(built["president"]["leader"], self.president)
        self.assertEqual(built["treasurer"]["leader"], self.treasurer)
        others = {node["leader"].pk for node in built["others"]}
        expected = set(
            self.organization.leaders.exclude(role__in=(ROLE.PRESIDENT, ROLE.SECRETARY, ROLE.TREASURER)).values_list("pk", flat=True)
        )
        self.assertEqual(others, expected)

    def test_a_missing_role_is_shown_empty(self):
        empty = CommunityOrganization.objects.create(name="Solo Presidente", registry_number=7791)
        OrganizationLeader.objects.create(organization=empty, role=ROLE.PRESIDENT, rut="12345678-5", name="Única Presidenta")
        built = chart.build(empty)
        self.assertIsNone(built["secretary"])
        page = self.client.get(reverse("core:organizaciones_detail", args=[empty.pk]))
        self.assertContains(page, "Única Presidenta")
        self.assertContains(page, "Sin secretario")
        self.assertContains(page, "Sin tesorero")

    def test_an_organization_without_directiva_says_so(self):
        empty = CommunityOrganization.objects.create(name="Sin Nadie", registry_number=7792)
        page = self.client.get(reverse("core:organizaciones_detail", args=[empty.pk]))
        self.assertContains(page, "todavía no tiene directiva")

    def test_each_person_shows_the_next_activity_they_lead(self):
        today = timezone.localdate()
        self.make(title="Ya pasó", start_date=today - timedelta(days=30), end_date=today - timedelta(days=29), status=STATUS.DONE)
        self.make(title="Cuota de socios", start_date=today + timedelta(days=20), end_date=today + timedelta(days=20), responsible=self.treasurer)
        self.make(title="Reunión próxima", start_date=today + timedelta(days=5), end_date=today + timedelta(days=5))
        built = chart.build(self.organization)
        self.assertEqual(built["president"]["next"].title, "Reunión próxima")
        self.assertEqual(built["treasurer"]["next"].title, "Cuota de socios")
        self.assertEqual(built["president"]["events"], 2)

    def test_a_suspended_event_is_not_a_next_activity(self):
        today = timezone.localdate()
        self.make(title="Cancelada", start_date=today + timedelta(days=3), end_date=today + timedelta(days=3), status=STATUS.SUSPENDED)
        self.assertIsNone(chart.build(self.organization)["president"]["next"])

    def test_the_page_shows_the_chart_and_the_calendar_with_what_they_will_do(self):
        today = timezone.localdate()
        self.make(
            title="Taller de costura", description="Taller de costura básica para las socias.",
            start_date=today + timedelta(days=7), end_date=today + timedelta(days=9),
        )
        page = self.client.get(reverse("core:organizaciones_detail", args=[self.organization.pk]))
        self.assertContains(page, "Organigrama")
        self.assertContains(page, self.president.name)
        self.assertContains(page, "Calendario de actividades")
        self.assertContains(page, "Taller de costura")
        self.assertContains(page, "Taller de costura básica para las socias.")
        self.assertContains(page, "Agregar evento")
        self.assertContains(page, "Planificado")

    def test_the_summary_counts_by_state_and_unassigned_events(self):
        self.make(status=STATUS.DONE)
        self.make(title="Sin responsable", responsible=None)
        self.make(title="Suspendido", status=STATUS.SUSPENDED)
        built = chart.build(self.organization)
        self.assertEqual(built["counts"], {"planned": 1, "done": 1, "suspended": 1})
        self.assertEqual(built["unassigned"], 1)

    def test_archived_events_and_leaders_are_left_out(self):
        gone = self.make(title="Archivado")
        OrganizationEvent.objects.filter(pk=gone.pk).update(deleted_at=timezone.now())
        self.assertEqual(chart.build(self.organization)["events"], [])


class SampleEventsCommandTests(PortalTestCase):
    """cargar_eventos_de_organizaciones deja eventos coherentes en una base que ya tenía las organizaciones."""

    def setUp(self):
        from io import StringIO

        from django.core.management import call_command

        self.run_command = lambda: call_command("cargar_eventos_de_organizaciones", stdout=StringIO())
        OrganizationEvent.objects.all().delete()
        self.organization = CommunityOrganization.objects.create(name="JUNTA DE VECINOS VILLA PRUEBA 1", registry_number=7001)
        for role, rut, name in (
            (ROLE.PRESIDENT, "11111111-1", "Presidenta Prueba"),
            (ROLE.TREASURER, "22222222-2", "Tesorero Prueba"),
        ):
            OrganizationLeader.objects.create(organization=self.organization, role=role, rut=rut, name=name)

    def test_it_gives_the_organization_dates_a_description_and_events_of_its_directiva(self):
        self.run_command()
        self.organization.refresh_from_db()
        self.assertIsNotNone(self.organization.start_date)
        self.assertTrue(self.organization.description)
        events = list(OrganizationEvent.objects.filter(organization=self.organization))
        self.assertEqual(len(events), 3)
        for event in events:
            self.assertGreaterEqual(event.start_date, self.organization.start_date)
            self.assertLessEqual(event.end_date, self.organization.end_date or event.end_date)
            self.assertGreaterEqual(event.end_date, event.start_date)
            self.assertEqual(event.responsible.organization_id, self.organization.pk)

    def test_the_treasurer_leads_the_fundraising_events(self):
        self.run_command()
        for event in OrganizationEvent.objects.filter(organization=self.organization):
            if event.title in ("Bingo para la sede",):
                self.assertEqual(event.responsible.role, ROLE.TREASURER)

    def test_running_it_again_changes_nothing(self):
        self.run_command()
        first = list(OrganizationEvent.objects.values_list("pk", "title", "start_date"))
        self.run_command()
        self.assertEqual(list(OrganizationEvent.objects.values_list("pk", "title", "start_date")), first)

    def test_it_leaves_the_organizations_outside_the_review_load_alone(self):
        real = CommunityOrganization.objects.create(name="Junta Real del Sector", registry_number=3)
        self.run_command()
        self.assertFalse(OrganizationEvent.objects.filter(organization=real).exists())
        real.refresh_from_db()
        self.assertIsNone(real.start_date)
