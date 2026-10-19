import hashlib
import uuid
from pathlib import PurePath

from django.core.exceptions import ValidationError
from django.utils.text import slugify

PDF = b"%PDF-"
PNG = b"\x89PNG\r\n\x1a\n"
JPEG = b"\xff\xd8\xff"
ZIP = b"PK\x03\x04"

EVIDENCE_TYPES = {
    "pdf": (PDF, "application/pdf", "PDF"),
    "png": (PNG, "image/png", "Imagen PNG"),
    "jpg": (JPEG, "image/jpeg", "Imagen JPG"),
    "jpeg": (JPEG, "image/jpeg", "Imagen JPG"),
    "docx": (ZIP, "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "Documento Word"),
    "xlsx": (ZIP, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "Planilla Excel"),
}
PHOTO_TYPES = {key: EVIDENCE_TYPES[key] for key in ("png", "jpg", "jpeg")}

INLINE_TYPES = {"application/pdf", "image/png", "image/jpeg"}


def extension_of(name):
    return PurePath(str(name or "")).suffix.lower().lstrip(".")


def is_image(name):
    return extension_of(name) in ("png", "jpg", "jpeg")


def content_type_of(name):
    return EVIDENCE_TYPES.get(extension_of(name), (None, "application/octet-stream", ""))[1]


def type_label(name):
    return EVIDENCE_TYPES.get(extension_of(name), (None, "", "Archivo"))[2]


def readable_size(size):
    if size < 1024:
        return f"{size} bytes"
    if size < 1024 * 1024:
        return f"{size / 1024:.0f} KB".replace(".", ",")
    return f"{size / (1024 * 1024):.1f} MB".replace(".", ",")


def accepted_text(types):
    names = sorted({key.upper() for key in types if key != "jpeg"})
    return ", ".join(names[:-1]) + " o " + names[-1]


def check_upload(uploaded, types, max_mb):
    extension = extension_of(uploaded.name)
    if extension not in types:
        raise ValidationError(
            f"Ese tipo de archivo no se acepta. Sube un archivo {accepted_text(types)}.",
            code="extension",
        )
    if uploaded.size > max_mb * 1024 * 1024:
        raise ValidationError(
            f"El archivo pesa {readable_size(uploaded.size)} y el máximo es {max_mb} MB.", code="size"
        )
    if uploaded.size == 0:
        raise ValidationError("El archivo está vacío.", code="empty")
    uploaded.seek(0)
    start = uploaded.read(8)
    uploaded.seek(0)
    signature = types[extension][0]
    if not start.startswith(signature):
        raise ValidationError(
            "El contenido del archivo no corresponde a su extensión. Revisa que no esté dañado.",
            code="content",
        )
    return uploaded


def sha256_of(uploaded):
    digest = hashlib.sha256()
    uploaded.seek(0)
    for chunk in uploaded.chunks():
        digest.update(chunk)
    uploaded.seek(0)
    return digest.hexdigest()


def describe_file(uploaded):
    return "\n".join(
        [
            f"Archivo original: {PurePath(uploaded.name).name}",
            f"Tipo: {type_label(uploaded.name)}",
            f"Tamaño: {readable_size(uploaded.size)}",
            f"Huella SHA-256: {sha256_of(uploaded)}",
        ]
    )


def evidence_path(instance, filename):
    from django.utils import timezone

    base = slugify(instance.unique_code or "evidencia") or "evidencia"
    return f"evidencias/{timezone.localdate().year}/{base}-{uuid.uuid4().hex[:8]}.{extension_of(filename)}"


def photo_path(instance, filename):
    return f"fotos/usuario-{instance.user_id or 'nuevo'}-{uuid.uuid4().hex[:8]}.{extension_of(filename)}"

