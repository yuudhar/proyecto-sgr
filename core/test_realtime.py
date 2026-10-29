import json
from asgiref.sync import async_to_sync, sync_to_async
from django.conf import settings
from django.contrib.auth.models import User
from django.urls import reverse
from core.models import AuditLog
from core.testing import PortalTestCase
from evidence.models import Evidence
from operations.models import Activity
from organization.models import Beneficiary, Officer, Territory
from core.crud import registry

from channels.layers import get_channel_layer
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.contrib.auth.models import AnonymousUser
from django.contrib.sessions.backends.db import SessionStore
from django.db import transaction

from core.access import ALL_DELEGATIONS, SESSION_DELEGATION
from operations.models import Commitment
from planning.models import Period
from sgr_project.asgi import application
from websocket.routing import websocket_urlpatterns
from websocket.services import crud_group

ROUTER = URLRouter(websocket_urlpatterns)
NORTE = "matias.cavieres"
SUR = "matias.quiroz"


def connect(user, path, session=None):
    """Abre una conexión WebSocket con el usuario y la sesión indicados (sin pasar por el navegador)."""
    communicator = WebsocketCommunicator(ROUTER, path)
    communicator.scope["user"] = user
    communicator.scope["session"] = session if session is not None else SessionStore()
    return communicator


async def open_socket(user, path, session=None):
    communicator = connect(user, path, session)
    connected, _ = await communicator.connect()
    return communicator, connected


async def nothing_arrives(communicator):
    return await communicator.receive_nothing(timeout=0.2)


class AsgiApplicationTests(PortalTestCase):

    def test_the_project_is_served_as_asgi_with_daphne_first(self):
        self.assertEqual(settings.INSTALLED_APPS[0], "daphne")
        self.assertLess(settings.INSTALLED_APPS.index("daphne"), settings.INSTALLED_APPS.index("django.contrib.staticfiles"))
        for app in ("channels", "websocket"):
            self.assertIn(app, settings.INSTALLED_APPS)
        self.assertEqual(settings.ASGI_APPLICATION, "sgr_project.asgi.application")
        self.assertEqual(settings.CHANNEL_LAYERS["default"]["BACKEND"], "channels.layers.InMemoryChannelLayer")
        self.assertIsNotNone(get_channel_layer())

    def test_the_router_separates_http_and_websocket_and_has_the_two_routes(self):
        self.assertEqual(set(application.application_mapping), {"http", "websocket"})
        routes = {str(pattern.pattern) for pattern in websocket_urlpatterns}
        self.assertEqual(routes, {"ws/crud/<slug:slug>/", "ws/live/"})

    def test_a_signed_in_browser_opens_the_socket_through_the_whole_stack(self):
        self.login_as(NORTE)
        cookie = self.client.cookies[settings.SESSION_COOKIE_NAME].value
        headers = [(b"origin", b"http://testserver"), (b"cookie", f"{settings.SESSION_COOKIE_NAME}={cookie}".encode())]

        async def scenario(extra):
            communicator = WebsocketCommunicator(application, "/ws/live/", headers=headers + extra)
            connected, _ = await communicator.connect()
            if connected:
                await communicator.disconnect()
            return connected

        self.assertTrue(async_to_sync(scenario)([]))

    def test_a_socket_from_a_foreign_origin_is_refused(self):
        self.login_as(NORTE)
        cookie = self.client.cookies[settings.SESSION_COOKIE_NAME].value
        headers = [(b"origin", b"http://sitio-ajeno.example"), (b"cookie", f"{settings.SESSION_COOKIE_NAME}={cookie}".encode())]

        async def scenario():
            communicator = WebsocketCommunicator(application, "/ws/live/", headers=headers)
            connected, _ = await communicator.connect()
            return connected

        self.assertFalse(async_to_sync(scenario)())

    def test_a_socket_without_a_session_is_refused(self):
        headers = [(b"origin", b"http://testserver")]

        async def scenario():
            communicator = WebsocketCommunicator(application, "/ws/live/", headers=headers)
            connected, _ = await communicator.connect()
            return connected

        self.assertFalse(async_to_sync(scenario)())


class LiveListTests(PortalTestCase):

    def setUp(self):
        self.norte = User.objects.get(username=NORTE)
        self.sur = User.objects.get(username=SUR)
        self.admin = User.objects.get(username="admin")

    def edit_territory(self, name="Territorio en vivo"):
        territory = Territory.objects.filter(delegation=self.north).first()
        return self.client.post(
            reverse("core:territorios_update", args=[territory.pk]),
            {"name": name, "delegation": self.north.pk, "description": ""},
        ), territory

    def test_the_list_page_connects_to_the_live_updates(self):
        self.login_as("admin")
        page = self.client.get(reverse("core:territorios_list"))
        self.assertContains(page, 'data-live-crud="territorios"')
        self.assertContains(page, "data-live-state")
        self.assertContains(page, "core/js/live-updates.js")
        script = (settings.BASE_DIR / "core/static/core/js/live-updates.js").read_text(encoding="utf-8")
        self.assertIn("/ws/crud/", script)
        self.assertIn("location.href", script)
        self.assertIn('[data-live-target="resultados"]', script)

    def test_the_deleted_users_view_is_live_too(self):
        self.login_as("admin")
        page = self.client.get(reverse("core:usuarios_list"), {"archivados": "solo"})
        self.assertContains(page, 'data-live-crud="usuarios"')

    def test_an_edit_is_announced_to_the_same_delegation_only_after_the_commit(self):
        self.login_as("admin")

        def edit():
            with self.captureOnCommitCallbacks(execute=False) as callbacks:
                response, _ = self.edit_territory()
            return response, callbacks

        def commit(callbacks):
            for callback in callbacks:
                callback()

        async def scenario():
            same, ok_same = await open_socket(self.norte, "/ws/crud/territorios/")
            other, ok_other = await open_socket(self.sur, "/ws/crud/territorios/")
            response, callbacks = await sync_to_async(edit)()
            quiet_before = await nothing_arrives(same)
            await sync_to_async(commit)(callbacks)
            got = json.loads(await same.receive_from())
            quiet_other = await nothing_arrives(other)
            await same.disconnect()
            await other.disconnect()
            return ok_same and ok_other, response.status_code, bool(callbacks), quiet_before, got, quiet_other

        ok, status, registered, quiet_before, got, quiet_other = async_to_sync(scenario)()
        self.assertTrue(ok)
        self.assertEqual(status, 302)
        self.assertTrue(registered, "el aviso debe quedar registrado para después del commit")
        self.assertTrue(quiet_before, "antes del commit no se avisa nada")
        self.assertEqual(got, {"type": "crud_changed", "slug": "territorios"})
        self.assertTrue(quiet_other, "la otra delegación no se entera del cambio")

    def test_creating_archiving_restoring_and_deleting_all_announce(self):
        self.login_as("admin")

        def act(method, url, data=None):
            with self.captureOnCommitCallbacks(execute=True):
                return getattr(self.client, method)(url, data or {})

        async def scenario():
            watcher, ok = await open_socket(self.admin, "/ws/crud/beneficiarios/")
            seen = []

            async def next_event():
                seen.append(json.loads(await watcher.receive_from(timeout=2)))

            await sync_to_async(act)("post", reverse("core:beneficiarios_create"), {"rut": "10000000-8", "name": "Persona En Vivo"})
            await next_event()
            person = await sync_to_async(Beneficiary.objects.get)(rut="10000000-8")
            for action in ("archive", "restore", "delete"):
                await sync_to_async(act)("post", reverse(f"core:beneficiarios_{action}", args=[person.pk]))
                await next_event()
            await watcher.disconnect()
            return ok, seen

        ok, seen = async_to_sync(scenario)()
        self.assertTrue(ok)
        self.assertEqual(seen, [{"type": "crud_changed", "slug": "beneficiarios"}] * 4)
        self.assertFalse(Beneficiary.objects.filter(rut="10000000-8").exists())

    def test_a_failed_save_announces_nothing(self):
        self.login_as("admin")

        def invalid():
            with self.captureOnCommitCallbacks(execute=True) as callbacks:
                response = self.client.post(reverse("core:beneficiarios_create"), {"rut": "", "name": ""})
            return response.status_code, callbacks

        async def scenario():
            watcher, _ = await open_socket(self.admin, "/ws/crud/beneficiarios/")
            status, callbacks = await sync_to_async(invalid)()
            quiet = await nothing_arrives(watcher)
            await watcher.disconnect()
            return status, callbacks, quiet

        status, callbacks, quiet = async_to_sync(scenario)()
        self.assertEqual(status, 200)
        self.assertEqual(callbacks, [])
        self.assertTrue(quiet)

    def test_the_socket_needs_the_permission_to_view_that_module(self):
        no_view = User.objects.create_user("sin.permisos", password="Hola123!")
        _, connected = async_to_sync(open_socket)(no_view, "/ws/crud/beneficiarios/")
        self.assertFalse(connected)

    def test_an_unknown_module_is_refused(self):
        _, connected = async_to_sync(open_socket)(self.admin, "/ws/crud/no-existe/")
        self.assertFalse(connected)

    def test_a_manager_viewing_all_delegations_hears_every_delegation(self):
        coordinacion = User.objects.get(username="coordinacion1")
        session = SessionStore()
        session[SESSION_DELEGATION] = ALL_DELEGATIONS
        layer = get_channel_layer()

        async def scenario():
            member, ok = await open_socket(coordinacion, "/ws/crud/territorios/", session)
            await layer.group_send(
                crud_group("territorios", self.south.pk),
                {"type": "crud_event", "payload": {"type": "crud_changed", "slug": "territorios"}},
            )
            got = json.loads(await member.receive_from())
            await member.disconnect()
            return ok, got

        ok, got = async_to_sync(scenario)()
        self.assertTrue(ok)
        self.assertEqual(got["slug"], "territorios")

    def test_every_module_can_be_watched_with_its_route_slug(self):
        for crud in registry.all():
            with self.subTest(slug=crud.slug):
                self.assertRegex(crud.slug, r"^[-a-zA-Z0-9_]+$")


class LiveDashboardTests(PortalTestCase):
    """Dashboard, tablero y validar: lo que cambia una persona lo ve otra que tiene la pantalla abierta."""

    def setUp(self):
        self.norte = User.objects.get(username=NORTE)
        self.sur = User.objects.get(username=SUR)
        self.admin = User.objects.get(username="admin")

    def save_north_activity(self, **changes):
        """Guarda una atención de la delegación Norte y ejecuta los avisos que quedan para el commit."""
        activity = Activity.objects.filter(delegation=self.north).first()
        for name, value in changes.items():
            setattr(activity, name, value)
        with self.captureOnCommitCallbacks(execute=True):
            activity.save()
        return activity

    def test_the_summary_pages_connect_to_the_live_updates(self):
        self.login_as("admin")
        dashboard = self.client.get(reverse("core:dashboard"))
        for page in (dashboard, self.client.get(reverse("core:delegation_board")), self.client.get(reverse("core:validate_list"))):
            self.assertContains(page, "data-live-page")
            self.assertContains(page, "data-live-region")
            self.assertContains(page, "data-live-state")
            self.assertContains(page, "core/js/live-updates.js")
        script = (settings.BASE_DIR / "core/static/core/js/live-updates.js").read_text(encoding="utf-8")
        self.assertIn("/ws/live/", script)
        self.assertIn('"[data-live-region]"', script)

    def test_a_live_refresh_does_not_count_as_a_new_visit(self):
        self.login_as("admin")
        self.client.get(reverse("core:dashboard"))
        second = self.client.get(reverse("core:dashboard"))
        self.assertEqual(second.context["visits"], 2)
        refreshed = self.client.get(reverse("core:dashboard"), HTTP_X_REQUESTED_WITH="fetch")
        self.assertEqual(refreshed.context["visits"], 2)
        self.assertContains(refreshed, "data-live-region")

    def test_the_live_socket_needs_a_session(self):
        _, connected = async_to_sync(open_socket)(AnonymousUser(), "/ws/live/")
        self.assertFalse(connected)

    def test_a_change_by_one_user_reaches_the_other_in_the_same_delegation_only(self):
        async def scenario():
            same, ok_same = await open_socket(self.norte, "/ws/live/")
            other, ok_other = await open_socket(self.sur, "/ws/live/")
            manager, ok_manager = await open_socket(self.admin, "/ws/live/")
            await sync_to_async(self.save_north_activity)(action_taken="Cambio hecho por A")
            got = json.loads(await same.receive_from(timeout=2))
            seen_by_manager = json.loads(await manager.receive_from(timeout=2))
            quiet_other = await nothing_arrives(other)
            quiet_same = await nothing_arrives(same)  # un solo aviso por guardado
            for communicator in (same, other, manager):
                await communicator.disconnect()
            return ok_same and ok_other and ok_manager, got, seen_by_manager, quiet_other, quiet_same

        ok, got, seen_by_manager, quiet_other, quiet_same = async_to_sync(scenario)()
        self.assertTrue(ok)
        self.assertEqual(got, {"type": "live_changed", "model": "operations.activity"})
        self.assertEqual(seen_by_manager, got)
        self.assertTrue(quiet_other, "la otra delegación no se entera")
        self.assertTrue(quiet_same)

    def test_a_general_change_reaches_every_delegation(self):
        period = Period.objects.first()

        async def scenario():
            north, _ = await open_socket(self.norte, "/ws/live/")
            south, _ = await open_socket(self.sur, "/ws/live/")

            def save():
                with self.captureOnCommitCallbacks(execute=True):
                    period.save()

            await sync_to_async(save)()
            got = [json.loads(await communicator.receive_from(timeout=2)) for communicator in (north, south)]
            await north.disconnect()
            await south.disconnect()
            return got

        for message in async_to_sync(scenario)():
            self.assertEqual(message, {"type": "live_changed", "model": "planning.period"})

    def test_moving_a_record_between_delegations_notifies_both(self):
        async def scenario():
            north, _ = await open_socket(self.norte, "/ws/live/")
            south, _ = await open_socket(self.sur, "/ws/live/")
            await sync_to_async(self.save_north_activity)(delegation=self.south)
            got = [json.loads(await communicator.receive_from(timeout=2)) for communicator in (north, south)]
            await north.disconnect()
            await south.disconnect()
            return got

        for message in async_to_sync(scenario)():
            self.assertEqual(message["type"], "live_changed")

    def test_deleting_and_changing_other_dashboard_data_also_announce(self):
        commitment = Commitment.objects.filter(delegation=self.north).first()
        evidence = Evidence.objects.filter(activity__delegation=self.north).first()

        async def scenario():
            watcher, _ = await open_socket(self.norte, "/ws/live/")
            seen = []

            def change(action):
                with self.captureOnCommitCallbacks(execute=True):
                    action()

            await sync_to_async(change)(commitment.save)
            seen.append(json.loads(await watcher.receive_from(timeout=2))["model"])
            await sync_to_async(change)(evidence.save)
            seen.append(json.loads(await watcher.receive_from(timeout=2))["model"])
            await sync_to_async(change)(commitment.delete)
            seen.append(json.loads(await watcher.receive_from(timeout=2))["model"])
            await watcher.disconnect()
            return seen

        self.assertEqual(
            async_to_sync(scenario)(),
            ["operations.commitment", "evidence.evidence", "operations.commitment"],
        )

    def test_a_rolled_back_change_announces_nothing(self):
        activity = Activity.objects.filter(delegation=self.north).first()

        def failing_save():
            with self.captureOnCommitCallbacks(execute=True) as callbacks:
                try:
                    with transaction.atomic():
                        activity.action_taken = "Se deshace"
                        activity.save()
                        raise RuntimeError("falla antes del commit")
                except RuntimeError:
                    pass
            return callbacks

        async def scenario():
            watcher, _ = await open_socket(self.norte, "/ws/live/")
            callbacks = await sync_to_async(failing_save)()
            quiet = await nothing_arrives(watcher)
            await watcher.disconnect()
            return callbacks, quiet

        callbacks, quiet = async_to_sync(scenario)()
        self.assertEqual(callbacks, [])
        self.assertTrue(quiet)

    def test_data_the_summary_screens_do_not_show_stays_quiet(self):
        def save():
            with self.captureOnCommitCallbacks(execute=True):
                AuditLog.objects.create(event="Prueba", affected_entity="Territory", record_id=1, user=self.admin)

        async def scenario():
            watcher, _ = await open_socket(self.norte, "/ws/live/")
            await sync_to_async(save)()
            quiet = await nothing_arrives(watcher)
            await watcher.disconnect()
            return quiet

        self.assertTrue(async_to_sync(scenario)())

    def test_the_real_edit_screen_announces_to_the_dashboard(self):
        """Recorrido completo: A guarda desde el formulario de atención y B, con su socket abierto, recibe el aviso."""
        self.login_as(NORTE)
        activity = Activity.objects.filter(delegation=self.north, author_officer=self.officer("F-1001")).first()
        self.assertIsNotNone(activity)

        def edit():
            data = self.activity_form_data(activity, action_taken="Editado por A")
            with self.captureOnCommitCallbacks(execute=True):
                return self.client.post(reverse("core:actividades_update", args=[activity.pk]), data).status_code

        async def scenario():
            watcher, _ = await open_socket(self.admin, "/ws/live/")
            status = await sync_to_async(edit)()
            got = json.loads(await watcher.receive_from(timeout=2))
            await watcher.disconnect()
            return status, got

        status, got = async_to_sync(scenario)()
        self.assertEqual(status, 302)
        self.assertEqual(got["type"], "live_changed")


SCRIPT = settings.BASE_DIR / "core/static/core/js/live-updates.js"


class LiveEverywhereTests(PortalTestCase):
    """v27: toda pantalla donde puedan coincidir varias personas se actualiza sola."""

    def setUp(self):
        self.login_as("admin")
        self.script = SCRIPT.read_text(encoding="utf-8")

    def test_the_attention_page_refreshes_only_its_results(self):
        page = self.client.get(reverse("core:atencion"))
        self.assertContains(page, "data-live-results")
        self.assertContains(page, "data-live-state")
        self.assertContains(page, "core/js/live-updates.js")
        self.assertIn("[data-live-results]", self.script)

    def test_a_list_listens_to_its_own_module_and_to_any_other_change(self):
        page = self.client.get(reverse("core:funcionarios_list"))
        self.assertContains(page, 'data-live-crud="funcionarios"')
        self.assertIn("crudChanged(panel.dataset.liveCrud), liveChanged", self.script)

    def test_every_record_sheet_is_live_and_knows_its_module(self):
        for slug, model in (("territorios", Territory), ("funcionarios", Officer), ("actividades", Activity), ("evidencias", Evidence)):
            with self.subTest(slug=slug):
                obj = model.objects.first()
                page = self.client.get(reverse(f"core:{slug}_detail", args=[obj.pk]))
                self.assertContains(page, "data-live-page")
                self.assertContains(page, "data-live-region")
                self.assertContains(page, f'data-live-slug="{slug}"')
                self.assertContains(page, "data-live-state")
        self.assertIn("page.dataset.liveSlug", self.script)

    def test_the_reports_and_the_administration_hub_are_live(self):
        for name in ("core:reports", "core:administration"):
            with self.subTest(name=name):
                page = self.client.get(reverse(name))
                self.assertContains(page, "data-live-page")
                self.assertContains(page, "data-live-region")
                self.assertContains(page, "data-live-state")

    def test_a_refresh_of_a_sheet_returns_the_same_region(self):
        obj = Territory.objects.first()
        refreshed = self.client.get(reverse("core:territorios_detail", args=[obj.pk]), HTTP_X_REQUESTED_WITH="fetch")
        self.assertContains(refreshed, "data-live-region")

    def test_the_other_screens_with_forms_stay_still(self):
        # Los formularios de alta y edición no se reemplazan solos: se perdería lo que la persona está escribiendo.
        page = self.client.get(reverse("core:territorios_create"))
        self.assertNotContains(page, "data-live-region")
        self.assertNotContains(page, "data-live-results")


class LiveCatalogChangesTests(PortalTestCase):
    """Los catálogos (territorios, beneficiarios, cargos…) avisan a todas las delegaciones."""

    def setUp(self):
        self.norte = User.objects.get(username=NORTE)
        self.sur = User.objects.get(username=SUR)
        self.admin = User.objects.get(username="admin")

    def save(self, obj):
        with self.captureOnCommitCallbacks(execute=True):
            obj.save()

    def test_a_catalog_change_reaches_every_delegation(self):
        territory = Territory.objects.filter(delegation=self.north).first()

        async def scenario():
            north, _ = await open_socket(self.norte, "/ws/live/")
            south, _ = await open_socket(self.sur, "/ws/live/")
            await sync_to_async(self.save)(territory)
            got = [json.loads(await c.receive_from(timeout=2)) for c in (north, south)]
            await north.disconnect()
            await south.disconnect()
            return got

        for message in async_to_sync(scenario)():
            self.assertEqual(message, {"type": "live_changed", "model": "organization.territory"})

    def test_a_beneficiary_change_is_announced(self):
        beneficiary = Beneficiary.objects.first()

        async def scenario():
            watcher, _ = await open_socket(self.norte, "/ws/live/")
            await sync_to_async(self.save)(beneficiary)
            got = json.loads(await watcher.receive_from(timeout=2))
            await watcher.disconnect()
            return got

        self.assertEqual(async_to_sync(scenario)()["model"], "organization.beneficiary")

    def test_an_audit_entry_reaches_the_audit_list_but_not_the_dashboards(self):
        def create():
            with self.captureOnCommitCallbacks(execute=True):
                AuditLog.objects.create(event="Prueba", affected_entity="Territory", record_id=1, user=self.admin)

        async def scenario():
            audit, ok = await open_socket(self.admin, "/ws/crud/auditoria/")
            dashboard, _ = await open_socket(self.admin, "/ws/live/")
            await sync_to_async(create)()
            got = json.loads(await audit.receive_from(timeout=2))
            quiet = await nothing_arrives(dashboard)
            await audit.disconnect()
            await dashboard.disconnect()
            return ok, got, quiet

        ok, got, quiet = async_to_sync(scenario)()
        self.assertTrue(ok)
        self.assertEqual(got, {"type": "crud_changed", "slug": "auditoria"})
        self.assertTrue(quiet)

    def test_an_edited_audit_entry_announces_nothing(self):
        entry = AuditLog.objects.create(event="Prueba", affected_entity="Territory", record_id=1, user=self.admin)

        async def scenario():
            audit, _ = await open_socket(self.admin, "/ws/crud/auditoria/")
            await sync_to_async(self.save)(entry)
            quiet = await nothing_arrives(audit)
            await audit.disconnect()
            return quiet

        self.assertTrue(async_to_sync(scenario)())


class EveryScreenIsLiveExceptFormsTests(PortalTestCase):
    """v28: todo listado y ficha se actualiza solo; los formularios de registro y edición, no."""

    def setUp(self):
        self.login_as("admin")

    def test_every_list_is_live_including_the_deleted_users_view(self):
        for crud in registry.all():
            if crud.list_redirect:
                continue
            with self.subTest(slug=crud.slug):
                page = self.client.get(reverse(f"core:{crud.route_name('list')}"))
                self.assertContains(page, f'data-live-crud="{crud.slug}"')
        archived = self.client.get(reverse("core:usuarios_list"), {"archivados": "solo"})
        self.assertContains(archived, 'data-live-crud="usuarios"')

    def test_the_registration_and_edit_forms_are_not_live(self):
        for name, args in (
            ("core:usuarios_create", []),
            ("core:funcionarios_create", []),
            ("core:profile", []),
        ):
            with self.subTest(name=name):
                page = self.client.get(reverse(name, args=args))
                self.assertNotContains(page, "data-live-region")
                self.assertNotContains(page, "data-live-crud")
                self.assertNotContains(page, "data-live-results")

    def test_the_evidence_validation_form_is_not_live(self):
        from evidence.models import Evidence

        evidence = Evidence.objects.first()
        page = self.client.get(reverse("core:validate_evidence", args=[evidence.pk]))
        self.assertNotContains(page, "data-live-region")
