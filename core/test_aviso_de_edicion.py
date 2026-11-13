"""Versión 43: aviso mientras se edita. Si otra persona guarda el mismo registro con el formulario abierto,
el formulario lo averigua (por el aviso del WebSocket o cada cierto tiempo) y muestra quién y qué cambió."""
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone

from core.audit import log_event
from core.testing import PortalTestCase
from operations.models import Activity


class WatchBase(PortalTestCase):

    def setUp(self):
        self.activity_obj = self.activity("María Pérez")
        self.url = reverse("core:actividades_check", args=[self.activity_obj.pk])

    def opened_version(self):
        self.login_as("matias.cavieres")
        response = self.client.get(reverse("core:actividades_update", args=[self.activity_obj.pk]))
        self.assertEqual(response.status_code, 200)
        return response.context["version"]

    def change_by_someone_else(self):
        other = User.objects.get(username="jefatura1")
        before = Activity.objects.get(pk=self.activity_obj.pk)
        changed = Activity.objects.get(pk=self.activity_obj.pk)
        changed.action_taken = "Llamada hecha por otra persona"
        changed.save()
        log_event(other, "Registro modificado", changed, previous="Acción realizada: (vacío)", new="Acción realizada: Llamada hecha por otra persona")
        return before, changed


class FormMarkupTests(WatchBase):

    def test_the_edit_form_tells_the_browser_where_to_ask_and_which_channel_to_listen_to(self):
        self.login_as("matias.cavieres")
        for suffix in ("", "?modal=1"):
            response = self.client.get(reverse("core:actividades_update", args=[self.activity_obj.pk]) + suffix)
            self.assertContains(response, f'data-watch-url="{self.url}"')
            self.assertContains(response, 'data-watch-slug="actividades"')

    def test_the_create_form_has_nothing_to_watch(self):
        self.login_as("matias.cavieres")
        response = self.client.get(reverse("core:actividades_create") + "?modal=1")
        self.assertNotContains(response, "data-watch-url")

    def test_the_script_is_loaded_on_every_page(self):
        self.login_as("matias.cavieres")
        response = self.client.get(reverse("core:actividades_detail", args=[self.activity_obj.pk]))
        self.assertContains(response, "core/js/edit-watch.js")


class CheckTests(WatchBase):

    def test_an_unchanged_record_is_not_stale(self):
        version = self.opened_version()
        response = self.client.get(self.url, {"abierta": version})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"stale": False})

    def test_after_someone_else_saves_it_says_who_and_what_changed(self):
        version = self.opened_version()
        self.change_by_someone_else()
        data = self.client.get(self.url, {"abierta": version}).json()
        self.assertTrue(data["stale"])
        self.assertFalse(data["gone"])
        self.assertIn("Otra persona modificó este registro mientras lo editas", data["message"])
        self.assertIn("jefatura1", data["message"])
        self.assertIn("Llamada hecha por otra persona", data["message"])
        self.assertIn("Lo que escribiste sigue aquí", data["message"])

    def test_the_answer_does_not_carry_the_record(self):
        version = self.opened_version()
        self.change_by_someone_else()
        data = self.client.get(self.url, {"abierta": version}).json()
        self.assertEqual(set(data), {"stale", "gone", "message"})

    def test_without_a_version_to_compare_it_is_not_stale(self):
        self.opened_version()
        self.change_by_someone_else()
        self.assertEqual(self.client.get(self.url).json(), {"stale": False})

    def test_an_archived_record_is_reported_as_gone(self):
        version = self.opened_version()
        Activity.objects.filter(pk=self.activity_obj.pk).update(deleted_at=timezone.now())
        data = self.client.get(self.url, {"abierta": version}).json()
        self.assertTrue(data["stale"] and data["gone"])
        self.assertIn("archivó", data["message"])

    def test_a_record_out_of_reach_is_reported_as_gone_without_details(self):
        self.login_as("matias.cavieres")
        other = Activity.objects.exclude(delegation=self.activity_obj.delegation).first()
        data = self.client.get(reverse("core:actividades_check", args=[other.pk]), {"abierta": "x"}).json()
        self.assertTrue(data["gone"])
        self.assertNotIn(other.contact_name, data["message"])

    def test_someone_who_cannot_edit_gets_a_403(self):
        self.login_as("consulta1")
        self.assertEqual(self.client.get(self.url, {"abierta": "x"}).status_code, 403)

    def test_it_asks_for_a_session(self):
        response = self.client.get(self.url, {"abierta": "x"})
        self.assertEqual(response.status_code, 302)
        self.assertIn("next=", response.url)

    def test_saving_still_asks_to_review_after_the_warning(self):
        version = self.opened_version()
        self.change_by_someone_else()
        response = self.client.post(
            reverse("core:actividades_update", args=[self.activity_obj.pk]),
            self.activity_form_data(self.activity_obj, _version=version, contact_name="Cambio mío"),
        )
        self.assertContains(response, "Otra persona modificó este registro")
        self.activity_obj.refresh_from_db()
        self.assertNotEqual(self.activity_obj.contact_name, "Cambio mío")

    def test_every_editable_crud_has_its_check_route(self):
        from core.crud import registry

        for crud in registry.all():
            if crud.allow_change:
                self.assertTrue(crud.url("check", 1).endswith("/revisar/"), crud.slug)
