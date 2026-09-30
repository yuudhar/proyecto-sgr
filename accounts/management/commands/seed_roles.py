
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand

from evidence.models import Evidence, Validation
from operations.models import Activity, Commitment, Followup
from organization.models import Item, Officer, Position, PositionItem, Service, Territory
from planning.models import Adjustment, Goal, Indicator, Period


def permissions_for(model, codenames):
    content_type = ContentType.objects.get_for_model(model)
    return list(
        Permission.objects.filter(content_type=content_type, codename__in=codenames)
    )


ROLES = {
    "Coordinación": [
        (Period, ["add_period", "change_period", "view_period"]),
        (Goal, ["add_goal", "change_goal", "view_goal"]),
        (Indicator, ["view_indicator"]),
        (Adjustment, ["add_adjustment", "change_adjustment", "view_adjustment"]),
        (Position, ["view_position"]),
        (Item, ["view_item"]),
        (Service, ["view_service"]),
        (PositionItem, ["view_positionitem"]),
        (Officer, ["view_officer"]),
        (Territory, ["view_territory"]),
    ],
    "Jefatura": [
        (Activity, ["view_activity"]),
        (Commitment, ["view_commitment", "change_commitment"]),
        (Followup, ["view_followup"]),
        (Indicator, ["view_indicator"]),
        (Evidence, ["view_evidence"]),
        (Validation, ["view_validation"]),
        (Officer, ["view_officer"]),
        (Territory, ["view_territory"]),
    ],
    "Funcionario": [
        (Activity, ["add_activity", "change_activity", "view_activity"]),
        (Followup, ["add_followup", "change_followup", "view_followup"]),
        (Evidence, ["add_evidence", "change_evidence", "view_evidence"]),
        (Commitment, ["add_commitment", "change_commitment", "view_commitment"]),
        (Officer, ["view_officer"]),
        (Territory, ["view_territory"]),
    ],
    "Verificador": [
        (Evidence, ["view_evidence"]),
        (Activity, ["view_activity"]),
        (Validation, ["add_validation", "change_validation", "view_validation"]),
    ],
    "Consulta": [
        (Activity, ["view_activity"]),
        (Commitment, ["view_commitment"]),
        (Indicator, ["view_indicator"]),
        (Evidence, ["view_evidence"]),
        (Validation, ["view_validation"]),
        (Followup, ["view_followup"]),
    ],
}


class Command(BaseCommand):
    help = "Crea/actualiza los grupos y permisos base del proyecto SGR."

    def handle(self, *args, **options):
        for role_name, rules in ROLES.items():
            group, created = Group.objects.get_or_create(name=role_name)
            all_permissions = []
            for model, codenames in rules:
                all_permissions.extend(permissions_for(model, codenames))
            group.permissions.set(all_permissions)
            action = "creado" if created else "actualizado"
            self.stdout.write(
                self.style.SUCCESS(
                    f"Grupo '{role_name}' {action} con "
                    f"{len(all_permissions)} permiso(s)."
                )
            )
