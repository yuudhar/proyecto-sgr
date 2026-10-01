from django.core.management.base import BaseCommand

from operations.models import ManagementType

INITIAL_VALUES = [
    "Atención a usuario presencial",
    "Visita a terreno",
    "Entrega de informe",
    "Entrega de beneficio",
    "Emergencia",
    "Otras gestiones",
]


class Command(BaseCommand):
    help = "Crea el catálogo inicial de ManagementType (igual al script SQL)."

    def handle(self, *args, **options):
        created_count = 0
        for name in INITIAL_VALUES:
            _, was_created = ManagementType.objects.get_or_create(name=name)
            created_count += int(was_created)
        self.stdout.write(
            self.style.SUCCESS(
                f"ManagementType: {created_count} nuevo(s) de "
                f"{len(INITIAL_VALUES)} totales."
            )
        )
