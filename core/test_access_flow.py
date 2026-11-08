import importlib.util
import os
import re
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ImproperlyConfigured
from django.test import Client, SimpleTestCase
from django.urls import reverse

from core.crud import PAGE_SIZE, PAGE_SIZES
from core.testing import PASSWORD, PortalTestCase
from organization.models import Beneficiary


class AuthRoutesTests(PortalTestCase):

    def test_django_auth_routes_are_available_under_accounts(self):
        expected = {
            "login": "/accounts/login/",
            "logout": "/accounts/logout/",
            "password_change": "/accounts/password_change/",
            "password_change_done": "/accounts/password_change/done/",
            "password_reset": "/accounts/password_reset/",
            "password_reset_done": "/accounts/password_reset/done/",
            "password_reset_complete": "/accounts/reset/done/",
        }
        for name, path in expected.items():
            with self.subTest(name=name):
                self.assertEqual(reverse(name), path)
        self.assertEqual(
            reverse("password_reset_confirm", args=["MQ", "token"]), "/accounts/reset/MQ/token/"
        )

    def test_settings_point_to_the_portal_screens(self):
        self.assertEqual(reverse(settings.LOGIN_URL), "/")
        self.assertEqual(reverse(settings.LOGIN_REDIRECT_URL), "/dashboard/")
        self.assertEqual(reverse(settings.LOGOUT_REDIRECT_URL), "/")

    def test_login_uses_the_default_registration_template(self):
        response = self.client.get(reverse("core:login"))
        self.assertTemplateUsed(response, "registration/login.html")
        self.assertTemplateNotUsed(response, "core/login.html")

    def test_accounts_login_shows_the_same_screen_and_logs_in(self):
        response = self.client.get("/accounts/login/")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "registration/login.html")
        response = self.client.post("/accounts/login/", {"username": "admin", "password": PASSWORD})
        self.assertRedirects(response, reverse("core:dashboard"))

    def test_accounts_login_wrong_password_uses_the_portal_wording(self):
        response = self.client.post("/accounts/login/", {"username": "admin", "password": "otra"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "El usuario, el correo o la contraseña no son correctos")

    def test_accounts_logout_closes_the_session(self):
        self.login_as("admin")
        self.assertEqual(self.client.get("/accounts/logout/").status_code, 405)
        response = self.client.post("/accounts/logout/")
        self.assertRedirects(response, reverse("core:login"))
        self.assertEqual(self.client.get(reverse("core:dashboard")).status_code, 302)

    def test_stock_password_screens_lead_to_the_portal_ones(self):
        self.login_as("admin")
        self.assertRedirects(
            self.client.get("/accounts/password_change/"), reverse("core:profile"), fetch_redirect_response=False
        )
        self.assertRedirects(
            self.client.get("/accounts/password_reset/"),
            reverse("accounts:recover"),
            fetch_redirect_response=False,
        )

    def test_the_login_view_does_not_name_which_credential_failed(self):
        wrong_user = self.client.post(reverse("core:login"), {"username": "no.existe", "password": PASSWORD})
        wrong_password = self.client.post(reverse("core:login"), {"username": "admin", "password": "otra"})
        self.assertEqual(
            wrong_user.context["form"].non_field_errors(), wrong_password.context["form"].non_field_errors()
        )

    def test_login_form_carries_the_csrf_token_and_rejects_posts_without_it(self):
        strict = Client(enforce_csrf_checks=True)
        page = strict.get(reverse("core:login"))
        self.assertContains(page, "csrfmiddlewaretoken")
        response = strict.post(reverse("core:login"), {"username": "admin", "password": PASSWORD})
        self.assertEqual(response.status_code, 403)

    def test_login_page_links_to_the_password_recovery(self):
        response = self.client.get(reverse("core:login"))
        self.assertContains(response, f'href="{reverse("accounts:recover")}"')
        self.assertContains(response, "¿Olvidaste tu contraseña?")


class AccessFlowTests(PortalTestCase):

    def test_valid_credentials_let_the_user_in(self):
        response = self.client.post(
            reverse("core:login"), {"username": "matias.cavieres", "password": PASSWORD}, follow=True
        )
        self.assertRedirects(response, reverse("core:dashboard"))
        self.assertEqual(response.context["user"].username, "matias.cavieres")
        self.assertTrue(response.context["user"].is_authenticated)

    def test_invalid_credentials_show_a_controlled_error(self):
        response = self.client.post(reverse("core:login"), {"username": "matias.cavieres", "password": "mal"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "El usuario, el correo o la contraseña no son correctos")
        self.assertFalse(response.context["user"].is_authenticated)

    def test_an_anonymous_visitor_is_sent_to_login_with_the_address_they_wanted(self):
        response = self.client.get(reverse("core:dashboard"))
        self.assertRedirects(
            response, f"{reverse('core:login')}?next={reverse('core:dashboard')}", fetch_redirect_response=False
        )

    def test_after_login_the_visitor_lands_on_the_address_they_wanted(self):
        target = reverse("core:atencion")
        response = self.client.post(
            f"{reverse('core:login')}?next={target}", {"username": "admin", "password": PASSWORD}
        )
        self.assertRedirects(response, target, fetch_redirect_response=False)

    def test_the_dashboard_is_only_for_users_with_a_session(self):
        self.assertEqual(self.client.get(reverse("core:dashboard")).status_code, 302)
        self.login_as("admin")
        self.assertEqual(self.client.get(reverse("core:dashboard")).status_code, 200)

    def test_after_logout_a_private_route_asks_for_login_again(self):
        self.login_as("admin")
        private = reverse("core:atencion")
        self.assertEqual(self.client.get(private).status_code, 200)
        self.client.post(reverse("core:logout"))
        response = self.client.get(private)
        self.assertRedirects(
            response, f"{reverse('core:login')}?next={private}", fetch_redirect_response=False
        )

    def test_logout_form_is_a_post_with_csrf(self):
        self.login_as("admin")
        response = self.client.get(reverse("core:dashboard"))
        self.assertContains(response, f'<form method="post" action="{reverse("core:logout")}"')
        self.assertContains(response, "Cerrar sesión")
        form = re.search(rf'<form method="post" action="{reverse("core:logout")}".*?</form>', response.content.decode(), re.DOTALL)
        self.assertIn("csrfmiddlewaretoken", form.group(0))

    def test_logout_shows_a_notice_on_the_login_screen(self):
        self.login_as("admin")
        response = self.client.post(reverse("core:logout"), follow=True)
        self.assertContains(response, "Cerraste tu sesión.")
        self.assertNotContains(self.client.get(reverse("core:login")), "Cerraste tu sesión.")


class NavigationTests(PortalTestCase):

    def test_a_visitor_sees_the_login_link_and_no_user_menu(self):
        response = self.client.get("/esta-direccion-no-existe/")
        self.assertEqual(response.status_code, 404)
        self.assertContains(response, ">Ingresar</a>", status_code=404)
        self.assertNotContains(response, "Cerrar sesión", status_code=404)
        self.assertNotContains(response, 'id="barra-lateral"', status_code=404)

    def test_a_user_with_a_session_sees_the_menu_and_the_logout_button(self):
        self.login_as("matias.cavieres")
        response = self.client.get("/esta-direccion-no-existe/")
        self.assertEqual(response.status_code, 404)
        self.assertContains(response, "Cerrar sesión", status_code=404)
        self.assertContains(response, 'id="barra-lateral"', status_code=404)
        self.assertNotContains(response, ">Ingresar</a>", status_code=404)

    def test_hiding_a_link_is_not_the_protection_the_view_still_refuses(self):
        self.login_as("coordinacion1")
        self.assertEqual(self.client.get(reverse("core:atencion")).status_code, 403)


class SessionValueTests(PortalTestCase):

    def test_dashboard_counts_visits_and_keeps_the_count_on_refresh(self):
        self.login_as("matias.cavieres")
        url = reverse("core:dashboard")
        for expected in (1, 2, 3):
            response = self.client.get(url)
            self.assertEqual(response.context["visits"], expected)
            self.assertContains(response, f"Visitas al inicio en esta sesión: <strong>{expected}</strong>")
        self.assertEqual(self.client.session["dashboard_visits"], 3)

    def test_the_count_survives_changing_page(self):
        self.login_as("admin")
        self.client.get(reverse("core:dashboard"))
        self.client.get(reverse("core:atencion"))
        self.client.get(reverse("core:beneficiarios_list"))
        self.assertEqual(self.client.get(reverse("core:dashboard")).context["visits"], 2)

    def test_each_session_has_its_own_count(self):
        self.login_as("admin")
        self.client.get(reverse("core:dashboard"))
        self.client.get(reverse("core:dashboard"))
        other = Client()
        other.force_login(User.objects.get(username="matias.quiroz"))
        self.assertEqual(other.get(reverse("core:dashboard")).context["visits"], 1)
        self.assertEqual(self.client.get(reverse("core:dashboard")).context["visits"], 3)

    def test_logout_erases_the_session_so_nobody_inherits_it(self):
        self.login_as("admin")
        self.client.get(reverse("core:dashboard"))
        self.client.post(reverse("core:page_size"), {"filas": "5"})
        self.assertIn("dashboard_visits", self.client.session)
        self.assertIn("page_size", self.client.session)
        self.client.post(reverse("core:logout"))
        self.assertNotIn("dashboard_visits", self.client.session)
        self.assertNotIn("page_size", self.client.session)
        self.client.post(reverse("core:login"), {"username": "admin", "password": PASSWORD})
        response = self.client.get(reverse("core:dashboard"))
        self.assertEqual(response.context["visits"], 1)
        self.assertEqual(self.client.get(reverse("core:beneficiarios_list")).context["page_size"], PAGE_SIZE)

    def test_the_session_cookie_only_carries_a_key_not_the_data(self):
        self.client.post(reverse("core:login"), {"username": "admin", "password": PASSWORD})
        self.client.get(reverse("core:dashboard"))
        cookie = self.client.cookies[settings.SESSION_COOKIE_NAME]
        self.assertNotIn("dashboard_visits", cookie.value)
        self.assertTrue(cookie["httponly"])
        self.assertEqual(settings.SESSION_ENGINE, "django.contrib.sessions.backends.db")


class PageSizeTests(PortalTestCase):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        Beneficiary.objects.bulk_create(
            [Beneficiary(rut=f"8{number:07d}-1", name=f"Persona Fila {number:02d}") for number in range(45)]
        )

    def setUp(self):
        self.login_as("admin")
        self.url = reverse("core:beneficiarios_list")

    def test_default_is_fifteen_rows(self):
        response = self.client.get(self.url)
        self.assertEqual(response.context["page_size"], PAGE_SIZE)
        self.assertEqual(len(response.context["rows"]), PAGE_SIZE)
        self.assertEqual(PAGE_SIZE, 15)
        self.assertEqual(PAGE_SIZES, (5, 15, 30))

    def test_choosing_a_size_stores_it_in_the_session_and_changes_every_list(self):
        response = self.client.post(reverse("core:page_size"), {"filas": "5", "next": self.url})
        self.assertRedirects(response, self.url, fetch_redirect_response=False)
        self.assertEqual(self.client.session["page_size"], 5)
        for url in (self.url, reverse("core:atencion"), reverse("core:delegaciones_list")):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).context["page_size"], 5)
        self.assertEqual(len(self.client.get(self.url).context["rows"]), 5)

    def test_the_success_notice_appears_after_the_redirect_and_only_once(self):
        response = self.client.post(reverse("core:page_size"), {"filas": "30", "next": self.url}, follow=True)
        self.assertContains(response, "Listo: los listados muestran 30 filas por página mientras dure tu sesión.")
        self.assertContains(response, "alert-success")
        self.assertNotContains(self.client.get(self.url), "mientras dure tu sesión")

    def test_the_button_of_the_current_size_is_marked(self):
        self.client.post(reverse("core:page_size"), {"filas": "5", "next": self.url})
        page = self.client.get(self.url).content.decode()
        self.assertRegex(page, r'class="btn btn-primary"[^>]*aria-pressed="true">5</button>')

    def test_the_chosen_size_survives_a_refresh(self):
        self.client.post(reverse("core:page_size"), {"filas": "30", "next": self.url})
        for _ in range(2):
            response = self.client.get(self.url)
            self.assertEqual(response.context["page_size"], 30)
            self.assertEqual(len(response.context["rows"]), 30)

    def test_invalid_sizes_are_refused_and_nothing_is_stored(self):
        for value in ("7", "0", "-5", "abc", "", "1000", "10", "20", "50"):
            with self.subTest(value=value):
                response = self.client.post(reverse("core:page_size"), {"filas": value, "next": self.url}, follow=True)
                self.assertContains(response, "Esa cantidad de filas no está disponible.")
                self.assertContains(response, "alert-danger")
                self.assertNotIn("page_size", self.client.session)

    def test_a_forged_value_in_the_session_falls_back_to_the_default(self):
        session = self.client.session
        session["page_size"] = 100000
        session.save()
        self.assertEqual(self.client.get(self.url).context["page_size"], PAGE_SIZE)

    def test_next_never_leaves_the_site(self):
        for target in ("https://ejemplo.invalid/", "//ejemplo.invalid/", "javascript:alert(1)", ""):
            with self.subTest(target=target):
                response = self.client.post(reverse("core:page_size"), {"filas": "5", "next": target})
                self.assertRedirects(response, reverse("core:dashboard"), fetch_redirect_response=False)

    def test_next_keeps_the_search_but_not_the_page(self):
        response = self.client.get(self.url, {"q": "persona", "page": 2})
        self.assertEqual(response.context["page_size_next"], f"{self.url}?q=persona")
        plain = self.client.get(self.url)
        self.assertEqual(plain.context["page_size_next"], self.url)

    def test_only_post_and_only_with_a_session(self):
        self.assertEqual(self.client.get(reverse("core:page_size")).status_code, 405)
        anonymous = Client()
        response = anonymous.post(reverse("core:page_size"), {"filas": "5"})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith(reverse("core:login")))

    def test_excel_export_ignores_the_page_size(self):
        self.client.post(reverse("core:page_size"), {"filas": "5", "next": self.url})
        response = self.client.get(self.url, {"formato": "xlsx"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("spreadsheetml", response["Content-Type"])


class EmailSettingsTests(SimpleTestCase):

    def load_settings(self, **env):
        path = settings.BASE_DIR / "sgr_project" / "settings.py"
        spec = importlib.util.spec_from_file_location("settings_de_prueba", path)
        module = importlib.util.module_from_spec(spec)
        defaults = {"EMAIL_HOST": "", "EMAIL_BACKEND": "", "DEFAULT_FROM_EMAIL": ""}
        with mock.patch.dict(os.environ, {**defaults, **env}):
            spec.loader.exec_module(module)
        return module

    def test_without_a_mail_server_the_email_goes_to_the_console(self):
        module = self.load_settings()
        self.assertEqual(module.EMAIL_BACKEND, "django.core.mail.backends.console.EmailBackend")
        self.assertEqual(module.DEFAULT_FROM_EMAIL, "noreply@proyecto.local")

    def test_with_a_mail_server_in_the_env_the_email_goes_by_smtp(self):
        module = self.load_settings(
            EMAIL_HOST="smtp.ejemplo.invalid",
            EMAIL_PORT="2525",
            EMAIL_HOST_USER="usuario-de-prueba",
            EMAIL_HOST_PASSWORD="clave-de-prueba",
            DEFAULT_FROM_EMAIL="sgr@ejemplo.invalid",
        )
        self.assertEqual(module.EMAIL_BACKEND, "django.core.mail.backends.smtp.EmailBackend")
        self.assertEqual(module.EMAIL_HOST, "smtp.ejemplo.invalid")
        self.assertEqual(module.EMAIL_PORT, 2525)
        self.assertEqual(module.EMAIL_HOST_USER, "usuario-de-prueba")
        self.assertEqual(module.EMAIL_HOST_PASSWORD, "clave-de-prueba")
        self.assertTrue(module.EMAIL_USE_TLS)
        self.assertEqual(module.DEFAULT_FROM_EMAIL, "sgr@ejemplo.invalid")

    def test_empty_values_in_the_env_use_the_defaults(self):
        module = self.load_settings(EMAIL_PORT="", EMAIL_USE_TLS="")
        self.assertEqual(module.EMAIL_PORT, 587)
        self.assertTrue(module.EMAIL_USE_TLS)

    def test_tls_and_ssl_accept_any_capitals_and_never_clash(self):
        self.assertTrue(self.load_settings(EMAIL_USE_TLS="true").EMAIL_USE_TLS)
        self.assertTrue(self.load_settings(EMAIL_USE_TLS=" True ").EMAIL_USE_TLS)
        self.assertFalse(self.load_settings(EMAIL_USE_TLS="false").EMAIL_USE_TLS)
        module = self.load_settings(EMAIL_PORT="465", EMAIL_USE_SSL="True")
        self.assertTrue(module.EMAIL_USE_SSL)
        self.assertFalse(module.EMAIL_USE_TLS)
        self.assertFalse(self.load_settings().EMAIL_USE_SSL)

    def test_a_port_that_is_not_a_number_stops_with_a_clear_message(self):
        with self.assertRaisesMessage(ImproperlyConfigured, "EMAIL_PORT"):
            self.load_settings(EMAIL_PORT="abc")

    def test_the_example_env_has_the_mail_variables_blank(self):
        example = (Path(settings.BASE_DIR) / ".env.example").read_text(encoding="utf-8").splitlines()
        for line in ("EMAIL_HOST=", "EMAIL_HOST_USER=", "EMAIL_HOST_PASSWORD="):
            self.assertIn(line, example)
        self.assertIn("DEFAULT_FROM_EMAIL=noreply@proyecto.local", example)

    def test_credentials_are_not_in_the_repository(self):
        base = Path(settings.BASE_DIR)
        example = (base / ".env.example").read_text(encoding="utf-8")
        for name in ("EMAIL_HOST_USER", "EMAIL_HOST_PASSWORD"):
            for line in example.splitlines():
                if name in line:
                    self.assertRegex(line, rf"^#?\s*{name}=$", "el ejemplo no debe traer credenciales")
        self.assertIn(".env", (base / ".gitignore").read_text(encoding="utf-8").splitlines())
        source = (base / "sgr_project" / "settings.py").read_text(encoding="utf-8")
        for name in ("EMAIL_HOST_USER", "EMAIL_HOST_PASSWORD"):
            self.assertRegex(source, rf'{name} = os\.environ\.get\("{name}", ""\)')
