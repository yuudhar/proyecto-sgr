"""Estado de los listados en la sesión, por módulo (v35).

Regla que se prueba: una URL con parámetros de listado se usa y se guarda; una URL sin ninguno restaura lo último
guardado (redirigiendo a la misma URL con esos parámetros); «Limpiar» (?limpiar=1) lo borra. Cambiar la búsqueda,
un filtro o el orden vuelve a la página 1; una página que ya no existe se ajusta; los parámetros inválidos se ignoran.
"""

from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from openpyxl import load_workbook
import io

from core.crud import LIVE_REFRESH_HEADER, PAGE_SIZE, registry
from core.testing import PortalTestCase
from operations.models import Activity
from organization.models import Beneficiary

KEY = "list_state:beneficiarios"


def rut_with_check_digit(body):
    total, factor = 0, 2
    for digit in reversed(str(body)):
        total += int(digit) * factor
        factor = 2 if factor == 7 else factor + 1
    check = 11 - total % 11
    return f"{body}-{'0' if check == 11 else 'K' if check == 10 else check}"


def make_people(count, prefix="Persona Listado"):
    """Beneficiarios de relleno con nombres «Persona Listado A0», «… B1»…, para tener varias páginas."""
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    return [
        Beneficiary.objects.create(rut=rut_with_check_digit(70000000 + index), name=f"{prefix} {letters[index % 26]}{index}")
        for index in range(count)
    ]


def query_of(response):
    """Parámetros de la URL a la que redirige una respuesta, como diccionario de textos."""
    return {name: values[-1] for name, values in parse_qs(urlsplit(response["Location"]).query, keep_blank_values=True).items()}


class ListCase(PortalTestCase):
    slug = "beneficiarios"

    def setUp(self):
        self.login_as("admin")
        self.url = reverse("core:beneficiarios_list")

    def saved(self, key=KEY):
        return self.client.session.get(key)


class ListStateIsSavedTests(ListCase):
    def test_a_visit_with_params_saves_them_in_the_session_under_the_module_key(self):
        make_people(7)
        self.client.get(self.url, {"q": "Persona", "orden": "name", "dir": "desc", "estado": "activo", "page": 2, "filas": 5})
        self.assertEqual(
            self.saved(),
            {"q": "Persona", "filters": {"estado": "activo"}, "orden": "name", "dir": "desc", "archivados": "", "page": 2, "size": 5},
        )

    def test_a_visit_without_params_and_nothing_saved_just_shows_the_list(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["page"].number, 1)

    def test_a_visit_without_params_restores_the_last_state_with_a_redirect(self):
        make_people(7)
        self.client.get(self.url, {"q": "Persona", "orden": "name", "dir": "desc", "page": 2, "filas": 5})
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(urlsplit(response["Location"]).path, self.url)
        self.assertEqual(query_of(response), {"q": "Persona", "orden": "name", "dir": "desc", "page": "2"})
        restored = self.client.get(response["Location"])
        self.assertEqual(restored.context["q"], "Persona")
        self.assertEqual((restored.context["sort"], restored.context["direction"]), ("name", "desc"))
        self.assertEqual((restored.context["page"].number, restored.context["page_size"]), (2, 5))

    def test_restoring_goes_through_a_single_redirect_to_a_url_that_does_not_redirect_again(self):
        make_people(7)
        self.client.get(self.url, {"q": "Persona", "page": 2, "filas": 5})
        first = self.client.get(self.url)
        self.assertEqual(first.status_code, 302)
        self.assertEqual(self.client.get(first["Location"]).status_code, 200)

    def test_params_win_over_the_saved_state_and_replace_it(self):
        make_people(3)
        self.client.get(self.url, {"q": "Persona", "orden": "name", "dir": "desc"})
        response = self.client.get(self.url, {"q": "Listado"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["q"], "Listado")
        self.assertEqual(response.context["sort"], "")
        self.assertEqual(self.saved()["q"], "Listado")
        self.assertEqual(self.saved()["orden"], "")

    def test_a_form_sent_with_empty_fields_means_no_filters_and_clears_the_saved_search(self):
        self.client.get(self.url, {"q": "Persona"})
        response = self.client.get(self.url, {"q": "", "estado": ""})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.saved()["q"], "")
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_other_params_are_kept_when_restoring(self):
        self.client.get(self.url, {"q": "Persona"})
        response = self.client.get(self.url, {"formato": "xlsx"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(query_of(response), {"formato": "xlsx", "q": "Persona"})

    def test_the_state_is_per_module(self):
        self.client.get(self.url, {"q": "Persona", "orden": "name"})
        services = reverse("core:servicios_list")
        self.client.get(services, {"q": "Servicio", "orden": "name", "dir": "desc"})
        self.assertEqual(self.saved()["q"], "Persona")
        self.assertEqual(self.saved("list_state:servicios")["q"], "Servicio")
        self.assertEqual(query_of(self.client.get(self.url)), {"q": "Persona", "orden": "name", "dir": "asc"})
        self.assertEqual(query_of(self.client.get(services)), {"q": "Servicio", "orden": "name", "dir": "desc"})

    def test_the_state_is_not_shared_between_sessions(self):
        self.client.get(self.url, {"q": "Persona"})
        other = Client()
        other.force_login(User.objects.get(username="admin"))
        self.assertEqual(other.get(self.url).status_code, 200)  # sin redirigir: no hereda nada
        self.assertEqual(other.session[KEY]["q"], "")

    def test_logging_out_forgets_the_state(self):
        self.client.get(self.url, {"q": "Persona"})
        self.client.post(reverse("core:logout"))
        self.login_as("admin")
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_clear_deletes_the_state_and_goes_back_to_the_plain_list(self):
        self.client.get(self.url, {"q": "Persona", "orden": "name", "filas": 5})
        response = self.client.get(self.url, {"limpiar": 1})
        self.assertRedirects(response, self.url, fetch_redirect_response=False)
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.assertEqual(self.saved()["q"], "")
        self.assertEqual(self.saved()["orden"], "")

    def test_clear_keeps_the_chosen_page_size(self):
        self.client.get(self.url, {"q": "Persona", "filas": 5})
        self.client.get(self.url, {"limpiar": 1})
        self.assertEqual(self.client.get(self.url).context["page_size"], 5)

    def test_the_clear_button_shows_only_when_something_is_active(self):
        plain = self.client.get(self.url)
        self.assertFalse(plain.context["can_reset"])
        self.assertNotContains(plain, "limpiar=1")
        searched = self.client.get(self.url, {"q": "Persona"})
        self.assertTrue(searched.context["can_reset"])
        self.assertContains(searched, f'href="{self.url}?limpiar=1">Limpiar')
        self.assertTrue(self.client.get(self.url, {"orden": "name"}).context["can_reset"])

    def test_the_clear_button_also_shows_in_the_attention_screen(self):
        page = self.client.get(reverse("core:atencion"), {"q": "María"})
        self.assertContains(page, f'href="{reverse("core:atencion")}?limpiar=1">Limpiar')


class ListStateValidationTests(ListCase):
    def test_a_page_that_is_not_a_number_is_page_one(self):
        make_people(7)
        for value in ("abc", "", "1.5", "-3", "0"):
            with self.subTest(page=value):
                response = self.client.get(self.url, {"q": "Persona", "filas": 5, "page": value})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context["page"].number, 1)

    def test_a_page_that_does_not_exist_is_adjusted_to_the_last_and_the_adjusted_one_is_saved(self):
        make_people(7)
        response = self.client.get(self.url, {"q": "Persona", "filas": 5, "page": 99})
        self.assertEqual(response.context["page"].number, 2)
        self.assertEqual(self.saved()["page"], 2)

    def test_a_saved_page_that_stopped_existing_is_adjusted_when_restoring(self):
        people = make_people(7)
        self.client.get(self.url, {"q": "Persona", "filas": 5, "page": 2})
        for person in people[:3]:
            person.delete()
        restored = self.client.get(self.client.get(self.url)["Location"])
        self.assertEqual(restored.context["page"].number, 1)
        self.assertEqual(self.saved()["page"], 1)

    def test_an_empty_result_still_answers_with_the_empty_message(self):
        response = self.client.get(self.url, {"q": "zzzz-no-existe", "page": 4})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["page"].paginator.count, 0)
        self.assertContains(response, "No hay beneficiarios que coincidan con la búsqueda")

    def test_a_page_size_that_is_not_5_15_or_30_is_ignored(self):
        make_people(7)
        for value in ("999", "0", "-5", "abc", "", "7"):
            with self.subTest(filas=value):
                response = self.client.get(self.url, {"q": "Persona", "filas": value})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context["page_size"], PAGE_SIZE)
                self.assertIsNone(self.saved()["size"])

    def test_the_three_page_sizes_work_and_are_saved(self):
        make_people(40)
        for size in (5, 15, 30):
            with self.subTest(filas=size):
                response = self.client.get(self.url, {"q": "Persona", "filas": size})
                self.assertEqual(response.context["page_size"], size)
                self.assertEqual(len(response.context["rows"]), size)
                self.assertEqual(self.saved()["size"], size)

    def test_the_page_size_is_kept_when_a_later_visit_does_not_say_it(self):
        make_people(7)
        self.client.get(self.url, {"q": "Persona", "filas": 5})
        self.assertEqual(self.client.get(self.url, {"q": "Persona", "page": 2}).context["page_size"], 5)

    def test_the_page_size_is_per_module(self):
        self.client.get(self.url, {"q": "Persona", "filas": 5})
        self.assertEqual(self.client.get(reverse("core:servicios_list"), {"q": ""}).context["page_size"], PAGE_SIZE)

    def test_an_order_that_is_not_allowed_is_ignored(self):
        for value in ("password", "id; DROP TABLE", "deleted_at", "__str__", "rut__x", ""):
            with self.subTest(orden=value):
                response = self.client.get(self.url, {"q": "", "orden": value, "dir": "desc"})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context["sort"], "")
                self.assertEqual(self.saved()["orden"], "")
                self.assertEqual(self.saved()["dir"], "")

    def test_a_direction_that_is_not_asc_or_desc_is_asc(self):
        response = self.client.get(self.url, {"orden": "name", "dir": "arriba"})
        self.assertEqual(response.context["direction"], "asc")
        self.assertEqual(self.saved()["dir"], "asc")

    def test_a_filter_value_that_is_not_an_option_is_ignored(self):
        for value in ("hackeado", "999999", "<script>"):
            with self.subTest(estado=value):
                response = self.client.get(self.url, {"estado": value})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(self.saved()["filters"], {})

    def test_an_archived_value_that_is_not_allowed_is_ignored(self):
        response = self.client.get(self.url, {"archivados": "quizas"})
        self.assertFalse(response.context["archived"])
        self.assertEqual(self.saved()["archivados"], "")

    def test_whoever_cannot_see_the_archived_users_does_not_get_them_from_the_url_or_the_session(self):
        manager = User.objects.create_user("gestor.listados", password="Hola123!")
        for label in ("auth.view_user", "auth.add_user", "auth.change_user"):
            self.give_perm(manager, label)
        self.client.force_login(manager)
        users = reverse("core:usuarios_list")
        response = self.client.get(users, {"archivados": "solo"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["archived"])
        self.assertEqual(self.saved("list_state:usuarios")["archivados"], "")
        session = self.client.session
        session["list_state:usuarios"] = {**session["list_state:usuarios"], "archivados": "solo"}
        session.save()
        restored = self.client.get(self.client.get(users)["Location"])
        self.assertFalse(restored.context["archived"])
        self.assertEqual(self.saved("list_state:usuarios")["archivados"], "")

    def test_a_session_value_that_was_tampered_with_never_breaks_the_list(self):
        session = self.client.session
        session[KEY] = {"q": 5, "filters": "x", "orden": ["name"], "dir": None, "page": "abc", "size": 999, "extra": 1}
        session.save()
        self.assertEqual(self.client.get(self.url).status_code, 200)
        session = self.client.session
        session[KEY] = "no es un diccionario"
        session.save()
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_a_saved_filter_the_person_may_not_use_is_ignored_when_restoring(self):
        self.login_as("consulta1")
        session = self.client.session
        session["list_state:actividades"] = {
            "q": "", "filters": {"delegation": str(self.south.pk)}, "orden": "", "dir": "", "archivados": "", "page": 1, "size": None,
        }
        session.save()
        restored = self.client.get(reverse("core:atencion"), follow=True)
        self.assertEqual(restored.status_code, 200)
        self.assertTrue(all(row.obj.delegation_id == self.north.pk for row in restored.context["rows"]))


class ListStatePageOneTests(ListCase):
    def setUp(self):
        super().setUp()
        make_people(12)

    def test_the_page_links_keep_the_search_and_the_order(self):
        response = self.client.get(self.url, {"q": "Persona", "orden": "name", "dir": "desc", "filas": 5})
        self.assertContains(response, "q=Persona&amp;orden=name&amp;dir=desc&amp;page=2")

    def test_a_new_search_comes_back_on_page_one(self):
        self.client.get(self.url, {"q": "Persona", "filas": 5, "page": 3})
        self.assertEqual(self.saved()["page"], 3)
        response = self.client.get(self.url, {"q": "Listado"})  # lo que envía el formulario: sin página
        self.assertEqual(response.context["page"].number, 1)
        self.assertEqual(self.saved()["page"], 1)

    def test_a_new_filter_comes_back_on_page_one(self):
        self.client.get(self.url, {"q": "Persona", "filas": 5, "page": 3})
        response = self.client.get(self.url, {"q": "Persona", "estado": "activo"})
        self.assertEqual(response.context["page"].number, 1)
        self.assertEqual(self.saved()["page"], 1)

    def test_a_new_order_comes_back_on_page_one(self):
        first = self.client.get(self.url, {"q": "Persona", "filas": 5, "page": 3})
        header = next(c for c in first.context["columns"] if c.sort_key == "name")
        self.assertNotIn("page=", header.sort_url)
        response = self.client.get(self.url + header.sort_url)
        self.assertEqual(response.context["page"].number, 1)
        self.assertEqual(self.saved()["page"], 1)

    def test_the_archived_toggle_comes_back_on_page_one(self):
        first = self.client.get(self.url, {"q": "Persona", "filas": 5, "page": 3})
        self.assertNotIn("page=", first.context["archived_url"])

    def test_changing_the_page_size_comes_back_on_page_one(self):
        self.client.get(self.url, {"q": "Persona", "filas": 5, "page": 3})
        self.client.post(reverse("core:page_size"), {"filas": "15", "modulo": "beneficiarios", "next": f"{self.url}?q=Persona"})
        self.assertEqual(self.saved()["page"], 1)
        self.assertEqual(self.saved()["size"], 15)


class ListStateNavigationTests(ListCase):
    """Filtrar → abrir el detalle (o editar) → volver → mismo filtro, página y orden."""

    def setUp(self):
        super().setUp()
        self.people = make_people(12)
        self.params = {"q": "Persona", "orden": "name", "dir": "desc", "filas": 5, "page": 2}
        self.client.get(self.url, self.params)

    def assertBackToTheSameState(self, response):
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["q"], "Persona")
        self.assertEqual((response.context["sort"], response.context["direction"]), ("name", "desc"))
        self.assertEqual((response.context["page"].number, response.context["page_size"]), (2, 5))

    def test_back_from_the_detail_with_the_breadcrumb(self):
        detail = self.client.get(reverse("core:beneficiarios_detail", args=[self.people[0].pk]))
        self.assertContains(detail, f'href="{self.url}"')
        self.assertBackToTheSameState(self.client.get(self.url, follow=True))

    def test_back_from_the_edit_form_with_cancel(self):
        detail_url = reverse("core:beneficiarios_detail", args=[self.people[0].pk])
        form = self.client.get(reverse("core:beneficiarios_update", args=[self.people[0].pk]))
        self.assertEqual(form.context["cancel_url"], detail_url)  # cancelar la edición vuelve al detalle…
        self.assertContains(self.client.get(detail_url), f'href="{self.url}"')  # …y el detalle vuelve al listado
        self.assertBackToTheSameState(self.client.get(self.url, follow=True))

    def test_back_after_saving_an_edit(self):
        person = self.people[0]
        data = {"rut": person.rut, "name": "Persona Listado Editada", "phone": "", "address": ""}
        saved = self.client.post(reverse("core:beneficiarios_update", args=[person.pk]), data)
        self.assertRedirects(saved, reverse("core:beneficiarios_detail", args=[person.pk]), fetch_redirect_response=False)
        self.assertEqual(Beneficiary.objects.get(pk=person.pk).name, "Persona Listado Editada")
        self.assertContains(self.client.get(saved["Location"]), f'href="{self.url}"')  # del detalle se vuelve al listado
        self.assertBackToTheSameState(self.client.get(self.url, follow=True))

    def test_back_after_archiving(self):
        person = self.people[0]
        done = self.client.post(reverse("core:beneficiarios_archive", args=[person.pk]))
        self.assertEqual(done.status_code, 302)
        self.assertBackToTheSameState(self.client.get(done["Location"], follow=True))

    def test_back_from_another_module_through_the_menu_link(self):
        self.client.get(reverse("core:servicios_list"), {"q": "x"})
        self.client.get(reverse("core:dashboard"))
        self.assertBackToTheSameState(self.client.get(self.url, follow=True))

    def test_the_menu_links_are_the_plain_list_url_so_they_restore(self):
        page = self.client.get(reverse("core:dashboard"))
        self.assertContains(page, f'href="{self.url}"')

    def test_the_address_bar_ends_up_with_the_restored_params(self):
        final = self.client.get(self.url, follow=True)
        self.assertEqual(final.redirect_chain[-1][0].split("?")[0], self.url)
        self.assertIn("page=2", final.redirect_chain[-1][0])


class ListStateEveryModuleTests(PortalTestCase):
    """El mismo recorrido en todos los módulos con listado: lo hereda del motor, no de cada módulo."""

    def setUp(self):
        self.login_as("admin")

    def modules(self):
        return [crud for crud in registry.all() if not crud.list_redirect]

    def test_there_are_modules_to_check(self):
        self.assertGreaterEqual(len(self.modules()), 20)

    def test_every_module_saves_its_own_state_under_its_own_key(self):
        for crud in self.modules():
            with self.subTest(module=crud.slug):
                response = self.client.get(crud.url("list"), {"q": "a", "filas": 5})
                self.assertEqual(response.status_code, 200)
                saved = self.client.session.get(f"list_state:{crud.slug}")
                self.assertIsNotNone(saved)
                self.assertEqual(saved["size"], 5)

    def test_every_module_restores_filter_order_and_size_when_it_comes_back(self):
        for crud in self.modules():
            with self.subTest(module=crud.slug):
                url = crud.url("list")
                first = self.client.get(url, {"filas": 5})
                params = {"filas": 5}
                sortable = next((c for c in first.context["columns"] if c.sort_key), None)
                if sortable is not None:
                    params.update(orden=sortable.sort_key, dir="desc")
                spec = next((f for f in first.context["filters"] if f.options), None)
                if spec is not None:
                    params[spec.name] = spec.options[0][0]
                self.client.get(url, params)
                row = (first.context["rows"] or [None])[0]
                if row is not None:
                    self.assertEqual(self.client.get(row.detail_url).status_code, 200)
                restored = self.client.get(url, follow=True)
                self.assertEqual(restored.status_code, 200)
                self.assertEqual(restored.context["page_size"], 5)
                if sortable is not None:
                    self.assertEqual((restored.context["sort"], restored.context["direction"]), (sortable.sort_key, "desc"))
                if spec is not None:
                    selected = next(f.selected for f in restored.context["filters"] if f.name == spec.name)
                    self.assertEqual(selected, spec.options[0][0])

    def test_every_module_ignores_invalid_params(self):
        for crud in self.modules():
            with self.subTest(module=crud.slug):
                response = self.client.get(
                    crud.url("list"), {"page": "abc", "filas": "999", "orden": "no_existe", "dir": "x", "archivados": "x"}
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context["page"].number, 1)
                self.assertEqual(response.context["page_size"], PAGE_SIZE)
                self.assertEqual(response.context["sort"], "")

    def test_every_module_adjusts_a_page_that_does_not_exist(self):
        for crud in self.modules():
            with self.subTest(module=crud.slug):
                response = self.client.get(crud.url("list"), {"page": 9999, "filas": 5})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context["page"].number, response.context["page"].paginator.num_pages)

    def test_every_module_clears_with_the_button_link(self):
        for crud in self.modules():
            with self.subTest(module=crud.slug):
                self.client.get(crud.url("list"), {"q": "a", "orden": "", "filas": 5})
                response = self.client.get(crud.url("list"), {"limpiar": 1})
                self.assertRedirects(response, crud.url("list"), fetch_redirect_response=False)

    def test_the_attention_screen_shares_the_state_of_its_module(self):
        self.client.get(reverse("core:atencion"), {"q": "María"})
        self.assertEqual(self.client.session["list_state:actividades"]["q"], "María")
        redirected = self.client.get(reverse("core:actividades_list"), follow=True)
        self.assertEqual(redirected.status_code, 200)
        self.assertEqual(redirected.context["q"], "María")

    def test_a_person_without_permission_still_gets_a_403_and_no_state_is_kept(self):
        self.login_as("consulta1")
        response = self.client.get(reverse("core:auditoria_list"), {"q": "a"})
        self.assertEqual(response.status_code, 403)
        self.assertIsNone(self.client.session.get("list_state:auditoria"))


class ListStateInteractionTests(ListCase):
    """Lo que el listado hace con el estado: Excel, WebSocket (consulta de fondo) y tamaño de página."""

    def test_the_excel_export_uses_the_state_in_force(self):
        make_people(3, prefix="Exportable")
        self.client.get(self.url, {"q": "Exportable", "filas": 5})
        response = self.client.get(self.url, {"formato": "xlsx"}, follow=True)
        self.assertEqual(response.status_code, 200)
        sheet = load_workbook(io.BytesIO(response.content)).active
        names = [cell.value for row in sheet.iter_rows(min_row=1) for cell in row if isinstance(cell.value, str)]
        self.assertEqual(sum(name.startswith("Exportable ") for name in names), 3)
        self.assertFalse(any("Persona Listado" in name for name in names))

    def test_the_export_button_link_carries_the_state_but_not_the_page(self):
        make_people(12)
        response = self.client.get(self.url, {"q": "Persona", "orden": "name", "dir": "desc", "filas": 5, "page": 2})
        link = response.context["export_url"]
        self.assertIn("q=Persona", link)
        self.assertIn("orden=name", link)
        self.assertIn("formato=xlsx", link)
        self.assertNotIn("page=", link)

    def test_exporting_does_not_change_the_saved_state(self):
        make_people(12)
        self.client.get(self.url, {"q": "Persona", "filas": 5, "page": 3})
        before = self.saved()
        self.client.get(self.url, {"q": "Persona", "formato": "xlsx"})
        self.assertEqual(self.saved(), before)

    def test_the_background_refresh_of_the_websocket_neither_restores_nor_saves(self):
        make_people(7)
        self.client.get(self.url, {"q": "Persona", "filas": 5, "page": 2})
        before = self.saved()
        plain = self.client.get(self.url, headers={LIVE_REFRESH_HEADER: "1"})
        self.assertEqual(plain.status_code, 200)  # sin redirigir: esa pestaña muestra lo suyo
        self.client.get(self.url, {"q": "Otra"}, headers={LIVE_REFRESH_HEADER: "1"})
        self.assertEqual(self.saved(), before)

    def test_the_background_refresh_of_the_restored_url_shows_the_same_rows(self):
        make_people(12)
        self.client.get(self.url, {"q": "Persona", "orden": "name", "dir": "desc", "filas": 5, "page": 2})
        restored = self.client.get(self.client.get(self.url)["Location"])
        refreshed = self.client.get(
            self.client.get(self.url)["Location"], headers={LIVE_REFRESH_HEADER: "1", "X-Requested-With": "fetch"}
        )
        self.assertEqual([r.obj.pk for r in restored.context["rows"]], [r.obj.pk for r in refreshed.context["rows"]])
        self.assertEqual(refreshed.context["page"].number, 2)

    def test_a_row_that_stops_matching_the_filter_leaves_the_refreshed_table(self):
        person = make_people(1, prefix="Sale del filtro")[0]
        url = f"{self.url}?q=Sale+del+filtro"
        self.assertEqual(len(self.client.get(url).context["rows"]), 1)
        person.name = "Otro nombre"
        person.save()
        refreshed = self.client.get(url, headers={LIVE_REFRESH_HEADER: "1"})
        self.assertEqual(len(refreshed.context["rows"]), 0)

    def test_the_live_script_sends_the_background_header(self):
        from django.conf import settings

        source = (settings.BASE_DIR / "core" / "static" / "core" / "js" / "live-updates.js").read_text(encoding="utf-8")
        self.assertIn("X-Live-Refresh", source)
        self.assertEqual(LIVE_REFRESH_HEADER, "X-Live-Refresh")

    def test_the_page_size_buttons_name_the_module(self):
        make_people(2)
        page = self.client.get(self.url, {"q": "Persona"})
        self.assertContains(page, '<input type="hidden" name="modulo" value="beneficiarios">')

    def test_choosing_a_page_size_in_a_module_only_changes_that_module(self):
        self.client.get(reverse("core:servicios_list"), {"q": ""})
        response = self.client.post(
            reverse("core:page_size"), {"filas": "5", "modulo": "beneficiarios", "next": f"{self.url}?q="}, follow=True
        )
        self.assertContains(response, "Beneficiarios muestra 5 filas por página mientras dure tu sesión.")
        self.assertEqual(self.client.get(self.url, {"q": ""}).context["page_size"], 5)
        self.assertEqual(self.client.get(reverse("core:servicios_list"), {"q": ""}).context["page_size"], PAGE_SIZE)
        self.assertNotIn("page_size", self.client.session)

    def test_a_page_size_without_module_keeps_working_for_every_list(self):
        self.client.post(reverse("core:page_size"), {"filas": "30", "next": self.url})
        self.assertEqual(self.client.get(self.url, {"q": ""}).context["page_size"], 30)
        self.assertEqual(self.client.get(reverse("core:servicios_list"), {"q": ""}).context["page_size"], 30)

    def test_the_page_size_of_the_module_wins_over_the_general_one(self):
        self.client.post(reverse("core:page_size"), {"filas": "30", "next": self.url})
        self.client.get(self.url, {"q": "", "filas": 5})
        self.assertEqual(self.client.get(self.url, {"q": ""}).context["page_size"], 5)

    def test_an_unknown_module_or_one_without_permission_falls_back_to_the_general_size(self):
        self.client.post(reverse("core:page_size"), {"filas": "5", "modulo": "no-existe", "next": self.url})
        self.assertEqual(self.client.session["page_size"], 5)
        self.login_as("consulta1")
        self.client.post(reverse("core:page_size"), {"filas": "30", "modulo": "auditoria", "next": self.url})
        self.assertEqual(self.client.session["page_size"], 30)
        self.assertIsNone(self.client.session.get("list_state:auditoria"))

    def test_the_page_size_link_never_carries_the_old_size_in_the_url(self):
        make_people(7)
        response = self.client.get(self.url, {"q": "Persona", "filas": 5, "page": 2})
        self.assertNotIn("filas", response.context["page_size_next"])
        self.assertNotIn("filas", response.context["page_query"])


class DefaultOrderTests(ListCase):
    """Sin orden elegido: lo más recién creado primero, con el id descendente de desempate (no la última edición)."""

    def setUp(self):
        super().setUp()
        now = timezone.now()
        self.zeta, self.alfa, self.mike = make_people(3, prefix="Orden")
        # Creados de más nuevo a más antiguo: Zeta, Mike, Alfa (a propósito, no es el orden alfabético).
        Beneficiary.objects.filter(pk=self.zeta.pk).update(name="Orden Zeta", created_at=now - timedelta(days=1))
        Beneficiary.objects.filter(pk=self.mike.pk).update(name="Orden Mike", created_at=now - timedelta(days=2))
        Beneficiary.objects.filter(pk=self.alfa.pk).update(name="Orden Alfa", created_at=now - timedelta(days=3))

    def names(self, **params):
        response = self.client.get(self.url, {"q": "Orden", **params})
        return [row.obj.name for row in response.context["rows"]]

    def test_the_newest_created_comes_first(self):
        self.assertEqual(self.names(), ["Orden Zeta", "Orden Mike", "Orden Alfa"])

    def test_it_is_not_alphabetical(self):
        self.assertNotEqual(self.names(), sorted(self.names()))

    def test_editing_a_record_does_not_move_it(self):
        oldest = Beneficiary.objects.get(pk=self.alfa.pk)
        oldest.address = "Calle nueva 123"
        oldest.save()
        self.assertGreater(Beneficiary.objects.get(pk=self.alfa.pk).updated_at, Beneficiary.objects.get(pk=self.zeta.pk).updated_at)
        self.assertEqual(self.names(), ["Orden Zeta", "Orden Mike", "Orden Alfa"])

    def test_with_the_same_creation_moment_the_higher_id_comes_first(self):
        same = timezone.now()
        Beneficiary.objects.filter(pk__in=[self.zeta.pk, self.alfa.pk, self.mike.pk]).update(created_at=same)
        ids = [row.obj.pk for row in self.client.get(self.url, {"q": "Orden"}).context["rows"]]
        self.assertEqual(ids, sorted(ids, reverse=True))

    def test_a_chosen_order_replaces_the_default_in_both_directions(self):
        self.assertEqual(self.names(orden="name", dir="asc"), ["Orden Alfa", "Orden Mike", "Orden Zeta"])
        self.assertEqual(self.names(orden="name", dir="desc"), ["Orden Zeta", "Orden Mike", "Orden Alfa"])
        self.assertEqual(self.names(orden="name", dir="asc"), ["Orden Alfa", "Orden Mike", "Orden Zeta"])

    def test_the_attention_list_orders_by_creation_and_not_by_the_attention_date(self):
        now = timezone.now()
        first, second = Activity.objects.order_by("pk")[:2]
        Activity.objects.filter(pk=first.pk).update(created_at=now + timedelta(days=1), date=timezone.localdate() - timedelta(days=30))
        Activity.objects.filter(pk=second.pk).update(created_at=now - timedelta(days=60), date=timezone.localdate())
        everything = self.client.get(reverse("core:atencion"), {"filas": 30}).context["rows"]
        pks = [row.obj.pk for row in everything]
        self.assertEqual(pks[0], first.pk)  # la de creación más reciente, aunque su fecha de atención sea la más antigua
        self.assertNotEqual(pks[0], second.pk)

    def test_every_module_has_the_default_order_by_creation_or_declares_its_own(self):
        for crud in registry.all():
            with self.subTest(module=crud.slug):
                order = crud.default_ordering()
                if crud.ordering:
                    self.assertEqual(order, tuple(crud.ordering))
                elif any(f.name == "created_at" for f in crud.model._meta.get_fields()):
                    self.assertEqual(order, ("-created_at", "-pk"))

    def test_the_modules_without_a_creation_date_are_the_roles_and_the_users(self):
        explicit = sorted(c.slug for c in registry.all() if not any(f.name == "created_at" for f in c.model._meta.get_fields()))
        self.assertEqual(explicit, ["roles", "usuarios"])
        self.assertEqual(registry.get("usuarios").default_ordering(), ("-date_joined", "-pk"))
