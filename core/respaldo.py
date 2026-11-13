"""Respaldo y restauración de la base de datos y de los archivos subidos (RNF-010).

Cada respaldo es un juego de tres archivos con el mismo sello de fecha, dentro de BACKUP_DIR:

    sgr-20261112-033000-base.sql.gz        la base (volcado de MariaDB/MySQL; en SQLite, una copia de la base)
    sgr-20261112-033000-archivos.tar.gz    las evidencias y fotos subidas (MEDIA_ROOT)
    sgr-20261112-033000.json               el sello, la versión, los tamaños y la huella SHA-256 de cada archivo

Los archivos se escriben con un nombre temporal y se renombran al final, así un respaldo a medias nunca parece completo.
Antes de dar un respaldo por bueno se vuelve a leer: el .gz se descomprime entero y el .tar.gz se recorre.
La contraseña de la base viaja por la variable MYSQL_PWD y nunca en la línea de comandos.
"""

import gzip
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import tarfile
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import connection
from django.utils import timezone

PREFIX = "sgr-"
SAFETY_PREFIX = "sgr-antes-de-restaurar-"
STAMP_FORMAT = "%Y%m%d-%H%M%S"
CHUNK = 1024 * 1024


class BackupError(Exception):
    """Algo impidió hacer o usar un respaldo; el mensaje dice qué."""


def backup_dir():
    return Path(settings.BACKUP_DIR)


def db_settings():
    return settings.DATABASES["default"]


def is_sqlite():
    return db_settings()["ENGINE"].endswith("sqlite3")


def sha256_of(path):
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for block in iter(lambda: source.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def local_now(now=None):
    """La hora de Santiago, que es la que ve el equipo (la base y el servidor trabajan en UTC)."""
    return (now or timezone.now()).astimezone(ZoneInfo(settings.PORTAL_TIME_ZONE))


def new_stamp(prefix=PREFIX, now=None):
    return prefix + local_now(now).strftime(STAMP_FORMAT)


def ensure_dir():
    folder = backup_dir()
    folder.mkdir(parents=True, exist_ok=True)
    try:
        folder.chmod(0o700)
    except OSError:
        pass
    return folder


# ------------------------------------------------------------------ hacer el respaldo
def dump_mysql(target):
    cfg = db_settings()
    command = [
        "mysqldump",
        "--single-transaction",
        "--routines",
        "--default-character-set=utf8mb4",
        "-h", str(cfg.get("HOST") or "localhost"),
        "-P", str(cfg.get("PORT") or "3306"),
        "-u", str(cfg.get("USER") or "root"),
        cfg["NAME"],
    ]
    env = {**os.environ, "MYSQL_PWD": str(cfg.get("PASSWORD") or "")}
    try:
        with gzip.open(target, "wb") as out:
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
            for block in iter(lambda: process.stdout.read(CHUNK), b""):
                out.write(block)
            error = process.stderr.read().decode("utf-8", "replace").strip()
            if process.wait() != 0:
                raise BackupError(f"mysqldump falló: {error or 'sin detalle'}")
    except FileNotFoundError as exc:
        raise BackupError("No se encontró mysqldump. Instala el cliente de MariaDB (paquete mariadb105).") from exc


def dump_sqlite(target):
    source = db_settings()["NAME"]
    with tempfile.TemporaryDirectory() as folder:
        copy = Path(folder) / "copia.sqlite3"
        origin = sqlite3.connect(str(source))
        destination = sqlite3.connect(str(copy))
        try:
            origin.backup(destination)  # copia consistente aunque haya gente usando la base
        finally:
            destination.close()
            origin.close()
        with open(copy, "rb") as read, gzip.open(target, "wb") as out:
            shutil.copyfileobj(read, out, CHUNK)


def pack_media(target):
    media = Path(settings.MEDIA_ROOT)
    with tarfile.open(target, "w:gz") as archive:
        if media.is_dir():
            for child in sorted(media.iterdir()):
                archive.add(child, arcname=child.name)


def verify_gzip(path):
    size = 0
    with gzip.open(path, "rb") as source:
        for block in iter(lambda: source.read(CHUNK), b""):
            size += len(block)
    if size == 0:
        raise BackupError(f"El archivo {path.name} quedó vacío.")
    return size


def verify_tar(path):
    with tarfile.open(path, "r:gz") as archive:
        return sum(1 for _ in archive)


def verify_dump_text(path):
    """Un volcado de mysqldump termina con «-- Dump completed»: si falta, quedó cortado."""
    with gzip.open(path, "rb") as source:
        tail = b""
        for block in iter(lambda: source.read(CHUNK), b""):
            tail = (tail + block)[-512:]
    if b"Dump completed" not in tail:
        raise BackupError("El volcado de la base quedó incompleto (no termina con «Dump completed»).")


def make_backup(prefix=PREFIX, now=None):
    """Hace un respaldo completo y devuelve su ficha (el contenido del .json)."""
    folder = ensure_dir()
    stamp = new_stamp(prefix, now)
    base = folder / f"{stamp}-base.sql.gz"
    files = folder / f"{stamp}-archivos.tar.gz"
    manifest = folder / f"{stamp}.json"
    if manifest.exists():
        raise BackupError(f"Ya existe un respaldo con el sello {stamp}. Espera un segundo e inténtalo de nuevo.")
    pending = [Path(f"{p}.tmp") for p in (base, files)]
    try:
        if is_sqlite():
            dump_sqlite(pending[0])
        else:
            dump_mysql(pending[0])
        pack_media(pending[1])
        db_size = verify_gzip(pending[0])
        if not is_sqlite():
            verify_dump_text(pending[0])
        entries = verify_tar(pending[1])
        pending[0].replace(base)
        pending[1].replace(files)
        data = {
            "sello": stamp,
            "creado": local_now(now).isoformat(),
            "version": read_version(),
            "motor": "sqlite" if is_sqlite() else "mysql",
            "base": {"archivo": base.name, "bytes": base.stat().st_size, "sin_comprimir": db_size, "sha256": sha256_of(base)},
            "archivos": {
                "archivo": files.name,
                "bytes": files.stat().st_size,
                "elementos": entries,
                "sha256": sha256_of(files),
            },
        }
        temp = Path(f"{manifest}.tmp")
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(manifest)
    except BaseException:
        for leftover in (*pending, base, files, Path(f"{manifest}.tmp")):
            leftover.unlink(missing_ok=True)
        raise
    for produced in (base, files, manifest):
        try:
            produced.chmod(0o600)
        except OSError:
            pass
    return data


def read_version():
    try:
        return (Path(settings.BASE_DIR) / "VERSION").read_text(encoding="utf-8").strip() or "sin definir"
    except OSError:
        return "sin definir"


# ------------------------------------------------------------------ listar y limpiar
def list_backups():
    """Respaldos completos (con su ficha), del más nuevo al más antiguo."""
    folder = backup_dir()
    found = []
    if not folder.is_dir():
        return found
    for path in folder.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            created = datetime.fromisoformat(data["creado"])
        except (OSError, ValueError, KeyError):
            continue
        if not (folder / data["base"]["archivo"]).is_file() or not (folder / data["archivos"]["archivo"]).is_file():
            continue
        found.append((created, data))
    found.sort(key=lambda item: item[0], reverse=True)
    return [data for _created, data in found]


def delete_backup(data):
    folder = backup_dir()
    for name in (data["base"]["archivo"], data["archivos"]["archivo"], f"{data['sello']}.json"):
        (folder / name).unlink(missing_ok=True)


def apply_retention(keep_days=None, minimum=3, now=None):
    """Borra los respaldos con más de keep_days días, pero deja siempre los `minimum` más recientes."""
    keep_days = settings.BACKUP_KEEP_DAYS if keep_days is None else keep_days
    limit = (now or timezone.now()) - timedelta(days=keep_days)
    removed = []
    for position, data in enumerate(list_backups()):
        if position < minimum or data["sello"].startswith(SAFETY_PREFIX):
            continue
        if datetime.fromisoformat(data["creado"]) < limit:
            delete_backup(data)
            removed.append(data["sello"])
    return removed


def status(now=None):
    """Estado del último respaldo para el chequeo de salud: «ok», «atrasado» o «sin respaldos»."""
    backups = [b for b in list_backups() if not b["sello"].startswith(SAFETY_PREFIX)]
    if not backups:
        return "sin respaldos"
    last = datetime.fromisoformat(backups[0]["creado"])
    age = (now or timezone.now()) - last
    return "ok" if age <= timedelta(hours=settings.BACKUP_MAX_AGE_HOURS) else "atrasado"


# ------------------------------------------------------------------ restaurar
def find_backup(stamp):
    for data in list_backups():
        if data["sello"] == stamp:
            return data
    raise BackupError(f"No existe el respaldo «{stamp}» en {backup_dir()}.")


def check_files(data):
    folder = backup_dir()
    for key in ("base", "archivos"):
        path = folder / data[key]["archivo"]
        if sha256_of(path) != data[key]["sha256"]:
            raise BackupError(f"El archivo {path.name} no coincide con su huella: está dañado o fue modificado.")


def restore_mysql(source):
    cfg = db_settings()
    command = [
        "mysql",
        "--default-character-set=utf8mb4",
        "-h", str(cfg.get("HOST") or "localhost"),
        "-P", str(cfg.get("PORT") or "3306"),
        "-u", str(cfg.get("USER") or "root"),
        cfg["NAME"],
    ]
    env = {**os.environ, "MYSQL_PWD": str(cfg.get("PASSWORD") or "")}
    try:
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
        with gzip.open(source, "rb") as dump:
            for block in iter(lambda: dump.read(CHUNK), b""):
                process.stdin.write(block)
        process.stdin.close()
        error = process.stderr.read().decode("utf-8", "replace").strip()
        if process.wait() != 0:
            raise BackupError(f"mysql no pudo cargar el respaldo: {error or 'sin detalle'}")
    except FileNotFoundError as exc:
        raise BackupError("No se encontró el cliente mysql. Instala el paquete mariadb105.") from exc


def restore_sqlite(source):
    target = Path(db_settings()["NAME"])
    connection.close()
    with gzip.open(source, "rb") as dump, open(f"{target}.restaurando", "wb") as out:
        shutil.copyfileobj(dump, out, CHUNK)
    for suffix in ("-wal", "-shm"):
        Path(f"{target}{suffix}").unlink(missing_ok=True)
    Path(f"{target}.restaurando").replace(target)


def restore_media(source):
    """Reemplaza el contenido de MEDIA_ROOT por el del respaldo. Primero se descomprime aparte: si el archivo
    viene dañado o trae rutas peligrosas, no se toca nada de lo que hay."""
    media = Path(settings.MEDIA_ROOT)
    media.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".sgr-restaurando-", dir=media.parent))
    try:
        try:
            with tarfile.open(source, "r:gz") as archive:
                archive.extractall(staging, filter="data")  # rechaza rutas fuera de la carpeta y enlaces peligrosos
        except (tarfile.TarError, OSError, EOFError) as exc:
            raise BackupError(f"No se pudieron leer los archivos del respaldo: {exc}") from exc
        for child in media.iterdir():
            shutil.rmtree(child) if child.is_dir() and not child.is_symlink() else child.unlink()
        for child in staging.iterdir():
            shutil.move(str(child), str(media / child.name))
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def restore_backup(stamp, with_files=True):
    """Restaura la base (y los archivos) de un respaldo. Antes deja un respaldo de seguridad de lo que hay."""
    data = find_backup(stamp)
    check_files(data)
    safety = make_backup(prefix=SAFETY_PREFIX)
    folder = backup_dir()
    source = folder / data["base"]["archivo"]
    if data["motor"] == "sqlite":
        if not is_sqlite():
            raise BackupError("Este respaldo es de SQLite y el sistema usa MariaDB/MySQL.")
        restore_sqlite(source)
    else:
        if is_sqlite():
            raise BackupError("Este respaldo es de MariaDB/MySQL y el sistema usa SQLite.")
        restore_mysql(source)
    if with_files:
        restore_media(folder / data["archivos"]["archivo"])
    return data, safety
