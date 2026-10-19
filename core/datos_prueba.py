from datetime import date, timedelta
from io import StringIO

from django.contrib.auth.models import Group, User
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts.delegations import sync_extra_delegations
from accounts.models import UserProfile
from core import uploads
from core.models import AuditLog
from evidence.models import Evidence, Validation
from operations.models import Activity, Commitment, Followup, ManagementType
from organization.models import (
    Beneficiary,
    Delegation,
    Item,
    Officer,
    Position,
    PositionItem,
    Service,
    Territory,
)
from planning.models import Adjustment, Goal, Indicator, Period

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "Hola123!"

OFFICER_NORTH_USERNAME = "matias.cavieres"
OFFICER_NORTH_PASSWORD = "Hola123!"

OFFICER_SOUTH_USERNAME = "matias.quiroz"
OFFICER_SOUTH_PASSWORD = "Hola123!"

COORDINACION_USERNAME = "coordinacion1"
COORDINACION_PASSWORD = "Hola123!"

JEFATURA_USERNAME = "jefatura1"
JEFATURA_PASSWORD = "Hola123!"

SUPERVISION_USERNAME = "supervision1"
SUPERVISION_PASSWORD = "Hola123!"

CONSULTA_USERNAME = "consulta1"
CONSULTA_PASSWORD = "Hola123!"

DEMO_EMAIL_DOMAIN = "sgr.example"


def demo_pdf(text):
    safe = text.replace("\\", "").replace("(", "").replace(")", "")
    stream = f"BT /F1 14 Tf 72 720 Td ({safe}) Tj ET".encode("latin-1", "replace")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = b"%PDF-1.4\n"
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    start = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode() + b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n".encode()
    return out


class CargaDatosPrueba(BaseCommand):

    def get_delegation(self, name, scope, color, manager, address, commune):
        delegation, created = Delegation.objects.get_or_create(
            name=name,
            defaults={
                "status": Delegation.Status.ACTIVE,
                "scope": scope,
                "color": color,
                "managers": manager,
                "address": address,
                "commune": commune,
            },
        )
        if not created:
            if delegation.color == Delegation._meta.get_field("color").default:
                delegation.color = color
            if not delegation.managers:
                delegation.managers = manager
            if not delegation.address:
                delegation.address = address
            if not delegation.commune:
                delegation.commune = commune
            delegation.save()
        return delegation

    def get_item(self, name, description, **defaults):
        item, created = Item.objects.get_or_create(
            name=name, defaults={"description": description, **defaults}
        )
        if not created and not item.description:
            item.description = description
            item.save()
        return item

    @transaction.atomic
    def write_demo_files(self):
        for evidence in Evidence.objects.all():
            name = evidence.file_link.name
            if not name:
                continue
            content = demo_pdf(f"Evidencia de demostración {evidence.unique_code}")
            if not evidence.file_link.storage.exists(name):
                evidence.file_link.storage.save(name, ContentFile(content))
            if not evidence.metadata:
                evidence.metadata = "\n".join(
                    [
                        f"Archivo original: {name.rsplit('/', 1)[-1]}",
                        "Tipo: PDF",
                        f"Tamaño: {uploads.readable_size(len(content))}",
                    ]
                )
                evidence.save(update_fields=["metadata", "updated_at"])

    def handle(self, *args, **options):
        self.stdout.write("Cargando roles y catálogo de tipos de gestión...")
        call_command("seed_roles")
        call_command("seed_management_types")

        today = date.today()

        north = self.get_delegation(
            "Delegación Norte", "Sector norte", "#1D4E89", "Diego Fuentes", "Av. Cuatro Esquinas 1200", "La Serena"
        )
        south = self.get_delegation(
            "Delegación Sur", "Sector sur", "#2E7D5B", "Ignacio Vidal", "Av. Juan Bohón 850", "La Serena"
        )

        position_social, _ = Position.objects.get_or_create(
            name="Encargado Social", defaults={"valid_from": today - timedelta(days=365)}
        )
        position_coord, _ = Position.objects.get_or_create(
            name="Coordinador de Terreno",
            defaults={"valid_from": today - timedelta(days=365)},
        )
        position_jefatura, _ = Position.objects.get_or_create(
            name="Jefe de Delegación",
            defaults={"valid_from": today - timedelta(days=365)},
        )
        position_analyst, _ = Position.objects.get_or_create(
            name="Analista de Datos",
            defaults={"valid_from": today - timedelta(days=180)},
        )

        item_social = self.get_item(
            "Atención Social",
            "Atención a vecinos y vecinas que piden apoyo social: orientación, visitas y seguimiento.",
            calculation_type=Item.CalculationType.QUALITATIVE,
        )
        item_home_visit = self.get_item(
            "Visita Domiciliaria",
            "Visita al domicilio del vecino para conocer su situación.",
            parent_item=item_social,
            calculation_type=Item.CalculationType.QUALITATIVE,
        )
        item_phone_followup = self.get_item(
            "Seguimiento Telefónico",
            "Llamado de seguimiento a un caso que ya fue atendido.",
            parent_item=item_social,
            calculation_type=Item.CalculationType.QUALITATIVE,
        )
        item_aid_delivery = self.get_item(
            "Entrega de Ayudas Sociales",
            "Entrega de ayudas sociales a quienes cumplen los requisitos.",
            calculation_type=Item.CalculationType.QUANTITATIVE,
        )
        item_territorial_coordination = self.get_item(
            "Coordinación Territorial",
            "Coordinación con las organizaciones y dirigentes del territorio.",
            calculation_type=Item.CalculationType.QUALITATIVE,
        )

        for position in (position_social, position_coord, position_jefatura):
            PositionItem.objects.get_or_create(
                position=position,
                item=item_social,
                defaults={
                    "weight": 50,
                    "valid_from": today - timedelta(days=365),
                    "kind": PositionItem.Kind.NORMAL,
                },
            )
        PositionItem.objects.get_or_create(
            position=position_social,
            item=item_aid_delivery,
            defaults={
                "weight": 10,
                "valid_from": today - timedelta(days=365),
                "kind": PositionItem.Kind.BONUS,
                "max_cap": 15,
            },
        )
        PositionItem.objects.get_or_create(
            position=position_coord,
            item=item_aid_delivery,
            defaults={
                "weight": 10,
                "valid_from": today - timedelta(days=365),
                "kind": PositionItem.Kind.PENALTY,
                "max_cap": 10,
            },
        )

        service_social_aid, _ = Service.objects.get_or_create(
            name="Ayuda Social", defaults={"status": Service.Status.ACTIVE}
        )
        service_housing, _ = Service.objects.get_or_create(
            name="Vivienda", defaults={"status": Service.Status.ACTIVE}
        )
        service_certificate, _ = Service.objects.get_or_create(
            name="Certificado de Residencia", defaults={"status": Service.Status.ACTIVE}
        )
        service_subsidy, _ = Service.objects.get_or_create(
            name="Postulación a Subsidio", defaults={"status": Service.Status.ACTIVE}
        )

        territory_north, _ = Territory.objects.get_or_create(
            name="Territorio 1", delegation=north
        )
        territory_north_2, _ = Territory.objects.get_or_create(
            name="Territorio 2", delegation=north
        )
        territory_south, _ = Territory.objects.get_or_create(
            name="Territorio 1", delegation=south
        )
        territory_south_2, _ = Territory.objects.get_or_create(
            name="Territorio 2", delegation=south
        )

        beneficiaries = {}
        for rut, name, phone, address in [
            ("11111111-1", "María Pérez", "+56911111111", "Los Aromos 1234"),
            ("22222222-2", "Juan Soto", "+56922222222", "Pasaje Las Rosas 56"),
            ("33333333-3", "Ana Rojas", "+56933333333", "Av. del Mar 789"),
            ("44444444-4", "Pedro Díaz", "+56944444444", "Calle Prat 321"),
            ("55555555-5", "Carla Muñoz", "+56955555555", "Los Olivos 4450"),
            ("66666666-6", "Luis Herrera", "+56966666666", "Arturo Prat 1020"),
            ("77777777-7", "Fernanda Silva", "+56977777777", "Pasaje El Sauce 15"),
            ("88888888-8", "Roberto Paredes", "+56988888888", "Balmaceda 2280"),
        ]:
            beneficiary, created = Beneficiary.objects.get_or_create(
                rut=rut,
                defaults={"name": name, "phone": phone, "address": address},
            )
            if not created and not beneficiary.address:
                beneficiary.address = address
                beneficiary.save()
            beneficiaries[rut] = beneficiary

        officer_north_1, _ = Officer.objects.get_or_create(
            institutional_id="F-1001",
            defaults={
                "name": "Matías Cavieres",
                "status": Officer.Status.ACTIVE,
                "delegation": north,
                "position": position_social,
            },
        )
        officer_north_2, _ = Officer.objects.get_or_create(
            institutional_id="F-1002",
            defaults={
                "name": "Diego Fuentes",
                "status": Officer.Status.ACTIVE,
                "delegation": north,
                "position": position_coord,
            },
        )
        officer_south_1, _ = Officer.objects.get_or_create(
            institutional_id="F-2001",
            defaults={
                "name": "Matías Quiroz",
                "status": Officer.Status.ACTIVE,
                "delegation": south,
                "position": position_social,
            },
        )
        officer_south_2, _ = Officer.objects.get_or_create(
            institutional_id="F-2002",
            defaults={
                "name": "Ignacio Vidal",
                "status": Officer.Status.ACTIVE,
                "delegation": south,
                "position": position_coord,
            },
        )
        officer_north_jefatura, _ = Officer.objects.get_or_create(
            institutional_id="F-1003",
            defaults={
                "name": "Jefatura Norte",
                "status": Officer.Status.ACTIVE,
                "delegation": north,
                "position": position_jefatura,
            },
        )
        officer_north_consulta, _ = Officer.objects.get_or_create(
            institutional_id="F-1004",
            defaults={
                "name": "Consulta Norte",
                "status": Officer.Status.ACTIVE,
                "delegation": north,
                "position": position_social,
            },
        )
        officer_south_consulta, _ = Officer.objects.get_or_create(
            institutional_id="F-2004",
            defaults={
                "name": "Consulta Sur",
                "status": Officer.Status.ACTIVE,
                "delegation": south,
                "position": position_social,
            },
        )
        officer_north_reader, _ = Officer.objects.get_or_create(
            institutional_id="F-1005",
            defaults={
                "name": "Consulta Delegación Norte",
                "status": Officer.Status.ACTIVE,
                "delegation": north,
                "position": position_jefatura,
            },
        )
        officer_south_jefatura, _ = Officer.objects.get_or_create(
            institutional_id="F-2005",
            defaults={
                "name": "Jefatura Sur",
                "status": Officer.Status.ACTIVE,
                "delegation": south,
                "position": position_jefatura,
            },
        )
        officer_north_supervision, _ = Officer.objects.get_or_create(
            institutional_id="F-1006",
            defaults={
                "name": "Supervisión Zonal",
                "status": Officer.Status.ACTIVE,
                "delegation": north,
                "position": position_jefatura,
            },
        )

        admin_user, admin_created = User.objects.get_or_create(
            username=ADMIN_USERNAME,
            defaults={"is_staff": True, "is_superuser": True},
        )
        if admin_created:
            admin_user.set_password(ADMIN_PASSWORD)
            admin_user.save()
        UserProfile.objects.get_or_create(
            user=admin_user, defaults={"status": UserProfile.Status.ACTIVE}
        )

        group_officer, _ = Group.objects.get_or_create(name="Funcionario")
        group_reviewer, _ = Group.objects.get_or_create(name="Verificador")

        north_user, north_created = User.objects.get_or_create(
            username=OFFICER_NORTH_USERNAME,
            defaults={
                "first_name": "Matías",
                "last_name": "Cavieres",
                "is_staff": True,
                "is_superuser": False,
            },
        )
        if north_created:
            north_user.set_password(OFFICER_NORTH_PASSWORD)
            north_user.save()
        north_user.groups.add(group_officer, group_reviewer)
        UserProfile.objects.get_or_create(
            user=north_user,
            defaults={"officer": officer_north_1, "status": UserProfile.Status.ACTIVE},
        )

        south_user, south_created = User.objects.get_or_create(
            username=OFFICER_SOUTH_USERNAME,
            defaults={
                "first_name": "Matías",
                "last_name": "Quiroz",
                "is_staff": True,
                "is_superuser": False,
            },
        )
        if south_created:
            south_user.set_password(OFFICER_SOUTH_PASSWORD)
            south_user.save()
        south_user.groups.add(group_officer, group_reviewer)
        UserProfile.objects.get_or_create(
            user=south_user,
            defaults={"officer": officer_south_1, "status": UserProfile.Status.ACTIVE},
        )

        group_coordination, _ = Group.objects.get_or_create(name="Coordinación")
        coordination_user, coordination_created = User.objects.get_or_create(
            username=COORDINACION_USERNAME,
            defaults={"is_staff": True, "is_superuser": False},
        )
        if coordination_created:
            coordination_user.set_password(COORDINACION_PASSWORD)
            coordination_user.save()
        coordination_user.groups.add(group_coordination)
        UserProfile.objects.get_or_create(
            user=coordination_user, defaults={"status": UserProfile.Status.ACTIVE}
        )

        group_leadership, _ = Group.objects.get_or_create(name="Jefatura")
        leadership_user, leadership_created = User.objects.get_or_create(
            username=JEFATURA_USERNAME,
            defaults={"is_staff": True, "is_superuser": False},
        )
        if leadership_created:
            leadership_user.set_password(JEFATURA_PASSWORD)
            leadership_user.save()
        leadership_user.groups.add(group_leadership)
        UserProfile.objects.get_or_create(
            user=leadership_user,
            defaults={
                "officer": officer_north_jefatura,
                "status": UserProfile.Status.ACTIVE,
            },
        )

        supervision_user, supervision_created = User.objects.get_or_create(
            username=SUPERVISION_USERNAME,
            defaults={
                "first_name": "Supervisión",
                "last_name": "Zonal",
                "is_staff": True,
                "is_superuser": False,
            },
        )
        if supervision_created:
            supervision_user.set_password(SUPERVISION_PASSWORD)
            supervision_user.save()
        supervision_user.groups.add(group_leadership)
        UserProfile.objects.get_or_create(
            user=supervision_user,
            defaults={"officer": officer_north_supervision, "status": UserProfile.Status.ACTIVE},
        )
        if supervision_created:
            sync_extra_delegations(supervision_user, [south])

        group_reader, _ = Group.objects.get_or_create(name="Consulta")
        reader_user, reader_created = User.objects.get_or_create(
            username=CONSULTA_USERNAME,
            defaults={
                "first_name": "Consulta",
                "last_name": "Norte",
                "is_staff": False,
                "is_superuser": False,
            },
        )
        if reader_created:
            reader_user.set_password(CONSULTA_PASSWORD)
            reader_user.save()
        reader_user.groups.add(group_reader)
        UserProfile.objects.get_or_create(
            user=reader_user,
            defaults={"officer": officer_north_reader, "status": UserProfile.Status.ACTIVE},
        )

        for demo_user in (admin_user, north_user, south_user, coordination_user, leadership_user, supervision_user, reader_user):
            if not demo_user.email:
                demo_user.email = f"{demo_user.username}@{DEMO_EMAIL_DOMAIN}"
                demo_user.save(update_fields=["email"])

        period, _ = Period.objects.get_or_create(
            start_date=today.replace(month=1, day=1),
            defaults={
                "end_date": today.replace(month=12, day=31),
                "computable_days": 240,
                "status": Period.Status.ACTIVE,
            },
        )
        period_prev, _ = Period.objects.get_or_create(
            start_date=today.replace(year=today.year - 1, month=1, day=1),
            defaults={
                "end_date": today.replace(year=today.year - 1, month=12, day=31),
                "computable_days": 235,
                "status": Period.Status.CLOSED,
            },
        )

        goal_north, _ = Goal.objects.get_or_create(
            item=item_home_visit,
            officer=officer_north_1,
            period=period,
            defaults={"target_value": 20, "unit": "visitas", "weight": 100},
        )
        goal_south, _ = Goal.objects.get_or_create(
            item=item_home_visit,
            officer=officer_south_1,
            period=period,
            defaults={"target_value": 20, "unit": "visitas", "weight": 100},
        )
        goal_position_social, _ = Goal.objects.get_or_create(
            item=item_aid_delivery,
            position=position_social,
            period=period,
            defaults={"target_value": 50, "unit": "entregas", "weight": 80},
        )

        Indicator.objects.get_or_create(
            goal=goal_north,
            defaults={
                "progress": 14,
                "compliance": 70,
                "weighting": 100,
                "status_light": Indicator.StatusLight.AMBER,
            },
        )
        Indicator.objects.get_or_create(
            goal=goal_south,
            defaults={
                "progress": 19,
                "compliance": 95,
                "weighting": 100,
                "status_light": Indicator.StatusLight.GREEN,
            },
        )
        Indicator.objects.get_or_create(
            goal=goal_position_social,
            defaults={
                "progress": 5,
                "compliance": 10,
                "weighting": 80,
                "status_light": Indicator.StatusLight.RED,
            },
        )

        Adjustment.objects.get_or_create(
            officer=officer_north_2,
            period=period,
            defaults={
                "kind": Adjustment.Kind.BONUS,
                "reason": "Felicitación de usuario por atención destacada",
                "percentage_value": 5,
                "responsible_user": admin_user,
            },
        )
        Adjustment.objects.get_or_create(
            officer=officer_south_2,
            period=period,
            defaults={
                "kind": Adjustment.Kind.PENALTY,
                "reason": "Atraso reiterado en la entrega de informes de gestión",
                "percentage_value": 8,
                "responsible_user": admin_user,
            },
        )

        mt_presencial = ManagementType.objects.get(name="Atención a usuario presencial")
        mt_visit = ManagementType.objects.get(name="Visita a terreno")
        mt_report = ManagementType.objects.get(name="Entrega de informe")
        mt_benefit = ManagementType.objects.get(name="Entrega de beneficio")
        mt_emergency = ManagementType.objects.get(name="Emergencia")
        mt_other = ManagementType.objects.get(name="Otras gestiones")

        activity_north_1, _ = Activity.objects.get_or_create(
            delegation=north,
            author_officer=officer_north_1,
            contact_name="María Pérez",
            defaults={
                "date": today - timedelta(days=10),
                "request_description": "Solicita orientación por corte de suministro eléctrico.",
                "phone": "+56911111111",
                "beneficiary": beneficiaries["11111111-1"],
                "status": Activity.Status.IN_PROGRESS,
                "requires_visit": True,
                "item": item_home_visit,
                "service": service_social_aid,
            },
        )
        activity_north_2, _ = Activity.objects.get_or_create(
            delegation=north,
            author_officer=officer_north_2,
            contact_name="Juan Soto",
            defaults={
                "date": today - timedelta(days=3),
                "request_description": "Solicita postulación a subsidio de vivienda.",
                "phone": "+56922222222",
                "beneficiary": beneficiaries["22222222-2"],
                "status": Activity.Status.REGISTERED,
                "item": item_aid_delivery,
                "service": service_housing,
            },
        )
        activity_south_1, _ = Activity.objects.get_or_create(
            delegation=south,
            author_officer=officer_south_1,
            contact_name="Ana Rojas",
            defaults={
                "date": today - timedelta(days=8),
                "request_description": "Solicita visita por situación de vulnerabilidad.",
                "phone": "+56933333333",
                "beneficiary": beneficiaries["33333333-3"],
                "status": Activity.Status.IN_PROGRESS,
                "requires_visit": True,
                "item": item_home_visit,
                "service": service_social_aid,
            },
        )
        activity_south_2, _ = Activity.objects.get_or_create(
            delegation=south,
            author_officer=officer_south_2,
            contact_name="Pedro Díaz",
            defaults={
                "date": today - timedelta(days=1),
                "request_description": "Consulta por entrega de ayuda social.",
                "phone": "+56944444444",
                "beneficiary": beneficiaries["44444444-4"],
                "status": Activity.Status.CLOSED,
                "item": item_aid_delivery,
                "service": service_social_aid,
            },
        )
        activity_north_3, _ = Activity.objects.get_or_create(
            delegation=north,
            author_officer=officer_north_1,
            contact_name="Carla Muñoz",
            defaults={
                "date": today - timedelta(days=5),
                "request_description": "Solicita certificado de residencia para trámite municipal.",
                "phone": "+56955555555",
                "beneficiary": beneficiaries["55555555-5"],
                "status": Activity.Status.REGISTERED,
                "added_to_pipeline": True,
                "item": item_territorial_coordination,
                "service": service_certificate,
            },
        )
        activity_south_3, _ = Activity.objects.get_or_create(
            delegation=south,
            author_officer=officer_south_1,
            contact_name="Luis Herrera",
            defaults={
                "date": today - timedelta(days=4),
                "request_description": "Solicita postulación a subsidio habitacional.",
                "phone": "+56966666666",
                "beneficiary": beneficiaries["66666666-6"],
                "status": Activity.Status.IN_PROGRESS,
                "item": item_phone_followup,
                "service": service_subsidy,
            },
        )

        activity_north_1.action_taken = (
            "Se coordinó visita domiciliaria y se derivó a Servicio de Ayuda Social."
        )
        activity_north_1.save()

        Followup.objects.get_or_create(
            activity=activity_north_1,
            sequence_number=1,
            defaults={
                "management_type": mt_presencial,
                "date": today - timedelta(days=9),
                "result": "Se agenda visita domiciliaria para evaluar el caso.",
                "scheduled_visit_date": today + timedelta(days=2),
            },
        )
        Followup.objects.get_or_create(
            activity=activity_north_1,
            sequence_number=2,
            defaults={
                "management_type": mt_report,
                "date": today - timedelta(days=2),
                "result": "Se entrega informe social al solicitante.",
                "report_delivery_date": today - timedelta(days=1),
            },
        )
        Followup.objects.get_or_create(
            activity=activity_north_2,
            sequence_number=1,
            defaults={
                "management_type": mt_emergency,
                "date": today - timedelta(days=2),
                "result": "Se prioriza como caso de emergencia social.",
            },
        )
        Followup.objects.get_or_create(
            activity=activity_north_3,
            sequence_number=1,
            defaults={
                "management_type": mt_other,
                "date": today - timedelta(days=4),
                "result": "Se deriva el trámite a Secretaría Municipal.",
            },
        )
        Followup.objects.get_or_create(
            activity=activity_south_1,
            sequence_number=1,
            defaults={
                "management_type": mt_presencial,
                "date": today - timedelta(days=7),
                "result": "Visita realizada, se deriva a evaluación social.",
                "visit_date": today - timedelta(days=6),
            },
        )
        Followup.objects.get_or_create(
            activity=activity_south_1,
            sequence_number=2,
            defaults={
                "management_type": mt_benefit,
                "date": today - timedelta(days=5),
                "result": "Se coordina entrega de ayuda social al beneficiario.",
                "benefit_delivery_date": today - timedelta(days=3),
            },
        )
        Followup.objects.get_or_create(
            activity=activity_south_2,
            sequence_number=1,
            defaults={
                "management_type": mt_report,
                "date": today,
                "result": "Se cierra el caso con informe final de la gestión.",
                "report_delivery_date": today,
            },
        )
        Followup.objects.get_or_create(
            activity=activity_south_3,
            sequence_number=1,
            defaults={
                "management_type": mt_visit,
                "date": today - timedelta(days=3),
                "result": "Se realiza visita para validar antecedentes de postulación.",
                "visit_date": today - timedelta(days=2),
            },
        )

        commitment_north_1, _ = Commitment.objects.get_or_create(
            delegation=north,
            territory=territory_north,
            requester="Junta de Vecinos Sector Norte",
            defaults={
                "requester_type": Commitment.RequesterType.EXTERNAL,
                "request_date": today - timedelta(days=15),
                "description": "Solicitud de mejora de luminarias en el sector.",
                "due_date": today + timedelta(days=15),
                "status": Commitment.Status.IN_PROGRESS,
                "responsible_officer": officer_north_2,
            },
        )
        Commitment.objects.get_or_create(
            delegation=south,
            territory=territory_south,
            requester="Club Deportivo Sector Sur",
            defaults={
                "requester_type": Commitment.RequesterType.EXTERNAL,
                "request_date": today - timedelta(days=20),
                "description": "Solicitud de apoyo para implementos deportivos.",
                "due_date": today + timedelta(days=10),
                "status": Commitment.Status.SUBMITTED,
                "responsible_officer": officer_south_2,
            },
        )
        Commitment.objects.get_or_create(
            delegation=north,
            territory=territory_north_2,
            requester="Jefatura Delegación Norte",
            defaults={
                "requester_type": Commitment.RequesterType.INTERNAL,
                "request_date": today - timedelta(days=25),
                "description": "Coordinación interna de agenda mensual.",
                "due_date": today - timedelta(days=5),
                "status": Commitment.Status.FULFILLED,
                "responsible_officer": officer_north_1,
                "source": "Reunión de coordinación mensual",
                "support": "Municipalidad",
            },
        )
        Commitment.objects.get_or_create(
            delegation=south,
            territory=territory_south_2,
            requester="Jefatura Delegación Sur",
            defaults={
                "requester_type": Commitment.RequesterType.INTERNAL,
                "request_date": today - timedelta(days=18),
                "description": "Coordinación interna de agenda mensual.",
                "due_date": today - timedelta(days=3),
                "status": Commitment.Status.FULFILLED,
                "responsible_officer": officer_south_1,
                "source": "Reunión de coordinación mensual",
                "support": "Municipalidad",
            },
        )

        evidence_north, _ = Evidence.objects.get_or_create(
            unique_code="EVD-NORTE-0001",
            defaults={
                "file_link": "evidencias/norte/visita-perez-2026.pdf",
                "review_status": Evidence.ReviewStatus.PENDING,
                "activity": activity_north_1,
                "author_officer": officer_north_2,
            },
        )
        evidence_north_2, _ = Evidence.objects.get_or_create(
            unique_code="EVD-NORTE-0002",
            defaults={
                "file_link": "evidencias/norte/informe-visita-perez-2026.pdf",
                "review_status": Evidence.ReviewStatus.APPROVED,
                "activity": activity_north_1,
                "author_officer": officer_north_2,
            },
        )
        Validation.objects.get_or_create(
            evidence=evidence_north_2,
            reviewer_officer=officer_north_1,
            defaults={
                "decision": Validation.Decision.APPROVED,
                "result": "Evidencia conforme, se aprueba.",
            },
        )

        evidence_north_3, _ = Evidence.objects.get_or_create(
            unique_code="EVD-NORTE-0003",
            defaults={
                "file_link": "evidencias/norte/certificado-munoz-2026.pdf",
                "review_status": Evidence.ReviewStatus.REJECTED,
                "activity": activity_north_3,
                "author_officer": officer_north_1,
            },
        )
        Validation.objects.get_or_create(
            evidence=evidence_north_3,
            reviewer_officer=officer_north_2,
            defaults={
                "decision": Validation.Decision.REJECTED,
                "result": "No cumple estándar de legibilidad del documento.",
                "notes": "Se solicita reenviar el certificado escaneado en mejor resolución.",
            },
        )
        if evidence_north_3.deleted_at is None:
            evidence_north_3.deleted_at = timezone.now()
            evidence_north_3.save()

        evidence_south, _ = Evidence.objects.get_or_create(
            unique_code="EVD-SUR-0001",
            defaults={
                "file_link": "evidencias/sur/visita-rojas-2026.pdf",
                "review_status": Evidence.ReviewStatus.APPROVED,
                "activity": activity_south_1,
                "author_officer": officer_south_1,
            },
        )
        Validation.objects.get_or_create(
            evidence=evidence_south,
            reviewer_officer=officer_south_2,
            defaults={
                "decision": Validation.Decision.APPROVED,
                "result": "Evidencia conforme, se aprueba.",
            },
        )

        evidence_south_2, _ = Evidence.objects.get_or_create(
            unique_code="EVD-SUR-0002",
            defaults={
                "file_link": "evidencias/sur/visita-rojas-seguimiento-2026.pdf",
                "review_status": Evidence.ReviewStatus.PENDING,
                "activity": activity_south_1,
                "author_officer": officer_south_2,
            },
        )

        evidence_south_3, _ = Evidence.objects.get_or_create(
            unique_code="EVD-SUR-0003",
            defaults={
                "file_link": "evidencias/sur/postulacion-herrera-2026.pdf",
                "review_status": Evidence.ReviewStatus.PENDING,
                "activity": activity_south_3,
                "author_officer": officer_south_2,
            },
        )
        Validation.objects.get_or_create(
            evidence=evidence_south_3,
            reviewer_officer=officer_south_2,
            defaults={
                "decision": Validation.Decision.FLAGGED,
                "result": "Observado: falta firma del solicitante.",
                "notes": "Se solicita reenvío con firma antes de continuar el trámite.",
            },
        )

        self.write_demo_files()

        if activity_north_2.deleted_at is None:
            activity_north_2.deleted_at = timezone.now()
            activity_north_2.save()

        AuditLog.objects.get_or_create(
            event="Carga de datos de demostración",
            affected_entity="Activity",
            record_id=activity_north_2.pk,
            defaults={
                "previous_value": "deleted_at=None",
                "new_value": f"deleted_at={activity_north_2.deleted_at.isoformat()}",
                "user": admin_user,
            },
        )
        AuditLog.objects.get_or_create(
            event="Carga de datos de demostración",
            affected_entity="Evidence",
            record_id=evidence_north_3.pk,
            defaults={
                "previous_value": "deleted_at=None",
                "new_value": f"deleted_at={evidence_north_3.deleted_at.isoformat()}",
                "user": admin_user,
            },
        )
        AuditLog.objects.get_or_create(
            event="Creación de cuentas de prueba",
            affected_entity="User",
            record_id=north_user.pk,
            defaults={
                "previous_value": "",
                "new_value": f"username={north_user.username}, grupos=Funcionario,Verificador",
                "user": admin_user,
            },
        )

        self.stdout.write(self.style.SUCCESS("\nDatos de demostración cargados."))
        self.stdout.write(self.style.WARNING(
            "\nCuentas de PRUEBA para la demostración (NO son credenciales personales):"
        ))
        self.stdout.write(f"  Superusuario   -> {ADMIN_USERNAME} / {ADMIN_PASSWORD}")
        self.stdout.write(
            f"  Funcionario(a) Delegación Norte -> "
            f"{OFFICER_NORTH_USERNAME} / {OFFICER_NORTH_PASSWORD}"
        )
        self.stdout.write(
            f"  Funcionario(a) Delegación Sur   -> "
            f"{OFFICER_SOUTH_USERNAME} / {OFFICER_SOUTH_PASSWORD}"
        )
        self.stdout.write(
            f"  Coordinación (ve todo el SGR)   -> "
            f"{COORDINACION_USERNAME} / {COORDINACION_PASSWORD}"
        )
        self.stdout.write(
            f"  Jefatura Delegación Norte       -> "
            f"{JEFATURA_USERNAME} / {JEFATURA_PASSWORD}"
        )
        self.stdout.write(
            f"  Jefatura Norte con acceso a Sur -> "
            f"{SUPERVISION_USERNAME} / {SUPERVISION_PASSWORD} (elige delegación arriba)"
        )
        self.stdout.write(
            f"  Consulta (solo lectura) Norte   -> "
            f"{CONSULTA_USERNAME} / {CONSULTA_PASSWORD}"
        )
        self.stdout.write(
            f"\nCada cuenta tiene el correo <usuario>@{DEMO_EMAIL_DOMAIN} (por ejemplo "
            f"{ADMIN_USERNAME}@{DEMO_EMAIL_DOMAIN}). Con él se prueba «¿Olvidaste tu contraseña?»: "
            "el código llega a la terminal donde corre runserver."
        )
        self.stdout.write(
            "\nPara comprobar el scoping: inicia sesión con cada usuario de "
            "Delegación y verifica que Actividad/Compromiso/Evidencia solo "
            "muestran los registros de su propia delegación."
        )
        self.stdout.write(
            "\nQuedaron 3 Officer 'de reserva', SIN usuario vinculado "
            "todavía, para que practiques tú mismo el alta de una cuenta "
            "(Admin > Auth > Users > Add user):\n"
            "  F-1004 'Consulta Norte'  (Delegación Norte, grupo Consulta)\n"
            "  F-2004 'Consulta Sur'    (Delegación Sur, grupo Consulta)\n"
            "  F-2005 'Jefatura Sur'    (Delegación Sur, grupo Jefatura)\n"
            "Mismo patrón que coordinacion1/jefatura1: creas el User, "
            "tildas 'Staff status', le pones el grupo correspondiente y en "
            "'Perfil de usuario' eliges uno de estos Officer."
        )
        self.stdout.write(
            f"\nHay 2 registros ya archivados de ejemplo (Activity #{activity_north_2.pk} "
            f"y Evidence #{evidence_north_3.pk}, deleted_at poblado en ambos, en modelos "
            "distintos). Por defecto el Admin los oculta; agrega ?show_archived=1 al "
            "final de la URL del listado para verlos (ver README.md)."
        )


def cargar_datos_prueba():
    CargaDatosPrueba(stdout=StringIO()).handle()
