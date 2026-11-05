"""Versión 30: cierre semanal de ingresos y ausencias con meta ajustada."""
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase
from django.urls import reverse

from core import entry_rules
from core.activity_stats import recent_activity
from core.test_reglas_puntaje import PHONE, PointsBase
from core.testing import PortalTestCase, portal_today
from operations.models import Activity
from planning import absences, calculation
from planning.absences import NONE, AbsenceDays
from planning.models import Absence
from planning.pace import pace_of, weekdays_between


class WeekRuleTests(SimpleTestCase):
    """RF-042: la semana va de lunes a domingo y se ingresa hasta el lunes siguiente."""

    WEDNESDAY = date(2026, 10, 28)

    def test_the_week_goes_from_monday_to_sunday(self):
        self.assertEqual(entry_rules.week_start(self.WEDNESDAY), date(2026, 10, 26))
        self.assertEqual(entry_rules.week_end(self.WEDNESDAY), date(2026, 11, 1))
        self.assertEqual(entry_rules.week_start(date(2026, 10, 26)), date(2026, 10, 26))
        self.assertEqual(entry_rules.week_end(date(2026, 11, 1)), date(2026, 11, 1))

    def test_a_saturday_or_sunday_belongs_to_the_week_that_contains_it(self):
        for day in (date(2026, 10, 31), date(2026, 11, 1)):
            self.assertEqual(entry_rules.week_start(day), date(2026, 10, 26))
            self.assertEqual(entry_rules.last_entry_day(day), date(2026, 11, 2))

    def test_the_last_day_to_enter_is_the_next_monday(self):
        self.assertEqual(entry_rules.last_entry_day(self.WEDNESDAY), date(2026, 11, 2))
        self.assertEqual(entry_rules.last_entry_day(self.WEDNESDAY).weekday(), 0)

    def test_the_week_is_open_until_monday_and_closed_from_tuesday(self):
        self.assertFalse(entry_rules.is_week_closed(self.WEDNESDAY, today=date(2026, 11, 1)))
        self.assertFalse(entry_rules.is_week_closed(self.WEDNESDAY, today=date(2026, 11, 2)))
        self.assertTrue(entry_rules.is_week_closed(self.WEDNESDAY, today=date(2026, 11, 3)))

    def test_the_current_week_is_always_open(self):
        self.assertFalse(entry_rules.is_week_closed(date(2026, 11, 3), today=date(2026, 11, 3)))
        self.assertFalse(entry_rules.is_week_closed(date(2026, 11, 6), today=date(2026, 11, 8)))

    def test_the_message_says_which_week_closed_and_until_when(self):
        message = entry_rules.closed_message(self.WEDNESDAY)
        self.assertIn("26/10/2026 al 01/11/2026", message)
        self.assertIn("hasta el lunes 02/11/2026", message)
        self.assertIn("Desde el martes", message)


class WeeklyClosureTests(PointsBase):
    """RF-042: una atención de una semana ya cerrada no se ingresa; las demás ediciones no se bloquean."""

    TODAY = date(2026, 11, 3)  # martes

    def activity(self, day, **changes):
        values = {
            "date": day, "item": self.visit, "contact_name": "Cierre", "phone": PHONE,
            "delegation": self.cavieres.delegation, "author_officer": self.cavieres,
        }
        values.update(changes)
        return Activity(**values)

    def test_a_new_attention_of_a_closed_week_is_refused(self):
        with patch("core.entry_rules.portal_today", return_value=self.TODAY):
            with self.assertRaises(ValidationError) as caught:
                self.activity(date(2026, 10, 30)).check_week_open()
        self.assertIn("ya cerró", caught.exception.messages[0])

    def test_on_monday_the_previous_week_can_still_be_entered(self):
        with patch("core.entry_rules.portal_today", return_value=date(2026, 11, 2)):
            self.assertIsNone(self.activity(date(2026, 10, 30)).check_week_open())

    def test_a_new_attention_of_the_current_week_is_accepted(self):
        with patch("core.entry_rules.portal_today", return_value=self.TODAY):
            self.assertIsNone(self.activity(date(2026, 11, 2)).check_week_open())

    def test_editing_other_data_of_an_old_attention_is_not_blocked(self):
        old = self.activity(date(2026, 9, 1))
        old.save()
        old.request_description = "Se corrige un dato"
        with patch("core.entry_rules.portal_today", return_value=self.TODAY):
            self.assertIsNone(old.check_week_open())

    def test_changing_the_date_to_a_closed_week_is_refused(self):
        with patch("core.entry_rules.portal_today", return_value=self.TODAY):
            fresh = self.activity(date(2026, 11, 3))
            fresh.save()
            fresh.date = date(2026, 10, 20)
            with self.assertRaises(ValidationError):
                fresh.check_week_open()

    def test_the_clean_of_the_model_applies_both_rules(self):
        with patch("core.entry_rules.portal_today", return_value=self.TODAY):
            with self.assertRaises(ValidationError):
                self.activity(date(2026, 10, 20)).clean()


class EntryNoteTests(PortalTestCase):
    """RF-041 y RF-042: el formulario cuenta lo ingresado hoy y avisa hasta cuándo se puede ingresar la semana."""

    def test_the_intake_form_says_how_many_attentions_of_the_day_were_entered(self):
        self.login_as("matias.cavieres")
        officer = self.officer("F-1001")
        used = Activity.objects.filter(author_officer=officer, date=portal_today(), deleted_at__isnull=True).count()
        note = self.client.get(reverse("core:actividades_create")).context["form"].note
        self.assertIn(f"Hoy llevas {used} de 7 atenciones.", note)

    def test_the_counter_goes_up_with_each_attention(self):
        self.login_as("matias.cavieres")
        before = self.client.get(reverse("core:actividades_create")).context["form"].note
        response = self.client.post(
            reverse("core:actividades_create"),
            self.intake_data(phone=PHONE),
        )
        self.assertEqual(response.status_code, 302)
        after = self.client.get(reverse("core:actividades_create")).context["form"].note
        self.assertNotEqual(before, after)
        used, limit = entry_rules.daily_state(self.officer("F-1001").pk)
        self.assertIn(f"Hoy llevas {used} de {limit} atenciones.", after)

    def test_the_form_tells_until_when_the_week_can_be_entered(self):
        self.login_as("matias.cavieres")
        note = self.client.get(reverse("core:actividades_create")).context["form"].note
        self.assertIn("se puede ingresar hasta el lunes", note)
        self.assertIn(entry_rules.week_text(portal_today()), note)

    def test_the_edit_form_refuses_a_date_of_a_closed_week_with_the_message(self):
        self.login_as("admin")
        activity = self.activity("María Pérez")
        closed = entry_rules.week_start(portal_today()) - timedelta(days=21)
        response = self.client.post(
            reverse("core:actividades_update", args=[activity.pk]),
            self.activity_form_data(activity, date=closed.isoformat()),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ya cerró")
        self.assertNotEqual(Activity.objects.get(pk=activity.pk).date, closed)


class AbsenceMathTests(SimpleTestCase):
    """RF-047: días efectivos y meta ajustada."""

    PERIOD = SimpleNamespace(start_date=date(2026, 1, 5), end_date=date(2026, 1, 16), computable_days=10, status="active")

    def test_the_effective_days_discount_the_absence_days(self):
        self.assertEqual(absences.effective_days(self.PERIOD, AbsenceDays(total=3)), 7)
        self.assertEqual(absences.effective_days(self.PERIOD, NONE), 10)
        self.assertEqual(absences.effective_days(self.PERIOD, AbsenceDays(total=15)), 0)

    def test_the_goal_is_multiplied_by_effective_days_over_computable_days(self):
        self.assertEqual(absences.adjusted_target(Decimal("20"), self.PERIOD, AbsenceDays(total=5)), Decimal("10.00"))
        self.assertEqual(absences.adjusted_target(Decimal("20"), self.PERIOD, AbsenceDays(total=1)), Decimal("18.00"))
        self.assertEqual(absences.adjusted_target(Decimal("7"), self.PERIOD, AbsenceDays(total=3)), Decimal("4.90"))

    def test_without_absences_the_goal_does_not_change(self):
        self.assertEqual(absences.adjusted_target(Decimal("20"), self.PERIOD, NONE), Decimal("20"))

    def test_only_weekdays_inside_the_period_count(self):
        # del viernes 2 al miércoles 7 de enero: solo el lunes 5, martes 6 y miércoles 7 están en el período
        self.assertEqual(absences.clipped_days(date(2026, 1, 2), date(2026, 1, 7), self.PERIOD.start_date, self.PERIOD.end_date), 3)
        # un fin de semana completo no descuenta
        self.assertEqual(absences.clipped_days(date(2026, 1, 10), date(2026, 1, 11), self.PERIOD.start_date, self.PERIOD.end_date), 0)
        self.assertEqual(absences.clipped_days(date(2025, 12, 1), date(2025, 12, 31), self.PERIOD.start_date, self.PERIOD.end_date), 0)

    def test_the_expected_pace_does_not_count_the_absence_days(self):
        friday = date(2026, 1, 9)
        plain = pace_of(self.PERIOD, today=friday)
        self.assertEqual(plain.expected_percent, Decimal("50.0"))
        # dos días de ausencia ya transcurridos: 3 de 8 días efectivos
        away = pace_of(self.PERIOD, today=friday, absence=AbsenceDays(total=2, elapsed=2))
        self.assertEqual(away.expected_percent, Decimal("37.5"))
        self.assertEqual(away.total_days, 8)
        # dos días de ausencia que todavía no llegan: 5 de 8 días efectivos
        later = pace_of(self.PERIOD, today=friday, absence=AbsenceDays(total=2, elapsed=0))
        self.assertEqual(later.expected_percent, Decimal("62.5"))

    def test_a_finished_period_is_always_one_hundred_percent(self):
        done = pace_of(self.PERIOD, today=date(2026, 3, 1), absence=AbsenceDays(total=4, elapsed=0))
        self.assertEqual(done.expected_percent, Decimal("100.0"))
        self.assertEqual(done.total_days, 6)


class AbsenceModelTests(PointsBase):
    """RF-047: el modelo valida las fechas y no deja traslapar las ausencias de una persona."""

    def make(self, start, end, officer=None, kind=Absence.Kind.VACATION, **changes):
        return Absence(officer=officer or self.cavieres, kind=kind, start_date=start, end_date=end, **changes)

    def test_the_business_days_skip_the_weekends(self):
        self.assertEqual(self.make(date(2026, 1, 5), date(2026, 1, 11)).business_days, 5)
        self.assertEqual(self.make(date(2026, 1, 9), date(2026, 1, 12)).business_days, 2)

    def test_the_end_date_cannot_be_before_the_start_date(self):
        with self.assertRaises(ValidationError) as caught:
            self.make(date(2026, 1, 9), date(2026, 1, 5)).clean()
        self.assertIn("end_date", caught.exception.message_dict)

    def test_two_absences_of_the_same_person_cannot_overlap(self):
        self.make(date(2026, 1, 5), date(2026, 1, 9)).save()
        with self.assertRaises(ValidationError) as caught:
            self.make(date(2026, 1, 9), date(2026, 1, 12)).clean()
        self.assertIn("no pueden traslaparse", caught.exception.messages[0])

    def test_absences_of_different_people_can_overlap(self):
        self.make(date(2026, 1, 5), date(2026, 1, 9)).save()
        self.assertIsNone(self.make(date(2026, 1, 5), date(2026, 1, 9), officer=self.officer("F-1002")).clean())

    def test_editing_an_absence_does_not_collide_with_itself(self):
        absence = self.make(date(2026, 1, 5), date(2026, 1, 9))
        absence.save()
        absence.notes = "Licencia médica"
        self.assertIsNone(absence.clean())

    def test_an_archived_absence_does_not_block_a_new_one(self):
        from django.utils import timezone

        old = self.make(date(2026, 1, 5), date(2026, 1, 9))
        old.save()
        Absence.objects.filter(pk=old.pk).update(deleted_at=timezone.now())
        self.assertIsNone(self.make(date(2026, 1, 5), date(2026, 1, 9)).clean())

    def test_the_five_kinds_of_the_matrix_exist(self):
        self.assertEqual(
            [label for _value, label in Absence.Kind.choices],
            ["Licencia", "Vacaciones", "Día administrativo", "Emergencia", "Compensatorio"],
        )


class AbsenceCalculationTests(PointsBase):
    """RF-047: la meta del funcionario se ajusta y el cumplimiento se recalcula solo."""

    def absent(self, days, officer=None, **changes):
        """Ausencia de `days` días hábiles desde el primer lunes del período."""
        start = self.period.start_date
        while start.weekday() != 0:
            start += timedelta(days=1)
        end = start
        counted = 1
        while counted < days:
            end += timedelta(days=1)
            if end.weekday() < 5:
                counted += 1
        return Absence.objects.create(
            officer=officer or self.cavieres, kind=Absence.Kind.VACATION, start_date=start, end_date=end, **changes
        )

    def test_the_compliance_uses_the_adjusted_goal(self):
        plain = calculation.compute(self.goal, self.cavieres)
        absence = self.absent(5)
        adjusted = absences.adjusted_target(self.goal.target_value, self.period, absences.absence_days(self.cavieres.pk, self.period))
        self.assertLess(adjusted, self.goal.target_value)
        self.assertEqual(absence.business_days, 5)
        result = calculation.compute(self.goal, self.cavieres)
        self.assertEqual(result.progress, plain.progress)
        self.assertEqual(result.uncapped, calculation.money(plain.progress * 100 / adjusted))
        self.assertGreater(result.compliance, plain.compliance)

    def test_an_absence_of_one_person_does_not_change_the_others(self):
        before = calculation.compute(self.goal, self.officer("F-1002")).compliance
        self.absent(5)
        self.assertEqual(calculation.compute(self.goal, self.officer("F-1002")).compliance, before)

    def test_an_absence_outside_the_period_changes_nothing(self):
        before = calculation.compute(self.goal, self.cavieres)
        Absence.objects.create(
            officer=self.cavieres, kind=Absence.Kind.LICENSE,
            start_date=self.period.start_date - timedelta(days=60), end_date=self.period.start_date - timedelta(days=40),
        )
        self.assertEqual(calculation.compute(self.goal, self.cavieres), before)

    def test_registering_an_absence_recalculates_the_indicator(self):
        calculation.recalculate_all()
        before = self.latest()
        with self.captureOnCommitCallbacks(execute=True):
            self.absent(5)
        after = self.latest()
        self.assertNotEqual(after.pk, before.pk)
        self.assertGreater(after.compliance, before.compliance)
        self.assertEqual(after.compliance, calculation.compute(self.goal, self.cavieres).compliance)

    def test_archiving_the_absence_gives_the_goal_back(self):
        from django.utils import timezone

        calculation.recalculate_all()
        original = self.latest().compliance
        with self.captureOnCommitCallbacks(execute=True):
            absence = self.absent(5)
        with self.captureOnCommitCallbacks(execute=True):
            absence.deleted_at = timezone.now()
            absence.save()
        self.assertEqual(self.latest().compliance, original)

    def test_changing_the_dates_recalculates_the_old_and_the_new_period(self):
        calculation.recalculate_all()
        with self.captureOnCommitCallbacks(execute=True):
            absence = self.absent(5)
        with self.captureOnCommitCallbacks(execute=True):
            absence.start_date = self.period.start_date - timedelta(days=90)
            absence.end_date = self.period.start_date - timedelta(days=80)
            absence.save()
        self.assertEqual(self.latest().compliance, calculation.compute(self.goal, self.cavieres).compliance)
        self.assertEqual(calculation.compute(self.goal, self.cavieres).uncapped, calculation.money(
            calculation.compute(self.goal, self.cavieres).progress * 100 / self.goal.target_value))

    def test_when_every_day_is_absent_the_goal_is_zero_and_nothing_breaks(self):
        Absence.objects.create(
            officer=self.cavieres, kind=Absence.Kind.LICENSE,
            start_date=self.period.start_date, end_date=self.period.end_date,
        )
        days = absences.absence_days(self.cavieres.pk, self.period)
        self.assertGreaterEqual(days.total, int(self.period.computable_days))
        result = calculation.compute(self.goal, self.cavieres)
        self.assertEqual(result.compliance, Decimal(0))


class AbsenceScreensTests(PortalTestCase):
    """RF-047: quién registra ausencias y dónde se ven."""

    def data(self, **changes):
        period = Period_active()
        start = period.start_date + timedelta(days=7)
        values = {
            "officer": self.officer("F-1001").pk, "kind": Absence.Kind.VACATION,
            "start_date": start.isoformat(), "end_date": (start + timedelta(days=4)).isoformat(), "notes": "Feriado legal",
        }
        values.update(changes)
        return values

    def test_jefatura_registers_an_absence_of_its_delegation(self):
        user = self.login_as("jefatura1")
        response = self.client.post(reverse("core:ausencias_create"), self.data())
        self.assertEqual(response.status_code, 302)
        created = Absence.objects.get(notes="Feriado legal")
        self.assertEqual(created.registered_by, user)
        self.assertEqual(created.officer, self.officer("F-1001"))

    def test_coordination_registers_absences_too(self):
        self.login_as("coordinacion1")
        self.client.post(reverse("core:set_context"), {"delegacion": self.north.pk, "next": reverse("core:dashboard")})
        self.assertEqual(self.client.post(reverse("core:ausencias_create"), self.data()).status_code, 302)

    def test_a_funcionario_cannot_register_an_absence(self):
        self.login_as("matias.cavieres")
        before = Absence.objects.count()
        self.assertEqual(self.client.get(reverse("core:ausencias_create")).status_code, 403)
        self.assertEqual(self.client.post(reverse("core:ausencias_create"), self.data()).status_code, 403)
        self.assertEqual(Absence.objects.count(), before)

    def test_the_other_roles_cannot_register_an_absence(self):
        for username in ("consulta1",):
            self.login_as(username)
            self.assertEqual(self.client.get(reverse("core:ausencias_create")).status_code, 403, username)

    def test_jefatura_only_sees_absences_of_its_delegation(self):
        north = Absence.objects.create(
            officer=self.officer("F-1001"), kind=Absence.Kind.LICENSE, start_date=date(2026, 1, 5), end_date=date(2026, 1, 9)
        )
        south_officer = self.officer("F-1002").__class__.objects.filter(delegation=self.south).first()
        south = Absence.objects.create(
            officer=south_officer, kind=Absence.Kind.LICENSE, start_date=date(2026, 1, 5), end_date=date(2026, 1, 9)
        )
        self.login_as("jefatura1")
        found = [row.obj.pk for row in self.client.get(reverse("core:ausencias_list")).context["rows"]]
        self.assertIn(north.pk, found)
        self.assertNotIn(south.pk, found)

    def test_the_end_date_before_the_start_date_is_refused_with_a_message(self):
        self.login_as("jefatura1")
        before = Absence.objects.count()
        response = self.client.post(
            reverse("core:ausencias_create"),
            self.data(start_date="2026-01-09", end_date="2026-01-05"),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "no puede ser anterior")
        self.assertEqual(Absence.objects.count(), before)

    def test_the_list_shows_the_business_days(self):
        created = Absence.objects.create(
            officer=self.officer("F-1001"), kind=Absence.Kind.EMERGENCY, start_date=date(2026, 1, 5), end_date=date(2026, 1, 9)
        )
        self.login_as("coordinacion1")
        rows = {row.obj.pk: row for row in self.client.get(reverse("core:ausencias_list")).context["rows"]}
        self.assertIn("5", [cell.text for cell in rows[created.pk].cells])

    def test_the_delegation_board_has_the_team_absences_block_and_the_adjusted_goal(self):
        period = Period_active()
        start = period.start_date
        while start.weekday() != 0:
            start += timedelta(days=1)
        Absence.objects.create(
            officer=self.officer("F-1001"), kind=Absence.Kind.VACATION, start_date=start, end_date=start + timedelta(days=4)
        )
        self.login_as("jefatura1")
        page = self.client.get(reverse("core:delegation_board"))
        self.assertContains(page, "Ausencias del equipo")
        self.assertContains(page, "Registrar ausencia")
        self.assertContains(page, "ajustada por ausencias")
        rows = {row["officer"].name: row for row in page.context["absence_rows"]}
        self.assertEqual(rows["Matías Cavieres"]["total"], 5)
        self.assertEqual(rows["Diego Fuentes"]["total"], 0)
        self.assertEqual(rows["Matías Cavieres"]["effective"], int(period.computable_days) - 5)

    def test_the_personal_sheet_shows_the_original_and_the_adjusted_goal(self):
        period = Period_active()
        start = period.start_date
        while start.weekday() != 0:
            start += timedelta(days=1)
        Absence.objects.create(
            officer=self.officer("F-1001"), kind=Absence.Kind.COMPENSATORY, start_date=start, end_date=start + timedelta(days=4)
        )
        self.login_as("admin")
        page = self.client.get(reverse("core:funcionarios_detail", args=[self.officer("F-1001").pk]))
        self.assertContains(page, "Meta original")
        sheet = page.context["sheet"]
        self.assertEqual(sheet["absence"].total, 5)
        self.assertTrue(all(line["adjusted"] for line in sheet["lines"]))

    def test_the_demo_data_has_an_example_absence(self):
        self.assertTrue(Absence.objects.filter(officer__institutional_id="F-1003").exists())

    def test_the_menu_lists_absences_for_the_roles_that_can_see_them(self):
        self.login_as("coordinacion1")
        self.assertIn("Ausencias", self.menu_labels(self.client.get(reverse("core:dashboard"))))
        self.login_as("consulta1")
        self.assertNotIn("Ausencias", self.menu_labels(self.client.get(reverse("core:dashboard"))))


class AbsenceActivityStatsTests(PointsBase):
    """RF-047: los días de ausencia no cuentan entre los días sin ingreso."""

    def test_the_days_of_absence_are_not_days_without_entries(self):
        from django.utils import timezone

        today = date(2026, 6, 15)
        officer = self.officer("F-1002")
        Activity.objects.filter(author_officer=officer).update(deleted_at=timezone.now())
        Activity.objects.create(
            date=date(2026, 6, 1), item=self.visit, contact_name="Ultimo", phone=PHONE,
            delegation=officer.delegation, author_officer=officer,
        )
        plain = recent_activity([officer.pk], self.period, None, today)[officer.pk]
        self.assertEqual(plain.days_without, 14)
        Absence.objects.create(
            officer=officer, kind=Absence.Kind.VACATION, start_date=date(2026, 6, 8), end_date=date(2026, 6, 12)
        )
        away = recent_activity([officer.pk], self.period, None, today)[officer.pk]
        self.assertEqual(away.days_without, 9)

    def test_the_daily_average_uses_the_effective_days(self):
        officer = self.cavieres
        today = self.period.start_date + timedelta(days=13)
        pace = pace_of(self.period, today)
        Activity.objects.create(
            date=self.period.start_date + timedelta(days=1), item=self.visit, contact_name="Promedio", phone=PHONE,
            delegation=officer.delegation, author_officer=officer,
        )
        plain = recent_activity([officer.pk], self.period, pace, today)[officer.pk]
        self.assertGreaterEqual(plain.total, 1)
        start = self.period.start_date
        while start.weekday() != 0:
            start += timedelta(days=1)
        Absence.objects.create(
            officer=officer, kind=Absence.Kind.LICENSE, start_date=start, end_date=start + timedelta(days=4)
        )
        away = recent_activity([officer.pk], self.period, pace, today)[officer.pk]
        self.assertGreater(away.daily_average, plain.daily_average)


def Period_active():
    from planning.models import Period

    return Period.objects.get(status=Period.Status.ACTIVE)
