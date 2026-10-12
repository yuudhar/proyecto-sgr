"""Pruebas del ingreso con el nombre de usuario o con el correo (accounts/backends.py)."""

from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.test import override_settings
from django.urls import reverse

from core.testing import PASSWORD, PortalTestCase

FAST_HASHER = ["django.contrib.auth.hashers.MD5PasswordHasher"]  # solo para que las pruebas corran rápido


@override_settings(PASSWORD_HASHERS=FAST_HASHER)
class EmailOrUsernameLoginTests(PortalTestCase):
    def login(self, who, password=PASSWORD, client=None):
        return (client or self.client).post(reverse("core:login"), {"username": who, "password": password})

    def assertEntered(self, response, username):
        self.assertRedirects(response, reverse("core:dashboard"), fetch_redirect_response=False)
        self.assertEqual(int(self.client.session["_auth_user_id"]), User.objects.get(username=username).pk)

    def assertRefused(self, response):
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "El usuario, el correo o la contraseña no son correctos")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_the_username_still_works(self):
        self.assertEntered(self.login("matias.cavieres"), "matias.cavieres")

    def test_the_email_works(self):
        self.assertEntered(self.login("matias.cavieres@sgr.example"), "matias.cavieres")

    def test_the_email_ignores_case_and_surrounding_spaces(self):
        self.assertEntered(self.login("  Matias.Cavieres@SGR.Example "), "matias.cavieres")

    def test_the_username_is_still_case_sensitive(self):
        self.assertRefused(self.login("Matias.Cavieres"))

    def test_a_wrong_password_is_refused_with_the_username_and_with_the_email(self):
        for who in ("matias.cavieres", "matias.cavieres@sgr.example"):
            with self.subTest(who=who):
                self.assertRefused(self.login(who, "otra"))

    def test_nothing_tells_which_part_failed(self):
        wrong_password = self.login("matias.cavieres@sgr.example", "otra")
        unknown_email = self.login("nadie@sgr.example")
        unknown_user = self.login("no.existe")
        messages = {tuple(r.context["form"].non_field_errors()) for r in (wrong_password, unknown_email, unknown_user)}
        self.assertEqual(len(messages), 1)

    def test_an_inactive_account_cannot_enter_by_either_way(self):
        User.objects.filter(username="matias.cavieres").update(is_active=False)
        for who in ("matias.cavieres", "matias.cavieres@sgr.example"):
            with self.subTest(who=who):
                self.assertRefused(self.login(who))

    def test_an_email_shared_by_two_accounts_does_not_let_anyone_in_by_email(self):
        User.objects.filter(username="matias.quiroz").update(email="matias.cavieres@sgr.example")
        self.assertRefused(self.login("matias.cavieres@sgr.example"))
        # cada una sigue pudiendo ingresar con su usuario
        self.assertEntered(self.login("matias.cavieres"), "matias.cavieres")
        self.client.logout()
        self.assertEntered(self.login("matias.quiroz"), "matias.quiroz")

    def test_an_exact_username_wins_over_the_email_of_another_account(self):
        # Alguien tiene como usuario el correo de otra persona: el usuario exacto gana, así que nadie le quita el
        # ingreso a esa cuenta, y la otra persona no entra con ese texto (puede usar su usuario).
        User.objects.create_user("matias.cavieres@sgr.example", password="Otra123!xyz")
        self.assertRefused(self.login("matias.cavieres@sgr.example", PASSWORD))
        self.assertEntered(self.login("matias.cavieres@sgr.example", "Otra123!xyz"), "matias.cavieres@sgr.example")
        self.client.logout()
        self.assertEntered(self.login("matias.cavieres"), "matias.cavieres")

    def test_an_account_without_email_enters_only_with_its_username(self):
        User.objects.filter(username="matias.cavieres").update(email="")
        self.assertRefused(self.login("matias.cavieres@sgr.example"))  # el correo que tenía ya no es suyo
        self.assertEntered(self.login("matias.cavieres"), "matias.cavieres")

    def test_the_session_and_the_last_login_are_set_like_with_the_username(self):
        user = User.objects.get(username="matias.cavieres")
        before = user.last_login
        self.assertEntered(self.login("matias.cavieres@sgr.example"), "matias.cavieres")
        user.refresh_from_db()
        self.assertNotEqual(user.last_login, before)
        self.assertEqual(self.client.get(reverse("core:dashboard")).status_code, 200)

    def test_permissions_still_come_from_the_groups(self):
        self.login("matias.cavieres@sgr.example")
        self.assertEqual(self.client.get(reverse("core:actividades_create")).status_code, 200)
        self.client.logout()
        self.login("consulta1@sgr.example")
        self.assertEqual(self.client.get(reverse("core:actividades_create")).status_code, 403)

    def test_the_backend_ignores_calls_without_credentials(self):
        self.assertIsNone(authenticate(username=None, password=None))
        self.assertIsNone(authenticate(username="matias.cavieres", password=None))
        self.assertIsNone(authenticate(username="", password=PASSWORD))
        self.assertIsNone(authenticate(username="   ", password=PASSWORD))
        self.assertIsNotNone(authenticate(username="matias.cavieres@sgr.example", password=PASSWORD))

    def test_the_login_screen_says_user_or_email(self):
        response = self.client.get(reverse("core:login"))
        self.assertContains(response, "Usuario o correo")
        field = response.context["form"].fields["username"]
        self.assertEqual(field.max_length, 254)
        self.assertContains(response, 'maxlength="254"')

    def test_the_django_admin_accepts_both_too(self):
        for who in ("admin", "admin@sgr.example"):
            with self.subTest(who=who):
                self.client.logout()
                response = self.client.post("/admin/login/?next=/admin/", {"username": who, "password": PASSWORD})
                self.assertRedirects(response, "/admin/", fetch_redirect_response=False)
