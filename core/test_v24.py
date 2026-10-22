import json

from asgiref.sync import async_to_sync, sync_to_async
from channels.layers import get_channel_layer
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.conf import settings
from django.contrib.auth.models import AnonymousUser, User
from django.contrib.sessions.backends.db import SessionStore
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.urls import reverse

from core.access import ALL_DELEGATIONS, SESSION_DELEGATION
from core.crud import registry
from core.models import AuditLog
from core.test_users import UserTestCase
from core.test_v16 import JPG, PNG, SIGNATURE_ONLY
from core.testing import PortalTestCase
from evidence.models import Evidence
from operations.models import Activity, Commitment
from organization.models import Beneficiary, Territory
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

    def test_the_deleted_users_view_is_not_live(self):
        self.login_as("admin")
        page = self.client.get(reverse("core:usuarios_list"), {"archivados": "solo"})
        self.assertNotContains(page, "data-live-crud")

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
        territory = Territory.objects.filter(delegation=self.north).first()

        def save():
            with self.captureOnCommitCallbacks(execute=True):
                territory.save()

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


class UserPhotoByAdminTests(UserTestCase):
    """El Super Usuario ve la foto de otra persona y puede cambiarla o quitársela al editar su usuario."""

    def setUp(self):
        self.target = User.objects.get(username="matias.quiroz")
        self.login_as("admin")

    def photo(self, content=PNG, name="foto.png", kind="image/png"):
        return SimpleUploadedFile(name, content, content_type=kind)

    def save(self, **changes):
        data = self.edit_data(self.target, **changes)
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(self.update_url(self.target), data)

    def stored(self):
        return User.objects.get(pk=self.target.pk).profile.photo

    def test_the_detail_shows_the_photo_or_says_there_is_none(self):
        detail = reverse("core:usuarios_detail", args=[self.target.pk])
        page = self.client.get(detail)
        self.assertContains(page, "Foto de perfil")
        self.assertNotContains(page, "avatar-lg")
        self.save(photo=self.photo())
        page = self.client.get(detail)
        self.assertContains(page, reverse("core:profile_photo", args=[self.target.pk]))
        self.assertContains(page, 'class="avatar avatar-lg"')

    def test_the_edit_form_accepts_files_and_shows_the_current_photo(self):
        page = self.client.get(self.update_url(self.target))
        self.assertContains(page, 'enctype="multipart/form-data"')
        self.assertContains(page, 'name="photo"')
        self.assertNotContains(page, 'name="remove_photo"')  # sin foto no hay nada que quitar
        self.save(photo=self.photo())
        page = self.client.get(self.update_url(self.target))
        self.assertContains(page, "photo-current")
        self.assertContains(page, 'name="remove_photo"')

    def test_the_superuser_sets_and_replaces_the_photo_of_another_person(self):
        response = self.save(photo=self.photo())
        self.assertEqual(response.status_code, 302)
        first = self.stored()
        self.assertTrue(first.name.startswith("fotos/"))
        self.assertTrue(first.storage.exists(first.name))
        event = AuditLog.objects.filter(event="Foto de perfil cambiada").latest("pk")
        self.assertEqual((event.user.username, event.record_id), ("admin", self.target.pk))
        self.save(photo=self.photo(JPG, "otra.jpg", "image/jpeg"))
        second = self.stored()
        self.assertNotEqual(second.name, first.name)
        self.assertFalse(second.storage.exists(first.name), "la foto anterior se borra al confirmar el cambio")
        self.assertTrue(second.storage.exists(second.name))

    def test_the_superuser_removes_the_photo_of_another_person(self):
        self.save(photo=self.photo())
        name = self.stored().name
        storage = self.stored().storage
        response = self.save(remove_photo="on")
        self.assertEqual(response.status_code, 302)
        self.assertFalse(self.stored())
        self.assertFalse(storage.exists(name))
        self.assertTrue(AuditLog.objects.filter(event="Foto de perfil quitada", record_id=self.target.pk, user__username="admin").exists())

    def test_saving_without_touching_the_photo_keeps_it(self):
        self.save(photo=self.photo())
        name = self.stored().name
        self.save(first_name="Matías S.")
        self.assertEqual(self.stored().name, name)

    def test_invalid_files_are_rejected_and_nothing_changes(self):
        for bad in (
            self.photo(SIGNATURE_ONLY),
            self.photo(b"texto", "nota.txt", "text/plain"),
            self.photo(PNG + b"\0" * (2 * 1024 * 1024), "grande.png"),
        ):
            with self.subTest(name=bad.name):
                response = self.save(photo=bad)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["form"].errors["photo"])
                self.assertFalse(self.stored())

    def test_a_new_photo_and_remove_together_is_an_error(self):
        self.save(photo=self.photo())
        response = self.save(photo=self.photo(JPG, "otra.jpg", "image/jpeg"), remove_photo="on")
        self.assertEqual(response.status_code, 200)
        self.assertIn("no las dos cosas", " ".join(response.context["form"].errors["remove_photo"]))

    def test_a_new_user_can_be_created_with_a_photo(self):
        data = self.user_data(photo=self.photo())
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse("core:usuarios_create"), data)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.get(username="ana.torres").profile.photo)

    def test_the_person_sees_the_photo_the_superuser_gave_them(self):
        self.save(photo=self.photo())
        self.login_as("matias.quiroz")
        page = self.client.get(reverse("core:profile"))
        self.assertContains(page, reverse("core:profile_photo", args=[self.target.pk]))
        self.assertEqual(self.client.get(reverse("core:profile_photo", args=[self.target.pk])).status_code, 200)

    def test_only_the_superuser_can_change_someone_elses_photo(self):
        self.login_as("matias.cavieres")
        response = self.client.post(self.update_url(self.target), self.edit_data(self.target, photo=self.photo()))
        self.assertEqual(response.status_code, 403)
        self.assertFalse(self.stored())


class DaphneDeployTests(PortalTestCase):

    base = settings.BASE_DIR

    def read(self, *parts):
        return self.base.joinpath(*parts).read_text(encoding="utf-8")

    def test_the_service_runs_daphne_on_the_asgi_application(self):
        unit = self.read("deploy", "sgr.service")
        self.assertIn("/opt/sgr/venv/bin/daphne", unit)
        self.assertIn("-b 127.0.0.1 -p 8000", unit)
        self.assertIn("--proxy-headers", unit)
        self.assertIn("sgr_project.asgi:application", unit)
        self.assertNotIn("gunicorn", unit)

    def test_apache_passes_the_websocket_before_everything_else(self):
        for name in ("apache-http.conf", "apache-https.conf"):
            text = self.read("deploy", "al2023", name)
            self.assertIn("ProxyPass /ws/ ws://127.0.0.1:8000/ws/", text, name)
            self.assertLess(text.index("ProxyPass /ws/"), text.index("ProxyPass / http://"), name)

    def test_nginx_passes_the_upgrade_headers_for_the_websocket(self):
        text = self.read("deploy", "nginx-sgr.conf")
        block = text[text.index("location /ws/") :]
        self.assertIn("proxy_set_header Upgrade $http_upgrade;", block)
        self.assertIn('proxy_set_header Connection "upgrade";', block)

    def test_the_upgrade_script_for_an_existing_server_is_safe_to_repeat(self):
        script = self.read("deploy", "al2023", "agregar_websocket.sh")
        self.assertIn("grep -q 'ProxyPass /ws/'", script)
        self.assertIn("httpd -t", script)
        self.assertIn("antes-websocket", script)
        self.assertIn("daemon-reload", script)

    def test_the_requirements_pin_channels_and_daphne(self):
        requirements = self.read("requirements.txt")
        self.assertRegex(requirements, r"(?m)^channels==\d+\.\d+\.\d+$")
        self.assertRegex(requirements, r"(?m)^daphne==\d+\.\d+\.\d+$")
