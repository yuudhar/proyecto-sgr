from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from core.crud import SEARCH_WORDS
from core.models import AuditLog
from core.testing import PortalTestCase
from evidence.models import Evidence
from operations.models import Activity
from organization.models import Item
from planning.models import Adjustment, Goal, Indicator, Period


class AuditTests(PortalTestCase):
    def test_creating_a_record_is_audited_with_its_name(self):
        self.login_as("matias.cavieres")
        self.client.post(reverse("core:actividades_create"), self.intake_data())
        created = Activity.objects.get(contact_name="Rosa Prueba")
        log = AuditLog.objects.get(event="Registro creado", record_id=created.pk)
        self.assertEqual(log.affected_entity, "Activity")
        self.assertEqual(log.user.username, "matias.cavieres")
        self.assertIn("Rosa Prueba", log.new_value)

    def test_updating_a_record_audits_each_changed_field_with_before_and_after(self):
        user = self.login_as("matias.cavieres")
        activity = self.activity("María Pérez")
        old_status = activity.get_status_display()
        data = self.activity_form_data(
            activity, contact_name="María Pérez Editada", status=Activity.Status.CLOSED
        )
        self.client.post(reverse("core:actividades_update", args=[activity.pk]), data)

        log = AuditLog.objects.get(event="Registro modificado", record_id=activity.pk)
        self.assertEqual(log.user, user)
        self.assertIn("Contacto: María Pérez", log.previous_value)
        self.assertIn("Contacto: María Pérez Editada", log.new_value)
        self.assertIn(f"Estado: {old_status}", log.previous_value)
        self.assertIn("Estado: Cerrada", log.new_value)
        self.assertNotIn("Teléfono", log.new_value)
        self.assertNotIn("Requiere visita", log.new_value)

    def test_saving_without_changes_leaves_no_audit_entry(self):
        self.login_as("matias.cavieres")
        activity = self.activity("María Pérez")
        response = self.client.post(
            reverse("core:actividades_update", args=[activity.pk]), self.activity_form_data(activity)
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            AuditLog.objects.filter(event="Registro modificado", record_id=activity.pk).exists()
        )


class ConcurrentEditTests(PortalTestCase):
    def open_form(self, activity):
        response = self.client.get(reverse("core:actividades_update", args=[activity.pk]))
        self.assertEqual(response.status_code, 200)
        return response

    def post_data(self, activity, version, **changes):
        return self.activity_form_data(activity, _version=version, **changes)

    def test_edit_form_carries_the_version_it_was_opened_with(self):
        self.login_as("matias.cavieres")
        activity = self.activity("María Pérez")
        response = self.open_form(activity)
        self.assertContains(response, 'name="_version"')
        self.assertEqual(response.context["version"], activity.updated_at.isoformat())

    def test_saving_over_a_newer_version_asks_to_review_and_saves_nothing(self):
        self.login_as("matias.cavieres")
        activity = self.activity("María Pérez")
        opened = self.open_form(activity).context["version"]

        same = Activity.objects.get(pk=activity.pk)
        same.action_taken = "Cambio de otra persona"
        same.save()

        response = self.client.post(
            reverse("core:actividades_update", args=[activity.pk]),
            self.post_data(activity, opened, contact_name="Cambio mío"),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Otra persona modificó este registro")
        activity.refresh_from_db()
        self.assertEqual(activity.contact_name, "María Pérez")
        self.assertEqual(activity.action_taken, "Cambio de otra persona")
        self.assertContains(response, "Cambio mío")

        retry = self.client.post(
            reverse("core:actividades_update", args=[activity.pk]),
            self.post_data(activity, response.context["version"], contact_name="Cambio mío"),
        )
        self.assertEqual(retry.status_code, 302)
        activity.refresh_from_db()
        self.assertEqual(activity.contact_name, "Cambio mío")


class EvidenceEditTests(PortalTestCase):
    def evidence_data(self, evidence, **changes):
        data = {
            "activity": evidence.activity_id,
            "unique_code": evidence.unique_code,
            "author_officer": evidence.author_officer_id,
        }
        data.update(changes)
        return data

    def test_unique_code_is_asked_on_creation_but_cannot_change_afterwards(self):
        self.login_as("matias.cavieres")
        evidence = Evidence.objects.filter(
            unique_code__startswith="EVD-NORTE-", deleted_at__isnull=True
        ).first()
        url = reverse("core:evidencias_update", args=[evidence.pk])
        form = self.client.get(url).context["form"]
        self.assertTrue(form.fields["unique_code"].disabled)

        response = self.client.post(url, self.evidence_data(evidence, unique_code="EVD-NORTE-9999"))
        self.assertEqual(response.status_code, 302)
        evidence.refresh_from_db()
        self.assertNotEqual(evidence.unique_code, "EVD-NORTE-9999")

        create = self.client.get(reverse("core:evidencias_create")).context["form"]
        self.assertFalse(create.fields["unique_code"].disabled)

    def test_changing_the_file_of_a_reviewed_evidence_sends_it_back_to_pending(self):
        self.login_as("admin")
        evidence = Evidence.objects.filter(review_status="approved", deleted_at__isnull=True).first()
        url = reverse("core:evidencias_update", args=[evidence.pk])
        upload = SimpleUploadedFile("otro archivo.pdf", b"%PDF-1.4\nnuevo\n%%EOF\n", content_type="application/pdf")
        response = self.client.post(url, self.evidence_data(evidence, file_link=upload), follow=True)
        evidence.refresh_from_db()
        self.assertEqual(evidence.review_status, Evidence.ReviewStatus.PENDING)
        self.assertTrue(evidence.file_link.name.endswith(".pdf"))
        self.assertIn("Archivo original: otro archivo.pdf", evidence.metadata)
        self.assertContains(response, "quedó pendiente de una nueva revisión")

    def test_a_change_that_does_not_alter_the_reviewed_file_keeps_the_review(self):
        self.login_as("admin")
        evidence = Evidence.objects.filter(review_status="approved", deleted_at__isnull=True).first()
        other = evidence.author_officer.__class__.objects.filter(
            delegation=evidence.activity.delegation, status="active"
        ).exclude(pk=evidence.author_officer_id).first()
        url = reverse("core:evidencias_update", args=[evidence.pk])
        response = self.client.post(url, self.evidence_data(evidence, author_officer=other.pk))
        self.assertEqual(response.status_code, 302)
        evidence.refresh_from_db()
        self.assertEqual(evidence.review_status, Evidence.ReviewStatus.APPROVED)
        self.assertEqual(evidence.author_officer, other)


class SearchLimitTests(PortalTestCase):
    def test_only_the_first_words_of_a_long_search_are_used(self):
        self.login_as("admin")
        url = reverse("core:atencion")
        total = self.client.get(url).context["page"].paginator.count
        words = ["a"] * SEARCH_WORDS + ["palabra-que-no-existe-en-ninguna-parte"]
        response = self.client.get(url, {"q": " ".join(words)})
        self.assertEqual(response.status_code, 200)
        self.assertGreater(response.context["page"].paginator.count, 0)
        self.assertLessEqual(response.context["page"].paginator.count, total)
        self.assertEqual(self.client.get(url, {"q": "a " * 5000}).status_code, 200)


class IdParameterTests(PortalTestCase):
    def test_non_ascii_digits_are_not_taken_as_ids(self):
        self.login_as("matias.cavieres")
        for params in ({"activity": "²"}, {"activity": "٣"}, {"activity": "9" * 40}):
            with self.subTest(params=params):
                response = self.client.get(reverse("core:evidencias_create"), params)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context["form"].initial["unique_code"], "EVD-NORTE-0004")
        response = self.client.get(reverse("core:gestiones_create"), {"activity": "²"})
        self.assertEqual(response.status_code, 200)

    def test_codes_with_unexpected_numbers_do_not_break_the_suggestion(self):
        admin = self.login_as("admin")
        activity = self.activity("María Pérez")
        Evidence.objects.create(
            unique_code="EVD-NORTE-²", file_link="x", activity=activity, author_officer=self.officer("F-1001")
        )
        response = self.client.get(reverse("core:evidencias_create"), {"activity": activity.pk})
        self.assertEqual(response.context["form"].initial["unique_code"], "EVD-NORTE-0004")
        self.assertIsNotNone(admin)


class PlanningFormRuleTests(PortalTestCase):
    def setUp(self):
        self.login_as("coordinacion1")
        self.item = Item.objects.get(name="Visita Domiciliaria")
        self.period = Period.objects.get(status="active")

    def period_data(self, **changes):
        data = {
            "start_date": "2027-01-01",
            "end_date": "2027-12-31",
            "computable_days": 240,
            "status": "planned",
            "collective_threshold": "80",
            "amber_threshold": "60",
            "weighted_cap": "150",
            "parameters_version": "1",
        }
        data.update(changes)
        return data

    def assertPeriodRejected(self, field, **changes):
        response = self.client.post(reverse("core:periodos_create"), self.period_data(**changes))
        self.assertEqual(response.status_code, 200, changes)
        self.assertIn(field, response.context["form"].errors, changes)
        self.assertFalse(Period.objects.filter(start_date=changes.get("start_date", "2027-01-01")).exists())

    def test_period_thresholds_and_days_have_limits(self):
        self.assertPeriodRejected("collective_threshold", collective_threshold="0")
        self.assertPeriodRejected("collective_threshold", collective_threshold="101")
        self.assertPeriodRejected("amber_threshold", amber_threshold="-1")
        self.assertPeriodRejected("amber_threshold", amber_threshold="100", collective_threshold="100")
        self.assertPeriodRejected("weighted_cap", weighted_cap="0")
        self.assertPeriodRejected("computable_days", computable_days="0")
        self.assertPeriodRejected("computable_days", computable_days="366")

    def test_a_valid_period_is_saved(self):
        response = self.client.post(reverse("core:periodos_create"), self.period_data())
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Period.objects.filter(start_date="2027-01-01").exists())

    def test_only_one_period_can_be_current(self):
        self.assertPeriodRejected("status", status="active")
        url = reverse("core:periodos_update", args=[self.period.pk])
        data = self.period_data(
            start_date=self.period.start_date.isoformat(),
            end_date=self.period.end_date.isoformat(),
            computable_days=self.period.computable_days,
            status="active",
        )
        self.assertEqual(self.client.post(url, data).status_code, 302)
        Period.objects.filter(pk=self.period.pk).update(deleted_at=self.period.created_at)
        response = self.client.post(reverse("core:periodos_create"), self.period_data(status="active"))
        self.assertEqual(response.status_code, 302)

    def goal_data(self, **changes):
        data = {
            "item": self.item.pk,
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

    def test_goal_weight_and_version_have_limits(self):
        url = reverse("core:metas_create")
        for field, value in (("weight", "0"), ("weight", "100.5"), ("weight", "-3"), ("version", "0")):
            with self.subTest(field=field, value=value):
                response = self.client.post(url, self.goal_data(**{field: value}))
                self.assertEqual(response.status_code, 200)
                self.assertIn(field, response.context["form"].errors)
        self.assertFalse(Goal.objects.filter(unit="visitas", target_value=20, version=0).exists())

    def test_the_same_goal_cannot_be_created_twice_for_an_officer_and_period(self):
        url = reverse("core:metas_create")
        self.assertEqual(self.client.post(url, self.goal_data()).status_code, 302)
        again = self.client.post(url, self.goal_data(version="2"))
        self.assertEqual(again.status_code, 200)
        self.assertIn("item", again.context["form"].errors)
        other_item = Item.objects.create(name="Ítem distinto")
        self.assertEqual(self.client.post(url, self.goal_data(item=other_item.pk)).status_code, 302)
        other = self.officer("F-1003")
        self.assertEqual(self.client.post(url, self.goal_data(officer=other.pk)).status_code, 302)

    def test_editing_a_goal_does_not_clash_with_itself(self):
        goal = Goal.objects.filter(officer__isnull=False).first()
        url = reverse("core:metas_update", args=[goal.pk])
        response = self.client.post(
            url,
            self.goal_data(
                item=goal.item_id,
                period=goal.period_id,
                officer=goal.officer_id,
                target_value=str(goal.target_value),
                unit=goal.unit,
                weight=str(goal.weight),
                version=str(goal.version),
            ),
        )
        self.assertEqual(response.status_code, 302)

    def test_adjustment_value_is_a_percentage_above_zero(self):
        url = reverse("core:ajustes_create")
        base = {
            "officer": self.officer("F-1001").pk,
            "kind": "bonus",
            "period": self.period.pk,
            "reason": "Prueba de límites",
        }
        for value in ("0", "-5", "100.01", "250"):
            with self.subTest(value=value):
                response = self.client.post(url, {**base, "percentage_value": value})
                self.assertEqual(response.status_code, 200)
                self.assertIn("percentage_value", response.context["form"].errors)
        self.assertFalse(Adjustment.objects.filter(reason="Prueba de límites").exists())
        self.assertEqual(self.client.post(url, {**base, "percentage_value": "100"}).status_code, 302)

    def test_indicator_numbers_cannot_be_negative(self):
        self.login_as("admin")
        goal = Goal.objects.filter(period__status="active", officer__isnull=False).first()
        url = reverse("core:indicadores_create")
        for field in ("progress", "compliance", "weighting"):
            with self.subTest(field=field):
                data = {"goal": goal.pk, "progress": "10", "compliance": "70", "weighting": "100"}
                data[field] = "-1"
                response = self.client.post(url, data)
                self.assertEqual(response.status_code, 200)
                self.assertIn(field, response.context["form"].errors)
        self.assertFalse(Indicator.objects.filter(goal=goal, compliance=Decimal("-1")).exists())
        data = {"goal": goal.pk, "progress": "30", "compliance": "120", "weighting": "100"}
        self.assertEqual(self.client.post(url, data).status_code, 302)
