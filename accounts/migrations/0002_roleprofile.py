import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0001_initial"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.CreateModel(
            name="RoleProfile",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True, verbose_name="creado el"),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True, verbose_name="actualizado el"),
                ),
                (
                    "deleted_at",
                    models.DateTimeField(
                        blank=True,
                        help_text="Borrado lógico: si tiene fecha, el registro está archivado.",
                        null=True,
                        verbose_name="eliminado el",
                    ),
                ),
                (
                    "description",
                    models.CharField(
                        blank=True,
                        default="",
                        max_length=255,
                        verbose_name="descripción",
                    ),
                ),
                (
                    "scope",
                    models.CharField(
                        choices=[
                            ("own", "Su delegación"),
                            ("all", "Todas las delegaciones"),
                        ],
                        default="own",
                        max_length=10,
                        verbose_name="alcance autorizado",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[("active", "Activo"), ("inactive", "Inactivo")],
                        default="active",
                        max_length=20,
                        verbose_name="estado",
                    ),
                ),
                (
                    "group",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="role_profile",
                        to="auth.group",
                        verbose_name="rol",
                    ),
                ),
            ],
            options={
                "verbose_name": "Ficha de rol",
                "verbose_name_plural": "Fichas de roles",
            },
        ),
    ]
