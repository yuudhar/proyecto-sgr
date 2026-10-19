from django.contrib.auth.models import Group, Permission
from django.urls import reverse

from core.models import AuditLog
from core.testing import PortalTestCase
from operations.models import Activity


class RoleMatrixTests(PortalTestCase):

    MATRIX = {
        "admin": (True, True, True, True),
        "matias.cavieres": (True, True, True, False),
        "jefatura1": (True, False, False, False),
        "consulta1": (True, False, False, False),
        "coordinacion1": (False, False, False, False),
    }

    def urls(self):
        activity = self.activity("María Pérez")
        return (
            reverse("core:atencion"),
            reverse("core:actividades_create"),
            reverse("core:actividades_update", args=[activity.pk]),
            reverse("core:actividades_archive", args=[activity.pk]),
        )

    def test_each_role_can_do_only_what_its_permissions_allow(self):
        for username, expected in self.MATRIX.items():
            self.login_as(username)
            for url, allowed, action in zip(self.urls(), expected, ("ver", "crear", "editar", "eliminar"), strict=True):
                with self.subTest(user=username, action=action):
                    status = self.client.get(url).status_code
                    self.assertEqual(status, 200 if allowed else 403)

    def test_the_server_refuses_post_without_the_permission(self):
        activity = self.activity("María Pérez")
        for username in ("matias.cavieres", "consulta1", "jefatura1"):
            self.login_as(username)
            url = reverse("core:actividades_archive", args=[activity.pk])
            with self.subTest(user=username):
                self.assertEqual(self.client.post(url).status_code, 403)
        activity.refresh_from_db()
        self.assertIsNone(activity.deleted_at)
        self.assertFalse(AuditLog.objects.filter(event="Registro archivado").exists())

    def test_consulta_cannot_create_edit_or_delete_even_with_the_direct_url(self):
        self.login_as("consulta1")
        activity = self.activity("María Pérez")
        before = Activity.objects.count()
        response = self.client.post(reverse("core:actividades_create"), self.intake_data())
        self.assertEqual(response.status_code, 403)
        response = self.client.post(
            reverse("core:actividades_update", args=[activity.pk]), self.activity_data(contact_name="Cambiada")
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.client.post(reverse("core:actividades_restore", args=[activity.pk])).status_code, 403)
        self.assertEqual(Activity.objects.count(), before)
        activity.refresh_from_db()
        self.assertEqual(activity.contact_name, "María Pérez")

    def test_anonymous_users_are_sent_to_the_login(self):
        activity = self.activity("María Pérez")
        for url in (
            reverse("core:atencion"),
            reverse("core:actividades_create"),
            reverse("core:actividades_update", args=[activity.pk]),
            reverse("core:actividades_archive", args=[activity.pk]),
            reverse("core:roles_list"),
        ):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertTrue(response["Location"].startswith(reverse("core:login")))

    def test_buttons_follow_the_permissions_of_each_role(self):
        activity = self.activity("María Pérez")
        listing = reverse("core:atencion")
        detail = reverse("core:actividades_detail", args=[activity.pk])

        self.login_as("consulta1")
        response = self.client.get(listing)
        self.assertFalse(response.context["can_add"])
        self.assertFalse(response.context["any_actions"])
        self.assertNotContains(response, "Registrar atención")
        self.assertNotContains(response, "data-delete=")
        self.assertContains(response, "Ver")
        page = self.client.get(detail)
        self.assertNotContains(page, "Editar")
        self.assertNotContains(page, "data-delete=")

        self.login_as("matias.cavieres")
        response = self.client.get(listing)
        self.assertTrue(response.context["can_add"])
        self.assertContains(response, "Registrar atención")
        self.assertTrue(response.context["any_actions"])
        self.assertNotContains(response, "data-delete=")
        self.assertContains(self.client.get(detail), "Editar")

        self.login_as("admin")
        self.assertContains(self.client.get(listing), "data-delete=")
        self.assertContains(self.client.get(detail), "data-delete=")

    def test_delete_is_independent_from_change(self):
        user = self.make_user("solo.elimina", officer=self.officer("F-1004"))
        self.give_perm(user, "operations.view_activity")
        self.give_perm(user, "operations.delete_activity")
        self.client.force_login(user)
        activity = self.activity("María Pérez")
        self.assertEqual(self.client.get(reverse("core:actividades_update", args=[activity.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse("core:actividades_archive", args=[activity.pk])).status_code, 200)
        response = self.client.post(reverse("core:actividades_archive", args=[activity.pk]))
        self.assertRedirects(response, reverse("core:atencion"))
        activity.refresh_from_db()
        self.assertIsNotNone(activity.deleted_at)

    def test_delete_with_the_permission_still_respects_the_delegation(self):
        user = self.login_as("matias.quiroz")
        self.give_perm(user, "operations.delete_activity")
        activity = self.activity("María Pérez")
        url = reverse("core:actividades_archive", args=[activity.pk])
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(url).status_code, 404)
        activity.refresh_from_db()
        self.assertIsNone(activity.deleted_at)

    def test_the_menu_only_shows_what_each_role_may_open(self):
        for username, shown, hidden in (
            ("consulta1", {"Atención"}, {"Roles y permisos", "Control de usuarios", "Delegaciones"}),
            ("matias.cavieres", {"Atención"}, {"Roles y permisos", "Control de usuarios"}),
            ("admin", {"Roles y permisos", "Control de usuarios", "Delegaciones"}, set()),
        ):
            self.login_as(username)
            labels = self.menu_labels(self.client.get(reverse("core:dashboard")))
            with self.subTest(user=username):
                self.assertTrue(shown <= labels, labels)
                self.assertFalse(hidden & labels, labels)

    def test_the_seeded_roles_have_no_delete_permission(self):
        for group in Group.objects.filter(name__in=("Coordinación", "Jefatura", "Funcionario", "Verificador", "Consulta")):
            with self.subTest(role=group.name):
                self.assertFalse(group.permissions.filter(codename__startswith="delete_").exists())

    def test_consulta_only_has_view_permissions(self):
        consulta = Group.objects.get(name="Consulta")
        actions = {permission.codename.split("_", 1)[0] for permission in consulta.permissions.all()}
        self.assertEqual(actions, {"view"})

    def test_a_forbidden_response_uses_the_403_page(self):
        self.login_as("consulta1")
        response = self.client.get(reverse("core:actividades_create"))
        self.assertEqual(response.status_code, 403)
        self.assertTemplateUsed(response, "403.html")


class PermissionLabelsTests(PortalTestCase):
    def test_every_matrix_permission_exists_in_the_database(self):
        from core.roles import PERMISSION_MODULES, managed_permissions

        total = sum(len(modules) for _title, modules in PERMISSION_MODULES) * 4
        self.assertEqual(managed_permissions().count(), total)

    def test_permission_text_reads_in_spanish(self):
        from core.roles import permission_text

        permission = Permission.objects.get(codename="view_period", content_type__app_label="planning")
        self.assertEqual(permission_text(permission), "Ver · Períodos")
