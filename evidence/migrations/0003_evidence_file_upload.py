import core.uploads
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("evidence", "0002_validation_reviewer_optional"),
    ]

    operations = [
        migrations.AlterField(
            model_name="evidence",
            name="file_link",
            field=models.FileField(
                help_text="PDF, imagen (PNG o JPG), Word o Excel de hasta 10 MB.",
                max_length=255,
                upload_to=core.uploads.evidence_path,
                verbose_name="archivo",
            ),
        ),
    ]
