from django.urls import path
from . import views

app_name = "core"

urlpatterns = [
    path("", views.login_view, name="login"),
    path("dashboard/", views.dashboard_view, name="dashboard"),
    path("actividades/registrar/", views.registrar_actividad_view, name="registrar_actividad"),
    path("evidencias/cargar/", views.cargar_evidencia_view, name="cargar_evidencia"),
    path("evidencias/validar/", views.validar_evidencia_view, name="validar_evidencia"),
    path("agenda/", views.agenda_colectiva_view, name="agenda_colectiva"),
    path("tablero/delegacion/", views.tablero_delegacion_view, name="tablero_delegacion"),
    path("administracion/", views.administracion_view, name="administracion"),
    path("informes/", views.informes_view, name="informes"),
    path("catalogo/servicios/", views.catalogo_servicios_view, name="catalogo_servicios"),
]
