import datetime

from django.contrib.messages import get_messages
from django.urls import reverse
from django.utils import timezone

from core.crud import STATE_FILTER, STATE_INACTIVE, registry
from core.models import AuditLog
from core.testing import PortalTestCase
from operations.models import Activity, Commitment, ManagementType
from organization.models import Beneficiary, Delegation, Item, Position, Service, Territory

DELETABLE = ("beneficiarios", "territorios", "servicios", "cargos", "tipos-de-gestion", "agenda")


def messages_of(response):
    return [str(message) for message in get_messages(response.wsgi_request)]


class RealDeleteTests(PortalTestCase):

    def setUp(self):
        self.login_as("admin")

    def test_the_catalogs_that_can_be_deleted_for_good_are_the_expected_ones(self):
        self.assertEqual({crud.slug for crud in registry.all() if crud.deletable}, {*DELETABLE, "roles"})

    def test_a_record_that_nobody_uses_is_deleted_for_good(self):
        person = Beneficiary.objects.create(rut="99999999-9", name="Persona Temporal")
        url = reverse("core:beneficiarios_delete", args=[person.pk])
        confirm = self.client.get(url)
        self.assertEqual(confirm.status_code, 200)
        self.assertContains(confirm, "se elimina definitivamente")
        response = self.client.post(url)
        self.assertRedirects(response, reverse("core:beneficiarios_list"), fetch_redirect_response=False)
        self.assertFalse(Beneficiary.objects.filter(pk=person.pk).exists())
        archived = self.client.get(reverse("core:beneficiarios_list"), {"archivados": "1", "q": "Temporal"})
        self.assertEqual(archived.context["page"].paginator.count, 0)
        self.assertTrue(AuditLog.objects.filter(event="Registro eliminado", previous_value__contains="Persona Temporal").exists())

    def test_every_catalog_deletes_an_unused_record_and_says_so(self):
        delegation = Delegation.objects.get(name="Delegación Norte")
        unused = {
            "beneficiarios": Beneficiary.objects.create(rut="98765432-1", name="Sin Uso Uno"),
            "territorios": Territory.objects.create(name="Sin uso", delegation=delegation),
            "servicios": Service.objects.create(name="Servicio sin uso"),
            "cargos": Position.objects.create(name="Cargo sin uso", valid_from=datetime.date(2026, 1, 1)),
            "tipos-de-gestion": ManagementType.objects.create(name="Gestión sin uso"),
        }
        for slug, obj in unused.items():
            with self.subTest(slug=slug):
                response = self.client.post(registry.get(slug).url("delete", obj.pk), follow=True)
                self.assertFalse(type(obj).objects.filter(pk=obj.pk).exists())
                self.assertEqual(response.status_code, 200)
                self.assertTrue(any("eliminad" in text for text in messages_of(response)))

    def test_a_record_in_use_is_not_deleted_and_the_reason_is_shown(self):
        activity = Activity.objects.exclude(beneficiary=None).first()
        person = activity.beneficiary
        url = reverse("core:beneficiarios_delete", args=[person.pk])
        confirm = self.client.get(url)
        self.assertContains(confirm, "No se puede eliminar.")
        self.assertContains(confirm, "Está en uso en")
        response = self.client.post(url, follow=True)
        self.assertTrue(Beneficiary.objects.filter(pk=person.pk).exists())
        self.assertTrue(any("No se puede eliminar" in text and "Está en uso" in text for text in messages_of(response)))

    def test_a_territory_with_commitments_is_not_deleted(self):
        territory = Commitment.objects.first().territory
        response = self.client.post(reverse("core:territorios_delete", args=[territory.pk]), follow=True)
        self.assertTrue(Territory.objects.filter(pk=territory.pk).exists())
        self.assertTrue(any("compromiso" in text for text in messages_of(response)))

    def test_the_list_tells_sweetalert_why_a_delete_is_blocked(self):
        person = Activity.objects.exclude(beneficiary=None).first().beneficiary
        page = self.client.get(reverse("core:beneficiarios_list"), {"q": person.name}).content.decode()
        self.assertIn('data-delete-kind="remove"', page)
        self.assertRegex(page, r'data-delete-kind="remove" data-blocked="Está en uso en \d+ actividad')

    def test_archive_and_delete_are_two_separate_actions_where_both_exist(self):
        page = self.client.get(reverse("core:beneficiarios_list")).content.decode()
        self.assertIn('data-delete-kind="archive" data-delete-label="archive"', page)
        self.assertIn('aria-label="Archivar ', page)
        self.assertIn('data-delete-kind="remove"', page)
        self.assertIn('aria-label="Eliminar ', page)

    def test_a_catalog_that_only_archives_keeps_its_single_delete_button(self):
        page = self.client.get(reverse("core:delegaciones_list")).content.decode()
        self.assertIn('data-delete-kind="archive"', page)
        self.assertNotIn("data-delete-label", page)
        self.assertNotIn('data-delete-kind="remove"', page)
        self.assertNotIn('aria-label="Archivar', page)

    def test_the_edit_modal_offers_archive_and_delete(self):
        person = Beneficiary.objects.create(rut="97531246-8", name="Para Modal")
        modal = self.client.get(reverse("core:beneficiarios_update", args=[person.pk]), {"modal": "1"})
        html = modal.content.decode()
        self.assertEqual(modal["X-Modal"], "form")
        self.assertIn('data-delete-label="archive"', html)
        self.assertIn('data-delete-kind="remove"', html)

    def test_an_archived_record_can_still_be_deleted_for_good(self):
        person = Beneficiary.objects.create(rut="96385274-1", name="Archivada Luego Eliminada")
        self.client.post(reverse("core:beneficiarios_archive", args=[person.pk]))
        person.refresh_from_db()
        self.assertIsNotNone(person.deleted_at)
        self.client.post(reverse("core:beneficiarios_delete", args=[person.pk]))
        self.assertFalse(Beneficiary.objects.filter(pk=person.pk).exists())

    def test_the_no_javascript_archive_page_says_archivar(self):
        person = Beneficiary.objects.create(rut="95175385-6", name="Pagina Sin Js")
        page = self.client.get(reverse("core:beneficiarios_archive", args=[person.pk]))
        self.assertContains(page, "Archivar beneficiario")
        self.assertContains(page, "Sí, archivar")
        empty = Delegation.objects.create(name="Delegación Vacía")
        other = self.client.get(reverse("core:delegaciones_archive", args=[empty.pk]))
        self.assertContains(other, "Sí, eliminar")
        self.assertNotContains(other, "Sí, archivar")

    def test_without_the_delete_permission_nothing_is_deleted(self):
        person = Beneficiary.objects.create(rut="94725836-0", name="Protegida")
        self.client.logout()
        self.login_as("consulta1")
        response = self.client.post(reverse("core:beneficiarios_delete", args=[person.pk]))
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Beneficiary.objects.filter(pk=person.pk).exists())
        anonymous = self.client.__class__()
        self.assertEqual(anonymous.post(reverse("core:beneficiarios_delete", args=[person.pk])).status_code, 302)

    def test_a_delete_only_works_by_post(self):
        person = Beneficiary.objects.create(rut="93615947-2", name="Solo Por Post")
        self.client.get(reverse("core:beneficiarios_delete", args=[person.pk]))
        self.assertTrue(Beneficiary.objects.filter(pk=person.pk).exists())


class ListToolsTests(PortalTestCase):

    def setUp(self):
        self.login_as("admin")

    def test_every_catalog_with_a_real_delete_has_search_and_a_filter(self):
        for slug in DELETABLE:
            with self.subTest(slug=slug):
                crud = registry.get(slug)
                self.assertTrue(crud.search_fields, "sin buscador")
                self.assertTrue(crud.list_filters or crud.state_filter, "sin filtro")

    def test_catalogs_without_fields_to_filter_get_the_state_filter(self):
        for slug in ("beneficiarios", "cargos", "tipos-de-gestion"):
            with self.subTest(slug=slug):
                response = self.client.get(reverse(f"core:{slug.replace('-', '_')}_list"))
                names = [spec.name for spec in response.context["filters"]]
                self.assertIn(STATE_FILTER, names)
                self.assertContains(response, 'name="estado"')

    def test_the_state_filter_shows_only_the_archived_ones(self):
        person = Beneficiary.objects.create(rut="92846573-1", name="Persona Archivada Filtro")
        person.deleted_at = timezone.now()
        person.save(update_fields=["deleted_at", "updated_at"])
        url = reverse("core:beneficiarios_list")
        inactive = self.client.get(url, {STATE_FILTER: STATE_INACTIVE})
        self.assertEqual([row.obj.pk for row in inactive.context["rows"]], [person.pk])
        active = self.client.get(url, {STATE_FILTER: "activo"})
        self.assertNotIn(person.pk, [row.obj.pk for row in active.context["rows"]])

    def test_the_state_filter_combines_with_search_and_keeps_the_page_links(self):
        for number in range(40):
            Beneficiary.objects.create(rut=f"8{number:07d}-0", name=f"Filtro Combinado {number:02d}")
        response = self.client.get(reverse("core:beneficiarios_list"), {"q": "Combinado", STATE_FILTER: "activo"})
        self.assertGreater(response.context["page"].paginator.num_pages, 1)
        self.assertContains(response, "q=Combinado&amp;estado=activo&amp;page=2")

    def test_items_can_now_be_searched(self):
        name = Item.objects.filter(deleted_at__isnull=True).first().name
        url = reverse("core:items_list")
        found = self.client.get(url, {"q": name})
        self.assertGreaterEqual(found.context["page"].paginator.count, 1)
        self.assertContains(found, 'name="q"')
        nothing = self.client.get(url, {"q": "zzzz sin coincidencias zzzz"})
        self.assertEqual(nothing.context["page"].paginator.count, 0)
