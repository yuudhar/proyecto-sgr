"""Versión 51: Tubo de cartas, el tablero con Ingresado, Pendiente, Realizado y Vencido."""
from datetime import date, timedelta

from django.urls import reverse
from django.utils import timezone

from core.testing import PortalTestCase, portal_today
from operations import tube
from planning import periods
from planning.models import Period
from operations.models import Activity, Commitment, TubeItem
from organization.models import Officer


def make_item(delegation, officer, title="Actividad de Prueba", **changes):
    values = {
        "title": title,
        "requester": "Vecina de Prueba",
        "entered_date": portal_today() - timedelta(days=2),
        "due_date": portal_today() + timedelta(days=10),
        "responsible_officer": officer,
        "delegation": delegation,
    }
    values.update(changes)
    return TubeItem.objects.create(**values)


class TubeBase(PortalTestCase):

    def setUp(self):
        self.cavieres = Officer.objects.get(institutional_id="F-1001")
        self.south_officer = Officer.objects.get(institutional_id="F-2001")
        self.url = reverse("core:tubo_de_cartas_list")

    def columns(self, response):
        return {column["label"]: column["cards"] for column in response.context["board"]["columns"]}

    def kpis(self, response):
        return {kpi["label"]: kpi["value"] for kpi in response.context["board"]["kpis"]}


class TubeRulesTests(TubeBase):
    """Alta desde una atención y paso automático a «Vencido»."""

    def test_an_attention_leaves_one_activity_in_the_tube_and_never_a_second(self):
        activity = Activity.objects.filter(deleted_at__isnull=True, commitment__isnull=True).first()
        TubeItem.objects.filter(activity=activity).delete()
        Activity.objects.filter(pk=activity.pk).update(status="registered")
        activity.refresh_from_db()
        item = tube.create_for_activity(activity)
        self.assertEqual(item.status, TubeItem.Status.SUBMITTED)
        self.assertEqual(item.entered_date, activity.date)
        period = periods.containing(activity.date, activity.delegation)
        expected = period.end_date if period else activity.date + timedelta(days=tube.DEFAULT_DAYS)
        self.assertEqual(item.due_date, expected)
        self.assertEqual(item.delegation_id, activity.delegation_id)
        self.assertEqual(tube.create_for_activity(activity).pk, item.pk)
        self.assertEqual(TubeItem.objects.filter(activity=activity).count(), 1)

    def test_an_activity_past_its_date_becomes_overdue(self):
        late = make_item(self.north, self.cavieres, "Atrasada", due_date=portal_today() - timedelta(days=1))
        late_pending = make_item(
            self.north, self.cavieres, "Atrasada pendiente", due_date=portal_today() - timedelta(days=3),
            status=TubeItem.Status.PENDING,
        )
        overdue, back = tube.sync_overdue()
        self.assertEqual((overdue, back), (2, 0))
        for item in (late, late_pending):
            item.refresh_from_db()
            self.assertEqual(item.status, TubeItem.Status.OVERDUE)

    def test_a_done_activity_never_becomes_overdue(self):
        done = make_item(
            self.north, self.cavieres, "Hecha", due_date=portal_today() - timedelta(days=5),
            status=TubeItem.Status.FULFILLED,
        )
        tube.sync_overdue()
        done.refresh_from_db()
        self.assertEqual(done.status, TubeItem.Status.FULFILLED)

    def test_the_date_of_today_is_not_overdue_yet(self):
        today = make_item(self.north, self.cavieres, "Vence hoy", due_date=portal_today())
        tube.sync_overdue()
        today.refresh_from_db()
        self.assertEqual(today.status, TubeItem.Status.SUBMITTED)

    def test_an_overdue_activity_with_a_new_future_date_goes_back_to_pending(self):
        item = make_item(
            self.north, self.cavieres, "Reprogramada", due_date=portal_today() + timedelta(days=4),
            status=TubeItem.Status.OVERDUE,
        )
        self.assertEqual(tube.sync_overdue(), (0, 1))
        item.refresh_from_db()
        self.assertEqual(item.status, TubeItem.Status.PENDING)

    def test_an_archived_activity_is_left_alone(self):
        item = make_item(self.north, self.cavieres, "Archivada", due_date=portal_today() - timedelta(days=9))
        TubeItem.objects.filter(pk=item.pk).update(deleted_at=timezone.now())
        tube.sync_overdue()
        item.refresh_from_db()
        self.assertEqual(item.status, TubeItem.Status.SUBMITTED)

    def test_the_moves_the_rules_allow(self):
        for current, reachable in {
            "submitted": ["pending", "fulfilled"],
            "pending": ["submitted", "fulfilled"],
            "overdue": ["fulfilled"],
            "fulfilled": ["pending"],
        }.items():
            self.assertEqual(
                [value for value, _ in TubeItem.next_choices(current) if value != current], reachable, current
            )


class TubeBoardTests(TubeBase):
    """El tablero: cuatro columnas, indicadores y alcance por delegación."""

    def test_the_list_is_a_board_with_the_four_states(self):
        self.login_as("matias.cavieres")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(self.columns(response)), ["Ingresado", "Pendiente", "Realizado", "Vencido"])
        self.assertContains(response, "Tubo de cartas")

    def test_each_card_sits_in_the_column_of_its_state(self):
        make_item(self.north, self.cavieres, "Nueva")
        make_item(self.north, self.cavieres, "En espera", status=TubeItem.Status.PENDING)
        make_item(self.north, self.cavieres, "Terminada", status=TubeItem.Status.FULFILLED)
        make_item(self.north, self.cavieres, "Atrasada", due_date=portal_today() - timedelta(days=2))
        self.login_as("matias.cavieres")
        columns = self.columns(self.client.get(self.url))
        titles = {name: [card["title"] for card in cards] for name, cards in columns.items()}
        self.assertIn("Nueva", titles["Ingresado"])
        self.assertIn("En espera", titles["Pendiente"])
        self.assertIn("Terminada", titles["Realizado"])
        self.assertIn("Atrasada", titles["Vencido"])

    def test_the_indicators_count_the_board(self):
        TubeItem.objects.all().delete()
        make_item(self.north, self.cavieres, "A")
        make_item(self.north, self.cavieres, "B", status=TubeItem.Status.FULFILLED)
        make_item(self.north, self.cavieres, "C", status=TubeItem.Status.PENDING)
        make_item(self.north, self.cavieres, "D", due_date=portal_today() - timedelta(days=2))
        self.login_as("matias.cavieres")
        response = self.client.get(self.url)
        kpis = self.kpis(response)
        self.assertEqual(kpis["Actividades"], 4)
        self.assertEqual(kpis["Realizadas"], 1)
        self.assertEqual(kpis["Pendientes"], 2)
        self.assertEqual(kpis["Vencidas"], 1)
        self.assertContains(response, "Tasa de cumplimiento: 25,0 %")

    def test_a_delegation_only_sees_its_own_activities(self):
        make_item(self.south, self.south_officer, "Solo de la Sur")
        self.login_as("matias.cavieres")
        columns = self.columns(self.client.get(self.url))
        every_title = [card["title"] for cards in columns.values() for card in cards]
        self.assertNotIn("Solo de la Sur", every_title)

    def test_the_menu_has_the_tube(self):
        self.login_as("matias.cavieres")
        self.assertContains(self.client.get(reverse("core:dashboard")), self.url)


class TubeMoveTests(TubeBase):
    """Mover tarjetas con los botones del tablero."""

    def setUp(self):
        super().setUp()
        self.item = make_item(self.north, self.cavieres, "Para Mover")

    def move(self, item, status):
        return self.client.post(reverse("core:tubo_de_cartas_move", args=[item.pk]), {"estado": status})

    def test_a_card_moves_and_the_change_is_audited(self):
        self.login_as("matias.cavieres")
        response = self.move(self.item, TubeItem.Status.PENDING)
        self.assertRedirects(response, self.url, fetch_redirect_response=False)
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, TubeItem.Status.PENDING)

    def test_a_card_can_be_marked_as_done_and_reopened(self):
        self.login_as("matias.cavieres")
        self.move(self.item, TubeItem.Status.FULFILLED)
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, TubeItem.Status.FULFILLED)
        self.move(self.item, TubeItem.Status.PENDING)
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, TubeItem.Status.PENDING)

    def test_overdue_cannot_be_chosen_by_hand(self):
        self.login_as("matias.cavieres")
        self.move(self.item, TubeItem.Status.OVERDUE)
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, TubeItem.Status.SUBMITTED)

    def test_an_overdue_card_only_offers_to_be_done(self):
        late = make_item(self.north, self.cavieres, "Atrasada", due_date=portal_today() - timedelta(days=2))
        self.login_as("matias.cavieres")
        columns = self.columns(self.client.get(self.url))
        card = next(card for card in columns["Vencido"] if card["row"].obj.pk == late.pk)
        self.assertEqual([value for value, _ in card["moves"]], ["fulfilled"])
        self.move(late, TubeItem.Status.PENDING)
        late.refresh_from_db()
        self.assertEqual(late.status, TubeItem.Status.OVERDUE)

    def test_a_reader_gets_403_and_sees_no_buttons(self):
        self.login_as("consulta1")
        self.assertEqual(self.move(self.item, TubeItem.Status.PENDING).status_code, 403)
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, TubeItem.Status.SUBMITTED)
        self.assertNotContains(self.client.get(self.url), "canvas-move")

    def test_a_card_of_another_delegation_cannot_be_moved(self):
        other = make_item(self.south, self.south_officer, "De la Sur")
        self.login_as("matias.cavieres")
        self.assertEqual(self.move(other, TubeItem.Status.PENDING).status_code, 404)

    def test_the_move_needs_a_post_and_a_session(self):
        self.login_as("matias.cavieres")
        self.assertEqual(self.client.get(reverse("core:tubo_de_cartas_move", args=[self.item.pk])).status_code, 405)
        self.client.logout()
        self.assertEqual(self.move(self.item, TubeItem.Status.PENDING).status_code, 302)
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, TubeItem.Status.SUBMITTED)


class TubeCreateTests(TubeBase):
    """Agregar una actividad a mano, editarla y lo que pasa al registrar una atención."""

    def data(self, **changes):
        values = {
            "title": "Revisar la luminaria de la plaza",
            "description": "Hay tres focos apagados.",
            "requester": "Junta de vecinos",
            "entered_date": portal_today().isoformat(),
            "due_date": (portal_today() + timedelta(days=7)).isoformat(),
            "responsible_officer": self.cavieres.pk,
            "delegation": self.north.pk,
        }
        values.update(changes)
        return values

    def test_an_activity_is_added_by_hand_and_starts_in_ingresado(self):
        self.login_as("matias.cavieres")
        response = self.client.post(reverse("core:tubo_de_cartas_create"), self.data())
        self.assertEqual(response.status_code, 302)
        item = TubeItem.objects.get(title="Revisar la luminaria de la plaza")
        self.assertEqual(item.status, TubeItem.Status.SUBMITTED)
        self.assertIsNone(item.activity)

    def test_the_form_starts_with_today_and_the_end_of_the_current_quarter(self):
        self.login_as("matias.cavieres")
        form = self.client.get(reverse("core:tubo_de_cartas_create")).context["form"]
        self.assertEqual(form.initial["entered_date"], portal_today())
        period = periods.containing(portal_today(), self.north)
        expected = period.end_date if period else portal_today() + timedelta(days=tube.DEFAULT_DAYS)
        self.assertEqual(form.initial["due_date"], expected)

    def test_a_due_date_before_the_entry_is_refused(self):
        self.login_as("matias.cavieres")
        before = TubeItem.objects.count()
        response = self.client.post(
            reverse("core:tubo_de_cartas_create"),
            self.data(due_date=(portal_today() - timedelta(days=1)).isoformat()),
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("due_date", response.context["form"].errors)
        self.assertEqual(TubeItem.objects.count(), before)

    def test_an_officer_of_another_delegation_is_refused(self):
        self.login_as("admin")
        before = TubeItem.objects.count()
        response = self.client.post(
            reverse("core:tubo_de_cartas_create"), self.data(responsible_officer=self.south_officer.pk)
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("responsible_officer", response.context["form"].errors)
        self.assertEqual(TubeItem.objects.count(), before)

    def test_a_reader_cannot_add_an_activity(self):
        self.login_as("consulta1")
        self.assertEqual(self.client.get(reverse("core:tubo_de_cartas_create")).status_code, 403)

    def test_moving_the_date_of_an_overdue_activity_brings_it_back_to_pending(self):
        late = make_item(self.north, self.cavieres, "Atrasada", due_date=portal_today() - timedelta(days=3))
        self.login_as("matias.cavieres")
        self.client.get(self.url)
        late.refresh_from_db()
        self.assertEqual(late.status, TubeItem.Status.OVERDUE)
        response = self.client.post(
            reverse("core:tubo_de_cartas_update", args=[late.pk]),
            self.data(
                title="Atrasada",
                entered_date=late.entered_date.isoformat(),
                due_date=(portal_today() + timedelta(days=5)).isoformat(),
            ),
        )
        self.assertEqual(response.status_code, 302)
        self.client.get(self.url)
        late.refresh_from_db()
        self.assertEqual(late.status, TubeItem.Status.PENDING)

    def test_registering_an_attention_leaves_its_activity_in_ingresado(self):
        self.login_as("matias.cavieres")
        before = TubeItem.objects.count()
        data = self.intake_data(request_description="Pide revisar una luminaria en el pasaje.")
        response = self.client.post(reverse("core:actividades_create"), data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(TubeItem.objects.count(), before + 1)
        activity = Activity.objects.order_by("-pk").first()
        item = activity.tube_item
        self.assertEqual(item.status, TubeItem.Status.SUBMITTED)
        self.assertEqual(item.responsible_officer_id, activity.author_officer_id)

    def test_an_attention_that_is_refused_leaves_nothing_in_the_tube(self):
        self.login_as("matias.cavieres")
        before = TubeItem.objects.count()
        data = self.intake_data(request_description="")
        response = self.client.post(reverse("core:actividades_create"), data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(TubeItem.objects.count(), before)


class TubeCoherenceTests(TubeBase):
    """Los datos del tubo salen de la atención a la que pertenecen y se mantienen de acuerdo con ella."""

    def fresh_activity(self, **changes):
        activity = Activity.objects.filter(deleted_at__isnull=True, delegation=self.north).order_by("pk").first()
        TubeItem.objects.filter(activity=activity).delete()
        for name, value in changes.items():
            setattr(activity, name, value)
        activity.save()
        return Activity.objects.get(pk=activity.pk)

    def test_the_activity_takes_its_data_from_the_attention(self):
        activity = self.fresh_activity(contact_name="Rosa Mella", request_description="Poda de un árbol caído.")
        item = tube.create_for_activity(activity)
        self.assertIn("Rosa Mella", item.title)
        self.assertEqual(item.requester, "Rosa Mella")
        self.assertEqual(item.description, "Poda de un árbol caído.")
        self.assertEqual(item.responsible_officer_id, activity.author_officer_id)

    def test_the_state_follows_the_state_of_the_attention(self):
        for attention_state, expected in (
            ("registered", TubeItem.Status.SUBMITTED),
            ("in_progress", TubeItem.Status.PENDING),
            ("closed", TubeItem.Status.FULFILLED),
        ):
            activity = self.fresh_activity(status=attention_state)
            self.assertEqual(tube.create_for_activity(activity).status, expected, attention_state)

    def test_the_date_of_the_linked_commitment_is_the_due_date(self):
        activity = self.fresh_activity()
        commitment = Commitment.objects.filter(deleted_at__isnull=True, delegation=self.north).first()
        commitment.due_date = activity.date + timedelta(days=40)
        commitment.save()
        Activity.objects.filter(pk=activity.pk).update(commitment=commitment)
        activity.refresh_from_db()
        item = tube.create_for_activity(activity)
        self.assertEqual(item.due_date, activity.commitment.due_date)

    def test_an_attention_that_creates_a_commitment_gives_its_date_to_the_tube(self):
        from organization.models import Territory

        self.login_as("matias.cavieres")
        due = portal_today() + timedelta(days=10)
        territory = Territory.objects.filter(delegation=self.north).first()
        data = self.intake_data(
            request_description="Pide poda de un árbol.", added_to_pipeline="on", due_date=due.isoformat(), territory=territory.pk
        )
        response = self.client.post(reverse("core:actividades_create"), data)
        self.assertEqual(response.status_code, 302)
        activity = Activity.objects.order_by("-pk").first()
        self.assertIsNotNone(activity.commitment_id)
        self.assertEqual(activity.tube_item.due_date, activity.commitment.due_date)
        self.assertEqual(activity.tube_item.due_date, due)

    def test_closing_the_attention_marks_its_activity_as_done(self):
        self.login_as("matias.cavieres")
        activity = self.fresh_activity(status="registered")
        item = tube.create_for_activity(activity)
        activity.status = "closed"
        activity.save()
        self.assertEqual(tube.follow_activity(activity).pk, item.pk)
        item.refresh_from_db()
        self.assertEqual(item.status, TubeItem.Status.FULFILLED)
        self.assertIsNone(tube.follow_activity(activity))

    def test_the_sample_only_uses_real_attentions_and_never_repeats(self):
        TubeItem.objects.filter(delegation=self.north).delete()
        available = Activity.objects.filter(deleted_at__isnull=True, delegation=self.north).count()
        created = tube.load_sample(self.north, available + 10)
        self.assertEqual(created, available)
        for item in TubeItem.objects.filter(delegation=self.north):
            self.assertIsNotNone(item.activity_id)
            self.assertEqual(item.delegation_id, item.activity.delegation_id)
            self.assertEqual(item.entered_date, item.activity.date)
        self.assertEqual(tube.load_sample(self.north, available + 10), 0)


class TubeDefaultTermTests(TubeBase):
    """El plazo por defecto es el último día del trimestre de la atención."""

    def quarter(self, start, end, delegation=None):
        return Period.objects.create(
            start_date=start, end_date=end, computable_days=60, status=Period.Status.ACTIVE, delegation=delegation
        )

    def test_the_default_term_is_the_last_day_of_the_quarter(self):
        self.quarter(date(2033, 1, 1), date(2033, 3, 31))
        self.assertEqual(tube.default_due_date(date(2033, 1, 10), self.north), date(2033, 3, 31))
        self.assertEqual(tube.default_due_date(date(2033, 3, 31), self.north), date(2033, 3, 31))

    def test_the_quarter_of_the_delegation_wins_over_the_general_one(self):
        self.quarter(date(2033, 1, 1), date(2033, 3, 31))
        self.quarter(date(2033, 1, 1), date(2033, 2, 28), self.north)
        self.assertEqual(tube.default_due_date(date(2033, 1, 10), self.north), date(2033, 2, 28))
        self.assertEqual(tube.default_due_date(date(2033, 1, 10), self.south), date(2033, 3, 31))

    def test_without_a_quarter_the_term_falls_back_to_fifteen_days(self):
        self.assertEqual(tube.default_due_date(date(2040, 5, 1), self.north), date(2040, 5, 16))

    def test_an_attention_late_in_the_quarter_is_due_at_its_end(self):
        self.quarter(date(2033, 10, 1), date(2033, 12, 31))
        activity = Activity.objects.filter(deleted_at__isnull=True, delegation=self.north, commitment__isnull=True).first()
        TubeItem.objects.filter(activity=activity).delete()
        Activity.objects.filter(pk=activity.pk).update(date=date(2033, 12, 20))
        activity.refresh_from_db()
        self.assertEqual(tube.create_for_activity(activity).due_date, date(2033, 12, 31))
