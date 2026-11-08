import importlib
from django.apps import apps as django_apps
from django.contrib.auth.models import Group, User
from django.urls import reverse

from accounts.models import RoleProfile, UserProfile
from core.models import AuditLog
from core.roles import ROLES
from core.test_catalogs import perm_ids
from core.test_export import ExcelTestCase
from core.testing import PortalTestCase
from operations.models import Activity
from organization.models import Delegation, Item, Officer


class DelegationFieldsTests(ExcelTestCase):

    def setUp(self):
        self.login_as("admin")

    def data(self, **changes):
        data = {
            "name": "Delegación Centro",
            "address": "Av. Francisco de Aguirre 100",
            "commune": "La Serena",
            "managers": "",
            "scope": "Sector centro",
            "color": "#920000",
            "status": "active",
        }
        data.update(changes)
        return data

    def test_the_demo_delegations_come_with_address_and_commune(self):
        self.assertEqual((self.north.address, self.north.commune), ("Av. Cuatro Esquinas 1200", "La Serena"))
        self.assertEqual((self.south.address, self.south.commune), ("Av. Juan Bohón 850", "La Serena"))

    def test_the_list_shows_code_name_address_commune_and_state(self):
        response = self.client.get(reverse("core:delegaciones_list"))
        labels = [column.label for column in response.context["columns"]]
        self.assertEqual(labels[:4], ["Código", "Nombre", "Dirección", "Comuna"])
        self.assertEqual(labels[-1], "Estado")
        rows = {row.cells[1].text: [cell.text for cell in row.cells] for row in response.context["rows"]}
        north = rows["Delegación Norte"]
        self.assertEqual(north[0], f"DEL{self.north.pk:02d}")
        self.assertEqual(north[2:4], ["Av. Cuatro Esquinas 1200", "La Serena"])
        self.assertEqual(north[-1], "Activa")

    def test_the_search_finds_by_address_and_commune(self):
        url = reverse("core:delegaciones_list")

        def names(**params):
            return sorted(row.cells[1].text for row in self.client.get(url, params).context["rows"])

        self.assertEqual(names(q="cuatro esquinas"), ["Delegación Norte"])
        self.assertEqual(names(q="juan bohon"), ["Delegación Sur"])
        self.assertEqual(names(q="la serena"), ["Delegación Norte", "Delegación Sur"])

    def test_the_create_form_asks_for_both_fields_and_suggests_the_commune(self):
        response = self.client.get(reverse("core:delegaciones_create"))
        form = response.context["form"]
        self.assertTrue(form.fields["address"].required)
        self.assertTrue(form.fields["commune"].required)
        self.assertContains(response, 'value="La Serena"')
        self.assertContains(response, 'data-rule="commune"')
        self.assertContains(response, 'data-rule="label"')

    def test_create_a_delegation_with_address_and_commune(self):
        response = self.client.post(reverse("core:delegaciones_create"), self.data())
        created = Delegation.objects.get(name="Delegación Centro")
        self.assertRedirects(response, reverse("core:delegaciones_detail", args=[created.pk]))
        self.assertEqual((created.address, created.commune), ("Av. Francisco de Aguirre 100", "La Serena"))
        self.assertTrue(AuditLog.objects.filter(event="Registro creado", record_id=created.pk).exists())

    def test_address_and_commune_are_required(self):
        for field in ("address", "commune"):
            with self.subTest(field=field):
                response = self.client.post(reverse("core:delegaciones_create"), self.data(**{field: "   "}))
                self.assertEqual(response.status_code, 200)
                self.assertIn(field, response.context["form"].errors)
        self.assertFalse(Delegation.objects.filter(name="Delegación Centro").exists())

    def test_the_commune_only_takes_letters(self):
        for written in ("La Serena 2", "Coquimbo <b>", "1234"):
            with self.subTest(written=written):
                response = self.client.post(reverse("core:delegaciones_create"), self.data(commune=written))
                self.assertIn("commune", response.context["form"].errors)
        response = self.client.post(reverse("core:delegaciones_create"), self.data(commune="  La   Higuera "))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Delegation.objects.get(name="Delegación Centro").commune, "La Higuera")

    def test_the_address_rejects_angle_brackets_and_long_texts(self):
        response = self.client.post(reverse("core:delegaciones_create"), self.data(address="<script>1</script>"))
        self.assertIn("address", response.context["form"].errors)
        response = self.client.post(reverse("core:delegaciones_create"), self.data(address="a" * 201))
        self.assertIn("address", response.context["form"].errors)
        response = self.client.post(reverse("core:delegaciones_create"), self.data(address="  Av.   del Mar  1500 "))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Delegation.objects.get(name="Delegación Centro").address, "Av. del Mar 1500")

    def test_edit_changes_the_address_and_leaves_a_trace(self):
        data = self.data(
            name=self.north.name,
            managers=self.north.managers,
            scope=self.north.scope,
            color=self.north.color,
            address="Av. Nueva 55",
            commune=self.north.commune,
        )
        response = self.client.post(reverse("core:delegaciones_update", args=[self.north.pk]), data)
        self.assertEqual(response.status_code, 302)
        self.north.refresh_from_db()
        self.assertEqual(self.north.address, "Av. Nueva 55")
        log = AuditLog.objects.get(event="Registro modificado", affected_entity="Delegation", record_id=self.north.pk)
        self.assertIn("Dirección: Av. Cuatro Esquinas 1200", log.previous_value)
        self.assertIn("Dirección: Av. Nueva 55", log.new_value)

    def test_an_old_delegation_without_address_is_listed_and_asks_for_it_when_edited(self):
        old = Delegation.objects.create(name="Delegación Antigua")
        listing = self.client.get(reverse("core:delegaciones_list"))
        row = next(row for row in listing.context["rows"] if row.cells[1].text == "Delegación Antigua")
        self.assertEqual([row.cells[2].text, row.cells[3].text], ["", ""])
        data = self.data(name="Delegación Antigua", address="", commune="")
        response = self.client.post(reverse("core:delegaciones_update", args=[old.pk]), data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.context["form"].errors), {"address", "commune"})

    def test_the_detail_shows_address_and_commune(self):
        response = self.client.get(reverse("core:delegaciones_detail", args=[self.north.pk]))
        labels = [label for label, _cell in response.context["pairs"]]
        self.assertIn("Dirección", labels)
        self.assertIn("Comuna", labels)
        self.assertContains(response, "Av. Cuatro Esquinas 1200")

    def test_the_excel_file_has_address_and_commune(self):
        response = self.download("core:delegaciones_list")
        headers, _rows = self.table(self.sheet(response))
        self.assertEqual(headers[:4], ["Código", "Nombre", "Dirección", "Comuna"])
        self.assertEqual(self.column(response, "Dirección"), ["Av. Cuatro Esquinas 1200", "Av. Juan Bohón 850"])
        self.assertEqual(self.column(response, "Comuna"), ["La Serena", "La Serena"])


class ItemDescriptionTests(ExcelTestCase):

    def setUp(self):
        self.login_as("admin")
        self.social = Item.objects.get(name="Atención Social")
        self.visit = Item.objects.get(name="Visita Domiciliaria")

    def labels(self, name):
        return [column.label for column in self.client.get(reverse(name)).context["columns"]]

    def test_the_demo_items_have_a_description(self):
        for item in Item.objects.all():
            with self.subTest(item=item.name):
                self.assertTrue(item.description)

    def test_the_item_and_type_lists_show_the_description_but_sub_attention_does_not(self):
        self.assertEqual(self.labels("core:items_list")[:3], ["Código", "Nombre", "Descripción"])
        self.assertEqual(self.labels("core:tipos_de_atencion_list")[:3], ["Código", "Nombre", "Descripción"])
        self.assertNotIn("Descripción", self.labels("core:sub_atenciones_list"))
        row = next(
            row
            for row in self.client.get(reverse("core:tipos_de_atencion_list")).context["rows"]
            if row.cells[1].text == "Atención Social"
        )
        self.assertEqual(row.cells[2].text, self.social.description)

    def test_the_search_finds_by_description(self):
        for name in ("core:items_list", "core:tipos_de_atencion_list"):
            with self.subTest(list=name):
                rows = self.client.get(reverse(name), {"q": "apoyo social"}).context["rows"]
                self.assertEqual([row.cells[1].text for row in rows], ["Atención Social"])

    def test_create_a_type_with_a_description(self):
        response = self.client.post(
            reverse("core:tipos_de_atencion_create"),
            {"name": "Salud", "description": "Atención de salud para vecinos.", "calculation_type": "quantitative"},
        )
        salud = Item.objects.get(name="Salud")
        self.assertRedirects(response, reverse("core:tipos_de_atencion_detail", args=[salud.pk]))
        self.assertEqual(salud.description, "Atención de salud para vecinos.")
        self.assertContains(self.client.get(reverse("core:tipos_de_atencion_detail", args=[salud.pk])), "Atención de salud")

    def test_the_description_is_optional(self):
        response = self.client.post(
            reverse("core:tipos_de_atencion_create"), {"name": "Sin texto", "calculation_type": "quantitative"}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Item.objects.get(name="Sin texto").description, "")

    def test_the_description_has_a_limit_and_no_angle_brackets(self):
        url = reverse("core:tipos_de_atencion_create")
        base = {"name": "Prueba", "calculation_type": "quantitative"}
        response = self.client.post(url, {**base, "description": "x" * 256})
        self.assertIn("description", response.context["form"].errors)
        response = self.client.post(url, {**base, "description": "<b>negrita</b>"})
        self.assertIn("description", response.context["form"].errors)
        self.assertFalse(Item.objects.filter(name="Prueba").exists())

    def test_a_description_in_several_lines_is_saved_on_one_line(self):
        response = self.client.post(
            reverse("core:tipos_de_atencion_create"),
            {"name": "Dos líneas", "description": "Primera\r\n  Segunda ", "calculation_type": "quantitative"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Item.objects.get(name="Dos líneas").description, "Primera Segunda")

    def test_the_item_form_edits_the_description_of_any_item(self):
        data = {
            "name": self.visit.name,
            "description": "Visita al hogar.",
            "parent_item": self.social.pk,
            "calculation_type": self.visit.calculation_type,
        }
        response = self.client.post(reverse("core:items_update", args=[self.visit.pk]), data)
        self.assertEqual(response.status_code, 302)
        self.visit.refresh_from_db()
        self.assertEqual(self.visit.description, "Visita al hogar.")
        log = AuditLog.objects.get(event="Registro modificado", affected_entity="Item", record_id=self.visit.pk)
        self.assertIn("Descripción", log.new_value)

    def test_sub_attention_has_no_description_field(self):
        response = self.client.get(reverse("core:sub_atenciones_create"))
        self.assertNotIn("description", response.context["form"].fields)
        detail = self.client.get(reverse("core:sub_atenciones_detail", args=[self.visit.pk]))
        self.assertNotIn("Descripción", [label for label, _cell in detail.context["pairs"]])

    def test_the_excel_file_of_the_types_has_the_description(self):
        response = self.download("core:tipos_de_atencion_list")
        self.assertIn("Descripción", self.table(self.sheet(response))[0])
        self.assertIn(self.social.description, self.column(response, "Descripción"))


class RoleProfileTests(ExcelTestCase):

    def setUp(self):
        self.login_as("admin")

    def role_data(self, name="Auditor", *labels, **changes):
        data = {
            "name": name,
            "description": "Revisa lo que pasa en todas las delegaciones.",
            "scope": "all",
            "status": "active",
            "permissions": perm_ids(*(labels or ("operations.view_activity",))),
        }
        data.update(changes)
        return data

    def create_role(self, name="Auditor", **changes):
        response = self.client.post(reverse("core:roles_create"), self.role_data(name, **changes))
        self.assertEqual(response.status_code, 302, getattr(response, "context", None) and response.context["form"].errors)
        return Group.objects.get(name=name)

    def update(self, role, *labels, **changes):
        details = RoleProfile.objects.get(group=role)
        data = self.role_data(role.name, *labels)
        data.update(description=details.description, scope=details.scope, status=details.status)
        data.update(changes)
        return self.client.post(reverse("core:roles_update", args=[role.pk]), data)


    def test_every_group_gets_its_profile_when_it_is_created(self):
        role = Group.objects.create(name="Equipo nuevo")
        profile = RoleProfile.objects.get(group=role)
        self.assertEqual((profile.description, profile.scope, profile.status), ("", "own", "active"))

    def test_the_system_roles_come_with_their_own_description_and_scope(self):
        for name, (_icon, description) in ROLES.items():
            if name not in ("Super Usuario",):
                profile = RoleProfile.objects.get(group__name=name)
                with self.subTest(role=name):
                    self.assertEqual(profile.description, description)
                    self.assertEqual(profile.scope, "all" if name == "Coordinación" else "own")
                    self.assertEqual(profile.status, "active")

    def test_the_migration_gives_a_profile_to_the_roles_that_already_existed(self):
        migration = importlib.import_module("accounts.migrations.0003_create_role_profiles")
        Group.objects.create(name="Antiguo")
        RoleProfile.objects.all().delete()
        migration.create_profiles(django_apps, None)
        self.assertEqual(RoleProfile.objects.count(), Group.objects.count())
        self.assertEqual(RoleProfile.objects.get(group__name="Coordinación").scope, "all")
        self.assertEqual(RoleProfile.objects.get(group__name="Consulta").scope, "own")
        self.assertEqual(RoleProfile.objects.get(group__name="Antiguo").description, "")

    def test_deleting_a_role_deletes_its_profile(self):
        role = Group.objects.create(name="Temporal A1")
        self.client.post(reverse("core:roles_delete", args=[role.pk]))
        self.assertFalse(RoleProfile.objects.filter(group_id=role.pk).exists())


    def test_the_list_shows_code_name_scope_state_users_and_permissions(self):
        response = self.client.get(reverse("core:roles_list"))
        self.assertEqual(
            [column.label for column in response.context["columns"]],
            ["Código", "Rol", "Alcance", "Estado", "Usuarios", "Permisos"],
        )
        rows = {row.cells[1].text: [cell.text for cell in row.cells] for row in response.context["rows"]}
        self.assertEqual(rows["Coordinación"][2:4], ["Todas las delegaciones", "Activo"])
        self.assertEqual(rows["Jefatura"][2:4], ["Su delegación", "Activo"])

    def test_the_list_filters_by_state_and_by_scope(self):
        auditor = self.create_role("Auditor")
        RoleProfile.objects.filter(group=auditor).update(status="inactive")
        url = reverse("core:roles_list")

        def names(**params):
            return sorted(row.cells[1].text for row in self.client.get(url, params).context["rows"])

        self.assertEqual(names(role_profile__status="inactive"), ["Auditor"])
        self.assertNotIn("Auditor", names(role_profile__status="active"))
        self.assertEqual(names(role_profile__scope="all"), ["Auditor", "Coordinación"])
        self.assertEqual(names(role_profile__scope="all", role_profile__status="active"), ["Coordinación"])
        filters = {spec.label: spec for spec in self.client.get(url).context["filters"]}
        self.assertEqual(set(filters), {"Estado", "Alcance autorizado"})
        self.assertEqual([label for _value, label in filters["Estado"].options], ["Activo", "Inactivo"])

    def test_the_search_finds_by_description(self):
        rows = self.client.get(reverse("core:roles_list"), {"q": "revisa las evidencias"}).context["rows"]
        self.assertEqual([row.cells[1].text for row in rows], ["Verificador"])

    def test_the_list_sorts_by_scope(self):
        url = reverse("core:roles_list")
        ascending = [row.cells[1].text for row in self.client.get(url, {"orden": "role_profile__scope"}).context["rows"]]
        self.assertEqual(ascending[0], "Coordinación")
        descending = [
            row.cells[1].text
            for row in self.client.get(url, {"orden": "role_profile__scope", "dir": "desc"}).context["rows"]
        ]
        self.assertEqual(descending[-1], "Coordinación")

    def test_the_excel_file_has_scope_and_state(self):
        response = self.download("core:roles_list")
        self.assertEqual(self.table(self.sheet(response))[0], ["Código", "Rol", "Alcance", "Estado", "Usuarios", "Permisos"])
        self.assertIn("Todas las delegaciones", self.column(response, "Alcance"))
        self.assertEqual(set(self.column(response, "Estado")), {"Activo"})


    def test_the_form_has_name_description_scope_state_and_permissions(self):
        response = self.client.get(reverse("core:roles_create"))
        form = response.context["form"]
        self.assertEqual(list(form.fields), ["name", "description", "scope", "status", "permissions"])
        self.assertEqual([label for _value, label in form.fields["scope"].choices], ["Su delegación", "Todas las delegaciones"])
        self.assertEqual([label for _value, label in form.fields["status"].choices], ["Activo", "Inactivo"])
        for text in ("Descripción", "Alcance autorizado", "Estado", "Permisos"):
            self.assertContains(response, text)

    def test_create_a_role_with_description_scope_and_state(self):
        role = self.create_role("Auditor", scope="all", status="active", description="Mira todo.")
        profile = RoleProfile.objects.get(group=role)
        self.assertEqual((profile.description, profile.scope, profile.status), ("Mira todo.", "all", "active"))
        self.assertTrue(AuditLog.objects.filter(event="Registro creado", record_id=role.pk).exists())

    def test_the_description_is_required_and_the_choices_must_be_valid(self):
        url = reverse("core:roles_create")
        response = self.client.post(url, self.role_data(description="  "))
        self.assertIn("description", response.context["form"].errors)
        response = self.client.post(url, self.role_data(scope="todas"))
        self.assertIn("scope", response.context["form"].errors)
        response = self.client.post(url, self.role_data(status="archivado"))
        self.assertIn("status", response.context["form"].errors)
        response = self.client.post(url, self.role_data(description="<i>x</i>"))
        self.assertIn("description", response.context["form"].errors)
        response = self.client.post(url, self.role_data(description="x" * 256))
        self.assertIn("description", response.context["form"].errors)
        self.assertFalse(Group.objects.filter(name="Auditor").exists())

    def test_editing_the_profile_of_a_role_leaves_a_trace(self):
        role = self.create_role("Auditor")
        response = self.update(role, "operations.view_activity", description="Otra descripción.", scope="own")
        self.assertEqual(response.status_code, 302)
        profile = RoleProfile.objects.get(group=role)
        self.assertEqual((profile.description, profile.scope), ("Otra descripción.", "own"))
        log = AuditLog.objects.get(event="Datos del rol modificados", affected_entity="Group", record_id=role.pk)
        self.assertIn("Alcance: Todas las delegaciones", log.previous_value)
        self.assertIn("Alcance: Su delegación", log.new_value)
        self.assertIn("Descripción: Otra descripción.", log.new_value)

    def test_saving_without_changing_the_profile_leaves_no_trace(self):
        role = self.create_role("Auditor")
        self.update(role, "operations.view_activity")
        self.assertFalse(AuditLog.objects.filter(event="Datos del rol modificados").exists())

    def test_a_system_role_keeps_its_scope_and_state_but_its_description_can_change(self):
        consulta = Group.objects.get(name="Consulta")
        data = self.role_data(
            "Consulta", "operations.view_activity", description="Solo mira.", scope="all", status="inactive"
        )
        response = self.client.post(reverse("core:roles_update", args=[consulta.pk]), data)
        self.assertEqual(response.status_code, 302)
        profile = RoleProfile.objects.get(group=consulta)
        self.assertEqual((profile.description, profile.scope, profile.status), ("Solo mira.", "own", "active"))
        form = self.client.get(reverse("core:roles_update", args=[consulta.pk])).context["form"]
        self.assertTrue(form.fields["scope"].disabled)
        self.assertTrue(form.fields["status"].disabled)
        self.assertFalse(form.fields["description"].disabled)


    def test_a_role_with_users_cannot_be_deactivated(self):
        role = self.create_role("Auditor", scope="own")
        self.make_user("auditor1", groups=["Auditor"], officer=self.officer("F-1004"))
        response = self.update(role, "operations.view_activity", status="inactive")
        self.assertEqual(response.status_code, 200)
        self.assertIn("1 usuario", " ".join(response.context["form"].errors["status"]))
        self.assertEqual(RoleProfile.objects.get(group=role).status, "active")

    def test_a_role_without_users_can_be_deactivated_and_is_not_offered_to_users(self):
        role = self.create_role("Auditor")
        self.assertEqual(self.update(role, "operations.view_activity", status="inactive").status_code, 302)
        self.assertEqual(RoleProfile.objects.get(group=role).status, "inactive")
        form = self.client.get(reverse("core:usuarios_create")).context["form"]
        offered = {group.name for group in form.fields["groups"].queryset}
        self.assertNotIn("Auditor", offered)
        self.assertIn("Funcionario", offered)

    def test_an_inactive_role_is_not_accepted_for_a_new_user(self):
        role = self.create_role("Auditor")
        self.update(role, "operations.view_activity", status="inactive")
        data = {
            "username": "ana.torres",
            "first_name": "Ana",
            "last_name": "Torres",
            "email": "ana.torres@dominio.cl",
            "groups": [role.pk],
            "officer": self.officer("F-1004").pk,
            "is_active": "on",
            "password1": "ClaveSegura#2026",
            "password2": "ClaveSegura#2026",
        }
        response = self.client.post(reverse("core:usuarios_create"), data)
        self.assertIn("groups", response.context["form"].errors)
        self.assertFalse(User.objects.filter(username="ana.torres").exists())

    def test_a_user_keeps_seeing_the_role_it_already_has_even_if_it_became_inactive(self):
        role = self.create_role("Auditor", scope="own")
        user = self.make_user("auditor1", groups=["Auditor"], officer=self.officer("F-1004"))
        RoleProfile.objects.filter(group=role).update(status="inactive")
        form = self.client.get(reverse("core:usuarios_update", args=[user.pk])).context["form"]
        self.assertIn(role.pk, {group.pk for group in form.fields["groups"].queryset})


    def test_a_global_role_cannot_be_limited_if_a_user_would_have_no_delegation(self):
        role = self.create_role("Auditor", scope="all")
        self.make_user("sin.funcionario", groups=["Auditor"])
        response = self.update(role, "operations.view_activity", scope="own")
        self.assertEqual(response.status_code, 200)
        message = " ".join(response.context["form"].errors["scope"])
        self.assertIn("sin.funcionario", message)
        self.assertEqual(RoleProfile.objects.get(group=role).scope, "all")

    def test_a_global_role_can_be_limited_when_its_users_have_an_officer_or_another_global_role(self):
        role = self.create_role("Auditor", scope="all")
        self.make_user("con.funcionario", groups=["Auditor"], officer=self.officer("F-1004"))
        other = self.make_user("con.otro.rol", groups=["Auditor", "Coordinación"])
        self.assertTrue(other.groups.filter(name="Coordinación").exists())
        self.assertEqual(self.update(role, "operations.view_activity", scope="own").status_code, 302)
        self.assertEqual(RoleProfile.objects.get(group=role).scope, "own")


    def test_the_detail_shows_description_scope_state_and_kind(self):
        role = self.create_role("Auditor", description="Mira todo.")
        response = self.client.get(reverse("core:roles_detail", args=[role.pk]))
        pairs = dict(response.context["pairs"])
        self.assertEqual(pairs["Descripción"].text, "Mira todo.")
        self.assertEqual(pairs["Alcance autorizado"].text, "Todas las delegaciones")
        self.assertEqual(pairs["Estado"].text, "Activo")
        self.assertEqual(pairs["Tipo de rol"].text, "Rol propio")

    def test_the_user_form_shows_the_description_written_in_the_role(self):
        self.create_role("Auditor", description="Descripción propia del auditor.")
        response = self.client.get(reverse("core:usuarios_create"))
        self.assertContains(response, "Descripción propia del auditor.")
        self.assertContains(response, ROLES["Consulta"][1])


class GlobalRoleScopeTests(PortalTestCase):

    def setUp(self):
        self.role = Group.objects.create(name="Auditor")
        self.role.permissions.add(*perm_ids("operations.view_activity"))

    def set_role(self, **changes):
        RoleProfile.objects.filter(group=self.role).update(**changes)

    def total_visible(self, username, url_name="core:atencion"):
        self.login_as(username)
        response = self.client.get(reverse(url_name))
        return response.status_code, response.context["page"].paginator.count if response.status_code == 200 else None

    def test_a_role_with_all_delegations_sees_every_delegation_even_without_an_officer(self):
        self.set_role(scope="all")
        self.make_user("auditor1", groups=["Auditor"])
        status, total = self.total_visible("auditor1")
        self.assertEqual(status, 200)
        self.assertEqual(total, Activity.objects.filter(deleted_at__isnull=True).count())

    def test_a_role_with_its_own_delegation_only_sees_that_one(self):
        self.set_role(scope="own")
        self.make_user("auditor1", groups=["Auditor"], officer=self.officer("F-1004"))
        status, total = self.total_visible("auditor1")
        self.assertEqual(status, 200)
        self.assertEqual(total, Activity.objects.filter(deleted_at__isnull=True, delegation=self.north).count())

    def test_a_role_with_its_own_delegation_and_no_officer_gets_a_403(self):
        self.set_role(scope="own")
        self.make_user("auditor1", groups=["Auditor"])
        self.assertEqual(self.total_visible("auditor1")[0], 403)

    def test_an_inactive_role_does_not_give_the_wider_scope(self):
        self.set_role(scope="all", status="inactive")
        self.make_user("auditor1", groups=["Auditor"], officer=self.officer("F-1004"))
        status, total = self.total_visible("auditor1")
        self.assertEqual(status, 200)
        self.assertEqual(total, Activity.objects.filter(deleted_at__isnull=True, delegation=self.north).count())

    def test_coordinacion_without_a_profile_is_still_recognised_by_its_name(self):
        RoleProfile.objects.filter(group__name="Coordinación").delete()
        status, total = self.total_visible("coordinacion1", "core:funcionarios_list")
        self.assertEqual(status, 200)
        self.assertEqual(total, Officer.objects.filter(deleted_at__isnull=True).count())

    def test_the_django_admin_follows_the_same_scope(self):
        everything = Activity.objects.filter(deleted_at__isnull=True).count()
        only_north = Activity.objects.filter(deleted_at__isnull=True, delegation=self.north).count()
        self.assertGreater(everything, only_north)
        self.set_role(scope="all")
        user = self.make_user("auditor1", groups=["Auditor"], officer=self.officer("F-1004"))
        user.is_staff = True
        user.save()
        self.login_as("auditor1")
        url = reverse("admin:operations_activity_changelist")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["cl"].result_count, everything)
        self.set_role(scope="own")
        response = self.client.get(url)
        self.assertEqual(response.context["cl"].result_count, only_north)

    def test_the_scope_shown_in_the_header_follows_the_role(self):
        self.set_role(scope="all")
        self.make_user("auditor1", groups=["Auditor"])
        self.login_as("auditor1")
        response = self.client.get(reverse("core:dashboard"))
        self.assertTrue(response.context["me_scope"]["all"])

    def test_the_user_form_lets_a_global_role_go_without_officer_and_asks_for_it_otherwise(self):
        self.login_as("admin")
        data = {
            "username": "ana.torres",
            "first_name": "Ana",
            "last_name": "Torres",
            "email": "ana.torres@dominio.cl",
            "groups": [self.role.pk],
            "officer": "",
            "is_active": "on",
            "password1": "ClaveSegura#2026",
            "password2": "ClaveSegura#2026",
        }
        self.set_role(scope="own")
        response = self.client.post(reverse("core:usuarios_create"), data)
        self.assertIn("officer", response.context["form"].errors)
        self.set_role(scope="all")
        response = self.client.post(reverse("core:usuarios_create"), data)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(username="ana.torres").exists())

    def test_the_user_list_says_all_delegations_for_a_global_role(self):
        self.set_role(scope="all")
        user = self.make_user("auditor1", groups=["Auditor"])
        self.assertFalse(UserProfile.objects.filter(user=user).exists())
        self.login_as("admin")
        rows = self.client.get(reverse("core:usuarios_list"), {"q": "auditor1"}).context["rows"]
        self.assertEqual([row.cells[4].text for row in rows], ["Todas las delegaciones"])
