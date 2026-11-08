from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from core.models import AuditLog
from core.test_users import UserTestCase
from core.testing import PortalTestCase
from evidence.models import Evidence
from operations.models import Activity
import io
import os

from django.contrib.auth.models import Group
from django.contrib.staticfiles import finders
from django.db import models
from PIL import Image

from core.datos_prueba import demo_pdf
from core.testing import PASSWORD
from accounts.models import UserProfile
from organization.models import Delegation, Officer, Position

def real_image(image_format, size=(4, 4), noise=False):
    buffer = io.BytesIO()
    if noise:
        image = Image.frombytes("RGB", size, os.urandom(size[0] * size[1] * 3))
    else:
        image = Image.new("RGB", size, (30, 90, 160))
    image.save(buffer, format=image_format)
    return buffer.getvalue()


PNG = real_image("PNG")
JPG = real_image("JPEG")
SIGNATURE_ONLY = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def pdf_file(name="informe.pdf"):
    return SimpleUploadedFile(name, demo_pdf("prueba"), content_type="application/pdf")


class EvidenceUploadTests(PortalTestCase):
    def new_data(self, **changes):
        activity = Activity.objects.filter(
            delegation=self.north, deleted_at__isnull=True, status=Activity.Status.REGISTERED
        ).first() or Activity.objects.filter(delegation=self.north, deleted_at__isnull=True).first()
        data = {
            "activity": activity.pk,
            "author_officer": self.officer("F-1001").pk,
            "file_link": pdf_file(),
        }
        data.update(changes)
        return data

    def test_a_file_is_uploaded_and_its_metadata_are_made_by_the_system(self):
        self.login_as("matias.cavieres")
        response = self.client.post(reverse("core:evidencias_create"), self.new_data())
        self.assertEqual(response.status_code, 302)
        evidence = Evidence.objects.get(unique_code="EVD-NORTE-0004")
        self.assertTrue(evidence.file_link.name.startswith("evidencias/"))
        self.assertTrue(evidence.file_link.storage.exists(evidence.file_link.name))
        self.assertIn("Archivo original: informe.pdf", evidence.metadata)
        self.assertIn("Tipo: PDF", evidence.metadata)
        self.assertIn("Huella SHA-256: ", evidence.metadata)

    def test_the_form_asks_for_a_file_and_not_for_metadata(self):
        self.login_as("matias.cavieres")
        response = self.client.get(reverse("core:evidencias_create"))
        form = response.context["form"]
        self.assertIn("file_link", form.fields)
        self.assertNotIn("metadata", form.fields)
        self.assertTrue(form.is_multipart())
        self.assertContains(response, 'enctype="multipart/form-data"')

    def test_a_file_type_that_is_not_accepted_is_rejected(self):
        self.login_as("matias.cavieres")
        bad = SimpleUploadedFile("macro.exe", b"MZ\x00\x00", content_type="application/octet-stream")
        response = self.client.post(reverse("core:evidencias_create"), self.new_data(file_link=bad))
        self.assertEqual(response.status_code, 200)
        self.assertIn("no se acepta", " ".join(response.context["form"].errors["file_link"]))
        self.assertFalse(Evidence.objects.filter(unique_code="EVD-NORTE-0004").exists())

    def test_a_file_whose_content_does_not_match_its_extension_is_rejected(self):
        self.login_as("matias.cavieres")
        fake = SimpleUploadedFile("falso.pdf", b"esto no es un pdf", content_type="application/pdf")
        response = self.client.post(reverse("core:evidencias_create"), self.new_data(file_link=fake))
        self.assertEqual(response.status_code, 200)
        self.assertIn("no corresponde", " ".join(response.context["form"].errors["file_link"]))

    def test_a_file_over_the_size_limit_is_rejected(self):
        self.login_as("matias.cavieres")
        big = SimpleUploadedFile("grande.pdf", b"%PDF-" + b"0" * (10 * 1024 * 1024), content_type="application/pdf")
        response = self.client.post(reverse("core:evidencias_create"), self.new_data(file_link=big))
        self.assertEqual(response.status_code, 200)
        self.assertIn("máximo es 10 MB", " ".join(response.context["form"].errors["file_link"]))

    def test_the_file_is_required_when_creating(self):
        self.login_as("matias.cavieres")
        data = self.new_data()
        del data["file_link"]
        response = self.client.post(reverse("core:evidencias_create"), data)
        self.assertEqual(response.status_code, 200)
        self.assertIn("file_link", response.context["form"].errors)

    def test_editing_without_a_new_file_keeps_the_current_one(self):
        self.login_as("matias.cavieres")
        evidence = Evidence.objects.get(unique_code="EVD-NORTE-0001")
        before = evidence.file_link.name
        data = {
            "activity": evidence.activity_id,
            "unique_code": evidence.unique_code,
            "author_officer": evidence.author_officer_id,
        }
        response = self.client.post(reverse("core:evidencias_update", args=[evidence.pk]), data)
        self.assertEqual(response.status_code, 302)
        evidence.refresh_from_db()
        self.assertEqual(evidence.file_link.name, before)

    def test_the_file_is_delivered_only_through_the_view_with_permission_and_scope(self):
        evidence = Evidence.objects.get(unique_code="EVD-NORTE-0001")
        url = reverse("core:evidence_file", args=[evidence.pk])
        self.assertEqual(self.client.get(url).status_code, 302)
        self.login_as("matias.cavieres")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertTrue(b"".join(response.streaming_content).startswith(b"%PDF-"))
        self.login_as("matias.quiroz")
        self.assertEqual(self.client.get(url).status_code, 404)
        user = self.make_user("sin.permiso")
        self.client.force_login(user)
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_the_detail_shows_a_link_to_the_file_and_the_metadata(self):
        self.login_as("matias.cavieres")
        evidence = Evidence.objects.get(unique_code="EVD-NORTE-0001")
        response = self.client.get(reverse("core:evidencias_detail", args=[evidence.pk]))
        self.assertContains(response, reverse("core:evidence_file", args=[evidence.pk]))
        self.assertContains(response, "Archivo original")

    def test_a_record_without_a_stored_file_shows_only_its_name(self):
        self.login_as("admin")
        evidence = Evidence.objects.get(unique_code="EVD-NORTE-0001")
        Evidence.objects.filter(pk=evidence.pk).update(file_link="evidencias/viejo/sin-archivo.pdf")
        response = self.client.get(reverse("core:evidencias_detail", args=[evidence.pk]))
        self.assertContains(response, "sin-archivo.pdf")
        self.assertContains(response, "el archivo no está en el sistema")
        missing = self.client.get(reverse("core:evidence_file", args=[evidence.pk]))
        self.assertEqual(missing.status_code, 404)


class ProfilePhotoTests(PortalTestCase):
    def upload(self, name, content, kind="image/png"):
        return self.client.post(
            reverse("core:profile"),
            {"accion": "foto", "photo": SimpleUploadedFile(name, content, content_type=kind)},
        )

    def test_a_png_or_jpg_photo_is_saved_and_shown_in_the_header(self):
        self.login_as("matias.cavieres")
        for name, content in (("yo.png", PNG), ("yo.jpg", JPG)):
            with self.subTest(name=name):
                response = self.upload(name, content)
                self.assertRedirects(response, reverse("core:profile"))
                user = User.objects.get(username="matias.cavieres")
                self.assertTrue(user.profile.photo.name.startswith("fotos/"))
                page = self.client.get(reverse("core:dashboard"))
                self.assertContains(page, reverse("core:profile_photo", args=[user.pk]))
        self.assertTrue(AuditLog.objects.filter(event="Foto de perfil cambiada").exists())

    def test_a_replaced_photo_removes_the_old_file(self):
        self.login_as("matias.cavieres")
        self.upload("uno.png", PNG)
        profile = User.objects.get(username="matias.cavieres").profile
        first = profile.photo.name
        self.upload("dos.png", PNG)
        profile.refresh_from_db()
        self.assertNotEqual(profile.photo.name, first)
        self.assertFalse(profile.photo.storage.exists(first))

    def test_other_file_types_and_false_images_are_rejected(self):
        self.login_as("matias.cavieres")
        for name, content in (("nota.txt", b"hola"), ("falsa.png", b"no soy una imagen"), ("doc.pdf", b"%PDF-1")):
            with self.subTest(name=name):
                response = self.upload(name, content)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["photo_form"].errors)
        self.assertFalse(User.objects.get(username="matias.cavieres").profile.photo)

    def test_a_photo_over_the_size_limit_is_rejected(self):
        self.login_as("matias.cavieres")
        big = real_image("PNG", size=(1100, 1100), noise=True)
        self.assertGreater(len(big), 3 * 1024 * 1024)
        response = self.upload("grande.png", big)
        self.assertEqual(response.status_code, 200)
        self.assertIn("máximo es 2 MB", " ".join(response.context["photo_form"].errors["photo"]))

    def test_the_photo_is_an_image_field_and_a_file_with_only_the_signature_is_rejected(self):
        self.assertIsInstance(UserProfile._meta.get_field("photo"), models.ImageField)
        self.login_as("matias.cavieres")
        response = self.upload("firma.png", SIGNATURE_ONLY)
        self.assertEqual(response.status_code, 200)
        self.assertIn("no es una imagen válida", " ".join(response.context["photo_form"].errors["photo"]))
        self.assertFalse(User.objects.get(username="matias.cavieres").profile.photo)

    def test_the_photo_can_be_removed(self):
        self.login_as("matias.cavieres")
        self.upload("yo.png", PNG)
        name = User.objects.get(username="matias.cavieres").profile.photo.name
        response = self.client.post(reverse("core:profile"), {"accion": "quitar_foto"})
        self.assertRedirects(response, reverse("core:profile"))
        profile = User.objects.get(username="matias.cavieres").profile
        self.assertFalse(profile.photo)
        self.assertFalse(profile.photo.storage.exists(name))

    def test_the_photo_is_only_delivered_to_people_who_signed_in(self):
        self.login_as("matias.cavieres")
        self.upload("yo.png", PNG)
        user = User.objects.get(username="matias.cavieres")
        url = reverse("core:profile_photo", args=[user.pk])
        self.assertEqual(self.client.get(url)["Content-Type"], "image/png")
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 302)

    def test_changing_the_password_still_works_next_to_the_photo_form(self):
        self.login_as("matias.cavieres")
        response = self.client.post(
            reverse("core:profile"),
            {"old_password": PASSWORD, "new_password1": "Nueva#Clave2026", "new_password2": "Nueva#Clave2026"},
        )
        self.assertRedirects(response, reverse("core:profile"))
        self.assertTrue(User.objects.get(username="matias.cavieres").check_password("Nueva#Clave2026"))


class OfficerWithAccessTests(PortalTestCase):
    def data(self, **changes):
        data = {
            "name": "Luis Soto Rojas",
            "status": "active",
            "delegation": Delegation.objects.get(name="Delegación Norte").pk,
            "position": Position.objects.first().pk,
        }
        data.update(changes)
        return data

    def access(self, **changes):
        data = {
            "username": "luis.soto",
            "email": "luis.soto@sgr.example",
            "password1": "Clave#2026x",
            "password2": "Clave#2026x",
            "groups": [Group.objects.get(name="Funcionario").pk],
        }
        data.update(changes)
        return data

    def test_the_officer_form_offers_the_access_section_to_who_can_create_users(self):
        self.login_as("admin")
        form = self.client.get(reverse("core:funcionarios_create")).context["form"]
        for name in ("username", "email", "password1", "password2", "groups"):
            self.assertIn(name, form.fields)

    def test_an_officer_with_access_is_created_in_one_step(self):
        self.login_as("admin")
        response = self.client.post(reverse("core:funcionarios_create"), {**self.data(), **self.access()})
        self.assertEqual(response.status_code, 302)
        officer = Officer.objects.get(name="Luis Soto Rojas")
        user = User.objects.get(username="luis.soto")
        self.assertEqual(user.profile.officer, officer)
        self.assertEqual((user.first_name, user.last_name), ("Luis", "Soto Rojas"))
        self.assertEqual([group.name for group in user.groups.all()], ["Funcionario"])
        self.assertTrue(AuditLog.objects.filter(event="Acceso creado junto con el funcionario").exists())
        self.client.logout()
        self.assertTrue(self.client.login(username="luis.soto", password="Clave#2026x"))

    def test_an_officer_without_access_is_created_alone(self):
        self.login_as("admin")
        before = User.objects.count()
        response = self.client.post(reverse("core:funcionarios_create"), self.data())
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Officer.objects.filter(name="Luis Soto Rojas").exists())
        self.assertEqual(User.objects.count(), before)

    def test_a_partly_filled_access_asks_for_the_rest_and_saves_nothing(self):
        self.login_as("admin")
        users = User.objects.count()
        response = self.client.post(reverse("core:funcionarios_create"), {**self.data(), "username": "solo.usuario"})
        self.assertEqual(response.status_code, 200)
        errors = response.context["form"].errors
        for name in ("email", "password1", "groups"):
            self.assertIn(name, errors)
        self.assertFalse(Officer.objects.filter(name="Luis Soto Rojas").exists())
        self.assertEqual(User.objects.count(), users)

    def test_the_access_follows_the_password_policy_and_unique_names(self):
        self.login_as("admin")
        weak = self.client.post(
            reverse("core:funcionarios_create"), {**self.data(), **self.access(password1="abc", password2="abc")}
        )
        self.assertIn("password1", weak.context["form"].errors)
        taken = self.client.post(reverse("core:funcionarios_create"), {**self.data(), **self.access(username="ADMIN")})
        self.assertIn("username", taken.context["form"].errors)
        mail = self.client.post(
            reverse("core:funcionarios_create"), {**self.data(), **self.access(email="admin@sgr.example")}
        )
        self.assertIn("email", mail.context["form"].errors)
        different = self.client.post(
            reverse("core:funcionarios_create"), {**self.data(), **self.access(password2="Otra#Clave2026")}
        )
        self.assertIn("password2", different.context["form"].errors)

    def test_who_cannot_create_users_does_not_get_the_access_section(self):
        self.login_as("matias.cavieres")
        user = User.objects.get(username="matias.cavieres")
        self.give_perm(user, "organization.add_officer")
        self.give_perm(user, "organization.view_officer")
        response = self.client.get(reverse("core:funcionarios_create"))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("username", response.context["form"].fields)
        users = User.objects.count()
        forged = self.client.post(reverse("core:funcionarios_create"), {**self.data(), **self.access()})
        self.assertEqual(forged.status_code, 302)
        self.assertEqual(User.objects.count(), users)

    def test_editing_an_officer_that_already_has_access_does_not_show_the_access_section(self):
        self.login_as("admin")
        officer = UserProfile.objects.exclude(officer__isnull=True).first().officer
        form = self.client.get(reverse("core:funcionarios_update", args=[officer.pk])).context["form"]
        self.assertNotIn("username", form.fields)

    def make_officer_without_access(self, **changes):
        data = {
            "institutional_id": "F-9003",
            "name": "Ana Vega Castro",
            "status": "active",
            "delegation": Delegation.objects.get(name="Delegación Norte"),
            "position": Position.objects.first(),
        }
        data.update(changes)
        return Officer.objects.create(**data)

    def test_an_officer_without_access_can_get_it_from_its_own_edit_screen(self):
        self.login_as("admin")
        officer = self.make_officer_without_access()
        form = self.client.get(reverse("core:funcionarios_update", args=[officer.pk])).context["form"]
        for name in ("username", "email", "password1", "password2", "groups"):
            self.assertIn(name, form.fields)
        data = {**self.data(name="Ana Vega Castro"), **self.access(username="ana.vega", email="ana@sgr.example")}
        response = self.client.post(reverse("core:funcionarios_update", args=[officer.pk]), data)
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(username="ana.vega")
        self.assertEqual(user.profile.officer, officer)
        self.assertTrue(AuditLog.objects.filter(event="Acceso creado para un funcionario existente").exists())
        self.client.logout()
        self.assertTrue(self.client.login(username="ana.vega", password="Clave#2026x"))

    def test_editing_an_officer_without_access_and_leaving_it_blank_creates_no_user(self):
        self.login_as("admin")
        officer = self.make_officer_without_access()
        users = User.objects.count()
        data = self.data(name="Ana Vega C.")
        response = self.client.post(reverse("core:funcionarios_update", args=[officer.pk]), data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(User.objects.count(), users)
        officer.refresh_from_db()
        self.assertEqual(officer.name, "Ana Vega C.")

    def test_an_inactive_officer_cannot_be_given_access(self):
        self.login_as("admin")
        officer = self.make_officer_without_access()
        data = {**self.data(name="Ana Vega Castro", status="inactive"), **self.access(username="ana.vega", email="ana@sgr.example")}
        response = self.client.post(reverse("core:funcionarios_update", args=[officer.pk]), data)
        self.assertEqual(response.status_code, 200)
        self.assertIn("status", response.context["form"].errors)
        self.assertFalse(User.objects.filter(username="ana.vega").exists())

    def test_the_officer_detail_tells_how_the_person_enters(self):
        self.login_as("admin")
        with_access = UserProfile.objects.exclude(officer__isnull=True).first()
        page = self.client.get(reverse("core:funcionarios_detail", args=[with_access.officer.pk]))
        self.assertContains(page, with_access.user.get_username())
        officer = self.make_officer_without_access()
        self.assertContains(self.client.get(reverse("core:funcionarios_detail", args=[officer.pk])), "Sin acceso")

    def test_the_user_form_takes_the_name_from_the_officer(self):
        self.login_as("admin")
        officer = Officer.objects.create(
            institutional_id="F-9002",
            name="Rosa Núñez Pardo",
            status="active",
            delegation=Delegation.objects.get(name="Delegación Norte"),
            position=Position.objects.first(),
        )
        data = {
            "username": "rosa.nunez",
            "email": "rosa@sgr.example",
            "password1": "Clave#2026x",
            "password2": "Clave#2026x",
            "groups": [Group.objects.get(name="Funcionario").pk],
            "officer": officer.pk,
            "is_active": "on",
        }
        response = self.client.post(reverse("core:usuarios_create"), data)
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(username="rosa.nunez")
        self.assertEqual((user.first_name, user.last_name), ("Rosa", "Núñez Pardo"))

    def test_an_account_without_officer_must_write_its_name(self):
        self.login_as("admin")
        data = {
            "username": "cuenta.tecnica",
            "email": "tecnica@sgr.example",
            "password1": "Clave#2026x",
            "password2": "Clave#2026x",
            "groups": [Group.objects.get(name="Coordinación").pk],
            "is_active": "on",
        }
        response = self.client.post(reverse("core:usuarios_create"), data)
        self.assertEqual(response.status_code, 200)
        self.assertIn("first_name", response.context["form"].errors)


class AtencionScreenTests(PortalTestCase):
    def test_the_old_activities_address_leads_to_attention_keeping_the_search(self):
        self.login_as("matias.cavieres")
        response = self.client.get("/actividades/", {"q": "Pérez"})
        self.assertRedirects(response, reverse("core:atencion") + "?q=P%C3%A9rez", fetch_redirect_response=False)

    def test_the_menu_has_attention_but_no_separate_activities_entry(self):
        self.login_as("matias.cavieres")
        labels = self.menu_labels(self.client.get(reverse("core:dashboard")))
        self.assertIn("Atención", labels)
        self.assertNotIn("Actividades", labels)

    def test_the_attention_screen_has_the_filters_and_the_archive_link_of_the_old_list(self):
        self.login_as("admin")
        response = self.client.get(reverse("core:atencion"))
        names = {spec.name for spec in response.context["filters"]}
        self.assertTrue({"status", "requires_visit"} <= names)
        self.assertContains(response, "Incluir archivados")

    def test_the_attention_screen_can_be_filtered_without_a_search_text(self):
        self.login_as("admin")
        total = self.client.get(reverse("core:atencion")).context["page"].paginator.count
        response = self.client.get(reverse("core:atencion"), {"status": Activity.Status.REGISTERED})
        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(response.context["page"].paginator.count, total)

    def test_a_record_page_goes_back_to_attention(self):
        self.login_as("matias.cavieres")
        activity = Activity.objects.filter(delegation=self.north, deleted_at__isnull=True).first()
        response = self.client.get(reverse("core:actividades_detail", args=[activity.pk]))
        self.assertContains(response, f'href="{reverse("core:atencion")}"')


class LiveSearchTests(PortalTestCase):
    def test_the_list_screens_search_while_typing(self):
        self.login_as("admin")
        html = self.client.get(reverse("core:usuarios_list")).content.decode()
        self.assertIn("data-live-search", html)
        self.assertIn('data-live-target="resultados"', html)
        self.assertIn('data-live-target="acciones"', html)
        self.assertIn("core/js/live-search.js", html)
        self.assertIsNotNone(finders.find("core/js/live-search.js"))

    def test_the_atencion_screen_searches_while_typing(self):
        self.login_as("matias.cavieres")
        html = self.client.get(reverse("core:atencion"), {"q": "perez"}).content.decode()
        self.assertIn("data-live-search", html)
        self.assertIn('data-live-target="resultados"', html)
        self.assertIn('data-live-target="aviso"', html)

    def test_the_search_button_is_still_there_for_who_has_no_javascript(self):
        self.login_as("admin")
        self.assertContains(self.client.get(reverse("core:usuarios_list")), " Buscar</button>")

    def test_the_part_that_changes_has_the_number_of_results_for_the_screen_reader(self):
        self.login_as("admin")
        total = User.objects.count()
        html = self.client.get(reverse("core:usuarios_list")).content.decode()
        self.assertIn(f'data-live-count="{total}"', html)
        none = self.client.get(reverse("core:usuarios_list"), {"q": "zzzz-no-existe"}).content.decode()
        self.assertIn('data-live-count="0"', none)


class UserPhotoByAdminTests(UserTestCase):
    """El Super Usuario ve la foto de otra persona y puede cambiarla o quitársela al editar su usuario."""

    def setUp(self):
        self.target = User.objects.get(username="matias.quiroz")
        self.login_as("admin")

    def photo(self, content=PNG, name="foto.png", kind="image/png"):
        return SimpleUploadedFile(name, content, content_type=kind)

    def save(self, **changes):
        data = self.edit_data(self.target, **changes)
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(self.update_url(self.target), data)

    def stored(self):
        return User.objects.get(pk=self.target.pk).profile.photo

    def test_the_detail_shows_the_photo_or_says_there_is_none(self):
        detail = reverse("core:usuarios_detail", args=[self.target.pk])
        page = self.client.get(detail)
        self.assertContains(page, "Foto de perfil")
        self.assertNotContains(page, "avatar-lg")
        self.save(photo=self.photo())
        page = self.client.get(detail)
        self.assertContains(page, reverse("core:profile_photo", args=[self.target.pk]))
        self.assertContains(page, 'class="avatar avatar-lg"')

    def test_the_edit_form_accepts_files_and_shows_the_current_photo(self):
        page = self.client.get(self.update_url(self.target))
        self.assertContains(page, 'enctype="multipart/form-data"')
        self.assertContains(page, 'name="photo"')
        self.assertNotContains(page, 'name="remove_photo"')  # sin foto no hay nada que quitar
        self.save(photo=self.photo())
        page = self.client.get(self.update_url(self.target))
        self.assertContains(page, "photo-current")
        self.assertContains(page, 'name="remove_photo"')

    def test_the_superuser_sets_and_replaces_the_photo_of_another_person(self):
        response = self.save(photo=self.photo())
        self.assertEqual(response.status_code, 302)
        first = self.stored()
        self.assertTrue(first.name.startswith("fotos/"))
        self.assertTrue(first.storage.exists(first.name))
        event = AuditLog.objects.filter(event="Foto de perfil cambiada").latest("pk")
        self.assertEqual((event.user.username, event.record_id), ("admin", self.target.pk))
        self.save(photo=self.photo(JPG, "otra.jpg", "image/jpeg"))
        second = self.stored()
        self.assertNotEqual(second.name, first.name)
        self.assertFalse(second.storage.exists(first.name), "la foto anterior se borra al confirmar el cambio")
        self.assertTrue(second.storage.exists(second.name))

    def test_the_superuser_removes_the_photo_of_another_person(self):
        self.save(photo=self.photo())
        name = self.stored().name
        storage = self.stored().storage
        response = self.save(remove_photo="on")
        self.assertEqual(response.status_code, 302)
        self.assertFalse(self.stored())
        self.assertFalse(storage.exists(name))
        self.assertTrue(AuditLog.objects.filter(event="Foto de perfil quitada", record_id=self.target.pk, user__username="admin").exists())

    def test_saving_without_touching_the_photo_keeps_it(self):
        self.save(photo=self.photo())
        name = self.stored().name
        self.save(first_name="Matías S.")
        self.assertEqual(self.stored().name, name)

    def test_invalid_files_are_rejected_and_nothing_changes(self):
        for bad in (
            self.photo(SIGNATURE_ONLY),
            self.photo(b"texto", "nota.txt", "text/plain"),
            self.photo(PNG + b"\0" * (2 * 1024 * 1024), "grande.png"),
        ):
            with self.subTest(name=bad.name):
                response = self.save(photo=bad)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["form"].errors["photo"])
                self.assertFalse(self.stored())

    def test_a_new_photo_and_remove_together_is_an_error(self):
        self.save(photo=self.photo())
        response = self.save(photo=self.photo(JPG, "otra.jpg", "image/jpeg"), remove_photo="on")
        self.assertEqual(response.status_code, 200)
        self.assertIn("no las dos cosas", " ".join(response.context["form"].errors["remove_photo"]))

    def test_a_new_user_can_be_created_with_a_photo(self):
        data = self.user_data(photo=self.photo())
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse("core:usuarios_create"), data)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.get(username="ana.torres").profile.photo)

    def test_the_person_sees_the_photo_the_superuser_gave_them(self):
        self.save(photo=self.photo())
        self.login_as("matias.quiroz")
        page = self.client.get(reverse("core:profile"))
        self.assertContains(page, reverse("core:profile_photo", args=[self.target.pk]))
        self.assertEqual(self.client.get(reverse("core:profile_photo", args=[self.target.pk])).status_code, 200)

    def test_only_the_superuser_can_change_someone_elses_photo(self):
        self.login_as("matias.cavieres")
        response = self.client.post(self.update_url(self.target), self.edit_data(self.target, photo=self.photo()))
        self.assertEqual(response.status_code, 403)
        self.assertFalse(self.stored())
