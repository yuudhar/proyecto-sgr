"""Pruebas de la franja de arriba (delegación, usuario y perfil) y de lo que la página deja listo para los estados de
carga y para ver/ocultar la contraseña."""

import re

from django.contrib.staticfiles import finders
from django.urls import reverse

from core.crud import registry
from core.testing import PortalTestCase


class HeaderTests(PortalTestCase):
    def header(self, url=None, username="matias.cavieres"):
        self.login_as(username)
        response = self.client.get(url or reverse("core:dashboard"))
        html = response.content.decode()
        start = html.index('<header class="topbar">')
        return html[start : html.index("</header>", start)]

    def test_it_shows_the_delegation_with_its_code_and_name_the_user_and_the_profiles(self):
        header = self.header()
        code = f"DEL{self.north.pk:02d}"
        self.assertRegex(code, r"^DEL\d{2}$")
        self.assertIn(f'<span class="topbar-code">{code}</span>', header)
        self.assertIn("Delegación Norte", header)
        self.assertIn("Matías Cavieres", header)
        for role in ("Funcionario", "Verificador"):
            self.assertIn(role, header)

    def test_the_code_is_the_one_of_the_delegations_list(self):
        crud = registry.get("delegaciones")
        for username, delegation in (("matias.cavieres", self.north), ("matias.quiroz", self.south)):
            with self.subTest(username=username):
                self.assertIn(f'<span class="topbar-code">{crud.code_of(delegation)}</span>', self.header(username=username))

    def test_every_profile_comes_with_its_icon(self):
        header = self.header()
        icons = re.findall(r'<li class="topbar-role"><i class="bi (bi-[a-z0-9-]+)" aria-hidden="true"></i>([^<]+)</li>', header)
        self.assertEqual([label for _icon, label in icons], ["Funcionario", "Verificador"])
        self.assertTrue(all(icon.startswith("bi-") for icon, _label in icons))
        self.assertEqual(len({icon for icon, _label in icons}), 2)  # cada perfil con el suyo

    def test_the_name_links_to_the_profile_screen(self):
        self.assertIn(f'href="{reverse("core:profile")}"', self.header())

    def test_a_user_who_sees_every_delegation_has_no_code(self):
        for username, role in (("admin", "Super Usuario"), ("coordinacion1", "Coordinación")):
            with self.subTest(username=username):
                header = self.header(username=username)
                self.assertIn("Todas las delegaciones", header)
                self.assertNotIn("topbar-code", header)
                self.assertIn(role, header)

    def test_a_read_only_profile_shows_its_own_delegation_and_profile(self):
        header = self.header(username="consulta1")
        self.assertIn(f"DEL{self.north.pk:02d}", header)
        self.assertIn("Consulta", header)

    def test_the_delegation_is_announced_to_screen_readers(self):
        header = self.header()
        self.assertIn(f'aria-label="Tu delegación: DEL{self.north.pk:02d}, Delegación Norte"', header)
        self.assertIn('aria-label="Tus perfiles"', header)
        self.assertIn('aria-label="Tu perfil"', self.header(username="consulta1"))

    def test_it_is_on_every_kind_of_screen(self):
        self.login_as("matias.cavieres")
        for url in (
            reverse("core:dashboard"),
            reverse("core:atencion"),
            reverse("core:actividades_create"),
            reverse("core:profile"),
            reverse("core:atencion"),
            "/no-existe-esta-pagina/",  # la pantalla de «no encontrado» también
        ):
            with self.subTest(url=url):
                self.assertContains(self.client.get(url), 'class="topbar-code"', status_code=self.client.get(url).status_code)

    def test_a_user_without_profile_is_told_so(self):
        user = self.make_user("sin.perfil", officer=self.officer("F-1004"))
        self.client.force_login(user)
        html = self.client.get(reverse("core:profile")).content.decode()
        start = html.index('<header class="topbar">')
        self.assertIn("Sin perfil asignado", html[start : html.index("</header>", start)])


class LoadingStateMarkupTests(PortalTestCase):
    def test_the_script_is_loaded_before_the_validation(self):
        self.login_as("matias.cavieres")
        html = self.client.get(reverse("core:dashboard")).content.decode()
        self.assertLess(html.index("core/js/busy.js"), html.index("core/js/validation.js"))
        self.assertIsNotNone(finders.find("core/js/busy.js"))

    def test_the_search_forms_show_a_loading_state_but_the_excel_download_does_not(self):
        self.login_as("matias.cavieres")
        listing = self.client.get(reverse("core:atencion"))
        self.assertContains(listing, '<form method="get" class="atencion-search" role="search" data-validate data-loading>')
        self.assertContains(listing, 'name="formato" value="xlsx" formnovalidate data-skip-validate data-no-busy')
        atencion = self.client.get(reverse("core:atencion"), {"q": "perez"})
        self.assertContains(atencion, "data-loading")
        self.assertContains(atencion, "data-no-busy")

    def test_the_boards_and_reports_forms_show_a_loading_state(self):
        self.login_as("admin")
        for url in (reverse("core:delegation_board"), reverse("core:reports")):
            with self.subTest(url=url):
                self.assertContains(self.client.get(url), 'class="filters" data-loading')

    def test_the_forms_that_send_data_do_not_allow_a_double_send(self):
        self.login_as("admin")
        self.assertContains(self.client.get(reverse("core:beneficiarios_create")), "data-once")
        self.assertContains(self.client.get(reverse("core:profile")), "data-once")
        self.client.logout()
        self.assertContains(self.client.get(reverse("core:login")), "data-once")

    def test_the_old_double_send_code_is_gone_from_the_classic_script(self):
        # Ahora lo hace busy.js (con el indicador de carga); sgr.js no debe repetirlo.
        source = open(finders.find("core/js/sgr.js"), encoding="utf-8").read()
        self.assertNotIn("form[data-once]", source)


class PasswordToggleTests(PortalTestCase):
    def test_the_script_that_adds_the_eye_is_part_of_the_widgets(self):
        source = open(finders.find("core/js/widgets.js"), encoding="utf-8").read()
        self.assertIn('input[type=password]', source)
        self.assertIn("Mostrar contraseña", source)
        self.assertIn("Ocultar contraseña", source)
        self.assertIn("data-no-reveal", source)

    def test_every_password_screen_loads_the_widgets_and_keeps_a_plain_field_without_javascript(self):
        self.client.logout()
        login = self.client.get(reverse("core:login"))
        self.assertContains(login, 'type="password"')
        self.assertContains(login, "core/js/widgets.js")
        self.login_as("admin")
        for url in (reverse("core:profile"), reverse("core:usuarios_create")):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertContains(response, 'type="password"')
                self.assertContains(response, "core/js/widgets.js")
