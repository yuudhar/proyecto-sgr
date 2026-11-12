"""Versión 38: Cartas (antes Felicitaciones y reclamos) y Compromisos (lo físico) en vista canvas."""
from datetime import timedelta

from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone

from core.commitments import history_of
from core.testing import PortalTestCase, portal_today
from operations.models import Activity, Commitment
from organization.models import Officer, Territory
from planning.models import Feedback


def make_commitment(delegation, officer, territory, requester="Vecina de Prueba", **changes):
    values = {
        "requester": requester,
        "territory": territory,
        "due_date": portal_today() + timedelta(days=10),
        "responsible_officer": officer,
        "delegation": delegation,
        "description": "Visita a terreno para revisar una luminaria.",
        "physical": True,
    }
    values.update(changes)
    return Commitment.objects.create(**values)


class BoardBase(PortalTestCase):

    def setUp(self):
        self.cavieres = Officer.objects.get(institutional_id="F-1001")
        self.south_officer = Officer.objects.get(institutional_id="F-2001")
        self.territory = Territory.objects.filter(delegation=self.north).first()
        self.south_territory = Territory.objects.filter(delegation=self.south).first()

    def columns(self, response):
        return {column["label"]: column["cards"] for column in response.context["board"]["columns"]}

    def kpis(self, response):
        return {kpi["label"]: kpi["value"] for kpi in response.context["board"]["kpis"]}


class CartasBoardTests(BoardBase):
    """Cartas: lo que antes era Felicitaciones y reclamos, ahora con otro nombre y en tarjetas."""

    def letter(self, kind, name, **changes):
        values = {
            "kind": kind,
            "date": portal_today(),
            "contact_name": name,
            "channel": Feedback.Channel.EMAIL,
            "officer": self.cavieres,
            "description": "Situación de prueba.",
            "support": "respaldos/demostracion/felicitacion-jefatura-norte.pdf",
            "registered_by": User.objects.get(username="admin"),
        }
        values.update(changes)
        return Feedback.objects.create(**values)

    def test_the_screen_is_called_cartas_and_the_old_address_is_gone(self):
        self.login_as("jefatura1")
        response = self.client.get(reverse("core:cartas_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<h1")
        self.assertContains(response, "Cartas")
        self.assertEqual(self.client.get("/felicitaciones-y-reclamos/").status_code, 404)

    def test_the_list_is_a_board_with_a_column_for_compliments_and_one_for_complaints(self):
        self.letter(Feedback.Kind.COMPLIMENT, "Rosa Núñez")
        self.letter(Feedback.Kind.COMPLAINT, "Vecino Molesto")
        self.login_as("jefatura1")
        columns = self.columns(self.client.get(reverse("core:cartas_list")))
        self.assertEqual(list(columns), ["Felicitación", "Reclamo"])
        self.assertIn("Rosa Núñez", [line[1] for card in columns["Felicitación"] for line in card["lines"]])
        self.assertIn("Vecino Molesto", [line[1] for card in columns["Reclamo"] for line in card["lines"]])

    def test_the_cards_show_the_effect_and_the_indicators_count_the_letters(self):
        self.letter(Feedback.Kind.COMPLIMENT, "Rosa Núñez")
        self.letter(Feedback.Kind.COMPLAINT, "Vecino Molesto")
        self.login_as("jefatura1")
        response = self.client.get(reverse("core:cartas_list"))
        self.assertContains(response, "canvas-card")
        total = Feedback.objects.filter(deleted_at__isnull=True, officer__delegation=self.north).count()
        kpis = self.kpis(response)
        self.assertEqual(kpis["Cartas"], total)
        self.assertEqual(kpis["Felicitaciones"] + kpis["Reclamos"], total)

    def test_the_board_respects_the_filters_and_the_own_delegation(self):
        self.letter(Feedback.Kind.COMPLAINT, "Vecina Sur", officer=self.south_officer)
        self.login_as("jefatura1")
        response = self.client.get(reverse("core:cartas_list"), {"kind": Feedback.Kind.COMPLAINT})
        self.assertNotContains(response, "Vecina Sur")
        self.assertEqual(self.kpis(response)["Felicitaciones"], 0)

    def test_the_codes_of_the_cards_start_with_car(self):
        self.letter(Feedback.Kind.COMPLIMENT, "Rosa Núñez")
        self.login_as("jefatura1")
        cards = self.columns(self.client.get(reverse("core:cartas_list")))["Felicitación"]
        self.assertTrue(all(card["code"].startswith("CAR") for card in cards))

    def test_the_roles_screen_lists_the_module_as_cartas(self):
        from core.roles import PERMISSION_MODULES

        labels = [label for _, rows in PERMISSION_MODULES for label, _ in rows]
        self.assertIn("Cartas", labels)
        self.assertNotIn("Felicitaciones y reclamos", labels)


class CompromisosBoardTests(BoardBase):
    """Compromisos: lo físico, en cuatro columnas por estado y con indicadores arriba."""

    def setUp(self):
        super().setUp()
        self.url = reverse("core:compromisos_list")

    def test_the_menu_has_compromisos_next_to_the_agenda(self):
        self.login_as("matias.cavieres")
        response = self.client.get(reverse("core:dashboard"))
        labels = self.menu_labels(response)
        self.assertIn("Compromisos", labels)
        self.assertIn("Agenda colectiva", labels)

    def test_the_list_is_a_board_with_the_four_states(self):
        make_commitment(self.north, self.cavieres, self.territory, "Ana Ingresada")
        self.login_as("matias.cavieres")
        columns = self.columns(self.client.get(self.url))
        self.assertEqual(list(columns), ["Ingresado", "Pendiente", "En proceso", "Realizado"])
        titles = [card["title"] for card in columns["Ingresado"]]
        self.assertIn("Visita a terreno para revisar una luminaria.", titles)

    def test_the_agenda_and_compromisos_do_not_share_their_lists(self):
        physical = make_commitment(self.north, self.cavieres, self.territory, "Solo Terreno")
        agenda = make_commitment(self.north, self.cavieres, self.territory, "Solo Agenda", physical=False)
        self.login_as("matias.cavieres")
        board = self.client.get(self.url)
        self.assertContains(board, "Solo Terreno")
        self.assertNotContains(board, "Solo Agenda")
        listing = self.client.get(reverse("core:agenda_list"), {"q": "Solo"})
        self.assertContains(listing, "Solo Agenda")
        self.assertNotContains(listing, "Solo Terreno")
        # La ficha abre desde cualquiera de las dos pantallas.
        self.assertEqual(self.client.get(reverse("core:agenda_detail", args=[physical.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("core:compromisos_detail", args=[agenda.pk])).status_code, 200)

    def test_the_indicators_count_by_state_and_give_the_resolution_rate(self):
        base = Commitment.objects.filter(physical=True, delegation=self.north, deleted_at__isnull=True)
        base.update(deleted_at=timezone.now())
        make_commitment(self.north, self.cavieres, self.territory, "A", status=Commitment.Status.FULFILLED)
        make_commitment(self.north, self.cavieres, self.territory, "B", status=Commitment.Status.FULFILLED)
        make_commitment(self.north, self.cavieres, self.territory, "C", status=Commitment.Status.IN_PROGRESS)
        make_commitment(self.north, self.cavieres, self.territory, "D", status=Commitment.Status.PENDING)
        self.login_as("matias.cavieres")
        response = self.client.get(self.url)
        kpis = self.kpis(response)
        self.assertEqual(kpis["Compromisos"], 4)
        self.assertEqual(kpis["Realizados"], 2)
        self.assertEqual(kpis["En proceso activo"], 1)
        self.assertEqual(kpis["Pendientes / alerta"], 1)
        self.assertContains(response, "Tasa de resolución: 50,0 %")

    def test_a_commitment_created_by_hand_in_compromisos_is_physical(self):
        self.login_as("matias.cavieres")
        response = self.client.post(
            reverse("core:compromisos_create"),
            {
                "requester": "Club de Adulto Mayor",
                "requester_type": Commitment.RequesterType.EXTERNAL,
                "request_date": portal_today().isoformat(),
                "description": "Visita para ver la sede.",
                "territory": self.territory.pk,
                "due_date": (portal_today() + timedelta(days=5)).isoformat(),
                "status": Commitment.Status.SUBMITTED,
                "responsible_officer": self.cavieres.pk,
                "delegation": self.north.pk,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Commitment.objects.get(requester="Club de Adulto Mayor").physical)


class CompromisosMoveTests(BoardBase):
    """Los botones de la tarjeta pasan el compromiso al estado siguiente y lo dejan en el historial."""

    def setUp(self):
        super().setUp()
        self.item = make_commitment(self.north, self.cavieres, self.territory, "Para Mover")

    def move(self, item, status):
        return self.client.post(reverse("core:compromisos_move", args=[item.pk]), {"estado": status})

    def test_a_card_moves_to_the_next_state_and_it_is_left_in_the_history(self):
        self.login_as("matias.cavieres")
        response = self.move(self.item, Commitment.Status.IN_PROGRESS)
        self.assertRedirects(response, reverse("core:compromisos_list"), fetch_redirect_response=False)
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, Commitment.Status.IN_PROGRESS)
        self.assertEqual(history_of(self.item)[-1]["new"], "En proceso")

    def test_a_move_the_rules_do_not_allow_is_refused_and_nothing_changes(self):
        self.item.status = Commitment.Status.FULFILLED
        self.item.save()
        self.login_as("matias.cavieres")
        self.move(self.item, Commitment.Status.PENDING)
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, Commitment.Status.FULFILLED)

    def test_a_made_up_state_is_refused(self):
        self.login_as("matias.cavieres")
        self.move(self.item, "inventado")
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, Commitment.Status.SUBMITTED)

    def test_the_cards_only_offer_the_buttons_that_are_allowed(self):
        self.login_as("matias.cavieres")
        columns = self.columns(self.client.get(reverse("core:compromisos_list")))
        card = next(card for card in columns["Ingresado"] if card["row"].obj.pk == self.item.pk)
        self.assertEqual([value for value, _ in card["moves"]], ["pending", "in_progress", "fulfilled"])
        self.item.status = Commitment.Status.FULFILLED
        self.item.save()
        columns = self.columns(self.client.get(reverse("core:compromisos_list")))
        card = next(card for card in columns["Realizado"] if card["row"].obj.pk == self.item.pk)
        self.assertEqual([value for value, _ in card["moves"]], ["in_progress"])

    def test_a_reader_gets_403_and_sees_no_buttons(self):
        self.login_as("consulta1")
        self.assertEqual(self.move(self.item, Commitment.Status.PENDING).status_code, 403)
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, Commitment.Status.SUBMITTED)
        response = self.client.get(reverse("core:compromisos_list"))
        self.assertNotContains(response, "canvas-move")

    def test_a_card_of_another_delegation_cannot_be_moved(self):
        other = make_commitment(self.south, self.south_officer, self.south_territory, "De la Sur")
        self.login_as("matias.cavieres")
        self.assertEqual(self.move(other, Commitment.Status.PENDING).status_code, 404)
        other.refresh_from_db()
        self.assertEqual(other.status, Commitment.Status.SUBMITTED)

    def test_the_move_needs_a_post_and_a_session(self):
        self.login_as("matias.cavieres")
        self.assertEqual(
            self.client.get(reverse("core:compromisos_move", args=[self.item.pk])).status_code, 405
        )
        self.client.logout()
        self.assertEqual(self.move(self.item, Commitment.Status.PENDING).status_code, 302)
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, Commitment.Status.SUBMITTED)


class AttentionWithVisitTests(PortalTestCase):
    """Una atención física (visita a terreno) crea sola su compromiso en la sección Compromisos."""

    def setUp(self):
        self.login_as("matias.cavieres")
        self.territory = Territory.objects.get(name="Territorio 1", delegation=self.north)
        self.due = portal_today() + timedelta(days=10)

    def register(self, **changes):
        data = self.intake_data(request_description="Pide revisar una luminaria en el pasaje.")
        data.update(changes)
        return self.client.post(reverse("core:actividades_create"), data)

    def newest(self):
        return Activity.objects.order_by("-pk").first()

    def test_an_attention_with_a_visit_creates_a_physical_commitment(self):
        before = Commitment.objects.count()
        response = self.register(requires_visit="on", due_date=self.due.isoformat(), territory=self.territory.pk)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Commitment.objects.count(), before + 1)
        activity = self.newest()
        self.assertTrue(activity.requires_visit)
        self.assertTrue(activity.commitment.physical)
        self.assertEqual(activity.commitment.due_date, self.due)
        self.assertEqual(history_of(activity.commitment)[0]["new"], "Ingresado")

    def test_the_new_commitment_shows_up_in_compromisos_and_not_in_the_agenda(self):
        self.register(
            requires_visit="on", due_date=self.due.isoformat(), territory=self.territory.pk, contact_name="Visita Prueba"
        )
        commitment = self.newest().commitment
        columns = {c["label"]: c["cards"] for c in self.client.get(reverse("core:compromisos_list")).context["board"]["columns"]}
        self.assertIn(commitment.pk, [card["row"].obj.pk for card in columns["Ingresado"]])
        agenda = self.client.get(reverse("core:agenda_list"), {"q": commitment.requester})
        self.assertNotIn(commitment.pk, [row.obj.pk for row in agenda.context["rows"]])

    def test_the_message_says_the_commitment_went_to_compromisos(self):
        response = self.register(requires_visit="on", due_date=self.due.isoformat(), territory=self.territory.pk)
        follow = self.client.get(response["Location"])
        self.assertContains(follow, "Se creó el compromiso en Compromisos")

    def test_the_pipeline_box_alone_still_goes_to_the_agenda(self):
        self.register(added_to_pipeline="on", due_date=self.due.isoformat(), territory=self.territory.pk)
        self.assertFalse(self.newest().commitment.physical)

    def test_both_boxes_create_a_single_physical_commitment(self):
        before = Commitment.objects.count()
        self.register(
            requires_visit="on", added_to_pipeline="on", due_date=self.due.isoformat(), territory=self.territory.pk
        )
        self.assertEqual(Commitment.objects.count(), before + 1)
        self.assertTrue(self.newest().commitment.physical)

    def test_a_visit_without_date_and_territory_is_refused(self):
        before = Commitment.objects.count()
        response = self.register(requires_visit="on")
        self.assertEqual(response.status_code, 200)
        self.assertIn("due_date", response.context["form"].errors)
        self.assertIn("territory", response.context["form"].errors)
        self.assertEqual(Commitment.objects.count(), before)

    def test_without_any_box_no_commitment_is_created(self):
        before = Commitment.objects.count()
        self.assertEqual(self.register().status_code, 302)
        self.assertEqual(Commitment.objects.count(), before)
        self.assertIsNone(self.newest().commitment)

    def test_the_form_shows_the_date_and_the_territory_for_either_box(self):
        response = self.client.get(reverse("core:actividades_create"))
        self.assertContains(response, 'data-show-when="id_requires_visit,id_added_to_pipeline"')


class ReportsCountEverythingTests(BoardBase):
    """Separar las pantallas no cambia los totales: el resumen y el dashboard cuentan todos los compromisos."""

    def test_the_collective_summary_counts_the_physical_commitments_too(self):
        self.login_as("jefatura1")
        before = self.client.get(reverse("core:commitment_summary")).context["total"]["total"]
        make_commitment(self.north, self.cavieres, self.territory, "Terreno Suma")
        make_commitment(self.north, self.cavieres, self.territory, "Agenda Suma", physical=False)
        after = self.client.get(reverse("core:commitment_summary")).context["total"]["total"]
        self.assertEqual(after, before + 2)
