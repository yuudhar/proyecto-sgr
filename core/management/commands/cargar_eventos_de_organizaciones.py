"""Deja eventos de ejemplo en las organizaciones de una base que ya tiene los datos de revisión (v52).

Sirve para un servidor que cargó los datos antes de que existieran los eventos: a cada organización de la carga de
revisión (número de registro 7001 en adelante) le pone su período de actividades, una descripción y 3 eventos acordes a
su tipo, y da a las cuentas de revisión los permisos del módulo. No toca lo que ya tenga fechas, descripción o eventos,
así que repetirlo no duplica.
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.management.base import BaseCommand
from django.db import transaction

from core.management.commands.cargar_datos_revision import ORGANIZACIONES, PERMISOS_EXTRA, Command as Carga
from organization.models import CommunityOrganization, OrganizationEvent

CUENTAS = {"admin_a": "administrador", "editor_a": "editor", "lector_a": "lector", "lector_b": "lector"}


class Command(BaseCommand):
    help = "Deja eventos de ejemplo en las organizaciones de la carga de revisión (no duplica) y da permisos a las cuentas."

    @transaction.atomic
    def handle(self, *args, **opciones):
        organizaciones = list(
            CommunityOrganization.objects.filter(
                deleted_at__isnull=True, registry_number__gte=7001, registry_number__lte=7000 + ORGANIZACIONES
            ).select_related("territory")
        )
        if not organizaciones:
            self.stdout.write("No hay organizaciones de la carga de revisión: no se hizo nada.")
            return
        nuevos = Carga().eventos_de_organizaciones(organizaciones)
        User = get_user_model()
        for username, rol in CUENTAS.items():
            usuario = User.objects.filter(username=username).first()
            if usuario is None:
                continue
            for etiqueta in PERMISOS_EXTRA[rol]:
                modulo, accion = etiqueta.split(":")
                if modulo != "organization.organizationevent":
                    continue
                app, modelo = modulo.split(".")
                permiso = Permission.objects.filter(
                    content_type__app_label=app, content_type__model=modelo, codename=f"{accion}_{modelo}"
                ).first()
                if permiso is not None:
                    usuario.user_permissions.add(permiso)
            self.stdout.write(f"{username}: permisos de los eventos al día.")
        self.stdout.write(
            self.style.SUCCESS(f"Listo. Eventos nuevos: {nuevos}. En total hay {OrganizationEvent._base_manager.count()}.")
        )
