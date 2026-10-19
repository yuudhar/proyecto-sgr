from django.db import models

from core.models import BaseModel
from core.uploads import evidence_path
from operations.models import Activity
from organization.models import Officer


class Evidence(BaseModel):
    class ReviewStatus(models.TextChoices):
        PENDING = "pending", "Pendiente"
        APPROVED = "approved", "Aprobada"
        REJECTED = "rejected", "Rechazada"

    unique_code = models.CharField(
        max_length=50, unique=True, verbose_name="código único"
    )
    # La columna sigue llamándose file_link (varchar 255): ahora guarda la ruta del archivo
    # subido dentro de la carpeta de archivos del sistema, no un texto libre.
    file_link = models.FileField(
        upload_to=evidence_path,
        max_length=255,
        verbose_name="archivo",
        help_text="PDF, imagen (PNG o JPG), Word o Excel de hasta 10 MB.",
    )
    uploaded_at = models.DateTimeField(
        auto_now_add=True, verbose_name="fecha de carga"
    )
    review_status = models.CharField(
        max_length=30,
        choices=ReviewStatus.choices,
        default=ReviewStatus.PENDING,
        verbose_name="estado de revisión",
    )
    metadata = models.TextField(blank=True, null=True, verbose_name="metadatos")
    activity = models.ForeignKey(
        Activity, on_delete=models.PROTECT, related_name="evidence_records",
        verbose_name="actividad",
    )
    author_officer = models.ForeignKey(
        Officer, on_delete=models.PROTECT, related_name="authored_evidence",
        verbose_name="funcionario autor",
    )

    class Meta:
        verbose_name = "Evidencia"
        verbose_name_plural = "Evidencias"
        ordering = ("-uploaded_at",)

    def __str__(self):
        return self.unique_code


class Validation(BaseModel):
    class Decision(models.TextChoices):
        APPROVED = "approved", "Aprobado"
        REJECTED = "rejected", "Rechazado"
        FLAGGED = "flagged", "Observado"

    decision = models.CharField(
        max_length=30, choices=Decision.choices, verbose_name="decisión"
    )
    date = models.DateTimeField(auto_now_add=True, verbose_name="fecha")
    notes = models.TextField(blank=True, null=True, verbose_name="observación")
    result = models.CharField(
        max_length=50, blank=True, null=True, verbose_name="resultado"
    )
    version = models.CharField(max_length=20, default="1", verbose_name="versión")
    evidence = models.ForeignKey(
        Evidence, on_delete=models.PROTECT, related_name="validations",
        verbose_name="evidencia",
    )
    # Vacío cuando revisó el Super Usuario, que no es un funcionario: el registro de
    # auditoría guarda igualmente qué usuario hizo la revisión.
    reviewer_officer = models.ForeignKey(
        Officer, on_delete=models.PROTECT, related_name="performed_validations",
        verbose_name="funcionario verificador", null=True, blank=True,
    )

    class Meta:
        verbose_name = "Validación"
        verbose_name_plural = "Validaciones"
        ordering = ("-date",)

    @property
    def reviewer_name(self):
        return str(self.reviewer_officer) if self.reviewer_officer_id else "Super Usuario"

    def __str__(self):
        return f"Validación {self.get_decision_display()} · {self.evidence}"
