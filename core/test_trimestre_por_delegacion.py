"""Versión 51: trimestres por delegación y la pantalla «Agregar trimestre»."""
from datetime import date
from decimal import Decimal

from django.urls import reverse

from core.forms import QuarterAddForm
from core.testing import PortalTestCase
from operations.quarters import next_period, period_of
from planning import periods
from planning.models import Period


def make_period(start, end, delegation=None, **changes):
    values = {"start_date": start, "end_date": end, "computable_days": 60, "delegation": delegation}
    values.update(changes)
    return Period.objects.create(**values)


class QuarterScopeTests(PortalTestCase):
    """Cuál período rige para una fecha y una delegación."""

    def test_a_period_without_delegation_rules_for_everyone(self):
        general = make_period(date(2031, 1, 1), date(2031, 3, 31))
        self.assertEqual(period_of(date(2031, 2, 1), self.north), general)
        self.assertEqual(period_of(date(2031, 2, 1), self.south), general)
        self.assertEqual(period_of(date(2031, 2, 1)), general)

    def test_the_period_of_the_delegation_wins_over_the_general_one(self):
        general = make_period(date(2031, 1, 1), date(2031, 3, 31))
        own = make_period(date(2031, 1, 1), date(2031, 3, 31), self.north)
        self.assertEqual(period_of(date(2031, 2, 1), self.north), own)
        self.assertEqual(period_of(date(2031, 2, 1), self.south), general)

    def test_a_period_of_one_delegation_does_not_rule_for_another(self):
        make_period(date(2031, 1, 1), date(2031, 3, 31), self.north)
        self.assertIsNone(period_of(date(2031, 2, 1), self.south))
        self.assertIsNone(period_of(date(2031, 2, 1)))

    def test_the_next_period_stays_in_the_delegation(self):
        first = make_period(date(2031, 1, 1), date(2031, 3, 31), self.north)
        north_next = make_period(date(2031, 4, 1), date(2031, 6, 30), self.north)
        make_period(date(2031, 4, 1), date(2031, 6, 30), self.south)
        self.assertEqual(next_period(first), north_next)

    def test_the_next_period_can_be_a_general_one(self):
        first = make_period(date(2031, 1, 1), date(2031, 3, 31), self.north)
        general = make_period(date(2031, 4, 1), date(2031, 6, 30))
        self.assertEqual(next_period(first), general)

    def test_a_selector_shows_the_periods_of_the_delegation_and_the_general_ones(self):
        general = make_period(date(2031, 1, 1), date(2031, 3, 31))
        north = make_period(date(2031, 4, 1), date(2031, 6, 30), self.north)
        south = make_period(date(2031, 4, 1), date(2031, 6, 30), self.south)
        shown = set(periods.visible(self.north))
        self.assertIn(general, shown)
        self.assertIn(north, shown)
        self.assertNotIn(south, shown)
        self.assertTrue({general, north, south} <= set(periods.visible(None)))

    def test_the_name_says_which_delegation_it_is(self):
        self.assertIn("Delegación Norte", str(make_period(date(2031, 1, 1), date(2031, 3, 31), self.north)))
        self.assertNotIn("Delegación", str(make_period(date(2032, 1, 1), date(2032, 3, 31))))


class QuarterFormTests(PortalTestCase):
    """Los años y trimestres del formulario."""

    def test_each_quarter_has_its_calendar_dates(self):
        self.assertEqual(QuarterAddForm.dates_of(2031, 1), (date(2031, 1, 1), date(2031, 3, 31)))
        self.assertEqual(QuarterAddForm.dates_of(2031, 2), (date(2031, 4, 1), date(2031, 6, 30)))
        self.assertEqual(QuarterAddForm.dates_of(2031, 3), (date(2031, 7, 1), date(2031, 9, 30)))
        self.assertEqual(QuarterAddForm.dates_of(2031, 4), (date(2031, 10, 1), date(2031, 12, 31)))


class QuarterAddTests(PortalTestCase):
    """La pantalla «Agregar trimestre»."""

    url = "core:quarter_add"

    def data(self, **changes):
        values = {
            "year": 2031,
            "quarter": 1,
            "delegations": [self.north.pk, self.south.pk],
            "computable_days": "",
            "collective_threshold": "85",
            "amber_threshold": "60",
            "status": Period.Status.PLANNED,
        }
        values.update(changes)
        return values

    def test_the_list_offers_the_button_to_who_can_add_periods(self):
        self.login_as("coordinacion1")
        response = self.client.get(reverse("core:periodos_list"))
        self.assertContains(response, reverse(self.url))
        self.assertContains(response, "Agregar trimestre")

    def test_who_cannot_add_periods_gets_403(self):
        self.login_as("matias.cavieres")
        self.assertEqual(self.client.get(reverse(self.url)).status_code, 403)
        self.assertEqual(self.client.post(reverse(self.url), self.data()).status_code, 403)
        self.assertFalse(Period.objects.filter(start_date=date(2031, 1, 1)).exists())

    def test_the_screen_starts_with_this_year_and_all_the_delegations(self):
        self.login_as("coordinacion1")
        response = self.client.get(reverse(self.url))
        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        self.assertEqual(form.initial["year"], date.today().year)
        self.assertEqual(
            set(form.fields["delegations"].initial), {self.north.pk, self.south.pk}
        )
        self.assertContains(response, "quarter-add.js")

    def test_the_quarter_is_created_in_every_chosen_delegation(self):
        self.login_as("coordinacion1")
        response = self.client.post(reverse(self.url), self.data())
        self.assertRedirects(response, reverse("core:periodos_list"), fetch_redirect_response=False)
        created = Period.objects.filter(start_date=date(2031, 1, 1))
        self.assertEqual(created.count(), 2)
        self.assertEqual({each.delegation_id for each in created}, {self.north.pk, self.south.pk})
        for period in created:
            self.assertEqual(period.end_date, date(2031, 3, 31))
            self.assertEqual(period.collective_threshold, Decimal("85"))
            self.assertEqual(period.amber_threshold, Decimal("60"))
            self.assertEqual(period.status, Period.Status.PLANNED)

    def test_the_days_are_calculated_when_left_empty(self):
        self.login_as("coordinacion1")
        self.client.post(reverse(self.url), self.data())
        # 2031: del 1 de enero (miércoles) al 31 de marzo hay 64 días de lunes a viernes.
        self.assertEqual({each.computable_days for each in Period.objects.filter(start_date=date(2031, 1, 1))}, {64})

    def test_the_days_written_by_hand_are_kept(self):
        self.login_as("coordinacion1")
        self.client.post(reverse(self.url), self.data(computable_days="60"))
        self.assertEqual({each.computable_days for each in Period.objects.filter(start_date=date(2031, 1, 1))}, {60})

    def test_more_days_than_the_quarter_has_is_refused(self):
        self.login_as("coordinacion1")
        response = self.client.post(reverse(self.url), self.data(computable_days="120"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("computable_days", response.context["form"].errors)
        self.assertFalse(Period.objects.filter(start_date=date(2031, 1, 1)).exists())

    def test_the_amber_threshold_must_be_below_the_goal(self):
        self.login_as("coordinacion1")
        response = self.client.post(reverse(self.url), self.data(amber_threshold="90"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("amber_threshold", response.context["form"].errors)

    def test_only_the_marked_delegations_get_the_quarter(self):
        self.login_as("coordinacion1")
        self.client.post(reverse(self.url), self.data(delegations=[self.south.pk]))
        created = Period.objects.filter(start_date=date(2031, 1, 1))
        self.assertEqual([each.delegation_id for each in created], [self.south.pk])

    def test_at_least_one_delegation_is_needed(self):
        self.login_as("coordinacion1")
        response = self.client.post(reverse(self.url), self.data(delegations=[]))
        self.assertEqual(response.status_code, 200)
        self.assertIn("delegations", response.context["form"].errors)

    def test_an_overlap_in_one_delegation_refuses_all_and_creates_nothing(self):
        make_period(date(2031, 2, 1), date(2031, 4, 30), self.south)
        self.login_as("coordinacion1")
        response = self.client.post(reverse(self.url), self.data())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Delegación Sur ya tiene un período que se traslapa")
        self.assertFalse(Period.objects.filter(start_date=date(2031, 1, 1)).exists())

    def test_a_general_period_does_not_block_the_quarter_of_a_delegation(self):
        make_period(date(2031, 1, 1), date(2031, 12, 31))
        self.login_as("coordinacion1")
        self.client.post(reverse(self.url), self.data())
        self.assertEqual(Period.objects.filter(start_date=date(2031, 1, 1), delegation__isnull=False).count(), 2)

    def test_two_active_periods_in_one_delegation_are_refused(self):
        make_period(date(2030, 1, 1), date(2030, 3, 31), self.north, status=Period.Status.ACTIVE)
        self.login_as("coordinacion1")
        response = self.client.post(reverse(self.url), self.data(status=Period.Status.ACTIVE))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Delegación Norte ya tiene un período vigente")
        self.assertFalse(Period.objects.filter(start_date=date(2031, 1, 1)).exists())

    def test_the_other_parameters_are_copied_from_the_last_quarter_of_the_delegation(self):
        make_period(
            date(2030, 10, 1), date(2030, 12, 31), self.north, compliment_value=Decimal("15"), complaint_value=Decimal("25")
        )
        self.login_as("coordinacion1")
        self.client.post(reverse(self.url), self.data())
        north = Period.objects.get(start_date=date(2031, 1, 1), delegation=self.north)
        south = Period.objects.get(start_date=date(2031, 1, 1), delegation=self.south)
        self.assertEqual((north.compliment_value, north.complaint_value), (Decimal("15"), Decimal("25")))
        self.assertEqual((south.compliment_value, south.complaint_value), (Decimal("10"), Decimal("30")))

    def test_the_creation_is_audited_once_per_delegation(self):
        from core.models import AuditLog

        self.login_as("coordinacion1")
        before = AuditLog.objects.filter(affected_entity="Period", event="Registro creado").count()
        self.client.post(reverse(self.url), self.data())
        after = AuditLog.objects.filter(affected_entity="Period", event="Registro creado").count()
        self.assertEqual(after - before, 2)


class PeriodListAndFormTests(PortalTestCase):
    """El mantenedor de períodos con la delegación."""

    def test_a_delegation_only_sees_its_own_periods_and_the_general_ones(self):
        general = make_period(date(2031, 1, 1), date(2031, 3, 31))
        north = make_period(date(2031, 4, 1), date(2031, 6, 30), self.north)
        south = make_period(date(2031, 4, 1), date(2031, 6, 30), self.south)
        user = self.login_as("jefatura1")
        self.give_perm(user, "planning.view_period")
        shown = [row.obj.pk for row in self.client.get(reverse("core:periodos_list"), {"q": ""}).context["rows"]]
        self.assertIn(general.pk, shown)
        self.assertIn(north.pk, shown)
        self.assertNotIn(south.pk, shown)

    def test_the_form_refuses_an_overlap_in_the_same_scope(self):
        make_period(date(2031, 1, 1), date(2031, 3, 31), self.north)
        self.login_as("coordinacion1")
        response = self.client.post(
            reverse("core:periodos_create"),
            {
                "delegation": self.north.pk,
                "start_date": "2031-03-15",
                "end_date": "2031-06-30",
                "computable_days": 60,
                "status": Period.Status.PLANNED,
                "collective_threshold": 80,
                "amber_threshold": 60,
                "weighted_cap": 120,
                "compliment_value": 10,
                "complaint_value": 30,
                "compliment_limit": 3,
                "parameters_version": "1",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("start_date", response.context["form"].errors)

    def test_the_same_dates_are_fine_in_another_delegation(self):
        make_period(date(2031, 1, 1), date(2031, 3, 31), self.north)
        self.login_as("coordinacion1")
        response = self.client.post(
            reverse("core:periodos_create"),
            {
                "delegation": self.south.pk,
                "start_date": "2031-01-01",
                "end_date": "2031-03-31",
                "computable_days": 60,
                "status": Period.Status.PLANNED,
                "collective_threshold": 80,
                "amber_threshold": 60,
                "weighted_cap": 120,
                "compliment_value": 10,
                "complaint_value": 30,
                "compliment_limit": 3,
                "parameters_version": "1",
            },
        )
        self.assertEqual(response.status_code, 302)
