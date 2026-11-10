"""Páginas de error 400, 403, 404 y 500 con DEBUG=False.

La evaluación pide demostrar el 400 y el 500 con pruebas controladas, sin dañar datos ni interrumpir el servicio:
aquí se provocan con el cliente de pruebas de Django (``raise_request_exception=False`` deja que la respuesta de error
llegue como la vería el navegador) y se comprueba el código HTTP, el mensaje y que no se filtre nada técnico.
"""

from unittest import mock

from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied, SuspiciousOperation
from django.db import OperationalError
from django.template.loader import render_to_string
from django.test import Client, RequestFactory, SimpleTestCase, override_settings
from django.urls import reverse

from core import errors
from core.testing import PASSWORD, PortalTestCase

SECRET_TEXT = "SELECT password FROM auth_user WHERE id=1 -- /srv/sgr/core/views.py SECRET_KEY=abc"

# Cosas que una pantalla de error jamás debe mostrar.
TECHNICAL = (
    "Traceback",
    "Exception",
    "SELECT ",
    "auth_user",
    "views.py",
    "/srv/sgr",
    "SECRET_KEY",
    "ALLOWED_HOSTS",
    "DisallowedHost",
    "Request Method",
    "Django Version",
    "OperationalError",
    "RuntimeError",
    "sqlite",
)


@override_settings(DEBUG=False)
class ErrorPagesTestCase(PortalTestCase):
    def quiet_client(self, username=None):
        """Cliente que entrega la página de error en vez de relanzar la excepción en la prueba."""
        client = Client(raise_request_exception=False)
        if username:
            client.force_login(User.objects.get(username=username))
        return client

    def assertClean(self, response, status):
        self.assertEqual(response.status_code, status)
        body = response.content.decode()
        for technical in TECHNICAL:
            self.assertNotIn(technical, body, f"la pantalla {status} muestra «{technical}»")
        self.assertIn('href="', body)
        self.assertIn("Volver al inicio", body)


class ErrorPagesTests(ErrorPagesTestCase):
    def test_these_tests_run_with_debug_off(self):
        self.assertFalse(settings.DEBUG)

    def test_the_four_pages_exist_and_the_400_has_its_own_handler(self):
        from sgr_project import urls

        self.assertEqual(urls.handler400, "core.errors.bad_request")
        for name in ("400.html", "403.html", "404.html", "500.html"):
            self.assertTrue(render_to_string(name, request=None), name)

    def test_a_missing_page_answers_404_with_the_portal_design(self):
        response = self.quiet_client().get("/no-existe-esta-pagina/")
        self.assertClean(response, 404)
        self.assertTemplateUsed(response, "404.html")
        self.assertContains(response, "No encontramos esa página", status_code=404)
        self.assertContains(response, '<img class="escudo escudo-public"', status_code=404)

    def test_a_record_that_does_not_exist_answers_404_with_the_same_page(self):
        client = self.quiet_client("matias.cavieres")
        response = client.get(reverse("core:actividades_detail", args=[999999]))
        self.assertClean(response, 404)
        self.assertContains(response, "No encontramos esa página", status_code=404)

    def test_a_logged_in_person_gets_the_404_inside_the_layout_with_the_menu(self):
        response = self.quiet_client("matias.cavieres").get("/no-existe-esta-pagina/")
        self.assertClean(response, 404)
        self.assertContains(response, 'class="app-shell"', status_code=404)

    def test_an_action_without_permission_answers_403_with_a_way_back(self):
        client = self.quiet_client("consulta1")
        response = client.get(reverse("core:actividades_create"))
        self.assertClean(response, 403)
        self.assertTemplateUsed(response, "403.html")
        self.assertContains(response, "No tienes permiso para esto", status_code=403)
        post = client.post(reverse("core:actividades_create"), self.activity_data())
        self.assertClean(post, 403)

    def test_a_client_asking_for_an_administrative_page_gets_a_403_without_content(self):
        response = self.quiet_client("cliente1").get(reverse("core:actividades_list"))
        self.assertClean(response, 403)
        self.assertContains(response, "Tu perfil solo puede ver tu portal", status_code=403)
        self.assertNotContains(response, "Carla", status_code=403)

    def test_an_expired_form_token_answers_403_with_its_own_notice(self):
        strict = Client(enforce_csrf_checks=True, raise_request_exception=False)
        response = strict.post(reverse("core:login"), {"username": "admin", "password": PASSWORD})
        self.assertClean(response, 403)
        self.assertTemplateUsed(response, "403_csrf.html")
        self.assertContains(response, "Esta pantalla ya no es válida", status_code=403)

    def test_a_forbidden_page_only_shows_the_messages_the_portal_wrote(self):
        with mock.patch("core.views.pick_period", side_effect=PermissionDenied):
            response = self.quiet_client("matias.cavieres").get(reverse("core:dashboard"))
        self.assertClean(response, 403)
        self.assertContains(response, "Tu cuenta no tiene acceso a esta pantalla", status_code=403)


class BadRequestTests(ErrorPagesTestCase):
    def test_a_host_that_is_not_allowed_answers_400_without_naming_it(self):
        response = self.quiet_client().get("/", HTTP_HOST="sitio-no-permitido.example")
        self.assertClean(response, 400)
        self.assertNotContains(response, "sitio-no-permitido", status_code=400)
        self.assertContains(response, "No pudimos procesar la solicitud", status_code=400)

    def test_a_host_that_is_not_allowed_is_refused_on_every_screen(self):
        client = self.quiet_client()
        for path in ("/", reverse("accounts:recover"), "/no-existe/", "/salud/"):
            with self.subTest(path=path):
                response = client.get(path, HTTP_HOST="sitio-no-permitido.example")
                self.assertClean(response, 400)

    def test_a_body_over_the_limit_answers_400_with_the_portal_page(self):
        size = settings.DATA_UPLOAD_MAX_MEMORY_SIZE + 1024
        response = self.quiet_client().post(
            reverse("core:login"), data="x=" + "a" * size, content_type="application/x-www-form-urlencoded"
        )
        self.assertClean(response, 400)
        self.assertTemplateUsed(response, "400.html")
        self.assertNotContains(response, "DATA_UPLOAD_MAX_MEMORY_SIZE", status_code=400)

    def test_a_broken_upload_answers_400_and_saves_nothing(self):
        from core.models import AuditLog

        before = AuditLog.objects.count()
        client = self.quiet_client("matias.cavieres")
        response = client.post(
            reverse("core:profile"),
            data=b"contenido roto sin delimitador",
            content_type="multipart/form-data",
        )
        self.assertClean(response, 400)
        self.assertEqual(AuditLog.objects.count(), before)

    def test_too_many_form_fields_answer_400(self):
        with override_settings(DATA_UPLOAD_MAX_NUMBER_FIELDS=5):
            response = self.quiet_client().post(reverse("core:login"), {f"campo{n}": "x" for n in range(20)})
        self.assertClean(response, 400)

    def test_the_400_page_says_what_happened_and_how_to_continue(self):
        response = self.quiet_client().get("/", HTTP_HOST="sitio-no-permitido.example")
        self.assertContains(response, "no se pudo procesar", status_code=400)
        self.assertContains(response, "Volver al inicio", status_code=400)
        self.assertContains(response, 'class="error-code">400<', status_code=400)

    def test_the_400_page_keeps_the_design_of_the_403_and_404_pages(self):
        client = self.quiet_client()
        bad = client.get("/", HTTP_HOST="sitio-no-permitido.example").content.decode()
        missing = client.get("/no-existe/").content.decode()
        for marker in ('class="error-page"', 'class="error-code"', 'class="page-title mb-3"', 'class="btn btn-primary"', "sgr.css"):
            self.assertIn(marker, bad)
            self.assertIn(marker, missing)

    def test_the_400_page_never_shows_the_text_of_the_exception(self):
        response = errors.bad_request(RequestFactory().get("/"), SuspiciousOperation(SECRET_TEXT))
        self.assertEqual(response.status_code, 400)
        self.assertNotIn("SELECT", response.content.decode())
        self.assertNotIn("SECRET_KEY", response.content.decode())

    def test_if_the_page_cannot_be_drawn_a_minimal_400_still_comes_out(self):
        with (
            mock.patch("core.errors.django_bad_request", side_effect=RuntimeError(SECRET_TEXT)),
            self.assertLogs("core.errors", level="ERROR"),
        ):
            response = self.quiet_client().get("/", HTTP_HOST="sitio-no-permitido.example")
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "No pudimos procesar la solicitud", status_code=400)
        self.assertContains(response, "Volver al inicio", status_code=400)
        self.assertNotContains(response, "SELECT", status_code=400)

    def test_a_bad_request_does_not_change_any_data(self):
        from core.models import AuditLog

        before = (User.objects.count(), AuditLog.objects.count())
        self.quiet_client().get("/", HTTP_HOST="sitio-no-permitido.example")
        self.assertEqual((User.objects.count(), AuditLog.objects.count()), before)


class ServerErrorTests(ErrorPagesTestCase):
    def test_a_failure_inside_a_view_answers_500_without_details(self):
        client = self.quiet_client("matias.cavieres")
        with (
            mock.patch("core.views.pick_period", side_effect=RuntimeError(SECRET_TEXT)),
            self.assertLogs("django.request", level="ERROR"),
        ):
            response = client.get(reverse("core:dashboard"))
        self.assertClean(response, 500)
        self.assertTemplateUsed(response, "500.html")
        self.assertContains(response, "Tuvimos un problema temporal", status_code=500)
        self.assertNotContains(response, SECRET_TEXT, status_code=500)

    def test_a_database_failure_answers_500_without_details(self):
        client = self.quiet_client("matias.cavieres")
        error = OperationalError(SECRET_TEXT)
        with (
            mock.patch("django.db.backends.utils.CursorWrapper.execute", side_effect=error),
            self.assertLogs("django.request", level="ERROR"),
        ):
            response = client.get(reverse("core:dashboard"))
        self.assertClean(response, 500)
        self.assertNotContains(response, SECRET_TEXT, status_code=500)

    def test_the_500_page_does_not_blame_the_person_and_offers_a_way_out(self):
        client = self.quiet_client("matias.cavieres")
        with mock.patch("core.views.pick_period", side_effect=RuntimeError("x")), self.assertLogs("django.request", level="ERROR"):
            response = client.get(reverse("core:dashboard"))
        self.assertContains(response, "No fue algo que hiciste tú", status_code=500)
        self.assertContains(response, "inténtalo de nuevo", status_code=500)
        self.assertContains(response, 'href="/"', status_code=500)

    def test_the_500_page_keeps_the_design_of_the_other_error_pages(self):
        page = render_to_string("500.html")
        for marker in ('class="error-page"', 'class="error-code"', 'class="page-title mb-3"', 'class="btn btn-primary"', "sgr.css"):
            self.assertIn(marker, page)

    def test_the_500_page_needs_nothing_from_the_session_or_the_database(self):
        with mock.patch("django.db.backends.utils.CursorWrapper.execute", side_effect=OperationalError("caída")):
            page = render_to_string("500.html")
        self.assertIn("Tuvimos un problema temporal", page)

    def test_a_failure_is_written_to_the_server_log_for_the_team(self):
        client = self.quiet_client("matias.cavieres")
        with (
            mock.patch("core.views.pick_period", side_effect=RuntimeError("falla de prueba")),
            self.assertLogs("django.request", level="ERROR") as logs,
        ):
            client.get(reverse("core:dashboard"))
        self.assertTrue(any("Internal Server Error" in line for line in logs.output))

    def test_a_failed_request_does_not_log_the_person_out_or_change_data(self):
        from core.models import AuditLog

        client = self.quiet_client("matias.cavieres")
        before = AuditLog.objects.count()
        with mock.patch("core.views.pick_period", side_effect=RuntimeError("x")), self.assertLogs("django.request", level="ERROR"):
            client.get(reverse("core:dashboard"))
        self.assertEqual(AuditLog.objects.count(), before)
        self.assertEqual(client.get(reverse("core:profile")).status_code, 200)


class ErrorTemplatesTests(SimpleTestCase):
    def test_no_error_page_prints_the_exception_or_the_request(self):
        for name in ("400.html", "403_csrf.html", "404.html", "500.html"):
            html = render_to_string(name)
            for token in ("{{ exception", "request_path", "debug", "settings."):
                self.assertNotIn(token, html, name)

    def test_the_403_page_prints_only_the_message_of_the_exception_and_nothing_else(self):
        source = render_to_string("403.html", {"exception": "Mensaje del portal"})
        self.assertIn("Mensaje del portal", source)
        self.assertNotIn("Traceback", source)
