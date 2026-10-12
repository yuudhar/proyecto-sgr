"""Pruebas de los mantenedores de Roles, Ítems y metas, Tipo de Atención y Sub Atención (Clases 7 y 8).

Cubren la matriz de permisos del rol, los códigos (ROL01, TA001, SA001, IT001), los nombres que no se repiten
aunque cambien las mayúsculas, la relación entre tipo y sub atención y las revisiones antes de eliminar.
"""

from django.contrib.auth.models import Group, Permission
from django.contrib.messages import get_messages
from django.urls import reverse

from core.models import AuditLog
from core.testing import PortalTestCase
from organization.models import Item, PositionItem
from planning.models import Goal


def perm_ids(*labels):
    """Ids de permisos escritos como "app.codename"."""
    ids = []
    for label in labels:
        app_label, codename = label.split(".")
        ids.append(Permission.objects.get(content_type__app_label=app_label, codename=codename).pk)
    return ids


class RoleCrudTests(PortalTestCase):
    def setUp(self):
        self.login_as("admin")

    def role_data(self, name="Operador de turno", *labels, **changes):
        data = {
            "name": name,
            "description": "Rol de prueba.",
            "scope": "own",
            "status": "active",
            "permissions": perm_ids(*labels),
        }
        data.update(changes)
        return data

    def test_only_who_has_group_permissions_opens_roles(self):
        for username in ("matias.cavieres", "jefatura1", "coordinacion1", "consulta1"):
            self.login_as(username)
            with self.subTest(user=username):
                self.assertEqual(self.client.get(reverse("core:roles_list")).status_code, 403)
                self.assertEqual(self.client.get(reverse("core:roles_create")).status_code, 403)

    def test_the_list_shows_code_scope_state_users_and_permissions(self):
        response = self.client.get(reverse("core:roles_list"))
        self.assertEqual(response.status_code, 200)
        rows = {row.cells[1].text: [cell.text for cell in row.cells] for row in response.context["rows"]}
        coordinacion = Group.objects.get(name="Coordinación")
        self.assertEqual(rows["Coordinación"][0], f"ROL{coordinacion.pk:02d}")
        self.assertEqual(rows["Coordinación"][2], "Todas las delegaciones")
        self.assertEqual(rows["Funcionario"][2], "Su delegación")
        self.assertEqual(rows["Funcionario"][3], "Activo")
        self.assertEqual(rows["Funcionario"][4], "2")  # matias.cavieres y matias.quiroz
        self.assertEqual(rows["Consulta"][5], str(Group.objects.get(name="Consulta").permissions.count()))

    def test_the_list_can_be_searched_by_code_and_name(self):
        url = reverse("core:roles_list")
        consulta = Group.objects.get(name="Consulta")
        found = self.client.get(url, {"q": f"rol{consulta.pk:02d}"}).context["rows"]
        self.assertEqual([row.cells[1].text for row in found], ["Consulta"])
        found = self.client.get(url, {"q": "coordinacion"}).context["rows"]
        self.assertEqual([row.cells[1].text for row in found], ["Coordinación"])

    def test_the_form_shows_the_permission_matrix(self):
        response = self.client.get(reverse("core:roles_create"))
        self.assertContains(response, "perm-table")
        for text in ("Ver", "Crear", "Editar", "Eliminar", "Períodos", "Roles y permisos", "Solo consulta"):
            self.assertContains(response, text)
        # una casilla por módulo y acción
        from core.roles import PERMISSION_MODULES

        modules = sum(len(items) for _title, items in PERMISSION_MODULES)
        self.assertContains(response, 'class="form-check-input perm-check"', count=modules * 4)

    def test_create_a_role_with_permissions_and_leave_a_trace(self):
        data = self.role_data("Operador de turno", "operations.view_activity", "operations.add_activity")
        response = self.client.post(reverse("core:roles_create"), data)
        role = Group.objects.get(name="Operador de turno")
        self.assertRedirects(response, reverse("core:roles_detail", args=[role.pk]))
        self.assertEqual(
            set(role.permissions.values_list("codename", flat=True)), {"view_activity", "add_activity"}
        )
        log = AuditLog.objects.get(event="Permisos del rol modificados", record_id=role.pk)
        self.assertIn("Crear · Actividades y atenciones", log.new_value)
        self.assertTrue(AuditLog.objects.filter(event="Registro creado", record_id=role.pk).exists())

    def test_a_role_cannot_create_edit_or_delete_without_seeing_the_module(self):
        response = self.client.post(
            reverse("core:roles_create"), self.role_data("Sin ver", "operations.add_activity")
        )
        self.assertEqual(response.status_code, 200)
        errors = response.context["form"].errors["permissions"]
        self.assertIn("Actividades y atenciones", " ".join(errors))
        self.assertFalse(Group.objects.filter(name="Sin ver").exists())

    def test_role_names_do_not_repeat_even_with_other_capitals(self):
        response = self.client.post(reverse("core:roles_create"), self.role_data("consulta", "operations.view_activity"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("name", response.context["form"].errors)
        self.assertEqual(Group.objects.filter(name__iexact="consulta").count(), 1)

    def test_a_system_role_keeps_its_name_but_its_permissions_can_change(self):
        consulta = Group.objects.get(name="Consulta")
        data = self.role_data(
            "Otro nombre", "operations.view_activity", "operations.view_followup", "planning.view_period"
        )
        response = self.client.post(reverse("core:roles_update", args=[consulta.pk]), data)
        self.assertRedirects(response, reverse("core:roles_detail", args=[consulta.pk]))
        consulta.refresh_from_db()
        self.assertEqual(consulta.name, "Consulta")  # las reglas de acceso lo buscan por su nombre
        self.assertEqual(
            set(consulta.permissions.values_list("codename", flat=True)),
            {"view_activity", "view_followup", "view_period"},
        )
        log = AuditLog.objects.get(event="Permisos del rol modificados", record_id=consulta.pk)
        self.assertIn("Ver · Períodos", log.new_value)
        self.assertIn("Quitados:", log.previous_value)
        self.assertIn("Ver · Agenda colectiva", log.previous_value)  # lo que tenía y ya no tiene

    def test_permissions_outside_the_matrix_are_kept_when_saving(self):
        role = Group.objects.create(name="Con permiso extra")
        extra = Permission.objects.get(codename="view_permission")
        role.permissions.add(extra, *perm_ids("operations.view_activity"))
        data = self.role_data("Con permiso extra", "operations.view_activity", "operations.view_followup")
        self.client.post(reverse("core:roles_update", args=[role.pk]), data)
        codenames = set(role.permissions.values_list("codename", flat=True))
        self.assertEqual(codenames, {"view_permission", "view_activity", "view_followup"})

    def test_the_detail_shows_the_permissions_the_role_has(self):
        consulta = Group.objects.get(name="Consulta")
        response = self.client.get(reverse("core:roles_detail", args=[consulta.pk]))
        panel = response.context["panel"]
        cells = {
            row["label"]: {cell["label"]: cell["granted"] for cell in row["cells"]}
            for section in panel["sections"]
            for row in section["rows"]
        }
        self.assertEqual(cells["Actividades y atenciones"], {"Ver": True, "Crear": False, "Editar": False, "Eliminar": False})
        self.assertEqual(cells["Períodos"], {"Ver": False, "Crear": False, "Editar": False, "Eliminar": False})
        self.assertEqual(panel["total"], consulta.permissions.count())
        self.assertContains(response, "Permisos del rol")
        self.assertContains(response, "Usuarios con este rol")
        self.assertContains(response, "consulta1")

    def test_a_role_without_users_is_deleted_for_real_after_the_confirmation(self):
        role = Group.objects.create(name="Temporal")
        url = reverse("core:roles_delete", args=[role.pk])
        page = self.client.get(url)
        self.assertContains(page, "Eliminar rol")
        self.assertContains(page, "se elimina definitivamente")
        response = self.client.post(url)
        self.assertRedirects(response, reverse("core:roles_list"))
        self.assertFalse(Group.objects.filter(pk=role.pk).exists())
        self.assertTrue(AuditLog.objects.filter(event="Registro eliminado", record_id=role.pk).exists())
        self.assertIn("eliminado", " ".join(str(m) for m in get_messages(response.wsgi_request)))

    def test_a_role_in_use_cannot_be_deleted(self):
        role = Group.objects.get(name="Consulta")  # lo tiene consulta1; además es del sistema
        custom = Group.objects.create(name="En uso")
        user = self.make_user("alguien", groups=["En uso"])
        self.assertEqual(user.groups.count(), 1)
        url = reverse("core:roles_delete", args=[custom.pk])
        self.assertContains(self.client.get(url), "No se puede eliminar")
        response = self.client.post(url)
        self.assertRedirects(response, reverse("core:roles_detail", args=[custom.pk]))
        self.assertTrue(Group.objects.filter(pk=custom.pk).exists())
        self.assertFalse(AuditLog.objects.filter(event="Registro eliminado").exists())
        messages = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertTrue(any("No se puede eliminar" in m and "1 usuario" in m for m in messages), messages)
        self.assertTrue(role.user_set.exists())

    def test_a_system_role_cannot_be_deleted(self):
        role = Group.objects.get(name="Jefatura")
        response = self.client.post(reverse("core:roles_delete", args=[role.pk]))
        self.assertRedirects(response, reverse("core:roles_detail", args=[role.pk]))
        self.assertTrue(Group.objects.filter(pk=role.pk).exists())

    def test_the_list_marks_what_cannot_be_deleted_so_the_alert_can_explain_it(self):
        Group.objects.create(name="Libre")
        response = self.client.get(reverse("core:roles_list"))
        blocked = {row.cells[1].text: row.delete_blocked for row in response.context["rows"]}
        self.assertTrue(blocked["Jefatura"])
        self.assertEqual(blocked["Libre"], "")
        self.assertContains(response, "data-delete-kind=\"remove\"")
        self.assertContains(response, "data-blocked=")

    def test_delete_needs_the_delete_group_permission(self):
        role = Group.objects.create(name="Temporal 2")
        user = self.make_user("gestor.roles")
        self.give_perm(user, "auth.view_group")
        self.give_perm(user, "auth.change_group")
        self.client.force_login(user)
        url = reverse("core:roles_delete", args=[role.pk])
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(url).status_code, 403)
        self.assertTrue(Group.objects.filter(pk=role.pk).exists())
        # Ver y editar sí, pero la ficha no ofrece Eliminar
        self.assertNotContains(self.client.get(reverse("core:roles_detail", args=[role.pk])), "data-delete=")

    def test_users_see_the_new_role_in_their_form(self):
        Group.objects.create(name="Rol nuevo")
        response = self.client.get(reverse("core:usuarios_create"))
        self.assertContains(response, "Rol nuevo")


class AttentionCatalogTests(PortalTestCase):
    def setUp(self):
        self.login_as("admin")
        self.social = Item.objects.get(name="Atención Social")
        self.visit = Item.objects.get(name="Visita Domiciliaria")
        self.phone = Item.objects.get(name="Seguimiento Telefónico")
        self.aid = Item.objects.get(name="Entrega de Ayudas Sociales")

    def names(self, response):
        return [row.cells[1].text for row in response.context["rows"]]

    def test_each_catalog_lists_its_own_items(self):
        types = self.client.get(reverse("core:tipos_de_atencion_list"))
        self.assertEqual(
            set(self.names(types)), {"Atención Social", "Entrega de Ayudas Sociales", "Coordinación Territorial"}
        )
        subs = self.client.get(reverse("core:sub_atenciones_list"))
        self.assertEqual(set(self.names(subs)), {"Visita Domiciliaria", "Seguimiento Telefónico"})
        everything = self.client.get(reverse("core:items_list"))
        self.assertEqual(len(self.names(everything)), 5)

    def test_codes_follow_the_prefix_of_each_catalog(self):
        types = self.client.get(reverse("core:tipos_de_atencion_list"))
        codes = {row.cells[1].text: row.cells[0].text for row in types.context["rows"]}
        self.assertEqual(codes["Atención Social"], f"TA{self.social.pk:03d}")
        subs = self.client.get(reverse("core:sub_atenciones_list"))
        codes = {row.cells[1].text: row.cells[0].text for row in subs.context["rows"]}
        self.assertEqual(codes["Visita Domiciliaria"], f"SA{self.visit.pk:03d}")
        items = self.client.get(reverse("core:items_list"))
        codes = {row.cells[1].text: row.cells[0].text for row in items.context["rows"]}
        self.assertEqual(codes["Atención Social"], f"IT{self.social.pk:03d}")

    def test_the_search_finds_by_code_name_and_parent(self):
        url = reverse("core:sub_atenciones_list")
        self.assertEqual(self.names(self.client.get(url, {"q": f"sa{self.visit.pk:03d}"})), ["Visita Domiciliaria"])
        self.assertEqual(self.names(self.client.get(url, {"q": "TELEFONICO"})), ["Seguimiento Telefónico"])
        found = self.names(self.client.get(url, {"q": "atencion social"}))  # el tipo asociado también se busca
        self.assertEqual(set(found), {"Visita Domiciliaria", "Seguimiento Telefónico"})

    def test_the_type_list_counts_its_active_sub_attentions(self):
        response = self.client.get(reverse("core:tipos_de_atencion_list"))
        totals = {row.cells[1].text: row.cells[4].text for row in response.context["rows"]}
        self.assertEqual(totals["Atención Social"], "2")
        self.assertEqual(totals["Entrega de Ayudas Sociales"], "0")

    def test_state_is_active_or_inactive_and_can_be_filtered(self):
        self.phone.deleted_at = self.phone.created_at
        self.phone.save()
        url = reverse("core:sub_atenciones_list")
        self.assertEqual(self.names(self.client.get(url)), ["Visita Domiciliaria"])
        inactive = self.client.get(url, {"estado": "inactivo"})
        self.assertEqual(self.names(inactive), ["Seguimiento Telefónico"])
        self.assertEqual(inactive.context["rows"][0].cells[-1].text, "Inactivo")
        active = self.client.get(url, {"estado": "activo"})
        self.assertEqual(active.context["rows"][0].cells[-1].text, "Activo")

    def test_create_a_type_and_a_sub_attention(self):
        response = self.client.post(
            reverse("core:tipos_de_atencion_create"), {"name": "Salud", "calculation_type": "quantitative"}
        )
        salud = Item.objects.get(name="Salud")
        self.assertIsNone(salud.parent_item)
        self.assertRedirects(response, reverse("core:tipos_de_atencion_detail", args=[salud.pk]))
        response = self.client.post(
            reverse("core:sub_atenciones_create"),
            {"name": "Consulta médica", "parent_item": salud.pk, "calculation_type": "quantitative"},
        )
        sub = Item.objects.get(name="Consulta médica")
        self.assertEqual(sub.parent_item, salud)
        self.assertRedirects(response, reverse("core:sub_atenciones_detail", args=[sub.pk]))
        self.assertContains(self.client.get(reverse("core:tipos_de_atencion_detail", args=[salud.pk])), "Consulta médica")

    def test_a_sub_attention_needs_a_type_and_the_type_must_be_a_type(self):
        url = reverse("core:sub_atenciones_create")
        response = self.client.post(url, {"name": "Sin tipo", "parent_item": "", "calculation_type": "quantitative"})
        self.assertIn("parent_item", response.context["form"].errors)
        # otra sub atención no puede ser el tipo asociado: ni siquiera se ofrece en la lista
        offered = {item.pk for item in response.context["form"].fields["parent_item"].queryset}
        self.assertNotIn(self.visit.pk, offered)
        response = self.client.post(
            url, {"name": "Mal padre", "parent_item": self.visit.pk, "calculation_type": "quantitative"}
        )
        self.assertIn("parent_item", response.context["form"].errors)
        self.assertFalse(Item.objects.filter(name__in=("Sin tipo", "Mal padre")).exists())

    def test_names_do_not_repeat_among_siblings_even_with_other_capitals(self):
        response = self.client.post(
            reverse("core:tipos_de_atencion_create"), {"name": "atención  SOCIAL", "calculation_type": "quantitative"}
        )
        self.assertIn("name", response.context["form"].errors)
        response = self.client.post(
            reverse("core:sub_atenciones_create"),
            {"name": "visita domiciliaria", "parent_item": self.social.pk, "calculation_type": "quantitative"},
        )
        self.assertIn("name", response.context["form"].errors)
        # el mismo nombre sí puede estar bajo otro tipo
        response = self.client.post(
            reverse("core:sub_atenciones_create"),
            {"name": "Visita Domiciliaria", "parent_item": self.aid.pk, "calculation_type": "quantitative"},
        )
        self.assertEqual(response.status_code, 302)

    def test_an_archived_name_is_reported_as_archived(self):
        self.phone.deleted_at = self.phone.created_at
        self.phone.save()
        response = self.client.post(
            reverse("core:sub_atenciones_create"),
            {"name": "Seguimiento telefónico", "parent_item": self.social.pk, "calculation_type": "quantitative"},
        )
        self.assertIn("archivado", " ".join(response.context["form"].errors["name"]))

    def test_the_sub_attention_form_only_offers_active_types(self):
        self.aid.deleted_at = self.aid.created_at
        self.aid.save()
        response = self.client.get(reverse("core:sub_atenciones_create"))
        offered = {item.name for item in response.context["form"].fields["parent_item"].queryset}
        self.assertEqual(offered, {"Atención Social", "Coordinación Territorial"})
        # y el filtro del listado ofrece solo tipos
        filters = {spec.name: [label for _value, label in spec.options] for spec in self.client.get(
            reverse("core:sub_atenciones_list")).context["filters"]}
        self.assertEqual(set(filters["parent_item"]), {"Atención Social", "Coordinación Territorial"})

    def test_a_type_with_active_sub_attentions_cannot_be_deleted(self):
        url = reverse("core:tipos_de_atencion_archive", args=[self.social.pk])
        page = self.client.get(url)
        self.assertContains(page, "No se puede eliminar")
        self.assertContains(page, "2 sub atenciones activas")
        response = self.client.post(url)
        self.assertRedirects(response, reverse("core:tipos_de_atencion_detail", args=[self.social.pk]))
        self.social.refresh_from_db()
        self.assertIsNone(self.social.deleted_at)
        messages = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertTrue(any("2 sub atenciones activas" in m for m in messages), messages)
        # la lista lo avisa antes de preguntar
        row = {row.cells[1].text: row for row in self.client.get(reverse("core:tipos_de_atencion_list")).context["rows"]}
        self.assertIn("2 sub atenciones activas", row["Atención Social"].archive_blocked)
        self.assertEqual(row["Coordinación Territorial"].archive_blocked, "")
        self.assertIn("meta activa", row["Entrega de Ayudas Sociales"].archive_blocked)

    def test_a_type_can_be_deleted_once_its_sub_attentions_are_inactive(self):
        # las metas de la sub atención se retiran primero (con una meta activa no se puede eliminar)
        Goal.objects.filter(item__in=(self.visit, self.phone)).update(deleted_at=self.visit.created_at)
        for sub in (self.visit, self.phone):
            self.assertEqual(self.client.post(reverse("core:sub_atenciones_archive", args=[sub.pk])).status_code, 302)
        self.visit.refresh_from_db()
        self.assertIsNotNone(self.visit.deleted_at)
        # mientras el tipo esté en un ítem de cargo tampoco se puede eliminar
        blocked = self.client.post(reverse("core:tipos_de_atencion_archive", args=[self.social.pk]))
        self.assertRedirects(blocked, reverse("core:tipos_de_atencion_detail", args=[self.social.pk]))
        PositionItem.objects.filter(item=self.social).update(deleted_at=self.visit.deleted_at)
        response = self.client.post(reverse("core:tipos_de_atencion_archive", args=[self.social.pk]))
        self.assertRedirects(response, reverse("core:tipos_de_atencion_list"))
        self.social.refresh_from_db()
        self.assertIsNotNone(self.social.deleted_at)

    def test_an_item_with_active_goals_cannot_be_deleted(self):
        goals = Goal.objects.filter(item=self.visit, deleted_at__isnull=True).count()
        self.assertGreater(goals, 0)
        response = self.client.post(reverse("core:sub_atenciones_archive", args=[self.visit.pk]))
        self.assertRedirects(response, reverse("core:sub_atenciones_detail", args=[self.visit.pk]))
        self.visit.refresh_from_db()
        self.assertIsNone(self.visit.deleted_at)
        self.assertIn("metas activas", " ".join(str(m) for m in get_messages(response.wsgi_request)))

    def test_a_sub_attention_cannot_be_restored_under_an_archived_type(self):
        self.client.post(reverse("core:sub_atenciones_archive", args=[self.phone.pk]))
        Item.objects.filter(pk=self.social.pk).update(deleted_at=self.phone.deleted_at or self.social.created_at)
        response = self.client.post(reverse("core:sub_atenciones_restore", args=[self.phone.pk]))
        self.phone.refresh_from_db()
        self.assertIsNotNone(self.phone.deleted_at)
        self.assertIn("archivado", " ".join(str(m) for m in get_messages(response.wsgi_request)))

    def test_an_item_with_history_cannot_change_its_type(self):
        data = {"name": "Visita Domiciliaria", "parent_item": self.aid.pk, "calculation_type": "qualitative"}
        response = self.client.post(reverse("core:sub_atenciones_update", args=[self.visit.pk]), data)
        self.assertEqual(response.status_code, 200)
        self.assertIn("atenciones registradas", " ".join(response.context["form"].errors["parent_item"]))
        self.visit.refresh_from_db()
        self.assertEqual(self.visit.parent_item, self.social)

    def test_a_type_with_sub_attentions_cannot_become_a_sub_attention(self):
        data = {"name": "Atención Social", "parent_item": self.aid.pk, "calculation_type": "qualitative"}
        response = self.client.post(reverse("core:items_update", args=[self.social.pk]), data)
        self.assertEqual(response.status_code, 200)
        self.assertIn("parent_item", response.context["form"].errors)

    def test_an_item_cannot_be_its_own_parent(self):
        response = self.client.get(reverse("core:items_update", args=[self.aid.pk]))
        offered = {item.pk for item in response.context["form"].fields["parent_item"].queryset}
        self.assertNotIn(self.aid.pk, offered)

    def test_the_detail_shows_class_state_and_sub_attentions(self):
        response = self.client.get(reverse("core:tipos_de_atencion_detail", args=[self.social.pk]))
        self.assertContains(response, "Tipo de atención")
        self.assertContains(response, "Activo")
        self.assertContains(response, "Visita Domiciliaria")
        response = self.client.get(reverse("core:sub_atenciones_detail", args=[self.visit.pk]))
        self.assertContains(response, "Sub atención")

    def test_roles_without_delete_see_no_delete_link_in_the_catalogs(self):
        self.login_as("coordinacion1")  # ve ítems pero no los elimina
        response = self.client.get(reverse("core:items_list"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "data-delete=")
        self.assertEqual(self.client.post(reverse("core:items_archive", args=[self.aid.pk])).status_code, 403)

    def test_the_catalogs_are_in_the_menu_for_who_can_see_them(self):
        labels = self.menu_labels(self.client.get(reverse("core:dashboard")))
        self.assertTrue({"Ítems y metas", "Tipos de Atención", "Sub Atención", "Roles y permisos"} <= labels, labels)
