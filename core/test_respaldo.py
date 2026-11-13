"""Versión 43: respaldo diario de la base y de los archivos subidos, y su restauración."""
import gzip
import io
import json
import shutil
import sqlite3
import tarfile
import tempfile
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.core.management import CommandError, call_command
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core import respaldo


class BackupBase(SimpleTestCase):
    """Una base SQLite de verdad en una carpeta temporal (la de las pruebas vive en memoria) y archivos de ejemplo."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="sgr-respaldo-prueba-"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.db = self.root / "base.sqlite3"
        with sqlite3.connect(self.db) as con:
            con.execute("CREATE TABLE dato (id INTEGER PRIMARY KEY, texto TEXT)")
            con.execute("INSERT INTO dato (texto) VALUES ('original')")
        self.media = self.root / "media"
        (self.media / "evidencias").mkdir(parents=True)
        (self.media / "evidencias" / "acta.txt").write_text("acta original", encoding="utf-8")
        self.backups = self.root / "respaldos"
        engine = {"ENGINE": "django.db.backends.sqlite3", "NAME": str(self.db)}
        overridden = override_settings(BACKUP_DIR=self.backups, MEDIA_ROOT=self.media)
        overridden.enable()
        self.addCleanup(overridden.disable)
        for patcher in (
            mock.patch.object(respaldo, "db_settings", return_value=engine),
            mock.patch.object(respaldo, "connection"),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def rows(self):
        with sqlite3.connect(self.db) as con:
            return [r[0] for r in con.execute("SELECT texto FROM dato ORDER BY id")]


class MakeBackupTests(BackupBase):

    def test_a_backup_is_three_files_with_the_same_stamp(self):
        data = respaldo.make_backup()
        names = sorted(p.name for p in self.backups.iterdir())
        self.assertEqual(names, [f"{data['sello']}-archivos.tar.gz", f"{data['sello']}-base.sql.gz", f"{data['sello']}.json"])
        self.assertTrue(data["sello"].startswith("sgr-"))

    def test_the_manifest_has_the_version_the_sizes_and_the_fingerprints(self):
        data = respaldo.make_backup()
        stored = json.loads((self.backups / f"{data['sello']}.json").read_text(encoding="utf-8"))
        self.assertEqual(stored, data)
        self.assertEqual(data["motor"], "sqlite")
        self.assertEqual(data["version"], respaldo.read_version())
        self.assertEqual(data["base"]["sha256"], respaldo.sha256_of(self.backups / data["base"]["archivo"]))
        self.assertEqual(data["archivos"]["sha256"], respaldo.sha256_of(self.backups / data["archivos"]["archivo"]))
        self.assertGreaterEqual(data["archivos"]["elementos"], 2)

    def test_the_files_are_only_readable_by_their_owner(self):
        data = respaldo.make_backup()
        for path in self.backups.iterdir():
            self.assertEqual(path.stat().st_mode & 0o077, 0, path.name)
        self.assertEqual(self.backups.stat().st_mode & 0o077, 0)
        self.assertTrue(data)

    def test_the_database_copy_can_be_opened_and_has_the_data(self):
        data = respaldo.make_backup()
        copy = self.root / "copia.sqlite3"
        with gzip.open(self.backups / data["base"]["archivo"], "rb") as src:
            copy.write_bytes(src.read())
        with sqlite3.connect(copy) as con:
            self.assertEqual([r[0] for r in con.execute("SELECT texto FROM dato")], ["original"])

    def test_the_uploaded_files_are_inside(self):
        data = respaldo.make_backup()
        with tarfile.open(self.backups / data["archivos"]["archivo"]) as archive:
            self.assertIn("evidencias/acta.txt", archive.getnames())

    def test_without_uploaded_files_the_backup_is_still_valid(self):
        shutil.rmtree(self.media)
        data = respaldo.make_backup()
        self.assertEqual(data["archivos"]["elementos"], 0)

    def test_a_failure_leaves_no_partial_files(self):
        with mock.patch.object(respaldo, "pack_media", side_effect=OSError("disco lleno")):
            with self.assertRaises(OSError):
                respaldo.make_backup()
        self.assertEqual(list(self.backups.iterdir()), [])

    def test_an_empty_dump_is_not_accepted(self):
        def empty(target):
            with gzip.open(target, "wb"):
                pass

        with mock.patch.object(respaldo, "dump_sqlite", side_effect=empty):
            with self.assertRaisesMessage(respaldo.BackupError, "quedó vacío"):
                respaldo.make_backup()
        self.assertEqual(list(self.backups.iterdir()), [])

    def test_two_backups_in_the_same_second_do_not_overwrite_each_other(self):
        now = timezone.now()
        respaldo.make_backup(now=now)
        with self.assertRaisesMessage(respaldo.BackupError, "Ya existe un respaldo"):
            respaldo.make_backup(now=now)

    def test_the_stamp_uses_santiago_time(self):
        moment = datetime(2026, 11, 12, 6, 30, 0, tzinfo=dt_timezone.utc)
        self.assertEqual(respaldo.new_stamp(now=moment), "sgr-20261112-033000")


class MysqlDumpTests(BackupBase):

    def setUp(self):
        super().setUp()
        self.cfg = {"ENGINE": "django.db.backends.mysql", "NAME": "sgr_django", "USER": "sgr", "PASSWORD": "clave-secreta", "HOST": "localhost", "PORT": "3306"}
        patcher = mock.patch.object(respaldo, "db_settings", return_value=self.cfg)
        patcher.start()
        self.addCleanup(patcher.stop)

    def fake_process(self, sql, code=0, error=b""):
        process = mock.Mock()
        process.stdout = io.BytesIO(sql)
        process.stderr = io.BytesIO(error)
        process.wait.return_value = code
        return process

    def test_the_password_goes_in_the_environment_and_never_in_the_command(self):
        process = self.fake_process(b"CREATE TABLE x;\n-- Dump completed on 2026-11-12\n")
        with mock.patch.object(respaldo.subprocess, "Popen", return_value=process) as popen:
            data = respaldo.make_backup()
        command = popen.call_args.args[0]
        self.assertEqual(command[0], "mysqldump")
        self.assertNotIn("clave-secreta", " ".join(command))
        self.assertEqual(popen.call_args.kwargs["env"]["MYSQL_PWD"], "clave-secreta")
        self.assertIn("--single-transaction", command)
        self.assertEqual(data["motor"], "mysql")

    def test_a_dump_that_does_not_finish_is_refused(self):
        process = self.fake_process(b"CREATE TABLE x;\n")
        with mock.patch.object(respaldo.subprocess, "Popen", return_value=process):
            with self.assertRaisesMessage(respaldo.BackupError, "incompleto"):
                respaldo.make_backup()
        self.assertEqual(list(self.backups.iterdir()), [])

    def test_mysqldump_failing_reports_its_message(self):
        process = self.fake_process(b"", code=2, error=b"Access denied")
        with mock.patch.object(respaldo.subprocess, "Popen", return_value=process):
            with self.assertRaisesMessage(respaldo.BackupError, "Access denied"):
                respaldo.make_backup()

    def test_a_missing_mysqldump_says_what_to_install(self):
        with mock.patch.object(respaldo.subprocess, "Popen", side_effect=FileNotFoundError):
            with self.assertRaisesMessage(respaldo.BackupError, "mariadb105"):
                respaldo.make_backup()

    def test_restoring_pipes_the_dump_to_mysql_with_the_password_in_the_environment(self):
        sql = b"CREATE TABLE x;\n-- Dump completed on 2026-11-12\n"
        with mock.patch.object(respaldo.subprocess, "Popen", return_value=self.fake_process(sql)):
            data = respaldo.make_backup()
        process = mock.Mock()
        process.stdin = io.BytesIO()
        process.stderr = io.BytesIO(b"")
        process.wait.return_value = 0
        written = []
        process.stdin.close = lambda: written.append(process.stdin.getvalue())
        with mock.patch.object(respaldo.subprocess, "Popen", return_value=process) as popen:
            respaldo.restore_mysql(self.backups / data["base"]["archivo"])
        self.assertEqual(popen.call_args.args[0][0], "mysql")
        self.assertNotIn("clave-secreta", " ".join(popen.call_args.args[0]))
        self.assertEqual(popen.call_args.kwargs["env"]["MYSQL_PWD"], "clave-secreta")
        self.assertEqual(written, [sql])


class RetentionTests(BackupBase):

    def make(self, days_ago, prefix=respaldo.PREFIX):
        return respaldo.make_backup(prefix=prefix, now=timezone.now() - timedelta(days=days_ago))["sello"]

    def test_old_backups_are_deleted_and_recent_ones_stay(self):
        old, mid, new = self.make(30), self.make(10), self.make(1)
        removed = respaldo.apply_retention(keep_days=14, minimum=1)
        self.assertEqual(removed, [old])
        self.assertEqual([b["sello"] for b in respaldo.list_backups()], [new, mid])
        self.assertFalse(any(old in p.name for p in self.backups.iterdir()))

    def test_the_newest_ones_are_always_kept_even_if_they_are_old(self):
        stamps = [self.make(60), self.make(50), self.make(40)]
        removed = respaldo.apply_retention(keep_days=14, minimum=2)
        self.assertEqual(removed, [stamps[0]])

    def test_safety_backups_taken_before_restoring_are_never_deleted_by_age(self):
        safety = self.make(90, prefix=respaldo.SAFETY_PREFIX)
        self.make(1)
        self.assertEqual(respaldo.apply_retention(keep_days=14, minimum=1), [])
        self.assertIn(safety, [b["sello"] for b in respaldo.list_backups()])

    def test_the_days_come_from_the_setting(self):
        self.make(20)
        self.make(1)
        with override_settings(BACKUP_KEEP_DAYS=30):
            self.assertEqual(respaldo.apply_retention(minimum=1), [])


class StatusTests(BackupBase):

    def test_without_backups(self):
        self.assertEqual(respaldo.status(), "sin respaldos")

    def test_a_recent_backup_is_ok(self):
        respaldo.make_backup()
        self.assertEqual(respaldo.status(), "ok")

    def test_an_old_backup_is_late(self):
        respaldo.make_backup(now=timezone.now() - timedelta(hours=50))
        self.assertEqual(respaldo.status(), "atrasado")

    def test_the_limit_comes_from_the_setting(self):
        respaldo.make_backup(now=timezone.now() - timedelta(hours=50))
        with override_settings(BACKUP_MAX_AGE_HOURS=72):
            self.assertEqual(respaldo.status(), "ok")

    def test_a_safety_backup_does_not_count_as_the_daily_one(self):
        respaldo.make_backup(prefix=respaldo.SAFETY_PREFIX)
        self.assertEqual(respaldo.status(), "sin respaldos")

    def test_an_incomplete_backup_is_not_listed(self):
        data = respaldo.make_backup()
        (self.backups / data["archivos"]["archivo"]).unlink()
        self.assertEqual(respaldo.list_backups(), [])


class RestoreTests(BackupBase):

    def change_everything(self):
        with sqlite3.connect(self.db) as con:
            con.execute("UPDATE dato SET texto = 'cambiado'")
            con.execute("INSERT INTO dato (texto) VALUES ('nuevo')")
        (self.media / "evidencias" / "acta.txt").write_text("acta cambiada", encoding="utf-8")
        (self.media / "otra.txt").write_text("sobra", encoding="utf-8")

    def test_restoring_brings_back_the_database_and_the_files(self):
        data = respaldo.make_backup()
        self.change_everything()
        respaldo.restore_backup(data["sello"])
        self.assertEqual(self.rows(), ["original"])
        self.assertEqual((self.media / "evidencias" / "acta.txt").read_text(encoding="utf-8"), "acta original")
        self.assertFalse((self.media / "otra.txt").exists())

    def test_before_restoring_it_keeps_a_safety_copy_of_what_was_there(self):
        data = respaldo.make_backup()
        self.change_everything()
        _data, safety = respaldo.restore_backup(data["sello"])
        self.assertTrue(safety["sello"].startswith(respaldo.SAFETY_PREFIX))
        copy = self.root / "seguridad.sqlite3"
        with gzip.open(self.backups / safety["base"]["archivo"], "rb") as src:
            copy.write_bytes(src.read())
        with sqlite3.connect(copy) as con:
            self.assertEqual([r[0] for r in con.execute("SELECT texto FROM dato ORDER BY id")], ["cambiado", "nuevo"])

    def test_the_files_can_be_left_out(self):
        data = respaldo.make_backup()
        self.change_everything()
        respaldo.restore_backup(data["sello"], with_files=False)
        self.assertEqual(self.rows(), ["original"])
        self.assertTrue((self.media / "otra.txt").exists())

    def test_a_damaged_backup_is_refused_and_nothing_changes(self):
        data = respaldo.make_backup()
        self.change_everything()
        with open(self.backups / data["base"]["archivo"], "ab") as damaged:
            damaged.write(b"basura")
        with self.assertRaisesMessage(respaldo.BackupError, "dañado"):
            respaldo.restore_backup(data["sello"])
        self.assertEqual(self.rows(), ["cambiado", "nuevo"])

    def test_an_unknown_stamp_is_refused(self):
        with self.assertRaisesMessage(respaldo.BackupError, "No existe el respaldo"):
            respaldo.restore_backup("sgr-20000101-000000")

    def test_a_backup_from_another_engine_is_refused(self):
        data = respaldo.make_backup()
        manifest = self.backups / f"{data['sello']}.json"
        stored = json.loads(manifest.read_text(encoding="utf-8"))
        stored["motor"] = "mysql"
        manifest.write_text(json.dumps(stored), encoding="utf-8")
        with self.assertRaisesMessage(respaldo.BackupError, "MariaDB/MySQL"):
            respaldo.restore_backup(data["sello"])

    def test_a_tar_with_paths_outside_the_folder_does_not_touch_anything(self):
        data = respaldo.make_backup()
        evil = self.backups / data["archivos"]["archivo"]
        with tarfile.open(evil, "w:gz") as archive:
            info = tarfile.TarInfo("../fuera.txt")
            payload = b"peligro"
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))
        with self.assertRaises(respaldo.BackupError):
            respaldo.restore_media(evil)
        self.assertFalse((self.root / "fuera.txt").exists())
        self.assertEqual((self.media / "evidencias" / "acta.txt").read_text(encoding="utf-8"), "acta original")


class CommandTests(BackupBase):

    def run_command(self, name, *args):
        out = io.StringIO()
        call_command(name, *args, stdout=out)
        return out.getvalue()

    def test_respaldar_makes_one_and_lists_it(self):
        text = self.run_command("respaldar")
        self.assertIn("Respaldo sgr-", text)
        listing = self.run_command("respaldar", "--listar")
        self.assertIn("sgr-", listing)
        self.assertEqual(len(respaldo.list_backups()), 1)

    def test_respaldar_with_nothing_to_list_says_so(self):
        self.assertIn("No hay respaldos", self.run_command("respaldar", "--listar"))

    def test_respaldar_applies_the_retention(self):
        respaldo.make_backup(now=timezone.now() - timedelta(days=40))
        respaldo.make_backup(now=timezone.now() - timedelta(days=39))
        respaldo.make_backup(now=timezone.now() - timedelta(days=38))
        respaldo.make_backup(now=timezone.now() - timedelta(days=37))
        text = self.run_command("respaldar")
        self.assertIn("Se borraron", text)

    def test_respaldar_can_skip_the_cleaning(self):
        respaldo.make_backup(now=timezone.now() - timedelta(days=40))
        self.assertNotIn("Se borraron", self.run_command("respaldar", "--sin-limpiar"))

    def test_a_failed_backup_is_an_error_exit(self):
        with mock.patch.object(respaldo, "dump_sqlite", side_effect=respaldo.BackupError("no hay espacio")):
            with self.assertRaisesMessage(CommandError, "no hay espacio"):
                call_command("respaldar", stdout=io.StringIO())

    def test_restaurar_without_confirming_only_shows_the_plan(self):
        data = respaldo.make_backup()
        with sqlite3.connect(self.db) as con:
            con.execute("UPDATE dato SET texto = 'cambiado'")
        text = self.run_command("restaurar_respaldo", data["sello"])
        self.assertIn("No se cambió nada", text)
        self.assertEqual(self.rows(), ["cambiado"])

    def test_restaurar_confirmed_restores_and_names_the_safety_copy(self):
        data = respaldo.make_backup()
        with sqlite3.connect(self.db) as con:
            con.execute("UPDATE dato SET texto = 'cambiado'")
        text = self.run_command("restaurar_respaldo", data["sello"], "--confirmar")
        self.assertIn("sgr-antes-de-restaurar-", text)
        self.assertEqual(self.rows(), ["original"])

    def test_restaurar_an_unknown_stamp_is_an_error(self):
        with self.assertRaisesMessage(CommandError, "No existe el respaldo"):
            call_command("restaurar_respaldo", "sgr-1", stdout=io.StringIO())


class HealthTests(TestCase):

    def test_the_health_check_reports_the_backup_without_failing_the_service(self):
        with mock.patch("core.health.respaldo.status", return_value="sin respaldos"):
            response = self.client.get(reverse("core:salud")) if False else self.client.get("/salud/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["respaldo"], "sin respaldos")

    def test_a_late_backup_does_not_turn_the_service_off(self):
        with mock.patch("core.health.respaldo.status", return_value="atrasado"):
            response = self.client.get("/salud/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["respaldo"], "atrasado")

    def test_an_error_reading_the_backups_is_shown_as_error(self):
        with mock.patch("core.health.respaldo.status", side_effect=OSError):
            response = self.client.get("/salud/")
        self.assertEqual(response.json()["respaldo"], "error")


class DeployFilesTests(SimpleTestCase):

    def read(self, *parts):
        return (Path(settings.BASE_DIR).joinpath(*parts)).read_text(encoding="utf-8")

    def test_the_timer_runs_daily_and_catches_up_after_a_shutdown(self):
        text = self.read("deploy", "sgr-respaldo.timer")
        self.assertIn("OnCalendar=*-*-* 03:30:00", text)
        self.assertIn("Persistent=true", text)
        self.assertIn("WantedBy=timers.target", text)

    def test_the_service_runs_the_command_as_the_app_user_with_its_environment(self):
        text = self.read("deploy", "sgr-respaldo.service")
        self.assertIn("ExecStart=/opt/sgr/venv/bin/python manage.py respaldar", text)
        self.assertIn("User=sgr", text)
        self.assertIn("EnvironmentFile=/etc/sgr/sgr.env", text)
        self.assertIn("Type=oneshot", text)

    def test_the_installer_enables_the_timer_and_makes_a_first_backup(self):
        text = self.read("deploy", "instalar_respaldo.sh")
        for piece in ("sgr-respaldo.timer", "enable --now", "manage.py\" respaldar", "install -d -o sgr -g sgr -m 700"):
            self.assertIn(piece, text)

    def test_every_deploy_installs_the_backup_and_a_failure_does_not_stop_it(self):
        text = self.read("deploy", "actualizar.sh")
        self.assertIn("instalar_respaldo.sh", text)
        self.assertIn("||", text.split("instalar_respaldo.sh", 1)[1].split("\n", 1)[0])

    def test_the_examples_document_the_settings_and_no_script_carries_a_password(self):
        for name in (("deploy", "sgr.env.example"), ("deploy", "al2023", "sgr.env.example")):
            text = self.read(*name)
            for key in ("BACKUP_DIR=", "BACKUP_KEEP_DAYS=", "BACKUP_MAX_AGE_HOURS="):
                self.assertIn(key, text)
        for name in ("sgr-respaldo.service", "instalar_respaldo.sh"):
            self.assertNotIn("PASSWORD", self.read("deploy", name).replace("EnvironmentFile", ""))

    def test_the_backups_folder_is_not_uploaded_to_git(self):
        self.assertIn("respaldos/", self.read(".gitignore"))
