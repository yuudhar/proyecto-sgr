from decimal import Decimal

from django.urls import reverse

from core.models import AuditLog
from core.testing import PortalTestCase
from evidence.models import Evidence, Validation
from operations.models import Activity
from organization.models import Item, Officer
from planning.models import Goal, Indicator, Period


class ReviewScopeTests(PortalTestCase):

    def setUp(self):
        reviewer = self.make_user(
            "coord.verificador", ["Coordinación", "Verificador"], self.officer("F-1002")
        )
        self.client.force_login(reviewer)
        Evidence.objects.filter(unique_code="EVD-NORTE-0001").update(author_officer=self.officer("F-1001"))

    def test_validation_list_only_has_evidence_of_the_reviewers_delegation(self):
        response = self.client.get(reverse("core:validate_list"))
        codes = {item["evidence"].unique_code for item in response.context["items"]}
        self.assertTrue(codes)
        self.assertTrue(all(code.startswith("EVD-NORTE-") for code in codes))

    def test_evidence_of_another_delegation_cannot_be_opened_or_reviewed(self):
        other = Evidence.objects.filter(
            unique_code__startswith="EVD-SUR-", review_status="pending", deleted_at__isnull=True
        ).first()
        url = reverse("core:validate_evidence", args=[other.pk])
        self.assertEqual(self.client.get(url).status_code, 404)

        before = Validation.objects.count()
        response = self.client.post(url, {"decision": "approved", "result": "Conforme"})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(Validation.objects.count(), before)
        other.refresh_from_db()
        self.assertEqual(other.review_status, "pending")

    def test_dashboard_counts_what_the_validation_list_shows(self):
        listed = len(self.client.get(reverse("core:validate_list")).context["items"])
        response = self.client.get(reverse("core:dashboard"))
        card = next(item for item in response.context["pending"] if item["label"] == "Evidencias por revisar")
        self.assertEqual(card["total"], listed)
        self.assertEqual(card["url"], reverse("core:validate_list"))


class IndicatorScopeTests(PortalTestCase):
    def indicator_officers(self, response):
        return {row.obj.goal.officer for row in response.context["rows"] if row.obj.goal.officer_id}

    def test_delegation_users_only_see_indicators_of_their_own_officers(self):
        self.login_as("jefatura1")
        response = self.client.get(reverse("core:indicadores_list"))
        officers = self.indicator_officers(response)
        self.assertTrue(officers)
        self.assertEqual({officer.delegation for officer in officers}, {self.north})

        south_indicator = Indicator.objects.get(goal__officer__delegation=self.south)
        detail = reverse("core:indicadores_detail", args=[south_indicator.pk])
        self.assertEqual(self.client.get(detail).status_code, 404)

    def test_indicators_of_a_position_goal_are_visible_to_every_delegation(self):
        position_indicator = Indicator.objects.get(goal__officer__isnull=True)
        self.login_as("jefatura1")
        detail = reverse("core:indicadores_detail", args=[position_indicator.pk])
        self.assertEqual(self.client.get(detail).status_code, 200)

    def test_coordination_sees_the_indicators_of_every_delegation(self):
        self.login_as("coordinacion1")
        response = self.client.get(reverse("core:indicadores_list"))
        delegations = {officer.delegation for officer in self.indicator_officers(response)}
        self.assertEqual(delegations, {self.north, self.south})


class EditPermissionConsistencyTests(PortalTestCase):

    def test_global_user_cannot_edit_other_delegation_records_anywhere(self):
        user = self.make_user("coord.funcionario", ["Coordinación", "Funcionario"], self.officer("F-1002"))
        self.client.force_login(user)
        south = self.activity("Ana Rojas")
        north = self.activity("María Pérez")

        rows = {
            row.obj.pk: row
            for row in self.client.get(reverse("core:atencion")).context["rows"]
        }
        self.assertEqual(rows[south.pk].edit_url, "")
        self.assertNotEqual(rows[north.pk].edit_url, "")

        detail = self.client.get(reverse("core:actividades_detail", args=[south.pk]))
        self.assertEqual(detail.status_code, 200)
        self.assertFalse(detail.context["can_edit"])
        self.assertFalse(detail.context["can_archive"])
        self.assertTrue(self.client.get(reverse("core:actividades_detail", args=[north.pk])).context["can_edit"])

        self.assertEqual(self.client.get(reverse("core:actividades_update", args=[south.pk])).status_code, 403)

    def test_user_without_officer_sees_records_without_edit_buttons(self):
        user = self.make_user("coord.sin.funcionario", ["Coordinación", "Funcionario"])
        self.client.force_login(user)
        response = self.client.get(reverse("core:atencion"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["rows"])
        self.assertTrue(all(not row.edit_url for row in response.context["rows"]))
        detail = self.client.get(reverse("core:actividades_detail", args=[Activity.objects.first().pk]))
        self.assertEqual(detail.status_code, 200)
        self.assertFalse(detail.context["can_edit"])


class ReportAdjustmentTests(PortalTestCase):

    def csv_header(self, response):
        return response.content.decode("utf-8-sig").splitlines()[0]

    def test_coordination_sees_the_adjustment_column_in_page_and_csv(self):
        self.login_as("coordinacion1")
        page = self.client.get(reverse("core:reports"))
        self.assertTrue(page.context["with_adjustment"])
        self.assertContains(page, "Ajuste neto")
        header = self.csv_header(self.client.get(reverse("core:reports"), {"formato": "csv"}))
        self.assertIn("Ajuste neto (%)", header)

    def test_jefatura_does_not_get_adjustments_in_page_or_csv(self):
        self.login_as("jefatura1")
        page = self.client.get(reverse("core:reports"))
        self.assertEqual(page.status_code, 200)
        self.assertFalse(page.context["with_adjustment"])
        self.assertNotIn("ajuste", page.content.decode().lower().split("<main")[1])
        csv_response = self.client.get(reverse("core:reports"), {"formato": "csv"})
        self.assertNotIn("Ajuste", self.csv_header(csv_response))


class ExactAverageTests(PortalTestCase):

    def give_goals(self, officer, compliances):
        period = Period.objects.get(status="active")
        for number, compliance in enumerate(compliances, start=1):
            item = Item.objects.create(name=f"Ítem de prueba {number}")
            goal = Goal.objects.create(
                item=item, officer=officer, period=period, target_value=10, unit="u", weight=50
            )
            Indicator.objects.create(
                goal=goal, progress=1, compliance=compliance, weighting=50, status_light="green"
            )

    def test_officer_average_just_below_the_threshold_stays_amber(self):
        diego = Officer.objects.get(name="Diego Fuentes")
        self.give_goals(diego, ["79.95", "79.97"])
        self.login_as("admin")
        response = self.client.get(reverse("core:delegation_board"), {"delegacion": self.north.pk})
        row = next(r for r in response.context["results"] if r["officer"] == diego)
        self.assertEqual(row["average"], Decimal("80.0"))
        self.assertEqual(row["light"], "amber")

        report = self.client.get(reverse("core:reports"), {"delegacion": self.north.pk})
        line = next(r for r in report.context["rows"] if r["officer"] == diego)
        self.assertEqual(line["average"], Decimal("80.0"))
        self.assertEqual(line["light"], "amber")

    def test_delegation_average_just_below_the_threshold_stays_red(self):
        diego = Officer.objects.get(name="Diego Fuentes")
        self.give_goals(diego, ["129.93", "129.95"])
        self.login_as("admin")
        response = self.client.get(reverse("core:delegation_board"), {"delegacion": self.north.pk})
        self.assertEqual(response.context["average"], Decimal("60.0"))
        self.assertEqual(response.context["average_light"], "red")

    def test_an_exact_threshold_value_gets_the_better_light(self):
        diego = Officer.objects.get(name="Diego Fuentes")
        self.give_goals(diego, ["80", "80"])
        self.login_as("admin")
        response = self.client.get(reverse("core:delegation_board"), {"delegacion": self.north.pk})
        row = next(r for r in response.context["results"] if r["officer"] == diego)
        self.assertEqual(row["light"], "green")


class AuditPageTests(PortalTestCase):
    def test_detail_shows_the_record_number_without_thousands_dots(self):
        admin = self.login_as("admin")
        log = AuditLog.objects.create(
            event="Prueba", affected_entity="Activity", record_id=1234, user=admin
        )
        response = self.client.get(reverse("core:auditoria_detail", args=[log.pk]))
        self.assertContains(response, "1234")
        self.assertNotContains(response, "1.234")
