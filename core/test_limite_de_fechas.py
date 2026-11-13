"""Versión 41: las fechas de compromisos, gestiones, cartas, ausencias y cambios de trimestre no pueden ser de hace más de 12 meses."""
from datetime import date, timedelta

from django.test import SimpleTestCase, override_settings
from django.urls import reverse

from core import entry_rules
from core.test_cartas_y_compromisos import make_commitment
from core.test_cambio_de_trimestre import Mode, QuarterBase
from core.testing import PortalTestCase, portal_today
from operations.models import Commitment, Followup, ManagementType
from organization.models import Territory
from planning.models import Absence


class DateHelperTests(SimpleTestCase):

    def test_months_back_keeps_the_day_when_it_exists(self):
        self.assertEqual(entry_rules.months_back(date(2026, 11, 11), 12), date(2025, 11, 11))
        self.assertEqual(entry_rules.months_back(date(2026, 1, 15), 14), date(2024, 11, 15))

    def test_months_back_uses_the_last_day_of_the_month_when_the_day_does_not_exist(self):
        self.assertEqual(entry_rules.months_back(date(2028, 2, 29), 12), date(2027, 2, 28))
        self.assertEqual(entry_rules.months_back(date(2026, 10, 31), 1), date(2026, 9, 30))

    @override_settings(BACKDATE_MONTHS=6)
    def test_the_limit_comes_from_the_setting(self):
        self.assertEqual(entry_rules.earliest_date(date(2026, 11, 11)), date(2026, 5, 11))

    def test_the_default_limit_is_twelve_months(self):
        self.assertEqual(entry_rules.earliest_date(date(2026, 11, 11)), date(2025, 11, 11))


class LimitBase(PortalTestCase):

    def setUp(self):
        self.today = portal_today()
        self.limit = entry_rules.earliest_date(self.today)
        self.cavieres = self.officer("F-1001")
        self.territory = Territory.objects.filter(delegation=self.north).first()

    def errors_of(self, response, field):
        self.assertEqual(response.status_code, 200)
        return " ".join(response.context["form"].errors.get(field, []))


class CommitmentLimitTests(LimitBase):

    def data(self, **changes):
        values = {
            "requester": "Club de Adulto Mayor",
            "requester_type": Commitment.RequesterType.EXTERNAL,
            "request_date": self.today.isoformat(),
            "description": "Visita para ver la sede.",
            "territory": self.territory.pk,
            "due_date": (self.today + timedelta(days=5)).isoformat(),
            "status": Commitment.Status.SUBMITTED,
            "responsible_officer": self.cavieres.pk,
            "delegation": self.north.pk,
        }
        values.update(changes)
        return values

    def test_the_form_tells_the_browser_the_earliest_date(self):
        self.login_as("matias.cavieres")
        widget = self.client.get(reverse("core:compromisos_create")).context["form"].fields["request_date"].widget
        self.assertEqual(widget.attrs["min"], self.limit.isoformat())
        self.assertEqual(widget.attrs["max"], self.today.isoformat())
        self.assertIn("12 meses", widget.attrs["data-min-message"])

    def test_a_date_from_1997_is_refused_with_a_message(self):
        self.login_as("matias.cavieres")
        before = Commitment.objects.count()
        response = self.client.post(reverse("core:compromisos_create"), self.data(request_date="1997-03-01"))
        message = self.errors_of(response, "request_date")
        self.assertIn("no puede ser de hace más de 12 meses", message)
        self.assertIn("la más antigua que se acepta es el", message)
        self.assertEqual(Commitment.objects.count(), before)

    def test_the_day_before_the_limit_is_refused_and_the_limit_itself_is_accepted(self):
        self.login_as("matias.cavieres")
        day_before = self.limit - timedelta(days=1)
        response = self.client.post(reverse("core:compromisos_create"), self.data(request_date=day_before.isoformat()))
        self.assertIn("hace más de 12 meses", self.errors_of(response, "request_date"))
        response = self.client.post(reverse("core:compromisos_create"), self.data(request_date=self.limit.isoformat()))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Commitment.objects.filter(requester="Club de Adulto Mayor", request_date=self.limit).exists())

    def test_an_old_commitment_can_be_edited_while_its_date_is_left_alone(self):
        old = self.limit - timedelta(days=200)
        item = make_commitment(self.north, self.cavieres, self.territory, "Vieja Solicitud", request_date=old)
        self.login_as("matias.cavieres")
        url = reverse("core:compromisos_update", args=[item.pk])
        page = self.client.get(url).context["form"].fields["request_date"].widget
        self.assertNotIn("min", page.attrs)
        data = self.data(requester="Vieja Solicitud", request_date=old.isoformat(), description="Texto corregido.")
        data["due_date"] = (self.today + timedelta(days=5)).isoformat()
        self.assertEqual(self.client.post(url, data).status_code, 302)
        item.refresh_from_db()
        self.assertEqual(item.description, "Texto corregido.")
        self.assertEqual(item.request_date, old)

    def test_an_old_commitment_cannot_move_to_another_old_date(self):
        old = self.limit - timedelta(days=200)
        item = make_commitment(self.north, self.cavieres, self.territory, "Vieja Solicitud", request_date=old)
        self.login_as("matias.cavieres")
        data = self.data(requester="Vieja Solicitud", request_date=(old - timedelta(days=30)).isoformat())
        response = self.client.post(reverse("core:compromisos_update", args=[item.pk]), data)
        self.assertIn("hace más de 12 meses", self.errors_of(response, "request_date"))
        item.refresh_from_db()
        self.assertEqual(item.request_date, old)


class FollowupLimitTests(LimitBase):

    def data(self, **changes):
        activity = self.activity("María Pérez")
        values = {
            "activity": activity.pk,
            "management_type": ManagementType.objects.first().pk,
            "date": activity.date.isoformat(),
            "result": "Se llamó por teléfono.",
        }
        values.update(changes)
        return values

    def test_the_form_tells_the_browser_the_earliest_date(self):
        self.login_as("matias.cavieres")
        fields = self.client.get(reverse("core:gestiones_create")).context["form"].fields
        for name in ("date", "visit_date", "report_delivery_date", "benefit_delivery_date"):
            self.assertEqual(fields[name].widget.attrs["min"], self.limit.isoformat(), name)

    def test_an_old_date_of_the_management_is_refused(self):
        self.login_as("matias.cavieres")
        before = Followup.objects.count()
        response = self.client.post(reverse("core:gestiones_create"), self.data(date="1997-03-01"))
        self.assertIn("La fecha de la gestión no puede ser de hace más de 12 meses", self.errors_of(response, "date"))
        self.assertEqual(Followup.objects.count(), before)

    def test_an_old_visit_date_is_refused(self):
        self.login_as("matias.cavieres")
        response = self.client.post(reverse("core:gestiones_create"), self.data(visit_date="2001-05-10"))
        self.assertIn("La fecha de la visita no puede ser de hace más de 12 meses", self.errors_of(response, "visit_date"))

    def test_a_recent_date_is_accepted(self):
        self.login_as("matias.cavieres")
        response = self.client.post(reverse("core:gestiones_create"), self.data())
        self.assertEqual(response.status_code, 302)


class FeedbackLimitTests(LimitBase):

    def data(self, **changes):
        values = {
            "kind": "compliment",
            "date": self.today.isoformat(),
            "officer": self.cavieres.pk,
            "channel": "email",
            "contact_name": "Rosa Núñez",
            "contact": "rosa@correo.example",
            "description": "Felicita la atención recibida.",
        }
        values.update(changes)
        return values

    def test_an_old_date_is_refused(self):
        self.login_as("jefatura1")
        self.client.post(reverse("core:set_context"), {"delegacion": self.north.pk, "next": "/"})
        response = self.client.post(reverse("core:cartas_create"), self.data(date="1997-03-01"))
        self.assertIn("La fecha no puede ser de hace más de 12 meses", self.errors_of(response, "date"))

    def test_the_limit_day_and_today_are_not_refused_for_being_too_old(self):
        self.login_as("jefatura1")
        self.client.post(reverse("core:set_context"), {"delegacion": self.north.pk, "next": "/"})
        for day in (self.limit, self.today):
            response = self.client.post(reverse("core:cartas_create"), self.data(date=day.isoformat()))
            # El límite puede caer en un período cerrado (otra regla); aquí solo importa que no se rechace por antigua.
            self.assertNotIn("hace más de", self.errors_of(response, "date"), day)


class AbsenceLimitTests(LimitBase):

    def data(self, **changes):
        values = {
            "officer": self.cavieres.pk, "kind": Absence.Kind.VACATION, "notes": "Feriado legal",
            "start_date": self.today.isoformat(), "end_date": (self.today + timedelta(days=4)).isoformat(),
        }
        values.update(changes)
        return values

    def test_the_form_tells_the_browser_the_earliest_date(self):
        self.login_as("jefatura1")
        widget = self.client.get(reverse("core:ausencias_create")).context["form"].fields["start_date"].widget
        self.assertEqual(widget.attrs["min"], self.limit.isoformat())

    def test_an_absence_that_started_in_1997_is_refused(self):
        self.login_as("jefatura1")
        before = Absence.objects.count()
        response = self.client.post(
            reverse("core:ausencias_create"), self.data(start_date="1997-03-03", end_date="1997-03-07")
        )
        self.assertIn("La fecha «desde» no puede ser de hace más de 12 meses", self.errors_of(response, "start_date"))
        self.assertEqual(Absence.objects.count(), before)

    def test_the_limit_day_is_accepted(self):
        self.login_as("jefatura1")
        end = self.limit + timedelta(days=4)
        response = self.client.post(
            reverse("core:ausencias_create"), self.data(start_date=self.limit.isoformat(), end_date=end.isoformat())
        )
        self.assertEqual(response.status_code, 302)

    def test_an_old_absence_can_still_be_corrected_without_touching_its_dates(self):
        old = self.limit - timedelta(days=100)
        absence = Absence.objects.create(
            officer=self.cavieres, kind=Absence.Kind.LICENSE, start_date=old, end_date=old + timedelta(days=4)
        )
        self.login_as("jefatura1")
        data = self.data(start_date=old.isoformat(), end_date=(old + timedelta(days=4)).isoformat(), notes="Licencia médica")
        response = self.client.post(reverse("core:ausencias_update", args=[absence.pk]), data)
        self.assertEqual(response.status_code, 302)
        absence.refresh_from_db()
        self.assertEqual(absence.notes, "Licencia médica")


class QuarterRequestLimitTests(QuarterBase):

    def test_a_manual_date_older_than_twelve_months_is_refused_by_the_form(self):
        self.login_as("matias.cavieres")
        old = entry_rules.earliest_date(self.today) - timedelta(days=1)
        response = self.ask(mode=Mode.MANUAL, new_date=old.isoformat())
        self.assertEqual(response.status_code, 200)
        self.assertIn("hace más de 12 meses", " ".join(response.context["form"].errors["new_date"]))
