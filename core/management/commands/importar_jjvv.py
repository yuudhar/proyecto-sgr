"""RF-049: importa la base de juntas de vecinos (planilla Excel «sin verificar») como organizaciones.

    python manage.py importar_jjvv base_datos_JJVV_sin_verificar.xlsx --simular
    python manage.py importar_jjvv base_datos_JJVV_sin_verificar.xlsx

* Es **idempotente por N.º de registro**: ejecutarlo dos veces no duplica; una fila ya cargada solo se actualiza si cambió.
* Con `--simular` hace todo el trabajo y lo deshace al final: no escribe nada, pero entrega el mismo informe.
* Las organizaciones nuevas quedan **sin verificar**; una importación posterior no cambia la marca de las existentes.
* Los territorios que no existan se crean en la delegación cuyo nombre contiene el del territorio; si ninguna calza
  (o calzan varias), se usa `--delegacion`. Sin ninguna de las dos, la organización se guarda sin territorio enlazado
  (el texto original queda en «territorio según la base») y el informe lo avisa.
"""
import unicodedata
from datetime import date, datetime

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from organization.models import CommunityOrganization, Delegation, Territory

NAME_MAX = 255


def plain(text):
    """Minúsculas, sin tildes y con espacios simples, para comparar nombres."""
    text = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode()
    return " ".join(text.lower().split())


# Las columnas de la planilla, como se comparan (sin tildes ni mayúsculas): «Nº REG. P.J.» pasa a «no reg. p.j.».
HEADERS = {
    "name": plain("ORGANIZACIONES"),
    "legal_address": plain("DOMICILIO LEGAL"),
    "territory": plain("TERRIT. DELEG."),
    "members": plain("SOCIOS ACTIVOS"),
    "constitution": plain("FECHA CONSTIT."),
    "registry": plain("Nº REG. P.J."),
    "registration": plain("FECHA INSCRIPC EN REG."),
    "directory": plain("REG. DIR. Nº"),
}


def clean(text, upper=False):
    text = " ".join(str(text or "").split())
    return text.upper() if upper else text


def as_int(value):
    if value in (None, ""):
        return None
    try:
        number = int(float(str(value).replace(",", ".").strip()))
    except ValueError:
        return None
    return number if number >= 0 else None


def as_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    for pattern in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            continue
    return None


def read_rows(path):
    from openpyxl import load_workbook

    try:
        workbook = load_workbook(path, read_only=True, data_only=True)
    except (OSError, ValueError, KeyError) as error:
        raise CommandError(f"No se pudo abrir «{path}»: {error}") from error
    sheet = workbook.worksheets[0]
    rows = sheet.iter_rows(values_only=True)
    header = next(rows, None)
    if header is None:
        raise CommandError("La planilla está vacía.")
    columns = {plain(value): index for index, value in enumerate(header) if value}
    missing = [label for label in HEADERS.values() if label not in columns]
    if missing:
        raise CommandError("Faltan columnas en la planilla: " + ", ".join(missing))
    for number, row in enumerate(rows, start=2):
        if not any(value not in (None, "") for value in row):
            continue
        yield number, {key: row[columns[label]] if columns[label] < len(row) else None for key, label in HEADERS.items()}


class Territories:
    """Busca o crea los territorios por nombre, sin importar tildes ni mayúsculas."""

    def __init__(self, default_delegation):
        self.default = default_delegation
        self.cache = {}
        self.created = []
        self.unlinked = set()
        self.delegations = list(Delegation.objects.filter(deleted_at__isnull=True))

    def find(self, text):
        if not text:
            return None
        key = plain(text)
        if key in self.cache:
            return self.cache[key]
        territory = next(
            (each for each in Territory.objects.filter(deleted_at__isnull=True) if plain(each.name) == key), None
        )
        if territory is None:
            delegation = self.delegation_for(key)
            if delegation is None:
                self.unlinked.add(text)
            else:
                territory = Territory.objects.create(name=text, delegation=delegation)
                self.created.append(f"{text} ({delegation.name})")
        self.cache[key] = territory
        return territory

    def delegation_for(self, key):
        matches = [each for each in self.delegations if key in plain(each.name)]
        if len(matches) == 1:
            return matches[0]
        return self.default


class Command(BaseCommand):
    help = "Importa la base de juntas de vecinos (Excel) como organizaciones, sin duplicar por N.º de registro."

    def add_arguments(self, parser):
        parser.add_argument("archivo", help="Planilla Excel con la base de organizaciones.")
        parser.add_argument("--simular", action="store_true", help="Calcula el informe sin escribir nada.")
        parser.add_argument(
            "--delegacion",
            default="",
            help="Delegación donde crear los territorios que no calcen con el nombre de ninguna.",
        )

    def handle(self, *args, **options):
        default = None
        if options["delegacion"]:
            default = Delegation.objects.filter(name__iexact=options["delegacion"], deleted_at__isnull=True).first()
            if default is None:
                raise CommandError(f"No existe la delegación «{options['delegacion']}».")
        simulate = options["simular"]
        with transaction.atomic():
            report = self.load(options["archivo"], default)
            if simulate:
                transaction.set_rollback(True)
        self.show(report, simulate)

    def load(self, path, default):
        territories = Territories(default)
        report = {
            "read": 0, "created": 0, "updated": 0, "unchanged": 0, "discarded": [],
            "without_territory": 0, "without_members": 0,
            "territories": territories,
        }
        seen = set()
        for number, row in read_rows(path):
            report["read"] += 1
            name = clean(row["name"])[:NAME_MAX]
            registry = as_int(row["registry"])
            if not name:
                report["discarded"].append(f"fila {number}: sin nombre")
                continue
            if registry is None:
                report["discarded"].append(f"fila {number}: sin N.º de registro ({name})")
                continue
            if registry in seen:
                report["discarded"].append(f"fila {number}: N.º de registro {registry} repetido en la planilla ({name})")
                continue
            seen.add(registry)
            territory_text = clean(row["territory"], upper=True)
            members = as_int(row["members"])
            if not territory_text:
                report["without_territory"] += 1
            if members is None:
                report["without_members"] += 1
            values = {
                "name": name,
                "legal_address": clean(row["legal_address"])[:255],
                "territory": territories.find(territory_text),
                "territory_text": territory_text[:100],
                "active_members": members,
                "constitution_date": as_date(row["constitution"]),
                "registration_date": as_date(row["registration"]),
                "directory_number": as_int(row["directory"]),
            }
            existing = CommunityOrganization.objects.filter(registry_number=registry).first()
            if existing is None:
                CommunityOrganization.objects.create(registry_number=registry, verified=False, **values)
                report["created"] += 1
                continue
            changed = [field for field, value in values.items() if getattr(existing, field) != value]
            if changed:
                for field in changed:
                    setattr(existing, field, values[field])
                existing.save()
                report["updated"] += 1
            else:
                report["unchanged"] += 1
        return report

    def show(self, report, simulate):
        out = self.stdout.write
        out("Simulación: no se escribió nada." if simulate else "Importación terminada.")
        out(f"Filas leídas: {report['read']}")
        out(f"Organizaciones creadas: {report['created']}")
        out(f"Organizaciones actualizadas: {report['updated']}")
        out(f"Organizaciones sin cambios: {report['unchanged']}")
        out(f"Filas descartadas: {len(report['discarded'])}")
        for text in report["discarded"][:20]:
            out(f"  - {text}")
        out(f"Filas sin territorio: {report['without_territory']}")
        out(f"Filas sin socios: {report['without_members']}")
        territories = report["territories"]
        out(f"Territorios creados: {len(territories.created)}")
        for text in territories.created:
            out(f"  - {text}")
        if territories.unlinked:
            out(
                "Territorios sin delegación (se guardó solo su texto; usa --delegacion para crearlos): "
                + ", ".join(sorted(territories.unlinked))
            )
