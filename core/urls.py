from django.urls import path
from django.views.generic import RedirectView

from core import registry as _mantenedores  # noqa: F401  (al importarlo se registran los mantenedores)
from core import views
from core.crud import registry

app_name = "core"

urlpatterns = [
    # Ingreso y salida
    path("", views.PortalLoginView.as_view(), name="login"),
    path("salir/", views.PortalLogoutView.as_view(), name="logout"),
    # Pantallas especiales
    path("perfil/", views.profile, name="profile"),
    path("perfil/foto/<int:user_id>/", views.profile_photo, name="profile_photo"),
    path(
        "atencion/",
        views.AtencionView.as_view(crud=registry.get("actividades")),
        name="atencion",
    ),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("filas/", views.set_page_size, name="page_size"),
    path("contexto/", views.set_context, name="set_context"),
    path("evidencias/<int:pk>/archivo/", views.evidence_file, name="evidence_file"),
    path("evidencias/validar/", views.validate_list, name="validate_list"),
    path("evidencias/<int:pk>/validar/", views.validate_evidence, name="validate_evidence"),
    path("tablero/delegacion/", views.delegation_board, name="delegation_board"),
    path("informes/", views.reports, name="reports"),
    path("administracion/", views.administration, name="administration"),
    # Direcciones antiguas: redirigen a la pantalla equivalente.
    path(
        "actividades/registrar/",
        RedirectView.as_view(pattern_name="core:actividades_create"),
        name="registrar_actividad",
    ),
    path(
        "evidencias/cargar/",
        RedirectView.as_view(pattern_name="core:evidencias_create"),
        name="cargar_evidencia",
    ),
    path(
        "catalogo/servicios/",
        RedirectView.as_view(pattern_name="core:servicios_list"),
        name="catalogo_servicios",
    ),
    # Listado, ficha, formulario y archivo de cada modelo (ver core/registry.py)
    *registry.urls(),
]
