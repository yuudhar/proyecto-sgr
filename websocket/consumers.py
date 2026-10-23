from asgiref.sync import async_to_sync
from channels.generic.websocket import JsonWebsocketConsumer

from core import registry as _mantenedores  # noqa: F401  (registra los mantenedores aunque aún no se haya cargado urls.py)
from core.crud import registry

from .services import crud_groups_for, live_groups_for


class CrudChangesConsumer(JsonWebsocketConsumer):
    """Avisa que un mantenedor cambió. No envía datos: el navegador vuelve a pedir la tabla por HTTP,
    y el listado vuelve a aplicar permisos, delegación, filtros y paginación."""

    def connect(self):
        user = self.scope["user"]
        if not user.is_authenticated:
            self.close()
            return
        slug = self.scope["url_route"]["kwargs"]["slug"]
        try:
            crud = registry.get(slug)
        except KeyError:
            self.close()
            return
        if not crud.has_perm(user, "view"):
            self.close()
            return
        self.groups_joined = crud_groups_for(self.scope, crud)
        if not self.groups_joined:
            self.close()
            return
        for name in self.groups_joined:
            async_to_sync(self.channel_layer.group_add)(name, self.channel_name)
        self.accept()

    def disconnect(self, close_code):
        for name in getattr(self, "groups_joined", []):
            async_to_sync(self.channel_layer.group_discard)(name, self.channel_name)

    def receive_json(self, content, **kwargs):
        return

    def crud_event(self, event):
        self.send_json(event["payload"])


class LiveConsumer(JsonWebsocketConsumer):
    """Avisa que cambió algún dato de la delegación (atenciones, evidencias, validaciones, compromisos,
    metas, indicadores...). Lo usan el dashboard, el tablero de delegación y la pantalla de validar:
    al recibir el aviso piden su propia pantalla por HTTP, que aplica permisos y delegación."""

    def connect(self):
        if not self.scope["user"].is_authenticated:
            self.close()
            return
        self.groups_joined = live_groups_for(self.scope)
        for name in self.groups_joined:
            async_to_sync(self.channel_layer.group_add)(name, self.channel_name)
        self.accept()

    def disconnect(self, close_code):
        for name in getattr(self, "groups_joined", []):
            async_to_sync(self.channel_layer.group_discard)(name, self.channel_name)

    def receive_json(self, content, **kwargs):
        return

    def live_event(self, event):
        self.send_json(event["payload"])
