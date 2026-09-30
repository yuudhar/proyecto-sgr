
from django.conf import settings
from django.db import models


class BaseModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="creado el")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="actualizado el")
    deleted_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="eliminado el",
        help_text="Borrado lógico: si tiene fecha, el registro está archivado.",
    )

    class Meta:
        abstract = True

    @property
    def is_active(self):
        return self.deleted_at is None


class AuditLog(BaseModel):

    event = models.CharField(max_length=100, verbose_name="evento")
    date = models.DateTimeField(auto_now_add=True, verbose_name="fecha")
    affected_entity = models.CharField(max_length=50, verbose_name="entidad afectada")
    record_id = models.PositiveIntegerField(verbose_name="identificador del registro")
    previous_value = models.TextField(
        blank=True, null=True, verbose_name="valor anterior"
    )
    new_value = models.TextField(blank=True, null=True, verbose_name="valor nuevo")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="audit_logs",
        verbose_name="usuario",
    )

    class Meta:
        verbose_name = "Auditoría"
        verbose_name_plural = "Auditorías"
        ordering = ("-date",)

    def __str__(self):
        return f"{self.event} · {self.affected_entity}#{self.record_id}"
