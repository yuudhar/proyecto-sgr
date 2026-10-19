import importlib.util
import os
import re
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from core.qa.catalogo import CLASES, ESPERADO, REQUISITOS
from core.qa.pasos import Indice

SIN_RASTROS = {
    "DEBUG": "True",
    "SECRET_KEY": "django-insecure-de-prueba",
    "HTTPS": "",
    "BEHIND_PROXY": "",
    "USE_WHITENOISE": "",
    "CACHE_BACKEND": "",
    "REDIS_URL": "",
    "CSRF_TRUSTED_ORIGINS": "",
    "SECURE_HSTS_SECONDS": "",
    "DB_CONN_MAX_AGE": "",
    "DB_ENGINE": "",
    "EMAIL_HOST": "",
    "EMAIL_BACKEND": "",
}
CLAVE_BUENA = "clave-de-prueba-" + "x" * 50


def cargar(**env):
    ruta = settings.BASE_DIR / "sgr_project" / "settings.py"
    spec = importlib.util.spec_from_file_location("settings_de_despliegue", ruta)
    modulo = importlib.util.module_from_spec(spec)
    with mock.patch.dict(os.environ, {**SIN_RASTROS, **env}):
        spec.loader.exec_module(modulo)
    return modulo


class ProductionSettingsTests(SimpleTestCase):
    def test_without_variables_nothing_changes_for_development(self):
        m = cargar()
        self.assertTrue(m.DEBUG)
        self.assertEqual(m.CSRF_TRUSTED_ORIGINS, [])
        self.assertFalse(getattr(m, "SESSION_COOKIE_SECURE", False))
        self.assertFalse(getattr(m, "SECURE_SSL_REDIRECT", False))
        self.assertFalse(hasattr(m, "CACHES"))
        self.assertFalse(hasattr(m, "LOGGING"))
        self.assertNotIn("whitenoise.middleware.WhiteNoiseMiddleware", m.MIDDLEWARE)
        self.assertNotIn("OPTIONS", m.DATABASES["default"])

    def test_production_refuses_the_example_secret_key(self):
        for clave in ("", "django-insecure-solo-para-desarrollo-cambiar-en-env", "cambia-esto-por-una-clave-secreta-propia"):
            with self.subTest(clave=clave):
                with self.assertRaisesMessage(ImproperlyConfigured, "SECRET_KEY"):
                    cargar(DEBUG="False", SECRET_KEY=clave)

    def test_production_accepts_its_own_secret_key_and_logs_to_the_console(self):
        m = cargar(DEBUG="False", SECRET_KEY=CLAVE_BUENA)
        self.assertFalse(m.DEBUG)
        self.assertEqual(m.SECRET_KEY, CLAVE_BUENA)
        self.assertIn("console", m.LOGGING["handlers"])
        self.assertEqual(m.LOGGING["root"]["level"], "INFO")

    def test_https_turns_on_secure_cookies_redirect_and_exempts_the_health_check(self):
        m = cargar(DEBUG="False", SECRET_KEY=CLAVE_BUENA, HTTPS="True", SECURE_HSTS_SECONDS="3600")
        self.assertTrue(m.SESSION_COOKIE_SECURE)
        self.assertTrue(m.CSRF_COOKIE_SECURE)
        self.assertTrue(m.SECURE_SSL_REDIRECT)
        self.assertEqual(m.SECURE_REDIRECT_EXEMPT, [r"^salud/$"])
        self.assertEqual(m.SECURE_HSTS_SECONDS, 3600)

    def test_hsts_is_off_unless_asked_for(self):
        self.assertEqual(cargar(DEBUG="False", SECRET_KEY=CLAVE_BUENA, HTTPS="True").SECURE_HSTS_SECONDS, 0)

    def test_behind_a_proxy_django_trusts_the_forwarded_protocol(self):
        m = cargar(BEHIND_PROXY="True")
        self.assertEqual(m.SECURE_PROXY_SSL_HEADER, ("HTTP_X_FORWARDED_PROTO", "https"))

    def test_trusted_origins_come_from_the_env_as_a_list(self):
        m = cargar(CSRF_TRUSTED_ORIGINS=" https://sgr.ejemplo.cl, https://www.sgr.ejemplo.cl ,")
        self.assertEqual(m.CSRF_TRUSTED_ORIGINS, ["https://sgr.ejemplo.cl", "https://www.sgr.ejemplo.cl"])

    def test_whitenoise_is_optional_and_goes_right_after_the_security_middleware(self):
        m = cargar(USE_WHITENOISE="True")
        self.assertEqual(m.MIDDLEWARE[0], "django.middleware.security.SecurityMiddleware")
        self.assertEqual(m.MIDDLEWARE[1], "whitenoise.middleware.WhiteNoiseMiddleware")
        self.assertEqual(m.STORAGES["staticfiles"]["BACKEND"], "whitenoise.storage.CompressedStaticFilesStorage")

    def test_static_files_are_collected_in_staticfiles(self):
        self.assertEqual(cargar().STATIC_ROOT, settings.BASE_DIR / "staticfiles")

    def test_the_shared_cache_for_recovery_attempts_is_chosen_from_the_env(self):
        redis = cargar(CACHE_BACKEND="redis", REDIS_URL="redis://cache.interno:6379/2").CACHES["default"]
        self.assertEqual(redis["BACKEND"], "django.core.cache.backends.redis.RedisCache")
        self.assertEqual(redis["LOCATION"], "redis://cache.interno:6379/2")
        self.assertEqual(cargar(CACHE_BACKEND="db").CACHES["default"]["LOCATION"], "sgr_cache")
        self.assertFalse(hasattr(cargar(CACHE_BACKEND="locmem"), "CACHES"))

    def test_an_unknown_cache_backend_stops_with_a_clear_message(self):
        with self.assertRaisesMessage(ImproperlyConfigured, "CACHE_BACKEND"):
            cargar(CACHE_BACKEND="memcached")

    def test_sqlite_gets_wal_and_a_longer_wait_only_outside_development(self):
        produccion = cargar(DEBUG="False", SECRET_KEY=CLAVE_BUENA).DATABASES["default"]["OPTIONS"]
        self.assertIn("journal_mode=WAL", produccion["init_command"])
        self.assertGreaterEqual(produccion["timeout"], 20)

    def test_persistent_connections_come_from_the_env(self):
        self.assertEqual(cargar().DATABASES["default"]["CONN_MAX_AGE"], 0)
        self.assertEqual(cargar(DB_CONN_MAX_AGE="60").DATABASES["default"]["CONN_MAX_AGE"], 60)
        with self.assertRaisesMessage(ImproperlyConfigured, "DB_CONN_MAX_AGE"):
            cargar(DB_CONN_MAX_AGE="mucho")


class ConfigurationFilesTests(SimpleTestCase):
    base = Path(settings.BASE_DIR)

    def test_the_production_env_example_has_no_secrets(self):
        ejemplo = (self.base / "deploy" / "sgr.env.example").read_text(encoding="utf-8").splitlines()
        for nombre in ("SECRET_KEY", "DB_PASSWORD", "EMAIL_HOST_PASSWORD", "EMAIL_HOST_USER", "ALLOWED_HOSTS", "EMAIL_HOST"):
            self.assertIn(f"{nombre}=", ejemplo, f"{nombre} debe ir en blanco en el ejemplo")

    def test_the_env_example_documents_the_production_variables_without_values(self):
        ejemplo = (self.base / ".env.example").read_text(encoding="utf-8")
        for nombre in ("CSRF_TRUSTED_ORIGINS", "CACHE_BACKEND", "USE_WHITENOISE", "BEHIND_PROXY", "HTTPS"):
            self.assertIn(nombre, ejemplo)
        for linea in ejemplo.splitlines():
            if linea.startswith(("SECRET_KEY=", "DB_PASSWORD=")) and "SECRET_KEY" in linea:
                self.assertIn("cambia-esto", linea)

    def test_the_requirements_pin_the_server_packages(self):
        produccion = (self.base / "deploy" / "requirements-produccion.txt").read_text(encoding="utf-8")
        for paquete in ("gunicorn", "whitenoise", "redis"):
            self.assertRegex(produccion, rf"(?m)^{paquete}==\d+")

    def test_deploy_files_exist(self):
        for archivo in ("gunicorn.conf.py", "sgr.service", "nginx-sgr.conf", "instalar_ec2.sh", "actualizar.sh"):
            self.assertTrue((self.base / "deploy" / archivo).is_file(), archivo)

    def test_the_al2023_deploy_files_exist(self):
        for archivo in ("instalar_al2023.sh", "https_certificado.sh", "apache-http.conf", "apache-https.conf", "sgr.env.example"):
            self.assertTrue((self.base / "deploy" / "al2023" / archivo).is_file(), archivo)

    def test_the_al2023_env_example_has_no_secrets_and_every_key_the_scripts_set(self):
        carpeta = self.base / "deploy" / "al2023"
        lineas = (carpeta / "sgr.env.example").read_text(encoding="utf-8").splitlines()
        for nombre in ("SECRET_KEY", "DB_PASSWORD", "EMAIL_HOST_PASSWORD", "ALLOWED_HOSTS", "CSRF_TRUSTED_ORIGINS"):
            self.assertIn(f"{nombre}=", lineas, f"{nombre} debe ir en blanco en el ejemplo")
        claves = {linea.split("=")[0] for linea in lineas if "=" in linea and not linea.startswith("#")}
        for script in ("instalar_al2023.sh", "https_certificado.sh"):
            for clave in re.findall(r"(?m)^\s*fijar ([A-Z_]+) ", (carpeta / script).read_text(encoding="utf-8")):
                self.assertIn(clave, claves, f"{script} fija {clave}, que no está en el ejemplo")

    def test_the_apache_files_proxy_to_gunicorn_and_leave_phpmyadmin_and_the_certificate_check_out(self):
        carpeta = self.base / "deploy" / "al2023"
        gunicorn = (self.base / "deploy" / "gunicorn.conf.py").read_text(encoding="utf-8")
        self.assertIn("127.0.0.1:8000", gunicorn)
        for nombre in ("apache-http.conf", "apache-https.conf"):
            texto = (carpeta / nombre).read_text(encoding="utf-8")
            self.assertIn("ProxyPass / http://127.0.0.1:8000/", texto, nombre)
            self.assertIn("ProxyPass /phpMyAdmin !", texto, nombre)
            self.assertIn("ProxyPass /static/ !", texto, nombre)
            self.assertIn("/.well-known/acme-challenge/", texto, nombre)
            self.assertIn("__HOST__", texto, nombre)
        https = (carpeta / "apache-https.conf").read_text(encoding="utf-8")
        self.assertIn('RequestHeader set X-Forwarded-Proto "https"', https)
        self.assertIn("/etc/letsencrypt/live/__HOST__/fullchain.pem", https)
        self.assertIn("RewriteRule ^ https://__HOST__", https)

    def test_the_al2023_scripts_use_dnf_check_the_mariadb_version_and_ask_for_certbot_5_4(self):
        carpeta = self.base / "deploy" / "al2023"
        instalar = (carpeta / "instalar_al2023.sh").read_text(encoding="utf-8")
        self.assertNotIn("apt-get", instalar)
        self.assertIn("dnf install", instalar)
        self.assertIn("mariadb105-server", instalar)
        self.assertIn("python3.13", instalar)
        https = (carpeta / "https_certificado.sh").read_text(encoding="utf-8")
        self.assertIn("certbot>=5.4", https)
        self.assertIn("--ip-address", https)
        self.assertIn("--preferred-profile shortlived", https)

    def test_the_al2023_shell_scripts_have_valid_syntax(self):
        import shutil
        import subprocess

        if not shutil.which("bash"):
            self.skipTest("no hay bash")
        for script in ("instalar_al2023.sh", "https_certificado.sh"):
            resultado = subprocess.run(["bash", "-n", str(self.base / "deploy" / "al2023" / script)], capture_output=True, text=True)
            self.assertEqual(resultado.returncode, 0, resultado.stderr)

    def test_secrets_stay_out_of_git(self):
        ignorados = (self.base / ".gitignore").read_text(encoding="utf-8").splitlines()
        for linea in (".env", "db.sqlite3", "staticfiles/", "COMMIT"):
            self.assertIn(linea, ignorados)

    def test_the_version_file_names_the_delivery(self):
        self.assertRegex((self.base / "VERSION").read_text(encoding="utf-8").strip(), r"^v\d+")


class HealthCheckTests(TestCase):
    def test_it_answers_without_a_session_and_says_the_version(self):
        respuesta = self.client.get(reverse("salud"))
        self.assertEqual(respuesta.status_code, 200)
        datos = respuesta.json()
        self.assertEqual((datos["servicio"], datos["base_de_datos"], datos["cache"]), ("ok", "ok", "ok"))
        self.assertRegex(datos["version"], r"^v\d+")

    def test_it_is_a_get_only_and_never_cached(self):
        self.assertEqual(self.client.post(reverse("salud")).status_code, 405)
        self.assertIn("no-cache", self.client.get(reverse("salud"))["Cache-Control"])

    def test_it_shows_no_secrets(self):
        cuerpo = self.client.get(reverse("salud")).content.decode()
        self.assertNotIn(settings.SECRET_KEY, cuerpo)
        for palabra in ("password", "clave", "SECRET", "token"):
            self.assertNotIn(palabra, cuerpo)

    def test_it_reports_503_when_the_database_fails(self):
        with mock.patch("core.health.connection.cursor", side_effect=RuntimeError("sin base")):
            respuesta = self.client.get(reverse("salud"))
        self.assertEqual(respuesta.status_code, 503)
        self.assertEqual(respuesta.json()["base_de_datos"], "error")

    def test_it_reports_503_when_the_cache_fails(self):
        with mock.patch("core.health.cache.set", side_effect=RuntimeError("sin caché")):
            respuesta = self.client.get(reverse("salud"))
        self.assertEqual(respuesta.status_code, 503)
        self.assertEqual(respuesta.json()["cache"], "error")


class TestRegistryTests(SimpleTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.indice = Indice(settings.BASE_DIR)

    def nombres_reales(self):
        import ast

        reales = {}
        for clase, (_, nodo) in self.indice.clases.items():
            metodos = [m.name[5:] for m in nodo.body if isinstance(m, ast.FunctionDef) and m.name.startswith("test_")]
            if metodos:
                reales[clase] = metodos
        return reales

    def test_every_test_has_an_expected_result_in_spanish(self):
        faltan = []
        for clase, metodos in self.nombres_reales().items():
            for metodo in metodos:
                if not ESPERADO.get(clase, {}).get(metodo, "").strip():
                    faltan.append(f"{clase}.test_{metodo}")
        self.assertEqual(faltan, [], "Agrega su resultado esperado en core/qa/esperado_*.py")

    def test_the_catalogue_has_no_leftovers_for_tests_that_no_longer_exist(self):
        reales = self.nombres_reales()
        sobran = [f"{c}.{m}" for c, d in ESPERADO.items() for m in d if m not in reales.get(c, [])]
        self.assertEqual(sobran, [])

    def test_every_class_maps_to_known_requirements(self):
        for clase in self.nombres_reales():
            self.assertIn(clase, CLASES, f"{clase} no está en core/qa/catalogo.py")
            for codigo in CLASES[clase][0]:
                self.assertIn(codigo, REQUISITOS)

    def test_every_step_list_ends_with_the_check_and_is_not_empty(self):
        for clase, metodos in list(self.nombres_reales().items())[:12]:
            for metodo in metodos[:3]:
                pasos = self.indice.pasos(clase, metodo)
                self.assertGreaterEqual(len(pasos), 2)
                self.assertEqual(pasos[-1], "Comprobar el resultado esperado")

    def test_the_summary_by_requirement_counts_each_status(self):
        from core.qa import registro

        filas = [{"Requisito": "A1-01, A3-03", "Estado": registro.APROBADA}, {"Requisito": "A1-01", "Estado": registro.FALLIDA}]
        cuentas = registro.resumen_por_requisito(filas)
        self.assertEqual(cuentas["A1-01"][registro.APROBADA], 1)
        self.assertEqual(cuentas["A1-01"][registro.FALLIDA], 1)
        self.assertEqual(cuentas["A3-03"][registro.APROBADA], 1)

