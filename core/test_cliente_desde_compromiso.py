"""Versión 42: del solicitante externo de la agenda colectiva a su cuenta de cliente."""
from django.contrib.auth.models import Group
from django.urls import reverse

from accounts.models import UserProfile
from core.test_cartas_y_compromisos import make_commitment
from core.testing import PortalTestCase
from operations.models import Commitment
from organization.models import Beneficiary, Territory

MARIA_RUT = "11111111-1"
FREE_RUT = "33333333-3"


class FromCommitmentBase(PortalTestCase):

    def setUp(self):
        self.cavieres = self.officer("F-1001")
        self.territory = Territory.objects.filter(delegation=self.north).first()
        self.item = make_commitment(
            self.north, self.cavieres, self.territory, "Vecina de la Población Nueva", physical=False
        )

    def url(self, commitment=None):
        return reverse("core:client_from_commitment", args=[(commitment or self.item).pk])

    def data(self, **changes):
        values = {"rut": "12.345.678-5", "name": "Vecina de la Población Nueva", "phone": "+56 9 1234 5678", "address": "Los Aromos 1234"}
        values.update(changes)
        return values

    def actions(self, commitment=None):
        response = self.client.get(reverse("core:agenda_detail", args=[(commitment or self.item).pk]))
        self.assertEqual(response.status_code, 200)
        return [label for label, _, _ in response.context["extra_actions"]]


class ButtonTests(FromCommitmentBase):

    def test_the_button_is_offered_for_an_external_requester_of_the_agenda(self):
        self.login_as("admin")
        self.assertIn("Crear cuenta de cliente", self.actions())

    def test_the_button_is_not_offered_to_someone_who_cannot_create_users(self):
        self.login_as("matias.cavieres")
        self.assertNotIn("Crear cuenta de cliente", self.actions())

    def test_the_button_needs_both_permissions(self):
        user = self.make_user("solo.usuarios", groups=["Consulta"], officer=self.officer("F-1004"))
        for label in ("operations.view_commitment", "auth.add_user"):
            self.give_perm(user, label)
        self.client.force_login(user)
        self.assertNotIn("Crear cuenta de cliente", self.actions())
        self.give_perm(user, "organization.add_beneficiary")
        user = type(user).objects.get(pk=user.pk)
        self.client.force_login(user)
        self.assertIn("Crear cuenta de cliente", self.actions())

    def test_the_button_is_not_offered_for_an_internal_requester(self):
        internal = make_commitment(
            self.north, self.cavieres, self.territory, "Dirección de Obras",
            physical=False, requester_type=Commitment.RequesterType.INTERNAL,
        )
        self.login_as("admin")
        self.assertNotIn("Crear cuenta de cliente", self.actions(internal))

    def test_a_field_commitment_has_no_button(self):
        physical = make_commitment(self.north, self.cavieres, self.territory, "Vecina de Terreno", physical=True)
        self.login_as("admin")
        response = self.client.get(reverse("core:compromisos_detail", args=[physical.pk]))
        self.assertNotIn("Crear cuenta de cliente", [label for label, _, _ in response.context["extra_actions"]])


class CreationTests(FromCommitmentBase):

    def setUp(self):
        super().setUp()
        self.login_as("admin")

    def test_the_form_starts_with_the_name_of_the_requester(self):
        response = self.client.get(self.url())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["form"].initial["name"], "Vecina de la Población Nueva")

    def test_a_new_rut_creates_the_beneficiary_and_goes_to_the_new_user(self):
        response = self.client.post(self.url(), self.data())
        person = Beneficiary.objects.get(rut="12345678-5")
        self.assertEqual((person.name, person.phone, person.address), ("Vecina de la Población Nueva", "+56 9 1234 5678", "Los Aromos 1234"))
        self.assertRedirects(response, f"{reverse('core:usuarios_create')}?beneficiary={person.pk}", fetch_redirect_response=False)

    def test_a_wrong_rut_is_refused_and_nothing_is_created(self):
        before = Beneficiary.objects.count()
        response = self.client.post(self.url(), self.data(rut="11.111.111-2"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("rut", response.context["form"].errors)
        self.assertEqual(Beneficiary.objects.count(), before)

    def test_a_rut_that_already_exists_reuses_the_beneficiary(self):
        before = Beneficiary.objects.count()
        response = self.client.post(self.url(), self.data(rut="33.333.333-3", name="Otro Nombre"))
        free = Beneficiary.objects.get(rut=FREE_RUT)
        self.assertEqual(Beneficiary.objects.count(), before)
        self.assertNotEqual(free.name, "Otro Nombre")
        self.assertRedirects(response, f"{reverse('core:usuarios_create')}?beneficiary={free.pk}", fetch_redirect_response=False)

    def test_a_beneficiary_that_already_has_an_account_is_not_offered_again(self):
        response = self.client.post(self.url(), self.data(rut="11.111.111-1"))
        self.assertRedirects(response, self.url(), fetch_redirect_response=False)
        page = self.client.get(self.url())
        self.assertIn("ya tiene una cuenta de cliente", " ".join(str(m) for m in page.context["messages"]))

    def test_the_creation_is_left_in_the_audit_log(self):
        from core.models import AuditLog  # noqa: PLC0415

        self.client.post(self.url(), self.data())
        self.assertTrue(AuditLog.objects.filter(event="Beneficiario creado desde un compromiso").exists())


class AccessTests(FromCommitmentBase):

    def test_someone_without_the_permissions_is_refused(self):
        self.login_as("matias.cavieres")
        self.assertEqual(self.client.get(self.url()).status_code, 403)
        before = Beneficiary.objects.count()
        self.assertEqual(self.client.post(self.url(), self.data()).status_code, 403)
        self.assertEqual(Beneficiary.objects.count(), before)

    def test_an_internal_or_field_commitment_does_not_open(self):
        internal = make_commitment(
            self.north, self.cavieres, self.territory, "Dirección de Obras",
            physical=False, requester_type=Commitment.RequesterType.INTERNAL,
        )
        physical = make_commitment(self.north, self.cavieres, self.territory, "Vecina de Terreno", physical=True)
        self.login_as("admin")
        for commitment in (internal, physical):
            self.assertEqual(self.client.get(self.url(commitment)).status_code, 404)

    def test_a_commitment_of_another_delegation_does_not_open_for_someone_with_a_delegation(self):
        user = self.make_user("jefa.cuentas", groups=["Consulta"], officer=self.officer("F-1004"))
        for label in ("operations.view_commitment", "auth.add_user", "organization.add_beneficiary"):
            self.give_perm(user, label)
        south_officer = self.officer("F-2001")
        other = make_commitment(
            self.south, south_officer, Territory.objects.filter(delegation=self.south).first(), "Vecina del Sur", physical=False
        )
        self.client.force_login(type(user).objects.get(pk=user.pk))
        self.assertEqual(self.client.get(self.url(other)).status_code, 404)

    def test_the_page_needs_a_session(self):
        response = self.client.get(self.url())
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith("/?next="))


class NewUserStartTests(FromCommitmentBase):

    def setUp(self):
        super().setUp()
        self.login_as("admin")

    def test_the_new_user_starts_as_a_client_of_the_beneficiary(self):
        free = Beneficiary.objects.get(rut=FREE_RUT)
        form = self.client.get(f"{reverse('core:usuarios_create')}?beneficiary={free.pk}").context["form"]
        self.assertEqual(form.initial["beneficiary"], free.pk)
        self.assertEqual(form.initial["groups"], [Group.objects.get(name="Cliente").pk])

    def test_a_beneficiary_with_an_account_does_not_prefill(self):
        maria = Beneficiary.objects.get(rut=MARIA_RUT)
        self.assertTrue(UserProfile.objects.filter(beneficiary=maria).exists())
        form = self.client.get(f"{reverse('core:usuarios_create')}?beneficiary={maria.pk}").context["form"]
        self.assertNotIn("beneficiary", form.initial)
        self.assertNotIn("groups", form.initial)

    def test_a_wrong_value_does_not_prefill(self):
        for value in ("abc", "999999", ""):
            form = self.client.get(f"{reverse('core:usuarios_create')}?beneficiary={value}").context["form"]
            self.assertNotIn("beneficiary", form.initial, value)

    def test_the_whole_path_leaves_a_client_account(self):
        self.client.post(self.url(), self.data())
        person = Beneficiary.objects.get(rut="12345678-5")
        response = self.client.post(
            reverse("core:usuarios_create"),
            {
                "username": "vecina.nueva", "first_name": "Vecina", "last_name": "Nueva", "email": "vecina@dominio.cl",
                "password1": "ClaveSegura#2026", "password2": "ClaveSegura#2026", "is_active": "on",
                "groups": [Group.objects.get(name="Cliente").pk], "officer": "", "beneficiary": person.pk,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(UserProfile.objects.get(user__username="vecina.nueva").beneficiary_id, person.pk)
