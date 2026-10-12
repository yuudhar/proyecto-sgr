"""Pruebas de la recuperación de contraseña con código temporal.

Cubren las condiciones mínimas del flujo: código de 6 dígitos, vigencia de 120 segundos, un solo uso,
rechazo del código incorrecto, nuevo código cuando vence, contraseña nueva con las validaciones de
siempre y correo configurado desde el .env (esto último está en core/test_access_flow.py).
"""

import copy
import json
import re
from datetime import timedelta
from smtplib import SMTPException
from unittest import mock

from django.apps import apps
from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.staticfiles import finders
from django.core import mail
from django.core.cache import cache
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts import recovery
from core.models import AuditLog
from core.testing import PASSWORD, PortalTestCase

NEW_PASSWORD = "ClaveNueva#2026"
FAST_HASHER = ["django.contrib.auth.hashers.MD5PasswordHasher"]  # solo para que las pruebas corran rápido


@override_settings(PASSWORD_HASHERS=FAST_HASHER)
class RecoveryTestCase(PortalTestCase):
    username = "matias.cavieres"
    email = "matias.cavieres@sgr.example"

    def setUp(self):
        # Los intentos de cada código se cuentan en la caché: se vacía para que nada pase de una prueba a otra.
        cache.clear()
        self.addCleanup(cache.clear)
        # Una hora fija: así los vencimientos se comprueban al segundo, sin depender del reloj real.
        self.start = timezone.now().replace(microsecond=0)

    def at(self, seconds):
        """Hace que la hora del sistema sea la de partida más estos segundos, mientras dure el with."""
        return mock.patch("django.utils.timezone.now", return_value=self.start + timedelta(seconds=seconds))

    def ask_for_code(self, email=None, client=None, seconds=0):
        with self.at(seconds):
            return (client or self.client).post(reverse("accounts:recover"), {"email": email or self.email})

    def last_code(self):
        """El código de 6 dígitos del último correo enviado."""
        return re.search(r"^ {4}(\d{6})$", mail.outbox[-1].body, re.MULTILINE).group(1)

    def send_code(self, code, seconds=0, client=None):
        with self.at(seconds):
            return (client or self.client).post(reverse("accounts:recover_code"), {"code": code})

    def wrong_code(self, code):
        return "000000" if code != "000000" else "111111"

    def validate_code(self):
        """Pide un código y lo valida: deja a la persona en el paso de la contraseña nueva."""
        self.ask_for_code()
        return self.send_code(self.last_code())

    def user(self):
        return User.objects.get(username=self.username)

    def stored(self):
        """Copia de lo que la sesión del navegador tiene guardado, como diccionario común."""
        return copy.deepcopy(dict(self.client.session.items()))


class RecoveryRequestTests(RecoveryTestCase):
    def test_a_registered_email_gets_one_message_with_a_six_digit_code(self):
        response = self.ask_for_code()
        self.assertRedirects(response, reverse("accounts:recover_code"), fetch_redirect_response=False)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, [self.email])
        self.assertEqual(message.from_email, settings.DEFAULT_FROM_EMAIL)
        self.assertRegex(self.last_code(), r"^\d{6}$")
        self.assertIn("120 segundos", message.body)
        self.assertIn("solo se puede usar una vez", message.body)

    def test_the_code_stays_in_the_session_as_a_fingerprint_and_lasts_120_seconds(self):
        with (
            mock.patch("accounts.recovery.new_code", return_value="482915"),
            mock.patch("accounts.recovery.secrets.token_hex", return_value="0123456789abcdef"),
        ):
            self.ask_for_code()
        session = self.client.session
        [[user_pk, stored, sent_id]] = session["recovery_codes"]
        self.assertEqual(user_pk, self.user().pk)
        self.assertEqual(len(stored), 64)
        # Además de la huella se recuerda cuál fue el envío: es lo que deja sin efecto los códigos anteriores.
        self.assertEqual(sent_id, AuditLog.objects.get(event=recovery.SENT_EVENT, user=self.user()).pk)
        self.assertEqual(stored, recovery.fingerprint(user_pk, "482915", "0123456789abcdef"))
        self.assertNotIn("482915", json.dumps(dict(session.items())))  # el código no queda escrito en la sesión
        self.assertEqual(session["recovery_deadline"], (self.start + timedelta(seconds=120)).timestamp())
        self.assertEqual(session["recovery_sent_at"], self.start.timestamp())
        self.assertEqual(settings.RECOVERY_CODE_SECONDS, 120)
        self.assertEqual(recovery.failures(session), 0)

    def test_the_recovery_adds_no_table_to_the_data_model(self):
        models = {model.__name__ for model in apps.get_app_config("accounts").get_models()}
        # Los códigos viven en la sesión y la auditoría. Las tablas de la app son las cuentas: el perfil del usuario,
        # desde la v8 la ficha de cada rol (descripción, alcance y estado) y desde la v9 las delegaciones de cada
        # usuario (Usuario_Rol_Delegacion), que tampoco tienen que ver con esto.
        self.assertEqual(models, {"UserProfile", "RoleProfile", "UserRoleDelegation"})

    def test_an_unknown_email_gets_the_same_answer_and_no_message(self):
        known = self.ask_for_code()
        stranger = Client()
        response = self.ask_for_code("nadie@sgr.example", client=stranger)
        self.assertRedirects(response, known["Location"], fetch_redirect_response=False)
        self.assertEqual(len(mail.outbox), 1)  # solo el del correo que sí existe
        self.assertEqual(stranger.session["recovery_codes"], [])
        # La pantalla siguiente trae el mismo aviso y el mismo reloj, con el correo escondido.
        notice = "Si ese correo está registrado, te enviamos un código de 6 dígitos. Vale 120 segundos."
        page = stranger.get(reverse("accounts:recover_code"))
        self.assertContains(page, notice)
        self.assertContains(page, "na***@sgr.example")
        self.assertContains(self.client.get(reverse("accounts:recover_code")), notice)

    def test_a_code_typed_for_an_unknown_email_fails_like_a_wrong_one(self):
        stranger = Client()
        self.ask_for_code("nadie@sgr.example", client=stranger)
        response = self.send_code("123456", client=stranger)
        self.assertContains(response, "El código no es correcto. Te quedan 4 intentos.")

    def test_the_email_is_matched_ignoring_case_and_spaces(self):
        self.ask_for_code("  MATIAS.Cavieres@SGR.example ")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.email])

    def test_inactive_accounts_get_no_code(self):
        User.objects.filter(username=self.username).update(is_active=False)
        self.ask_for_code()
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(self.client.session["recovery_codes"], [])

    def test_a_badly_written_email_is_rejected_by_the_form(self):
        for text in ("sin-arroba", "a@b", "dos@@sgr.example", "con espacio@sgr.example"):
            with self.subTest(text=text):
                response = self.ask_for_code(text)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["form"].errors)
        self.assertEqual(len(mail.outbox), 0)

    def test_accounts_sharing_an_email_each_get_their_own_code(self):
        twin = User.objects.create_user("gemelo", email=self.email, password=PASSWORD)
        with mock.patch("accounts.recovery.new_code", side_effect=["111111", "222222"]):
            self.ask_for_code()
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual({m.to[0] for m in mail.outbox}, {self.email})  # los dos llegan a la misma dirección
        state = self.stored()
        self.assertEqual(len(state["recovery_codes"]), 2)
        # Cada código habilita solo a la cuenta a la que se envió.
        accepted = {recovery.check(copy.deepcopy(state), code).user for code in ("111111", "222222")}
        self.assertEqual(accepted, {self.user(), twin})

    def test_a_new_request_voids_the_previous_code(self):
        with mock.patch("accounts.recovery.new_code", side_effect=["111111", "222222"]):
            self.ask_for_code()
            self.ask_for_code(seconds=50)  # pasada la espera para pedir otro
        self.assertEqual(len(mail.outbox), 2)
        self.assertContains(self.send_code("111111", seconds=51), "El código no es correcto")
        self.assertRedirects(
            self.send_code("222222", seconds=52), reverse("accounts:recover_password"), fetch_redirect_response=False
        )

    def test_requests_per_hour_are_limited_with_the_same_answer(self):
        wait = settings.RECOVERY_RESEND_SECONDS + 5  # entre un pedido y otro hay que esperar
        for number in range(settings.RECOVERY_MAX_REQUESTS):
            self.ask_for_code(seconds=number * wait)
        self.assertEqual(len(mail.outbox), settings.RECOVERY_MAX_REQUESTS)
        response = self.ask_for_code(seconds=settings.RECOVERY_MAX_REQUESTS * wait)
        self.assertRedirects(response, reverse("accounts:recover_code"), fetch_redirect_response=False)
        self.assertEqual(len(mail.outbox), settings.RECOVERY_MAX_REQUESTS)  # no salió otro correo
        self.ask_for_code(seconds=3601)  # una hora después se puede pedir de nuevo
        self.assertEqual(len(mail.outbox), settings.RECOVERY_MAX_REQUESTS + 1)

    def test_a_failed_send_gives_the_same_answer_and_does_not_use_up_the_hourly_limit(self):
        with (
            mock.patch("accounts.recovery.send_mail", side_effect=SMTPException("sin conexión")),
            self.assertLogs("accounts.recovery", level="ERROR"),
        ):
            response = self.ask_for_code()
        # No se delata que el correo existe: la respuesta es la de siempre y el error queda solo en el registro del servidor.
        self.assertRedirects(response, reverse("accounts:recover_code"), fetch_redirect_response=False)
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(self.client.session["recovery_codes"], [])
        self.assertFalse(AuditLog.objects.filter(event=recovery.SENT_EVENT).exists())
        # Como no salió ningún correo, no se gastó ninguno de los códigos por hora.
        wait = settings.RECOVERY_RESEND_SECONDS + 5
        for number in range(settings.RECOVERY_MAX_REQUESTS):
            self.ask_for_code(seconds=(number + 1) * wait)
        self.assertEqual(len(mail.outbox), settings.RECOVERY_MAX_REQUESTS)

    def test_the_request_form_needs_the_csrf_token(self):
        strict = Client(enforce_csrf_checks=True)
        response = strict.post(reverse("accounts:recover"), {"email": self.email})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(len(mail.outbox), 0)

    def test_people_with_a_session_are_sent_to_their_profile(self):
        self.login_as(self.username)
        for name in ("accounts:recover", "accounts:recover_code", "accounts:recover_resend", "accounts:recover_password"):
            with self.subTest(name=name):
                self.assertRedirects(self.client.get(reverse(name)), reverse("core:profile"), fetch_redirect_response=False)
        self.client.post(reverse("accounts:recover"), {"email": self.email})
        self.client.post(reverse("accounts:recover_resend"))
        self.assertEqual(len(mail.outbox), 0)


class RecoveryCodeTests(RecoveryTestCase):
    def test_the_code_screen_needs_the_email_step_first(self):
        response = self.client.get(reverse("accounts:recover_code"), follow=True)
        self.assertRedirects(response, reverse("accounts:recover"))
        self.assertContains(response, "Primero escribe tu correo")

    def test_the_screen_shows_the_masked_email_and_the_seconds_left(self):
        self.ask_for_code()
        response = self.client.get(reverse("accounts:recover_code"))
        self.assertContains(response, "ma***@sgr.example")
        self.assertNotContains(response, self.email)
        self.assertTrue(100 < response.context["seconds_left"] <= 120)
        self.assertContains(response, 'data-countdown data-seconds="')
        self.assertContains(response, "Si ese correo está registrado, te enviamos un código de 6 dígitos. Vale 120 segundos.")

    def test_a_correct_code_opens_the_new_password_step(self):
        self.ask_for_code()
        response = self.send_code(self.last_code())
        self.assertRedirects(response, reverse("accounts:recover_password"), fetch_redirect_response=False)
        session = self.client.session
        self.assertEqual(session["recovery_user"], self.user().pk)
        self.assertNotIn("recovery_email", session)
        self.assertNotIn("recovery_codes", session)  # el código ya no está: quedó usado

    def test_a_code_works_only_once(self):
        self.ask_for_code()
        code = self.last_code()
        state = self.stored()
        self.assertEqual(recovery.check(state, code).user, self.user())
        self.assertIsNone(recovery.check(state, code).user)  # al aceptarlo se borró de la sesión

    def test_a_used_code_is_refused_on_the_screen_too(self):
        self.ask_for_code()
        code = self.last_code()
        self.send_code(code)  # primera vez: aceptado y usado
        response = self.send_code(code, seconds=5)
        self.assertRedirects(response, reverse("accounts:recover"), fetch_redirect_response=False)

    def test_a_wrong_code_is_rejected_and_counts_the_attempts(self):
        self.ask_for_code()
        code = self.last_code()
        response = self.send_code(self.wrong_code(code))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "El código no es correcto. Te quedan 4 intentos.")
        # El campo queda marcado (una sola vez) y la página muestra el aviso con el título propio de este paso.
        classes = response.context["form"].fields["code"].widget.attrs["class"].split()
        self.assertEqual(classes.count("is-invalid"), 1)
        self.assertContains(response, 'data-error-title="No se pudo validar el código"')
        self.assertEqual(recovery.failures(self.client.session), 1)
        self.assertNotIn("recovery_user", self.client.session)
        # Un error no gasta el código: el correcto sigue sirviendo.
        self.assertRedirects(self.send_code(code), reverse("accounts:recover_password"), fetch_redirect_response=False)

    def test_the_last_attempt_is_announced_in_singular(self):
        self.ask_for_code()
        code = self.last_code()
        for _ in range(3):
            self.send_code(self.wrong_code(code))
        self.assertContains(self.send_code(self.wrong_code(code)), "Te queda 1 intento.")

    def test_after_five_failures_not_even_the_right_code_works(self):
        self.ask_for_code()
        code = self.last_code()
        before = self.stored()  # la sesión tal como la vería un envío paralelo que la cargó antes de los intentos
        for _ in range(settings.RECOVERY_MAX_ATTEMPTS):
            response = self.send_code(self.wrong_code(code))
        self.assertContains(response, "Ya no quedan intentos: pide uno nuevo.")
        # Sin intentos no se muestra el reloj: el aviso dice que hay que pedir otro código.
        self.assertContains(response, "Ya no quedan intentos con este código. Pide uno nuevo para seguir.")
        self.assertNotContains(response, "data-countdown-clock")
        response = self.send_code(code)
        self.assertContains(response, "Fallaste demasiadas veces con este código. Pide uno nuevo.")
        self.assertNotIn("recovery_user", self.client.session)
        self.assertContains(response, 'class="btn btn-primary btn-sm" data-resend data-new-code')
        # El límite lo lleva el servidor, no lo que diga la sesión: con la sesión de antes tampoco pasa.
        self.assertEqual(recovery.check(before, code).problem, recovery.LOCKED)

    def test_attempts_are_counted_before_checking_so_parallel_requests_cannot_exceed_the_limit(self):
        self.ask_for_code()
        code = self.last_code()
        state = self.stored()
        results = [recovery.check(copy.deepcopy(state), self.wrong_code(code)) for _ in range(8)]
        self.assertEqual(
            [result.problem for result in results],
            [recovery.WRONG] * settings.RECOVERY_MAX_ATTEMPTS + [recovery.LOCKED] * 3,
        )
        self.assertEqual([result.left for result in results[:5]], [4, 3, 2, 1, 0])

    def test_an_expired_code_is_rejected_and_asking_for_a_new_one_works(self):
        self.ask_for_code()
        old = self.last_code()
        response = self.send_code(old, seconds=121)
        self.assertContains(response, "El código venció: duraba 120 segundos. Pide uno nuevo.")
        self.assertNotIn("recovery_user", self.client.session)
        self.assertEqual(recovery.failures(self.client.session), 0)  # un código vencido no gasta intentos
        # La pantalla ofrece pedir otro, y el nuevo sí funciona.
        self.assertContains(response, 'class="btn btn-primary btn-sm" data-resend data-new-code')
        self.ask_for_code(seconds=130)
        new = self.last_code()
        self.assertEqual(len(mail.outbox), 2)
        self.assertRedirects(
            self.send_code(new, seconds=140), reverse("accounts:recover_password"), fetch_redirect_response=False
        )

    def test_the_expiry_is_checked_to_the_second(self):
        self.ask_for_code()
        code = self.last_code()
        self.assertContains(self.send_code(code, seconds=120), "El código venció")
        self.assertRedirects(
            self.send_code(code, seconds=119), reverse("accounts:recover_password"), fetch_redirect_response=False
        )

    def test_the_server_rejects_an_expired_code_even_if_the_screen_lets_it_through(self):
        # La cuenta regresiva es solo un aviso: el servidor revisa el vencimiento con su propio reloj.
        self.ask_for_code()
        code = self.last_code()
        state = self.stored()
        with self.at(121):
            self.assertEqual(recovery.check(copy.deepcopy(state), code).problem, recovery.EXPIRED)
        with self.at(119):
            self.assertEqual(recovery.check(copy.deepcopy(state), code).user, self.user())

    def test_a_code_of_another_account_does_not_work(self):
        with mock.patch("accounts.recovery.new_code", side_effect=["111111", "222222"]):
            self.ask_for_code()
            self.ask_for_code("matias.quiroz@sgr.example", client=Client())
        response = self.send_code("222222")  # el código de matias.quiroz, escrito en la recuperación de matias.cavieres
        self.assertContains(response, "El código no es correcto")
        self.assertNotIn("recovery_user", self.client.session)
        self.assertRedirects(self.send_code("111111"), reverse("accounts:recover_password"), fetch_redirect_response=False)

    def test_a_code_from_another_browser_session_does_not_work(self):
        # El código vale solo en la sesión que lo pidió: otra sesión con el mismo correo no lo puede usar.
        self.ask_for_code()
        code = self.last_code()
        other = Client()
        self.ask_for_code(client=other)
        self.assertNotEqual(self.client.session["recovery_nonce"], other.session["recovery_nonce"])
        self.assertContains(self.send_code(code, client=other), "El código no es correcto")

    def test_codes_written_with_spaces_are_accepted_and_bad_formats_rejected(self):
        self.ask_for_code()
        code = self.last_code()
        for text in ("12345", "1234567", "abcdef", "12 34 5a", "１２３４５６"):
            with self.subTest(text=text):
                response = self.send_code(text)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "El código tiene 6 dígitos, solo números.")
        self.assertEqual(recovery.failures(self.client.session), 0)  # un formato malo no gasta intentos
        spaced = f"{code[:3]} {code[3:]}"
        self.assertRedirects(self.send_code(spaced), reverse("accounts:recover_password"), fetch_redirect_response=False)

    def test_the_code_form_needs_the_csrf_token(self):
        self.ask_for_code()
        strict = Client(enforce_csrf_checks=True)
        strict.cookies = self.client.cookies
        response = strict.post(reverse("accounts:recover_code"), {"code": self.last_code()})
        self.assertEqual(response.status_code, 403)
        self.assertTrue(self.client.session["recovery_codes"])  # el código sigue sin usar

    def test_the_typed_code_is_hidden_from_error_reports(self):
        self.ask_for_code()
        response = self.send_code(self.wrong_code(self.last_code()))
        self.assertEqual(list(response.wsgi_request.sensitive_post_parameters), ["code"])


class RecoveryPasswordTests(RecoveryTestCase):
    def test_the_step_needs_a_validated_code(self):
        response = self.client.get(reverse("accounts:recover_password"), follow=True)
        self.assertRedirects(response, reverse("accounts:recover"))
        self.assertContains(response, "primero hay que validar el código")
        self.ask_for_code()  # tener el correo escrito tampoco alcanza
        self.assertRedirects(
            self.client.get(reverse("accounts:recover_password")),
            reverse("accounts:recover"),
            fetch_redirect_response=False,
        )
        self.assertEqual(self.client.post(reverse("accounts:recover_password"), {"new_password1": NEW_PASSWORD, "new_password2": NEW_PASSWORD}).status_code, 302)
        self.assertTrue(self.user().check_password(PASSWORD))

    def test_the_screen_asks_for_confirmation_before_saving_the_new_password(self):
        # SweetAlert2 solo pregunta (confirm.js): el servidor sigue siendo quien valida y guarda.
        self.validate_code()
        response = self.client.get(reverse("accounts:recover_password"))
        self.assertContains(response, "data-confirm-submit")
        self.assertContains(response, 'data-confirm-title="¿Guardar la contraseña nueva?"')
        self.assertContains(response, 'data-confirm-button="Sí, guardar contraseña"')
        self.assertContains(response, 'data-cancel-text="Todavía no se cambió tu contraseña."')

    def test_the_permission_to_choose_a_password_expires(self):
        self.validate_code()
        with self.at(settings.RECOVERY_PASSWORD_SECONDS + 1):
            response = self.client.get(reverse("accounts:recover_password"), follow=True)
        self.assertRedirects(response, reverse("accounts:recover"))
        # El aviso dice que se acabó el tiempo, no que se saltó el paso del código.
        self.assertContains(response, "Pasaron más de 10 minutos desde que validaste el código")
        self.assertNotContains(response, "primero hay que validar el código")
        self.assertNotIn("recovery_user", self.client.session)

    def test_weak_passwords_are_rejected_and_the_person_can_try_again(self):
        self.validate_code()
        url = reverse("accounts:recover_password")
        # Demasiado corta, común, solo números y parecida al nombre de usuario.
        for password in ("abc", "password", "12345678", "matias.cavieres"):
            with self.subTest(password=password):
                response = self.client.post(url, {"new_password1": password, "new_password2": password})
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["form"].errors["new_password1"])
                self.assertNotIn("new_password2", response.context["form"].errors)
        response = self.client.post(url, {"new_password1": NEW_PASSWORD, "new_password2": "Otra#Distinta1"})
        self.assertContains(response, "Las dos contraseñas nuevas no son iguales.")
        self.assertTrue(self.user().check_password(PASSWORD))  # nada cambió
        self.assertIn("recovery_user", self.client.session)  # y sigue pudiendo intentar
        self.assertEqual(list(response.wsgi_request.sensitive_post_parameters), ["new_password1", "new_password2"])

    def test_a_strong_password_is_saved_and_the_person_goes_back_to_login(self):
        self.validate_code()
        response = self.client.post(
            reverse("accounts:recover_password"),
            {"new_password1": NEW_PASSWORD, "new_password2": NEW_PASSWORD},
            follow=True,
        )
        self.assertRedirects(response, reverse("core:login"))
        self.assertContains(response, "Cambiaste tu contraseña. Ya puedes ingresar con la nueva.")
        self.assertNotIn("recovery_user", self.client.session)
        user = self.user()
        self.assertTrue(user.check_password(NEW_PASSWORD))
        self.assertFalse(user.check_password(PASSWORD))
        login = self.client.post(reverse("core:login"), {"username": self.username, "password": NEW_PASSWORD})
        self.assertRedirects(login, reverse("core:dashboard"))

    def test_the_old_password_stops_working_and_other_open_sessions_close(self):
        elsewhere = Client()
        elsewhere.post(reverse("core:login"), {"username": self.username, "password": PASSWORD})
        self.assertEqual(elsewhere.get(reverse("core:dashboard")).status_code, 200)
        self.validate_code()
        self.client.post(
            reverse("accounts:recover_password"), {"new_password1": NEW_PASSWORD, "new_password2": NEW_PASSWORD}
        )
        self.assertEqual(elsewhere.get(reverse("core:dashboard")).status_code, 302)
        rejected = Client().post(reverse("core:login"), {"username": self.username, "password": PASSWORD})
        self.assertContains(rejected, "El usuario, el correo o la contraseña no son correctos")

    def test_the_code_cannot_be_used_again_after_the_change(self):
        self.ask_for_code()
        code = self.last_code()
        self.send_code(code)
        self.client.post(
            reverse("accounts:recover_password"), {"new_password1": NEW_PASSWORD, "new_password2": NEW_PASSWORD}
        )
        session = self.client.session
        self.assertFalse([key for key in recovery.ALL_KEYS if key in session])  # no queda nada de la recuperación
        # El código no vuelve a servir ni se puede entrar de nuevo al paso de la contraseña.
        self.assertRedirects(self.send_code(code), reverse("accounts:recover"), fetch_redirect_response=False)
        self.assertRedirects(
            self.client.get(reverse("accounts:recover_password")), reverse("accounts:recover"), fetch_redirect_response=False
        )

    def test_the_whole_flow_is_audited_without_secrets(self):
        self.ask_for_code()
        code = self.last_code()
        self.send_code(code)
        self.client.post(
            reverse("accounts:recover_password"), {"new_password1": NEW_PASSWORD, "new_password2": NEW_PASSWORD}
        )
        events = list(AuditLog.objects.filter(user=self.user()).values_list("event", flat=True))
        for event in (
            "Código de recuperación enviado",
            "Código de recuperación validado",
            "Contraseña restablecida con código",
        ):
            self.assertIn(event, events)
        for entry in AuditLog.objects.filter(user=self.user(), event__in=events):
            self.assertIsNone(entry.previous_value)
            self.assertIsNone(entry.new_value)

    def test_the_password_form_needs_the_csrf_token(self):
        self.validate_code()
        strict = Client(enforce_csrf_checks=True)
        strict.cookies = self.client.cookies
        response = strict.post(
            reverse("accounts:recover_password"), {"new_password1": NEW_PASSWORD, "new_password2": NEW_PASSWORD}
        )
        self.assertEqual(response.status_code, 403)
        self.assertTrue(self.user().check_password(PASSWORD))


class RecoveryResendTests(RecoveryTestCase):
    """Reenvío (Clase 6): un código nuevo deja sin efecto los anteriores de la cuenta, con espera entre un pedido y otro."""

    def resend(self, seconds=0, client=None):
        with self.at(seconds):
            return (client or self.client).post(reverse("accounts:recover_resend"))

    def code_page(self, seconds=0, client=None):
        with self.at(seconds):
            return (client or self.client).get(reverse("accounts:recover_code"))

    def test_the_code_screen_offers_the_resend_button_with_the_waiting_time(self):
        self.ask_for_code()
        page = self.code_page(seconds=10)
        self.assertContains(page, f'action="{reverse("accounts:recover_resend")}"')
        self.assertEqual(page.context["resend_seconds"], settings.RECOVERY_RESEND_SECONDS - 10)
        self.assertContains(page, 'data-resend data-new-code data-seconds="35"')
        self.assertContains(page, "Reenviar código (en 35 s)")
        ready = self.code_page(seconds=settings.RECOVERY_RESEND_SECONDS)
        self.assertEqual(ready.context["resend_seconds"], 0)
        self.assertContains(ready, 'data-seconds="0"')
        self.assertNotContains(ready, "Reenviar código (en")

    def test_the_waiting_time_is_45_seconds(self):
        self.assertEqual(settings.RECOVERY_RESEND_SECONDS, 45)

    def test_resending_too_soon_sends_nothing_and_says_how_long_to_wait(self):
        self.ask_for_code()
        code = self.last_code()
        response = self.resend(seconds=10)
        self.assertRedirects(response, reverse("accounts:recover_code"), fetch_redirect_response=False)
        self.assertEqual(len(mail.outbox), 1)
        self.assertContains(self.code_page(seconds=10), "Espera 35 segundos para pedir otro código.")
        self.assertEqual(AuditLog.objects.filter(event=recovery.SENT_EVENT).count(), 1)
        # Nada cambió: el código del primer correo sigue sirviendo.
        self.assertRedirects(
            self.send_code(code, seconds=11), reverse("accounts:recover_password"), fetch_redirect_response=False
        )

    def test_the_last_second_of_the_wait_is_announced_in_singular(self):
        self.ask_for_code()
        self.resend(seconds=settings.RECOVERY_RESEND_SECONDS - 1)
        self.assertContains(
            self.code_page(seconds=settings.RECOVERY_RESEND_SECONDS - 1), "Espera 1 segundo para pedir otro código."
        )

    def test_resending_after_the_wait_sends_a_new_code_and_voids_the_old_one(self):
        with mock.patch("accounts.recovery.new_code", side_effect=["111111", "222222"]):
            self.ask_for_code()
            response = self.resend(seconds=46)
        self.assertRedirects(response, reverse("accounts:recover_code"), fetch_redirect_response=False)
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(mail.outbox[1].to, [self.email])
        page = self.code_page(seconds=47)
        self.assertContains(page, "te enviamos un código nuevo de 6 dígitos. El anterior ya no sirve. Vale 120 segundos.")
        # El código nuevo vale 120 segundos desde que se envió (no desde el primero) y vuelve a tener 5 intentos.
        self.assertEqual(page.context["seconds_left"], 119)
        self.assertEqual(recovery.failures(self.client.session), 0)
        self.assertEqual(page.context["resend_seconds"], settings.RECOVERY_RESEND_SECONDS - 1)
        self.assertContains(self.send_code("111111", seconds=47), "El código no es correcto")
        self.assertRedirects(
            self.send_code("222222", seconds=48), reverse("accounts:recover_password"), fetch_redirect_response=False
        )

    def test_every_send_is_in_the_audit_log_and_the_last_one_is_the_live_code(self):
        user = self.user()
        self.assertIsNone(recovery.live_code_id(user))
        self.ask_for_code()
        first = recovery.live_code_id(user)
        self.resend(seconds=50)
        second = recovery.live_code_id(user)
        sent = list(AuditLog.objects.filter(user=user, event=recovery.SENT_EVENT).order_by("pk").values_list("pk", flat=True))
        self.assertEqual(sent, [first, second])
        self.assertGreater(second, first)

    def test_a_resend_without_a_started_recovery_goes_back_to_the_first_step(self):
        response = self.resend()
        self.assertRedirects(response, reverse("accounts:recover"), fetch_redirect_response=False)
        self.assertEqual(len(mail.outbox), 0)
        self.assertContains(self.client.get(reverse("accounts:recover")), "Primero escribe tu correo")

    def test_a_link_does_not_resend_and_the_button_needs_the_csrf_token(self):
        self.ask_for_code()
        with self.at(60):
            response = self.client.get(reverse("accounts:recover_resend"))
        self.assertRedirects(response, reverse("accounts:recover_code"), fetch_redirect_response=False)
        strict = Client(enforce_csrf_checks=True)
        strict.cookies = self.client.cookies
        with self.at(60):
            denied = strict.post(reverse("accounts:recover_resend"))
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(len(mail.outbox), 1)

    def test_typing_the_same_email_again_also_waits(self):
        self.ask_for_code()
        response = self.ask_for_code(seconds=10)
        self.assertRedirects(response, reverse("accounts:recover_code"), fetch_redirect_response=False)
        self.assertEqual(len(mail.outbox), 1)
        self.assertContains(self.code_page(seconds=10), "Espera 35 segundos para pedir otro código.")
        self.ask_for_code(seconds=46)
        self.assertEqual(len(mail.outbox), 2)

    def test_another_email_does_not_wait_for_the_first_one(self):
        self.ask_for_code()
        self.ask_for_code("matias.quiroz@sgr.example", seconds=10)
        self.assertEqual([message.to for message in mail.outbox], [[self.email], ["matias.quiroz@sgr.example"]])

    def test_the_wait_and_the_notices_are_the_same_for_an_email_nobody_has(self):
        known, stranger = Client(), Client()
        self.ask_for_code(client=known)
        self.ask_for_code("nadie@sgr.example", client=stranger)
        for seconds, expected in ((10, "Espera 35 segundos para pedir otro código."), (46, "te enviamos un código nuevo")):
            self.resend(seconds=seconds, client=known)
            self.resend(seconds=seconds, client=stranger)
            for client in (known, stranger):
                self.assertContains(self.code_page(seconds=seconds, client=client), expected)
        self.assertEqual(len(mail.outbox), 2)  # el desconocido no recibió nada, ni la primera vez ni al reenviar
        self.assertEqual(stranger.session["recovery_codes"], [])

    def test_resends_count_for_the_hourly_limit(self):
        wait = settings.RECOVERY_RESEND_SECONDS + 5
        self.ask_for_code()
        for number in range(1, settings.RECOVERY_MAX_REQUESTS + 2):
            self.resend(seconds=number * wait)
        self.assertEqual(len(mail.outbox), settings.RECOVERY_MAX_REQUESTS)  # el pedido inicial y cuatro reenvíos
        self.assertEqual(AuditLog.objects.filter(event=recovery.SENT_EVENT).count(), settings.RECOVERY_MAX_REQUESTS)


class RecoveryVoidedCodeTests(RecoveryTestCase):
    """Clase 6: «Solicitar un nuevo código debe invalidar los anteriores activos del mismo usuario»."""

    def test_a_code_requested_from_another_browser_voids_the_one_in_this_browser(self):
        other = Client()
        with mock.patch("accounts.recovery.new_code", side_effect=["111111", "222222"]):
            self.ask_for_code()  # navegador 1
            self.ask_for_code(client=other, seconds=1)  # navegador 2, la misma cuenta
        self.assertEqual(len(mail.outbox), 2)
        response = self.send_code("111111", seconds=2)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ese código ya no sirve: se pidió uno más nuevo para esta cuenta.")
        self.assertNotIn("recovery_user", self.client.session)
        # La pantalla invita a pedir otro desde aquí.
        self.assertContains(response, 'class="btn btn-primary btn-sm" data-resend data-new-code')
        # El código nuevo sí sirve, en el navegador que lo pidió.
        self.assertRedirects(
            self.send_code("222222", client=other, seconds=3),
            reverse("accounts:recover_password"),
            fetch_redirect_response=False,
        )

    def test_a_replaced_code_is_only_pointed_out_to_whoever_typed_it_right(self):
        other = Client()
        with mock.patch("accounts.recovery.new_code", side_effect=["111111", "222222"]):
            self.ask_for_code()
            self.ask_for_code(client=other, seconds=1)
        page = self.client.get(reverse("accounts:recover_code"))
        self.assertNotContains(page, "ya no sirve")  # mirar la pantalla no dice nada
        response = self.send_code(self.wrong_code("111111"), seconds=2)
        self.assertContains(response, "El código no es correcto")  # un código equivocado recibe la respuesta de siempre
        self.assertNotContains(response, "ya no sirve")

    def test_a_replaced_code_still_uses_up_an_attempt(self):
        other = Client()
        with mock.patch("accounts.recovery.new_code", side_effect=["111111", "222222"]):
            self.ask_for_code()
            self.ask_for_code(client=other, seconds=1)
        self.send_code("111111", seconds=2)
        self.assertEqual(recovery.failures(self.client.session), 1)

    def test_a_code_for_one_account_does_not_void_the_code_of_another(self):
        with mock.patch("accounts.recovery.new_code", side_effect=["111111", "222222"]):
            self.ask_for_code()
            self.ask_for_code("matias.quiroz@sgr.example", client=Client(), seconds=1)
        self.assertRedirects(
            self.send_code("111111", seconds=2), reverse("accounts:recover_password"), fetch_redirect_response=False
        )

    def test_an_accepted_code_is_no_longer_live_and_stays_used(self):
        self.ask_for_code()
        code = self.last_code()
        before = self.stored()  # la sesión con el código todavía sin usar
        self.send_code(code, seconds=1)
        user = self.user()
        self.assertIsNone(recovery.live_code_id(user))
        # Una copia de la sesión de antes (por ejemplo, una petición que se cruzó con la primera) tampoco lo vuelve a usar.
        with self.at(2):
            result = recovery.check(copy.deepcopy(before), code)
        self.assertEqual(result.problem, recovery.SUPERSEDED)
        self.assertIsNone(result.user)
        self.assertEqual(AuditLog.objects.filter(user=user, event=recovery.VALIDATED_EVENT).count(), 1)

    def test_the_audit_trail_of_a_flow_is_sent_then_validated(self):
        self.ask_for_code()
        self.send_code(self.last_code(), seconds=1)
        events = list(
            AuditLog.objects.filter(user=self.user(), event__startswith="Código de recuperación")
            .order_by("pk")
            .values_list("event", flat=True)
        )
        self.assertEqual(events, [recovery.SENT_EVENT, recovery.VALIDATED_EVENT])

    def test_a_failed_send_does_not_void_the_code_that_is_still_live(self):
        self.ask_for_code()
        user = self.user()
        live = recovery.live_code_id(user)
        with (
            mock.patch("accounts.recovery.send_mail", side_effect=SMTPException("sin conexión")),
            self.assertLogs("accounts.recovery", level="ERROR"),
        ):
            self.ask_for_code(client=Client(), seconds=1)
        self.assertEqual(recovery.live_code_id(user), live)


class RecoveryCodeBoxesTests(RecoveryTestCase):
    def test_the_code_field_is_marked_to_become_six_boxes_and_still_works_without_scripts(self):
        self.ask_for_code()
        page = self.client.get(reverse("accounts:recover_code"))
        # Sin JavaScript queda el campo de texto de siempre, el que se envía con el nombre «code».
        self.assertContains(page, 'name="code"')
        self.assertContains(page, 'data-code-boxes="6"')
        self.assertContains(page, "core/js/code-boxes.js")
        self.assertContains(page, "core/js/countdown.js")
        for name in ("code-boxes.js", "countdown.js"):
            self.assertIsNotNone(finders.find(f"core/js/{name}"))


class RecoveryHelperTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

    def test_codes_have_six_digits_and_keep_the_leading_zeros(self):
        for _ in range(200):
            self.assertRegex(recovery.new_code(), r"^\d{6}$")
        with mock.patch("accounts.recovery.secrets.randbelow", return_value=42):
            self.assertEqual(recovery.new_code(), "000042")

    def test_masking_keeps_only_the_start_and_the_domain(self):
        self.assertEqual(recovery.mask_email("ana.torres@dominio.cl"), "an***@dominio.cl")
        self.assertEqual(recovery.mask_email("a@dominio.cl"), "a***@dominio.cl")

    def test_the_fingerprint_depends_on_the_account_the_shipment_and_the_code(self):
        base = recovery.fingerprint(1, "123456", "a")
        self.assertEqual(base, recovery.fingerprint(1, "123456", "a"))
        self.assertNotEqual(base, recovery.fingerprint(2, "123456", "a"))
        self.assertNotEqual(base, recovery.fingerprint(1, "123456", "b"))
        self.assertNotEqual(base, recovery.fingerprint(1, "123457", "a"))
        self.assertNotIn("123456", base)

    def test_the_counter_adds_one_each_time(self):
        self.assertEqual([recovery._count("prueba", 60) for _ in range(3)], [1, 2, 3])
        cache.delete("prueba")
        self.assertEqual(recovery._count("prueba", 60), 1)

    def test_checking_a_session_without_a_pending_code_never_accepts(self):
        for state in ({}, {recovery.CODES_KEY: [], recovery.NONCE_KEY: "x"}):
            with self.subTest(state=state):
                self.assertIsNone(recovery.check(state, "123456").user)


class RecoveryBlankEmailTests(TestCase):
    def test_a_blank_email_matches_nobody_even_if_some_accounts_have_no_email(self):
        User.objects.create_user("sin_correo", password="x")
        self.assertFalse(recovery.users_for("").exists())
        self.assertFalse(recovery.users_for(None).exists())
        self.assertFalse(recovery.users_for("   ").exists())
