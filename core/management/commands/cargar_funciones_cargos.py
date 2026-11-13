from datetime import date

from django.core.management.base import BaseCommand
from django.db import transaction

from organization.descriptor import DESCRIPTOR, VALID_FROM
from organization.models import Position, PositionFunction


class Command(BaseCommand):
    help = (
        "Carga los siete cargos del descriptor de funciones 2026 con su descripción y sus funciones. "
        "Se puede correr las veces que haga falta: no repite lo que ya está ni pisa lo que se editó a mano."
    )

    @transaction.atomic
    def handle(self, *args, **options):
        desde = date.fromisoformat(VALID_FROM)
        cargos_nuevos = descripciones = funciones_nuevas = 0
        for cargo in DESCRIPTOR:
            position = Position.objects.filter(name__iexact=cargo["name"], deleted_at__isnull=True).first()
            if position is None:
                position = Position.objects.create(name=cargo["name"], description=cargo["description"], valid_from=desde)
                cargos_nuevos += 1
                descripciones += 1
            elif not position.description:
                position.description = cargo["description"]
                position.save(update_fields=["description", "updated_at"])
                descripciones += 1
            existentes = {
                (f.group, f.text.casefold())
                for f in PositionFunction._base_manager.filter(position=position)
            }
            siguiente = {}
            for grupo, texto in cargo["functions"]:
                clave = (grupo, texto.casefold())
                if clave in existentes:
                    continue
                orden = siguiente.get(grupo)
                if orden is None:
                    orden = PositionFunction._base_manager.filter(position=position, group=grupo).count()
                orden += 1
                siguiente[grupo] = orden
                PositionFunction.objects.create(position=position, group=grupo, order=orden, text=texto)
                funciones_nuevas += 1
        total = len(DESCRIPTOR)
        self.stdout.write(
            f"Descriptor 2026: {total} cargos revisados, {cargos_nuevos} creados, {descripciones} con descripción "
            f"cargada y {funciones_nuevas} funciones nuevas."
        )
