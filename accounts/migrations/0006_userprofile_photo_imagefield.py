import core.uploads
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0005_userprofile_photo"),
    ]

    operations = [
        migrations.AlterField(
            model_name="userprofile",
            name="photo",
            field=models.ImageField(
                blank=True,
                max_length=255,
                null=True,
                upload_to=core.uploads.photo_path,
                verbose_name="foto de perfil",
            ),
        ),
    ]
