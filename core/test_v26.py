from datetime import date, timedelta
from decimal import Decimal
from io import StringIO
from types import SimpleNamespace

from django.contrib.messages import get_messages
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, transaction
from django.test import SimpleTestCase
from django.urls import reverse
from django.utils import timezone

from core import ui
from core.activity_stats import ALERT_DAYS, Recent, daily_average, delegation_recent, recent_activity
from core.commitments import (
    DUE_SOON_DAYS,
    collective_summary,
    deadline_counts,
    deadline_state,
    deadline_text,
)
from core.crud import conflict_message, last_change_text
from core.models import AuditLog
from core.results import officer_summary, officer_weights, weight_problems, weights_state
from core.testing import PortalTestCase
from evidence.models import Evidence
from operations.models import Activity, Commitment
from organization.models import Item, Officer
from planning import calculation
from planning.calculation import IndicatorIndex, is_suspended, suspended
from planning.models import Goal, Indicator, Period
from planning.pace import pace_of


class CalculationBase(PortalTestCase):
    """Datos comunes: la semilla trae metas pero los indicadores de prueba no están calculados por funcionario."""

    def setUp(self):
        self.period = Period.objects.get(status=Period.Status.ACTIVE)
        self.cavieres = self.officer("F-1001")
        self.goal = Goal.objects.get(officer=self.cavieres, item__name="Visita Domiciliaria")
        self.cargo_goal = Goal.objects.get(position__isnull=False, period=self.period)
        self.visit = Item.objects.get(name="Visita Domiciliaria")
        self.counter = 0

    def approved_activity(self, officer=None, item=None, when=None, status=Evidence.ReviewStatus.APPROVED):
        """Crea una actividad con una evidencia en el estado pedido."""
        officer = officer or self.cavieres
        self.counter += 1
        activity = Activity.objects.create(
            date=when or self.period.start_date + timedelta(days=30),
            item=item or self.visit,
            contact_name=f"Contacto {self.counter}",
            delegation=officer.delegation,
            author_officer=officer,
        )
        Evidence.objects.create(
            unique_code=f"EVD-T26-{activity.pk}",
            file_link="evidencias/prueba.pdf",
            review_status=status,
            activity=activity,
            author_officer=self.officer("F-1002"),
        )
        return activity

    def progress(self, goal=None, officer=None):
        return calculation.compute(goal or self.goal, officer or self.cavieres).progress

    def latest(self, goal=None, officer=None):
        return (
            Indicator.objects.filter(goal=goal or self.goal, officer=officer or self.cavieres)
            .order_by("-calculated_at", "-pk")
            .first()
        )


class AutomaticCalculationTests(CalculationBase):
    """RF-022, RF-023, RF-024 y RF-014: avance, cumplimiento y ponderado se calculan solos con evidencia aprobada."""

    def test_only_activities_with_approved_evidence_count(self):
        before = self.progress()
        self.approved_activity(status=Evidence.ReviewStatus.PENDING)
        self.approved_activity(status=Evidence.ReviewStatus.REJECTED)
        self.assertEqual(self.progress(), before)
        self.approved_activity()
        self.assertEqual(self.progress(), before + 1)

    def test_the_seed_activity_with_an_approved_evidence_is_the_only_one_that_counts_today(self):
        self.assertEqual(self.progress(), Decimal(1))
        self.assertEqual(calculation.valid_activities(self.goal, self.cavieres).count(), 1)

    def test_an_activity_with_two_approved_evidences_counts_once(self):
        activity = self.approved_activity()
        Evidence.objects.create(
            unique_code="EVD-T26-DOBLE",
            file_link="evidencias/prueba.pdf",
            review_status=Evidence.ReviewStatus.APPROVED,
            activity=activity,
            author_officer=self.officer("F-1002"),
        )
        self.assertEqual(self.progress(), Decimal(2))

    def test_archived_activities_and_deleted_evidence_do_not_count(self):
        activity = self.approved_activity()
        self.assertEqual(self.progress(), Decimal(2))
        Evidence.objects.filter(activity=activity).update(deleted_at=timezone.now())
        self.assertEqual(self.progress(), Decimal(1))
        other = self.approved_activity()
        Activity.objects.filter(pk=other.pk).update(deleted_at=timezone.now())
        self.assertEqual(self.progress(), Decimal(1))

    def test_activities_outside_the_period_or_of_other_officers_do_not_count(self):
        self.approved_activity(when=self.period.start_date - timedelta(days=1))
        self.approved_activity(when=self.period.end_date + timedelta(days=1))
        self.approved_activity(officer=self.officer("F-2001"))
        self.assertEqual(self.progress(), Decimal(1))
        self.approved_activity(when=self.period.end_date)
        self.approved_activity(when=self.period.start_date)
        self.assertEqual(self.progress(), Decimal(3))

    def test_activities_of_a_sub_attention_count_for_the_parent_item(self):
        parent = Item.objects.create(name="Atención general T26")
        child = Item.objects.create(name="Sub atención T26", parent_item=parent)
        goal = Goal.objects.create(
            item=parent, officer=self.cavieres, period=self.period, target_value=4, unit="atenciones", weight=10
        )
        self.approved_activity(item=child)
        self.approved_activity(item=parent)
        self.approved_activity(item=self.visit)  # otro ítem
        self.assertEqual(self.progress(goal), Decimal(2))

    def test_compliance_is_progress_over_the_target(self):
        Goal.objects.filter(pk=self.goal.pk).update(target_value=4)
        self.goal.refresh_from_db()
        result = calculation.compute(self.goal, self.cavieres)
        self.assertEqual((result.progress, result.compliance), (Decimal("1.00"), Decimal("25.00")))

    def test_compliance_is_capped_at_the_period_cap(self):
        Goal.objects.filter(pk=self.goal.pk).update(target_value=2)
        self.goal.refresh_from_db()
        for _ in range(3):
            self.approved_activity()
        result = calculation.compute(self.goal, self.cavieres)
        self.assertEqual(result.progress, Decimal("4.00"))
        self.assertEqual(result.uncapped, Decimal("200.00"))
        self.assertEqual(result.compliance, self.period.weighted_cap)
        self.assertEqual(result.light, Indicator.StatusLight.GREEN)

    def test_the_weighted_compliance_uses_the_weight_of_the_goal(self):
        Goal.objects.filter(pk=self.goal.pk).update(target_value=2, weight=50)
        self.goal.refresh_from_db()
        result = calculation.compute(self.goal, self.cavieres)
        self.assertEqual((result.compliance, result.weighting), (Decimal("50.00"), Decimal("25.00")))

    def test_the_traffic_light_follows_the_period_thresholds(self):
        Goal.objects.filter(pk=self.goal.pk).update(target_value=1)
        self.goal.refresh_from_db()
        green = calculation.compute(self.goal, self.cavieres)
        self.assertEqual(green.light, Indicator.StatusLight.GREEN)
        Goal.objects.filter(pk=self.goal.pk).update(target_value=Decimal("1.5"))
        self.goal.refresh_from_db()
        amber = calculation.compute(self.goal, self.cavieres)  # 66,67 %: ámbar entre 60 y 80
        self.assertEqual(amber.light, Indicator.StatusLight.AMBER)
        Goal.objects.filter(pk=self.goal.pk).update(target_value=20)
        self.goal.refresh_from_db()
        self.assertEqual(calculation.compute(self.goal, self.cavieres).light, Indicator.StatusLight.RED)

    def test_the_result_is_saved_as_an_indicator_of_that_officer(self):
        created = calculation.save_if_changed(self.goal, self.cavieres)
        self.assertEqual(created.officer, self.cavieres)
        self.assertEqual((created.progress, created.compliance, created.weighting), (Decimal(1), Decimal(5), Decimal(5)))
        self.assertEqual(created.status_light, Indicator.StatusLight.RED)

    def test_an_indicator_is_only_saved_again_when_the_values_change(self):
        self.assertIsNotNone(calculation.save_if_changed(self.goal, self.cavieres))
        self.assertIsNone(calculation.save_if_changed(self.goal, self.cavieres))
        self.assertEqual(Indicator.objects.filter(goal=self.goal, officer=self.cavieres).count(), 1)
        self.approved_activity()
        newer = calculation.save_if_changed(self.goal, self.cavieres)
        self.assertEqual(newer.progress, Decimal(2))
        self.assertEqual(Indicator.objects.filter(goal=self.goal, officer=self.cavieres).count(), 2)
        self.assertEqual(self.latest(), newer)

    def test_a_goal_of_the_position_is_calculated_for_each_active_officer_of_that_position(self):
        officers = calculation.officers_of(self.cargo_goal)
        expected = Officer.objects.filter(
            position=self.cargo_goal.position, status=Officer.Status.ACTIVE, deleted_at__isnull=True
        )
        self.assertEqual({officer.pk for officer in officers}, {officer.pk for officer in expected})
        self.assertGreaterEqual(len(officers), 4)
        created = calculation.recalculate_goal(self.cargo_goal)
        self.assertEqual(created, len(officers))

    def test_each_officer_of_the_position_gets_his_own_progress(self):
        mine = self.officer("F-1001")
        other = self.officer("F-2001")
        item = self.cargo_goal.item
        self.approved_activity(officer=mine, item=item)
        self.approved_activity(officer=mine, item=item)
        self.approved_activity(officer=other, item=item)
        calculation.recalculate_goal(self.cargo_goal)
        self.assertEqual(self.latest(self.cargo_goal, mine).progress, Decimal(2))
        self.assertEqual(self.latest(self.cargo_goal, other).progress, Decimal(1))
        self.assertEqual(self.latest(self.cargo_goal, self.officer("F-1004")).progress, Decimal(0))
        self.assertEqual(self.latest(self.cargo_goal, mine).compliance, Decimal("4.00"))

    def test_a_personal_goal_is_only_calculated_for_its_officer(self):
        self.assertEqual([officer.pk for officer in calculation.officers_of(self.goal)], [self.cavieres.pk])
        calculation.recalculate_goal(self.goal)
        self.assertEqual(Indicator.objects.filter(goal=self.goal, officer__isnull=False).count(), 1)

    def test_recalculating_a_period_creates_indicators_only_once(self):
        first = calculation.recalculate_period(self.period)
        self.assertGreater(first, 0)
        self.assertEqual(calculation.recalculate_period(self.period), 0)

    def test_a_closed_period_is_not_recalculated_unless_forced(self):
        Period.objects.filter(pk=self.period.pk).update(status=Period.Status.CLOSED)
        period = Period.objects.get(pk=self.period.pk)
        self.assertEqual(calculation.recalculate_period(period), 0)
        self.assertEqual(calculation.recalculate_all(), 0)
        self.assertFalse(Indicator.objects.filter(officer__isnull=False).exists())
        self.assertGreater(calculation.recalculate_all(include_closed=True), 0)
        self.assertTrue(Indicator.objects.filter(officer__isnull=False).exists())

    def test_deleted_goals_are_not_calculated(self):
        Goal.objects.filter(pk=self.goal.pk).update(deleted_at=timezone.now())
        goal = Goal.objects.get(pk=self.goal.pk)
        self.assertFalse(calculation.calculable(goal))
        self.assertEqual(calculation.recalculate_goal(goal), 0)

    def test_a_target_of_zero_does_not_divide_by_zero(self):
        goal = Goal(
            item=self.visit, officer=self.cavieres, period=self.period, target_value=Decimal(0), unit="x", weight=10
        )
        result = calculation.compute(goal, self.cavieres)
        self.assertEqual((result.compliance, result.weighting), (Decimal(0), Decimal("0.00")))

    def test_the_management_command_recalculates_everything(self):
        out = StringIO()
        call_command("recalcular_indicadores", stdout=out)
        self.assertIn("Indicadores recalculados:", out.getvalue())
        self.assertTrue(Indicator.objects.filter(officer=self.cavieres).exists())
        again = StringIO()
        call_command("recalcular_indicadores", stdout=again)
        self.assertIn("0 nuevo(s)", again.getvalue())

    def test_the_management_command_accepts_a_period_and_rejects_an_unknown_one(self):
        out = StringIO()
        call_command("recalcular_indicadores", periodo=self.period.pk, stdout=out)
        self.assertTrue(Indicator.objects.filter(goal__period=self.period, officer__isnull=False).exists())
        with self.assertRaises(CommandError):
            call_command("recalcular_indicadores", periodo=999999, stdout=StringIO())

    def test_the_management_command_skips_closed_periods_unless_asked(self):
        Period.objects.filter(pk=self.period.pk).update(status=Period.Status.CLOSED)
        call_command("recalcular_indicadores", stdout=StringIO())
        self.assertFalse(Indicator.objects.filter(officer__isnull=False).exists())
        call_command("recalcular_indicadores", "--incluir-cerrados", stdout=StringIO())
        self.assertTrue(Indicator.objects.filter(officer__isnull=False).exists())


class AutomaticTriggersTests(CalculationBase):
    """El cálculo se dispara solo al cambiar actividades, evidencias, validaciones, metas o el período."""

    def test_approving_an_evidence_recalculates_the_officer(self):
        activity = self.approved_activity(status=Evidence.ReviewStatus.PENDING)
        evidence = Evidence.objects.get(activity=activity)
        with self.captureOnCommitCallbacks(execute=True):
            evidence.review_status = Evidence.ReviewStatus.APPROVED
            evidence.save()
        self.assertEqual(self.latest().progress, Decimal(2))

    def test_rejecting_an_approved_evidence_lowers_the_progress(self):
        calculation.recalculate_all()
        self.assertEqual(self.latest().progress, Decimal(1))
        evidence = Evidence.objects.get(unique_code="EVD-NORTE-0002")
        with self.captureOnCommitCallbacks(execute=True):
            evidence.review_status = Evidence.ReviewStatus.REJECTED
            evidence.save()
        self.assertEqual(self.latest().progress, Decimal(0))

    def test_validating_through_the_screen_recalculates_the_indicator(self):
        calculation.recalculate_all()
        activity = Activity.objects.create(
            date=self.period.start_date + timedelta(days=10),
            item=self.visit,
            contact_name="Contacto pantalla",
            delegation=self.north,
            author_officer=self.cavieres,
        )
        evidence = Evidence.objects.create(
            unique_code="EVD-T26-PANTALLA",
            file_link="evidencias/prueba.pdf",
            activity=activity,
            author_officer=self.officer("F-1002"),
        )
        self.login_as("matias.cavieres")
        url = reverse("core:validate_evidence", args=[evidence.pk])
        version = self.client.get(url).context["version"]
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                url, {"decision": "approved", "result": "Conforme", "notes": "", "_version": version}
            )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.latest().progress, Decimal(2))

    def test_a_new_activity_that_changes_nothing_adds_no_indicator(self):
        calculation.recalculate_all()
        total = Indicator.objects.filter(officer__isnull=False).count()
        with self.captureOnCommitCallbacks(execute=True):
            Activity.objects.create(
                date=self.period.start_date + timedelta(days=12),
                item=self.visit,
                delegation=self.north,
                author_officer=self.cavieres,
            )
        self.assertEqual(Indicator.objects.filter(officer__isnull=False).count(), total)

    def test_changing_the_author_of_an_activity_recalculates_both_officers(self):
        calculation.recalculate_all()
        activity = Activity.objects.get(contact_name="María Pérez")
        new_author = self.officer("F-1004")  # mismo cargo: la meta del cargo cuenta para él
        with self.captureOnCommitCallbacks(execute=True):
            activity.author_officer = new_author
            activity.save()
        self.assertEqual(self.latest().progress, Decimal(0))

    def test_archiving_an_activity_recalculates(self):
        calculation.recalculate_all()
        activity = Activity.objects.get(contact_name="María Pérez")
        with self.captureOnCommitCallbacks(execute=True):
            activity.deleted_at = timezone.now()
            activity.save()
        self.assertEqual(self.latest().progress, Decimal(0))

    def test_moving_an_activity_to_another_date_recalculates(self):
        calculation.recalculate_all()
        activity = Activity.objects.get(contact_name="María Pérez")
        with self.captureOnCommitCallbacks(execute=True):
            activity.date = self.period.end_date + timedelta(days=5)
            activity.save()
        self.assertEqual(self.latest().progress, Decimal(0))

    def test_changing_the_target_of_a_goal_recalculates(self):
        calculation.recalculate_all()
        goal = Goal.objects.get(pk=self.goal.pk)
        with self.captureOnCommitCallbacks(execute=True):
            goal.target_value = 4
            goal.save()
        self.assertEqual(self.latest().compliance, Decimal("25.00"))

    def test_a_new_goal_is_calculated_when_it_is_created(self):
        item = Item.objects.get(name="Coordinación Territorial")
        with self.captureOnCommitCallbacks(execute=True):
            goal = Goal.objects.create(
                item=item, officer=self.cavieres, period=self.period, target_value=2, unit="x", weight=10
            )
        self.assertEqual(self.latest(goal).progress, Decimal(0))

    def test_closing_nothing_is_calculated_for_a_closed_period(self):
        Period.objects.filter(pk=self.period.pk).update(status=Period.Status.CLOSED)
        activity = self.approved_activity(status=Evidence.ReviewStatus.PENDING)
        with self.captureOnCommitCallbacks(execute=True):
            evidence = Evidence.objects.get(activity=activity)
            evidence.review_status = Evidence.ReviewStatus.APPROVED
            evidence.save()
        self.assertFalse(Indicator.objects.filter(officer__isnull=False).exists())

    def test_the_automatic_recalculation_can_be_suspended(self):
        self.assertFalse(is_suspended())
        activity = self.approved_activity(status=Evidence.ReviewStatus.PENDING)
        evidence = Evidence.objects.get(activity=activity)
        with suspended():
            self.assertTrue(is_suspended())
            with suspended():
                self.assertTrue(is_suspended())
            self.assertTrue(is_suspended())
            with self.captureOnCommitCallbacks(execute=True):
                evidence.review_status = Evidence.ReviewStatus.APPROVED
                evidence.save()
        self.assertFalse(is_suspended())
        self.assertFalse(Indicator.objects.filter(officer__isnull=False).exists())

    def test_loading_the_test_data_calculates_nothing_by_itself(self):
        self.assertFalse(Indicator.objects.filter(officer__isnull=False).exists())
        self.assertEqual(Indicator.objects.filter(officer__isnull=True).count(), 3)


class IndicatorIndexTests(CalculationBase):

    def test_without_an_own_indicator_the_general_one_is_used(self):
        index = IndicatorIndex([self.goal.pk])
        general = Indicator.objects.get(goal=self.goal, officer__isnull=True)
        self.assertEqual(index.of(self.goal, self.cavieres), general)
        self.assertEqual(index.of(self.goal), general)

    def test_the_own_indicator_wins_when_it_is_newer(self):
        calculation.recalculate_goal(self.goal)
        index = IndicatorIndex([self.goal.pk])
        own = index.of(self.goal, self.cavieres)
        self.assertEqual(own.officer, self.cavieres)
        self.assertEqual(own.progress, Decimal(1))

    def test_a_goal_without_indicators_has_none(self):
        item = Item.objects.get(name="Coordinación Territorial")
        goal = Goal.objects.create(item=item, officer=self.cavieres, period=self.period, target_value=2, unit="x", weight=1)
        self.assertIsNone(IndicatorIndex([goal.pk]).of(goal, self.cavieres))

    def test_the_effective_list_does_not_repeat_the_general_row_of_a_calculated_goal(self):
        calculation.recalculate_goal(self.goal)
        effective = IndicatorIndex([self.goal.pk]).effective()
        self.assertEqual(len(effective), 1)
        self.assertEqual(effective[0].officer, self.cavieres)

    def test_the_effective_list_keeps_the_general_row_of_a_goal_not_calculated_yet(self):
        effective = IndicatorIndex([self.goal.pk]).effective()
        self.assertEqual(len(effective), 1)
        self.assertIsNone(effective[0].officer)

    def test_only_the_latest_row_per_officer_is_kept(self):
        calculation.recalculate_goal(self.goal)
        self.approved_activity()
        calculation.recalculate_goal(self.goal)
        index = IndicatorIndex([self.goal.pk])
        self.assertEqual(index.of(self.goal, self.cavieres).progress, Decimal(2))
        self.assertEqual(len([row for row in index.effective() if row.goal_id == self.goal.pk]), 1)


class RecalculateScreenTests(CalculationBase):

    def board_url(self):
        return reverse("core:delegation_board")

    def test_the_super_user_recalculates_a_period_from_the_board(self):
        self.login_as("admin")
        response = self.client.post(reverse("core:recalculate_indicators"), {"periodo": self.period.pk})
        self.assertEqual(response.status_code, 302)
        self.assertIn(f"periodo={self.period.pk}", response["Location"])
        self.assertTrue(Indicator.objects.filter(officer__isnull=False).exists())
        entry = AuditLog.objects.filter(event="Indicadores recalculados").latest("pk")
        self.assertIn("nuevo", entry.new_value)

    def test_recalculating_twice_says_everything_is_up_to_date(self):
        self.login_as("admin")
        self.client.post(reverse("core:recalculate_indicators"), {"periodo": self.period.pk})
        response = self.client.post(reverse("core:recalculate_indicators"), {"periodo": self.period.pk}, follow=True)
        self.assertContains(response, "ya estaban al día")

    def test_it_only_accepts_post(self):
        self.login_as("admin")
        self.assertEqual(self.client.get(reverse("core:recalculate_indicators")).status_code, 405)

    def test_users_without_the_permission_cannot_recalculate(self):
        for username in ("consulta1", "jefatura1", "matias.cavieres"):
            with self.subTest(username=username):
                self.login_as(username)
                response = self.client.post(reverse("core:recalculate_indicators"), {"periodo": self.period.pk})
                self.assertEqual(response.status_code, 403)
        self.assertFalse(Indicator.objects.filter(officer__isnull=False).exists())

    def test_a_closed_period_says_it_does_not_change(self):
        Period.objects.filter(pk=self.period.pk).update(status=Period.Status.CLOSED)
        self.login_as("admin")
        response = self.client.post(reverse("core:recalculate_indicators"), {"periodo": self.period.pk}, follow=True)
        self.assertContains(response, "está cerrado")
        self.assertFalse(Indicator.objects.filter(officer__isnull=False).exists())

    def test_a_missing_period_asks_to_choose_one(self):
        self.login_as("admin")
        response = self.client.post(reverse("core:recalculate_indicators"), {"periodo": "999999"}, follow=True)
        self.assertContains(response, "Elige un período")

    def test_the_board_shows_the_recalculate_button_only_to_who_can_use_it(self):
        self.login_as("admin")
        self.assertContains(self.client.get(self.board_url(), {"delegacion": self.north.pk}), "Recalcular indicadores")
        self.login_as("jefatura1")
        self.assertNotContains(self.client.get(self.board_url()), "Recalcular indicadores")

    def test_the_board_shows_the_weight_columns_after_recalculating(self):
        calculation.recalculate_all()
        self.login_as("admin")
        response = self.client.get(self.board_url(), {"delegacion": self.north.pk})
        self.assertContains(response, "Ponderador")
        self.assertContains(response, "Ponderado")
        lines = [line for result in response.context["results"] for line in result["lines"]]
        mine = [line for line in lines if line["goal"].pk == self.goal.pk]
        self.assertEqual(mine[0]["indicator"].officer, self.cavieres)
        self.assertEqual(mine[0]["weighted"], Decimal("5.00"))


class WeightRuleTests(CalculationBase):
    """RF-006: los ponderadores de cada funcionario en un período deben sumar 100 %."""

    def test_the_states_of_the_sum(self):
        self.assertEqual(weights_state(Decimal(100)), "ok")
        self.assertEqual(weights_state(Decimal("99.99")), "under")
        self.assertEqual(weights_state(Decimal("100.01")), "over")
        self.assertEqual(weights_state(None), "")

    def test_the_sum_adds_personal_and_position_goals(self):
        self.assertEqual(officer_weights(self.period, self.cavieres), Decimal("180.00"))
        self.assertEqual(officer_weights(self.period, self.officer("F-1002")), None)

    def test_an_officer_without_goals_has_no_sum(self):
        summary = officer_summary(self.officer("F-1003"), self.period, [], IndicatorIndex([]))
        self.assertIsNone(summary["weights_total"])
        self.assertEqual(summary["weights_state"], "")
        self.assertEqual(summary["goal_total"], 0)

    def test_the_problems_of_a_goal_list_the_affected_officers(self):
        problems = {officer.pk: (total, state) for officer, total, state in weight_problems(self.goal)}
        self.assertEqual(problems, {self.cavieres.pk: (Decimal("180.00"), "over")})
        cargo = weight_problems(self.cargo_goal)
        self.assertEqual(len(cargo), 4)
        self.assertTrue(all(state in ("over", "under") for _, _, state in cargo))

    def test_no_problem_when_the_weights_add_up(self):
        Goal.objects.filter(pk=self.goal.pk).update(weight=20)
        self.assertEqual(Decimal("100.00"), officer_weights(self.period, self.cavieres))
        self.assertEqual(weight_problems(Goal.objects.get(pk=self.goal.pk)), [])

    def goal_data(self, **changes):
        data = {
            "item": Item.objects.get(name="Coordinación Territorial").pk,
            "period": self.period.pk,
            "officer": self.officer("F-1002").pk,
            "position": "",
            "target_value": "20",
            "unit": "visitas",
            "weight": "50",
            "version": "1",
        }
        data.update(changes)
        return data

    def test_saving_a_goal_that_leaves_the_sum_under_100_warns_but_saves(self):
        self.login_as("admin")
        response = self.client.post(reverse("core:metas_create"), self.goal_data(), follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Goal.objects.filter(officer=self.officer("F-1002"), weight=50).exists())
        self.assertContains(response, "no llegan a 100 %")

    def test_saving_a_goal_that_passes_100_warns(self):
        self.login_as("admin")
        response = self.client.post(
            reverse("core:metas_create"), self.goal_data(officer=self.cavieres.pk, weight="30"), follow=True
        )
        self.assertContains(response, "superan 100 %")

    def test_saving_a_goal_that_completes_100_does_not_warn(self):
        self.login_as("admin")
        response = self.client.post(reverse("core:metas_create"), self.goal_data(weight="100"), follow=True)
        self.assertNotContains(response, "deben sumar 100 %.")
        self.assertNotContains(response, "no llegan a")
        self.assertNotContains(response, "superan 100")

    def test_the_goal_form_explains_the_rule(self):
        self.login_as("admin")
        self.assertContains(self.client.get(reverse("core:metas_create")), "deben sumar 100 %")

    def test_the_goal_detail_shows_the_sum_of_the_officer(self):
        self.login_as("admin")
        personal = self.client.get(reverse("core:metas_detail", args=[self.goal.pk]))
        self.assertContains(personal, "Suma de ponderadores del funcionario")
        self.assertContains(personal, "180")
        cargo = self.client.get(reverse("core:metas_detail", args=[self.cargo_goal.pk]))
        self.assertContains(cargo, "Ponderadores de los funcionarios del cargo")
        self.assertContains(cargo, "no suman 100 %")


class OfficerSheetTests(CalculationBase):
    """RF-008: ficha del funcionario con sus metas, cumplimiento y total ponderado."""

    def sheet(self, officer, **query):
        self.login_as("admin")
        return self.client.get(reverse("core:funcionarios_detail", args=[officer.pk]), query)

    def test_the_detail_has_the_sheet_with_goals_and_weights(self):
        calculation.recalculate_all()
        response = self.sheet(self.cavieres)
        self.assertContains(response, "Ficha del período")
        self.assertContains(response, "Total ponderado")
        self.assertContains(response, "Suma de ponderadores")
        sheet = response.context["panel"]["sheet"]
        self.assertEqual(sheet["goal_total"], 2)
        self.assertEqual({line["goal"].pk for line in sheet["lines"]}, {self.goal.pk, self.cargo_goal.pk})
        self.assertEqual(sheet["weights_total"], Decimal("180.00"))
        self.assertEqual(sheet["weights_state"], "over")

    def test_the_weighted_total_adds_the_weighted_values(self):
        calculation.recalculate_all()
        sheet = self.sheet(self.cavieres).context["panel"]["sheet"]
        self.assertEqual(sheet["weighted_total"], sum(line["weighted"] for line in sheet["lines"]))
        self.assertEqual(sheet["average"], Decimal("2.5"))  # (5 % + 0 %) / 2

    def test_an_officer_without_goals_says_so(self):
        response = self.sheet(self.officer("F-1003"))
        self.assertContains(response, "no tiene metas en este período")

    def test_the_period_can_be_chosen(self):
        previous = Period.objects.get(status=Period.Status.CLOSED)
        response = self.sheet(self.cavieres, periodo=previous.pk)
        self.assertEqual(response.context["panel"]["period"], previous)
        self.assertContains(response, "no tiene metas en este período")

    def test_the_sheet_shows_the_recent_activity(self):
        response = self.sheet(self.cavieres)
        recent = response.context["panel"]["recent"]
        self.assertGreaterEqual(recent.total, 2)
        self.assertContains(response, "Registros del período")

    def test_a_scoped_user_cannot_open_the_sheet_of_another_delegation(self):
        self.login_as("jefatura1")
        self.assertEqual(
            self.client.get(reverse("core:funcionarios_detail", args=[self.officer("F-2001").pk])).status_code, 404
        )


class RecentActivityTests(CalculationBase):
    """RF-030: último ingreso, días sin ingreso, registros del período y promedio diario por funcionario."""

    TODAY = date(2026, 6, 10)

    def activity_of(self, officer, when, **extra):
        return Activity.objects.create(
            date=when, item=self.visit, delegation=officer.delegation, author_officer=officer, **extra
        )

    def pace(self):
        return pace_of(self.period, today=self.TODAY)

    def test_the_last_date_the_days_without_and_the_total_come_from_the_activities(self):
        officer = self.officer("F-1006")
        for when in (date(2026, 6, 8), date(2026, 6, 1), date(2026, 5, 20)):
            self.activity_of(officer, when)
        recent = recent_activity([officer.pk], self.period, self.pace(), self.TODAY)[officer.pk]
        self.assertEqual(recent.last_date, date(2026, 6, 8))
        self.assertEqual(recent.days_without, 2)
        self.assertEqual(recent.total, 3)
        self.assertFalse(recent.alert)

    def test_future_archived_and_other_period_activities_are_not_counted(self):
        officer = self.officer("F-1006")
        self.activity_of(officer, date(2026, 6, 8))
        self.activity_of(officer, date(2026, 7, 1))  # futura
        archived = self.activity_of(officer, date(2026, 6, 9))
        Activity.objects.filter(pk=archived.pk).update(deleted_at=timezone.now())
        self.activity_of(officer, date(2025, 12, 31))  # período anterior
        recent = recent_activity([officer.pk], self.period, self.pace(), self.TODAY)[officer.pk]
        self.assertEqual((recent.last_date, recent.total), (date(2026, 6, 8), 1))

    def test_an_officer_without_activities_is_listed_in_alert(self):
        officer = self.officer("F-1006")
        recent = recent_activity([officer.pk], self.period, self.pace(), self.TODAY)[officer.pk]
        self.assertEqual((recent.last_date, recent.days_without, recent.total), (None, None, 0))
        self.assertTrue(recent.alert)

    def test_the_alert_starts_after_the_limit_of_days(self):
        self.assertEqual(ALERT_DAYS, 7)
        self.assertFalse(Recent(self.TODAY, 7, 1, Decimal(1)).alert)
        self.assertTrue(Recent(self.TODAY, 8, 1, Decimal(1)).alert)
        self.assertFalse(Recent(self.TODAY, 0, 1, Decimal(1)).alert)

    def test_the_daily_average_divides_by_the_computable_days_elapsed(self):
        officer = self.officer("F-1006")
        for day in range(3):
            self.activity_of(officer, date(2026, 6, 1) + timedelta(days=day))
        pace = self.pace()
        recent = recent_activity([officer.pk], self.period, pace, self.TODAY)[officer.pk]
        self.assertEqual(recent.daily_average, daily_average(3, pace.elapsed_days))
        self.assertEqual(daily_average(3, 10), Decimal("0.30"))
        self.assertEqual(daily_average(1, 3), Decimal("0.33"))
        self.assertEqual(daily_average(0, 5), Decimal("0.00"))
        self.assertIsNone(daily_average(3, 0))
        self.assertIsNone(daily_average(3, None))

    def test_many_officers_are_answered_at_once(self):
        ids = [self.officer("F-1001").pk, self.officer("F-1006").pk]
        found = recent_activity(ids, self.period, None, self.TODAY)
        self.assertEqual(set(found), set(ids))
        self.assertIsNone(found[ids[1]].daily_average)

    def test_a_delegation_summary_adds_the_officers(self):
        first, second = self.officer("F-1006"), self.officer("F-1003")
        self.activity_of(first, date(2026, 6, 8))
        self.activity_of(second, date(2026, 6, 5))
        self.activity_of(second, date(2026, 6, 4))
        pace = self.pace()
        recent = recent_activity([first.pk, second.pk], self.period, pace, self.TODAY)
        summary = delegation_recent(recent, pace, self.TODAY)
        self.assertEqual((summary.last_date, summary.days_without, summary.total), (date(2026, 6, 8), 2, 3))
        self.assertEqual(summary.daily_average, daily_average(3, pace.elapsed_days))
        empty = delegation_recent({}, pace, self.TODAY)
        self.assertEqual((empty.last_date, empty.days_without, empty.total), (None, None, 0))

    def test_the_board_shows_the_recent_activity_panel(self):
        self.login_as("admin")
        response = self.client.get(reverse("core:delegation_board"), {"delegacion": self.north.pk})
        self.assertContains(response, "Actividad reciente")
        self.assertContains(response, "Días sin ingreso")
        rows = response.context["results"]
        self.assertTrue(all("recent" in row for row in rows))
        summary = response.context["recent_summary"]
        self.assertEqual(summary.total, sum(row["recent"].total for row in rows))

    def test_the_officer_results_screen_shows_it(self):
        self.login_as("matias.cavieres")
        response = self.client.get(reverse("core:dashboard"))
        recent = response.context["personal"]["recent"]
        self.assertGreaterEqual(recent.total, 2)
        self.assertContains(response, "Último ingreso")


class DeadlineTests(SimpleTestCase):
    """RF-019: vencidos, por vencer y fuera de plazo."""

    TODAY = date(2026, 10, 20)
    OPEN = Commitment.Status.IN_PROGRESS
    DONE = Commitment.Status.FULFILLED

    def test_an_open_commitment_past_its_date_is_overdue(self):
        self.assertEqual(deadline_state(self.TODAY - timedelta(days=1), self.OPEN, self.TODAY), "overdue")
        self.assertEqual(deadline_state(self.TODAY - timedelta(days=90), Commitment.Status.PENDING, self.TODAY), "overdue")

    def test_it_is_due_soon_from_today_up_to_the_limit(self):
        self.assertEqual(DUE_SOON_DAYS, 7)
        self.assertEqual(deadline_state(self.TODAY, self.OPEN, self.TODAY), "due_soon")
        self.assertEqual(deadline_state(self.TODAY + timedelta(days=7), self.OPEN, self.TODAY), "due_soon")

    def test_after_the_limit_it_is_on_time(self):
        self.assertEqual(deadline_state(self.TODAY + timedelta(days=8), self.OPEN, self.TODAY), "on_time")

    def test_a_fulfilled_commitment_is_judged_by_the_day_it_was_done(self):
        due = self.TODAY
        self.assertEqual(deadline_state(due, self.DONE, self.TODAY, done_on=due), "done_on_time")
        self.assertEqual(deadline_state(due, self.DONE, self.TODAY, done_on=due - timedelta(days=3)), "done_on_time")
        self.assertEqual(deadline_state(due, self.DONE, self.TODAY, done_on=due + timedelta(days=1)), "done_late")
        self.assertEqual(deadline_state(due, self.DONE, self.TODAY), "done_on_time")

    def test_a_fulfilled_commitment_is_never_overdue(self):
        long_ago = self.TODAY - timedelta(days=200)
        self.assertEqual(deadline_state(long_ago, self.DONE, self.TODAY, done_on=long_ago), "done_on_time")

    def commitment(self, days, status=None):
        return SimpleNamespace(pk=0, due_date=self.TODAY + timedelta(days=days), status=status or self.OPEN)

    def test_the_sentences_for_the_detail(self):
        self.assertIn("Vencido hace 1 día (era para el", deadline_text(self.commitment(-1), self.TODAY))
        self.assertIn("Vencido hace 5 días", deadline_text(self.commitment(-5), self.TODAY))
        self.assertIn("Vence hoy", deadline_text(self.commitment(0), self.TODAY))
        self.assertIn("Vence en 1 día (", deadline_text(self.commitment(1), self.TODAY))
        self.assertIn("Vence en 3 días", deadline_text(self.commitment(3), self.TODAY))
        far = deadline_text(self.commitment(30), self.TODAY)
        self.assertTrue(far.startswith("En plazo: vence en 30 días"))

    def test_the_tones_of_the_five_states_exist(self):
        for state in ("overdue", "due_soon", "on_time", "done_on_time", "done_late"):
            with self.subTest(state=state):
                tone = ui.tone_for(state)
                self.assertTrue(tone[0])


class DeadlineScreensTests(PortalTestCase):

    def setUp(self):
        self.today = timezone.localdate()
        self.admin_officer = self.officer("F-1001")

    def make(self, days, status=Commitment.Status.IN_PROGRESS, officer=None, label="x"):
        officer = officer or self.admin_officer
        return Commitment.objects.create(
            requester=f"Plazo {label}",
            territory=officer.delegation.territories.first(),
            due_date=self.today + timedelta(days=days),
            request_date=self.today - timedelta(days=30),
            status=status,
            responsible_officer=officer,
            delegation=officer.delegation,
        )

    def test_the_list_has_a_deadline_column_with_the_label(self):
        self.make(-3, label="vencido")
        self.make(2, label="porvencer")
        self.login_as("admin")
        response = self.client.get(reverse("core:agenda_list"))
        self.assertContains(response, "Plazo")
        self.assertContains(response, "Vencido")
        self.assertContains(response, "Por vencer")

    def test_the_detail_explains_the_deadline(self):
        overdue = self.make(-4)
        self.login_as("admin")
        response = self.client.get(reverse("core:agenda_detail", args=[overdue.pk]))
        self.assertContains(response, "Detalle del plazo")
        self.assertContains(response, "Vencido hace 4 días")

    def test_a_commitment_fulfilled_after_its_date_is_out_of_term(self):
        late = self.make(-2, status=Commitment.Status.SUBMITTED, label="tarde")
        self.login_as("admin")
        data = {
            "requester": late.requester,
            "requester_type": late.requester_type,
            "source": "",
            "request_date": late.request_date.isoformat(),
            "description": "",
            "territory": late.territory_id,
            "due_date": late.due_date.isoformat(),
            "support": "",
            "status": Commitment.Status.FULFILLED,
            "notes": "",
            "responsible_officer": late.responsible_officer_id,
            "delegation": late.delegation_id,
        }
        response = self.client.post(reverse("core:agenda_update", args=[late.pk]), data)
        self.assertEqual(response.status_code, 302)
        late.refresh_from_db()
        detail = self.client.get(reverse("core:agenda_detail", args=[late.pk]))
        self.assertContains(detail, "después de la fecha comprometida")
        counts = deadline_counts(Commitment.objects.filter(pk=late.pk), self.today)
        self.assertEqual(counts[self.admin_officer.pk]["done_late"], 1)

    def test_a_commitment_fulfilled_on_time_is_not_late(self):
        counts = deadline_counts(
            Commitment.objects.filter(pk=self.make(5, status=Commitment.Status.FULFILLED).pk), self.today
        )
        self.assertEqual(counts[self.admin_officer.pk]["done_on_time"], 1)
        self.assertEqual(counts[self.admin_officer.pk].get("done_late", 0), 0)

    def test_the_summary_counts_overdue_due_soon_and_late(self):
        before, _ = collective_summary(
            Commitment.objects.filter(responsible_officer=self.admin_officer), [self.admin_officer], self.today
        )
        self.make(-5, label="a")
        self.make(-1, label="b")
        self.make(3, label="c")
        rows, total = collective_summary(
            Commitment.objects.filter(responsible_officer=self.admin_officer), [self.admin_officer], self.today
        )
        self.assertEqual(rows[0]["overdue"], before[0]["overdue"] + 2)
        self.assertEqual(rows[0]["due_soon"], before[0]["due_soon"] + 1)
        self.assertEqual(total["overdue"], rows[0]["overdue"])

    def test_the_summary_screen_shows_the_new_columns(self):
        self.make(-5)
        self.login_as("admin")
        response = self.client.get(reverse("core:commitment_summary"))
        self.assertContains(response, "Vencidos")
        self.assertContains(response, "Por vencer")
        self.assertContains(response, "Fuera de plazo")
        self.assertContains(response, f"{DUE_SOON_DAYS} días")

    def test_the_dashboard_open_commitments_mention_those_due_soon(self):
        self.make(2)
        self.login_as("admin")
        response = self.client.get(reverse("core:dashboard"))
        self.assertContains(response, "por vencer")


class PersonalDashboardTests(PortalTestCase):
    """RF-028: panel personal del funcionario y período elegible en el inicio."""

    def test_the_personal_panel_has_evidence_commitments_and_activity(self):
        self.login_as("matias.cavieres")
        response = self.client.get(reverse("core:dashboard"))
        personal = response.context["personal"]
        self.assertContains(response, "Mis evidencias, compromisos y actividad")
        self.assertEqual(
            [item["label"] for item in personal["evidence"]], ["Pendiente", "Aprobada", "Rechazada"]
        )
        self.assertEqual(
            [item["label"] for item in personal["commitments"]], ["Ingresado", "Pendiente", "En proceso", "Realizado"]
        )

    def test_the_evidence_counts_belong_to_the_officer(self):
        self.login_as("matias.cavieres")
        personal = self.client.get(reverse("core:dashboard")).context["personal"]
        mine = Evidence.objects.filter(author_officer=self.officer("F-1001"), deleted_at__isnull=True)
        self.assertEqual(sum(item["total"] for item in personal["evidence"]), mine.count())

    def test_the_commitment_counts_belong_to_the_officer(self):
        self.login_as("matias.cavieres")
        personal = self.client.get(reverse("core:dashboard")).context["personal"]
        mine = Commitment.objects.filter(responsible_officer=self.officer("F-1001"), deleted_at__isnull=True)
        self.assertEqual(sum(item["total"] for item in personal["commitments"]), mine.count())
        self.assertEqual(personal["commitments"][3]["total"], 1)  # el realizado de la semilla

    def test_overdue_and_due_soon_are_counted(self):
        officer = self.officer("F-1001")
        today = timezone.localdate()
        for days in (-3, 2):
            Commitment.objects.create(
                requester=f"Personal {days}",
                territory=officer.delegation.territories.first(),
                due_date=today + timedelta(days=days),
                request_date=today - timedelta(days=20),
                status=Commitment.Status.IN_PROGRESS,
                responsible_officer=officer,
                delegation=officer.delegation,
            )
        self.login_as("matias.cavieres")
        personal = self.client.get(reverse("core:dashboard")).context["personal"]
        self.assertEqual((personal["overdue"], personal["due_soon"]), (1, 1))

    def test_a_general_user_has_no_personal_panel(self):
        self.login_as("admin")
        response = self.client.get(reverse("core:dashboard"))
        self.assertNotContains(response, "Mis evidencias, compromisos y actividad")

    def test_the_goal_lines_show_the_weight_and_the_weighted_contribution(self):
        calculation.recalculate_all()
        self.login_as("matias.cavieres")
        response = self.client.get(reverse("core:dashboard"))
        self.assertContains(response, "Ponderador: 100")
        self.assertContains(response, "Aporte ponderado: 5")
        self.assertContains(response, "Total ponderado")
        self.assertEqual(response.context["sheet"]["weights_state"], "over")
        self.assertContains(response, "Ver las actividades")

    def test_the_period_can_be_changed(self):
        previous = Period.objects.get(status=Period.Status.CLOSED)
        self.login_as("matias.cavieres")
        response = self.client.get(reverse("core:dashboard"))
        self.assertContains(response, "Ver período")
        other = self.client.get(reverse("core:dashboard"), {"periodo": previous.pk})
        self.assertEqual(other.context["period"], previous)
        self.assertEqual(other.context["goal_lines"], [])
        self.assertContains(other, "Todavía no tienes metas asignadas")

    def test_the_link_to_the_activities_filters_by_item_and_author(self):
        self.login_as("matias.cavieres")
        response = self.client.get(reverse("core:dashboard"))
        goal = Goal.objects.get(officer=self.officer("F-1001"), item__name="Visita Domiciliaria")
        self.assertContains(response, f"?item={goal.item_id}&amp;author_officer={self.officer('F-1001').pk}")
        listing = self.client.get(
            response.context["activities_url"],
            {"item": goal.item_id, "author_officer": self.officer("F-1001").pk},
            follow=True,
        )
        self.assertContains(listing, "María Pérez")
        self.assertNotContains(listing, "Ana Rojas")


class PositionOverviewTests(CalculationBase):
    """RF-031: vista global por cargos."""

    def url(self):
        return reverse("core:position_overview")

    def test_it_groups_the_officers_by_position(self):
        self.login_as("admin")
        response = self.client.get(self.url(), {"delegacion": self.north.pk})
        groups = {group["position"].name: group for group in response.context["groups"]}
        self.assertEqual(set(groups), {"Encargado Social", "Coordinador de Terreno", "Jefe de Delegación"})
        social = groups["Encargado Social"]
        self.assertEqual({row["officer"].institutional_id for row in social["officers"]}, {"F-1001", "F-1004"})
        self.assertContains(response, "Encargado Social")

    def test_the_global_user_can_see_every_delegation(self):
        self.login_as("admin")
        response = self.client.get(self.url(), {"delegacion": "todas"})
        social = [g for g in response.context["groups"] if g["position"].name == "Encargado Social"][0]
        self.assertEqual(len(social["officers"]), 4)

    def test_the_team_goals_add_up_targets_and_progress(self):
        mine = self.cavieres
        item = self.cargo_goal.item
        self.approved_activity(officer=mine, item=item)
        self.approved_activity(officer=self.officer("F-1004"), item=item)
        calculation.recalculate_all()
        self.login_as("admin")
        response = self.client.get(self.url(), {"delegacion": self.north.pk})
        social = [g for g in response.context["groups"] if g["position"].name == "Encargado Social"][0]
        team = {row["item"].name: row for row in social["team_goals"]}
        row = team["Entrega de Ayudas Sociales"]
        self.assertEqual(row["target"], Decimal(100))
        self.assertEqual(row["progress"], Decimal(2))
        self.assertEqual(row["percent"], Decimal("2.0"))

    def test_each_officer_shows_goals_average_and_last_entry(self):
        calculation.recalculate_all()
        self.login_as("admin")
        response = self.client.get(self.url(), {"delegacion": self.north.pk})
        social = [g for g in response.context["groups"] if g["position"].name == "Encargado Social"][0]
        row = [r for r in social["officers"] if r["officer"] == self.cavieres][0]
        self.assertEqual(row["goal_total"], 2)
        self.assertEqual(row["average"], Decimal("2.5"))
        self.assertIsNotNone(row["recent"].last_date)
        self.assertIsNotNone(social["last_date"])
        self.assertIn(social["light"], ("green", "amber", "red"))

    def test_officers_and_positions_link_to_their_sheets(self):
        self.login_as("admin")
        response = self.client.get(self.url(), {"delegacion": self.north.pk})
        self.assertContains(response, reverse("core:funcionarios_detail", args=[self.cavieres.pk]))
        social = [g for g in response.context["groups"] if g["position"].name == "Encargado Social"][0]
        self.assertContains(response, reverse("core:cargos_detail", args=[social["position"].pk]))

    def test_the_menu_offers_it_to_who_can_read_indicators(self):
        self.login_as("admin")
        self.assertIn("Vista por cargos", self.menu_labels(self.client.get(reverse("core:dashboard"))))
        self.login_as("matias.cavieres")
        self.assertNotIn("Vista por cargos", self.menu_labels(self.client.get(reverse("core:dashboard"))))

    def test_without_the_permission_it_is_forbidden(self):
        self.login_as("matias.cavieres")
        self.assertEqual(self.client.get(self.url()).status_code, 403)

    def test_a_scoped_user_only_sees_the_officers_of_his_delegation(self):
        self.login_as("jefatura1")
        response = self.client.get(self.url(), {"delegacion": self.south.pk})
        shown = {row["officer"].delegation_id for group in response.context["groups"] for row in group["officers"]}
        self.assertLessEqual(shown, {self.north.pk})

    def test_the_period_can_be_chosen(self):
        previous = Period.objects.get(status=Period.Status.CLOSED)
        self.login_as("admin")
        response = self.client.get(self.url(), {"periodo": previous.pk, "delegacion": self.north.pk})
        self.assertEqual(response.context["period"], previous)
        for group in response.context["groups"]:
            self.assertEqual(group["team_goals"], [])

    def test_it_works_without_periods(self):
        from planning.models import Adjustment

        Adjustment.objects.all().delete()
        Indicator.objects.all().delete()
        Goal.objects.all().delete()
        Period.objects.all().delete()
        self.login_as("admin")
        response = self.client.get(self.url())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["groups"], [])


class ConcurrencyTests(PortalTestCase):
    """RF-034 y RNF-003: dos personas editando lo mismo no se pisan sin saberlo."""

    def activity(self):
        return Activity.objects.get(contact_name="María Pérez")

    def open_version(self, activity):
        return self.client.get(reverse("core:actividades_update", args=[activity.pk])).context["version"]

    def post(self, activity, version, **changes):
        return self.client.post(
            reverse("core:actividades_update", args=[activity.pk]),
            self.activity_form_data(activity, _version=version, **changes),
        )

    def test_a_stale_save_changes_nothing_and_names_who_changed_it(self):
        self.login_as("matias.cavieres")
        activity = self.activity()
        opened = self.open_version(activity)
        other = Activity.objects.get(pk=activity.pk)
        other.action_taken = "Cambio ajeno"
        other.save()
        from core.audit import log_event

        log_event(User_for("coordinacion1"), "Registro modificado", other)
        response = self.post(activity, opened, contact_name="Cambio mío")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Otra persona modificó este registro")
        self.assertContains(response, "coordinacion1")
        activity.refresh_from_db()
        self.assertEqual(activity.contact_name, "María Pérez")

    def test_the_message_has_who_when_and_what(self):
        activity = self.activity()
        from core.audit import log_event

        log_event(User_for("coordinacion1"), "Registro modificado", activity, previous="a", new="b")
        text = conflict_message(activity)
        self.assertIn("coordinacion1", text)
        self.assertIn("Registro modificado", text)
        self.assertTrue(last_change_text(activity).startswith(": "))

    def test_without_history_the_message_still_reads_well(self):
        activity = self.activity()
        AuditLog.objects.filter(affected_entity="Activity", record_id=activity.pk).delete()
        self.assertEqual(last_change_text(activity), "")
        self.assertIn("Otra persona modificó este registro mientras lo editabas.", conflict_message(activity))

    def test_the_second_attempt_with_the_new_version_saves(self):
        self.login_as("matias.cavieres")
        activity = self.activity()
        opened = self.open_version(activity)
        other = Activity.objects.get(pk=activity.pk)
        other.action_taken = "Cambio ajeno"
        other.save()
        stale = self.post(activity, opened, contact_name="Cambio mío")
        retry = self.post(activity, stale.context["version"], contact_name="Cambio mío")
        self.assertEqual(retry.status_code, 302)
        activity.refresh_from_db()
        self.assertEqual(activity.contact_name, "Cambio mío")

    def test_a_save_with_the_current_version_goes_through(self):
        self.login_as("matias.cavieres")
        activity = self.activity()
        response = self.post(activity, self.open_version(activity), contact_name="Sin choque")
        self.assertEqual(response.status_code, 302)
        activity.refresh_from_db()
        self.assertEqual(activity.contact_name, "Sin choque")

    def test_the_row_is_checked_again_inside_the_transaction(self):
        """Aunque el formulario llegue con la versión que cargó la vista, se compara con la fila bloqueada."""
        from core import crud as crud_module

        self.login_as("matias.cavieres")
        activity = self.activity()
        opened = self.open_version(activity)
        original = crud_module.CrudFormView.save

        def sneaky(view, request, form, creating, opened=""):
            Activity.objects.filter(pk=activity.pk).update(action_taken="Cambio en el último instante")
            Activity.objects.get(pk=activity.pk).save()
            return original(view, request, form, creating, opened)

        crud_module.CrudFormView.save = sneaky
        try:
            response = self.post(activity, opened, contact_name="Cambio mío")
        finally:
            crud_module.CrudFormView.save = original
        self.assertEqual(response.status_code, 200)
        activity.refresh_from_db()
        self.assertEqual(activity.contact_name, "María Pérez")

    def test_a_duplicate_found_when_saving_is_reported_not_a_server_error(self):
        self.login_as("admin")
        data = {"name": "Encargado Social", "description": "", "version": "1"}
        response = self.client.post(reverse("core:cargos_create"), data)
        self.assertIn(response.status_code, (200, 302))
        self.assertNotEqual(response.status_code, 500)

    def test_the_validation_form_carries_the_version(self):
        self.login_as("matias.cavieres")
        evidence = Evidence.objects.get(unique_code="EVD-NORTE-0001")
        response = self.client.get(reverse("core:validate_evidence", args=[evidence.pk]))
        self.assertContains(response, 'name="_version"')
        self.assertEqual(response.context["version"], evidence.updated_at.isoformat())

    def test_two_reviewers_cannot_validate_the_same_evidence_without_noticing(self):
        self.login_as("matias.cavieres")
        evidence = Evidence.objects.get(unique_code="EVD-NORTE-0001")
        url = reverse("core:validate_evidence", args=[evidence.pk])
        opened = self.client.get(url).context["version"]
        other = Evidence.objects.get(pk=evidence.pk)
        other.metadata = "Otra revisión en curso"
        other.save()
        response = self.client.post(
            url, {"decision": "approved", "result": "Conforme", "notes": "", "_version": opened}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Otra persona modificó este registro")
        evidence.refresh_from_db()
        self.assertEqual(evidence.review_status, Evidence.ReviewStatus.PENDING)
        self.assertFalse(evidence.validations.exists() if hasattr(evidence, "validations") else False)

    def test_the_validation_goes_through_after_reloading(self):
        self.login_as("matias.cavieres")
        evidence = Evidence.objects.get(unique_code="EVD-NORTE-0001")
        url = reverse("core:validate_evidence", args=[evidence.pk])
        opened = self.client.get(url).context["version"]
        other = Evidence.objects.get(pk=evidence.pk)
        other.metadata = "Otra revisión en curso"
        other.save()
        stale = self.client.post(url, {"decision": "approved", "result": "Conforme", "notes": "", "_version": opened})
        retry = self.client.post(
            url, {"decision": "approved", "result": "Conforme", "notes": "", "_version": stale.context["version"]}
        )
        self.assertEqual(retry.status_code, 302)
        evidence.refresh_from_db()
        self.assertEqual(evidence.review_status, Evidence.ReviewStatus.APPROVED)

    def test_the_integrity_error_type_is_the_one_the_views_catch(self):
        self.assertTrue(issubclass(IntegrityError, Exception))
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Evidence.objects.create(
                    unique_code="EVD-NORTE-0001",
                    file_link="evidencias/x.pdf",
                    activity=self.activity(),
                    author_officer=self.officer("F-1002"),
                )


def User_for(username):
    from django.contrib.auth.models import User

    return User.objects.get(username=username)
