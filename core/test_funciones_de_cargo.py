"""Versión 44: funciones de cada cargo según el descriptor 2026 (RF-050), en la ficha personal."""
from io import StringIO

from django.contrib.auth.models import Group, Permission
from django.core.management import call_command
from django.urls import reverse

from core.crud import version_of
from core.duties import duties_of
from core.testing import PortalTestCase
from organization.descriptor import DESCRIPTOR
from organization.models import Position, PositionFunction
from websocket.signals import LIVE_MODELS


def load():
    out = StringIO()
    call_command("cargar_funciones_cargos", stdout=out)
    return out.getvalue()


def make_function(position, text, order=1, group="", **changes):
    return PositionFunction.objects.create(position=position, order=order, group=group, text=text, **changes)


class DescriptorDataTests(PortalTestCase):
    """El texto del descriptor cabe en los campos y no lleva símbolos que el sistema rechaza."""

    def test_the_descriptor_has_the_seven_positions(self):
        self.assertEqual(
            [c["name"] for c in DESCRIPTOR],
            [
                "Delegado",
                "Gestor Social",
                "Apoyo Administrativo",
                "Organizaciones Comunitarias",
                "Gestor de Compras y Proyectos",
                "Gestión y Planificación",
                "Coordinador de Servicios Comunitarios",
            ],
        )

    def test_every_text_fits_its_field_and_has_no_forbidden_symbols(self):
        for cargo in DESCRIPTOR:
            self.assertLessEqual(len(cargo["description"]), 500, cargo["name"])
            self.assertTrue(cargo["functions"], cargo["name"])
            for group, text in cargo["functions"]:
                self.assertLessEqual(len(text), PositionFunction.MAX_LENGTH, text[:40])
                self.assertLessEqual(len(group), 100)
                self.assertNotIn("<", text + group)
                self.assertNotIn(">", text + group)


class DescriptorLoadTests(PortalTestCase):
    """El comando carga los cargos del descriptor y se puede repetir sin duplicar ni pisar lo editado."""

    def test_it_loads_the_seven_positions_with_description_and_functions(self):
        out = load()
        self.assertIn("7 cargos revisados, 7 creados", out)
        for cargo in DESCRIPTOR:
            position = Position.objects.get(name=cargo["name"])
            self.assertEqual(position.description, cargo["description"])
            self.assertEqual(position.functions.count(), len(cargo["functions"]))
            self.assertEqual(str(position.valid_from), "2026-01-01")

    def test_running_it_twice_changes_nothing(self):
        load()
        positions, functions = Position.objects.count(), PositionFunction.objects.count()
        out = load()
        self.assertEqual((Position.objects.count(), PositionFunction.objects.count()), (positions, functions))
        self.assertIn("0 creados", out)
        self.assertIn("0 funciones nuevas", out)

    def test_the_numbering_restarts_inside_each_group(self):
        load()
        social = Position.objects.get(name="Gestor Social")
        groups = list(social.functions.order_by("id").values_list("group", "order"))
        self.assertEqual([order for group, order in groups if group == "Atención de casos"], [1, 2, 3, 4, 5])
        self.assertEqual([order for group, order in groups if group == "Acciones comunitarias"], [1, 2, 3, 4])
        self.assertEqual(len({group for group, order in groups}), 4)

    def test_an_existing_position_is_reused_and_keeps_its_description(self):
        existing = Position.objects.create(name="gestor social", valid_from="2025-03-01", description="La de siempre")
        load()
        self.assertEqual(Position.objects.filter(name__iexact="Gestor Social").count(), 1)
        existing.refresh_from_db()
        self.assertEqual(existing.description, "La de siempre")
        self.assertEqual(existing.functions.count(), 15)

    def test_an_edited_function_keeps_its_text_and_the_original_comes_back_once(self):
        load()
        function = PositionFunction.objects.filter(position__name="Delegado").order_by("id").first()
        function.text = "Texto corregido por la jefatura"
        function.save()
        load()
        function.refresh_from_db()
        self.assertEqual(function.text, "Texto corregido por la jefatura")
        # La función original se vuelve a cargar porque ya no existe con ese texto: solo una más, en el orden siguiente.
        self.assertEqual(PositionFunction.objects.filter(position__name="Delegado").count(), 12)

    def test_an_archived_function_is_not_loaded_again(self):
        load()
        function = PositionFunction.objects.filter(position__name="Delegado").order_by("id").first()
        PositionFunction.objects.filter(pk=function.pk).update(deleted_at=function.created_at)
        load()
        self.assertEqual(PositionFunction._base_manager.filter(position__name="Delegado").count(), 11)

    def test_the_demo_positions_are_left_alone(self):
        before = list(Position.objects.order_by("name").values_list("name", "description"))
        load()
        for name, description in before:
            self.assertEqual(Position.objects.get(name=name).description, description)


class DutiesTests(PortalTestCase):
    """duties_of arma lo que muestra la ficha: descripción y funciones agrupadas."""

    def test_no_position_gives_an_empty_answer(self):
        self.assertEqual(duties_of(None)["groups"], [])

    def test_functions_are_grouped_in_order_and_archived_ones_are_left_out(self):
        position = Position.objects.create(name="Cargo de Prueba", valid_from="2026-01-01", description="Hace cosas")
        make_function(position, "Segunda", order=2)
        make_function(position, "Primera", order=1)
        make_function(position, "Archivada", order=3, deleted_at=position.created_at)
        data = duties_of(position)
        self.assertEqual(data["description"], "Hace cosas")
        self.assertEqual(data["total"], 2)
        self.assertEqual([i["text"] for i in data["groups"][0]["items"]], ["Primera", "Segunda"])

    def test_grouped_functions_keep_their_titles(self):
        load()
        data = duties_of(Position.objects.get(name="Gestor Social"))
        self.assertEqual(
            [g["title"] for g in data["groups"]],
            ["Atención de casos", "Acciones comunitarias", "Acciones de coordinación y gestión", "Acciones de auto-mejora de desempeño"],
        )


class SheetTests(PortalTestCase):
    """La ficha personal del funcionario muestra las funciones de su cargo."""

    def setUp(self):
        load()
        self.officer_ = self.officer("F-1001")
        self.social = Position.objects.get(name="Gestor Social")
        self.officer_.position = self.social
        self.officer_.save()
        self.url = reverse("core:funcionarios_detail", args=[self.officer_.pk])

    def test_the_sheet_shows_the_description_and_the_functions_of_the_position(self):
        self.login_as("matias.cavieres")
        response = self.client.get(self.url)
        self.assertContains(response, "Funciones del cargo: Gestor Social")
        self.assertContains(response, "Atención de casos")
        self.assertContains(response, "Recepción y evaluación de casos.")
        self.assertContains(response, "promover el bienestar y la calidad de vida")
        self.assertContains(response, "descriptor de funciones 2026")

    def test_it_does_not_show_the_functions_of_other_positions(self):
        self.login_as("matias.cavieres")
        response = self.client.get(self.url)
        self.assertNotContains(response, "Llevar la agenda del delegado")

    def test_a_position_without_functions_says_so(self):
        self.officer_.position = Position.objects.exclude(functions__isnull=False).first()
        self.officer_.save()
        self.login_as("matias.cavieres")
        response = self.client.get(self.url)
        self.assertContains(response, "aún no tiene funciones registradas")

    def test_it_is_shown_even_without_permission_to_see_the_goals(self):
        other = self.officer("F-1002") if self.officer_.institutional_id != "F-1002" else self.officer("F-1003")
        user = self.make_user("solo.ficha", officer=other)
        self.give_perm(user, "organization.view_officer")
        self.client.force_login(user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Recepción y evaluación de casos.")

    def test_it_is_shown_together_with_the_goals_for_whoever_sees_them(self):
        self.login_as("jefatura1")
        response = self.client.get(self.url)
        self.assertContains(response, "Ficha del período")
        self.assertContains(response, "Funciones del cargo: Gestor Social")

    def test_the_text_is_escaped(self):
        make_function(self.social, "Revisar &amp; <b>negrita</b>", order=99)
        self.login_as("matias.cavieres")
        response = self.client.get(self.url)
        self.assertNotContains(response, "<b>negrita</b>")


class FunctionCrudTests(PortalTestCase):
    """Mantenedor de funciones de cargo."""

    def setUp(self):
        self.login_as("admin")
        self.position = Position.objects.create(name="Cargo de Prueba", valid_from="2026-01-01")

    def form(self, **changes):
        data = {"position": self.position.pk, "order": 1, "group": "", "text": "Atender a los vecinos."}
        data.update(changes)
        return data

    def test_the_menu_lists_funciones_de_cargo_next_to_cargos(self):
        response = self.client.get(reverse("core:funciones_de_cargo_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Funciones de cargos")

    def test_a_function_is_created(self):
        response = self.client.post(reverse("core:funciones_de_cargo_create"), self.form())
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.position.functions.get().text, "Atender a los vecinos.")

    def test_the_position_page_lists_its_functions_and_a_link_to_add(self):
        make_function(self.position, "Atender a los vecinos.")
        response = self.client.get(reverse("core:cargos_detail", args=[self.position.pk]))
        self.assertContains(response, "Funciones del cargo")
        self.assertContains(response, "Atender a los vecinos.")
        self.assertContains(response, f"{reverse('core:funciones_de_cargo_create')}?position={self.position.pk}")

    def test_the_position_form_has_the_description_and_saves_it(self):
        response = self.client.get(reverse("core:cargos_update", args=[self.position.pk]))
        self.assertContains(response, 'name="description"')
        response = self.client.post(
            reverse("core:cargos_update", args=[self.position.pk]),
            {"name": "Cargo de Prueba", "description": "Hace cosas útiles", "valid_from": "2026-01-01", "valid_until": "",
             "_version": version_of(self.position)},
        )
        self.assertEqual(response.status_code, 302)
        self.position.refresh_from_db()
        self.assertEqual(self.position.description, "Hace cosas útiles")

    def test_the_position_description_over_the_limit_is_refused(self):
        response = self.client.post(
            reverse("core:cargos_update", args=[self.position.pk]),
            {"name": "Cargo de Prueba", "description": "a" * 501, "valid_from": "2026-01-01", "valid_until": "",
             "_version": version_of(self.position)},
        )
        self.assertEqual(response.status_code, 200)
        self.position.refresh_from_db()
        self.assertEqual(self.position.description, "")

    def test_an_empty_text_is_refused(self):
        response = self.client.post(reverse("core:funciones_de_cargo_create"), self.form(text=""))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.position.functions.exists())

    def test_a_text_over_the_limit_is_refused(self):
        response = self.client.post(reverse("core:funciones_de_cargo_create"), self.form(text="a" * 601))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.position.functions.exists())

    def test_the_order_goes_from_1_to_99(self):
        for bad in (0, 100):
            response = self.client.post(reverse("core:funciones_de_cargo_create"), self.form(order=bad))
            self.assertEqual(response.status_code, 200, bad)
        self.assertFalse(self.position.functions.exists())

    def test_the_same_text_twice_in_one_position_is_refused(self):
        make_function(self.position, "Atender a los vecinos.")
        response = self.client.post(reverse("core:funciones_de_cargo_create"), self.form(text="atender a los vecinos.", order=2))
        self.assertContains(response, "ya tiene una función con ese mismo texto")
        self.assertEqual(self.position.functions.count(), 1)

    def test_the_same_text_in_another_position_is_fine(self):
        other = Position.objects.create(name="Otro Cargo", valid_from="2026-01-01")
        make_function(other, "Atender a los vecinos.")
        response = self.client.post(reverse("core:funciones_de_cargo_create"), self.form())
        self.assertEqual(response.status_code, 302)

    def test_a_function_is_archived_and_leaves_the_sheet(self):
        function = make_function(self.position, "Atender a los vecinos.")
        response = self.client.post(reverse("core:funciones_de_cargo_archive", args=[function.pk]))
        self.assertEqual(response.status_code, 302)
        function.refresh_from_db()
        self.assertIsNotNone(function.deleted_at)
        self.assertEqual(duties_of(self.position)["total"], 0)

    def test_a_function_of_an_archived_position_cannot_be_restored_first(self):
        function = make_function(self.position, "Atender a los vecinos.")
        PositionFunction.objects.filter(pk=function.pk).update(deleted_at=function.created_at)
        Position.objects.filter(pk=self.position.pk).update(deleted_at=function.created_at)
        response = self.client.post(reverse("core:funciones_de_cargo_restore", args=[function.pk]))
        function.refresh_from_db()
        self.assertIsNotNone(function.deleted_at)
        self.assertEqual(response.status_code, 302)

    def test_a_position_with_functions_cannot_be_deleted(self):
        make_function(self.position, "Atender a los vecinos.")
        self.client.post(reverse("core:cargos_delete", args=[self.position.pk]))
        self.assertTrue(Position.objects.filter(pk=self.position.pk).exists())


class FunctionPermissionTests(PortalTestCase):
    """Quién ve y quién cambia las funciones de cargo."""

    def setUp(self):
        self.position = Position.objects.create(name="Cargo de Prueba", valid_from="2026-01-01")

    def test_coordinacion_reads_but_does_not_change(self):
        self.login_as("coordinacion1")
        self.assertEqual(self.client.get(reverse("core:funciones_de_cargo_list")).status_code, 200)
        response = self.client.post(
            reverse("core:funciones_de_cargo_create"), {"position": self.position.pk, "order": 1, "group": "", "text": "x"}
        )
        self.assertEqual(response.status_code, 403)

    def test_the_other_roles_have_no_access_to_the_list(self):
        for username in ("matias.cavieres", "jefatura1", "consulta1"):
            self.login_as(username)
            self.assertEqual(self.client.get(reverse("core:funciones_de_cargo_list")).status_code, 403, username)

    def test_only_coordinacion_gets_the_view_permission(self):
        code = "organization.view_positionfunction"
        holders = [g.name for g in Group.objects.all() if g.permissions.filter(codename="view_positionfunction").exists()]
        self.assertEqual(holders, ["Coordinación"])
        self.assertTrue(Permission.objects.filter(codename="view_positionfunction").exists(), code)

    def test_it_needs_a_session(self):
        response = self.client.get(reverse("core:funciones_de_cargo_list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("next=", response.url)

    def test_the_roles_screen_lists_the_module(self):
        self.login_as("admin")
        group = Group.objects.get(name="Coordinación")
        response = self.client.get(reverse("core:roles_update", args=[group.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Funciones de cargo")

    def test_a_change_warns_every_delegation_live(self):
        self.assertIn("organization.PositionFunction", LIVE_MODELS)
        self.assertIsNone(LIVE_MODELS["organization.PositionFunction"])
