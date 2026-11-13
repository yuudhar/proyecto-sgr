"""Versión 43: comentarios con autor y fecha en la ficha de una atención, un compromiso o una evidencia."""
from datetime import timedelta
from unittest import mock

from django.contrib.auth.models import Group, User
from django.urls import reverse
from django.utils import timezone

from core.models import AuditLog, Comment
from core.test_cartas_y_compromisos import make_commitment
from core.testing import PortalTestCase
from evidence.models import Evidence
from operations.models import Activity
from organization.models import Territory


class CommentBase(PortalTestCase):

    def setUp(self):
        self.activity_obj = self.activity("María Pérez")
        self.detail = reverse("core:actividades_detail", args=[self.activity_obj.pk])
        self.add_url = reverse("core:actividades_comment", args=[self.activity_obj.pk])

    def comment(self, text="Falta el acta firmada.", author="matias.cavieres", record=None):
        record = record or self.activity_obj
        return Comment.objects.create(
            entity=record.__class__.__name__,
            record_id=record.pk,
            delegation_id=getattr(record, "delegation_id", None),
            author=User.objects.get(username=author),
            text=text,
        )


class SectionTests(CommentBase):

    def test_the_activity_file_has_the_comments_section_with_a_form(self):
        self.login_as("matias.cavieres")
        response = self.client.get(self.detail)
        self.assertContains(response, 'id="comentarios"')
        self.assertContains(response, "Este registro aún no tiene comentarios.")
        self.assertContains(response, f'action="{self.add_url}"')
        self.assertContains(response, "data-keep-draft")

    def test_commitments_of_the_agenda_and_of_the_field_have_it_too(self):
        territory = Territory.objects.filter(delegation=self.north).first()
        agenda = make_commitment(self.north, self.officer("F-1001"), territory, "Vecina Uno", physical=False)
        field = make_commitment(self.north, self.officer("F-1001"), territory, "Vecina Dos", physical=True)
        self.login_as("matias.cavieres")
        self.assertContains(self.client.get(reverse("core:agenda_detail", args=[agenda.pk])), 'id="comentarios"')
        self.assertContains(self.client.get(reverse("core:compromisos_detail", args=[field.pk])), 'id="comentarios"')

    def test_the_evidence_file_has_it(self):
        self.login_as("admin")
        evidence = Evidence.objects.first()
        self.assertContains(self.client.get(reverse("core:evidencias_detail", args=[evidence.pk])), 'id="comentarios"')

    def test_other_files_do_not_have_it(self):
        self.login_as("admin")
        from planning.models import Period

        period = Period.objects.first()
        self.assertNotContains(self.client.get(reverse("core:periodos_detail", args=[period.pk])), 'id="comentarios"')

    def test_comments_are_shown_oldest_first_with_author_and_date(self):
        first = self.comment("Primero", "matias.cavieres")
        second = self.comment("Segundo", "jefatura1")
        Comment.objects.filter(pk=first.pk).update(created_at=timezone.now() - timedelta(days=1))
        self.login_as("matias.cavieres")
        response = self.client.get(self.detail)
        body = response.content.decode()
        self.assertLess(body.index("Primero"), body.index("Segundo"))
        self.assertContains(response, "2 comentarios")
        self.assertContains(response, "jefatura1")

    def test_the_comments_of_one_record_do_not_show_on_another(self):
        self.comment("Solo para María")
        other = Activity.objects.exclude(pk=self.activity_obj.pk).filter(delegation=self.north).first()
        self.login_as("matias.cavieres")
        response = self.client.get(reverse("core:actividades_detail", args=[other.pk]))
        self.assertNotContains(response, "Solo para María")

    def test_the_text_is_escaped(self):
        self.comment("<script>alert(1)</script>")
        self.login_as("matias.cavieres")
        response = self.client.get(self.detail)
        self.assertNotContains(response, "<script>alert(1)</script>")
        self.assertContains(response, "&lt;script&gt;alert(1)&lt;/script&gt;")

    def test_an_archived_record_shows_its_comments_but_no_form(self):
        self.comment("Antiguo")
        Activity.objects.filter(pk=self.activity_obj.pk).update(deleted_at=timezone.now())
        self.login_as("admin")
        response = self.client.get(self.detail)
        self.assertContains(response, "Antiguo")
        self.assertNotContains(response, f'action="{self.add_url}"')


class AddTests(CommentBase):

    def test_a_comment_is_saved_with_author_record_delegation_and_audit(self):
        user = self.login_as("matias.cavieres")
        response = self.client.post(self.add_url, {"text": "  Llamé a la presidenta.  "})
        self.assertRedirects(response, self.detail + "#comentarios", fetch_redirect_response=False)
        saved = Comment.objects.get()
        self.assertEqual(
            (saved.entity, saved.record_id, saved.author, saved.text, saved.delegation_id),
            ("Activity", self.activity_obj.pk, user, "Llamé a la presidenta.", self.activity_obj.delegation_id),
        )
        entry = AuditLog.objects.get(event="Comentario agregado")
        self.assertEqual((entry.affected_entity, entry.record_id, entry.user), ("Comment", saved.pk, user))
        self.assertIn(f"Activity#{self.activity_obj.pk}", entry.new_value)

    def test_the_comment_shows_on_the_file_with_the_name_of_who_wrote_it(self):
        self.login_as("matias.cavieres")
        self.client.post(self.add_url, {"text": "Quedó pendiente la firma."})
        self.login_as("jefatura1")
        response = self.client.get(self.detail)
        self.assertContains(response, "Quedó pendiente la firma.")

    def test_an_empty_comment_is_refused(self):
        self.login_as("matias.cavieres")
        for text in ("", "   \n  "):
            response = self.client.post(self.add_url, {"text": text}, follow=True)
            self.assertContains(response, "Escribe el comentario antes de enviarlo.")
        self.assertEqual(Comment.objects.count(), 0)

    def test_a_comment_over_the_limit_is_refused(self):
        self.login_as("matias.cavieres")
        response = self.client.post(self.add_url, {"text": "x" * (Comment.MAX_LENGTH + 1)}, follow=True)
        self.assertContains(response, "1000 caracteres")
        self.assertEqual(Comment.objects.count(), 0)
        self.client.post(self.add_url, {"text": "x" * Comment.MAX_LENGTH})
        self.assertEqual(Comment.objects.count(), 1)

    def test_someone_who_only_consults_sees_them_but_cannot_comment(self):
        self.comment("Visible")
        self.login_as("consulta1")
        response = self.client.get(self.detail)
        self.assertContains(response, "Visible")
        self.assertNotContains(response, f'action="{self.add_url}"')
        self.assertEqual(self.client.post(self.add_url, {"text": "No debería"}).status_code, 403)
        self.assertEqual(Comment.objects.count(), 1)

    def test_nobody_comments_on_a_record_of_another_delegation(self):
        other = Activity.objects.exclude(delegation=self.activity_obj.delegation).first()
        self.login_as("matias.cavieres")
        response = self.client.post(reverse("core:actividades_comment", args=[other.pk]), {"text": "Ajeno"})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(Comment.objects.count(), 0)

    def test_an_archived_record_takes_no_comments(self):
        Activity.objects.filter(pk=self.activity_obj.pk).update(deleted_at=timezone.now())
        self.login_as("admin")
        self.assertEqual(self.client.post(self.add_url, {"text": "Tarde"}).status_code, 403)

    def test_it_needs_post_and_a_session(self):
        self.assertEqual(self.client.post(self.add_url, {"text": "x"}).status_code, 302)
        self.login_as("matias.cavieres")
        self.assertEqual(self.client.get(self.add_url).status_code, 405)

    def test_a_commitment_and_an_evidence_take_comments_too(self):
        territory = Territory.objects.filter(delegation=self.north).first()
        commitment = make_commitment(self.north, self.officer("F-1001"), territory, "Vecina Tres", physical=True)
        self.login_as("matias.cavieres")
        self.client.post(reverse("core:compromisos_comment", args=[commitment.pk]), {"text": "Visita lunes"})
        self.assertEqual(Comment.objects.get().entity, "Commitment")
        evidence = Evidence.objects.filter(
            activity__delegation=self.north, deleted_at__isnull=True, activity__deleted_at__isnull=True
        ).order_by("pk").first()
        response = self.client.post(reverse("core:evidencias_comment", args=[evidence.pk]), {"text": "Foto borrosa"})
        self.assertEqual(response.status_code, 302, response.status_code)
        self.assertEqual(Comment.objects.filter(entity="Evidence").count(), 1)


class DeleteTests(CommentBase):

    def delete_url(self, comment):
        return reverse("core:actividades_comment_delete", args=[self.activity_obj.pk, comment.pk])

    def test_the_author_deletes_their_own_comment(self):
        comment = self.comment()
        self.login_as("matias.cavieres")
        response = self.client.post(self.delete_url(comment))
        self.assertRedirects(response, self.detail + "#comentarios", fetch_redirect_response=False)
        comment.refresh_from_db()
        self.assertIsNotNone(comment.deleted_at)
        self.assertNotContains(self.client.get(self.detail), "Falta el acta firmada.")
        self.assertTrue(AuditLog.objects.filter(event="Comentario eliminado", record_id=comment.pk).exists())

    def test_someone_else_cannot_delete_it_and_does_not_see_the_button(self):
        comment = self.comment(author="matias.cavieres")
        self.login_as("jefatura1")
        self.assertNotContains(self.client.get(self.detail), self.delete_url(comment))
        self.assertEqual(self.client.post(self.delete_url(comment)).status_code, 403)
        comment.refresh_from_db()
        self.assertIsNone(comment.deleted_at)

    def test_a_super_user_can_delete_any_comment(self):
        comment = self.comment(author="matias.cavieres")
        self.login_as("admin")
        self.assertContains(self.client.get(self.detail), self.delete_url(comment))
        self.client.post(self.delete_url(comment))
        comment.refresh_from_db()
        self.assertIsNotNone(comment.deleted_at)

    def test_a_comment_of_another_record_cannot_be_deleted_through_this_one(self):
        other = Activity.objects.exclude(pk=self.activity_obj.pk).filter(delegation=self.north).first()
        comment = self.comment(record=other)
        self.login_as("admin")
        self.assertEqual(self.client.post(self.delete_url(comment)).status_code, 404)

    def test_a_deleted_comment_cannot_be_deleted_again(self):
        comment = self.comment()
        self.login_as("matias.cavieres")
        self.client.post(self.delete_url(comment))
        self.assertEqual(self.client.post(self.delete_url(comment)).status_code, 404)


class PermissionTests(PortalTestCase):

    def codes(self, role):
        group = Group.objects.get(name=role)
        return {p.codename for p in group.permissions.filter(content_type__app_label="core", content_type__model="comment")}

    def test_the_roles_that_work_on_records_can_comment(self):
        for role in ("Coordinación", "Jefatura", "Funcionario", "Verificador"):
            self.assertEqual(self.codes(role), {"add_comment", "view_comment"}, role)

    def test_consulta_only_reads_and_the_client_gets_nothing(self):
        self.assertEqual(self.codes("Consulta"), {"view_comment"})
        self.assertEqual(self.codes("Cliente"), set())

    def test_nobody_can_edit_a_comment(self):
        for role in ("Coordinación", "Jefatura", "Funcionario", "Verificador", "Consulta"):
            self.assertNotIn("change_comment", self.codes(role))


class LiveTests(CommentBase):

    def test_a_comment_warns_the_delegation_that_something_changed(self):
        self.login_as("matias.cavieres")
        with mock.patch("websocket.signals.publish_live_changed") as publish:
            with self.captureOnCommitCallbacks(execute=True):
                self.client.post(self.add_url, {"text": "En vivo"})
        labels = [call.args[0] for call in publish.call_args_list]
        self.assertIn("core.comment", labels)
        call = next(c for c in publish.call_args_list if c.args[0] == "core.comment")
        self.assertIn(self.activity_obj.delegation_id, call.args[1:])

    def test_the_live_refresh_keeps_what_is_being_typed(self):
        script = (self.project_root() / "core" / "static" / "core" / "js" / "live-updates.js").read_text(encoding="utf-8")
        for piece in ("keepDrafts(region)", "restoreDrafts(drafts)", "[data-keep-draft]"):
            self.assertIn(piece, script)

    def project_root(self):
        from django.conf import settings

        return settings.BASE_DIR
