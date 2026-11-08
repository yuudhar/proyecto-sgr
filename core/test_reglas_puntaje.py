"""Versión 29: gestiones que no puntúan, tope de 120 %, límite diario y listas para números de pocas opciones."""
import importlib
from datetime import timedelta
from decimal import Decimal

from django.apps import apps
from django.core.exceptions import ValidationError
from django.test import override_settings
from django.urls import reverse

from core.forms import CrudForm
from core.results import officer_summary
from core.test_results_and_calculation import CalculationBase
from core.testing import PortalTestCase, portal_today
from evidence.models import Evidence
from operations.models import Activity, Followup
from organization.models import Beneficiary, Item
from planning import calculation
from planning.calculation import IndicatorIndex
from planning.models import Goal, Period

PHONE = "+56912345678"


class PointsBase(CalculationBase):
    """Como CalculationBase, pero cada actividad trae nombre y teléfono (si no, no puntúa) y se puede pedir otra cosa."""

    def scoring_activity(self, officer=None, item=None, **changes):
        officer = officer or self.cavieres
        self.counter += 1
        values = {
            "date": self.period.start_date + timedelta(days=30),
            "item": item or self.visit,
            "contact_name": f"Contacto {self.counter}",
            "phone": PHONE,
            "delegation": officer.delegation,
            "author_officer": officer,
        }
        values.update(changes)
        activity = Activity.objects.create(**values)
        Evidence.objects.create(
            unique_code=f"EVD-T29-{activity.pk}",
            file_link="evidencias/prueba.pdf",
            review_status=Evidence.ReviewStatus.APPROVED,
            activity=activity,
            author_officer=self.officer("F-1002"),
        )
        return activity


class ScoringRulesTests(PointsBase):
    """RF-039, RF-040 y RF-043: qué gestiones no puntúan."""

    def test_an_activity_asked_by_the_delegate_is_other_management_and_does_not_score(self):
        before = self.progress()
        activity = self.scoring_activity(requester_is_delegate=True)
        self.assertFalse(activity.counts_for_score)
        self.assertEqual(activity.no_score_reason, Activity.REASON_DELEGATE)
        self.assertEqual(self.progress(), before)
        self.scoring_activity()
        self.assertEqual(self.progress(), before + 1)

    def test_an_activity_without_the_phone_of_the_user_does_not_score(self):
        before = self.progress()
        activity = self.scoring_activity(phone="")
        self.assertFalse(activity.counts_for_score)
        self.assertEqual(activity.no_score_reason, Activity.REASON_NO_CONTACT)
        self.assertEqual(self.progress(), before)

    def test_an_activity_without_the_name_of_the_user_does_not_score(self):
        activity = self.scoring_activity(contact_name="")
        self.assertFalse(activity.counts_for_score)
        self.assertEqual(activity.no_score_reason, Activity.REASON_NO_CONTACT)

    def test_the_name_and_phone_of_the_linked_person_count(self):
        person = Beneficiary.objects.create(rut="12.345.678-5", name="Rosa Vecina", phone=PHONE)
        activity = self.scoring_activity(contact_name="", phone="", beneficiary=person)
        self.assertTrue(activity.counts_for_score)
        self.assertEqual(activity.no_score_reason, "")

    def test_completing_the_data_makes_it_score(self):
        before = self.progress()
        activity = self.scoring_activity(phone="")
        self.assertEqual(self.progress(), before)
        activity.phone = PHONE
        activity.save()
        self.assertTrue(Activity.objects.get(pk=activity.pk).counts_for_score)
        self.assertEqual(self.progress(), before + 1)

    def switch(self, item, value):
        item.scores = value
        with self.captureOnCommitCallbacks(execute=True):
            item.save()

    def test_an_item_that_does_not_give_points_makes_its_activities_not_score(self):
        self.scoring_activity()
        self.assertGreaterEqual(self.progress(), 2)
        self.switch(self.visit, False)
        self.assertEqual(self.progress(), 0)
        activities = Activity.objects.filter(item=self.visit)
        self.assertTrue(activities.exists())
        self.assertFalse(activities.filter(counts_for_score=True).exists())
        self.assertEqual({each.no_score_reason for each in activities}, {Activity.REASON_ITEM})

    def test_turning_the_item_back_on_gives_the_points_back(self):
        before = self.progress()
        self.scoring_activity()
        self.switch(self.visit, False)
        self.switch(self.visit, True)
        self.assertEqual(self.progress(), before + 1)

    def test_a_sub_attention_follows_the_type_it_belongs_to(self):
        parent = Item.objects.create(name="Tipo de prueba", calculation_type=self.visit.calculation_type)
        child = Item.objects.create(name="Sub de prueba", calculation_type=self.visit.calculation_type, parent_item=parent)
        activity = self.scoring_activity(item=child)
        self.assertTrue(activity.counts_for_score)
        self.switch(parent, False)
        activity = Activity.objects.get(pk=activity.pk)
        self.assertFalse(activity.counts_for_score)
        self.assertEqual(activity.no_score_reason, Activity.REASON_ITEM)

    def test_every_item_gives_points_until_the_client_says_otherwise(self):
        self.assertFalse(Item.objects.filter(scores=False).exists())


class ScoringScreensTests(PortalTestCase):

    def intake(self, **changes):
        return self.client.post(
            reverse("core:actividades_create"), self.intake_data(phone="+56912345678", **changes)
        )

    def test_the_intake_form_has_the_delegate_checkbox(self):
        self.login_as("matias.cavieres")
        form = self.client.get(reverse("core:actividades_create")).context["form"]
        self.assertIn("requester_is_delegate", form.fields)
        self.assertIn("delegado", form.fields["requester_is_delegate"].label.lower())

    def test_the_checkbox_saves_the_flag_and_the_activity_does_not_score(self):
        self.login_as("matias.cavieres")
        response = self.intake(requester_is_delegate="on")
        self.assertEqual(response.status_code, 302)
        created = Activity.objects.filter(contact_name="Rosa Prueba").latest("pk")
        self.assertTrue(created.requester_is_delegate)
        self.assertFalse(created.counts_for_score)

    def test_a_normal_activity_with_phone_scores(self):
        self.login_as("matias.cavieres")
        self.assertEqual(self.intake().status_code, 302)
        self.assertTrue(Activity.objects.filter(contact_name="Rosa Prueba").latest("pk").counts_for_score)

    def test_the_list_shows_whether_each_attention_scores_and_can_filter_by_it(self):
        self.login_as("admin")
        Activity.objects.filter(contact_name="María Pérez").update(counts_for_score=False, no_score_reason="x")
        page = self.client.get(reverse("core:atencion"))
        self.assertContains(page, "No puntúa")
        self.assertContains(page, "Puntúa")
        only = self.client.get(reverse("core:atencion"), {"counts_for_score": "0"})
        self.assertEqual([row.obj.contact_name for row in only.context["rows"]], ["María Pérez"])
        scoring = self.client.get(reverse("core:atencion"), {"counts_for_score": "1"})
        names = [row.obj.contact_name for row in scoring.context["rows"]]
        self.assertNotIn("María Pérez", names)
        self.assertEqual(len(names), len(page.context["rows"]) - 1)

    def test_the_detail_tells_why_it_does_not_score(self):
        self.login_as("admin")
        activity = self.activity("María Pérez")
        activity.requester_is_delegate = True
        activity.save()
        page = self.client.get(reverse("core:actividades_detail", args=[activity.pk]))
        self.assertContains(page, Activity.REASON_DELEGATE)

    def test_the_item_forms_have_the_gives_points_checkbox(self):
        self.login_as("admin")
        for name in ("core:items_create", "core:tipos_de_atencion_create", "core:sub_atenciones_create"):
            form = self.client.get(reverse(name)).context["form"]
            self.assertIn("scores", form.fields, name)
            self.assertEqual(form.fields["scores"].label.lower(), "otorga punto")


class CapTests(PointsBase):
    """RF-045: tope de 120 % por ítem y panel de ítems con menor puntaje."""

    def reach(self, extra):
        target = int(self.goal.target_value)
        have = int(self.progress())
        for _ in range(target + extra - have):
            self.scoring_activity()
        calculation.recalculate_period(self.period)

    def test_the_default_cap_is_120(self):
        self.assertEqual(Period._meta.get_field("weighted_cap").default, 120)
        self.assertEqual(self.period.weighted_cap, Decimal(120))

    def test_the_compliance_stops_at_120_percent(self):
        self.reach(extra=int(self.goal.target_value))
        result = calculation.compute(self.goal, self.cavieres)
        self.assertEqual(result.compliance, Decimal(120))
        self.assertGreater(result.uncapped, Decimal(120))

    def test_more_activities_do_not_raise_the_weighting_once_the_cap_is_reached(self):
        self.reach(extra=int(self.goal.target_value))
        first = calculation.compute(self.goal, self.cavieres).weighting
        self.scoring_activity()
        self.scoring_activity()
        self.assertEqual(calculation.compute(self.goal, self.cavieres).weighting, first)

    def test_the_migration_lowers_open_periods_and_keeps_the_closed_ones(self):
        migration = importlib.import_module("planning.migrations.0003_reglas_de_puntaje_v29")
        Period.objects.filter(pk=self.period.pk).update(weighted_cap=150, parameters_version="1")
        closed = Period.objects.create(
            start_date=self.period.start_date - timedelta(days=400),
            end_date=self.period.start_date - timedelta(days=300),
            computable_days=70,
            status=Period.Status.CLOSED,
            weighted_cap=150,
        )
        migration.lower_cap(apps, None)
        self.period.refresh_from_db()
        closed.refresh_from_db()
        self.assertEqual((self.period.weighted_cap, self.period.parameters_version), (Decimal(120), "2"))
        self.assertEqual((closed.weighted_cap, closed.parameters_version), (Decimal(150), "1"))

    def summary(self):
        goals = list(Goal.objects.filter(period=self.period, deleted_at__isnull=True).select_related("period", "item"))
        calculation.recalculate_period(self.period)
        index = IndicatorIndex([goal.pk for goal in goals])
        return officer_summary(self.cavieres, self.period, goals, index)

    def test_a_line_that_reached_the_cap_is_marked_and_is_not_in_the_lowest(self):
        self.reach(extra=int(self.goal.target_value))
        summary = self.summary()
        line = next(each for each in summary["lines"] if each["goal"].pk == self.goal.pk)
        self.assertTrue(line["capped"])
        self.assertNotIn(self.goal.item_id, [each["item"].pk for each in summary["lowest"]])
        self.assertGreaterEqual(summary["capped_total"], 1)

    def test_the_lowest_items_are_sorted_from_the_worst_and_at_most_three(self):
        summary = self.summary()
        lowest = summary["lowest"]
        self.assertLessEqual(len(lowest), 3)
        values = [each["compliance"] for each in lowest]
        self.assertEqual(values, sorted(values))
        self.assertTrue(all(value < 100 for value in values))

    def test_the_dashboard_shows_the_lowest_items_and_the_cap_badge(self):
        self.reach(extra=int(self.goal.target_value))
        self.login_as("matias.cavieres")
        page = self.client.get(reverse("core:dashboard"))
        self.assertContains(page, "Tope alcanzado")
        self.assertContains(page, "Ítems con menor puntaje")

    def test_the_officer_sheet_shows_them_too(self):
        self.reach(extra=int(self.goal.target_value))
        self.login_as("admin")
        page = self.client.get(reverse("core:funcionarios_detail", args=[self.cavieres.pk]))
        self.assertContains(page, "Tope alcanzado")


class DailyLimitTests(PointsBase):
    """RF-041: máximo de atenciones por día y funcionario."""

    def fill_today(self, count):
        today = portal_today()
        for number in range(count):
            Activity.objects.create(
                date=today, item=self.visit, contact_name=f"Lleno {number}", phone=PHONE,
                delegation=self.cavieres.delegation, author_officer=self.cavieres,
            )
        return today

    def post(self):
        return self.client.post(reverse("core:actividades_create"), self.intake_data(phone=PHONE))

    def test_the_limit_is_seven(self):
        from django.conf import settings

        self.assertEqual(settings.DAILY_ENTRY_LIMIT, 7)

    def test_the_seventh_attention_of_the_day_is_accepted(self):
        today = self.fill_today(6)
        before = Activity.objects.filter(author_officer=self.cavieres, date=today).count()
        self.login_as("matias.cavieres")
        self.assertEqual(self.post().status_code, 302)
        self.assertEqual(Activity.objects.filter(author_officer=self.cavieres, date=today).count(), before + 1)

    def test_the_eighth_is_refused_with_a_clear_message(self):
        today = self.fill_today(7)
        before = Activity.objects.filter(author_officer=self.cavieres, date=today).count()
        self.login_as("matias.cavieres")
        response = self.post()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "el máximo es 7 por día")
        self.assertEqual(Activity.objects.filter(author_officer=self.cavieres, date=today).count(), before)

    def test_the_count_is_per_officer_and_per_day(self):
        today = self.fill_today(7)
        other = Activity(
            date=today, item=self.visit, contact_name="Otra", phone=PHONE,
            delegation=self.cavieres.delegation, author_officer=self.officer("F-1002"),
        )
        self.assertIsNone(other.check_daily_limit())
        same = Activity(
            date=today, item=self.visit, contact_name="Mismo", phone=PHONE,
            delegation=self.cavieres.delegation, author_officer=self.cavieres,
        )
        with self.assertRaises(ValidationError):
            same.check_daily_limit()
        yesterday = Activity(
            date=today - timedelta(days=1), item=self.visit, contact_name="Ayer", phone=PHONE,
            delegation=self.cavieres.delegation, author_officer=self.cavieres,
        )
        self.assertIsNone(yesterday.check_daily_limit())

    def test_editing_an_attention_of_a_full_day_is_not_blocked(self):
        today = self.fill_today(7)
        activity = Activity.objects.filter(author_officer=self.cavieres, date=today).first()
        self.assertIsNone(activity.check_daily_limit())

    def test_archived_attentions_do_not_count(self):
        today = self.fill_today(7)
        from django.utils import timezone

        Activity.objects.filter(pk=Activity.objects.filter(author_officer=self.cavieres, date=today).first().pk).update(
            deleted_at=timezone.now()
        )
        self.login_as("matias.cavieres")
        self.assertEqual(self.post().status_code, 302)

    @override_settings(DAILY_ENTRY_LIMIT=2)
    def test_the_limit_comes_from_the_settings(self):
        self.fill_today(2)
        self.login_as("matias.cavieres")
        response = self.post()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "el máximo es 2 por día")


class SmallRangeTests(PortalTestCase):
    """Un número con pocos valores posibles (1 a 3) se elige de una lista: no se escribe ni se puede equivocar."""

    class Probe(CrudForm):
        class Meta:
            model = Followup
            fields = ("sequence_number",)

    def test_a_field_from_one_to_three_is_a_list(self):
        field = self.Probe().fields["sequence_number"]
        self.assertEqual([value for value, _ in field.choices if value], ["1", "2", "3"])

    def test_the_list_asks_to_choose_when_required(self):
        field = self.Probe().fields["sequence_number"]
        self.assertEqual(field.choices[0][0], "")

    def test_a_value_out_of_range_is_refused_with_a_clear_message(self):
        for wrong in ("1000", "0", "4", "-1"):
            form = self.Probe(data={"sequence_number": wrong})
            self.assertFalse(form.is_valid(), wrong)
            self.assertIn("entre 1 y 3", " ".join(form.errors["sequence_number"]))

    def test_a_valid_choice_comes_back_as_a_number(self):
        form = self.Probe(data={"sequence_number": "2"})
        form.is_valid()
        self.assertEqual(form.cleaned_data["sequence_number"], 2)

    def test_the_followup_screen_shows_the_number_as_a_list(self):
        self.login_as("admin")
        followup = Followup.objects.first()
        form = self.client.get(reverse("core:gestiones_update", args=[followup.pk])).context["form"]
        self.assertEqual([value for value, _ in form.fields["sequence_number"].choices if value], ["1", "2", "3"])
        self.assertTrue(form.fields["sequence_number"].disabled)

    def test_numbers_with_wide_ranges_stay_numeric_inputs(self):
        self.login_as("admin")
        form = self.client.get(reverse("core:periodos_create")).context["form"]
        self.assertEqual(form.fields["computable_days"].widget.input_type, "number")
