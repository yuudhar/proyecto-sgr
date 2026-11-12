"""Versión 31: felicitaciones y reclamos, puntaje de equipo e importación de juntas de vecinos."""
import tempfile
from datetime import datetime, timedelta
from decimal import Decimal
from io import StringIO
from pathlib import Path
from types import SimpleNamespace

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase
from django.utils import timezone
from django.urls import reverse
from openpyxl import Workbook

from core.test_results_and_calculation import CalculationBase
from core.testing import PortalTestCase, portal_today
from operations.models import Activity
from organization.models import CommunityOrganization, Delegation, Officer, Territory
from planning import feedback as rules
from planning.models import Adjustment, Feedback, Period
from planning.team import team_score

PDF = b"%PDF-1.4\n1 0 obj\n<< >>\nendobj\ntrailer\n<< >>\n%%EOF\n"


def support(name="captura.pdf", content=PDF):
    return SimpleUploadedFile(name, content, content_type="application/pdf")


class FeedbackBase(CalculationBase):
    """Datos comunes: la delegada (jefatura1) y un funcionario de la Norte; los ajustes se generan al confirmar la transacción."""

    def setUp(self):
        super().setUp()
        self.jefatura = self.make_user("delegada.prueba", groups=("Jefatura",))
        self.day = self.period.start_date + timedelta(days=10)

    def register(self, kind=Feedback.Kind.COMPLIMENT, officer=None, day=None, **changes):
        values = {
            "kind": kind,
            "date": day or self.day,
            "contact_name": "Rosa Núñez",
            "channel": Feedback.Channel.EMAIL,
            "officer": officer or self.cavieres,
            "description": "Atención destacada en la oficina.",
            "support": "respaldos/prueba.pdf",
            "registered_by": self.jefatura,
        }
        values.update(changes)
        with self.captureOnCommitCallbacks(execute=True):
            feedback = Feedback.objects.create(**values)
        feedback.refresh_from_db()  # el ajuste se enlaza al confirmar la transacción
        return feedback

    def adjustments(self, officer=None, period=None):
        """Los ajustes vigentes generados por felicitaciones y reclamos (la semilla trae otros ajustes sueltos)."""
        return Adjustment.objects.filter(
            officer=officer or self.cavieres, period=period or self.period, deleted_at__isnull=True,
            feedback__isnull=False,
        )


class FeedbackEffectTests(FeedbackBase):
    """RF-046: cada felicitación suma y cada reclamo resta; el ajuste se genera solo."""

    def test_a_compliment_adds_the_value_of_the_period_as_a_bonus(self):
        feedback = self.register()
        feedback.refresh_from_db()
        adjustment = feedback.adjustment
        self.assertEqual(adjustment.kind, Adjustment.Kind.BONUS)
        self.assertEqual(adjustment.percentage_value, Decimal("10"))
        self.assertEqual(adjustment.officer, self.cavieres)
        self.assertEqual(adjustment.period, self.period)
        self.assertEqual(adjustment.responsible_user, self.jefatura)
        self.assertIn("Felicitación", adjustment.reason)
        self.assertTrue(feedback.effective)

    def test_a_complaint_subtracts_the_value_of_the_period_as_a_penalty(self):
        feedback = self.register(Feedback.Kind.COMPLAINT)
        feedback.refresh_from_db()
        self.assertEqual(feedback.adjustment.kind, Adjustment.Kind.PENALTY)
        self.assertEqual(feedback.adjustment.percentage_value, Decimal("30"))
        self.assertIn("Reclamo", feedback.adjustment.reason)

    def test_the_period_is_the_one_that_contains_the_date(self):
        feedback = self.register()
        self.assertEqual(feedback.period, self.period)

    def test_the_values_are_configurable_in_the_period(self):
        Period.objects.filter(pk=self.period.pk).update(complaint_value=Decimal("20"), compliment_value=Decimal("5"))
        complaint = self.register(Feedback.Kind.COMPLAINT)
        compliment = self.register()
        complaint.refresh_from_db()
        compliment.refresh_from_db()
        self.assertEqual(complaint.adjustment.percentage_value, Decimal("20"))
        self.assertEqual(compliment.adjustment.percentage_value, Decimal("5"))

    def test_the_fourth_compliment_of_a_person_is_registered_without_effect(self):
        saved = [self.register(day=self.day + timedelta(days=n)) for n in range(4)]
        for each in saved:
            each.refresh_from_db()
        self.assertEqual([each.effective for each in saved], [True, True, True, False])
        self.assertIsNone(saved[3].adjustment)
        self.assertEqual(self.adjustments().count(), 3)
        self.assertEqual(sum(each.percentage_value for each in self.adjustments()), Decimal("30"))

    def test_the_limit_is_per_person(self):
        for n in range(3):
            self.register(day=self.day + timedelta(days=n))
        other = self.register(officer=self.officer("F-1002"))
        other.refresh_from_db()
        self.assertTrue(other.effective)
        self.assertEqual(self.adjustments(self.officer("F-1002")).count(), 1)

    def test_the_limit_is_configurable_in_the_period(self):
        Period.objects.filter(pk=self.period.pk).update(compliment_limit=1)
        first = self.register()
        second = self.register(day=self.day + timedelta(days=1))
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertTrue(first.effective)
        self.assertFalse(second.effective)

    def test_complaints_have_no_limit(self):
        for n in range(4):
            self.register(Feedback.Kind.COMPLAINT, day=self.day + timedelta(days=n))
        self.assertEqual(self.adjustments().count(), 4)

    def test_archiving_a_compliment_removes_its_adjustment_and_frees_a_place(self):
        saved = [self.register(day=self.day + timedelta(days=n)) for n in range(4)]
        with self.captureOnCommitCallbacks(execute=True):
            saved[0].deleted_at = timezone.now()
            saved[0].save()
        for each in saved:
            each.refresh_from_db()
        self.assertFalse(Adjustment.objects.get(pk=saved[0].adjustment_id).deleted_at is None)
        self.assertTrue(saved[3].effective)
        self.assertEqual(self.adjustments().count(), 3)

    def test_changing_the_person_moves_the_adjustment(self):
        feedback = self.register()
        other = self.officer("F-1002")
        with self.captureOnCommitCallbacks(execute=True):
            feedback.officer = other
            feedback.save()
        feedback.refresh_from_db()
        self.assertEqual(feedback.adjustment.officer, other)
        self.assertEqual(self.adjustments(self.cavieres).count(), 0)
        self.assertEqual(self.adjustments(other).count(), 1)

    def test_changing_the_kind_updates_the_adjustment(self):
        feedback = self.register()
        with self.captureOnCommitCallbacks(execute=True):
            feedback.kind = Feedback.Kind.COMPLAINT
            feedback.save()
        feedback.refresh_from_db()
        self.assertEqual(feedback.adjustment.kind, Adjustment.Kind.PENALTY)
        self.assertEqual(feedback.adjustment.percentage_value, Decimal("30"))
        self.assertEqual(self.adjustments().count(), 1)

    def test_deleting_the_record_removes_its_adjustment(self):
        feedback = self.register()
        adjustment_id = Feedback.objects.get(pk=feedback.pk).adjustment_id
        with self.captureOnCommitCallbacks(execute=True):
            feedback.delete()
        self.assertFalse(Adjustment.objects.filter(pk=adjustment_id, deleted_at__isnull=True).exists())

    def test_saving_twice_does_not_duplicate_the_adjustment(self):
        feedback = self.register()
        for _ in range(2):
            with self.captureOnCommitCallbacks(execute=True):
                feedback.save()
        self.assertEqual(self.adjustments().count(), 1)

    def test_the_net_adds_bonuses_and_subtracts_penalties(self):
        self.register()
        self.register(day=self.day + timedelta(days=1))
        self.register(Feedback.Kind.COMPLAINT, day=self.day + timedelta(days=2))
        net = rules.net_by_officer(self.period, [self.cavieres.pk])
        self.assertEqual(net[self.cavieres.pk], Decimal("-10"))

    def test_the_effect_text_says_what_the_record_does(self):
        compliment = self.register()
        complaint = self.register(Feedback.Kind.COMPLAINT)
        self.assertEqual(rules.effect_text(compliment), "Suma 10 %")
        self.assertEqual(rules.effect_text(complaint), "Resta 30 %")
        for n in range(3):
            last = self.register(day=self.day + timedelta(days=n + 1))
        last.refresh_from_db()
        self.assertIn("Sin efecto", rules.effect_text(last))


class FeedbackModelTests(FeedbackBase):
    """RF-046: la fecha debe caer en un período abierto y el funcionario estar activo."""

    def build(self, **changes):
        values = {
            "kind": Feedback.Kind.COMPLIMENT, "date": self.day, "contact_name": "Rosa", "officer": self.cavieres,
            "channel": Feedback.Channel.LOGBOOK, "description": "Texto", "support": "respaldos/prueba.pdf",
            "registered_by": self.jefatura,
        }
        values.update(changes)
        return Feedback(**values)

    def test_a_date_outside_every_period_is_refused(self):
        with self.assertRaises(ValidationError) as caught:
            self.build(date=self.period.start_date - timedelta(days=4000)).clean()
        self.assertIn("date", caught.exception.message_dict)

    def test_a_date_inside_a_closed_period_is_refused(self):
        closed = Period.objects.get(status=Period.Status.CLOSED)
        with self.assertRaises(ValidationError) as caught:
            self.build(date=closed.start_date + timedelta(days=3)).clean()
        self.assertIn("cerrado", caught.exception.message_dict["date"][0])

    def test_an_inactive_officer_is_refused(self):
        Officer.objects.filter(pk=self.cavieres.pk).update(status=Officer.Status.INACTIVE)
        with self.assertRaises(ValidationError) as caught:
            self.build(officer=Officer.objects.get(pk=self.cavieres.pk)).clean()
        self.assertIn("officer", caught.exception.message_dict)

    def test_clean_sets_the_period(self):
        feedback = self.build()
        feedback.clean()
        self.assertEqual(feedback.period, self.period)

    def test_the_channels_are_the_ones_of_the_matrix(self):
        self.assertEqual(
            [label for _value, label in Feedback.Channel.choices],
            ["Correo al delegado", "WhatsApp al delegado", "Libro de observaciones de la oficina"],
        )


class ComplaintAlertTests(FeedbackBase):
    """Un reclamo en más de dos períodos seguidos se informa a Recursos Humanos."""

    def setUp(self):
        super().setUp()
        year = self.period.start_date.year
        self.periods = [Period.objects.get(status=Period.Status.CLOSED)]
        self.older = Period.objects.create(
            start_date=self.periods[0].start_date.replace(year=year - 2),
            end_date=self.periods[0].end_date.replace(year=year - 2),
            computable_days=200,
            status=Period.Status.CLOSED,
        )

    def complaint(self, period):
        return Feedback.objects.create(
            kind=Feedback.Kind.COMPLAINT, date=period.start_date + timedelta(days=3), contact_name="Ana",
            channel=Feedback.Channel.EMAIL, officer=self.cavieres, description="Mala atención",
            support="respaldos/prueba.pdf", registered_by=self.jefatura,
        )

    def test_two_periods_in_a_row_do_not_raise_the_alert(self):
        self.complaint(self.periods[0])
        current = self.complaint(self.period)
        self.assertEqual(rules.complaint_streak(self.cavieres.pk, self.period), 2)
        self.assertEqual(rules.hr_alert(current), "")

    def test_three_periods_in_a_row_raise_the_alert(self):
        self.complaint(self.older)
        self.complaint(self.periods[0])
        current = self.complaint(self.period)
        self.assertEqual(rules.complaint_streak(self.cavieres.pk, self.period), 3)
        self.assertIn("Recursos Humanos", rules.hr_alert(current))

    def test_a_period_without_complaints_breaks_the_streak(self):
        self.complaint(self.older)
        current = self.complaint(self.period)
        self.assertEqual(rules.complaint_streak(self.cavieres.pk, self.period), 1)
        self.assertEqual(rules.hr_alert(current), "")

    def test_a_compliment_never_raises_the_alert(self):
        compliment = self.register()
        self.assertEqual(rules.hr_alert(compliment), "")


class FeedbackInResultsTests(FeedbackBase):
    """RF-046: el ajuste se suma al total ponderado en la ficha, el tablero y el dashboard."""

    def test_the_summary_adds_the_adjustment_to_the_weighted_total(self):
        from core.results import officer_summary
        from planning.calculation import IndicatorIndex
        from planning.models import Goal

        self.approved_activity()
        goals = list(Goal.objects.filter(deleted_at__isnull=True, period=self.period).select_related("item"))
        index = IndicatorIndex([goal.pk for goal in goals])
        before = officer_summary(self.cavieres, self.period, goals, index)
        self.assertEqual(before["adjustment_net"], 0)
        self.register()
        after = officer_summary(self.cavieres, self.period, goals, index)
        self.assertEqual(after["adjustment_net"], Decimal("10"))
        self.assertEqual(after["total_with_adjustment"], after["weighted_total"] + 10)

    def test_the_personal_sheet_shows_the_adjustment(self):
        self.approved_activity()
        self.register()
        self.login_as("jefatura1")
        officer = self.officer("F-1001")
        response = self.client.get(reverse("core:funcionarios_detail", args=[officer.pk]))
        self.assertContains(response, "Ajustes del período")
        self.assertContains(response, "+10")

    def test_the_dashboard_of_the_person_shows_the_adjustment(self):
        self.register()
        self.login_as("matias.cavieres")
        response = self.client.get(reverse("core:dashboard"))
        self.assertContains(response, "Total con ajustes")


class FeedbackScreensTests(PortalTestCase):
    """RF-046: solo el delegado (Jefatura) registra; cada delegación ve lo suyo."""

    def setUp(self):
        self.period = Period.objects.get(status=Period.Status.ACTIVE)
        self.cavieres = self.officer("F-1001")
        self.day = portal_today()

    def data(self, **changes):
        values = {
            "kind": Feedback.Kind.COMPLIMENT,
            "date": self.day.isoformat(),
            "officer": self.cavieres.pk,
            "channel": Feedback.Channel.EMAIL,
            "contact_name": "Rosa Núñez",
            "contact": "rosa@correo.example",
            "description": "Felicita la atención recibida.",
            "support": support(),
        }
        values.update(changes)
        return values

    def create(self, **changes):
        self.client.post(reverse("core:set_context"), {"delegacion": self.north.pk, "next": "/"})
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(reverse("core:cartas_create"), self.data(**changes))

    def test_the_delegate_registers_a_compliment_and_the_adjustment_appears(self):
        self.login_as("jefatura1")
        response = self.create()
        feedback = Feedback.objects.get(contact_name="Rosa Núñez", officer=self.cavieres)
        self.assertRedirects(response, reverse("core:cartas_detail", args=[feedback.pk]))
        self.assertEqual(feedback.registered_by.username, "jefatura1")
        self.assertEqual(feedback.adjustment.percentage_value, Decimal("10"))
        self.assertTrue(feedback.support.name.startswith("respaldos/"))

    def test_without_the_support_nothing_is_saved(self):
        self.login_as("jefatura1")
        before = Feedback.objects.count()
        response = self.create(support="")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "El respaldo es obligatorio")
        self.assertEqual(Feedback.objects.count(), before)
        self.assertEqual(Adjustment.objects.filter(reason__contains="Felicita la atención recibida.").count(), 0)

    def test_a_file_of_another_type_is_refused(self):
        self.login_as("jefatura1")
        before = Feedback.objects.count()
        response = self.create(support=SimpleUploadedFile("virus.exe", b"MZ....", content_type="application/octet-stream"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "no se acepta")
        self.assertEqual(Feedback.objects.count(), before)

    def test_a_file_whose_content_does_not_match_is_refused(self):
        self.login_as("jefatura1")
        before = Feedback.objects.count()
        response = self.create(support=support("falso.pdf", b"esto no es un pdf"))
        self.assertContains(response, "no corresponde")
        self.assertEqual(Feedback.objects.count(), before)

    def test_a_future_date_is_refused(self):
        self.login_as("jefatura1")
        before = Feedback.objects.count()
        response = self.create(date=(self.day + timedelta(days=3)).isoformat())
        self.assertContains(response, "no puede ser futura")
        self.assertEqual(Feedback.objects.count(), before)

    def test_a_date_outside_every_period_is_refused_in_the_form(self):
        self.login_as("jefatura1")
        before = Feedback.objects.count()
        response = self.create(date="2001-01-05")
        self.assertContains(response, "ningún período")
        self.assertEqual(Feedback.objects.count(), before)

    def test_the_delegate_cannot_point_to_an_officer_of_another_delegation(self):
        self.login_as("jefatura1")
        before = Feedback.objects.count()
        response = self.create(officer=self.officer("F-2001").pk)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Feedback.objects.count(), before)

    def test_a_field_with_html_symbols_is_refused(self):
        self.login_as("jefatura1")
        before = Feedback.objects.count()
        response = self.create(description="<script>alert(1)</script>")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Feedback.objects.count(), before)

    def test_an_officer_gets_403_to_open_or_send_the_form(self):
        self.login_as("matias.cavieres")
        before = Feedback.objects.count()
        self.assertEqual(self.client.get(reverse("core:cartas_create")).status_code, 403)
        self.assertEqual(
            self.client.post(reverse("core:cartas_create"), self.data()).status_code, 403
        )
        self.assertEqual(self.client.get(reverse("core:cartas_list")).status_code, 403)
        self.assertEqual(Feedback.objects.count(), before)

    def test_the_reader_cannot_open_the_module(self):
        self.login_as("consulta1")
        self.assertEqual(self.client.get(reverse("core:cartas_list")).status_code, 403)

    def test_coordination_can_see_but_not_register(self):
        self.login_as("coordinacion1")
        self.assertEqual(self.client.get(reverse("core:cartas_list")).status_code, 200)
        self.assertEqual(self.client.get(reverse("core:cartas_create")).status_code, 403)

    def test_the_list_shows_the_effect_and_only_the_own_delegation(self):
        south = Feedback.objects.create(
            kind=Feedback.Kind.COMPLAINT, date=self.day, contact_name="Vecina Sur", channel=Feedback.Channel.EMAIL,
            officer=self.officer("F-2001"), description="Mala atención", support="respaldos/demostracion/felicitacion-jefatura-norte.pdf",
            registered_by=User_of("admin"),
        )
        self.login_as("jefatura1")
        response = self.client.get(reverse("core:cartas_list"))
        self.assertContains(response, "Suma 10 %")
        self.assertNotContains(response, "Vecina Sur")
        self.assertEqual(
            self.client.get(reverse("core:cartas_detail", args=[south.pk])).status_code, 404
        )

    def test_the_support_opens_only_for_the_own_delegation(self):
        own = Feedback.objects.get(contact_name="Rosa Núñez")
        south = Feedback.objects.create(
            kind=Feedback.Kind.COMPLAINT, date=self.day, contact_name="Vecina Sur", channel=Feedback.Channel.EMAIL,
            officer=self.officer("F-2001"), description="Mala atención", support=own.support.name,
            registered_by=User_of("admin"),
        )
        self.login_as("jefatura1")
        response = self.client.get(reverse("core:feedback_file", args=[own.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertEqual(self.client.get(reverse("core:feedback_file", args=[south.pk])).status_code, 404)

    def test_the_support_needs_the_login_and_the_permission(self):
        own = Feedback.objects.get(contact_name="Rosa Núñez")
        self.assertEqual(self.client.get(reverse("core:feedback_file", args=[own.pk])).status_code, 302)
        self.login_as("matias.cavieres")
        self.assertEqual(self.client.get(reverse("core:feedback_file", args=[own.pk])).status_code, 403)

    def test_the_menu_lists_the_module_only_for_the_roles_that_see_it(self):
        self.login_as("jefatura1")
        self.assertIn("Cartas", self.menu_labels(self.client.get(reverse("core:dashboard"))))
        self.login_as("matias.cavieres")
        self.assertNotIn("Cartas", self.menu_labels(self.client.get(reverse("core:dashboard"))))

    def test_the_period_form_asks_for_the_new_values(self):
        self.login_as("coordinacion1")
        response = self.client.get(reverse("core:periodos_create"))
        for name in ("compliment_value", "complaint_value", "compliment_limit"):
            self.assertContains(response, f'name="{name}"')

    def test_the_period_refuses_a_value_out_of_range(self):
        self.login_as("coordinacion1")
        base = {
            "start_date": "2030-01-01", "end_date": "2030-12-31", "computable_days": 240, "status": "planned",
            "collective_threshold": "80", "amber_threshold": "60", "weighted_cap": "120", "parameters_version": "2",
            "compliment_value": "10", "complaint_value": "30", "compliment_limit": "3",
        }
        for name, bad in (("compliment_value", "0"), ("complaint_value", "150"), ("compliment_limit", "0")):
            response = self.client.post(reverse("core:periodos_create"), {**base, name: bad})
            self.assertEqual(response.status_code, 200, name)
        self.assertFalse(Period.objects.filter(start_date="2030-01-01").exists())

    def test_the_demo_data_has_an_example(self):
        example = Feedback.objects.get(contact_name="Rosa Núñez", kind=Feedback.Kind.COMPLIMENT)
        self.assertIsNotNone(example.adjustment_id)


def User_of(username):
    from django.contrib.auth.models import User

    return User.objects.get(username=username)


def item(name, weight, target, progress, unit="visitas", key=None):
    """Una línea de meta de un funcionario, como la entrega `core.results.goal_lines`."""
    return {
        "goal": SimpleNamespace(item_id=key or name),
        "item": SimpleNamespace(name=name),
        "unit": unit,
        "adjusted_target": Decimal(target),
        "indicator": SimpleNamespace(progress=Decimal(progress)) if progress is not None else None,
        "weight": Decimal(weight),
    }


def person(pk, name, lines, total):
    return {"officer": SimpleNamespace(pk=pk, name=name), "lines": lines, "weighted_total": Decimal(total) if total is not None else None}


PERIOD = SimpleNamespace(weighted_cap=Decimal(120), collective_threshold=Decimal(80), amber_threshold=Decimal(60))


class TeamScoreTests(SimpleTestCase):
    """RF-048: el equipo suma metas y avances, con el tope del período, y los aportes suman el puntaje."""

    def test_what_one_person_does_beyond_compensates_the_other(self):
        team = team_score(
            [
                person(1, "A", [item("Visitas", 100, 10, 14)], 120),
                person(2, "B", [item("Visitas", 100, 10, 2)], 20),
            ],
            PERIOD,
        )
        self.assertEqual(team["score"], Decimal("80.00"))
        self.assertEqual(team["individual_average"], Decimal("70.00"))
        self.assertEqual(team["difference"], Decimal("10.00"))

    def test_the_team_cannot_pass_the_cap_of_the_period(self):
        team = team_score(
            [person(1, "A", [item("Visitas", 100, 10, 20)], 120), person(2, "B", [item("Visitas", 100, 10, 10)], 100)],
            PERIOD,
        )
        self.assertEqual(team["score"], Decimal("120.00"))
        self.assertTrue(team["lines"][0]["capped"])
        self.assertEqual(team["lines"][0]["percent"], Decimal("150.00"))

    def test_the_contributions_add_up_to_the_score(self):
        team = team_score(
            [
                person(1, "A", [item("Visitas", 60, 10, 14), item("Charlas", 40, 4, 1)], 90),
                person(2, "B", [item("Visitas", 60, 10, 2), item("Charlas", 40, 4, 3)], 60),
            ],
            PERIOD,
        )
        total = sum(member["contribution"] for member in team["members"])
        self.assertAlmostEqual(float(total), float(team["score"]), delta=0.02)

    def test_the_contributions_add_up_to_the_score_even_with_the_cap(self):
        team = team_score(
            [person(1, "A", [item("Visitas", 100, 10, 20)], 120), person(2, "B", [item("Visitas", 100, 10, 10)], 100)],
            PERIOD,
        )
        total = sum(member["contribution"] for member in team["members"])
        self.assertAlmostEqual(float(total), 120.0, delta=0.02)

    def test_each_item_is_weighted_by_the_average_weight_and_the_score_is_on_a_base_of_100(self):
        team = team_score(
            [person(1, "A", [item("Visitas", 60, 10, 10), item("Charlas", 40, 4, 2)], 80)], PERIOD
        )
        self.assertEqual(team["score"], Decimal("80.00"))

    def test_weights_that_do_not_add_up_to_100_are_scaled(self):
        team = team_score([person(1, "A", [item("Visitas", 50, 10, 10), item("Charlas", 25, 4, 2)], 62)], PERIOD)
        self.assertEqual(team["score"], Decimal("83.33"))

    def test_an_absence_lowers_the_target_of_the_team(self):
        team = team_score(
            [person(1, "A", [item("Visitas", 100, 5, 5)], 120), person(2, "B", [item("Visitas", 100, 10, 5)], 50)], PERIOD
        )
        self.assertEqual(team["lines"][0]["target"], Decimal(15))
        self.assertEqual(team["score"], Decimal("66.67"))

    def test_without_calculated_indicators_the_progress_is_zero(self):
        team = team_score([person(1, "A", [item("Visitas", 100, 10, None)], None)], PERIOD)
        self.assertEqual(team["score"], Decimal("0.00"))
        self.assertIsNone(team["individual_average"])

    def test_without_goals_there_is_no_score(self):
        team = team_score([person(1, "A", [], None)], PERIOD)
        self.assertIsNone(team["score"])
        self.assertEqual(team["members"], [])

    def test_the_light_follows_the_thresholds_of_the_period(self):
        green = team_score([person(1, "A", [item("Visitas", 100, 10, 9)], 90)], PERIOD)
        amber = team_score([person(1, "A", [item("Visitas", 100, 10, 7)], 70)], PERIOD)
        red = team_score([person(1, "A", [item("Visitas", 100, 10, 3)], 30)], PERIOD)
        self.assertEqual((green["light"], amber["light"], red["light"]), ("green", "amber", "red"))

    def test_the_same_item_with_other_unit_is_not_mixed(self):
        team = team_score(
            [person(1, "A", [item("Visitas", 50, 10, 10, "visitas", key=1), item("Visitas", 50, 4, 0, "cartas", key=1)], 50)],
            PERIOD,
        )
        self.assertEqual(len(team["lines"]), 2)


class TeamScreensTests(PortalTestCase):
    """RF-048: el puntaje del equipo se ve en el dashboard personal, el tablero y la vista por cargos."""

    def test_the_personal_dashboard_shows_mine_and_the_team(self):
        self.login_as("matias.cavieres")
        response = self.client.get(reverse("core:dashboard"))
        self.assertContains(response, "Puntaje del equipo")
        self.assertContains(response, "Mi puntaje")
        self.assertEqual(response.context["team_label"], "Delegación Norte")

    def test_the_board_of_the_delegation_shows_the_team(self):
        self.login_as("jefatura1")
        response = self.client.get(reverse("core:delegation_board"))
        self.assertContains(response, "Puntaje del equipo")
        self.assertIn("score", response.context["team"])

    def test_the_view_by_position_shows_the_team_of_each_position(self):
        self.login_as("coordinacion1")
        response = self.client.get(reverse("core:position_overview"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(all("team" in group for group in response.context["groups"]))

    def test_the_team_only_counts_the_people_of_the_delegation(self):
        from core.views import team_of_delegation

        period = Period.objects.get(status=Period.Status.ACTIVE)
        north = team_of_delegation(self.north, period)
        south = team_of_delegation(self.south, period)
        north_names = {member["officer"].name for member in north["members"]}
        south_names = {member["officer"].name for member in south["members"]}
        self.assertFalse(north_names & south_names)


def workbook(rows, path, headers=None):
    book = Workbook()
    sheet = book.active
    sheet.append(
        headers
        or ["ORGANIZACIONES", "DOMICILIO LEGAL ", "TERRIT. DELEG.", "SOCIOS ACTIVOS", "FECHA CONSTIT.",
            "Nº REG. P.J.", "FECHA INSCRIPC EN REG.", "REG. DIR. Nº"]
    )
    for row in rows:
        sheet.append(row)
    book.save(path)
    return path


class ImportBase(TestCase):

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.north = Delegation.objects.create(name="Delegación Norte Importación")
        self.south = Delegation.objects.create(name="Delegación Sur Importación")

    def file(self, rows, **kwargs):
        return workbook(rows, Path(self.directory.name) / "base.xlsx", **kwargs)

    def run_import(self, path, *args):
        out = StringIO()
        call_command("importar_jjvv", str(path), *args, stdout=out)
        return out.getvalue()


ROWS = [
    ["JUNTA DE VECINOS EL SOL ", "CALLE UNO 123", "NORTE", 40, datetime(2001, 5, 3), 101, datetime(2001, 5, 9), 9001],
    ["CLUB DEPORTIVO LA ESTRELLA", None, "SUR ", 25, datetime(2010, 1, 2), 102, datetime(2010, 1, 5), None],
    ["AGRUPACION SIN TERRITORIO", "PASAJE 4", None, None, None, 103, None, None],
]


class ImportCommandTests(ImportBase):
    """RF-049: la importación no duplica por N.º de registro, informa y puede simularse."""

    def test_a_simulation_writes_nothing_but_reports(self):
        text = self.run_import(self.file(ROWS), "--simular")
        self.assertEqual(CommunityOrganization.objects.count(), 0)
        self.assertEqual(Territory.objects.filter(name__in=["NORTE", "SUR"]).count(), 0)
        self.assertIn("Simulación: no se escribió nada.", text)
        self.assertIn("Filas leídas: 3", text)
        self.assertIn("Organizaciones creadas: 3", text)

    def test_the_real_import_creates_the_organizations_unverified(self):
        self.run_import(self.file(ROWS))
        self.assertEqual(CommunityOrganization.objects.count(), 3)
        sun = CommunityOrganization.objects.get(registry_number=101)
        self.assertEqual(sun.name, "JUNTA DE VECINOS EL SOL")
        self.assertEqual(sun.active_members, 40)
        self.assertEqual(sun.constitution_date.year, 2001)
        self.assertEqual(sun.directory_number, 9001)
        self.assertFalse(sun.verified)

    def test_running_it_twice_does_not_duplicate(self):
        path = self.file(ROWS)
        self.run_import(path)
        text = self.run_import(path)
        self.assertEqual(CommunityOrganization.objects.count(), 3)
        self.assertIn("Organizaciones creadas: 0", text)
        self.assertIn("Organizaciones sin cambios: 3", text)

    def test_a_changed_row_is_updated_and_keeps_the_verified_mark(self):
        self.run_import(self.file(ROWS))
        CommunityOrganization.objects.filter(registry_number=101).update(verified=True)
        changed = [list(row) for row in ROWS]
        changed[0][3] = 55
        text = self.run_import(self.file(changed))
        sun = CommunityOrganization.objects.get(registry_number=101)
        self.assertEqual(sun.active_members, 55)
        self.assertTrue(sun.verified)
        self.assertIn("Organizaciones actualizadas: 1", text)

    def test_the_territory_is_created_in_the_delegation_whose_name_contains_it(self):
        text = self.run_import(self.file(ROWS))
        north = Territory.objects.get(name="NORTE")
        self.assertEqual(north.delegation, self.north)
        self.assertEqual(Territory.objects.get(name="SUR").delegation, self.south)
        self.assertEqual(CommunityOrganization.objects.get(registry_number=101).territory, north)
        self.assertIn("Territorios creados: 2", text)

    def test_the_extra_space_of_a_territory_does_not_make_another_one(self):
        rows = ROWS + [["OTRA DEL SUR", None, "SUR", 10, None, 104, None, None]]
        self.run_import(self.file(rows))
        self.assertEqual(Territory.objects.filter(name="SUR").count(), 1)

    def test_an_existing_territory_is_reused_without_tildes_or_capitals(self):
        existing = Territory.objects.create(name="Norte", delegation=self.south)
        self.run_import(self.file(ROWS))
        self.assertEqual(CommunityOrganization.objects.get(registry_number=101).territory, existing)
        self.assertFalse(Territory.objects.filter(name="NORTE").exists())

    def test_a_territory_without_delegation_keeps_only_its_text(self):
        rows = [["JUNTA LEJANA", None, "PAMPA", 12, None, 201, None, None]]
        text = self.run_import(self.file(rows))
        organization = CommunityOrganization.objects.get(registry_number=201)
        self.assertIsNone(organization.territory)
        self.assertEqual(organization.territory_text, "PAMPA")
        self.assertIn("Territorios sin delegación", text)
        self.assertIn("PAMPA", text)

    def test_the_delegation_option_creates_the_missing_territories_there(self):
        rows = [["JUNTA LEJANA", None, "PAMPA", 12, None, 201, None, None]]
        self.run_import(self.file(rows), "--delegacion", "Delegación Sur Importación")
        self.assertEqual(Territory.objects.get(name="PAMPA").delegation, self.south)
        self.assertIsNotNone(CommunityOrganization.objects.get(registry_number=201).territory)

    def test_an_unknown_delegation_is_an_error(self):
        with self.assertRaisesMessage(CommandError, "No existe la delegación"):
            self.run_import(self.file(ROWS), "--delegacion", "Inventada")

    def test_the_rows_without_name_or_registry_number_are_discarded_and_reported(self):
        rows = ROWS + [
            [None, None, "NORTE", 1, None, 301, None, None],
            ["SIN NUMERO", None, "NORTE", 1, None, None, None, None],
            ["REPETIDA", None, "NORTE", 1, None, 101, None, None],
        ]
        text = self.run_import(self.file(rows))
        self.assertEqual(CommunityOrganization.objects.count(), 3)
        self.assertIn("Filas descartadas: 3", text)
        self.assertIn("sin nombre", text)
        self.assertIn("sin N.º de registro", text)
        self.assertIn("repetido en la planilla", text)

    def test_the_report_counts_rows_without_territory_or_members(self):
        text = self.run_import(self.file(ROWS))
        self.assertIn("Filas sin territorio: 1", text)
        self.assertIn("Filas sin socios: 1", text)

    def test_a_workbook_without_the_expected_columns_is_an_error(self):
        path = self.file([["x", "y"]], headers=["A", "B"])
        with self.assertRaisesMessage(CommandError, "Faltan columnas"):
            self.run_import(path)

    def test_a_missing_file_is_an_error(self):
        with self.assertRaises(CommandError):
            self.run_import(Path(self.directory.name) / "no-existe.xlsx")

    def test_the_names_are_cleaned_of_extra_spaces(self):
        rows = [["  JUNTA   CON   ESPACIOS ", "  CALLE   X  ", "NORTE", "15", "2020-03-04", "401", "04/05/2020", "7"]]
        self.run_import(self.file(rows))
        organization = CommunityOrganization.objects.get(registry_number=401)
        self.assertEqual(organization.name, "JUNTA CON ESPACIOS")
        self.assertEqual(organization.legal_address, "CALLE X")
        self.assertEqual(organization.active_members, 15)
        self.assertEqual(organization.constitution_date.isoformat(), "2020-03-04")
        self.assertEqual(organization.registration_date.isoformat(), "2020-05-04")


class OrganizationScreensTests(PortalTestCase):
    """RF-049: el catálogo se ve en el listado y la atención puede quedar ligada a una organización."""

    def setUp(self):
        self.organization = CommunityOrganization.objects.create(name="JUNTA DE VECINOS PRUEBA", registry_number=9001)
        CommunityOrganization.objects.create(name="CLUB DE MADRES OTRA", registry_number=9002, verified=True)

    def test_the_superuser_sees_and_searches_the_catalog(self):
        self.login_as("admin")
        response = self.client.get(reverse("core:organizaciones_list"), {"q": "prueba"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "JUNTA DE VECINOS PRUEBA")
        self.assertNotContains(response, "CLUB DE MADRES OTRA")

    def test_the_catalog_filters_by_verified(self):
        self.login_as("admin")
        response = self.client.get(reverse("core:organizaciones_list"), {"verified": "1"})
        self.assertContains(response, "CLUB DE MADRES OTRA")
        self.assertNotContains(response, "JUNTA DE VECINOS PRUEBA")

    def test_the_registry_number_is_unique(self):
        self.login_as("admin")
        before = CommunityOrganization.objects.count()
        response = self.client.post(
            reverse("core:organizaciones_create"), {"name": "OTRA", "registry_number": "9001", "legal_address": ""}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(CommunityOrganization.objects.count(), before)

    def test_an_officer_cannot_manage_the_catalog(self):
        self.login_as("matias.cavieres")
        self.assertEqual(self.client.get(reverse("core:organizaciones_list")).status_code, 403)

    def test_the_intake_form_links_the_attention_to_an_organization(self):
        self.login_as("matias.cavieres")
        response = self.client.post(
            reverse("core:actividades_create"),
            self.intake_data(requester="Pedro Presidente", organization=self.organization.pk),
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.activity("Pedro Presidente").organization, self.organization)

    def test_the_organization_is_optional(self):
        self.login_as("matias.cavieres")
        self.client.post(reverse("core:actividades_create"), self.intake_data(requester="Sin Junta"))
        self.assertIsNone(self.activity("Sin Junta").organization)

    def test_the_selector_of_the_form_can_be_searched(self):
        self.login_as("matias.cavieres")
        for number in range(10):
            CommunityOrganization.objects.create(name=f"ORGANIZACION {number}", registry_number=9100 + number)
        response = self.client.get(reverse("core:actividades_create"))
        self.assertContains(response, 'name="organization"')
        self.assertContains(response, "data-searchable")

    def test_the_attentions_can_be_searched_by_the_name_of_the_organization(self):
        from core.crud import registry

        self.assertIn("organization__name", registry.get("actividades").search_fields)

    def test_an_organization_with_attentions_cannot_be_deleted(self):
        self.login_as("admin")
        Activity.objects.filter(contact_name="María Pérez").update(organization=self.organization)
        self.client.post(reverse("core:organizaciones_delete", args=[self.organization.pk]))
        self.assertTrue(CommunityOrganization.objects.filter(pk=self.organization.pk).exists())

    def test_the_menu_lists_the_catalog_for_the_superuser(self):
        self.login_as("admin")
        self.assertIn("Organizaciones", self.menu_labels(self.client.get(reverse("core:dashboard"))))
        self.login_as("matias.cavieres")
        self.assertNotIn("Organizaciones", self.menu_labels(self.client.get(reverse("core:dashboard"))))

