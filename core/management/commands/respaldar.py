from django.core.management.base import BaseCommand, CommandError

from core import respaldo


class Command(BaseCommand):
    help = (
        "Hace un respaldo de la base de datos y de los archivos subidos (evidencias y fotos) en BACKUP_DIR "
        "y borra los respaldos con más de BACKUP_KEEP_DAYS días. Lo corre solo el temporizador sgr-respaldo."
    )

    def add_arguments(self, parser):
        parser.add_argument("--dias", type=int, help="Días que se guardan los respaldos (por defecto BACKUP_KEEP_DAYS).")
        parser.add_argument("--sin-limpiar", action="store_true", help="No borra los respaldos antiguos.")
        parser.add_argument("--listar", action="store_true", help="Solo muestra los respaldos que hay, sin hacer uno nuevo.")

    def handle(self, *args, **options):
        if options["listar"]:
            backups = respaldo.list_backups()
            if not backups:
                self.stdout.write(f"No hay respaldos en {respaldo.backup_dir()}.")
            for data in backups:
                mb = (data["base"]["bytes"] + data["archivos"]["bytes"]) / 1024 / 1024
                self.stdout.write(f"{data['sello']}  {data['creado']}  {data['version']}  {mb:.1f} MB")
            return
        try:
            data = respaldo.make_backup()
        except respaldo.BackupError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            self.style.SUCCESS(
                f"Respaldo {data['sello']} listo en {respaldo.backup_dir()}: base {data['base']['bytes']} bytes, "
                f"archivos {data['archivos']['bytes']} bytes ({data['archivos']['elementos']} elementos)."
            )
        )
        if not options["sin_limpiar"]:
            removed = respaldo.apply_retention(options["dias"])
            if removed:
                self.stdout.write(f"Se borraron {len(removed)} respaldo(s) antiguo(s): {', '.join(removed)}.")
