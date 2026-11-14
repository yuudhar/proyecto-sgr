import re
from datetime import datetime, timedelta
from smtplib import SMTPException
from unittest import mock
from urllib.parse import urlsplit

from django.apps import apps
from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.auth.tokens import PasswordResetTokenGenerator, default_token_generator
from django.core import mail
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.utils.http import urlsafe_base64_encode

from accounts import recovery
from accounts.forms import RecoveryRequestForm
from core.models import AuditLog
from core.testing import PASSWORD, PortalTestCase

NEW_PASSWORD = "ClaveNueva#2026"
FAST_HASHER = ["django.contrib.auth.hashers.MD5PasswordHasher"]
LINK = re.compile(r"^(https?://\S+/recuperar/[^/\s]+/[^/\s]+/)$", re.MULTILINE)
SET_PASSWORD = "set-password"


@override_settings(PASSWORD_HASHERS=FAST_HASHER)
class RecoveryTestCase(PortalTestCase):
    username = "matias.cavieres"
    email = "matias.cavieres@sgr.example"

    def setUp(self):
        self.start = timezone.now().replace(microsecond=0)
        self.token_start = datetime.now()  # una sola vez: si se pidiera en cada reloj, un cambio de segundo desfasaría 1 s los tokens

    def at(self, seconds):
        return mock.patch("django.utils.timezone.now", return_value=self.start + timedelta(seconds=seconds))

    def token_clock(self, seconds=0):
        """Adelanta el reloj con el que Django firma y revisa los tokens (no usa timezone.now)."""
        moment = self.token_start + timedelta(seconds=seconds)
        return mock.patch.object(PasswordResetTokenGenerator, "_now", lambda generator: moment)

    def ask_for_link(self, email=None, client=None, seconds=0):
        with self.at(seconds):
            return (client or self.client).post(reverse("accounts:recover"), {"email": email or self.email})

    def link_in(self, message):
        return LINK.search(message.body).group(1)

    def last_link(self):
        return self.link_in(mail.outbox[-1])

    def path_of(self, link):
        return urlsplit(link).path

    def open_link(self, link=None, client=None):
        """Abre el enlace del correo; con enlace vigente Django guarda el token y redirige a la pantalla sin token."""
        return (client or self.client).get(self.path_of(link or self.last_link()))

    def choose(self, passwords=NEW_PASSWORD, client=None, link=None):
        """Abre el enlace y envía la contraseña nueva. Devuelve la respuesta del envío."""
        client = client or self.client
        opened = self.open_link(link, client=client)
        self.assertEqual(opened.status_code, 302, "el enlace debería estar vigente")
        return client.post(opened["Location"], {"new_password1": passwords, "new_password2": passwords})

    def user(self):
        return User.objects.get(username=self.username)


class RecoveryRequestTests(RecoveryTestCase):
    def test_a_registered_email_gets_one_message_with_a_link(self):
        response = self.ask_for_link()
        self.assertRedirects(response, reverse("accounts:recover_done"), fetch_redirect_response=False)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, [self.email])
        self.assertEqual(message.from_email, settings.DEFAULT_FROM_EMAIL)
        self.assertEqual(message.subject, "Elige una contraseña nueva para tu cuenta del SGR")
        uid = LINK.search(message.body).group(1).split("/")[-3]
        self.assertEqual(uid, urlsafe_base64_encode(str(self.user().pk).encode()))
        self.assertIn("El enlace vale 1 hora", message.body)
        self.assertIn("solo se puede usar una vez", message.body)

    def test_the_link_is_the_one_django_signs_and_it_is_not_a_six_digit_code(self):
        self.ask_for_link()
        link = self.last_link()
        token = link.rstrip("/").split("/")[-1]
        self.assertTrue(default_token_generator.check_token(self.user(), token))
        self.assertNotRegex(mail.outbox[0].body, r"(?m)^ {4}\d{6}$")
        self.assertEqual(settings.PASSWORD_RESET_TIMEOUT, 3600)

    def test_the_message_also_comes_as_html_with_the_button_and_the_portal_colours(self):
        self.ask_for_link()
        message = mail.outbox[0]
        [(html, mimetype)] = message.alternatives
        self.assertEqual(mimetype, "text/html")
        link = self.last_link()
        self.assertIn(f'href="{link}"', html)
        self.assertIn("Elegir mi contraseña nueva", html)
        self.assertIn("El enlace vale <strong>1 hora</strong>", html)
        self.assertIn("una vez", html)
        for colour in ("#920000", "#f3f2ef"):
            self.assertIn(colour, html)
        self.assertNotIn("font-size:44px", html)

    def test_the_html_message_escapes_the_name(self):
        User.objects.filter(username=self.username).update(first_name="<b>Matías</b>", last_name="")
        self.ask_for_link()
        html = mail.outbox[0].alternatives[0].content
        self.assertNotIn("<b>Matías</b>", html)
        self.assertIn("&lt;b&gt;Matías&lt;/b&gt;", html)

    def test_the_link_uses_the_address_the_person_used_and_https_when_it_is_secure(self):
        with override_settings(ALLOWED_HOSTS=["sgr.example.cl"]):
            self.client.post(reverse("accounts:recover"), {"email": self.email}, HTTP_HOST="sgr.example.cl", secure=True)
        self.assertTrue(self.last_link().startswith("https://sgr.example.cl/recuperar/"))
        self.client.post(reverse("accounts:recover"), {"email": self.email})
        self.assertTrue(self.last_link().startswith("http://testserver/recuperar/"))

    def test_the_recovery_adds_no_table_to_the_data_model(self):
        models = {model.__name__ for model in apps.get_app_config("accounts").get_models()}
        self.assertEqual(models, {"UserProfile", "RoleProfile", "UserRoleDelegation"})

    def test_an_unknown_email_gets_the_same_answer_and_no_message(self):
        known = self.ask_for_link()
        stranger = Client()
        response = self.ask_for_link("nadie@sgr.example", client=stranger)
        self.assertRedirects(response, known["Location"], fetch_redirect_response=False)
        self.assertEqual(len(mail.outbox), 1)
        page = lambda client: re.sub(r'(csrf-token" content|csrfmiddlewaretoken" value)="[^"]+"', "", client.get(known["Location"]).content.decode())
        self.assertEqual(page(self.client), page(stranger))
        self.assertIn("Si ese correo está registrado, te enviamos un enlace", page(stranger))

    def test_the_answer_does_not_repeat_or_store_the_email(self):
        self.ask_for_link()
        page = self.client.get(reverse("accounts:recover_done")).content.decode()
        self.assertNotIn(self.email, page)
        self.assertNotIn("matias.cavieres@", page)
        self.assertNotIn(self.email, str(dict(self.client.session.items())))

    def test_the_email_is_matched_ignoring_case_and_spaces(self):
        self.ask_for_link("  Matias.Cavieres@SGR.example ")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.email])

    def test_inactive_accounts_get_no_link(self):
        User.objects.filter(username=self.username).update(is_active=False)
        response = self.ask_for_link()
        self.assertRedirects(response, reverse("accounts:recover_done"), fetch_redirect_response=False)
        self.assertEqual(mail.outbox, [])

    def test_accounts_without_a_usable_password_get_no_link(self):
        user = self.user()
        user.set_unusable_password()
        user.save()
        self.ask_for_link()
        self.assertEqual(mail.outbox, [])

    def test_a_badly_written_email_is_rejected_by_the_form(self):
        for text in ("sin-arroba", "dos@@sgr.example", "", "con espacio@sgr.example"):
            with self.subTest(text=text):
                response = self.client.post(reverse("accounts:recover"), {"email": text})
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["form"].errors["email"])
        self.assertEqual(mail.outbox, [])

    def test_accounts_sharing_an_email_each_get_their_own_link(self):
        User.objects.filter(username="matias.quiroz").update(email=self.email)
        self.ask_for_link()
        self.assertEqual(len(mail.outbox), 2)
        links = {self.link_in(message) for message in mail.outbox}
        self.assertEqual(len(links), 2)

    def test_every_send_is_in_the_audit_log_without_the_link(self):
        self.ask_for_link()
        entries = AuditLog.objects.filter(user=self.user(), event=recovery.SENT_EVENT)
        self.assertEqual(entries.count(), 1)
        token = self.last_link().rstrip("/").split("/")[-1]
        for entry in entries:
            self.assertIsNone(entry.previous_value)
            self.assertIsNone(entry.new_value)
            self.assertNotIn(token, f"{entry.event}{entry.affected_entity}")

    def test_requests_per_hour_are_limited_with_the_same_answer(self):
        for number in range(5):
            self.ask_for_link(seconds=number)
        self.assertEqual(len(mail.outbox), 5)
        sixth = self.ask_for_link(seconds=10)
        self.assertRedirects(sixth, reverse("accounts:recover_done"), fetch_redirect_response=False)
        self.assertEqual(len(mail.outbox), 5)
        self.ask_for_link(seconds=3601)
        self.assertEqual(len(mail.outbox), 6)

    def test_the_limit_is_per_account_not_per_email_address_typed(self):
        for number in range(5):
            self.ask_for_link(seconds=number)
        self.ask_for_link("matias.quiroz@sgr.example", seconds=10)
        self.assertEqual(mail.outbox[-1].to, ["matias.quiroz@sgr.example"])
        self.assertEqual(len(mail.outbox), 6)

    def test_a_failed_send_gives_the_same_answer_and_does_not_use_up_the_hourly_limit(self):
        with (
            mock.patch("django.core.mail.EmailMultiAlternatives.send", side_effect=SMTPException("servidor caído")),
            self.assertLogs("accounts.forms", level="ERROR"),
        ):
            response = self.ask_for_link()
        self.assertRedirects(response, reverse("accounts:recover_done"), fetch_redirect_response=False)
        self.assertNotContains(self.client.get(response["Location"]), "caído")
        self.assertFalse(AuditLog.objects.filter(event=recovery.SENT_EVENT).exists())
        self.ask_for_link()
        self.assertEqual(len(mail.outbox), 1)

    def test_the_request_form_needs_the_csrf_token(self):
        strict = Client(enforce_csrf_checks=True)
        page = strict.get(reverse("accounts:recover"))
        self.assertContains(page, "csrfmiddlewaretoken")
        self.assertEqual(strict.post(reverse("accounts:recover"), {"email": self.email}).status_code, 403)
        self.assertEqual(mail.outbox, [])

    def test_people_with_a_session_are_sent_to_their_profile(self):
        self.login_as(self.username)
        for name, args in (("accounts:recover", []), ("accounts:recover_done", []), ("accounts:recover_confirm", ["MQ", "abc-def"])):
            with self.subTest(name=name):
                self.assertRedirects(self.client.get(reverse(name, args=args)), reverse("core:profile"), fetch_redirect_response=False)
        self.client.post(reverse("accounts:recover"), {"email": self.email})
        self.assertEqual(mail.outbox, [])

    def test_the_screen_talks_about_a_link_and_not_about_a_code(self):
        page = self.client.get(reverse("accounts:recover")).content.decode()
        self.assertIn("te enviamos un enlace", page)
        self.assertIn("Enviar enlace", page)
        self.assertNotIn("código", page.lower())


class RecoveryLinkTests(RecoveryTestCase):
    def test_a_valid_link_opens_the_new_password_form_and_hides_the_token(self):
        self.ask_for_link()
        link = self.last_link()
        opened = self.open_link(link)
        self.assertEqual(opened.status_code, 302)
        self.assertTrue(opened["Location"].endswith(f"/{SET_PASSWORD}/"))
        token = link.rstrip("/").split("/")[-1]
        self.assertNotIn(token, opened["Location"])
        response = self.client.get(opened["Location"])
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "registration/recover_confirm.html")
        self.assertContains(response, "Elige tu contraseña nueva")
        self.assertNotContains(response, token)

    def test_the_screen_asks_for_confirmation_before_saving_the_new_password(self):
        self.ask_for_link()
        response = self.client.get(self.open_link()["Location"])
        self.assertContains(response, "data-confirm-submit")
        self.assertContains(response, "¿Guardar la contraseña nueva?")
        self.assertContains(response, "La contraseña anterior deja de servir.")

    def test_a_made_up_link_is_refused_with_a_notice_and_a_400(self):
        self.ask_for_link()
        uid = self.last_link().split("/")[-3]
        response = self.client.get(reverse("accounts:recover_confirm", args=[uid, "abc123-0123456789abcdef0123"]))
        self.assertEqual(response.status_code, 400)
        self.assertTemplateUsed(response, "registration/recover_confirm.html")
        self.assertContains(response, "Este enlace ya no sirve", status_code=400)
        self.assertContains(response, "Pedir un enlace nuevo", status_code=400)
        self.assertContains(response, f'href="{reverse("accounts:recover")}"', status_code=400)
        for technical in ("Traceback", "Exception", "SELECT ", "django.", "File \""):
            self.assertNotContains(response, technical, status_code=400)

    def test_a_link_with_garbage_in_it_is_refused_without_an_internal_error(self):
        for uid, token in (("!!!", "abc-def"), ("MQ", "x"), ("a" * 400, "abc-def"), ("OTk5OTk5OTk5", "abc-def"), ("%00", "abc-def")):
            with self.subTest(uid=uid[:10], token=token):
                response = self.client.get(f"/recuperar/{uid}/{token}/")
                self.assertEqual(response.status_code, 400)
                self.assertContains(response, "Este enlace ya no sirve", status_code=400)

    def test_the_token_of_one_account_does_not_work_with_another_account(self):
        self.ask_for_link()
        token = self.last_link().rstrip("/").split("/")[-1]
        other = User.objects.get(username="matias.quiroz")
        uid = urlsafe_base64_encode(str(other.pk).encode())
        response = self.client.get(reverse("accounts:recover_confirm", args=[uid, token]))
        self.assertEqual(response.status_code, 400)

    def test_an_expired_link_is_refused_to_the_second(self):
        with self.token_clock(0):
            self.ask_for_link()
            link = self.last_link()
        with self.token_clock(3600):
            self.assertEqual(self.open_link(link).status_code, 302)
        with self.token_clock(3601):
            response = self.open_link(link)
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Este enlace ya no sirve", status_code=400)

    def test_the_step_after_opening_the_link_expires_too(self):
        with self.token_clock(0):
            self.ask_for_link()
            opened = self.open_link()
        with self.token_clock(3601):
            shown = self.client.get(opened["Location"])
            sent = self.client.post(opened["Location"], {"new_password1": NEW_PASSWORD, "new_password2": NEW_PASSWORD})
        self.assertEqual((shown.status_code, sent.status_code), (400, 400))
        self.assertTrue(self.user().check_password(PASSWORD))

    def test_the_screen_without_opening_a_link_first_is_refused(self):
        self.ask_for_link()
        uid = self.last_link().split("/")[-3]
        response = self.client.get(reverse("accounts:recover_confirm", args=[uid, SET_PASSWORD]))
        self.assertEqual(response.status_code, 400)

    def test_an_account_deactivated_after_the_email_cannot_use_its_link(self):
        self.ask_for_link()
        link = self.last_link()
        User.objects.filter(username=self.username).update(is_active=False)
        self.assertEqual(self.open_link(link).status_code, 400)

    def test_a_link_stops_working_if_the_email_of_the_account_changes(self):
        self.ask_for_link()
        link = self.last_link()
        User.objects.filter(username=self.username).update(email="otro.correo@sgr.example")
        self.assertEqual(self.open_link(link).status_code, 400)

    def test_a_link_can_be_opened_from_another_browser_than_the_one_that_asked(self):
        self.ask_for_link()
        other = Client()
        opened = self.open_link(client=other)
        self.assertEqual(opened.status_code, 302)
        self.assertEqual(other.get(opened["Location"]).status_code, 200)

    def test_the_link_of_another_browser_session_does_not_open_the_screen_without_the_link(self):
        self.ask_for_link()
        opened = self.open_link()
        stranger = Client()
        self.assertEqual(stranger.get(opened["Location"]).status_code, 400)
        self.assertEqual(
            stranger.post(opened["Location"], {"new_password1": NEW_PASSWORD, "new_password2": NEW_PASSWORD}).status_code, 400
        )
        self.assertTrue(self.user().check_password(PASSWORD))


class RecoveryPasswordTests(RecoveryTestCase):
    def test_weak_passwords_are_rejected_and_the_person_can_try_again(self):
        self.ask_for_link()
        opened = self.open_link()
        for weak in ("corta1!", "sinnumeros!A", "TODOMAYUSCULA1!", "12345678", "Password1!"):
            with self.subTest(weak=weak):
                response = self.client.post(opened["Location"], {"new_password1": weak, "new_password2": weak})
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["form"].errors)
                self.assertTrue(self.user().check_password(PASSWORD))
        good = self.client.post(opened["Location"], {"new_password1": NEW_PASSWORD, "new_password2": NEW_PASSWORD})
        self.assertRedirects(good, reverse("core:login"), fetch_redirect_response=False)

    def test_two_different_passwords_are_rejected_with_a_clear_message(self):
        self.ask_for_link()
        opened = self.open_link()
        response = self.client.post(opened["Location"], {"new_password1": NEW_PASSWORD, "new_password2": NEW_PASSWORD + "x"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Las dos contraseñas nuevas no son iguales.")
        self.assertTrue(self.user().check_password(PASSWORD))

    def test_a_strong_password_is_saved_and_the_person_goes_back_to_login(self):
        self.ask_for_link()
        response = self.choose()
        self.assertRedirects(response, reverse("core:login"), fetch_redirect_response=False)
        followed = self.client.get(response["Location"])
        self.assertContains(followed, "Cambiaste tu contraseña. Ya puedes ingresar con la nueva.")
        user = self.user()
        self.assertTrue(user.check_password(NEW_PASSWORD))
        self.assertFalse(user.check_password(PASSWORD))

    def test_the_person_is_not_logged_in_by_the_change(self):
        self.ask_for_link()
        self.choose()
        self.assertEqual(self.client.get(reverse("core:dashboard")).status_code, 302)

    def test_the_old_password_stops_working_and_other_open_sessions_close(self):
        other = Client()
        other.force_login(self.user())
        self.assertEqual(other.get(reverse("core:dashboard")).status_code, 200)
        self.ask_for_link()
        self.choose()
        self.assertEqual(other.get(reverse("core:dashboard")).status_code, 302)
        fresh = Client()
        self.assertFalse(fresh.login(username=self.username, password=PASSWORD))
        self.assertTrue(fresh.login(username=self.username, password=NEW_PASSWORD))

    def test_the_used_link_cannot_change_the_password_again(self):
        self.ask_for_link()
        link = self.last_link()
        self.choose()
        again = Client()
        refused = self.open_link(link, client=again)
        self.assertEqual(refused.status_code, 400)
        self.assertContains(refused, "Este enlace ya no sirve", status_code=400)
        stale = self.client.post(
            reverse("accounts:recover_confirm", args=[link.split("/")[-3], SET_PASSWORD]),
            {"new_password1": "OtraClave#2027", "new_password2": "OtraClave#2027"},
        )
        self.assertEqual(stale.status_code, 400)
        self.assertTrue(self.user().check_password(NEW_PASSWORD))

    def test_every_other_link_still_pending_dies_with_the_change(self):
        self.ask_for_link()
        self.ask_for_link()
        first, second = (self.link_in(message) for message in mail.outbox)
        self.choose(link=first)
        self.assertEqual(self.open_link(second, client=Client()).status_code, 400)

    def test_the_whole_flow_is_audited_without_secrets(self):
        self.ask_for_link()
        link = self.last_link()
        self.choose()
        events = list(AuditLog.objects.filter(user=self.user()).values_list("event", flat=True))
        self.assertIn(recovery.SENT_EVENT, events)
        self.assertIn(recovery.RESET_EVENT, events)
        token = link.rstrip("/").split("/")[-1]
        for entry in AuditLog.objects.filter(user=self.user(), event__in=(recovery.SENT_EVENT, recovery.RESET_EVENT)):
            self.assertIsNone(entry.previous_value)
            self.assertIsNone(entry.new_value)
            self.assertNotIn(token, entry.event)
            self.assertNotIn(NEW_PASSWORD, entry.event)

    def test_the_password_form_needs_the_csrf_token(self):
        self.ask_for_link()
        strict = Client(enforce_csrf_checks=True)
        opened = self.open_link(client=strict)
        page = strict.get(opened["Location"])
        self.assertContains(page, "csrfmiddlewaretoken")
        response = strict.post(opened["Location"], {"new_password1": NEW_PASSWORD, "new_password2": NEW_PASSWORD})
        self.assertEqual(response.status_code, 403)
        self.assertTrue(self.user().check_password(PASSWORD))

    def test_the_typed_passwords_are_hidden_from_error_reports(self):
        self.ask_for_link()
        opened = self.open_link()
        response = self.client.post(opened["Location"], {"new_password1": "corta", "new_password2": "corta"})
        self.assertEqual(response.wsgi_request.sensitive_post_parameters, "__ALL__")


class RecoveryRoutesTests(RecoveryTestCase):
    def test_the_screens_of_the_six_digit_code_no_longer_exist(self):
        for path in ("/recuperar/codigo/", "/recuperar/reenviar/", "/recuperar/nueva/"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 404)

    def test_the_stock_django_reset_screens_lead_to_the_portal_ones(self):
        self.assertRedirects(self.client.get("/accounts/password_reset/done/"), reverse("accounts:recover_done"), fetch_redirect_response=False)
        self.assertRedirects(self.client.get("/accounts/reset/done/"), reverse("core:login"), fetch_redirect_response=False)
        self.ask_for_link()
        link = self.last_link()
        uid, token = link.rstrip("/").split("/")[-2:]
        redirected = self.client.get(f"/accounts/reset/{uid}/{token}/")
        self.assertRedirects(redirected, self.path_of(link), fetch_redirect_response=False)

    def test_the_login_page_still_links_to_the_recovery(self):
        self.assertContains(self.client.get(reverse("core:login")), f'href="{reverse("accounts:recover")}"')


class RecoveryHelperTests(SimpleTestCase):
    def test_the_duration_is_said_in_the_biggest_whole_unit(self):
        self.assertEqual(recovery.describe_duration(3600), "1 hora")
        self.assertEqual(recovery.describe_duration(7200), "2 horas")
        self.assertEqual(recovery.describe_duration(1800), "30 minutos")
        self.assertEqual(recovery.describe_duration(60), "1 minuto")
        self.assertEqual(recovery.describe_duration(45), "45 segundos")

    def test_the_settings_say_one_hour_and_five_links_per_hour(self):
        self.assertEqual(recovery.link_duration(), "1 hora")
        self.assertEqual(settings.RECOVERY_MAX_REQUESTS, 5)

    def test_the_old_settings_of_the_code_are_gone(self):
        for name in ("RECOVERY_CODE_SECONDS", "RECOVERY_MAX_ATTEMPTS", "RECOVERY_RESEND_SECONDS", "RECOVERY_PASSWORD_SECONDS"):
            self.assertFalse(hasattr(settings, name), name)


class RecoveryBlankEmailTests(TestCase):
    def test_a_blank_email_matches_nobody_even_if_some_accounts_have_no_email(self):
        User.objects.create_user("sin.correo", email="", password="x")
        form = RecoveryRequestForm({"email": ""})
        self.assertFalse(form.is_valid())
        self.assertEqual(list(RecoveryRequestForm().get_users("")), [])
        self.assertEqual(list(RecoveryRequestForm().get_users("   ")), [])
        self.assertEqual(mail.outbox, [])
