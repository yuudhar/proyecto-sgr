from django.core.management.base import BaseCommand, CommandError

from planning import calculation
from planning.models import Period


class Command(BaseCommand):
    help = (
        "Recalcula los indicadores (avance, cumplimiento, ponderado y semáforo) con las actividades que tienen "
        "evidencia aprobada. Solo guarda un indicador nuevo cuando el valor cambió."
    )

    def add_arguments(self, parser):
        parser.add_argument("--periodo", type=int, help="Identificador del período; sin él se recalculan todos.")
        parser.add_argument(
            "--incluir-cerrados", action="store_true", help="Recalcula también los períodos cerrados."
        )

    def handle(self, *args, **options):
        period = None
        if options["periodo"]:
            period = Period.objects.filter(pk=options["periodo"], deleted_at__isnull=True).first()
            if period is None:
                raise CommandError(f"No existe el período {options['periodo']}.")
        created = calculation.recalculate_all(include_closed=options["incluir_cerrados"], period=period)
        self.stdout.write(self.style.SUCCESS(f"Indicadores recalculados: {created} nuevo(s) o actualizado(s)."))
