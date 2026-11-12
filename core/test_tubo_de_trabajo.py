"""Versión 32: la casilla «ingresa al tubo de trabajo» crea el compromiso en la agenda colectiva."""
from datetime import timedelta

from django.urls import reverse

from core.commitments import STATUS_EVENT, history_of
from core.models import AuditLog
from core.testing import PortalTestCase, portal_today
from operations.models import Activity, Commitment
from organization.models import Delegation, Territory


class PipelineBase(PortalTestCase):
    """Matías Cavieres (funcionario de la Norte) registra atenciones; el territorio 1 de la Norte y el de la Sur sirven de ejemplo."""

    def setUp(self):
        self.login_as("matias.cavieres")
        self.north = Delegation.objects.get(name="Delegación Norte")
        self.south = Delegation.objects.get(name="Delegación Sur")
        self.territory = Territory.objects.get(name="Territorio 1", delegation=self.north)
        self.other_territory = Territory.objects.get(name="Territorio 1", delegation=self.south)
        self.due = portal_today() + timedelta(days=10)

    def register(self, **changes):
        data = self.intake_data(request_description="Solicita poda de árbol en el pasaje.")
        data.update(changes)
        return self.client.post(reverse("core:actividades_create"), data)

    def piped(self, **changes):
        data = {"added_to_pipeline": "on", "due_date": self.due.isoformat(), "territory": self.territory.pk}
        data.update(changes)
        return self.register(**data)

    def newest(self):
        return Activity.objects.order_by("-pk").first()

    def refused(self, response, field, text):
        self.assertEqual(response.status_code, 200)
        self.assertIn(field, response.context["form"].errors)
        self.assertContains(response, text)


class PipelineCreationTests(PipelineBase):
    """El compromiso nace con lo que dice la atención más la fecha y el territorio que se piden en el formulario."""

    def test_an_attention_without_the_box_creates_no_commitment(self):
        before = Commitment.objects.count()
        response = self.register()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Commitment.objects.count(), before)
        self.assertIsNone(self.newest().commitment)

    def test_marking_the_box_creates_the_commitment_in_the_agenda(self):
        before = Commitment.objects.count()
        response = self.piped()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Commitment.objects.count(), before + 1)
        activity = self.newest()
        self.assertTrue(activity.added_to_pipeline)
        self.assertEqual(activity.commitment, Commitment.objects.order_by("-pk").first())

    def test_the_commitment_takes_its_data_from_the_attention(self):
        self.piped()
        activity = self.newest()
        commitment = activity.commitment
        self.assertEqual(commitment.requester, activity.contact_name)
        self.assertEqual(commitment.description, activity.request_description)
        self.assertEqual(commitment.request_date, activity.date)
        self.assertEqual(commitment.delegation, activity.delegation)
        self.assertEqual(commitment.responsible_officer, activity.author_officer)
        self.assertEqual(commitment.territory, self.territory)
        self.assertEqual(commitment.due_date, self.due)
        self.assertEqual(commitment.status, Commitment.Status.SUBMITTED)
        self.assertEqual(commitment.source, f"Atención ATN{activity.pk:05d}")

    def test_the_first_state_goes_to_the_history_and_the_creation_to_the_audit(self):
        self.piped()
        commitment = self.newest().commitment
        self.assertEqual([entry["new"] for entry in history_of(commitment)], ["Ingresado"])
        self.assertTrue(AuditLog.objects.filter(event=STATUS_EVENT, record_id=commitment.pk).exists())
        self.assertTrue(
            AuditLog.objects.filter(event="Registro creado", affected_entity="Commitment", record_id=commitment.pk).exists()
        )

    def test_the_user_is_told_that_the_commitment_was_created(self):
        response = self.piped()
        follow = self.client.get(response.url)
        self.assertContains(follow, "Se creó el compromiso en la Agenda colectiva")

    def test_the_commitment_shows_up_in_the_agenda_of_the_delegation(self):
        self.piped(requester="Rosa Agenda")
        listing = self.client.get(reverse("core:agenda_list"), {"q": "Rosa Agenda"})
        self.assertEqual(listing.context["page"].paginator.count, 1)

    def test_a_rejected_attention_creates_neither_the_attention_nor_the_commitment(self):
        activities, commitments = Activity.objects.count(), Commitment.objects.count()
        response = self.piped(request_description="")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Activity.objects.count(), activities)
        self.assertEqual(Commitment.objects.count(), commitments)

    def test_the_two_fields_are_ignored_when_the_box_is_not_marked(self):
        before = Commitment.objects.count()
        response = self.register(due_date="2000-01-01", territory=self.other_territory.pk)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Commitment.objects.count(), before)
        self.assertFalse(self.newest().added_to_pipeline)


class PipelineValidationTests(PipelineBase):
    """Con la casilla marcada, la fecha comprometida y el territorio son obligatorios y deben tener sentido."""

    def test_the_due_date_is_required_when_the_box_is_marked(self):
        response = self.piped(due_date="")
        self.refused(response, "due_date", "Indica la fecha comprometida")

    def test_the_territory_is_required_when_the_box_is_marked(self):
        response = self.piped(territory="")
        self.refused(response, "territory", "Elige el territorio")

    def test_the_due_date_cannot_be_before_the_attention_date(self):
        response = self.piped(due_date=(portal_today() - timedelta(days=1)).isoformat())
        self.refused(response, "due_date", "no puede ser anterior a la fecha de la atención")

    def test_the_due_date_can_be_the_same_day_as_the_attention(self):
        response = self.piped(due_date=portal_today().isoformat())
        self.assertEqual(response.status_code, 302)

    def test_the_territory_must_belong_to_the_delegation_of_the_attention(self):
        response = self.piped(territory=self.other_territory.pk)
        self.assertEqual(response.status_code, 200)
        self.assertIn("territory", response.context["form"].errors)

    def test_the_territory_list_only_offers_the_territories_of_the_delegation(self):
        form = self.client.get(reverse("core:actividades_create")).context["form"]
        offered = set(form.fields["territory"].queryset.values_list("pk", flat=True))
        self.assertIn(self.territory.pk, offered)
        self.assertNotIn(self.other_territory.pk, offered)

    def test_an_archived_territory_is_not_offered(self):
        from django.utils import timezone

        Territory.objects.filter(pk=self.territory.pk).update(deleted_at=timezone.now())
        form = self.client.get(reverse("core:actividades_create")).context["form"]
        self.assertNotIn(self.territory.pk, set(form.fields["territory"].queryset.values_list("pk", flat=True)))


class PipelineFormTests(PipelineBase):
    """El formulario trae los dos campos, ocultos hasta marcar la casilla (lo hace `widgets.js`)."""

    def test_the_form_has_the_two_fields_right_after_the_box(self):
        form = self.client.get(reverse("core:actividades_create")).context["form"]
        names = list(form.fields)
        self.assertEqual(names[names.index("added_to_pipeline") + 1 : names.index("added_to_pipeline") + 3], ["due_date", "territory"])

    def test_the_fields_are_tied_to_the_box_and_asked_when_it_is_marked(self):
        form = self.client.get(reverse("core:actividades_create")).context["form"]
        for name in ("due_date", "territory"):
            attrs = form.fields[name].widget.attrs
            self.assertEqual(attrs["data-show-when"], "id_requires_visit,id_added_to_pipeline")
            self.assertEqual(attrs["data-required-when-shown"], "1")

    def test_the_page_shows_the_labels_of_the_two_fields(self):
        page = self.client.get(reverse("core:actividades_create"))
        self.assertContains(page, "Fecha comprometida")
        self.assertContains(page, "Territorio del compromiso")

    def test_the_box_help_says_what_will_be_asked(self):
        page = self.client.get(reverse("core:actividades_create"))
        self.assertContains(page, "se pide la fecha comprometida y el territorio")

    def test_the_script_hides_and_shows_the_fields_with_the_box(self):
        from pathlib import Path

        text = (Path(__file__).parent / "static/core/js/widgets.js").read_text(encoding="utf-8")
        self.assertIn("data-show-when", text.replace("dataset.showWhen", "data-show-when"))
        self.assertIn("setUpShowWhen", text)


class PipelineEditTests(PipelineBase):
    """Al editar una atención no se duplica el compromiso, y una marcada de antes puede seguir editándose."""

    def edit(self, activity, **changes):
        data = self.activity_form_data(activity)
        data.update(changes)
        return self.client.post(reverse("core:actividades_update", args=[activity.pk]), data)

    def fresh_activity(self):
        self.register()
        return self.newest()

    def test_marking_the_box_when_editing_creates_the_commitment(self):
        activity = self.fresh_activity()
        response = self.edit(
            activity, added_to_pipeline="on", due_date=self.due.isoformat(), territory=self.territory.pk
        )
        self.assertEqual(response.status_code, 302)
        activity.refresh_from_db()
        self.assertEqual(activity.commitment.due_date, self.due)

    def test_marking_the_box_when_editing_asks_for_the_two_fields(self):
        activity = self.fresh_activity()
        response = self.edit(activity, added_to_pipeline="on")
        self.refused(response, "due_date", "Indica la fecha comprometida")
        activity.refresh_from_db()
        self.assertIsNone(activity.commitment)
        self.assertFalse(activity.added_to_pipeline)

    def test_an_attention_that_already_has_its_commitment_does_not_ask_again(self):
        self.piped()
        activity = self.newest()
        form = self.client.get(reverse("core:actividades_update", args=[activity.pk])).context["form"]
        self.assertNotIn("due_date", form.fields)
        self.assertNotIn("territory", form.fields)

    def test_editing_an_attention_with_its_commitment_does_not_create_another(self):
        self.piped()
        activity = self.newest()
        commitments = Commitment.objects.count()
        response = self.edit(activity, request_description="Descripción corregida.")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Commitment.objects.count(), commitments)
        activity.refresh_from_db()
        self.assertEqual(activity.request_description, "Descripción corregida.")

    def test_unmarking_the_box_keeps_the_commitment_in_the_agenda(self):
        self.piped()
        activity = self.newest()
        data = self.activity_form_data(activity)
        data.pop("added_to_pipeline", None)
        self.client.post(reverse("core:actividades_update", args=[activity.pk]), data)
        activity.refresh_from_db()
        self.assertFalse(activity.added_to_pipeline)
        self.assertIsNotNone(activity.commitment)
        self.assertTrue(Commitment.objects.filter(pk=activity.commitment_id, deleted_at__isnull=True).exists())

    def test_an_attention_marked_before_without_commitment_can_be_edited_without_the_dates(self):
        activity = self.fresh_activity()
        Activity.objects.filter(pk=activity.pk).update(added_to_pipeline=True)
        activity.refresh_from_db()
        commitments = Commitment.objects.count()
        response = self.edit(activity, request_description="Otro texto.")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Commitment.objects.count(), commitments)

    def test_an_attention_marked_before_can_create_its_commitment_if_both_data_are_given(self):
        activity = self.fresh_activity()
        Activity.objects.filter(pk=activity.pk).update(added_to_pipeline=True)
        activity.refresh_from_db()
        response = self.edit(activity, due_date=self.due.isoformat(), territory=self.territory.pk)
        self.assertEqual(response.status_code, 302)
        activity.refresh_from_db()
        self.assertIsNotNone(activity.commitment)

    def test_an_attention_marked_before_needs_both_data_if_only_one_is_given(self):
        activity = self.fresh_activity()
        Activity.objects.filter(pk=activity.pk).update(added_to_pipeline=True)
        activity.refresh_from_db()
        response = self.edit(activity, due_date=self.due.isoformat())
        self.refused(response, "territory", "completa la fecha comprometida y el territorio")


class PipelineModelTests(PortalTestCase):
    """El enlace entre la atención y su compromiso."""

    def test_the_link_is_not_editable_and_is_kept_if_the_commitment_is_removed(self):
        field = Activity._meta.get_field("commitment")
        self.assertFalse(field.editable)
        self.assertTrue(field.null)
        self.assertEqual(field.remote_field.on_delete.__name__, "SET_NULL")

    def test_create_commitment_does_not_create_a_second_one_for_the_same_attention(self):
        from operations import pipeline

        activity = Activity.objects.filter(delegation__name="Delegación Norte").first()
        territory = Territory.objects.filter(delegation=activity.delegation).first()
        first = pipeline.create_commitment(activity, portal_today() + timedelta(days=3), territory)
        second = pipeline.create_commitment(activity, portal_today() + timedelta(days=9), territory)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(Commitment.objects.filter(source__startswith=f"Atención ATN{activity.pk:05d}").count(), 1)
