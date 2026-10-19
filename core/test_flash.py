import re

from django.contrib.staticfiles import finders
from django.urls import reverse

from core.testing import PortalTestCase
from core.views import SESSION_PAGE_SIZE
from operations.models import Activity
from organization.models import Beneficiary


class NoticeScriptsTests(PortalTestCase):
    def test_every_page_loads_the_scripts_in_the_right_order(self):
        self.login_as("matias.cavieres")
        html = self.client.get(reverse("core:dashboard")).content.decode()
        head = html.split("</head>")[0]
        self.assertIn("core/js/has-js.js", head)
        self.assertNotIn("core/js/flash.js", head)
        order = [html.index(f"core/js/{name}.js") for name in ("validation", "confirm", "flash")]
        self.assertEqual(order, sorted(order))

    def test_the_login_page_loads_them_too(self):
        html = self.client.get(reverse("core:login")).content.decode()
        self.assertIn("core/js/has-js.js", html)
        self.assertIn("core/js/flash.js", html)

    def test_the_scripts_are_part_of_the_static_files(self):
        for name in ("has-js", "flash", "confirm", "alerts", "validation", "crud-modal", "dialog"):
            with self.subTest(name=name):
                self.assertIsNotNone(finders.find(f"core/js/{name}.js"))

    def test_the_sweetalert_files_are_served_with_the_project(self):
        for path in ("core/vendor/sweetalert2/sweetalert2.esm.min.js", "core/vendor/sweetalert2/sweetalert2.min.css"):
            with self.subTest(path=path):
                self.assertIsNotNone(finders.find(path))


class NoticeMarkupTests(PortalTestCase):

    def page_size(self, value):
        return self.client.post(reverse("core:page_size"), {"filas": value, "next": reverse("core:dashboard")}, follow=True)

    def notice(self, response):
        found = re.search(r'<div class="alert[^>]*data-flash="([a-z]+)" data-flash-tags="([^"]*)"[^>]*>.*?data-flash-text>([^<]*)<', response.content.decode(), re.S)
        self.assertIsNotNone(found, "la página no trae ningún aviso")
        return found.groups()

    def test_a_success_comes_with_its_level_and_text(self):
        self.login_as("admin")
        response = self.client.post(
            reverse("core:beneficiarios_create"),
            {"rut": "12.345.678-5", "name": "Pedro Pérez", "phone": "", "address": ""},
            follow=True,
        )
        level, tags, text = self.notice(response)
        self.assertEqual((level, tags), ("success", ""))
        self.assertIn("Pedro Pérez", text)
        self.assertTrue(Beneficiary.objects.filter(rut="12345678-5").exists())

    def test_a_preference_change_is_a_short_toast(self):
        self.login_as("matias.cavieres")
        level, tags, text = self.notice(self.page_size(10))
        self.assertEqual((level, tags), ("success", "toast"))
        self.assertIn("10 filas por página", text)

    def test_an_error_is_marked_as_error_and_changes_nothing(self):
        self.login_as("matias.cavieres")
        level, tags, text = self.notice(self.page_size(7))
        self.assertEqual(level, "error")
        self.assertEqual(text, "Esa cantidad de filas no está disponible.")
        self.assertNotIn(SESSION_PAGE_SIZE, self.client.session)

    def test_a_warning_and_an_info_keep_their_level(self):
        self.login_as("admin")
        archived = Activity.objects.filter(deleted_at__isnull=False).first()
        warning = self.client.get(reverse("core:actividades_update", args=[archived.pk]), follow=True)
        self.assertEqual(self.notice(warning)[0], "warning")
        info = self.client.post(reverse("core:logout"), follow=True)
        self.assertEqual(self.notice(info)[0], "info")

    def test_the_text_of_the_notice_is_escaped(self):
        self.login_as("matias.cavieres")
        response = self.client.post(
            reverse("core:actividades_create"),
            self.intake_data(requester="<b>negrita</b>"),
            follow=True,
        )
        html = response.content.decode()
        self.assertNotIn("<b>negrita</b>", html)
        self.assertIn("&lt;b&gt;negrita&lt;/b&gt;", html)

    def test_without_javascript_the_notice_is_a_normal_banner_with_a_close_button(self):
        self.login_as("matias.cavieres")
        html = self.page_size(20).content.decode()
        self.assertIn('class="flash"', html)
        self.assertIn('data-bs-dismiss="alert"', html)
        css = open(finders.find("core/css/sgr.css"), encoding="utf-8").read()
        self.assertIn(".has-js .flash", css)


class ConfirmationMarkupTests(PortalTestCase):
    def test_the_password_change_asks_for_confirmation(self):
        self.login_as("matias.cavieres")
        response = self.client.get(reverse("core:profile"))
        self.assertContains(response, "data-confirm-submit")
        self.assertContains(response, 'data-confirm-title="¿Cambiar tu contraseña?"')
        self.assertContains(response, 'data-confirm-button="Sí, cambiar contraseña"')
        self.assertContains(response, 'data-cancel-text="Tu contraseña sigue siendo la misma."')

    def test_other_forms_do_not_ask_for_confirmation(self):
        self.login_as("admin")
        for url in (reverse("core:beneficiarios_create"), reverse("core:actividades_create")):
            with self.subTest(url=url):
                self.assertNotContains(self.client.get(url), "data-confirm-submit")
        self.client.logout()
        self.assertNotContains(self.client.get(reverse("core:login")), "data-confirm-submit")

    def test_the_cancel_buttons_say_whether_they_create_or_edit(self):
        self.login_as("admin")
        beneficiary = Beneficiary.objects.get(rut="11111111-1")
        for url, kind in (
            (reverse("core:beneficiarios_create"), "create"),
            (reverse("core:beneficiarios_create") + "?modal=1", "create"),
            (reverse("core:beneficiarios_update", args=[beneficiary.pk]), "edit"),
            (reverse("core:beneficiarios_update", args=[beneficiary.pk]) + "?modal=1", "edit"),
        ):
            with self.subTest(url=url):
                self.assertContains(self.client.get(url), f'data-cancel-form="{kind}"')

    def test_the_window_closes_with_the_cross_as_a_cancel_too(self):
        self.login_as("admin")
        response = self.client.get(reverse("core:beneficiarios_create"), {"modal": "1"})
        self.assertContains(response, 'class="btn-close" data-dialog-close data-cancel-form="create"')

    def test_the_delete_confirmation_is_still_there(self):
        self.login_as("admin")
        self.assertContains(self.client.get(reverse("core:atencion")), "data-delete=")
