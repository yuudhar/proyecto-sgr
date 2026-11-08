import io
from datetime import timedelta
from pathlib import Path

from asgiref.sync import async_to_sync
from django.conf import settings
from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase
from django.urls import reverse
from PIL import Image

from accounts.models import UserProfile
from core import uploads
from core.clients import client_beneficiary, is_client, own_activities
from core.models import AuditLog
from core.test_realtime import open_socket
from core.test_users import NEW_PASSWORD, UserTestCase
from core.testing import PASSWORD, PortalTestCase
from operations.models import Activity
from organization.models import Beneficiary

MARIA_RUT = "11111111-1"
OTHER_RUT = "55555555-5"
STATIC_DIR = Path(settings.BASE_DIR) / "core" / "static" / "core"


def picture(size, image_format="PNG", color=(30, 90, 160)):
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format=image_format)
    return buffer.getvalue()


def activity_of(rut):
    return Activity.objects.filter(beneficiary__rut=rut, deleted_at__isnull=True).order_by("date")


class ClientCase(PortalTestCase):
    """Cliente 1 es María Pérez y Cliente 2 es Carla Muñoz: los dos de la Delegación Norte, con atenciones distintas."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        from django.utils import timezone

        officer = User.objects.get(username="matias.cavieres").profile.officer
        base = activity_of(MARIA_RUT).first()
        Activity.objects.create(  # una segunda atención de María, cerrada, para que su listado tenga más de una fila
            delegation=cls.north,
            author_officer=officer,
            contact_name="María Pérez",
            phone="+56911111111",
            beneficiary=base.beneficiary,
            status=Activity.Status.CLOSED,
            request_description="Consulta por el estado de su solicitud de orientación eléctrica.",
            action_taken="Se le informó el avance.",
            item=base.item,
            service=base.service,
            date=timezone.localdate() - timedelta(days=2),
        )

    def setUp(self):
        self.maria = User.objects.get(username="cliente1")
        self.other = User.objects.get(username="cliente2")
        self.login_as("cliente1")


class ClientAccountTests(ClientCase):
    def test_the_client_role_exists_and_has_no_module_permissions(self):
        group = Group.objects.get(name="Cliente")
        self.assertEqual(group.permissions.count(), 0)

    def test_each_demo_client_is_linked_to_one_beneficiary(self):
        self.assertEqual(self.maria.profile.beneficiary.rut, MARIA_RUT)
        self.assertEqual(self.other.profile.beneficiary.rut, OTHER_RUT)
        self.assertIsNone(self.maria.profile.officer)

    def test_is_client_looks_at_the_role_and_never_at_a_superuser(self):
        self.assertTrue(is_client(self.maria))
        self.assertFalse(is_client(User.objects.get(username="matias.cavieres")))
        admin = User.objects.get(username="admin")
        admin.groups.add(Group.objects.get(name="Cliente"))
        admin = User.objects.get(pk=admin.pk)
        self.assertFalse(is_client(admin))

    def test_an_account_cannot_have_an_officer_and_a_beneficiary(self):
        from django.core.exceptions import ValidationError

        profile = self.maria.profile
        profile.officer = User.objects.get(username="matias.cavieres").profile.officer
        with self.assertRaises(ValidationError):
            profile.full_clean()

    def test_a_beneficiary_has_at_most_one_account(self):
        from django.db import IntegrityError, transaction

        other = User.objects.create_user("cliente3", password=PASSWORD)
        with self.assertRaises(IntegrityError), transaction.atomic():
            UserProfile.objects.create(user=other, beneficiary=self.maria.profile.beneficiary)

    def test_own_activities_are_the_ones_of_the_linked_beneficiary_only(self):
        mine = set(own_activities(self.maria).values_list("pk", flat=True))
        self.assertEqual(mine, set(activity_of(MARIA_RUT).values_list("pk", flat=True)))
        self.assertGreaterEqual(len(mine), 2)
        self.assertFalse(mine & set(activity_of(OTHER_RUT).values_list("pk", flat=True)))

    def test_without_a_linked_beneficiary_there_is_nothing_to_see(self):
        UserProfile.objects.filter(user=self.maria).update(beneficiary=None)
        user = User.objects.get(pk=self.maria.pk)
        self.assertIsNone(client_beneficiary(user))
        self.assertEqual(own_activities(user).count(), 0)

    def test_an_archived_beneficiary_shows_nothing(self):
        from django.utils import timezone

        Beneficiary.objects.filter(rut=MARIA_RUT).update(deleted_at=timezone.now())
        self.assertEqual(own_activities(User.objects.get(pk=self.maria.pk)).count(), 0)


class ClientLoginTests(PortalTestCase):
    def test_after_signing_in_the_client_lands_on_the_portal(self):
        response = self.client.post(reverse("core:login"), {"username": "cliente1", "password": PASSWORD})
        self.assertRedirects(response, reverse("core:portal_home"))

    def test_a_signed_in_client_who_opens_the_login_goes_to_the_portal(self):
        self.login_as("cliente1")
        self.assertRedirects(self.client.get(reverse("core:login")), reverse("core:portal_home"), fetch_redirect_response=False)

    def test_the_client_who_opens_the_dashboard_is_taken_to_the_portal(self):
        self.login_as("cliente1")
        response = self.client.get(reverse("core:dashboard"))
        self.assertRedirects(response, reverse("core:portal_home"))

    def test_the_staff_still_land_on_the_dashboard(self):
        response = self.client.post(reverse("core:login"), {"username": "matias.cavieres", "password": PASSWORD})
        self.assertRedirects(response, reverse("core:dashboard"))


class ClientPortalScreensTests(ClientCase):
    def test_the_portal_home_shows_the_own_profile_and_a_summary(self):
        page = self.client.get(reverse("core:portal_home"))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "María Pérez")
        self.assertContains(page, MARIA_RUT)
        self.assertContains(page, "Atenciones en total")
        self.assertEqual(page.context["total"], activity_of(MARIA_RUT).count())

    def test_the_portal_home_never_shows_data_of_the_other_client(self):
        page = self.client.get(reverse("core:portal_home"))
        for text in ("Carla Muñoz", OTHER_RUT, "+56955555555", "Los Olivos 4450"):
            self.assertNotContains(page, text)

    def test_the_list_shows_only_the_own_attentions(self):
        page = self.client.get(reverse("core:portal_activities"))
        shown = {row["pk"] for row in page.context["rows"]}
        self.assertEqual(shown, set(activity_of(MARIA_RUT).values_list("pk", flat=True)))
        for other in activity_of(OTHER_RUT):
            self.assertNotContains(page, reverse("core:portal_activity", args=[other.pk]))
            self.assertNotContains(page, other.request_description)

    def test_the_other_client_sees_a_different_list(self):
        self.login_as("cliente2")
        page = self.client.get(reverse("core:portal_activities"))
        shown = {row["pk"] for row in page.context["rows"]}
        self.assertEqual(shown, set(activity_of(OTHER_RUT).values_list("pk", flat=True)))
        self.assertNotContains(page, "María Pérez")

    def test_the_list_filters_by_state_and_by_text_inside_the_own_attentions(self):
        closed = self.client.get(reverse("core:portal_activities"), {"estado": "closed"})
        self.assertTrue(closed.context["rows"])
        self.assertTrue(all(row["status"] == "closed" for row in closed.context["rows"]))
        found = self.client.get(reverse("core:portal_activities"), {"q": "eléctrico"})
        self.assertTrue(found.context["rows"])
        none = self.client.get(reverse("core:portal_activities"), {"q": "certificado de residencia"})
        self.assertEqual(none.context["rows"], [])  # eso lo pidió el otro cliente

    def test_an_unknown_state_is_ignored(self):
        page = self.client.get(reverse("core:portal_activities"), {"estado": "no-existe"})
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.context["status"], "")

    def test_the_detail_of_an_own_attention_shows_its_followups(self):
        own = activity_of(MARIA_RUT).get(status=Activity.Status.IN_PROGRESS)
        page = self.client.get(reverse("core:portal_activity", args=[own.pk]))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, own.request_description)
        self.assertContains(page, "Se agenda visita domiciliaria")
        self.assertContains(page, "Gestiones")

    def test_the_detail_does_not_show_internal_data(self):
        own = activity_of(MARIA_RUT).first()
        page = self.client.get(reverse("core:portal_activity", args=[own.pk]))
        for text in ("puntúa", "Evidencia", "compromiso", "tubo"):
            self.assertNotContains(page, text)

    def test_the_detail_of_an_attention_of_the_other_client_is_a_404_without_content(self):
        other = activity_of(OTHER_RUT).first()
        page = self.client.get(reverse("core:portal_activity", args=[other.pk]))
        self.assertEqual(page.status_code, 404)
        for text in ("Carla Muñoz", other.request_description, OTHER_RUT):
            self.assertNotContains(page, text, status_code=404)

    def test_the_detail_of_an_attention_that_does_not_exist_answers_the_same(self):
        self.assertEqual(self.client.get(reverse("core:portal_activity", args=[999999])).status_code, 404)

    def test_an_archived_attention_cannot_be_opened(self):
        from django.utils import timezone

        own = activity_of(MARIA_RUT).first()
        Activity.objects.filter(pk=own.pk).update(deleted_at=timezone.now())
        self.assertEqual(self.client.get(reverse("core:portal_activity", args=[own.pk])).status_code, 404)

    def test_a_client_without_a_linked_beneficiary_sees_an_empty_portal(self):
        UserProfile.objects.filter(user=self.maria).update(beneficiary=None)
        home = self.client.get(reverse("core:portal_home"))
        self.assertContains(home, "todavía no está vinculada")
        self.assertEqual(self.client.get(reverse("core:portal_activities")).context["rows"], [])
        own = activity_of(MARIA_RUT).first()
        self.assertEqual(self.client.get(reverse("core:portal_activity", args=[own.pk])).status_code, 404)

    def test_the_portal_screens_need_a_session(self):
        self.client.logout()
        for name, args in (("portal_home", []), ("portal_activities", []), ("portal_activity", [1])):
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(f"core:{name}", args=args)).status_code, 302)

    def test_the_portal_is_only_for_the_client_role(self):
        for username in ("matias.cavieres", "coordinacion1", "admin"):
            with self.subTest(username=username):
                self.login_as(username)
                for name, args in (("portal_home", []), ("portal_activities", []), ("portal_activity", [1])):
                    self.assertEqual(self.client.get(reverse(f"core:{name}", args=args)).status_code, 403)


class ClientIsKeptInsideTheirPortalTests(ClientCase):
    OUTSIDE = (
        "core:atencion",
        "core:actividades_list",
        "core:beneficiarios_list",
        "core:usuarios_list",
        "core:evidencias_list",
        "core:agenda_list",
        "core:gestiones_list",
        "core:auditoria_list",
        "core:administration",
        "core:delegation_board",
        "core:reports",
        "core:position_overview",
        "core:validate_list",
        "core:commitment_summary",
    )

    def test_every_other_screen_is_refused(self):
        for name in self.OUTSIDE:
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 403)

    def test_the_detail_and_edit_pages_of_the_registers_are_refused(self):
        other = activity_of(OTHER_RUT).first()
        own = activity_of(MARIA_RUT).first()
        for name, args in (
            ("core:actividades_detail", [other.pk]),
            ("core:actividades_detail", [own.pk]),
            ("core:actividades_update", [own.pk]),
            ("core:beneficiarios_detail", [self.other.profile.beneficiary.pk]),
            ("core:beneficiarios_detail", [self.maria.profile.beneficiary.pk]),
            ("core:usuarios_detail", [self.other.pk]),
        ):
            with self.subTest(name=name, args=args):
                self.assertEqual(self.client.get(reverse(name, args=args)).status_code, 403)

    def test_the_exports_are_refused_and_nothing_is_sent(self):
        for name in ("core:actividades_list", "core:beneficiarios_list", "core:atencion"):
            with self.subTest(name=name):
                response = self.client.get(reverse(name), {"formato": "xlsx"})
                self.assertEqual(response.status_code, 403)
                self.assertNotIn("spreadsheet", response.headers.get("Content-Type", ""))
        self.assertFalse(AuditLog.objects.filter(event="Listado exportado a Excel").exists())

    def test_the_posts_to_the_registers_are_refused(self):
        own = activity_of(MARIA_RUT).first()
        for name, args in (("core:actividades_update", [own.pk]), ("core:actividades_create", []), ("core:set_context", [])):
            with self.subTest(name=name):
                self.assertEqual(self.client.post(reverse(name, args=args), {"delegacion": "todas"}).status_code, 403)
        own.refresh_from_db()
        self.assertEqual(own.status, activity_of(MARIA_RUT).first().status)

    def test_the_django_admin_is_closed(self):
        self.assertEqual(self.client.get("/admin/").status_code, 403)
        self.assertEqual(self.client.get("/admin/auth/user/").status_code, 403)

    def test_a_refusal_shows_no_content_and_is_logged(self):
        response = self.client.get(reverse("core:beneficiarios_list"))
        self.assertEqual(response.status_code, 403)
        self.assertNotContains(response, "Carla Muñoz", status_code=403)
        log = AuditLog.objects.get(event="Acceso de cliente rechazado", user=self.maria)
        self.assertIn(reverse("core:beneficiarios_list"), log.new_value)

    def test_the_dashboard_post_is_not_redirected_but_refused(self):
        self.assertEqual(self.client.post(reverse("core:dashboard")).status_code, 403)

    def test_the_allowed_screens_are_not_refused(self):
        for name in ("core:portal_home", "core:portal_activities", "core:profile"):
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)

    def test_the_middleware_allows_only_the_portal_names(self):
        from core.clients import ALLOWED_URL_NAMES

        self.assertEqual(
            set(ALLOWED_URL_NAMES),
            {"login", "logout", "profile", "profile_photo", "portal_home", "portal_activities", "portal_activity"},
        )

    def test_the_staff_are_not_affected_by_the_middleware(self):
        self.login_as("matias.cavieres")
        self.assertEqual(self.client.get(reverse("core:atencion")).status_code, 200)
        self.assertEqual(self.client.get(reverse("core:dashboard")).status_code, 200)


class ClientInterfaceTests(ClientCase):
    def test_the_menu_has_only_the_portal_entries(self):
        page = self.client.get(reverse("core:portal_home"))
        labels = [item.label for item in page.context["menu_top"]]
        self.assertEqual(labels, ["Mi portal", "Mis atenciones", "Mi perfil"])
        self.assertEqual(page.context["menu_groups"], [])
        for text in ("Administración", "Dashboard", "Operación", "Resultados"):
            self.assertNotContains(page, f">{text}<")

    def test_the_delegation_strip_and_card_are_hidden(self):
        page = self.client.get(reverse("core:portal_home"))
        self.assertNotContains(page, "topbar-scope")
        self.assertNotContains(page, "scope-card")
        self.assertNotContains(page, 'data-context-form')

    def test_the_active_entry_follows_the_page(self):
        page = self.client.get(reverse("core:portal_activities"))
        active = [item.label for item in page.context["menu_top"] if item.active]
        self.assertEqual(active, ["Mis atenciones"])

    def test_the_role_chip_says_cliente(self):
        self.assertContains(self.client.get(reverse("core:portal_home")), "Cliente")

    def test_the_brand_takes_the_client_home(self):
        page = self.client.get(reverse("core:portal_home"))
        self.assertContains(page, f'class="brand sidebar-brand" href="{reverse("core:portal_home")}"')

    def test_the_error_page_of_a_refusal_also_renders_for_the_client(self):
        response = self.client.get(reverse("core:usuarios_list"))
        self.assertContains(response, "No tienes permiso", status_code=403)

    def test_the_pages_of_the_portal_are_not_cached(self):
        self.assertIn("no-store", self.client.get(reverse("core:portal_home"))["Cache-Control"])


class ClientProfileTests(ClientCase):
    def data(self, **changes):
        data = {"accion": "datos", "email": "maria.nueva@correo.cl", "phone": "+56 9 1111 2222", "address": "Los Aromos 999"}
        data.update(changes)
        return data

    def test_the_profile_has_the_client_panel_and_no_delegation_panel(self):
        page = self.client.get(reverse("core:profile"))
        self.assertContains(page, "Mis datos")
        self.assertContains(page, 'value="datos"')
        self.assertNotContains(page, "Delegación y funcionario")
        self.assertNotContains(page, "Esta cuenta no tiene un funcionario asociado")

    def test_the_client_edits_the_own_contact_data(self):
        response = self.client.post(reverse("core:profile"), self.data())
        self.assertRedirects(response, reverse("core:profile"))
        beneficiary = Beneficiary.objects.get(rut=MARIA_RUT)
        self.assertEqual(beneficiary.address, "Los Aromos 999")
        self.assertEqual(beneficiary.phone, "+56 9 1111 2222")
        self.assertEqual(User.objects.get(pk=self.maria.pk).email, "maria.nueva@correo.cl")
        self.assertTrue(AuditLog.objects.filter(event="Datos de cliente actualizados", user=self.maria).exists())

    def test_the_edit_never_touches_the_other_client(self):
        before = Beneficiary.objects.get(rut=OTHER_RUT)
        other = self.data(beneficiary=before.pk, id=before.pk, user=self.other.pk, rut=OTHER_RUT, name="Cambiado")
        self.client.post(reverse("core:profile"), other)
        after = Beneficiary.objects.get(rut=OTHER_RUT)
        self.assertEqual((after.name, after.phone, after.address), (before.name, before.phone, before.address))
        self.assertEqual(User.objects.get(pk=self.other.pk).email, "cliente2@sgr.example")

    def test_the_client_cannot_change_the_name_the_rut_the_role_or_the_owner(self):
        beneficiary = Beneficiary.objects.get(rut=MARIA_RUT)
        tries = self.data(name="Otra Persona", rut="99999999-9", groups=[Group.objects.get(name="Coordinación").pk],
                          is_superuser="on", is_staff="on", officer=1, beneficiary=Beneficiary.objects.get(rut=OTHER_RUT).pk)
        self.client.post(reverse("core:profile"), tries)
        user = User.objects.get(pk=self.maria.pk)
        after = Beneficiary.objects.get(rut=MARIA_RUT)
        self.assertEqual((after.name, after.rut), (beneficiary.name, beneficiary.rut))
        self.assertEqual(list(user.groups.values_list("name", flat=True)), ["Cliente"])
        self.assertFalse(user.is_superuser or user.is_staff)
        self.assertEqual(user.profile.beneficiary_id, beneficiary.pk)
        self.assertIsNone(user.profile.officer)

    def test_a_bad_phone_is_rejected_and_nothing_is_saved(self):
        before = Beneficiary.objects.get(rut=MARIA_RUT).phone
        response = self.client.post(reverse("core:profile"), self.data(phone="abc"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("phone", response.context["client_form"].errors)
        self.assertEqual(Beneficiary.objects.get(rut=MARIA_RUT).phone, before)

    def test_a_bad_email_is_rejected(self):
        response = self.client.post(reverse("core:profile"), self.data(email="no-es-correo"))
        self.assertIn("email", response.context["client_form"].errors)

    def test_the_staff_cannot_use_the_client_form(self):
        self.login_as("matias.cavieres")
        self.assertEqual(self.client.post(reverse("core:profile"), self.data()).status_code, 403)
        self.assertIsNone(self.client.get(reverse("core:profile")).context["client_form"])

    def test_the_client_changes_the_own_password(self):
        response = self.client.post(
            reverse("core:profile"),
            {"old_password": PASSWORD, "new_password1": "Nueva#Clave2026", "new_password2": "Nueva#Clave2026"},
        )
        self.assertRedirects(response, reverse("core:profile"))

    def test_the_client_photo_is_served_only_to_the_client_and_never_the_others(self):
        self.client.post(reverse("core:profile"), {"accion": "foto", "photo": SimpleUploadedFile("yo.png", picture((80, 80)), content_type="image/png")})
        mine = reverse("core:profile_photo", args=[self.maria.pk])
        theirs = reverse("core:profile_photo", args=[self.other.pk])
        self.assertEqual(self.client.get(mine).status_code, 200)
        self.assertEqual(self.client.get(theirs).status_code, 404)

    def test_a_client_cannot_open_the_photo_of_an_officer(self):
        self.login_as("matias.cavieres")
        self.client.post(reverse("core:profile"), {"accion": "foto", "photo": SimpleUploadedFile("yo.png", picture((80, 80)), content_type="image/png")})
        officer = User.objects.get(username="matias.cavieres")
        self.login_as("cliente1")
        self.assertEqual(self.client.get(reverse("core:profile_photo", args=[officer.pk])).status_code, 404)


class ClientSocketTests(PortalTestCase):
    def test_the_client_cannot_listen_to_the_live_events(self):
        client = User.objects.get(username="cliente1")
        _, connected = async_to_sync(open_socket)(client, "/ws/live/")
        self.assertFalse(connected)

    def test_the_client_cannot_listen_to_the_changes_of_a_register(self):
        client = User.objects.get(username="cliente1")
        for slug in ("actividades", "beneficiarios", "gestiones"):
            with self.subTest(slug=slug):
                _, connected = async_to_sync(open_socket)(client, f"/ws/crud/{slug}/")
                self.assertFalse(connected)

    def test_the_staff_still_connect(self):
        officer = User.objects.get(username="matias.cavieres")

        async def scenario():
            communicator, connected = await open_socket(officer, "/ws/live/")
            await communicator.disconnect()
            return connected

        self.assertTrue(async_to_sync(scenario)())


class ClientAccountCreationTests(UserTestCase):
    def setUp(self):
        self.login_as("admin")
        self.free = Beneficiary.objects.get(rut="33333333-3")

    def client_data(self, **changes):
        base = {
            "username": "ana.cliente",
            "first_name": "Ana",
            "last_name": "Rojas",
            "email": "ana.rojas@dominio.cl",
            "groups": [self.group("Cliente")],
            "officer": "",
            "beneficiary": self.free.pk,
        }
        base.update(changes)
        return self.user_data(**base)

    def test_the_superuser_creates_a_client_linked_to_a_beneficiary(self):
        response = self.client.post(reverse("core:usuarios_create"), self.client_data())
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(username="ana.cliente")
        self.assertEqual(user.profile.beneficiary_id, self.free.pk)
        self.assertIsNone(user.profile.officer)
        self.assertTrue(is_client(user))

    def test_a_client_needs_a_beneficiary(self):
        response = self.client.post(reverse("core:usuarios_create"), self.client_data(beneficiary=""))
        self.assertEqual(response.status_code, 200)
        self.assertIn("beneficiary", response.context["form"].errors)
        self.assertFalse(User.objects.filter(username="ana.cliente").exists())

    def test_a_client_cannot_have_an_officer(self):
        response = self.client.post(reverse("core:usuarios_create"), self.client_data(officer=self.officer("F-1004").pk))
        self.assertIn("officer", response.context["form"].errors)

    def test_the_client_role_is_not_mixed_with_another_role(self):
        response = self.client.post(
            reverse("core:usuarios_create"), self.client_data(groups=[self.group("Cliente"), self.group("Consulta")])
        )
        self.assertIn("groups", response.context["form"].errors)

    def test_a_beneficiary_goes_only_with_the_client_role(self):
        response = self.client.post(
            reverse("core:usuarios_create"),
            self.user_data(beneficiary=self.free.pk),
        )
        self.assertIn("beneficiary", response.context["form"].errors)

    def test_a_beneficiary_with_an_account_is_not_offered_again(self):
        form = self.client.get(reverse("core:usuarios_create")).context["form"]
        offered = set(form.fields["beneficiary"].queryset.values_list("rut", flat=True))
        self.assertNotIn(MARIA_RUT, offered)
        self.assertNotIn(OTHER_RUT, offered)
        self.assertIn("33333333-3", offered)

    def test_a_beneficiary_with_an_account_is_rejected(self):
        taken = Beneficiary.objects.get(rut=MARIA_RUT)
        response = self.client.post(reverse("core:usuarios_create"), self.client_data(beneficiary=taken.pk))
        self.assertIn("beneficiary", response.context["form"].errors)

    def test_a_client_account_cannot_be_super_user_or_staff(self):
        response = self.client.post(reverse("core:usuarios_create"), self.client_data(is_superuser="on", is_staff="on"))
        errors = response.context["form"].errors
        self.assertIn("is_superuser", errors)
        self.assertIn("is_staff", errors)

    def test_the_detail_shows_the_beneficiary(self):
        self.client.post(reverse("core:usuarios_create"), self.client_data())
        user = User.objects.get(username="ana.cliente")
        self.assertContains(self.client.get(reverse("core:usuarios_detail", args=[user.pk])), "Ana Rojas")

    def test_the_new_client_can_sign_in_and_sees_the_portal(self):
        self.client.post(reverse("core:usuarios_create"), self.client_data())
        self.client.logout()
        response = self.client.post(reverse("core:login"), {"username": "ana.cliente", "password": NEW_PASSWORD})
        self.assertRedirects(response, reverse("core:portal_home"))


class ClientRoleCatalogTests(PortalTestCase):
    def test_the_role_is_described_in_the_roles_catalog(self):
        from core.roles import CLIENT_ROLE, ROLES, SYSTEM_GROUPS

        self.assertIn(CLIENT_ROLE, ROLES)
        self.assertIn(CLIENT_ROLE, SYSTEM_GROUPS)


class PhotoSquareTests(PortalTestCase):
    def upload(self, content, name="foto.png", kind="image/png", username="matias.cavieres"):
        self.login_as(username)
        return self.client.post(
            reverse("core:profile"), {"accion": "foto", "photo": SimpleUploadedFile(name, content, content_type=kind)}
        )

    def stored(self, username="matias.cavieres"):
        account = User.objects.get(username=username).profile
        with account.photo.open("rb") as handle:
            return Image.open(io.BytesIO(handle.read())), account.photo.name

    def test_a_wide_photo_is_saved_square_and_centered(self):
        wide = Image.new("RGB", (300, 100), (255, 0, 0))
        wide.paste((0, 0, 255), (100, 0, 200, 100))  # el cuadrado central es azul
        buffer = io.BytesIO()
        wide.save(buffer, format="PNG")
        self.upload(buffer.getvalue())
        image, _ = self.stored()
        self.assertEqual(image.size, (100, 100))
        self.assertEqual(image.convert("RGB").getpixel((50, 50)), (0, 0, 255))

    def test_a_tall_jpg_is_saved_square_and_stays_a_jpg(self):
        self.upload(picture((100, 260), "JPEG"), "alta.jpg", "image/jpeg")
        image, name = self.stored()
        self.assertEqual(image.size, (100, 100))
        self.assertEqual(image.format, "JPEG")
        self.assertTrue(name.endswith(".jpg"))

    def test_a_big_photo_is_reduced_to_the_maximum_side(self):
        self.upload(picture((1600, 1400)))
        image, _ = self.stored()
        self.assertEqual(image.size, (settings.PHOTO_SIDE_PX, settings.PHOTO_SIDE_PX))

    def test_an_already_cropped_square_is_not_changed_in_size(self):
        self.upload(picture((200, 200)))
        image, _ = self.stored()
        self.assertEqual(image.size, (200, 200))

    def test_a_png_stays_a_png(self):
        self.upload(picture((90, 90)))
        image, name = self.stored()
        self.assertEqual(image.format, "PNG")
        self.assertTrue(name.endswith(".png"))

    def test_a_rejected_upload_keeps_the_previous_photo(self):
        self.upload(picture((90, 90)))
        _, first = self.stored()
        response = self.upload(b"no soy una imagen", "falsa.png")
        self.assertEqual(response.status_code, 200)
        _, kept = self.stored()
        self.assertEqual(kept, first)

    def test_the_photo_is_kept_after_reloading_the_profile(self):
        self.upload(picture((120, 120)))
        _, name = self.stored()
        page = self.client.get(reverse("core:profile"))
        user = User.objects.get(username="matias.cavieres")
        self.assertContains(page, reverse("core:profile_photo", args=[user.pk]))
        self.assertEqual(self.stored()[1], name)

    def test_the_photo_is_always_tied_to_the_signed_in_user(self):
        other = User.objects.get(username="matias.quiroz")
        self.login_as("matias.cavieres")
        self.client.post(
            reverse("core:profile"),
            {
                "accion": "foto",
                "user_id": other.pk,
                "user": other.pk,
                "id": other.pk,
                "photo": SimpleUploadedFile("yo.png", picture((90, 90)), content_type="image/png"),
            },
        )
        self.assertTrue(User.objects.get(username="matias.cavieres").profile.photo)
        self.assertFalse(User.objects.get(pk=other.pk).profile.photo)

    def test_the_square_helper_does_not_alter_the_original_name(self):
        uploaded = SimpleUploadedFile("mi foto.PNG", picture((50, 80)), content_type="image/png")
        result = uploads.square_photo(uploaded, 512)
        self.assertEqual(result.name, "mi foto.PNG")
        self.assertEqual(Image.open(result).size, (50, 50))

    def test_the_size_limit_still_applies(self):
        import os

        noise = Image.frombytes("RGB", (1100, 1100), os.urandom(1100 * 1100 * 3))
        buffer = io.BytesIO()
        noise.save(buffer, format="PNG")
        response = self.upload(buffer.getvalue())
        self.assertIn("máximo es 2 MB", " ".join(response.context["photo_form"].errors["photo"]))


class PhotoCropScreenTests(PortalTestCase):
    def page(self):
        self.login_as("matias.cavieres")
        return self.client.get(reverse("core:profile"))

    def test_the_profile_form_is_ready_for_the_crop(self):
        page = self.page()
        for marker in ("data-photo-crop", "data-crop-panel", "data-crop-image", "data-crop-preview", "data-crop-save", "data-crop-cancel"):
            self.assertContains(page, marker)

    def test_the_crop_panel_starts_hidden_and_the_normal_upload_stays_available(self):
        page = self.page()
        self.assertContains(page, "data-crop-panel hidden")
        self.assertContains(page, "Subir foto")

    def test_the_page_loads_the_crop_script(self):
        self.assertContains(self.page(), "core/js/photo-crop.js")

    def test_the_format_and_size_controls_are_kept_in_the_form(self):
        page = self.page()
        self.assertContains(page, 'accept=".png,.jpg,.jpeg"')
        self.assertContains(page, f'data-max-mb="{settings.PHOTO_MAX_MB}"')

    def test_the_croppr_files_are_only_linked_when_they_are_in_the_project(self):
        from core.templatetags.core_ui import vendor_url

        self.assertEqual(vendor_url("core/vendor/croppr/no-esta.js"), "")
        self.assertIn("sgr-mark.svg", vendor_url("core/img/sgr-mark.svg"))

    def test_the_page_links_croppr_when_the_files_exist(self):
        from unittest import mock

        with mock.patch("core.templatetags.core_ui.finders.find", return_value="/ruta"):
            page = self.page()
        self.assertContains(page, "vendor/croppr/croppr.min.js")
        self.assertContains(page, "vendor/croppr/croppr.min.css")

    def test_the_page_works_without_the_croppr_files(self):
        from unittest import mock

        with mock.patch("core.templatetags.core_ui.finders.find", return_value=None):
            page = self.page()
        self.assertEqual(page.status_code, 200)
        self.assertNotContains(page, "croppr.min.js")


class PhotoCropScriptTests(SimpleTestCase):
    """Revisa que el script use las piezas de Croppr y de recorte real; el comportamiento se prueba en el navegador."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.script = (STATIC_DIR / "js" / "photo-crop.js").read_text(encoding="utf-8")
        cls.validation = (STATIC_DIR / "js" / "validation.js").read_text(encoding="utf-8")

    def test_it_creates_a_square_croppr_over_the_chosen_image(self):
        self.assertIn("new Croppr(", self.script)
        self.assertIn("aspectRatio: 1", self.script)
        self.assertIn('returnMode: "real"', self.script)

    def test_it_crops_the_real_pixels_and_not_with_css(self):
        for piece in ("getValue()", "drawImage(source, crop.x, crop.y, crop.width, crop.height", "toBlob"):
            self.assertIn(piece, self.script)

    def test_the_cropped_file_replaces_the_one_in_the_field(self):
        self.assertIn("new DataTransfer()", self.script)
        self.assertIn("input.files = transfer.files", self.script)
        self.assertIn("form.requestSubmit()", self.script)

    def test_it_shows_a_preview_and_lets_the_person_cancel(self):
        self.assertIn("onCropMove: drawPreview", self.script)
        self.assertIn("onCropEnd: drawPreview", self.script)
        self.assertIn("cropper.destroy()", self.script)
        self.assertIn('input.value = ""', self.script)

    def test_without_the_library_the_form_is_left_as_a_normal_upload(self):
        self.assertIn('typeof Croppr !== "function") return;', self.script)

    def test_the_original_is_not_checked_before_the_crop(self):
        self.assertIn("data-crop-pending", self.validation)
        self.assertIn("data-crop-pending", self.script)

    def test_the_output_has_a_maximum_side_and_keeps_the_format(self):
        self.assertIn("OUTPUT_PX = 512", self.script)
        self.assertIn('"image/png"', self.script)
        self.assertIn('"image/jpeg"', self.script)
