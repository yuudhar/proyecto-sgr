"""Carga de datos para la revisión (v36): comando reproducible, seis cuentas de prueba y diagrama de modelos."""
import importlib.util
import os
import re
import subprocess
import sys
from datetime import timedelta
from io import BytesIO, StringIO
from pathlib import Path
from unittest import mock

from django.apps import apps
from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client, TestCase
from django.urls import reverse
from openpyxl import load_workbook

from accounts.models import UserProfile
from core.datos_prueba import cargar_datos_prueba
from core.management.commands import cargar_datos_revision as carga
from core.models import AuditLog
from evidence.models import Evidence, Validation
from operations.models import Activity, Commitment, Followup
from organization.models import Beneficiary, Delegation, Item
from planning import calculation
from planning.models import Adjustment, Feedback, Indicator, Period

User = get_user_model()

CLAVE = "Revision#2026x"
CLAVE_NUEVA = "Otra#Clave2026y"
BASE = Path(settings.BASE_DIR)


def contrasena_escrita(linea):
    """True si la línea parece escribir una contraseña real (y no un marcador como <clave> o $CLAVE)."""
    asignada = re.search(r"(?:SGR_REVISION_PASSWORD|SGR_PASSWORD_[A-Z_]+)=['\"]?(?![<$'\"\s])\S", linea)
    en_argumento = re.search(r"--password(?:=|\s+)['\"]?(?![<$'\"\s])[A-Za-z0-9#!%&*+.,:;@^_-]{4,}", linea)
    return bool(asignada or (en_argumento and not re.search(r"--password`", linea)))


def cargar(*argumentos, **opciones):
    salida = StringIO()
    call_command("cargar_datos_revision", *argumentos, stdout=salida, **opciones)
    return salida.getvalue()


def modelos_de_negocio():
    for etiqueta in carga.APLICACIONES_PROPIAS:
        yield from apps.get_app_config(etiqueta).get_models()


def totales():
    return {modelo._meta.label: modelo._base_manager.count() for modelo in modelos_de_negocio()}


def cliente_de(usuario):
    cliente = Client(HTTP_HOST="localhost", raise_request_exception=False)
    cliente.force_login(User.objects.get(username=usuario))
    return cliente


def filas_exportadas(respuesta):
    """Filas de datos de un Excel exportado (las que siguen a la fila de encabezados «Identificador»)."""
    hoja = load_workbook(BytesIO(respuesta.content)).active
    filas = [[celda.value for celda in fila] for fila in hoja.iter_rows()]
    inicio = next(i for i, fila in enumerate(filas) if fila[0] == "Identificador")
    return [fila for fila in filas[inicio + 1:] if fila[0] is not None]


class RevisionTestCase(TestCase):
    """Base de datos vacía + una ejecución del comando (la misma que se hace en AWS)."""

    @classmethod
    def setUpTestData(cls):
        cls.salida = cargar("--password", CLAVE)
        cls.norte = Delegation.objects.get(name="Delegación Norte")
        cls.sur = Delegation.objects.get(name="Delegación Sur")
        cls.ambitos = {"Norte": cls.norte, "Sur": cls.sur}


class ReviewDataVolumeTests(RevisionTestCase):

    def test_there_are_at_least_2000_business_records_among_the_projects_own_models(self):
        etiquetas = [modelo._meta.label for modelo in modelos_de_negocio()]
        self.assertFalse([e for e in etiquetas if e.split(".")[0] in ("auth", "sessions", "contenttypes", "admin")])
        self.assertGreaterEqual(sum(totales().values()), carga.MINIMO_TOTAL)

    def test_the_totals_table_in_the_output_matches_the_database(self):
        impresos = {}
        for linea in self.salida.splitlines():
            partes = linea.split()
            if len(partes) == 4 and "." in partes[0] and all(p.isdigit() for p in partes[1:]):
                impresos[partes[0]] = int(partes[1])
        self.assertEqual(impresos, totales())
        total = sum(totales().values())
        self.assertRegex(self.salida, rf"TOTAL\s+{total}\b")

    def test_each_evaluated_crud_has_at_least_50_records_in_each_delegation(self):
        import core.registry  # noqa: F401
        from core.crud import registry

        self.assertEqual(set(carga.CRUDS_EVALUADOS), {"actividades", "beneficiarios"})
        for slug in carga.CRUDS_EVALUADOS:
            crud = registry.get(slug)
            activos = crud.model._base_manager.filter(deleted_at__isnull=True)
            activos = activos.filter(**crud.queryset_filter)
            self.assertGreaterEqual(activos.count(), carga.MINIMO_POR_CRUD, slug)
            if crud.delegation_lookup:
                for nombre, delegacion in self.ambitos.items():
                    cuantos = activos.filter(**{crud.delegation_lookup: delegacion}).count()
                    self.assertGreaterEqual(cuantos, carga.MINIMO_POR_CRUD, f"{slug} · {nombre}")

    def test_every_crud_filtered_by_delegation_has_at_least_50_in_each_one(self):
        import core.registry  # noqa: F401
        from core.crud import registry

        revisados = []
        for crud in registry.all():
            if not crud.delegation_lookup or not hasattr(crud.model, "deleted_at"):
                continue
            activos = crud.model._base_manager.filter(deleted_at__isnull=True)
            activos = activos.filter(**crud.queryset_filter)
            for nombre, delegacion in self.ambitos.items():
                cuantos = activos.filter(**{crud.delegation_lookup: delegacion}).count()
                self.assertGreaterEqual(cuantos, carga.MINIMO_POR_CRUD, f"{crud.slug} · {nombre}")
            revisados.append(crud.slug)
        self.assertGreaterEqual(len(revisados), 9)

    def test_there_is_more_than_one_page_of_30_in_the_lists_of_both_scopes(self):
        for nombre, delegacion in self.ambitos.items():
            self.assertGreater(Activity.objects.filter(delegation=delegacion, deleted_at__isnull=True).count(), 60, nombre)
        self.assertGreater(Beneficiary.objects.count(), 60)
        cliente = cliente_de("admin_a")
        for pagina in (1, 2, 3):
            self.assertEqual(cliente.get(reverse("core:atencion"), {"page": pagina}).status_code, 200)
            self.assertEqual(cliente.get(reverse("core:beneficiarios_list"), {"page": pagina}).status_code, 200)

    def test_the_data_is_varied_enough_to_search_filter_and_sort(self):
        actividades = Activity.objects.filter(deleted_at__isnull=True)
        self.assertEqual(set(actividades.values_list("status", flat=True)), set(Activity.Status.values))
        self.assertGreaterEqual(actividades.values("item").distinct().count(), 4)
        self.assertGreaterEqual(actividades.values("service").distinct().count(), 4)
        self.assertGreaterEqual(actividades.values("date").distinct().count(), 100)
        self.assertGreaterEqual(actividades.values("beneficiary").distinct().count(), 100)
        self.assertEqual(set(actividades.values_list("requires_visit", flat=True)), {True, False})
        self.assertEqual(set(actividades.values_list("counts_for_score", flat=True)), {True, False})
        self.assertGreaterEqual(Beneficiary.objects.values("name").distinct().count(), 200)
        self.assertGreaterEqual(Commitment.objects.values("status").distinct().count(), 4)
        self.assertEqual(set(Evidence.objects.values_list("review_status", flat=True)), set(Evidence.ReviewStatus.values))

    def test_the_data_includes_archived_records_but_most_are_active(self):
        for modelo in (Activity, Commitment):
            archivados = modelo._base_manager.filter(deleted_at__isnull=False).count()
            self.assertGreater(archivados, 0, modelo.__name__)
            self.assertLess(archivados, modelo._base_manager.count() * 0.2, modelo.__name__)

    def test_the_data_is_fictitious_and_has_valid_formats(self):
        for beneficiario in Beneficiary.objects.all():
            numero, digito = beneficiario.rut.split("-")
            self.assertEqual(digito, carga.digito_verificador(int(numero)), beneficiario.rut)
        correos = list(User.objects.values_list("email", flat=True))
        self.assertTrue(all(correo.endswith(".example") for correo in correos))
        self.assertTrue(all(c.contact.endswith(".example") or c.contact.startswith("+56") for c in Feedback.objects.all()))
        for evidencia in Evidence.objects.all():
            self.assertTrue(evidencia.file_link.storage.exists(evidencia.file_link.name), evidencia.unique_code)
        for registro in Feedback.objects.all():
            self.assertTrue(registro.support.storage.exists(registro.support.name))

    def test_the_attentions_respect_the_business_rules(self):
        limite = settings.DAILY_ENTRY_LIMIT
        por_dia = {}
        for actividad in Activity.objects.select_related("author_officer", "item", "item__parent_item", "beneficiary"):
            self.assertEqual(actividad.delegation_id, actividad.author_officer.delegation_id)
            self.assertEqual(actividad.counts_for_score, actividad.score_reason() == "", actividad.pk)
            clave = (actividad.author_officer_id, actividad.date)
            por_dia[clave] = por_dia.get(clave, 0) + 1
            self.assertGreaterEqual(actividad.date, carga.FECHA_BASE - timedelta(days=carga.DIAS_ATRAS))
            self.assertLessEqual(actividad.date, carga.FECHA_BASE)
            self.assertLess(actividad.date.weekday(), 5)
        self.assertLessEqual(max(por_dia.values()), limite)

    def test_the_followups_evidence_and_validations_hang_from_the_right_records(self):
        for secuencia in Followup.objects.values_list("sequence_number", flat=True).distinct():
            self.assertIn(secuencia, (1, 2, 3))
        self.assertEqual(Followup.objects.values("activity", "sequence_number").distinct().count(), Followup.objects.count())
        for evidencia in Evidence.objects.select_related("activity__delegation"):
            nombre = evidencia.activity.delegation.name.removeprefix("Delegación ").upper()
            self.assertTrue(evidencia.unique_code.startswith(f"EVD-{nombre}-R"), evidencia.unique_code)
            self.assertEqual(evidencia.author_officer_id, evidencia.activity.author_officer_id)
            self.assertIsNone(evidencia.activity.deleted_at)
        for validacion in Validation.objects.select_related("evidence__activity", "reviewer_officer"):
            self.assertEqual(validacion.reviewer_officer.delegation_id, validacion.evidence.activity.delegation_id)
            self.assertNotEqual(validacion.evidence.review_status, Evidence.ReviewStatus.PENDING)
        self.assertGreaterEqual(Activity.objects.filter(commitment__isnull=False).count(), 2 * 30)

    def test_the_indicators_and_adjustments_come_from_the_real_calculation(self):
        self.assertGreaterEqual(Indicator.objects.count(), carga.MINIMO_POR_CRUD)
        periodo = Period.objects.get(start_date="2026-01-01")
        self.assertEqual(calculation.recalculate_period(periodo), 0)
        self.assertEqual(Adjustment.objects.count(), Feedback.objects.filter(effective=True).count())
        self.assertGreaterEqual(Adjustment.objects.count(), carga.MINIMO_POR_CRUD)

    def test_the_command_does_not_depend_on_the_day_it_runs(self):
        fuente = Path(carga.__file__).read_text(encoding="utf-8")
        self.assertEqual(carga.SEMILLA, 2026)
        self.assertIn("random.Random(SEMILLA)", fuente)
        for prohibido in ("date.today(", "timezone.now(", "timezone.localdate(", "datetime.now(", "portal_today("):
            self.assertNotIn(prohibido, fuente)

    def test_the_command_does_not_use_the_local_demo_data_module(self):
        fuente = Path(carga.__file__).read_text(encoding="utf-8")
        self.assertNotIn("datos_prueba import", fuente)
        self.assertNotIn("cargar_datos_prueba", fuente)


class ReviewDataIdempotencyTests(RevisionTestCase):

    def archivos(self):
        return sum(len(archivos) for _, _, archivos in os.walk(settings.MEDIA_ROOT))

    def test_running_it_again_creates_nothing_and_changes_nothing(self):
        antes, archivos = totales(), self.archivos()
        usuarios = list(User.objects.order_by("pk").values_list("pk", "username", "password", "email"))
        salida = cargar()
        self.assertEqual(totales(), antes)
        self.assertEqual(self.archivos(), archivos)
        self.assertEqual(list(User.objects.order_by("pk").values_list("pk", "username", "password", "email")), usuarios)
        self.assertIn("Registros de negocio nuevos en esta ejecución: 0.", salida)
        self.assertIn("Indicadores nuevos calculados: 0.", salida)

    def test_running_it_a_third_time_keeps_what_someone_edited_or_archived(self):
        actividad = Activity.objects.filter(deleted_at__isnull=True).order_by("pk").first()
        actividad.deleted_at = actividad.created_at
        actividad.save(update_fields=["deleted_at"])
        beneficiario = Beneficiary.objects.order_by("pk").first()
        beneficiario.name = "Nombre Editado Por Alguien"
        beneficiario.save()
        antes = totales()
        cargar()
        cargar()
        self.assertEqual(totales(), antes)
        actividad.refresh_from_db()
        beneficiario.refresh_from_db()
        self.assertIsNotNone(actividad.deleted_at)
        self.assertEqual(beneficiario.name, "Nombre Editado Por Alguien")

    def test_if_some_rows_are_missing_only_those_are_created_again(self):
        faltantes = list(Followup.objects.order_by("pk").values_list("activity_id", "sequence_number")[:7])
        for actividad_id, secuencia in faltantes:
            Followup.objects.filter(activity_id=actividad_id, sequence_number=secuencia).delete()
        antes = totales()
        salida = cargar()
        self.assertIn("Registros de negocio nuevos en esta ejecución: 7.", salida)
        self.assertEqual(totales()["operations.Followup"], antes["operations.Followup"] + 7)
        for actividad_id, secuencia in faltantes:
            self.assertTrue(Followup.objects.filter(activity_id=actividad_id, sequence_number=secuencia).exists())

    def test_the_totals_match_the_ones_written_in_the_readme(self):
        texto = (BASE / "README.md").read_text(encoding="utf-8")
        cifras = totales()
        for etiqueta, cantidad in cifras.items():
            self.assertRegex(texto, rf"\|\s*`{re.escape(etiqueta)}`\s*\|\s*{cantidad}\s*\|", etiqueta)
        self.assertRegex(texto, rf"\|\s*\*\*Total\*\*\s*\|\s*\*\*{sum(cifras.values())}\*\*\s*\|")


class ReviewWithDemoDataTests(TestCase):

    def test_it_lives_together_with_the_local_demo_data_without_duplicating_or_changing_it(self):
        cargar_datos_prueba()
        demo = {
            "usuarios": list(User.objects.order_by("pk").values_list("username", "password")),
            "beneficiario": Beneficiary.objects.get(rut="11111111-1").name,
            "perfil": UserProfile.objects.get(user__username="cliente1").beneficiary_id,
        }
        cargar("--password", CLAVE)
        despues = totales()
        cargar()
        self.assertEqual(totales(), despues)
        self.assertEqual(demo["beneficiario"], Beneficiary.objects.get(rut="11111111-1").name)
        # Las cuentas que ya existían conservan su contraseña y su vínculo; el comando solo les suma atenciones.
        self.assertIsNotNone(authenticate(username="cliente1", password="Hola123!"))
        perfil = UserProfile.objects.get(user__username="cliente1")
        self.assertEqual(perfil.beneficiary_id, demo["perfil"])
        self.assertGreaterEqual(Activity.objects.filter(beneficiary=perfil.beneficiary).count(), carga.ATENCIONES_CLIENTE)
        for nombre in ("admin_a", "editor_a", "lector_a", "lector_b"):
            self.assertTrue(User.objects.filter(username=nombre).exists())
        self.assertEqual(User.objects.filter(username="cliente1").count(), 1)


class ReviewPasswordsTests(TestCase):

    def entorno_limpio(self):
        limpio = {k: v for k, v in os.environ.items() if not k.startswith(("SGR_PASSWORD_", carga.PASSWORD_ENV_COMUN))}
        return mock.patch.dict(os.environ, limpio, clear=True)

    def test_without_a_password_it_stops_before_writing_anything(self):
        with self.entorno_limpio(), mock.patch("sys.stdin") as entrada:
            entrada.isatty.return_value = False
            with self.assertRaisesMessage(CommandError, carga.PASSWORD_ENV_COMUN):
                cargar()
        self.assertEqual(Beneficiary.objects.count(), 0)
        self.assertEqual(User.objects.count(), 0)

    def test_a_weak_password_is_rejected_before_writing_anything(self):
        with self.entorno_limpio():
            with self.assertRaisesMessage(CommandError, "no es válida"):
                cargar("--password", "12345678")
        self.assertEqual(User.objects.count(), 0)
        self.assertEqual(Beneficiary.objects.count(), 0)

    def test_the_environment_variables_set_the_passwords_and_one_account_can_have_its_own(self):
        with self.entorno_limpio():
            with mock.patch.dict(os.environ, {carga.PASSWORD_ENV_COMUN: CLAVE, "SGR_PASSWORD_LECTOR_B": CLAVE_NUEVA}):
                cargar()
        for nombre in ("admin_a", "editor_a", "lector_a", "cliente1", "cliente2"):
            self.assertIsNotNone(authenticate(username=nombre, password=CLAVE), nombre)
        self.assertIsNone(authenticate(username="lector_b", password=CLAVE))
        self.assertIsNotNone(authenticate(username="lector_b", password=CLAVE_NUEVA))

    def test_reassigning_the_passwords_only_happens_when_it_is_asked_for(self):
        with self.entorno_limpio():
            cargar("--password", CLAVE)
            cargar("--password", CLAVE_NUEVA)  # las cuentas ya existen: no se toca nada
            self.assertIsNotNone(authenticate(username="admin_a", password=CLAVE))
            cargar("--password", CLAVE_NUEVA, "--reasignar-claves")
        self.assertIsNone(authenticate(username="admin_a", password=CLAVE))
        self.assertIsNotNone(authenticate(username="admin_a", password=CLAVE_NUEVA))

    def test_no_password_is_written_in_the_repository(self):
        revisados = [BASE / "README.md", BASE / "docs" / "aws" / "DESPLIEGUE_AL2023.md", BASE / "core/management/commands/cargar_datos_revision.py"]
        revisados += [archivo for archivo in sorted((BASE / "deploy").rglob("*")) if archivo.is_file()]
        sospechosas = []
        for archivo in revisados:
            for numero, linea in enumerate(archivo.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                if contrasena_escrita(linea):
                    sospechosas.append(f"{archivo.name}:{numero}: {linea.strip()}")
        self.assertEqual(sospechosas, [])

    def test_the_password_check_catches_a_written_password_and_accepts_placeholders(self):
        for mala in (
            "export SGR_REVISION_PASSWORD=Abc12345!",
            "SGR_PASSWORD_LECTOR_B='Secreta#2026'",
            'python manage.py cargar_datos_revision --password "Secreta#2026"',
            "python manage.py cargar_datos_revision --password=Secreta#2026",
        ):
            self.assertTrue(contrasena_escrita(mala), mala)
        for buena in (
            "export SGR_REVISION_PASSWORD='<contraseña-segura-de-las-cuentas>'",
            'read -rs -p "Contraseña: " SGR_REVISION_PASSWORD; export SGR_REVISION_PASSWORD',
            "SGR_PASSWORD_<ALIAS> (una cuenta) o `--password` (queda en el historial)",
            'python manage.py cargar_datos_revision --password "$CLAVE"',
            "claves[cuenta['username']] = clave",
        ):
            self.assertFalse(contrasena_escrita(buena), buena)


class ReviewAccountsTests(RevisionTestCase):

    ESPERADAS = {
        "admin_a": ("Norte", {"Jefatura", "Funcionario"}),
        "editor_a": ("Norte", {"Funcionario"}),
        "lector_a": ("Norte", {"Consulta"}),
        "lector_b": ("Sur", {"Consulta"}),
        "cliente1": (None, {"Cliente"}),
        "cliente2": (None, {"Cliente"}),
    }

    def crud(self, slug):
        import core.registry  # noqa: F401
        from core.crud import registry

        return registry.get(slug)

    def test_there_are_exactly_the_six_accounts_with_their_role_and_scope(self):
        self.assertEqual({c["username"] for c in carga.CUENTAS}, set(self.ESPERADAS))
        for nombre, (ambito, grupos) in self.ESPERADAS.items():
            usuario = User.objects.get(username=nombre)
            self.assertTrue(usuario.is_active)
            self.assertEqual(set(usuario.groups.values_list("name", flat=True)), grupos)
            perfil = usuario.profile
            if ambito:
                self.assertEqual(perfil.officer.delegation, self.ambitos[ambito], nombre)
                self.assertIsNone(perfil.beneficiary_id)
            else:
                self.assertIsNone(perfil.officer_id)
                self.assertIsNotNone(perfil.beneficiary_id)
        self.assertEqual(len(set(User.objects.values_list("email", flat=True))), 6)

    def test_no_account_is_a_superuser_or_has_access_to_the_django_admin(self):
        for nombre in self.ESPERADAS:
            usuario = User.objects.get(username=nombre)
            self.assertFalse(usuario.is_superuser, nombre)
            self.assertFalse(usuario.is_staff, nombre)

    def test_the_administrator_can_manage_the_evaluated_modules_and_users_without_being_a_superuser(self):
        admin = User.objects.get(username="admin_a")
        for slug in carga.CRUDS_EVALUADOS:
            for accion in ("view", "add", "change", "delete"):
                self.assertTrue(self.crud(slug).has_perm(admin, accion), f"{slug}:{accion}")
        for permiso in ("auth.view_user", "auth.add_user", "auth.change_user"):
            self.assertTrue(admin.has_perm(permiso), permiso)
        self.assertFalse(admin.has_perm("planning.add_period"))
        self.assertFalse(admin.has_perm("auth.change_group"))

    def test_the_editor_can_create_and_edit_but_has_no_delete_permission_anywhere(self):
        from core.crud import registry

        editor = User.objects.get(username="editor_a")
        for slug in carga.CRUDS_EVALUADOS:
            self.assertTrue(self.crud(slug).has_perm(editor, "add"), slug)
            self.assertTrue(self.crud(slug).has_perm(editor, "change"), slug)
        self.assertEqual([c.slug for c in registry.all() if c.has_perm(editor, "delete")], [])

    def test_the_editor_cannot_archive_or_delete_by_url_or_direct_request(self):
        cliente = cliente_de("editor_a")
        actividad = Activity.objects.filter(delegation=self.norte, deleted_at__isnull=True).first()
        beneficiario = Beneficiary.objects.order_by("pk").first()
        self.assertEqual(cliente.post(reverse("core:actividades_archive", args=[actividad.pk])).status_code, 403)
        self.assertEqual(cliente.post(reverse("core:beneficiarios_archive", args=[beneficiario.pk])).status_code, 403)
        self.assertEqual(cliente.post(reverse("core:beneficiarios_delete", args=[beneficiario.pk])).status_code, 403)
        actividad.refresh_from_db()
        beneficiario.refresh_from_db()
        self.assertIsNone(actividad.deleted_at)
        self.assertIsNone(beneficiario.deleted_at)
        self.assertTrue(Beneficiary.objects.filter(pk=beneficiario.pk).exists())

    def test_the_editor_creates_an_attention_in_their_own_delegation(self):
        cliente = cliente_de("editor_a")
        datos = {
            "requester": "Persona de Prueba",
            "phone": "",
            "attention_type": Item.objects.get(name="Atención Social").pk,
            "item": Item.objects.get(name="Visita Domiciliaria").pk,
            "service": "",
            "request_description": "Consulta creada por el editor A.",
            "action_taken": "",
        }
        antes = Activity.objects.count()
        respuesta = cliente.post(reverse("core:actividades_create"), datos)
        creada = Activity.objects.order_by("-pk").first()
        self.assertRedirects(respuesta, reverse("core:actividades_detail", args=[creada.pk]), fetch_redirect_response=False)
        self.assertEqual(Activity.objects.count(), antes + 1)
        self.assertEqual(creada.delegation, self.norte)
        self.assertEqual(creada.author_officer.institutional_id, "REV-N-002")
        # lo ve el lector A y no el lector B
        self.assertEqual(cliente_de("lector_a").get(reverse("core:actividades_detail", args=[creada.pk])).status_code, 200)
        self.assertEqual(cliente_de("lector_b").get(reverse("core:actividades_detail", args=[creada.pk])).status_code, 404)

    def test_the_readers_can_only_view_and_export(self):
        for nombre in ("lector_a", "lector_b"):
            cliente = cliente_de(nombre)
            actividad = Activity.objects.filter(delegation=self.ambitos["Norte" if nombre == "lector_a" else "Sur"], deleted_at__isnull=True).first()
            self.assertEqual(cliente.get(reverse("core:atencion")).status_code, 200)
            self.assertEqual(cliente.get(reverse("core:actividades_detail", args=[actividad.pk])).status_code, 200)
            self.assertEqual(cliente.get(reverse("core:beneficiarios_list")).status_code, 200)
            exportado = cliente.get(reverse("core:beneficiarios_list"), {"formato": "xlsx"})
            self.assertEqual(exportado.status_code, 200)
            self.assertIn("spreadsheetml", exportado["Content-Type"])
            self.assertEqual(cliente.get(reverse("core:actividades_create")).status_code, 403)
            self.assertEqual(cliente.post(reverse("core:actividades_create"), {"contact_name": "X"}).status_code, 403)
            self.assertEqual(cliente.get(reverse("core:actividades_update", args=[actividad.pk])).status_code, 403)
            self.assertEqual(cliente.post(reverse("core:actividades_update", args=[actividad.pk]), {"contact_name": "X"}).status_code, 403)
            self.assertEqual(cliente.post(reverse("core:actividades_archive", args=[actividad.pk])).status_code, 403)
            self.assertEqual(cliente.get(reverse("core:beneficiarios_create")).status_code, 403)
            self.assertEqual(cliente.post(reverse("core:beneficiarios_delete", args=[1])).status_code, 403)
            actividad.refresh_from_db()
            self.assertIsNone(actividad.deleted_at)

    def test_each_reader_only_sees_and_exports_the_records_of_their_own_organization(self):
        for nombre, propia, ajena in (("lector_a", self.norte, self.sur), ("lector_b", self.sur, self.norte)):
            cliente = cliente_de(nombre)
            filas = filas_exportadas(cliente.get(reverse("core:atencion"), {"formato": "xlsx"}))
            propias = Activity.objects.filter(delegation=propia, deleted_at__isnull=True)
            self.assertEqual(len(filas), propias.count(), nombre)
            codigos = {fila[0] for fila in filas}
            self.assertFalse(codigos & {str(pk) for pk in Activity.objects.filter(delegation=ajena).values_list("pk", flat=True)} - {str(pk) for pk in propias.values_list("pk", flat=True)})
            ajena_pk = Activity.objects.filter(delegation=ajena, deleted_at__isnull=True).first().pk
            self.assertEqual(cliente.get(reverse("core:actividades_detail", args=[ajena_pk])).status_code, 404, nombre)
            evidencia = Evidence.objects.filter(activity__delegation=ajena).first()
            self.assertEqual(cliente.get(reverse("core:evidencias_detail", args=[evidencia.pk])).status_code, 404, nombre)
            gestion = Followup.objects.filter(activity__delegation=ajena).first()
            self.assertEqual(cliente.get(reverse("core:gestiones_detail", args=[gestion.pk])).status_code, 404, nombre)

    def test_the_administrator_archives_and_restores_only_in_their_own_organization(self):
        cliente = cliente_de("admin_a")
        propia = Activity.objects.filter(delegation=self.norte, deleted_at__isnull=True).first()
        ajena = Activity.objects.filter(delegation=self.sur, deleted_at__isnull=True).first()
        self.assertEqual(cliente.post(reverse("core:actividades_archive", args=[propia.pk])).status_code, 302)
        propia.refresh_from_db()
        self.assertIsNotNone(propia.deleted_at)
        self.assertEqual(cliente.post(reverse("core:actividades_restore", args=[propia.pk])).status_code, 302)
        propia.refresh_from_db()
        self.assertIsNone(propia.deleted_at)
        self.assertEqual(cliente.post(reverse("core:actividades_archive", args=[ajena.pk])).status_code, 404)
        ajena.refresh_from_db()
        self.assertIsNone(ajena.deleted_at)

    def test_the_administrator_manages_users_but_only_a_superuser_deletes_them(self):
        cliente = cliente_de("admin_a")
        objetivo = User.objects.get(username="lector_a")
        self.assertEqual(cliente.get(reverse("core:usuarios_list")).status_code, 200)
        self.assertEqual(cliente.get(reverse("core:usuarios_create")).status_code, 200)
        self.assertEqual(cliente.post(reverse("core:usuarios_archive", args=[objetivo.pk])).status_code, 403)
        objetivo.refresh_from_db()
        self.assertTrue(objetivo.is_active)
        for nombre in ("editor_a", "lector_a", "lector_b"):
            self.assertEqual(cliente_de(nombre).get(reverse("core:usuarios_list")).status_code, 403, nombre)

    def test_the_two_clients_have_their_own_distinct_data_and_cannot_see_the_other(self):
        uno = User.objects.get(username="cliente1").profile.beneficiary
        dos = User.objects.get(username="cliente2").profile.beneficiary
        self.assertNotEqual(uno.pk, dos.pk)
        propias_1 = set(Activity.objects.filter(beneficiary=uno).values_list("pk", flat=True))
        propias_2 = set(Activity.objects.filter(beneficiary=dos).values_list("pk", flat=True))
        self.assertGreaterEqual(len(propias_1), carga.ATENCIONES_CLIENTE)
        self.assertGreaterEqual(len(propias_2), carga.ATENCIONES_CLIENTE)
        self.assertFalse(propias_1 & propias_2)
        self.assertEqual({a.delegation for a in Activity.objects.filter(beneficiary=uno)}, {self.norte})
        self.assertEqual({a.delegation for a in Activity.objects.filter(beneficiary=dos)}, {self.sur})
        uno_cliente, dos_cliente = cliente_de("cliente1"), cliente_de("cliente2")
        respuesta = uno_cliente.get(reverse("core:portal_activities"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.context["page"].paginator.count, len(propias_1))
        propia, ajena = min(propias_1), min(propias_2)
        self.assertEqual(uno_cliente.get(reverse("core:portal_activity", args=[propia])).status_code, 200)
        self.assertEqual(uno_cliente.get(reverse("core:portal_activity", args=[ajena])).status_code, 404)
        self.assertEqual(dos_cliente.get(reverse("core:portal_activity", args=[propia])).status_code, 404)
        self.assertEqual(uno_cliente.get(reverse("core:atencion")).status_code, 403)
        self.assertEqual(uno_cliente.get(reverse("core:beneficiarios_list")).status_code, 403)

    def test_the_accounts_can_log_in_with_the_password_given_to_the_command(self):
        for nombre in self.ESPERADAS:
            self.assertIsNotNone(authenticate(username=nombre, password=CLAVE), nombre)
            self.assertIsNone(authenticate(username=nombre, password="Hola123!"), nombre)

    def test_creating_the_accounts_leaves_an_audit_trail(self):
        eventos = AuditLog.objects.filter(event="Creación de cuenta de revisión")
        self.assertEqual(eventos.count(), 6)
        self.assertFalse(any(CLAVE in (e.new_value or "") for e in AuditLog.objects.all()))

    def test_the_command_verifies_the_permissions_of_the_accounts_and_fails_if_they_are_wrong(self):
        admin = User.objects.get(username="admin_a")
        admin.is_superuser = True
        admin.save()
        with self.assertRaisesMessage(CommandError, "admin_a no debe ser superusuario"):
            cargar()
        admin.is_superuser = False
        admin.save()
        editor = User.objects.get(username="editor_a")
        editor.user_permissions.add(*self.permisos_de_borrado())
        with self.assertRaisesMessage(CommandError, "editor_a no debe poder eliminar"):
            cargar()

    def permisos_de_borrado(self):
        from django.contrib.auth.models import Permission

        return Permission.objects.filter(codename="delete_activity")


class RoleSeedRequirementTests(TestCase):

    def test_the_command_prepares_roles_and_management_types_by_itself(self):
        from django.contrib.auth.models import Group
        from operations.models import ManagementType

        self.assertEqual(Group.objects.count(), 0)
        cargar("--password", CLAVE)
        self.assertEqual(set(Group.objects.values_list("name", flat=True)), {"Coordinación", "Jefatura", "Funcionario", "Verificador", "Consulta", "Cliente"})
        self.assertEqual(ManagementType.objects.count(), 6)

    def test_the_docs_say_that_the_deploy_does_not_load_roles_or_data(self):
        aws = (BASE / "docs" / "aws" / "DESPLIEGUE_AL2023.md").read_text(encoding="utf-8")
        readme = (BASE / "README.md").read_text(encoding="utf-8")
        for texto in (aws, readme):
            self.assertIn("seed_roles", texto)
            self.assertIn("cargar_datos_revision", texto)
        self.assertIn("actualizar.sh", aws)
        self.assertRegex(aws, r"(?s)actualizar\.sh.{0,400}no (?:ejecuta|carga|corre)")
        for archivo in sorted((BASE / "deploy").rglob("*.sh")):
            fuente = archivo.read_text(encoding="utf-8")
            self.assertNotIn("datos_prueba", fuente, archivo.name)
            self.assertNotIn("cargar_datos_revision", fuente, archivo.name)


class ReviewReadmeTests(TestCase):

    def readme(self):
        return (BASE / "README.md").read_text(encoding="utf-8")

    def test_the_readme_documents_the_six_accounts_without_passwords(self):
        texto = self.readme()
        self.assertIn("Cuentas de prueba", texto)
        for cuenta in carga.CUENTAS:
            self.assertRegex(texto, rf"\|\s*`{cuenta['username']}`\s*\|", cuenta["username"])
        for columna in ("Alias", "Rol", "Ámbito", "Responsabilidad", "Permitido", "Restringido", "Prueba"):
            self.assertIn(columna, texto)
        self.assertNotIn("Hola123!", texto)
        self.assertNotIn(CLAVE, texto)
        self.assertIn("Delegación Norte", texto)
        self.assertIn("organización A", texto)
        self.assertIn("organización B", texto)

    def test_the_readme_explains_the_aws_address_and_how_http_and_websocket_start(self):
        texto = self.readme()
        self.assertRegex(texto, r"(?i)direcci[oó]n de acceso")
        for pieza in ("Daphne", "sgr_project.asgi:application", "WebSocket", "InMemoryChannelLayer", "un solo proceso", "systemctl"):
            self.assertIn(pieza, texto)

    def test_the_readme_explains_how_the_seed_command_is_run_and_what_it_loads(self):
        texto = self.readme()
        self.assertIn("python manage.py cargar_datos_revision", texto)
        self.assertIn("SGR_REVISION_PASSWORD", texto)
        self.assertIn("Random(2026)", texto)
        self.assertIn("no duplica", texto)
        self.assertIn("core/datos_prueba.py", texto)
        self.assertIn("DIAGRAMA_MODELOS.md", texto)


class ModelDiagramTests(TestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        especificacion = importlib.util.spec_from_file_location("diagrama_modelos", BASE / "tools" / "diagrama_modelos.py")
        cls.script = importlib.util.module_from_spec(especificacion)
        especificacion.loader.exec_module(cls.script)
        cls.texto = cls.script.generar()
        cls.documento = (BASE / "docs" / "DIAGRAMA_MODELOS.md").read_text(encoding="utf-8")

    def bloque(self):
        return self.texto.split("```mermaid\n")[1].split("```")[0]

    def test_the_document_is_what_the_generator_produces_today(self):
        self.assertEqual(self.documento, self.texto)

    def test_every_model_of_the_project_is_an_entity_of_the_diagram(self):
        bloque = self.bloque()
        for modelo in modelos_de_negocio():
            self.assertIn(f"    {modelo.__name__} {{", bloque, modelo._meta.label)
        self.assertIn("    User {", bloque)
        self.assertIn("    Group {", bloque)

    def test_every_relation_between_models_is_drawn_once_with_its_multiplicity(self):
        lineas = re.findall(r'^\s+(\w+) ([|}][o|]--[o|][|{]) (\w+) : "(\w+)"$', self.bloque(), re.M)
        conjunto = self.script.modelos()
        esperadas = [
            (campo.related_model.__name__, modelo.__name__, campo.name)
            for modelo in conjunto
            for campo in modelo._meta.get_fields()
            if campo.is_relation and not campo.auto_created and (campo.concrete or campo.many_to_many)
            and campo.related_model in conjunto
        ]
        self.assertEqual(sorted((p, h, c) for p, _, h, c in lineas), sorted(esperadas))
        simbolos = {(p, h, c): s for p, s, h, c in lineas}
        self.assertEqual(simbolos[("Item", "Activity", "item")], "||--o{")
        self.assertEqual(simbolos[("Beneficiary", "Activity", "beneficiary")], "|o--o{")
        self.assertEqual(simbolos[("User", "UserProfile", "user")], "||--o|")
        self.assertEqual(simbolos[("Officer", "UserProfile", "officer")], "|o--o|")
        self.assertEqual(simbolos[("Commitment", "Activity", "commitment")], "|o--o|")
        self.assertEqual(simbolos[("Item", "Item", "parent_item")], "|o--o{")
        self.assertEqual(simbolos[("Group", "User", "groups")], "}o--o{")

    def test_every_relation_has_a_row_in_the_manual_review_table(self):
        filas = re.findall(r"^\| `(\w+)\.(\w+)` \|", self.texto, re.M)
        lineas = re.findall(r'^\s+\w+ [|}][o|]--[o|][|{] (\w+) : "(\w+)"$', self.bloque(), re.M)
        self.assertEqual(len(filas), len(lineas))
        revisadas = [clave for clave in self.script.REVISION_MANUAL]
        self.assertGreaterEqual(len(revisadas), 20)
        for clave in revisadas:
            modelo, campo = clave.split(".")
            self.assertIn((modelo, campo), filas)

    def test_the_diagram_is_well_formed_and_does_not_show_secrets(self):
        bloque = self.bloque()
        self.assertTrue(bloque.startswith("erDiagram"))
        self.assertEqual(len(re.findall(r"^    \w+ \{$", bloque, re.M)), len(re.findall(r"^    \}$", bloque, re.M)))
        self.assertNotIn("password", bloque)
        self.assertEqual(len(re.findall(r"^    \w+ \{$", bloque, re.M)), len(list(modelos_de_negocio())) + 2)

    def test_the_generator_can_check_that_the_document_is_up_to_date(self):
        entorno = dict(os.environ, PYTHONPATH=str(BASE))
        buena = subprocess.run([sys.executable, str(BASE / "tools" / "diagrama_modelos.py"), "--verificar"], capture_output=True, text=True, env=entorno, cwd=BASE)
        self.assertEqual(buena.returncode, 0, buena.stderr)
        archivo = BASE / "tools" / "_diagrama_viejo.md"
        try:
            archivo.write_text("viejo", encoding="utf-8")
            mala = subprocess.run([sys.executable, str(BASE / "tools" / "diagrama_modelos.py"), "--verificar", "--salida", str(archivo)], capture_output=True, text=True, env=entorno, cwd=BASE)
        finally:
            archivo.unlink(missing_ok=True)
        self.assertNotEqual(mala.returncode, 0)
        self.assertIn("desactualizado", mala.stderr)
