"""Deja atenciones en el Tubo de cartas (v51) en una base que ya tiene datos, sin tocar nada más.

Sirve para un servidor que ya cargó los datos de revisión antes de que existiera el tubo: crea actividades de ejemplo
(en «Ingresado», «Pendiente» y «Realizado»; «Vencido» lo calcula el sistema por la fecha) a partir de las atenciones
más recientes de cada delegación y les da a las cuentas de revisión los permisos del módulo. Repetirlo no duplica.
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction
from io import StringIO

from operations import tube
from operations.models import TubeItem
from organization.models import Delegation

ACCIONES = ("view", "add", "change", "delete")


class Command(BaseCommand):
    help = "Deja atenciones de ejemplo en el Tubo de cartas (no duplica) y da permisos a admin_a."

    def add_arguments(self, parser):
        parser.add_argument("--por-delegacion", type=int, default=55, help="Cuántas actividades debe tener cada delegación.")

    @transaction.atomic
    def handle(self, *args, **opciones):
        call_command("seed_roles", stdout=StringIO())
        total = 0
        for delegation in Delegation.objects.filter(deleted_at__isnull=True).order_by("pk"):
            nuevas = tube.load_sample(delegation, opciones["por_delegacion"])
            total += nuevas
            self.stdout.write(f"{delegation.name}: {nuevas} actividad(es) nueva(s) en el tubo.")
        permisos = Permission.objects.filter(
            content_type__app_label="operations", codename__in=[f"{accion}_tubeitem" for accion in ACCIONES]
        )
        cuenta = get_user_model().objects.filter(username="admin_a").first()
        if cuenta is not None:
            cuenta.user_permissions.add(*permisos)
            self.stdout.write("admin_a: permisos del Tubo de cartas al día.")
        self.stdout.write(self.style.SUCCESS(f"Listo. Actividades nuevas: {total}. En total hay {TubeItem._base_manager.count()}."))
