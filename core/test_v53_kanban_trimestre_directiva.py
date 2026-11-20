"""Versión 53: trimestre de la persona en la barra, «Felicitaciones y reclamos», vista Lista/Kanban y directivas
vinculadas a beneficiarios por el RUT."""
from datetime import date, timedelta
from unittest import mock

from django.urls import reverse
from django.utils import timezone

from core import entry_rules
from core.crud import registry
from core.rules import rut_check_digit
from core.testing import PortalTestCase
from operations.models import Commitment
from organization.models import Beneficiary, CommunityOrganization, OrganizationEvent, OrganizationLeader
from planning.models import Period

ROLE = OrganizationLeader.Role


def rut(body):
    return f"{body}-{rut_check_digit(str(body))}"


def quarter_of(day):
    first_month = 3 * ((day.month - 1) // 3) + 1
    start = date(day.year, first_month, 1)
    end = (date(day.year + 1, 1, 1) if first_month == 10 else date(day.year, first_month + 3, 1)) - timedelta(days=1)
    return start, end


class QuarterInTopbarTests(PortalTestCase):
    """La barra de arriba dice en qué trimestre está hoy la persona."""

    def setUp(self):
        self.today = entry_rules.portal_today()
        self.start, self.end = quarter_of(self.today)
        self.number = (self.start.month - 1) // 3 + 1

    def quarter_text(self, username):
        self.login_as(username)
        return self.client.get(reverse("core:dashboard")).context["me_quarter"]

    def test_it_shows_the_general_quarter_that_contains_today(self):
        Period.objects.create(start_date=self.start, end_date=self.end, computable_days=60, status=Period.Status.ACTIVE)
        quarter = self.quarter_text("matias.cavieres")
        self.assertIn(f"trimestre {self.start.year}", quarter["label"])
        self.assertTrue(quarter["label"].startswith({1: "1.er", 2: "2.º", 3: "3.er", 4: "4.º"}[self.number]))
        self.assertEqual(quarter["range"], f"{self.start:%d/%m} al {self.end:%d/%m/%Y}")
        self.assertIn("general", quarter["title"])
        html = self.client.get(reverse("core:dashboard")).content.decode()
        self.assertIn("topbar-quarter", html)

    def test_the_quarter_of_the_users_delegation_wins_over_the_general_one(self):
        Period.objects.create(start_date=self.start, end_date=self.end, computable_days=60, status=Period.Status.ACTIVE)
        Period.objects.create(
            start_date=self.start, end_date=self.end, computable_days=50, status=Period.Status.ACTIVE, delegation=self.north
        )
        self.assertIn("Delegación Norte", self.quarter_text("matias.cavieres")["title"])
        self.assertIn("general", self.quarter_text("matias.quiroz")["title"])

    def test_a_yearly_period_is_shown_as_a_period(self):
        self.assertEqual(self.quarter_text("matias.cavieres")["label"], f"Período {self.today.year}")

    def test_without_a_period_for_today_it_says_so(self):
        Period.objects.update(deleted_at=timezone.now())
        quarter = self.quarter_text("matias.cavieres")
        self.assertEqual(quarter["label"], "Sin trimestre vigente")
        self.assertEqual(quarter["range"], "")

    def test_clients_do_not_see_it(self):
        self.login_as("cliente1")
        response = self.client.get(reverse("core:portal_home"))
        self.assertNotIn("me_quarter", response.context)
        self.assertNotIn("topbar-quarter", response.content.decode())


class FeedbackRenameTests(PortalTestCase):
    """«Cartas» pasa a llamarse «Felicitaciones y reclamos» en el menú, el listado, el formulario y los permisos."""

    def test_the_screen_menu_and_button_use_the_new_name(self):
        self.login_as("admin")
        response = self.client.get(reverse("core:cartas_list"))
        html = response.content.decode()
        self.assertContains(response, "Felicitaciones y reclamos")
        self.assertContains(response, "Nueva felicitación o reclamo")
        self.assertNotIn(">Cartas<", html)
        self.assertIn("Felicitaciones y reclamos", self.menu_labels(response))

    def test_the_form_and_the_permission_matrix_use_the_new_name(self):
        from core.roles import MODULE_LABELS

        self.login_as("admin")
        self.assertContains(self.client.get(reverse("core:cartas_create")), "Nueva felicitación o reclamo")
        self.assertEqual(MODULE_LABELS["planning.feedback"], "Felicitaciones y reclamos")


class ViewSwitchTests(PortalTestCase):
    """Los listados con tablero se ven como lista o como Kanban, con un botón que recuerda la elección."""

    BOARDS = ("atencion", "agenda", "compromisos", "tubo-de-cartas", "cartas", "cambios-trimestre", "evidencias",
              "validaciones", "indicadores", "periodos", "eventos-de-organizaciones")

    def setUp(self):
        self.login_as("admin")

    def url(self, slug):
        return reverse("core:atencion") if slug == "atencion" else reverse(f"core:{slug.replace('-', '_')}_list")

    def test_every_screen_with_states_has_the_switch_and_both_views_work(self):
        for slug in self.BOARDS:
            with self.subTest(slug=slug):
                listed = self.client.get(self.url(slug) + "?vista=lista")
                board = self.client.get(self.url(slug) + "?vista=kanban")
                self.assertEqual((listed.status_code, board.status_code), (200, 200))
                self.assertTrue(listed.context["can_switch_view"])
                self.assertNotIn("board", listed.context)
                self.assertIn("board", board.context)
                self.assertContains(board, "view-switch")

    def test_the_boards_that_existed_open_as_kanban_and_the_new_ones_as_a_list(self):
        for slug, view in (("compromisos", "kanban"), ("cartas", "kanban"), ("agenda", "lista"), ("evidencias", "lista")):
            with self.subTest(slug=slug):
                self.assertEqual(self.client.get(self.url(slug)).context["view"], view)

    def test_the_choice_is_remembered_and_kept_when_searching(self):
        self.client.get(self.url("agenda") + "?vista=kanban")
        self.assertEqual(self.client.get(self.url("agenda"), follow=True).context["view"], "kanban")
        self.assertEqual(self.client.get(self.url("agenda") + "?q=a&vista=kanban").context["view"], "kanban")
        self.assertEqual(self.client.get(self.url("compromisos"), follow=True).context["view"], "kanban")
        self.client.get(self.url("agenda") + "?vista=lista")
        self.assertEqual(self.client.get(self.url("agenda"), follow=True).context["view"], "lista")

    def test_an_unknown_view_is_ignored_and_screens_without_states_have_no_switch(self):
        self.assertEqual(self.client.get(self.url("agenda") + "?vista=otra").context["view"], "lista")
        response = self.client.get(reverse("core:beneficiarios_list"))
        self.assertFalse(response.context["can_switch_view"])
        self.assertNotContains(response, "view-switch")

    def test_each_column_counts_the_whole_filtered_set_not_only_the_page(self):
        crud = registry.get("compromisos")
        total = Commitment.objects.filter(deleted_at__isnull=True, physical=True).count()
        self.assertGreater(total, 1)
        with mock.patch.object(crud.canvas, "page_size", 1):
            board = self.client.get(self.url("compromisos") + "?vista=kanban").context["board"]
        self.assertEqual(sum(column["total"] for column in board["columns"]), total)
        self.assertEqual(sum(len(column["cards"]) for column in board["columns"]), 1)
        self.assertTrue(any(column["partial"] for column in board["columns"]))

    def test_events_move_from_the_board_and_a_reader_cannot_move_them(self):
        organization = CommunityOrganization.objects.get(registry_number=1001)
        event = OrganizationEvent.objects.create(
            organization=organization, title="Asamblea de prueba", start_date=date(2031, 3, 1), end_date=date(2031, 3, 1)
        )
        move = reverse("core:eventos_de_organizaciones_move", args=[event.pk])
        self.client.post(move, {"estado": OrganizationEvent.Status.DONE})
        event.refresh_from_db()
        self.assertEqual(event.status, OrganizationEvent.Status.DONE)
        self.login_as("consulta1")
        self.assertEqual(self.client.post(move, {"estado": OrganizationEvent.Status.SUSPENDED}).status_code, 403)
        event.refresh_from_db()
        self.assertEqual(event.status, OrganizationEvent.Status.DONE)

    def test_moving_a_commitment_of_the_agenda_keeps_its_status_history(self):
        from core.commitments import history_of

        commitment = Commitment.objects.filter(
            deleted_at__isnull=True, physical=False, status=Commitment.Status.SUBMITTED, delegation=self.north
        ).first() or Commitment.objects.filter(deleted_at__isnull=True, physical=False, status=Commitment.Status.SUBMITTED).first()
        self.assertIsNotNone(commitment)
        before = len(history_of(commitment))
        self.client.post(reverse("core:agenda_move", args=[commitment.pk]), {"estado": Commitment.Status.PENDING})
        commitment.refresh_from_db()
        self.assertEqual(commitment.status, Commitment.Status.PENDING)
        self.assertEqual(len(history_of(commitment)), before + 1)


class LeaderBeneficiaryTests(PortalTestCase):
    """La directiva se vincula al beneficiario con el mismo RUT y la pantalla completa sus datos al escribirlo."""

    def setUp(self):
        self.login_as("admin")
        self.organization = CommunityOrganization.objects.get(registry_number=1001)
        self.person = Beneficiary.objects.filter(deleted_at__isnull=True).order_by("pk").first()
        self.lookup = reverse("core:person_by_rut")

    def create(self, rut, name, **extra):
        data = {"organization": self.organization.pk, "role": ROLE.DIRECTOR, "rut": rut, "name": name, "email": "", **extra}
        self.client.post(reverse("core:directivas_create"), data)
        return OrganizationLeader.objects.filter(organization=self.organization, name=name).first()

    def dotted(self, rut):
        body, digit = rut.split("-")
        return f"{int(body):,}".replace(",", ".") + f"-{digit}"

    def test_the_lookup_returns_what_the_system_knows_of_a_rut(self):
        data = self.client.get(self.lookup, {"rut": self.dotted(self.person.rut)}).json()
        self.assertTrue(data["valid"])
        self.assertEqual(data["beneficiary"]["name"], self.person.name)
        self.assertEqual(data["name"], self.person.name)
        leader = OrganizationLeader.objects.exclude(email="").first() or OrganizationLeader.objects.first()
        leader.email = leader.email or "dirigente@prueba.cl"
        leader.save()
        data = self.client.get(self.lookup, {"rut": leader.rut}).json()
        self.assertEqual((data["name"], data["email"]), (leader.name, leader.email))
        self.assertTrue(any(leader.organization.name in text for text in data["memberships"]))
        self.assertFalse(self.client.get(self.lookup, {"rut": "12345678-0"}).json()["valid"])

    def test_only_who_can_see_directives_or_beneficiaries_may_ask(self):
        self.login_as("cliente1")
        self.assertEqual(self.client.get(self.lookup, {"rut": self.person.rut}).status_code, 403)

    def test_saving_links_the_beneficiary_with_the_same_rut(self):
        leader = self.create(self.dotted(self.person.rut), "Integrante Vinculado")
        self.assertEqual(leader.beneficiary, self.person)
        detail = self.client.get(reverse("core:beneficiarios_detail", args=[self.person.pk]))
        self.assertContains(detail, "Directivas de organizaciones")
        self.assertContains(detail, self.organization.name)

    def test_a_new_person_is_registered_as_beneficiary_only_when_asked(self):
        before = Beneficiary.objects.count()
        alone = self.create(rut(21_345_679), "Persona Sin Registrar")
        self.assertIsNone(alone.beneficiary)
        self.assertEqual(Beneficiary.objects.count(), before)
        linked = self.create(rut(21_345_678), "Persona Registrada", create_beneficiary="on")
        self.assertIsNotNone(linked.beneficiary)
        self.assertEqual((linked.beneficiary.rut, linked.beneficiary.name), (rut(21_345_678), "Persona Registrada"))

    def test_changing_the_rut_moves_the_link(self):
        leader = self.create(self.person.rut, "Integrante Que Cambia")
        other = Beneficiary.objects.filter(deleted_at__isnull=True).exclude(pk=self.person.pk).order_by("pk").first()
        data = {"organization": self.organization.pk, "role": ROLE.DIRECTOR, "rut": other.rut, "name": leader.name, "email": ""}
        self.client.post(reverse("core:directivas_update", args=[leader.pk]), data)
        leader.refresh_from_db()
        self.assertEqual(leader.beneficiary, other)

    def test_the_form_asks_for_the_rut_first_and_offers_the_beneficiaries(self):
        html = self.client.get(reverse("core:directivas_create")).content.decode()
        self.assertLess(html.find('name="rut"'), html.find('name="name"'))
        self.assertIn("data-person-lookup", html)
        self.assertIn(f'value="{self.person.rut}"', html)
        self.assertIn('name="create_beneficiary"', html)

    def test_a_beneficiary_in_a_directive_cannot_be_deleted(self):
        self.create(self.person.rut, "Integrante Que Protege")
        self.client.post(reverse("core:beneficiarios_delete", args=[self.person.pk]))
        self.assertTrue(Beneficiary.objects.filter(pk=self.person.pk).exists())


class QuartersAheadTests(PortalTestCase):
    """Los trimestres se planifican hasta 10 años hacia adelante (PERIOD_YEARS_AHEAD), no solo el año siguiente."""

    def setUp(self):
        self.login_as("admin")
        self.last_year = timezone.localdate().year + 10

    def add_quarter(self, year):
        data = {
            "year": year, "quarter": 2, "delegations": [self.north.pk, self.south.pk],
            "collective_threshold": 80, "amber_threshold": 60, "status": Period.Status.PLANNED,
        }
        return self.client.post(reverse("core:quarter_add"), data)

    def new_period(self, start, end):
        data = {
            "start_date": start.isoformat(), "end_date": end.isoformat(), "computable_days": 60,
            "status": Period.Status.PLANNED, "collective_threshold": 80, "amber_threshold": 60, "weighted_cap": 120,
            "parameters_version": "v1", "compliment_value": 1, "complaint_value": 1, "compliment_limit": 3,
        }
        return self.client.post(reverse("core:periodos_create"), data)

    def test_a_quarter_up_to_ten_years_ahead_is_created_in_each_delegation(self):
        for year in (timezone.localdate().year + 2, self.last_year):
            with self.subTest(year=year):
                self.assertEqual(self.add_quarter(year).status_code, 302)
                self.assertEqual(Period.objects.filter(start_date=date(year, 4, 1)).count(), 2)

    def test_a_quarter_beyond_ten_years_is_refused_with_the_last_allowed_day(self):
        response = self.add_quarter(self.last_year + 1)
        self.assertEqual(response.status_code, 200)
        self.assertIn(f"31/12/{self.last_year}", " ".join(response.context["form"].errors["year"]))
        self.assertFalse(Period.objects.filter(start_date=date(self.last_year + 1, 4, 1)).exists())

    def test_the_period_form_has_the_same_limit_and_the_browser_knows_it(self):
        self.assertEqual(self.new_period(date(self.last_year, 7, 1), date(self.last_year, 9, 30)).status_code, 302)
        response = self.new_period(date(self.last_year, 10, 1), date(self.last_year + 1, 1, 15))
        self.assertEqual(response.status_code, 200)
        self.assertIn("end_date", response.context["form"].errors)
        self.assertContains(self.client.get(reverse("core:periodos_create")), f'max="{self.last_year}-12-31"')
        self.assertContains(self.client.get(reverse("core:quarter_add")), f'max="{self.last_year}"')
