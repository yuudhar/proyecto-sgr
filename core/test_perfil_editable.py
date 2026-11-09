"""Mi perfil: cada persona edita su propio nombre y correo (v35), sin tocar permisos ni a otras personas."""

from django.contrib.auth.models import Group, User
from django.test import Client
from django.urls import reverse

from accounts.models import UserProfile
from core.forms import ProfileDataForm
from core.models import AuditLog
from core.testing import ALL_USERS, PASSWORD, PortalTestCase
from organization.models import Beneficiary, Officer


def snapshot(user):
    """Todo lo que un perfil NO debe poder cambiar: permisos, perfiles, estado, delegación, funcionario y vínculos."""
    user = User.objects.get(pk=user.pk)
    profile = UserProfile.objects.filter(user=user).first()
    return {
        "username": user.username,
        "password": user.password,
        "is_active": user.is_active,
        "is_staff": user.is_staff,
        "is_superuser": user.is_superuser,
        "groups": sorted(user.groups.values_list("name", flat=True)),
        "permissions": sorted(user.user_permissions.values_list("codename", flat=True)),
        "officer": profile.officer_id if profile else None,
        "beneficiary": profile.beneficiary_id if profile else None,
        "extra": sorted(user.role_delegations.values_list("delegation_id", flat=True)),
    }


class ProfileIdentityTests(PortalTestCase):
    def setUp(self):
        self.user = self.login_as("matias.cavieres")
        self.url = reverse("core:profile")

    def data(self, **changes):
        data = {"accion": "perfil", "first_name": "Matías Andrés", "last_name": "Cavieres Soto", "email": "matias.nuevo@sgr.example"}
        data.update(changes)
        return data

    def test_every_role_sees_the_form_with_name_and_email(self):
        for username in ALL_USERS + ("cliente1",):
            with self.subTest(user=username):
                self.login_as(username)
                page = self.client.get(self.url)
                self.assertContains(page, '<input type="hidden" name="accion" value="perfil">', html=False)
                self.assertEqual(list(page.context["identity_form"].fields), ["first_name", "last_name", "email"])
                self.assertContains(page, "Guardar nombre y correo")

    def test_the_form_has_a_whitelist_of_three_fields_and_never_all(self):
        self.assertEqual(ProfileDataForm._meta.fields, ("first_name", "last_name", "email"))
        self.assertEqual(ProfileDataForm._meta.model, User)

    def test_the_form_instance_is_always_the_person_with_the_session(self):
        form = self.client.get(self.url).context["identity_form"]
        self.assertEqual(form.instance.pk, self.user.pk)
        self.assertEqual(form.initial["email"], self.user.email)

    def test_it_saves_the_name_and_the_email_and_says_so(self):
        response = self.client.post(self.url, self.data(), follow=True)
        self.assertRedirects(response, self.url)
        self.assertContains(response, "Listo: actualizaste tu nombre y tu correo.")
        saved = User.objects.get(pk=self.user.pk)
        self.assertEqual((saved.first_name, saved.last_name, saved.email), ("Matías Andrés", "Cavieres Soto", "matias.nuevo@sgr.example"))

    def test_the_new_name_shows_in_the_page_header(self):
        self.client.post(self.url, self.data())
        self.assertEqual(self.client.get(self.url).context["me_name"], "Matías Andrés Cavieres Soto")

    def test_the_change_is_audited_with_before_and_after(self):
        before = User.objects.get(pk=self.user.pk)
        self.client.post(self.url, self.data())
        log = AuditLog.objects.get(event="Datos de perfil actualizados")
        self.assertEqual((log.user, log.affected_entity, log.record_id), (self.user, "User", self.user.pk))
        self.assertIn(f"correo: {before.email}", log.previous_value)
        self.assertIn("correo: matias.nuevo@sgr.example", log.new_value)
        self.assertIn("nombre: Matías Andrés", log.new_value)

    def test_only_what_changed_is_saved_and_audited(self):
        before = User.objects.get(pk=self.user.pk)
        self.client.post(self.url, self.data(first_name=before.first_name, last_name=before.last_name))
        log = AuditLog.objects.get(event="Datos de perfil actualizados")
        self.assertNotIn("nombre", log.new_value)
        self.assertNotIn("apellido", log.new_value)
        self.assertIn("correo", log.new_value)

    def test_sending_the_same_data_changes_nothing_and_leaves_no_audit_entry(self):
        before = User.objects.get(pk=self.user.pk)
        response = self.client.post(
            self.url, self.data(first_name=before.first_name, last_name=before.last_name, email=before.email), follow=True
        )
        self.assertContains(response, "No hiciste cambios en tu nombre ni en tu correo.")
        self.assertFalse(AuditLog.objects.filter(event="Datos de perfil actualizados").exists())

    def test_the_name_of_the_officer_file_does_not_change(self):
        officer = Officer.objects.get(pk=self.user.profile.officer_id)
        name = officer.name
        self.client.post(self.url, self.data())
        self.assertEqual(Officer.objects.get(pk=officer.pk).name, name)

    def test_a_name_with_symbols_is_rejected_and_nothing_is_saved(self):
        before = snapshot(self.user), User.objects.get(pk=self.user.pk).first_name
        for value in ("<b>Matías</b>", "Mat1as", "Matías;DROP", "   "):
            with self.subTest(first_name=value):
                response = self.client.post(self.url, self.data(first_name=value))
                self.assertEqual(response.status_code, 200)
                self.assertIn("first_name", response.context["identity_form"].errors)
                self.assertEqual(User.objects.get(pk=self.user.pk).first_name, before[1])
        self.assertEqual(snapshot(self.user), before[0])

    def test_an_invalid_form_does_not_change_the_name_shown_in_the_header(self):
        shown = self.client.get(self.url).context["me_name"]
        response = self.client.post(self.url, self.data(first_name="Nuevo Nombre", email="no-es-correo"))
        self.assertEqual(response.context["me_name"], shown)
        self.assertContains(response, "No se guardaron tu nombre ni tu correo.")

    def test_a_bad_email_is_rejected(self):
        for value in ("no-es-correo", "a@b", "a b@c.cl", "@sgr.cl", "x@y..cl"):
            with self.subTest(email=value):
                response = self.client.post(self.url, self.data(email=value))
                self.assertIn("email", response.context["identity_form"].errors)

    def test_an_email_that_is_too_long_is_rejected(self):
        response = self.client.post(self.url, self.data(email="a" * 250 + "@sgr.cl"))
        self.assertIn("email", response.context["identity_form"].errors)

    def test_a_name_that_is_too_long_is_rejected(self):
        response = self.client.post(self.url, self.data(first_name="A" * 151))
        self.assertIn("first_name", response.context["identity_form"].errors)

    def test_an_email_that_another_account_uses_is_rejected_even_with_other_capitals(self):
        other = User.objects.get(username="consulta1")
        for value in (other.email, other.email.upper()):
            with self.subTest(email=value):
                response = self.client.post(self.url, self.data(email=value))
                self.assertIn("Ese correo ya lo usa otro usuario", str(response.context["identity_form"].errors["email"]))
        self.assertNotEqual(User.objects.get(pk=self.user.pk).email, other.email)

    def test_the_own_email_with_other_capitals_is_accepted(self):
        own = User.objects.get(pk=self.user.pk).email
        response = self.client.post(self.url, self.data(email=own.upper()))
        self.assertRedirects(response, self.url, fetch_redirect_response=False)

    def test_the_name_and_the_email_cannot_be_emptied_once_they_exist(self):
        for field, message in (("first_name", "Escribe tu nombre."), ("email", "Escribe tu correo")):
            with self.subTest(field=field):
                response = self.client.post(self.url, self.data(**{field: ""}))
                self.assertIn(message, str(response.context["identity_form"].errors[field]))

    def test_the_last_name_may_be_empty(self):
        response = self.client.post(self.url, self.data(last_name=""))
        self.assertRedirects(response, self.url, fetch_redirect_response=False)
        self.assertEqual(User.objects.get(pk=self.user.pk).last_name, "")

    def test_an_account_without_email_or_name_may_leave_them_empty(self):
        bare = User.objects.create_user("sin.datos", password=PASSWORD)
        self.client.force_login(bare)
        response = self.client.post(self.url, {"accion": "perfil", "first_name": "", "last_name": "", "email": ""})
        self.assertRedirects(response, self.url, fetch_redirect_response=False)

    def test_an_account_without_email_can_add_one(self):
        bare = User.objects.create_user("sin.correo", password=PASSWORD)
        self.client.force_login(bare)
        self.client.post(self.url, {"accion": "perfil", "first_name": "Sin", "last_name": "Correo", "email": "sin.correo@sgr.example"})
        self.assertEqual(User.objects.get(pk=bare.pk).email, "sin.correo@sgr.example")

    def test_the_email_is_trimmed(self):
        self.client.post(self.url, self.data(email="  matias.nuevo@sgr.example  "))
        self.assertEqual(User.objects.get(pk=self.user.pk).email, "matias.nuevo@sgr.example")

    def test_the_password_form_and_the_photo_form_keep_working_next_to_it(self):
        response = self.client.post(
            self.url, {"old_password": PASSWORD, "new_password1": "Nueva#Clave2026", "new_password2": "Nueva#Clave2026"}
        )
        self.assertRedirects(response, self.url, fetch_redirect_response=False)
        self.assertEqual(User.objects.get(pk=self.user.pk).first_name, self.user.first_name)

    def test_an_anonymous_visitor_cannot_use_the_form(self):
        anonymous = Client()
        response = anonymous.post(self.url, self.data())
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/?next=/perfil/")
        self.assertNotEqual(User.objects.get(pk=self.user.pk).email, "matias.nuevo@sgr.example")


class ProfileTamperingTests(PortalTestCase):
    """Lo que no es nombre ni correo se ignora: ni permisos, ni delegación, ni la cuenta de otra persona."""

    def setUp(self):
        self.user = self.login_as("matias.cavieres")
        self.url = reverse("core:profile")
        self.other = User.objects.get(username="consulta1")

    def tampered(self, **extra):
        data = {"accion": "perfil", "first_name": "Matías", "last_name": "Cavieres", "email": "matias.cavieres@sgr.example"}
        data.update(extra)
        return data

    def test_sending_permissions_roles_state_or_ownership_changes_nothing(self):
        before = snapshot(self.user)
        data = self.tampered(
            groups=[Group.objects.get(name="Coordinación").pk, Group.objects.get(name="Jefatura").pk],
            is_superuser="on",
            is_staff="on",
            is_active="",
            username="otro.usuario",
            password="hackeada",
            password1="Hackeada#2026",
            user_permissions=[1, 2, 3],
            officer=Officer.objects.exclude(pk=self.user.profile.officer_id).first().pk,
            beneficiary=Beneficiary.objects.first().pk,
            extra_delegations=[self.south.pk],
            delegation=self.south.pk,
        )
        response = self.client.post(self.url, data)
        self.assertRedirects(response, self.url, fetch_redirect_response=False)
        self.assertEqual(snapshot(self.user), before)

    def test_an_id_that_belongs_to_another_person_does_not_change_that_person(self):
        before = snapshot(self.other), User.objects.get(pk=self.other.pk).email, User.objects.get(pk=self.other.pk).first_name
        for name in ("id", "pk", "user", "user_id", "instance", "profile", "profile_id"):
            self.client.post(self.url, self.tampered(**{name: self.other.pk, "first_name": "Cambiado", "email": "ajeno@sgr.example"}))
        after = User.objects.get(pk=self.other.pk)
        self.assertEqual((snapshot(self.other), after.email, after.first_name), before)
        self.assertEqual(User.objects.get(pk=self.user.pk).first_name, "Cambiado")  # lo suyo sí se guardó

    def test_the_other_persons_email_in_the_url_is_ignored_too(self):
        self.client.post(f"{self.url}?id={self.other.pk}&user={self.other.pk}", self.tampered(first_name="Solo Yo"))
        self.assertEqual(User.objects.get(pk=self.user.pk).first_name, "Solo Yo")
        self.assertNotEqual(User.objects.get(pk=self.other.pk).first_name, "Solo Yo")

    def test_the_profile_of_the_session_is_the_only_one_edited_even_for_a_superuser(self):
        admin = self.login_as("admin")
        self.client.post(self.url, self.tampered(first_name="Administradora", email="admin.nuevo@sgr.example", id=self.other.pk, user=self.other.pk))
        self.assertEqual(User.objects.get(pk=admin.pk).first_name, "Administradora")
        self.assertNotEqual(User.objects.get(pk=self.other.pk).first_name, "Administradora")
        self.assertTrue(User.objects.get(pk=admin.pk).is_superuser)

    def test_a_reader_cannot_use_the_profile_to_get_more_than_reading(self):
        reader = self.login_as("consulta1")
        before = snapshot(reader)
        self.client.post(
            self.url,
            self.tampered(first_name="Lectora", groups=[Group.objects.get(name="Jefatura").pk], is_superuser="on", is_staff="on"),
        )
        self.assertEqual(snapshot(reader), before)
        self.assertEqual(self.client.get(reverse("core:usuarios_list")).status_code, 403)

    def test_the_other_actions_of_the_page_still_need_their_own_form(self):
        before = User.objects.get(pk=self.user.pk).email
        self.client.post(self.url, {"accion": "datos", "first_name": "X", "email": "otro@sgr.example"})
        self.assertEqual(User.objects.get(pk=self.user.pk).email, before)


class ClientProfileIdentityTests(PortalTestCase):
    """Cliente: edita el nombre y el correo de su CUENTA; el nombre de su ficha de beneficiario es el dato oficial."""

    def setUp(self):
        self.maria = self.login_as("cliente1")
        self.url = reverse("core:profile")
        self.profile = UserProfile.objects.get(user=self.maria)
        self.beneficiary = Beneficiary.objects.get(pk=self.profile.beneficiary_id)

    def data(self, **changes):
        data = {"accion": "perfil", "first_name": "María José", "last_name": "Pérez Soto", "email": "maria.jose@correo.cl"}
        data.update(changes)
        return data

    def test_the_client_edits_the_name_and_the_email_of_the_account(self):
        response = self.client.post(self.url, self.data(), follow=True)
        self.assertRedirects(response, self.url)
        saved = User.objects.get(pk=self.maria.pk)
        self.assertEqual((saved.first_name, saved.last_name, saved.email), ("María José", "Pérez Soto", "maria.jose@correo.cl"))
        self.assertTrue(AuditLog.objects.filter(event="Datos de perfil actualizados", user=self.maria).exists())

    def test_the_name_of_the_beneficiary_file_and_the_link_do_not_change(self):
        name, rut = self.beneficiary.name, self.beneficiary.rut
        self.client.post(self.url, self.data())
        again = Beneficiary.objects.get(pk=self.beneficiary.pk)
        self.assertEqual((again.name, again.rut), (name, rut))
        self.assertEqual(UserProfile.objects.get(user=self.maria).beneficiary_id, self.beneficiary.pk)

    def test_the_client_still_sees_their_own_attentions_after_changing_the_name(self):
        before = self.client.get(reverse("core:portal_activities")).context["page"].paginator.count
        self.client.post(self.url, self.data(first_name="Otra", last_name="Persona"))
        page = self.client.get(reverse("core:portal_activities"))
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.context["page"].paginator.count, before)
        self.assertGreater(before, 0)

    def test_the_page_shows_the_file_name_as_read_only_and_has_no_input_for_it(self):
        page = self.client.get(self.url)
        self.assertContains(page, "Nombre en tu ficha")
        self.assertContains(page, self.beneficiary.name)
        self.assertNotIn("name", page.context["client_form"].fields)
        self.assertEqual(list(page.context["client_form"].fields), ["phone", "address"])

    def test_the_email_is_edited_in_one_place_only(self):
        page = self.client.get(self.url)
        self.assertNotIn("email", page.context["client_form"].fields)
        self.assertIn("email", page.context["identity_form"].fields)

    def test_the_contact_form_does_not_touch_the_email_or_the_name(self):
        before = User.objects.get(pk=self.maria.pk)
        self.client.post(
            self.url, {"accion": "datos", "phone": "+56 9 1111 2222", "address": "Los Aromos 999", "email": "otro@correo.cl", "first_name": "X"}
        )
        after = User.objects.get(pk=self.maria.pk)
        self.assertEqual((after.email, after.first_name), (before.email, before.first_name))
        self.assertEqual(Beneficiary.objects.get(pk=self.beneficiary.pk).address, "Los Aromos 999")

    def test_the_client_cannot_take_the_email_of_the_other_client(self):
        other = User.objects.get(username="cliente2")
        response = self.client.post(self.url, self.data(email=other.email))
        self.assertIn("email", response.context["identity_form"].errors)

    def test_the_client_cannot_use_the_form_to_get_permissions_or_another_beneficiary(self):
        before = snapshot(self.maria)
        other = Beneficiary.objects.exclude(pk=self.beneficiary.pk).first()
        self.client.post(
            self.url,
            self.data(groups=[Group.objects.get(name="Coordinación").pk], is_superuser="on", is_staff="on", beneficiary=other.pk, officer=1),
        )
        self.assertEqual(snapshot(self.maria), before)
        self.assertEqual(self.client.get(reverse("core:usuarios_list")).status_code, 403)

    def test_the_other_client_is_not_touched(self):
        other = User.objects.get(username="cliente2")
        before = (snapshot(other), other.first_name, other.email)
        self.client.post(self.url, self.data(id=other.pk, user=other.pk))
        again = User.objects.get(pk=other.pk)
        self.assertEqual((snapshot(other), again.first_name, again.email), before)
