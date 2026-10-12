from django.db import migrations

# Los perfiles del sistema con la descripción y el alcance que tenían hasta la v7, cuando se deducían del nombre.
# Se copian aquí (y no se importan de core/roles.py) para que la migración no cambie si esa lista cambia después.
SYSTEM_ROLES = {
    "Coordinación": ("Define períodos, metas y ajustes, y consulta todas las delegaciones.", "all"),
    "Jefatura": ("Consulta la gestión de su delegación y actualiza los compromisos.", "own"),
    "Funcionario": ("Registra atenciones, gestiones, evidencias y compromisos de su delegación.", "own"),
    "Verificador": ("Revisa las evidencias de su delegación y registra la validación.", "own"),
    "Consulta": ("Solo consulta la información de su delegación.", "own"),
}


def create_profiles(apps, schema_editor):
    """Una ficha para cada rol que ya existe: los de fábrica con lo suyo y los demás con alcance sobre su delegación."""
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
        # Al deshacerla no hay nada que hacer: la tabla de fichas se borra con la migración anterior.
        migrations.RunPython(create_profiles, migrations.RunPython.noop),
    ]
