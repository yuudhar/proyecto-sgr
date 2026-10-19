import json
import unittest
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.test.runner import DiscoverRunner

from core.qa import registro


class _Resultado(unittest.TextTestResult):

    estados = {}

    def _anotar(self, test, estado, detalle=""):
        self.estados[test.id()] = {"estado": estado, "detalle": detalle}

    def addSuccess(self, test):
        super().addSuccess(test)
        self._anotar(test, registro.APROBADA)

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self._anotar(test, registro.FALLIDA, self._exc_info_to_string(err, test))

    def addError(self, test, err):
        super().addError(test, err)
        self._anotar(test, registro.ERROR, self._exc_info_to_string(err, test))

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self._anotar(test, registro.OMITIDA, reason)

    def addExpectedFailure(self, test, err):
        super().addExpectedFailure(test, err)
        self._anotar(test, registro.APROBADA)

    def addUnexpectedSuccess(self, test):
        super().addUnexpectedSuccess(test)
        self._anotar(test, registro.FALLIDA, "Éxito inesperado")


class _Runner(DiscoverRunner):
    def get_resultclass(self):
        return _Resultado


class Command(BaseCommand):
    help = "Ejecuta las pruebas y escribe el registro de pruebas funcionales (Excel y CSV) en docs/pruebas/."

    def add_arguments(self, parser):
        parser.add_argument("--salida", default="docs/pruebas", help="Carpeta de salida (por defecto docs/pruebas).")
        parser.add_argument("--responsable", default="Equipo SGR", help="Nombre que figura como responsable de la ejecución.")
        parser.add_argument("--paralelo", type=int, default=0, help="Procesos en paralelo (0 = automático; 1 = en serie).")
        parser.add_argument("--resultados", help="Archivo JSON de una ejecución anterior: arma el registro sin correr las pruebas.")

    def handle(self, *args, **opciones):
        base = Path(settings.BASE_DIR)
        salida = (base / opciones["salida"]).resolve()
        carpeta_resultados = salida / "resultados"
        carpeta_resultados.mkdir(parents=True, exist_ok=True)

        if opciones["resultados"]:
            datos = json.loads(Path(opciones["resultados"]).read_text(encoding="utf-8"))
            resultados, meta_ejecucion = datos["resultados"], datos["ejecucion"]
        else:
            resultados, meta_ejecucion = self._ejecutar(opciones["paralelo"])
            nombre = f"ejecucion_{meta_ejecucion['fecha'][:10]}.json"
            (carpeta_resultados / nombre).write_text(
                json.dumps({"ejecucion": meta_ejecucion, "resultados": resultados}, ensure_ascii=False, indent=1), encoding="utf-8"
            )
            self.stdout.write(f"Detalle de la ejecución: {carpeta_resultados / nombre}")

        archivo = f"docs/pruebas/resultados/ejecucion_{meta_ejecucion['fecha'][:10]}.json"
        filas = registro.filas(base, resultados, opciones["responsable"], meta_ejecucion["fecha"], archivo)
        meta = {
            "Fecha de la ejecución": meta_ejecucion["fecha"],
            "Responsable": opciones["responsable"],
            "Entorno": meta_ejecucion["entorno"],
            "Base de datos": meta_ejecucion["base"],
            "Pruebas encontradas": meta_ejecucion["total"],
            "Duración (s)": meta_ejecucion["duracion"],
        }
        extras = {}
        for clave, nombre in (("navegador", "navegador.json"), ("estres", "estres.json")):
            ruta = carpeta_resultados / nombre
            if ruta.exists():
                extras[clave] = json.loads(ruta.read_text(encoding="utf-8"))
        totales = registro.escribir(salida, filas, meta, extras)
        self.stdout.write(self.style.SUCCESS(f"Registro escrito en {salida}"))
        self.stdout.write(", ".join(f"{estado}: {n}" for estado, n in totales.items()))
        if any(totales.get(e) for e in (registro.FALLIDA, registro.ERROR)):
            raise CommandError("Hay pruebas que no pasan: revisa el registro y la hoja «Defectos».")

    def _ejecutar(self, paralelo):
        import platform
        import time

        import django
        from django.db import connection

        _Resultado.estados = {}
        runner = _Runner(verbosity=1, interactive=False, parallel=paralelo or 0)
        inicio = time.time()
        runner.run_tests([])
        duracion = round(time.time() - inicio, 1)
        total = len(_Resultado.estados)
        if not total:
            raise CommandError("No se encontraron pruebas.")
        meta = {
            "fecha": registro.ahora(),
            "entorno": f"Python {platform.python_version()} · Django {django.get_version()} · {platform.system()} {platform.release()}",
            "base": connection.vendor,
            "total": total,
            "duracion": duracion,
        }
        return dict(_Resultado.estados), meta
