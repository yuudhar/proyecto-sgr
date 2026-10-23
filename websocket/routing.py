from django.urls import path

from .consumers import CrudChangesConsumer, LiveConsumer

websocket_urlpatterns = [
    path("ws/crud/<slug:slug>/", CrudChangesConsumer.as_asgi()),
    path("ws/live/", LiveConsumer.as_asgi()),
]
