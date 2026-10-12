"""Carga (o borra) un volumen grande de atenciones de prueba para las pruebas de estrés.

    python manage.py cargar_volumen_estres --atenciones 5000 --beneficiarios 1000
    python manage.py cargar_volumen_estres --limpiar

Las atenciones se marcan con «(carga de prueba)» al final de la descripción (las que crea la herramienta de estrés
llevan el contacto «[ESTRES] …») y los beneficiarios tienen RUT desde 90.000.000, así --limpiar los encuentra y solo
borra lo que se creó para las pruebas. Requiere haber corrido antes seed_demo_data.
"""

import random
from datetime import date, timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from operations.models import Activity
from organization.models import Beneficiary, Delegation, Item, Officer

MARCA = "(carga de prueba)"
MARCA_ESTRES = "[ESTRES]"
RUT_BASE = 90_000_000
NOMBRES = ["Rosa", "Juan", "María", "Pedro", "Ana", "Luis", "Carla", "Diego", "Sofía", "Mateo", "Elena", "Jorge"]
APELLIDOS = ["Núñez", "Pérez", "González", "Rojas", "Díaz", "Soto", "Araya", "Castillo", "Muñoz", "Tapia", "Rivera", "Vega"]
SOLICITUDES = [
    "Solicita certificado de residencia",
    "Consulta por ayuda social",
    "Reclama por luminaria en mal estado",
    "Pide visita domiciliaria",
    "Consulta por subsidio de agua potable",
    "Solicita orientación sobre trámites municipales",
]


def digito_verificador(numero):
    suma, factor = 0, 2
    for cifra in reversed(str(numero)):
        suma += int(cifra) * factor
        factor = 2 if factor == 7 else factor + 1
    resto = 11 - suma % 11
    return "0" if resto == 11 else "K" if resto == 10 else str(resto)


class Command(BaseCommand):
    help = "Carga o borra atenciones y beneficiarios de prueba para las pruebas de estrés."

    def add_arguments(self, parser):
        parser.add_argument("--atenciones", type=int, default=5000)
        parser.add_argument("--beneficiarios", type=int, default=1000)
        parser.add_argument("--limpiar", action="store_true", help="Borra lo que creó este comando.")

    @transaction.atomic
    def handle(self, *args, **opciones):
        if opciones["limpiar"]:
            marcadas = Activity.objects.filter(request_description__endswith=MARCA) | Activity.objects.filter(contact_name__startswith=MARCA_ESTRES)
            actividades = marcadas.delete()[0]
            beneficiarios = Beneficiary.objects.filter(rut__startswith="90").filter(rut__regex=r"^90\d{6}-").delete()[0]
            self.stdout.write(self.style.SUCCESS(f"Borrados: {actividades} registros de atención y {beneficiarios} beneficiarios de prueba."))
            return

        funcionarios = list(Officer.objects.filter(deleted_at__isnull=True, delegation__isnull=False))
        items = list(Item.objects.filter(deleted_at__isnull=True))
        if not funcionarios or not items:
            raise CommandError("Faltan funcionarios o ítems: corre antes `python manage.py seed_demo_data`.")
        azar = random.Random(2026)

        existentes = Beneficiary.objects.filter(rut__regex=r"^90\d{6}-").count()
        nuevos = []
        for i in range(existentes, existentes + opciones["beneficiarios"]):
            numero = RUT_BASE + i
            nuevos.append(
                Beneficiary(
                    rut=f"{numero}-{digito_verificador(numero)}",
                    name=f"{azar.choice(NOMBRES)} {azar.choice(APELLIDOS)} {azar.choice(APELLIDOS)}",
                    phone=f"+56 9 {azar.randint(1000, 9999)} {azar.randint(1000, 9999)}",
                    address=f"Calle {azar.randint(1, 300)} N° {azar.randint(1, 3000)}",
                )
            )
        Beneficiary.objects.bulk_create(nuevos, batch_size=500)
        beneficiarios = list(Beneficiary.objects.filter(rut__regex=r"^90\d{6}-"))

        hoy = date.today()
        actividades = []
        for i in range(opciones["atenciones"]):
            funcionario = azar.choice(funcionarios)
            persona = azar.choice(beneficiarios) if beneficiarios else None
            actividades.append(
                Activity(
                    date=hoy - timedelta(days=azar.randint(0, 365)),
                    request_description=f"{azar.choice(SOLICITUDES)} {MARCA}",
                    contact_name=persona.name if persona else "Persona",
                    beneficiary=persona,
                    item=azar.choice(items),
                    delegation=funcionario.delegation,
                    author_officer=funcionario,
                )
            )
        Activity.objects.bulk_create(actividades, batch_size=500)
        self.stdout.write(
            self.style.SUCCESS(
                f"Cargados {len(nuevos)} beneficiarios y {len(actividades)} atenciones de prueba "
                f"(total en la base: {Activity.objects.count()} atenciones, {Delegation.objects.count()} delegaciones)."
            )
        )
