"""Pruebas de los formularios en ventana modal (?modal=1) y de los enlaces que los abren."""

import json

from django.contrib.messages import get_messages
from django.urls import reverse

from core.models import AuditLog
from core.testing import PortalTestCase
from organization.models import Beneficiary, Delegation


class ModalFormTests(PortalTestCase):
    def modal(self, url, **params):
        return self.client.get(url, {"modal": "1", **params})

    def beneficiary_data(self, **changes):
        data = {"rut": "12.345.678-5", "name": "Pedro Pérez", "phone": "", "address": ""}
        data.update(changes)
        return data

    def test_the_create_form_comes_as_the_content_of_the_window(self):
        self.login_as("admin")
        response = self.modal(reverse("core:beneficiarios_create"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["X-Modal"], "form")
        self.assertContains(response, 'class="modal-content"')
        self.assertContains(response, 'data-validate')
        self.assertContains(response, "csrfmiddlewaretoken")
        self.assertContains(response, "Nuevo beneficiario")
        # solo el contenido de la ventana: nada de menú, barra superior ni pie de la página
        self.assertNotContains(response, "<html")
        self.assertNotContains(response, "app-shell")
        self.assertNotContains(response, "Saltar al contenido")

    def test_the_window_posts_back_to_the_same_address_with_modal(self):
        self.login_as("admin")
        response = self.modal(reverse("core:beneficiarios_create"))
        self.assertContains(response, 'action="/beneficiarios/nuevo/?modal=1"')

    def test_the_edit_form_carries_its_version_and_the_four_buttons(self):
        self.login_as("admin")
        response = self.modal(reverse("core:delegaciones_update", args=[self.north.pk]))
        self.assertEqual(response["X-Modal"], "form")
        self.assertContains(response, 'name="_version"')
        self.assertContains(response, "Editar delegación")
        for text in ("Guardar", "Guardar y agregar otro", "Eliminar", "Cancelar"):
            self.assertContains(response, text)
        self.assertContains(response, 'data-delete=')  # Eliminar pide confirmación con SweetAlert2
        self.assertContains(response, 'data-lookup-open')  # el buscador del Encargado
        self.assertContains(response, 'type="color"')

    def test_without_modal_the_page_is_the_same_as_always(self):
        self.login_as("admin")
        response = self.client.get(reverse("core:beneficiarios_create"))
        self.assertNotIn("X-Modal", response)
        self.assertContains(response, "<html")
        self.assertContains(response, "app-shell")

    def test_a_form_with_mistakes_comes_back_in_the_window_with_its_messages(self):
        self.login_as("admin")
        response = self.client.post(
            reverse("core:beneficiarios_create") + "?modal=1", self.beneficiary_data(rut="11.111.111-2", name="")
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["X-Modal"], "form")
        self.assertContains(response, "is-invalid")
        self.assertContains(response, "data-form-error", count=0)  # son errores de campo, no del formulario
        self.assertFalse(Beneficiary.objects.filter(rut="12345678-5").exists())
        self.assertEqual(list(get_messages(response.wsgi_request)), [])

    def test_a_saved_form_answers_with_json_and_leaves_the_notice_for_the_next_page(self):
        admin = self.login_as("admin")
        response = self.client.post(reverse("core:beneficiarios_create") + "?modal=1", self.beneficiary_data())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["X-Modal"], "saved")
        self.assertEqual(response["Content-Type"], "application/json")
        result = json.loads(response.content)
        self.assertTrue(result["saved"])
        self.assertFalse(result["again"])
        beneficiary = Beneficiary.objects.get(rut="12345678-5")
        self.assertEqual(beneficiary.name, "Pedro Pérez")
        log = AuditLog.objects.get(event="Registro creado", record_id=beneficiary.pk)
        self.assertEqual(log.user, admin)
        # el aviso queda para la página que se recarga
        shown = [str(message) for message in get_messages(response.wsgi_request)]
        self.assertEqual(shown, [result["message"]])
        self.assertIn("Pedro Pérez", result["message"])

    def test_save_and_add_another_keeps_the_notice_inside_the_window(self):
        self.login_as("admin")
        response = self.client.post(
            reverse("core:beneficiarios_create") + "?modal=1", {**self.beneficiary_data(), "_addanother": "1"}
        )
        result = json.loads(response.content)
        self.assertTrue(result["saved"])
        self.assertTrue(result["again"])
        self.assertEqual(result["create_url"], reverse("core:beneficiarios_create"))
        self.assertEqual(list(get_messages(response.wsgi_request)), [])  # no se repite arriba al recargar

    def test_editing_in_the_window_saves_and_audits_the_change(self):
        self.login_as("admin")
        url = reverse("core:delegaciones_update", args=[self.north.pk]) + "?modal=1"
        page = self.client.get(url)
        version = page.context["version"]
        response = self.client.post(
            url,
            {
                "name": self.north.name,
                "address": self.north.address,
                "commune": self.north.commune,
                "managers": "Persona Nueva",
                "color": "#2e7d5b",
                "scope": self.north.scope,
                "status": self.north.status,
                "_version": version,
            },
        )
        self.assertEqual(response["X-Modal"], "saved")
        north = Delegation.objects.get(pk=self.north.pk)
        self.assertEqual((north.managers, north.color), ("Persona Nueva", "#2E7D5B"))
        self.assertTrue(AuditLog.objects.filter(event="Registro modificado", record_id=self.north.pk).exists())

    def test_an_edit_over_a_newer_version_comes_back_in_the_window(self):
        self.login_as("admin")
        url = reverse("core:delegaciones_update", args=[self.north.pk]) + "?modal=1"
        stale = "1999-01-01T00:00:00"
        response = self.client.post(
            url,
            {
                "name": self.north.name,
                "managers": "Otro",
                "color": self.north.color,
                "scope": self.north.scope,
                "status": self.north.status,
                "_version": stale,
            },
        )
        self.assertEqual(response["X-Modal"], "form")
        self.assertContains(response, "Otra persona modificó este registro")
        self.assertEqual(Delegation.objects.get(pk=self.north.pk).managers, self.north.managers)

    def test_without_permission_the_window_gets_a_403_and_the_page_link_takes_over(self):
        self.login_as("matias.cavieres")  # Funcionario: no administra beneficiarios... ni usuarios
        response = self.modal(reverse("core:usuarios_create"))
        self.assertEqual(response.status_code, 403)
        self.assertNotIn("X-Modal", response)

    def test_an_archived_record_is_not_opened_in_the_window(self):
        self.login_as("admin")
        beneficiary = Beneficiary.objects.get(rut="11111111-1")
        beneficiary.deleted_at = beneficiary.created_at
        beneficiary.save(update_fields=["deleted_at"])
        response = self.modal(reverse("core:beneficiarios_update", args=[beneficiary.pk]))
        self.assertEqual(response.status_code, 302)  # a la ficha, con su aviso: el navegador lo toma como "no llegó"
        self.assertNotIn("X-Modal", response)

    def test_anonymous_users_are_sent_to_the_login(self):
        response = self.modal(reverse("core:beneficiarios_create"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/?next=", response["Location"])


class ModalLinksTests(PortalTestCase):
    def test_every_page_has_the_shared_window_and_the_csrf_token(self):
        self.login_as("admin")
        response = self.client.get(reverse("core:beneficiarios_list"))
        self.assertContains(response, 'id="sgr-modal"')
        self.assertContains(response, 'name="csrf-token"')
        self.assertContains(response, "core/js/crud-modal.js")
        self.assertContains(response, "core/js/confirm.js")

    def test_the_public_pages_have_no_window(self):
        response = self.client.get("/esta-pagina-no-existe/")
        self.assertNotContains(response, 'id="sgr-modal"', status_code=404)

    def test_new_and_edit_links_open_the_window(self):
        self.login_as("admin")
        response = self.client.get(reverse("core:beneficiarios_list"))
        self.assertContains(response, 'data-modal-form')
        html = response.content.decode()
        create = reverse("core:beneficiarios_create")
        self.assertIn(f'href="{create}" data-modal-form', html)
        beneficiary = Beneficiary.objects.get(rut="11111111-1")
        edit = reverse("core:beneficiarios_update", args=[beneficiary.pk])
        self.assertIn(f'href="{edit}" data-modal-form', html)

    def test_archive_links_carry_the_record_name_for_the_confirmation(self):
        self.login_as("admin")
        response = self.client.get(reverse("core:beneficiarios_list"))
        self.assertContains(response, 'data-delete="María Pérez (11111111-1)" data-delete-kind="archive"')

    def test_the_detail_page_opens_edit_in_the_window_and_archive_with_a_confirmation(self):
        self.login_as("admin")
        beneficiary = Beneficiary.objects.get(rut="11111111-1")
        response = self.client.get(reverse("core:beneficiarios_detail", args=[beneficiary.pk]))
        edit = reverse("core:beneficiarios_update", args=[beneficiary.pk])
        self.assertContains(response, f'href="{edit}" data-modal-form')
        self.assertContains(response, 'data-delete=')

    def test_the_confirmation_page_still_works_without_javascript(self):
        self.login_as("admin")
        beneficiary = Beneficiary.objects.get(rut="11111111-1")
        url = reverse("core:beneficiarios_archive", args=[beneficiary.pk])
        self.assertContains(self.client.get(url), "Eliminar beneficiario")
        self.assertEqual(self.client.post(url).status_code, 302)
        beneficiary.refresh_from_db()
        self.assertIsNotNone(beneficiary.deleted_at)

    def test_atencion_opens_new_attention_in_the_window(self):
        self.login_as("matias.cavieres")
        response = self.client.get(reverse("core:atencion"), {"q": "perez"})
        self.assertContains(response, "data-modal-form")
        self.assertContains(response, "?beneficiary=")

    def test_the_lookup_button_and_suggestions_are_still_in_the_markup(self):
        self.login_as("admin")
        response = self.client.get(reverse("core:delegaciones_update", args=[self.north.pk]))
        self.assertContains(response, "data-lookup-open")
        self.assertContains(response, "<datalist")
