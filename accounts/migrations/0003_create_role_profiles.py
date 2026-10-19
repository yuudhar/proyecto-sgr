from django.db import migrations

SYSTEM_ROLES = {
    "Coordinación": ("Define períodos, metas y ajustes, y consulta todas las delegaciones.", "all"),
    "Jefatura": ("Consulta la gestión de su delegación y actualiza los compromisos.", "own"),
    "Funcionario": ("Registra atenciones, gestiones, evidencias y compromisos de su delegación.", "own"),
    "Verificador": ("Revisa las evidencias de su delegación y registra la validación.", "own"),
    "Consulta": ("Solo consulta la información de su delegación.", "own"),
}


def create_profiles(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    RoleProfile = apps.get_model("accounts", "RoleProfile")
    for group in Group.objects.all():
        description, scope = SYSTEM_ROLES.get(group.name, ("", "own"))
        RoleProfile.objects.get_or_create(
            group=group,
            defaults={"description": description, "scope": scope, "status": "active"},
        )


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0002_roleprofile"),
    ]

    operations = [
        migrations.RunPython(create_profiles, migrations.RunPython.noop),
    ]
