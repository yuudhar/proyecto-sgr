from django.core.management.base import BaseCommand, CommandError

from core import respaldo


class Command(BaseCommand):
    help = (
        "Restaura la base de datos y los archivos subidos desde un respaldo (sello que muestra «respaldar --listar»). "
        "Antes de tocar nada deja un respaldo de seguridad de lo que hay."
    )

    def add_arguments(self, parser):
        parser.add_argument("sello", help="Sello del respaldo, por ejemplo sgr-20261112-033000.")
        parser.add_argument("--confirmar", action="store_true", help="Sin esta opción solo se muestra qué se haría.")
        parser.add_argument("--sin-archivos", action="store_true", help="Restaura solo la base, no las evidencias ni las fotos.")

    def handle(self, *args, **options):
        try:
            data = respaldo.find_backup(options["sello"])
            respaldo.check_files(data)
            plan = (
                f"Respaldo {data['sello']} ({data['creado']}, versión {data['version']}): "
                f"base de datos {'y archivos ' if not options['sin_archivos'] else ''}"
                f"se reemplazan por lo que contiene."
            )
            if not options["confirmar"]:
                self.stdout.write(plan)
                self.stdout.write(self.style.WARNING("No se cambió nada. Para restaurar de verdad, repite con --confirmar."))
                return
            _data, safety = respaldo.restore_backup(options["sello"], with_files=not options["sin_archivos"])
        except respaldo.BackupError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(f"Restauración lista. Lo que había antes quedó en el respaldo {safety['sello']}."))
        self.stdout.write("Reinicia el servicio para que tome los datos: sudo systemctl restart sgr")
