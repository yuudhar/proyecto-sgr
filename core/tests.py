from io import StringIO

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from evidence.models import Evidence, Validation
from operations.models import Activity
from organization.models import Item, Officer


class AdminRegressionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo_data", stdout=StringIO())

    def login_as(self, username):
        user = User.objects.get(username=username)
        self.client.force_login(user)
        return user

    def inline_data(self, evidence, reviewer):
        return {
            "unique_code": evidence.unique_code,
            "file_link": evidence.file_link,
            "review_status": evidence.review_status,
            "activity": evidence.activity_id,
            "author_officer": evidence.author_officer_id,
            "validations-TOTAL_FORMS": "1",
            "validations-INITIAL_FORMS": "0",
            "validations-MIN_NUM_FORMS": "0",
            "validations-MAX_NUM_FORMS": "1000",
            "validations-0-decision": Validation.Decision.APPROVED,
            "validations-0-reviewer_officer": reviewer.pk,
            "validations-0-result": "Revisión de prueba",
            "_save": "Guardar",
        }

    def test_inline_only_offers_reviewers_from_own_delegation(self):
        for username, code in (
            ("matias.cavieres", "EVD-NORTE-0001"),
            ("matias.quiroz", "EVD-SUR-0002"),
        ):
            with self.subTest(username=username):
                user = self.login_as(username)
                evidence = Evidence.objects.get(unique_code=code)
                response = self.client.get(
                    reverse("admin:evidence_evidence_change", args=[evidence.pk])
                )
                self.assertEqual(response.status_code, 200)
                form = response.context["inline_admin_formsets"][0].formset.empty_form
                reviewers = form.fields["reviewer_officer"].queryset
                self.assertTrue(reviewers.exists())
                self.assertFalse(
                    reviewers.exclude(delegation=user.profile.officer.delegation).exists()
                )

    def test_inline_rejects_forged_foreign_reviewer_post(self):
        for username, code, foreign_id in (
            ("matias.cavieres", "EVD-NORTE-0001", "F-2001"),
            ("matias.quiroz", "EVD-SUR-0002", "F-1001"),
        ):
            with self.subTest(username=username):
                self.login_as(username)
                evidence = Evidence.objects.get(unique_code=code)
                reviewer = Officer.objects.get(institutional_id=foreign_id)
                response = self.client.post(
                    reverse("admin:evidence_evidence_change", args=[evidence.pk]),
                    self.inline_data(evidence, reviewer),
                )
                self.assertEqual(response.status_code, 200)
                formset = response.context["inline_admin_formsets"][0].formset
                errors = formset.forms[0].errors.as_data()
                self.assertEqual(errors["reviewer_officer"][0].code, "invalid_choice")
                self.assertFalse(Validation.objects.filter(evidence=evidence).exists())

    def test_inline_accepts_reviewer_from_own_delegation(self):
        for username, code in (
            ("matias.cavieres", "EVD-NORTE-0001"),
            ("matias.quiroz", "EVD-SUR-0002"),
        ):
            with self.subTest(username=username):
                user = self.login_as(username)
                evidence = Evidence.objects.get(unique_code=code)
                response = self.client.post(
                    reverse("admin:evidence_evidence_change", args=[evidence.pk]),
                    self.inline_data(evidence, user.profile.officer),
                )
                self.assertEqual(response.status_code, 302)
                self.assertTrue(
                    Validation.objects.filter(
                        evidence=evidence, reviewer_officer=user.profile.officer
                    ).exists()
                )

    def test_inline_excludes_archived_reviewers(self):
        self.login_as("matias.cavieres")
        archived = Officer.objects.get(institutional_id="F-1002")
        archived.deleted_at = timezone.now()
        archived.save()
        evidence = Evidence.objects.get(unique_code="EVD-NORTE-0001")
        response = self.client.post(
            reverse("admin:evidence_evidence_change", args=[evidence.pk]),
            self.inline_data(evidence, archived),
        )
        self.assertEqual(response.status_code, 200)
        formset = response.context["inline_admin_formsets"][0].formset
        self.assertIn("reviewer_officer", formset.forms[0].errors)
        self.assertFalse(Validation.objects.filter(evidence=evidence).exists())

    def test_superuser_keeps_access_to_reviewers_in_both_delegations(self):
        self.login_as("admin")
        evidence = Evidence.objects.get(unique_code="EVD-NORTE-0001")
        response = self.client.get(
            reverse("admin:evidence_evidence_change", args=[evidence.pk])
        )
        form = response.context["inline_admin_formsets"][0].formset.empty_form
        delegations = set(
            form.fields["reviewer_officer"].queryset.values_list(
                "delegation__name", flat=True
            )
        )
        self.assertEqual(delegations, {"Delegación Norte", "Delegación Sur"})

    def test_archived_lists_work_and_preserve_delegation_scope(self):
        for username in ("admin", "matias.cavieres", "matias.quiroz"):
            user = self.login_as(username)
            for model, urlname, lookup in (
                (Activity, "admin:operations_activity_changelist", "delegation"),
                (Evidence, "admin:evidence_evidence_changelist", "activity__delegation"),
            ):
                for value in (None, "0", "1"):
                    with self.subTest(username=username, model=model, flag=value):
                        params = {} if value is None else {"show_archived": value}
                        response = self.client.get(reverse(urlname), params)
                        self.assertEqual(response.status_code, 200)
                        expected = model.objects.all()
                        if not user.is_superuser:
                            expected = expected.filter(
                                **{lookup: user.profile.officer.delegation}
                            )
                        if value != "1":
                            expected = expected.filter(deleted_at__isnull=True)
                        cl = response.context["cl"]
                        self.assertSetEqual(
                            set(cl.queryset.values_list("pk", flat=True)),
                            set(expected.values_list("pk", flat=True)),
                        )
                        self.assertEqual("deleted_at" in cl.list_display, value == "1")

    def test_archived_search_and_existing_filters_still_work(self):
        user = self.login_as("matias.cavieres")
        response = self.client.get(
            reverse("admin:operations_activity_changelist"),
            {"show_archived": "1", "q": "Juan", "status__exact": "registered"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["cl"].result_count, 1)
        activity = response.context["cl"].queryset.get()
        self.assertIsNotNone(activity.deleted_at)
        self.assertEqual(activity.delegation, user.profile.officer.delegation)

    def test_archive_filter_is_available_on_global_catalogs(self):
        self.login_as("admin")
        item = Item.objects.first()
        item.deleted_at = timezone.now()
        item.save()
        url = reverse("admin:organization_item_changelist")
        response = self.client.get(url)
        self.assertNotIn(item, response.context["cl"].queryset)
        response = self.client.get(url, {"show_archived": "1"})
        self.assertEqual(response.status_code, 200)
        self.assertIn(item, response.context["cl"].queryset)
        self.assertContains(response, "Incluir archivados")

    def test_archive_action_does_not_modify_foreign_records(self):
        user = self.login_as("matias.cavieres")
        own = Activity.objects.filter(
            delegation=user.profile.officer.delegation, deleted_at=None
        ).first()
        foreign = Activity.objects.exclude(
            delegation=user.profile.officer.delegation
        ).filter(deleted_at=None).first()
        response = self.client.post(
            reverse("admin:operations_activity_changelist") + "?show_archived=1",
            {"action": "archive_selected", "_selected_action": [own.pk, foreign.pk]},
        )
        self.assertEqual(response.status_code, 302)
        own.refresh_from_db()
        foreign.refresh_from_db()
        self.assertIsNotNone(own.deleted_at)
        self.assertIsNone(foreign.deleted_at)
