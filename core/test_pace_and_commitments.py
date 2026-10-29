from zoneinfo import ZoneInfo

from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

from django.conf import settings
from django.contrib.auth.models import User
from django.test import SimpleTestCase
from django.urls import reverse
from django.utils import timezone

from core import ui
from core.commitments import STATUS_EVENT, collective_summary, history_of
from core.models import AuditLog
from core.testing import PortalTestCase, portal_today
from operations.models import Commitment
from organization.models import Officer
from planning.models import Period
from planning.pace import pace_of, weekdays_between


def fake_period(start, end, computable_days, status="active"):
    return SimpleNamespace(start_date=start, end_date=end, computable_days=computable_days, status=status)


class PaceRuleTests(SimpleTestCase):
    """RF-026: meta esperada al día = días computables transcurridos / días computables totales x 100."""

    MONDAY = date(2026, 1, 5)
    FRIDAY_NEXT = date(2026, 1, 16)  # dos semanas completas: 10 días computables

    def period(self, **changes):
        data = {"start": self.MONDAY, "end": self.FRIDAY_NEXT, "computable_days": 10, "status": "active"}
        data.update(changes)
        return fake_period(data["start"], data["end"], data["computable_days"], data["status"])

    def test_only_weekdays_are_counted(self):
        self.assertEqual(weekdays_between(self.MONDAY, self.MONDAY + timedelta(days=4)), 5)
        self.assertEqual(weekdays_between(self.MONDAY, self.FRIDAY_NEXT), 10)
        self.assertEqual(weekdays_between(date(2026, 1, 10), date(2026, 1, 11)), 0)  # sábado y domingo
        self.assertEqual(weekdays_between(self.MONDAY, self.MONDAY), 1)
        self.assertEqual(weekdays_between(self.FRIDAY_NEXT, self.MONDAY), 0)

    def test_the_first_day_already_counts_and_the_last_day_completes_it(self):
        first = pace_of(self.period(), today=self.MONDAY)
        self.assertEqual((first.elapsed_days, first.expected_percent), (1, Decimal("10.0")))
        last = pace_of(self.period(), today=self.FRIDAY_NEXT)
        self.assertEqual((last.elapsed_days, last.expected_percent), (10, Decimal("100.0")))

    def test_the_midpoint_is_half(self):
        pace = pace_of(self.period(), today=date(2026, 1, 9))
        self.assertEqual(pace.expected_percent, Decimal("50.0"))
        self.assertEqual(pace.stage, "running")
        self.assertEqual(pace.remaining_days, 5)

    def test_before_the_start_nothing_is_expected_and_after_the_end_it_never_exceeds_100(self):
        before = pace_of(self.period(), today=self.MONDAY - timedelta(days=3))
        self.assertEqual((before.expected_percent, before.stage), (Decimal("0.0"), "not_started"))
        after = pace_of(self.period(), today=self.FRIDAY_NEXT + timedelta(days=60))
        self.assertEqual((after.expected_percent, after.stage, after.elapsed_days), (Decimal("100.0"), "finished", 10))

    def test_weekends_do_not_advance_the_pace(self):
        friday = pace_of(self.period(), today=date(2026, 1, 9))
        sunday = pace_of(self.period(), today=date(2026, 1, 11))
        self.assertEqual(friday.expected_percent, sunday.expected_percent)

    def test_a_closed_period_is_fully_expected(self):
        pace = pace_of(self.period(status="closed"), today=date(2026, 1, 7))
        self.assertEqual(pace.expected_percent, Decimal("100.0"))

    def test_declared_computable_days_are_the_total_that_is_shown(self):
        pace = pace_of(self.period(computable_days=8), today=date(2026, 1, 9))
        self.assertEqual(pace.expected_percent, Decimal("50.0"))
        self.assertEqual((pace.total_days, pace.elapsed_days), (8, 4))
        self.assertEqual(pace.daily_percent, Decimal("12.50"))

    def test_the_expected_value_of_a_goal_follows_the_percentage(self):
        pace = pace_of(self.period(), today=date(2026, 1, 9))
        self.assertEqual(pace.expected_for(Decimal("200")), Decimal("100.00"))
        self.assertEqual(pace.expected_for(Decimal("15")), Decimal("7.50"))
        self.assertIsNone(pace.expected_for(None))

    def test_the_standing_compares_the_progress_with_what_is_expected(self):
        pace = pace_of(self.period(), today=date(2026, 1, 9))  # esperado: 50 %
        amber = Decimal("60")
        self.assertEqual(pace.standing(Decimal("50"), amber), "green")
        self.assertEqual(pace.standing(Decimal("80"), amber), "green")
        self.assertEqual(pace.standing(Decimal("30"), amber), "amber")
        self.assertEqual(pace.standing(Decimal("29.9"), amber), "red")
        self.assertEqual(pace.standing(None, amber), "")
        self.assertEqual(pace.difference(Decimal("35")), Decimal("-15.0"))

    def test_a_period_without_weekdays_does_not_divide_by_zero(self):
        weekend = fake_period(date(2026, 1, 10), date(2026, 1, 11), 0)
        self.assertEqual(pace_of(weekend, today=date(2026, 1, 10)).expected_percent, Decimal("0.0"))
        self.assertEqual(pace_of(weekend, today=date(2026, 2, 1)).expected_percent, Decimal("100.0"))


class PaceScreensTests(PortalTestCase):

    def test_the_delegation_board_shows_the_pace_of_the_period(self):
        self.login_as("admin")
        response = self.client.get(reverse("core:delegation_board"), {"delegacion": self.north.pk})
        summary = response.context["pace_summary"]
        with timezone.override(ZoneInfo(settings.PORTAL_TIME_ZONE)):  # el día de Santiago, como en la pantalla
            self.assertEqual(summary["pace"], pace_of(response.context["period"]))
        self.assertContains(response, "Ritmo del período")
        self.assertContains(response, "Meta esperada al día")
        self.assertContains(response, "% diario esperado")
        self.assertContains(response, "Esperado hoy")
        self.assertTrue(summary["has_achieved"])
        self.assertIn(summary["standing"], ("green", "amber", "red"))

    def test_every_goal_line_has_its_expected_value(self):
        self.login_as("admin")
        response = self.client.get(reverse("core:delegation_board"), {"delegacion": self.north.pk})
        lines = [line for result in response.context["results"] for line in result["lines"]]
        self.assertTrue(lines)
        pace = response.context["pace_summary"]["pace"]
        for line in lines:
            self.assertNotEqual(line["expected"], "")
            self.assertEqual(line["expected"], ui.fmt_number(pace.expected_for(line["goal"].target_value)))

    def test_the_personal_dashboard_shows_the_pace_and_the_expected_value_per_goal(self):
        self.login_as("matias.cavieres")
        response = self.client.get(reverse("core:dashboard"))
        self.assertContains(response, "Ritmo del período")
        self.assertContains(response, "Esperado hoy:")
        self.assertIsNotNone(response.context["pace_summary"])

    def test_the_general_dashboard_also_shows_it(self):
        self.login_as("admin")
        response = self.client.get(reverse("core:dashboard"))
        self.assertContains(response, "Meta esperada al día")

    def test_there_is_no_pace_panel_without_periods(self):
        from planning.models import Adjustment, Goal, Indicator

        Adjustment.objects.all().delete()
        Indicator.objects.all().delete()
        Goal.objects.all().delete()
        Period.objects.all().delete()
        self.login_as("admin")
        response = self.client.get(reverse("core:delegation_board"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Ritmo del período")
        self.assertEqual(self.client.get(reverse("core:dashboard")).status_code, 200)


class CommitmentStatusTests(PortalTestCase):
    """RF-018: Ingresado, Pendiente, En proceso y Realizado, con transiciones válidas e historial."""

    def setUp(self):
        self.admin = User.objects.get(username="admin")

    def commitment_in(self, status, delegation=None):
        delegation = delegation or self.north
        territory = delegation.territories.first()
        officer = Officer.objects.filter(delegation=delegation).first()
        return Commitment.objects.create(
            requester=f"Solicitante {status}",
            territory=territory,
            due_date=portal_today() + timedelta(days=10),
            request_date=portal_today(),
            status=status,
            responsible_officer=officer,
            delegation=delegation,
        )

    def post_status(self, commitment, status):
        data = {
            "requester": commitment.requester,
            "requester_type": commitment.requester_type,
            "source": "",
            "request_date": commitment.request_date.isoformat(),
            "description": "",
            "territory": commitment.territory_id,
            "due_date": commitment.due_date.isoformat(),
            "support": "",
            "status": status,
            "notes": "",
            "responsible_officer": commitment.responsible_officer_id,
            "delegation": commitment.delegation_id,
        }
        self.client.force_login(self.admin)
        return self.client.post(reverse("core:agenda_update", args=[commitment.pk]), data)

    def test_the_four_states_exist_in_the_order_of_the_flow(self):
        self.assertEqual(
            [label for _, label in Commitment.Status.choices],
            ["Ingresado", "Pendiente", "En proceso", "Realizado"],
        )

    def test_the_transition_rules(self):
        status = Commitment.Status
        self.assertTrue(Commitment.can_move(status.SUBMITTED, status.PENDING))
        self.assertTrue(Commitment.can_move(status.SUBMITTED, status.FULFILLED))
        self.assertTrue(Commitment.can_move(status.PENDING, status.IN_PROGRESS))
        self.assertTrue(Commitment.can_move(status.IN_PROGRESS, status.PENDING))
        self.assertTrue(Commitment.can_move(status.IN_PROGRESS, status.FULFILLED))
        self.assertTrue(Commitment.can_move(status.FULFILLED, status.IN_PROGRESS))  # reapertura
        self.assertTrue(Commitment.can_move(status.PENDING, status.PENDING))
        for current in (status.PENDING, status.IN_PROGRESS, status.FULFILLED):
            self.assertFalse(Commitment.can_move(current, status.SUBMITTED), current)
        self.assertFalse(Commitment.can_move(status.FULFILLED, status.PENDING))

    def test_every_state_is_covered_by_the_transition_table(self):
        self.assertEqual(set(Commitment.TRANSITIONS), set(Commitment.Status.values))

    def test_the_edit_form_only_offers_reachable_states(self):
        self.client.force_login(self.admin)
        expected = {
            Commitment.Status.SUBMITTED: {"submitted", "pending", "in_progress", "fulfilled"},
            Commitment.Status.PENDING: {"pending", "in_progress", "fulfilled"},
            Commitment.Status.IN_PROGRESS: {"in_progress", "pending", "fulfilled"},
            Commitment.Status.FULFILLED: {"fulfilled", "in_progress"},
        }
        for status, values in expected.items():
            commitment = self.commitment_in(status)
            form = self.client.get(reverse("core:agenda_update", args=[commitment.pk])).context["form"]
            self.assertEqual({value for value, _ in form.fields["status"].choices}, values, status)

    def test_a_new_commitment_can_start_in_any_state(self):
        self.client.force_login(self.admin)
        form = self.client.get(reverse("core:agenda_create")).context["form"]
        self.assertEqual({value for value, _ in form.fields["status"].choices}, set(Commitment.Status.values))

    def test_an_invalid_transition_is_refused_and_nothing_changes(self):
        commitment = self.commitment_in(Commitment.Status.PENDING)
        response = self.post_status(commitment, Commitment.Status.SUBMITTED)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "solo puede pasar a")
        commitment.refresh_from_db()
        self.assertEqual(commitment.status, Commitment.Status.PENDING)
        self.assertEqual(history_of(commitment), [])

    def test_a_valid_transition_is_saved_and_recorded_with_who_and_when(self):
        commitment = self.commitment_in(Commitment.Status.SUBMITTED)
        response = self.post_status(commitment, Commitment.Status.PENDING)
        self.assertEqual(response.status_code, 302)
        commitment.refresh_from_db()
        self.assertEqual(commitment.status, Commitment.Status.PENDING)
        [entry] = history_of(commitment)
        self.assertEqual((entry["previous"], entry["new"]), ("Ingresado", "Pendiente"))
        self.assertEqual(entry["user"], "admin")
        self.assertLessEqual(abs(timezone.now() - entry["date"]), timedelta(minutes=1))

    def test_the_history_keeps_every_step_in_order_and_includes_the_reopening(self):
        commitment = self.commitment_in(Commitment.Status.SUBMITTED)
        for status in ("pending", "in_progress", "fulfilled", "in_progress"):
            self.assertEqual(self.post_status(commitment, status).status_code, 302)
        steps = [(entry["previous"], entry["new"]) for entry in history_of(commitment)]
        self.assertEqual(
            steps,
            [
                ("Ingresado", "Pendiente"),
                ("Pendiente", "En proceso"),
                ("En proceso", "Realizado"),
                ("Realizado", "En proceso"),
            ],
        )

    def test_saving_without_changing_the_state_adds_no_history(self):
        commitment = self.commitment_in(Commitment.Status.IN_PROGRESS)
        self.post_status(commitment, Commitment.Status.IN_PROGRESS)
        self.assertEqual(history_of(commitment), [])
        self.assertFalse(AuditLog.objects.filter(event=STATUS_EVENT, record_id=commitment.pk).exists())

    def test_creating_a_commitment_records_its_initial_state(self):
        self.client.force_login(self.admin)
        territory = self.north.territories.first()
        officer = Officer.objects.filter(delegation=self.north).first()
        response = self.client.post(
            reverse("core:agenda_create"),
            {
                "requester": "Vecinos de prueba",
                "requester_type": "EXTERNAL",
                "request_date": portal_today().isoformat(),
                "due_date": (portal_today() + timedelta(days=5)).isoformat(),
                "territory": territory.pk,
                "status": "submitted",
                "responsible_officer": officer.pk,
                "delegation": self.north.pk,
            },
        )
        self.assertEqual(response.status_code, 302)
        commitment = Commitment.objects.get(requester="Vecinos de prueba")
        [entry] = history_of(commitment)
        self.assertEqual((entry["previous"], entry["new"]), ("", "Ingresado"))

    def test_the_detail_shows_the_history_panel(self):
        commitment = self.commitment_in(Commitment.Status.SUBMITTED)
        self.post_status(commitment, Commitment.Status.PENDING)
        page = self.client.get(reverse("core:agenda_detail", args=[commitment.pk]))
        self.assertContains(page, "Historial de estados")
        self.assertContains(page, "Pendiente")
        self.assertContains(page, "admin")
        empty = self.commitment_in(Commitment.Status.SUBMITTED)
        self.assertContains(self.client.get(reverse("core:agenda_detail", args=[empty.pk])), "aún no tiene cambios de estado")

    def test_a_pending_commitment_still_counts_as_open(self):
        self.login_as("admin")
        before = self.client.get(reverse("core:dashboard")).context["pending"]
        open_before = next(item["total"] for item in before if item["label"] == "Compromisos abiertos")
        self.commitment_in(Commitment.Status.PENDING)
        after = self.client.get(reverse("core:dashboard")).context["pending"]
        self.assertEqual(next(item["total"] for item in after if item["label"] == "Compromisos abiertos"), open_before + 1)

    def test_the_seed_has_one_commitment_in_each_state(self):
        self.assertEqual(
            set(Commitment.objects.values_list("status", flat=True)), set(Commitment.Status.values)
        )

    def test_the_pending_state_has_its_own_tone_in_the_list(self):
        self.commitment_in(Commitment.Status.PENDING)
        self.login_as("admin")
        page = self.client.get(reverse("core:agenda_list"), {"status": "pending"})
        self.assertContains(page, "Pendiente")
        self.assertContains(page, "chip-warn")


class CollectiveSummaryTests(PortalTestCase):
    """RF-021: compromisos por funcionario y estado, con % realizado y % por realizar."""

    def setUp(self):
        self.url = reverse("core:commitment_summary")

    def make(self, officer, status, requester="Prueba", due=None):
        return Commitment.objects.create(
            requester=requester,
            territory=officer.delegation.territories.first(),
            due_date=due or portal_today() + timedelta(days=3),
            request_date=portal_today(),
            status=status,
            responsible_officer=officer,
            delegation=officer.delegation,
        )

    def rows_by_name(self, response):
        return {row["label"]: row for row in response.context["rows"]}

    def test_the_summary_counts_by_officer_and_state_from_the_data(self):
        self.login_as("admin")
        response = self.client.get(self.url, {"delegacion": self.north.pk})
        self.assertEqual(response.status_code, 200)
        rows = self.rows_by_name(response)
        for officer in Officer.objects.filter(delegation=self.north, status=Officer.Status.ACTIVE):
            counts = [
                Commitment.objects.filter(responsible_officer=officer, status=status).count()
                for status in Commitment.Status.values
            ]
            self.assertEqual(rows[officer.name]["counts"], counts, officer.name)
            self.assertEqual(rows[officer.name]["total"], sum(counts))
        total = response.context["total"]
        self.assertEqual(total["total"], Commitment.objects.filter(delegation=self.north).count())
        self.assertEqual(total["total"], sum(row["total"] for row in response.context["rows"]))

    def test_percentages_are_done_over_total_and_the_rest(self):
        officer = Officer.objects.filter(delegation=self.north, status=Officer.Status.ACTIVE).first()
        Commitment.objects.filter(responsible_officer=officer).delete()
        self.make(officer, Commitment.Status.FULFILLED)
        self.make(officer, Commitment.Status.PENDING)
        self.make(officer, Commitment.Status.IN_PROGRESS)
        self.login_as("admin")
        row = self.rows_by_name(self.client.get(self.url, {"delegacion": self.north.pk}))[officer.name]
        self.assertEqual(row["counts"], [0, 1, 1, 1])
        self.assertEqual(row["done_percent"], Decimal("33.3"))
        self.assertEqual(row["todo_percent"], Decimal("66.7"))

    def test_an_officer_without_commitments_is_listed_without_percentages(self):
        officer = Officer.objects.filter(delegation=self.north, status=Officer.Status.ACTIVE).first()
        Commitment.objects.filter(responsible_officer=officer).delete()
        self.login_as("admin")
        response = self.client.get(self.url, {"delegacion": self.north.pk})
        row = self.rows_by_name(response)[officer.name]
        self.assertEqual((row["total"], row["done_percent"], row["todo_percent"]), (0, None, None))
        self.assertContains(response, "Sin compromisos")

    def test_all_the_delegations_can_be_summed_together(self):
        self.login_as("admin")
        response = self.client.get(self.url, {"delegacion": "todas"})
        self.assertIsNone(response.context["delegation"])
        self.assertEqual(response.context["total"]["total"], Commitment.objects.count())

    def test_the_period_filters_by_the_committed_date(self):
        officer = Officer.objects.filter(delegation=self.north, status=Officer.Status.ACTIVE).first()
        self.make(officer, Commitment.Status.FULFILLED, "Antiguo", due=date(2020, 1, 15))
        period = Period.objects.create(
            start_date=date(2020, 1, 1), end_date=date(2020, 3, 31), computable_days=63
        )
        self.login_as("admin")
        response = self.client.get(self.url, {"delegacion": self.north.pk, "periodo": period.pk})
        self.assertEqual(response.context["period"], period)
        self.assertEqual(response.context["total"]["total"], 1)
        self.assertEqual(response.context["total"]["done_percent"], Decimal("100.0"))
        everything = self.client.get(self.url, {"delegacion": self.north.pk, "periodo": "todos"})
        self.assertGreater(everything.context["total"]["total"], 1)

    def test_the_light_follows_the_collective_threshold(self):
        officer = Officer.objects.filter(delegation=self.north, status=Officer.Status.ACTIVE).first()
        Commitment.objects.filter(responsible_officer=officer).delete()
        for _ in range(4):
            self.make(officer, Commitment.Status.FULFILLED)
        self.make(officer, Commitment.Status.SUBMITTED)  # 80 %
        self.login_as("admin")
        row = self.rows_by_name(self.client.get(self.url, {"delegacion": self.north.pk}))[officer.name]
        self.assertEqual(row["done_percent"], Decimal("80.0"))
        self.assertEqual(row["light"], "green")
        self.make(officer, Commitment.Status.SUBMITTED)
        self.make(officer, Commitment.Status.SUBMITTED)  # 4 de 7 = 57,1 %
        row = self.rows_by_name(self.client.get(self.url, {"delegacion": self.north.pk}))[officer.name]
        self.assertEqual(row["light"], "red")

    def test_a_worker_only_sees_their_own_delegation(self):
        south_officer = Officer.objects.filter(delegation=self.south, status=Officer.Status.ACTIVE).first()
        self.login_as("matias.cavieres")
        response = self.client.get(self.url, {"delegacion": self.south.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["delegation"], self.north)
        self.assertNotIn(south_officer.name, self.rows_by_name(response))
        self.assertEqual(response.context["total"]["total"], Commitment.objects.filter(delegation=self.north).count())
        self.assertFalse(response.context["can_pick_delegation"])

    def test_someone_without_the_permission_gets_403(self):
        self.client.force_login(self.make_user("sin.permisos"))
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_an_anonymous_visitor_is_sent_to_the_login(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)

    def test_the_page_is_live_and_in_the_menu(self):
        self.login_as("admin")
        response = self.client.get(self.url)
        self.assertContains(response, "data-live-page")
        self.assertContains(response, "data-live-region")
        self.assertContains(response, "% realizado")
        self.assertContains(response, "% por realizar")
        self.assertIn("Resumen colectivo", self.menu_labels(response))

    def test_the_summary_function_adds_commitments_of_officers_outside_the_list(self):
        officer = Officer.objects.filter(delegation=self.north, status=Officer.Status.ACTIVE).first()
        self.make(officer, Commitment.Status.FULFILLED)
        rows, total = collective_summary(Commitment.objects.filter(responsible_officer=officer), [])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["label"], officer.name)
        self.assertEqual(total["total"], rows[0]["total"])
