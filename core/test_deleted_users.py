from django.contrib.auth.models import User
from django.urls import reverse

from accounts.models import UserProfile
from core.models import AuditLog
from core.testing import PASSWORD, PortalTestCase


def usernames(response):
    return [row.obj.username for row in response.context["rows"]]


class DeletedUsersTests(PortalTestCase):

    def setUp(self):
        self.admin = self.login_as("admin")
        self.target = self.make_user("para.eliminar")
        self.target.email = "para.eliminar@example.cl"
        self.target.save()
        self.list_url = reverse("core:usuarios_list")
        self.archive_url = reverse("core:usuarios_archive", args=[self.target.pk])

    def delete_target(self):
        return self.client.post(self.archive_url)

    def test_deleting_a_user_moves_it_to_the_deleted_users_place(self):
        response = self.delete_target()
        self.assertRedirects(response, self.list_url, fetch_redirect_response=False)
        self.target.refresh_from_db()
        self.assertFalse(self.target.is_active)
        self.assertIsNotNone(self.target.profile.deleted_at)
        self.assertEqual(self.target.profile.status, UserProfile.Status.INACTIVE)
        self.assertTrue(User.objects.filter(pk=self.target.pk).exists())
        self.assertTrue(AuditLog.objects.filter(event="Registro archivado", record_id=self.target.pk).exists())

    def test_a_deleted_user_leaves_the_normal_list_and_appears_in_the_deleted_one(self):
        self.delete_target()
        normal = self.client.get(self.list_url, {"q": "para.eliminar"})
        self.assertEqual(usernames(normal), [])
        self.assertNotIn("para.eliminar", self.client.get(self.list_url).content.decode())
        deleted = self.client.get(self.list_url, {"archivados": "solo"})
        self.assertEqual(usernames(deleted), ["para.eliminar"])
        self.assertContains(deleted, "Usuarios eliminados")
        self.assertContains(deleted, "Restaurar")
        self.assertNotContains(deleted, "Nuevo usuario")
        searched = self.client.get(self.list_url, {"archivados": "solo", "q": "inexistente"})
        self.assertEqual(usernames(searched), [])

    def test_the_normal_list_links_to_the_deleted_users(self):
        page = self.client.get(self.list_url)
        self.assertContains(page, "archivados=solo")
        self.assertContains(page, "Usuarios eliminados")
        back = self.client.get(self.list_url, {"archivados": "solo"})
        self.assertContains(back, "Volver a usuarios")

    def test_a_deleted_user_cannot_sign_in(self):
        self.delete_target()
        self.client.logout()
        self.assertFalse(self.client.login(username="para.eliminar", password=PASSWORD))

    def test_a_deleted_user_is_restored_but_stays_inactive(self):
        self.delete_target()
        response = self.client.post(reverse("core:usuarios_restore", args=[self.target.pk]), follow=True)
        self.assertContains(response, "Sigue inactivo")
        self.target.refresh_from_db()
        self.assertIsNone(self.target.profile.deleted_at)
        self.assertFalse(self.target.is_active)
        self.assertIn("para.eliminar", usernames(self.client.get(self.list_url, {"q": "para.eliminar"})))
        self.assertEqual(usernames(self.client.get(self.list_url, {"archivados": "solo"})), [])
        self.assertTrue(AuditLog.objects.filter(event="Registro restaurado", record_id=self.target.pk).exists())

    def test_the_confirmation_page_explains_where_the_user_goes(self):
        page = self.client.get(self.archive_url)
        self.assertContains(page, "Usuarios eliminados")
        self.assertContains(page, "Sí, eliminar")
        self.assertTrue(User.objects.get(pk=self.target.pk).is_active)

    def test_a_deleted_user_cannot_be_edited(self):
        self.delete_target()
        update = reverse("core:usuarios_update", args=[self.target.pk])
        self.assertRedirects(self.client.get(update), reverse("core:usuarios_detail", args=[self.target.pk]), fetch_redirect_response=False)
        self.assertEqual(self.client.post(update, {"username": "otro"}).status_code, 403)
        detail = self.client.get(reverse("core:usuarios_detail", args=[self.target.pk]))
        self.assertContains(detail, "Este usuario está eliminado")
        self.assertContains(detail, "Eliminado el")

    def test_a_user_without_a_profile_can_also_be_deleted(self):
        bare = User.objects.create_user("sin.perfil", password=PASSWORD)
        self.assertFalse(UserProfile.objects.filter(user=bare).exists())
        self.client.post(reverse("core:usuarios_archive", args=[bare.pk]))
        bare.refresh_from_db()
        self.assertFalse(bare.is_active)
        self.assertIsNotNone(bare.profile.deleted_at)
        self.assertEqual(usernames(self.client.get(self.list_url, {"archivados": "solo", "q": "sin.perfil"})), ["sin.perfil"])

    def test_you_cannot_delete_your_own_account(self):
        own = reverse("core:usuarios_archive", args=[self.admin.pk])
        page = self.client.get(own)
        self.assertContains(page, "No puedes eliminar tu propia cuenta.")
        response = self.client.post(own, follow=True)
        self.assertContains(response, "No puedes eliminar tu propia cuenta.")
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)
        self.assertIn("admin", usernames(self.client.get(self.list_url, {"q": "admin"})))

    def test_the_list_row_shows_a_delete_button_that_explains_the_own_account_block(self):
        page = self.client.get(self.list_url, {"q": "admin"}).content.decode()
        self.assertIn('data-delete-kind="archive"', page)
        self.assertIn('data-blocked="No puedes eliminar tu propia cuenta."', page)
        self.assertNotIn("data-delete-label", page)


class OnlySuperuserDeletesUsersTests(PortalTestCase):

    def setUp(self):
        self.target = self.make_user("objetivo")
        self.deleted = self.make_user("ya.eliminado")
        self.login_as("admin")
        self.client.post(reverse("core:usuarios_archive", args=[self.deleted.pk]))
        self.client.logout()
        self.manager = self.make_user("gestor.usuarios")
        for label in ("auth.view_user", "auth.add_user", "auth.change_user", "auth.delete_user"):
            self.give_perm(self.manager, label)
        self.client.force_login(self.manager)
        self.list_url = reverse("core:usuarios_list")

    def test_a_manager_with_the_delete_permission_cannot_delete_users(self):
        archive = reverse("core:usuarios_archive", args=[self.target.pk])
        self.assertEqual(self.client.get(archive).status_code, 403)
        self.assertEqual(self.client.post(archive).status_code, 403)
        self.target.refresh_from_db()
        self.assertTrue(self.target.is_active)
        self.assertFalse(UserProfile.objects.filter(user=self.target, deleted_at__isnull=False).exists())

    def test_a_manager_cannot_restore_users(self):
        restore = reverse("core:usuarios_restore", args=[self.deleted.pk])
        self.assertIn(self.client.post(restore).status_code, (403, 404))
        self.deleted.refresh_from_db()
        self.assertIsNotNone(self.deleted.profile.deleted_at)

    def test_a_manager_sees_no_delete_button_and_no_deleted_users_place(self):
        page = self.client.get(self.list_url, {"q": "objetivo"})
        html = page.content.decode()
        self.assertNotIn("data-delete", html)
        self.assertNotIn("archivados=solo", html)
        self.assertNotContains(page, "Usuarios eliminados")
        detail = self.client.get(reverse("core:usuarios_detail", args=[self.target.pk]))
        self.assertNotIn("data-delete", detail.content.decode())

    def test_a_manager_never_sees_the_deleted_users(self):
        self.assertNotIn("ya.eliminado", usernames(self.client.get(self.list_url, {"q": "ya.eliminado"})))
        for params in ({"archivados": "solo"}, {"archivados": "1"}, {"estado": "inactivo"}):
            with self.subTest(params=params):
                self.assertNotIn("ya.eliminado", usernames(self.client.get(self.list_url, params)))
        self.assertEqual(self.client.get(reverse("core:usuarios_detail", args=[self.deleted.pk])).status_code, 404)

    def test_the_superuser_does_see_and_restore_them(self):
        self.client.force_login(User.objects.get(username="admin"))
        self.assertEqual(usernames(self.client.get(self.list_url, {"archivados": "solo"})), ["ya.eliminado"])
        self.client.post(reverse("core:usuarios_restore", args=[self.deleted.pk]))
        self.deleted.refresh_from_db()
        self.assertIsNone(self.deleted.profile.deleted_at)
