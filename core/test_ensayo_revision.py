"""Ensayo de la revisión (v37): una clase por cada uno de los diez pasos de la Evaluación Sumativa III.

Los pasos se repiten aquí sobre los datos reales de la revisión (los que deja ``cargar_datos_revision``) y con las seis
cuentas de prueba, sin navegador: cliente de pruebas de Django para HTTP y ``WebsocketCommunicator`` para el WebSocket.
El recorrido con navegador real, contra el servidor local o AWS, es ``tools/ensayo/ensayo_revision.py``.
"""
import ast
import importlib.util
import io
import json
import re
import struct
import zlib
from unittest import mock

from asgiref.sync import async_to_sync, sync_to_async
from channels.testing import WebsocketCommunicator
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, SimpleTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.rules import is_valid_rut
from core.test_carga_revision import BASE, CLAVE, RevisionTestCase, cliente_de, contrasena_escrita, filas_exportadas
from core.test_realtime import nothing_arrives, open_socket
from evidence.models import Evidence
from operations.models import Activity, Followup
from organization.models import Beneficiary, Item, Officer, Territory
from sgr_project.asgi import application

User = get_user_model()

PDF = b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"
GIF = b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"


def png(ancho, alto, ruido=False):
    """PNG válido de color liso; con ``ruido`` pesa más de 2 MiB (datos incompresibles)."""
    import os

    filas = b"".join(b"\x00" + (os.urandom(ancho * 3) if ruido else bytes([180, 40, 40]) * ancho) for _ in range(alto))

    def trozo(tipo, datos):
        cuerpo = tipo + datos
        return struct.pack(">I", len(datos)) + cuerpo + struct.pack(">I", zlib.crc32(cuerpo) & 0xFFFFFFFF)

    return (
        b"\x89PNG\r\n\x1a\n"
        + trozo(b"IHDR", struct.pack(">IIBBBBB", ancho, alto, 8, 2, 0, 0, 0))
        + trozo(b"IDAT", zlib.compress(filas, 0 if ruido else 6))
        + trozo(b"IEND", b"")
    )


def rut_con_dv(numero):
    suma, factor = 0, 2
    for digito in reversed(str(numero)):
        suma += int(digito) * factor
        factor = 2 if factor == 7 else factor + 1
    resto = 11 - suma % 11
    return f"{numero}-" + ("0" if resto == 11 else "K" if resto == 10 else str(resto))


def subida(nombre, contenido, tipo):
    return SimpleUploadedFile(nombre, contenido, content_type=tipo)


RUT_NUEVO = rut_con_dv(14999111)


class EnsayoTestCase(RevisionTestCase):
    """Datos de la revisión + ayudas para los diez pasos."""

    def cliente(self, nombre):
        return cliente_de(nombre)

    def de_norte(self, **filtros):
        return Activity.objects.filter(delegation=self.norte, deleted_at__isnull=True, **filtros)

    def de_sur(self, **filtros):
        return Activity.objects.filter(delegation=self.sur, deleted_at__isnull=True, **filtros)

    def datos_de_beneficiario(self, **cambios):
        datos = {"rut": RUT_NUEVO, "name": "Persona Ensayo Paso", "phone": "+56 9 5555 0000", "address": "Calle Falsa 123, La Serena"}
        datos.update(cambios)
        return datos

    def datos_de_edicion(self, actividad, **cambios):
        """Lo que envía el formulario de edición de una atención, tal como está guardada."""
        compromiso = actividad.commitment
        datos = {
            "date": actividad.date.isoformat(),
            "item": actividad.item_id or "",
            "service": actividad.service_id or "",
            "beneficiary": actividad.beneficiary_id or "",
            "organization": actividad.organization_id or "",
            "contact_name": actividad.contact_name,
            "phone": actividad.phone or "",
            "request_description": actividad.request_description,
            "action_taken": actividad.action_taken or "",
            "status": actividad.status,
            "due_date": compromiso.due_date.isoformat() if compromiso and compromiso.due_date else "",
            "territory": compromiso.territory_id if compromiso and compromiso.territory_id else "",
            "delegation": actividad.delegation_id,
            "author_officer": actividad.author_officer_id,
        }
        for campo in ("requires_visit", "added_to_pipeline", "requester_is_delegate"):
            if getattr(actividad, campo):
                datos[campo] = "on"
        datos.update(cambios)
        return datos

    def datos_de_atencion_nueva(self, **cambios):
        datos = {
            "requester": "Persona de Prueba",
            "phone": "",
            "attention_type": Item.objects.get(name="Atención Social").pk,
            "item": Item.objects.get(name="Visita Domiciliaria").pk,
            "service": "",
            "request_description": "Consulta del ensayo de la revisión.",
            "action_taken": "",
        }
        datos.update(cambios)
        return datos


# --- Paso 1 ----------------------------------------------------------------------------------------------------


class EnsayoPaso1AplicacionYDatosTests(EnsayoTestCase):

    def test_the_health_page_shows_service_database_version_commit_and_environment(self):
        respuesta = Client(HTTP_HOST="localhost").get("/salud/")
        self.assertEqual(respuesta.status_code, 200)
        datos = respuesta.json()
        self.assertEqual({"servicio", "base_de_datos", "cache", "version", "commit", "entorno"}, set(datos))
        self.assertEqual((datos["servicio"], datos["base_de_datos"], datos["cache"]), ("ok", "ok", "ok"))
        self.assertEqual(datos["entorno"], "desarrollo" if settings.DEBUG else "producción")
        self.assertEqual(datos["version"], (BASE / "VERSION").read_text(encoding="utf-8").strip())

    def test_the_commit_written_by_the_deploy_shows_up_in_the_health_page(self):
        def leer(nombre):
            return {"VERSION": "v37", "COMMIT": "v37-0-gabc1234"}.get(nombre)

        with mock.patch("core.health._leer", side_effect=leer):
            datos = Client(HTTP_HOST="localhost").get("/salud/").json()
        self.assertEqual((datos["version"], datos["commit"]), ("v37", "v37-0-gabc1234"))
        script = (BASE / "deploy/actualizar.sh").read_text(encoding="utf-8")
        self.assertIn("git -C \"$APP_DIR\" describe --tags --always", script)
        self.assertIn("$APP_DIR/COMMIT", script)

    def test_every_attention_has_its_officer_and_delegation_and_the_detail_shows_its_relations(self):
        self.assertFalse(Activity.objects.filter(author_officer__isnull=True).exists())
        self.assertFalse(Activity.objects.filter(delegation__isnull=True).exists())
        for ambito in (self.norte, self.sur):
            self.assertGreaterEqual(Activity.objects.filter(delegation=ambito, beneficiary__isnull=False, deleted_at__isnull=True).count(), 50)
        actividad = self.de_norte(beneficiary__isnull=False).select_related("beneficiary", "author_officer", "delegation").first()
        pagina = self.cliente("lector_a").get(reverse("core:actividades_detail", args=[actividad.pk]))
        self.assertEqual(pagina.status_code, 200)
        for texto in (actividad.beneficiary.name, actividad.author_officer.name, actividad.delegation.name):
            self.assertContains(pagina, texto)

    def test_the_evaluated_cruds_and_their_relations_exist_with_enough_records(self):
        self.assertGreaterEqual(Beneficiary.objects.filter(deleted_at__isnull=True).count(), 50)
        self.assertGreaterEqual(self.de_norte().count(), 50)
        self.assertGreaterEqual(self.de_sur().count(), 50)
        self.assertTrue(Evidence.objects.filter(activity__delegation=self.norte).exists())
        self.assertTrue(Followup.objects.filter(activity__delegation=self.sur).exists())

    def test_the_django_admin_is_closed_to_the_administrator_a(self):
        respuesta = self.cliente("admin_a").get("/admin/")
        self.assertIn(respuesta.status_code, (302, 403))
        if respuesta.status_code == 302:
            self.assertIn("login", respuesta["Location"])
        self.assertFalse(User.objects.get(username="admin_a").is_superuser)


# --- Paso 2 ----------------------------------------------------------------------------------------------------


class EnsayoPaso2CrudConModalYBorradoLogicoTests(EnsayoTestCase):

    def test_the_administrator_creates_edits_archives_and_restores_a_beneficiary_with_the_modal_protocol(self):
        admin = self.cliente("admin_a")
        nuevo = admin.post(reverse("core:beneficiarios_create") + "?modal=1", self.datos_de_beneficiario())
        self.assertEqual(nuevo["X-Modal"], "saved")
        persona = Beneficiary.objects.get(rut=RUT_NUEVO.replace(".", ""))
        editado = admin.post(reverse("core:beneficiarios_update", args=[persona.pk]) + "?modal=1", self.datos_de_beneficiario(phone="+56 9 5555 1111"))
        self.assertEqual(editado["X-Modal"], "saved")
        persona.refresh_from_db()
        self.assertEqual(persona.phone, "+56 9 5555 1111")
        listado = reverse("core:beneficiarios_list")

        def vigentes(**consulta):
            return [fila.obj.pk for fila in admin.get(listado, {"q": "Persona Ensayo", **consulta}).context["rows"]]

        self.assertEqual(vigentes(), [persona.pk])
        self.assertEqual(admin.post(reverse("core:beneficiarios_archive", args=[persona.pk])).status_code, 302)
        persona.refresh_from_db()
        self.assertIsNotNone(persona.deleted_at)
        self.assertEqual(vigentes(), [])
        self.assertEqual(vigentes(archivados="1"), [persona.pk])
        self.assertEqual(admin.post(reverse("core:beneficiarios_restore", args=[persona.pk])).status_code, 302)
        persona.refresh_from_db()
        self.assertIsNone(persona.deleted_at)

    def test_a_get_request_never_archives_or_deletes(self):
        admin = self.cliente("admin_a")
        persona = Beneficiary.objects.filter(deleted_at__isnull=True).first()
        actividad = self.de_norte().first()
        for ruta in (
            reverse("core:beneficiarios_archive", args=[persona.pk]),
            reverse("core:beneficiarios_delete", args=[persona.pk]),
            reverse("core:actividades_archive", args=[actividad.pk]),
        ):
            self.assertNotEqual(admin.get(ruta).status_code, 302, ruta)
        persona.refresh_from_db()
        actividad.refresh_from_db()
        self.assertIsNone(persona.deleted_at)
        self.assertIsNone(actividad.deleted_at)
        self.assertTrue(Beneficiary.objects.filter(pk=persona.pk).exists())

    def test_the_lists_offer_the_sweetalert_confirmation_that_posts_with_the_csrf_token(self):
        for ruta in (reverse("core:beneficiarios_list"), reverse("core:atencion")):
            pagina = self.cliente("admin_a").get(ruta)
            self.assertContains(pagina, 'data-delete-kind="archive"')
            self.assertContains(pagina, 'name="csrf-token"')
            self.assertContains(pagina, "core/js/confirm.js")
        script = (BASE / "core/static/core/js/confirm.js").read_text(encoding="utf-8")
        self.assertIn('form.method = "post"', script)
        self.assertIn("csrfmiddlewaretoken", script)
        self.assertRegex(script, r"showCancelButton|cancelButtonText")

    def test_the_editor_creates_and_edits_attentions_but_never_gets_archive_or_delete(self):
        editor = self.cliente("editor_a")
        antes = Activity.objects.count()
        respuesta = editor.post(reverse("core:actividades_create"), self.datos_de_atencion_nueva())
        creada = Activity.objects.order_by("-pk").first()
        self.assertRedirects(respuesta, reverse("core:actividades_detail", args=[creada.pk]), fetch_redirect_response=False)
        self.assertEqual((Activity.objects.count(), creada.delegation), (antes + 1, self.norte))
        editada = editor.post(reverse("core:actividades_update", args=[creada.pk]) + "?modal=1", self.datos_de_edicion(creada, action_taken="Se corrigió la acción."))
        self.assertEqual(editada["X-Modal"], "saved", editada.content.decode()[:300])
        creada.refresh_from_db()
        self.assertEqual(creada.action_taken, "Se corrigió la acción.")
        for ruta in ("core:atencion", "core:beneficiarios_list"):
            pagina = editor.get(reverse(ruta))
            self.assertTrue(pagina.context["rows"])
            self.assertFalse(any(fila.archive_url or fila.delete_url for fila in pagina.context["rows"]), ruta)

    def test_the_administrator_archives_an_attention_and_it_moves_to_the_archived_view(self):
        admin = self.cliente("admin_a")
        listado = reverse("core:atencion")
        actividad = self.de_norte().first()
        vigentes = admin.get(listado, {"q": ""}).context["page"].paginator.count
        self.assertEqual(admin.post(reverse("core:actividades_archive", args=[actividad.pk])).status_code, 302)
        actividad.refresh_from_db()
        self.assertIsNotNone(actividad.deleted_at)
        self.assertEqual(admin.get(listado, {"q": ""}).context["page"].paginator.count, vigentes - 1)
        buscada = admin.get(listado, {"q": f"ATN{actividad.pk:05d}", "archivados": "1"})
        self.assertEqual([fila.obj.pk for fila in buscada.context["rows"]], [actividad.pk])
        self.assertEqual(admin.get(listado, {"q": f"ATN{actividad.pk:05d}"}).context["page"].paginator.count, 0)
        self.assertEqual(admin.post(reverse("core:actividades_restore", args=[actividad.pk])).status_code, 302)
        actividad.refresh_from_db()
        self.assertIsNone(actividad.deleted_at)


# --- Paso 3 ----------------------------------------------------------------------------------------------------


class EnsayoPaso3DatosInvalidosYArchivosTests(EnsayoTestCase):

    def test_invalid_beneficiary_data_is_rejected_inside_the_modal_without_saving(self):
        admin = self.cliente("admin_a")
        antes = Beneficiary.objects.count()
        casos = {
            "dígito verificador": self.datos_de_beneficiario(rut="12345678-9"),
            "nombre con números": self.datos_de_beneficiario(name="Persona 123"),
            "campos vacíos": self.datos_de_beneficiario(rut="", name=""),
            "RUT repetido": self.datos_de_beneficiario(rut=Beneficiary.objects.first().rut),
        }
        for motivo, datos in casos.items():
            respuesta = admin.post(reverse("core:beneficiarios_create") + "?modal=1", datos)
            self.assertEqual(respuesta.status_code, 200, motivo)
            self.assertEqual(respuesta["X-Modal"], "form", motivo)
            self.assertContains(respuesta, "is-invalid", msg_prefix=motivo)
        self.assertEqual(Beneficiary.objects.count(), antes)

    def test_at_least_three_different_business_rules_reject_the_save(self):
        editor = self.cliente("editor_a")
        antes = Activity.objects.count()
        # 1. Una sub atención que no es del tipo de atención elegido.
        sin_hijos = Item.objects.get(name="Coordinación Territorial")
        r1 = editor.post(reverse("core:actividades_create") + "?modal=1", self.datos_de_atencion_nueva(attention_type=sin_hijos.pk))
        self.assertEqual(r1["X-Modal"], "form")
        self.assertContains(r1, "no pertenece al tipo de atención elegido")
        # 2. Un RUT con dígito verificador válido que no está registrado.
        r2 = editor.post(reverse("core:actividades_create") + "?modal=1", self.datos_de_atencion_nueva(requester="12.345.678-5"))
        self.assertEqual(r2["X-Modal"], "form")
        # 3. Un RUT repetido en Beneficiarios.
        admin = self.cliente("admin_a")
        repetido = Beneficiary.objects.first()
        r3 = admin.post(reverse("core:beneficiarios_create") + "?modal=1", self.datos_de_beneficiario(rut=repetido.rut))
        self.assertEqual(r3["X-Modal"], "form")
        # 4. Un teléfono que no es un teléfono.
        actividad = self.de_norte().first()
        r4 = editor.post(reverse("core:actividades_update", args=[actividad.pk]) + "?modal=1", self.datos_de_edicion(actividad, phone="abc"))
        self.assertEqual(r4["X-Modal"], "form")
        self.assertContains(r4, "teléfono")
        self.assertEqual(Activity.objects.count(), antes)

    def test_a_valid_png_is_saved_and_invalid_files_are_rejected_without_changing_the_photo(self):
        admin = self.cliente("admin_a")
        perfil = User.objects.get(username="admin_a").profile
        buena = admin.post(reverse("core:profile"), {"accion": "foto", "photo": subida("valida.png", png(60, 60), "image/png")})
        self.assertEqual(buena.status_code, 302)
        perfil.refresh_from_db()
        nombre = perfil.photo.name
        self.assertTrue(nombre)
        malos = [
            ("texto.png", b"esto no es una imagen", "image/png", "no es una imagen válida"),
            ("animada.png", GIF, "image/png", None),
            ("pesada.png", png(1000, 800, ruido=True), "image/png", "el máximo es 2 MB"),
            ("programa.exe", b"MZ\x90\x00 programa", "application/octet-stream", None),
        ]
        for archivo, contenido, tipo, mensaje in malos:
            respuesta = admin.post(reverse("core:profile"), {"accion": "foto", "photo": subida(archivo, contenido, tipo)})
            self.assertEqual(respuesta.status_code, 200, archivo)
            if mensaje:
                self.assertContains(respuesta, mensaje, msg_prefix=archivo)
            perfil.refresh_from_db()
            self.assertEqual(perfil.photo.name, nombre, archivo)

    def test_an_evidence_with_a_forbidden_file_is_rejected_and_nothing_is_written(self):
        editor = self.cliente("editor_a")
        actividad = self.de_norte().first()
        antes = Evidence.objects.count()
        for archivo, contenido, tipo in (
            ("informe.exe", b"MZ\x90\x00 programa", "application/octet-stream"),
            ("informe.pdf", b"esto es texto, no un PDF", "application/pdf"),
            ("pagina.html", b"<script>alert(1)</script>", "text/html"),
        ):
            respuesta = editor.post(reverse("core:evidencias_create"), {"activity": actividad.pk, "file_link": subida(archivo, contenido, tipo)})
            self.assertEqual(respuesta.status_code, 200, archivo)
            self.assertContains(respuesta, "is-invalid", msg_prefix=archivo)
        self.assertEqual(Evidence.objects.count(), antes)


# --- Paso 4 ----------------------------------------------------------------------------------------------------


class EnsayoPaso4ListadosYExcelTests(EnsayoTestCase):

    def total(self, cliente, ruta, **parametros):
        return cliente.get(reverse(ruta), parametros).context["page"].paginator.count

    def test_the_search_covers_at_least_two_fields_in_both_lists(self):
        lector = self.cliente("lector_a")
        persona = Beneficiary.objects.filter(deleted_at__isnull=True).order_by("pk").first()
        todos = self.total(lector, "core:beneficiarios_list")
        self.assertEqual(self.total(lector, "core:beneficiarios_list", q=persona.rut), 1)
        self.assertGreaterEqual(self.total(lector, "core:beneficiarios_list", q=persona.name.split()[0]), 1)
        self.assertLess(self.total(lector, "core:beneficiarios_list", q=persona.name.split()[0]), todos)
        actividad = self.de_norte().first()
        self.assertEqual(self.total(lector, "core:atencion", q=f"ATN{actividad.pk:05d}"), 1)
        por_contacto = self.total(lector, "core:atencion", q=actividad.contact_name.split()[0])
        self.assertTrue(0 < por_contacto < self.de_norte().count())

    def test_a_business_filter_narrows_the_attentions(self):
        lector = self.cliente("lector_a")
        todos = self.total(lector, "core:atencion")
        for estado in Activity.Status.values:
            cuantos = self.total(lector, "core:atencion", status=estado)
            self.assertEqual(cuantos, self.de_norte(status=estado).count(), estado)
            self.assertLess(cuantos, todos)

    def test_sorting_goes_both_ways_by_two_columns_and_the_default_order_is_creation_date_then_id_descending(self):
        lector = self.cliente("lector_a")
        for ruta, columnas in (("core:atencion", ("contact_name", "date")), ("core:beneficiarios_list", ("name", "rut"))):
            for columna in columnas:
                primeras = []
                for sentido in ("asc", "desc"):
                    pagina = lector.get(reverse(ruta), {"orden": columna, "dir": sentido, "filas": 30})
                    self.assertEqual(pagina.status_code, 200)
                    primeras.append(pagina.context["rows"][0].obj.pk)
                self.assertNotEqual(primeras[0], primeras[1], f"{ruta} {columna}")
        pagina = lector.get(reverse("core:atencion"), {"filas": 30})
        esperadas = list(self.de_norte().order_by("-created_at", "-pk").values_list("pk", flat=True)[:30])
        self.assertEqual([fila.obj.pk for fila in pagina.context["rows"]], esperadas)
        pagina = lector.get(reverse("core:beneficiarios_list"), {"filas": 30})
        esperadas = list(Beneficiary.objects.filter(deleted_at__isnull=True).order_by("-created_at", "-pk").values_list("pk", flat=True)[:30])
        self.assertEqual([fila.obj.pk for fila in pagina.context["rows"]], esperadas)

    def test_page_sizes_are_5_15_and_30_and_invalid_parameters_are_controlled(self):
        lector = self.cliente("lector_a")
        for tamano in (5, 15, 30):
            pagina = lector.get(reverse("core:atencion"), {"filas": tamano})
            self.assertEqual(len(pagina.context["rows"]), tamano)
        primera = [f.obj.pk for f in lector.get(reverse("core:atencion"), {"filas": 30, "page": 1}).context["rows"]]
        segunda = [f.obj.pk for f in lector.get(reverse("core:atencion"), {"filas": 30, "page": 2}).context["rows"]]
        self.assertTrue(segunda and not set(primera) & set(segunda))
        for ruta in ("core:atencion", "core:beneficiarios_list"):
            for consulta in ({"page": "abc"}, {"page": "99999"}, {"filas": "999"}, {"orden": "drop_table", "dir": "sideways"}, {"q": "';--", "estado": "zzz"}):
                respuesta = lector.get(reverse(ruta), consulta)
                self.assertEqual(respuesta.status_code, 200, (ruta, consulta))

    def test_the_preference_is_kept_per_module_and_restored_when_coming_back(self):
        lector = self.cliente("lector_a")
        lector.get(reverse("core:atencion"), {"q": "a", "orden": "date", "dir": "desc", "filas": 5, "page": 3})
        lector.get(reverse("core:beneficiarios_list"), {"q": "Hugo"})
        vuelta = lector.get(reverse("core:atencion"))
        self.assertEqual(vuelta.status_code, 302)
        destino = vuelta["Location"]
        for parte in ("q=a", "orden=date", "dir=desc", "page=3"):
            self.assertIn(parte, destino)
        restaurada = lector.get(destino)
        self.assertEqual((restaurada.context["page"].number, restaurada.context["page_size"]), (3, 5))
        self.assertIn("q=Hugo", lector.get(reverse("core:beneficiarios_list"))["Location"])
        self.assertEqual(lector.get(reverse("core:atencion"), {"limpiar": 1}).status_code, 302)
        self.assertEqual(lector.get(reverse("core:atencion")).status_code, 200)

    def test_changing_the_search_goes_back_to_page_one_and_a_missing_page_is_adjusted(self):
        lector = self.cliente("lector_a")
        lector.get(reverse("core:atencion"), {"q": "a", "filas": 5, "page": 3})
        guardado = lector.session["list_state:actividades"]
        self.assertEqual(guardado["page"], 3)
        nueva = lector.get(reverse("core:atencion"), {"q": "o", "filas": 5})
        self.assertEqual(nueva.context["page"].number, 1)
        ultima = lector.get(reverse("core:atencion"), {"q": "o", "filas": 5, "page": 99999})
        self.assertEqual(ultima.context["page"].number, ultima.context["page"].paginator.num_pages)

    def test_the_export_brings_the_whole_filtered_set_without_archived_or_internal_columns(self):
        lector = self.cliente("lector_a")
        archivada = self.de_norte().first()
        archivada.deleted_at = timezone.now()
        archivada.save(update_fields=["deleted_at"])
        for ruta, consulta in (("core:atencion", {"q": "a", "filas": 5}), ("core:beneficiarios_list", {"q": "a", "filas": 5})):
            total = self.total(lector, ruta, **consulta)
            self.assertGreater(total, 5)
            respuesta = lector.get(reverse(ruta), {**consulta, "formato": "xlsx"})
            self.assertEqual(respuesta.status_code, 200)
            self.assertIn("spreadsheetml", respuesta["Content-Type"])
            hoja = io.BytesIO(respuesta.content)
            from openpyxl import load_workbook

            filas = [[c.value for c in fila] for fila in load_workbook(hoja).active.iter_rows()]
            inicio = next(i for i, fila in enumerate(filas) if sum(c is not None for c in fila) >= 3)
            encabezados = [str(c or "") for c in filas[inicio]]
            datos = [fila for fila in filas[inicio + 1:] if any(c is not None for c in fila)]
            self.assertEqual(len(datos), total, ruta)
            self.assertTrue(all(encabezados), encabezados)
            self.assertFalse([h for h in encabezados if re.search(r"password|contraseñ|token|deleted|hash|_id$", h, re.I)], encabezados)
        codigos = {fila[0] for fila in filas_exportadas(lector.get(reverse("core:atencion"), {"q": "", "formato": "xlsx"}))}
        self.assertNotIn(f"ATN{archivada.pk:05d}", codigos)

    def test_an_empty_search_shows_its_own_message(self):
        lector = self.cliente("lector_a")
        vacio = lector.get(reverse("core:beneficiarios_list"), {"q": "zzzzzzzz"})
        self.assertEqual(vacio.context["page"].paginator.count, 0)
        self.assertContains(vacio, "No hay beneficiarios que coincidan con la búsqueda")


# --- Paso 5 ----------------------------------------------------------------------------------------------------


class EnsayoPaso5LectorSinPermisosTests(EnsayoTestCase):

    def escrituras(self, actividad, persona):
        return [
            ("get", reverse("core:actividades_create"), None),
            ("get", reverse("core:beneficiarios_create"), None),
            ("get", reverse("core:actividades_update", args=[actividad.pk]), None),
            ("get", reverse("core:beneficiarios_update", args=[persona.pk]), None),
            ("post", reverse("core:actividades_create"), {"requester": "X"}),
            ("post", reverse("core:beneficiarios_create"), self.datos_de_beneficiario()),
            ("post", reverse("core:actividades_update", args=[actividad.pk]), {"contact_name": "X"}),
            ("post", reverse("core:beneficiarios_update", args=[persona.pk]), self.datos_de_beneficiario()),
            ("post", reverse("core:actividades_archive", args=[actividad.pk]), {}),
            ("post", reverse("core:beneficiarios_archive", args=[persona.pk]), {}),
            ("post", reverse("core:beneficiarios_delete", args=[persona.pk]), {}),
        ]

    def test_the_reader_gets_403_on_every_write_url_and_request_and_nothing_changes(self):
        lector = self.cliente("lector_a")
        actividad = self.de_norte().first()
        persona = Beneficiary.objects.filter(deleted_at__isnull=True).first()
        antes = (Activity.objects.count(), Beneficiary.objects.count(), actividad.contact_name, persona.name)
        for metodo, ruta, datos in self.escrituras(actividad, persona):
            respuesta = getattr(lector, metodo)(ruta, datos) if datos is not None else getattr(lector, metodo)(ruta)
            self.assertEqual(respuesta.status_code, 403, f"{metodo.upper()} {ruta}")
            self.assertContains(respuesta, "403", status_code=403)
            self.assertNotContains(respuesta, "Traceback", status_code=403)
        actividad.refresh_from_db()
        persona.refresh_from_db()
        self.assertEqual((Activity.objects.count(), Beneficiary.objects.count(), actividad.contact_name, persona.name), antes)
        self.assertIsNone(actividad.deleted_at)

    def test_the_editor_cannot_archive_or_delete_even_with_a_valid_token(self):
        editor = Client(HTTP_HOST="localhost", enforce_csrf_checks=True)
        editor.force_login(User.objects.get(username="editor_a"))
        editor.get(reverse("core:atencion"))
        token = editor.cookies["csrftoken"].value
        actividad = self.de_norte().first()
        respuesta = editor.post(reverse("core:actividades_archive", args=[actividad.pk]), HTTP_X_CSRFTOKEN=token)
        self.assertEqual(respuesta.status_code, 403)
        actividad.refresh_from_db()
        self.assertIsNone(actividad.deleted_at)

    def test_the_reader_does_not_see_the_write_buttons(self):
        for ruta in ("core:atencion", "core:beneficiarios_list"):
            pagina = self.cliente("lector_a").get(reverse(ruta))
            self.assertNotContains(pagina, reverse("core:actividades_create"))
            self.assertNotContains(pagina, reverse("core:beneficiarios_create"))
            self.assertFalse(any(f.edit_url or f.archive_url or f.delete_url for f in pagina.context["rows"]), ruta)

    def test_without_a_session_the_private_views_go_to_the_login_and_writes_are_refused(self):
        anonimo = Client(HTTP_HOST="localhost")
        actividad = self.de_norte().first()
        for ruta in (reverse("core:atencion"), reverse("core:beneficiarios_list"), reverse("core:actividades_detail", args=[actividad.pk]), reverse("core:profile")):
            respuesta = anonimo.get(ruta)
            self.assertEqual(respuesta.status_code, 302, ruta)
            self.assertTrue(respuesta["Location"].startswith(reverse("core:login") + "?next="), respuesta["Location"])
        antes = Beneficiary.objects.count()
        respuesta = anonimo.post(reverse("core:beneficiarios_create"), self.datos_de_beneficiario())
        self.assertIn(respuesta.status_code, (302, 403))
        self.assertEqual(Beneficiary.objects.count(), antes)


# --- Paso 6 ----------------------------------------------------------------------------------------------------


class EnsayoPaso6AislamientoTests(EnsayoTestCase):

    def ajenos(self):
        return {
            "actividad": self.de_sur().first(),
            "evidencia": Evidence.objects.filter(activity__delegation=self.sur, deleted_at__isnull=True).first(),
            "gestion": Followup.objects.filter(activity__delegation=self.sur).first(),
        }

    def test_an_object_of_the_other_scope_answers_404_for_every_account_of_the_first(self):
        ajenos = self.ajenos()
        for nombre in ("lector_a", "editor_a", "admin_a"):
            cliente = self.cliente(nombre)
            for ruta in (
                reverse("core:actividades_detail", args=[ajenos["actividad"].pk]),
                reverse("core:evidencias_detail", args=[ajenos["evidencia"].pk]),
                reverse("core:gestiones_detail", args=[ajenos["gestion"].pk]),
                reverse("core:evidence_file", args=[ajenos["evidencia"].pk]),
            ):
                self.assertEqual(cliente.get(ruta).status_code, 404, (nombre, ruta))
        for ruta in (
            reverse("core:actividades_update", args=[ajenos["actividad"].pk]),
            reverse("core:evidencias_update", args=[ajenos["evidencia"].pk]),
            reverse("core:gestiones_update", args=[ajenos["gestion"].pk]),
        ):
            self.assertEqual(self.cliente("editor_a").get(ruta).status_code, 404, ruta)

    def test_writing_to_an_object_of_the_other_scope_answers_404_and_changes_nothing(self):
        ajenos = self.ajenos()
        actividad = ajenos["actividad"]
        nombre = actividad.contact_name
        r1 = self.cliente("editor_a").post(reverse("core:actividades_update", args=[actividad.pk]), self.datos_de_edicion(actividad, contact_name="Intruso Norte"))
        r2 = self.cliente("admin_a").post(reverse("core:actividades_archive", args=[actividad.pk]))
        r3 = self.cliente("admin_a").post(reverse("core:evidencias_archive", args=[ajenos["evidencia"].pk]))
        self.assertEqual((r1.status_code, r2.status_code, r3.status_code), (404, 404, 404))
        actividad.refresh_from_db()
        ajenos["evidencia"].refresh_from_db()
        self.assertEqual(actividad.contact_name, nombre)
        self.assertIsNone(actividad.deleted_at)
        self.assertIsNone(ajenos["evidencia"].deleted_at)

    def test_a_foreign_relation_is_rejected_without_changes(self):
        editor = self.cliente("editor_a")
        sur = self.ajenos()["actividad"]
        antes = Evidence.objects.count()
        respuesta = editor.post(reverse("core:evidencias_create"), {"activity": sur.pk, "file_link": subida("respaldo.pdf", PDF, "application/pdf")})
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "is-invalid")
        self.assertEqual(Evidence.objects.count(), antes)
        propia = self.de_norte().first()
        funcionario_sur = Officer.objects.filter(delegation=self.sur).first()
        territorio_sur = Territory.objects.filter(delegation=self.sur).first()
        hoy = timezone.localdate().isoformat()
        casos = (
            ("author_officer", {"author_officer": funcionario_sur.pk}),
            ("territory", {"territory": territorio_sur.pk, "added_to_pipeline": "on", "due_date": hoy}),
            ("delegation", {"delegation": self.sur.pk}),
        )
        for campo, cambios in casos:
            respuesta = editor.post(reverse("core:actividades_update", args=[propia.pk]) + "?modal=1", self.datos_de_edicion(propia, **cambios))
            if campo == "delegation":
                # La delegación la fija el servidor según el ámbito de la cuenta: el valor enviado se ignora.
                self.assertIn(respuesta["X-Modal"], ("form", "saved"), campo)
            else:
                self.assertEqual(respuesta["X-Modal"], "form", campo)
        propia.refresh_from_db()
        self.assertEqual(propia.delegation, self.norte)
        self.assertEqual(propia.author_officer.delegation, self.norte)

    def test_the_relation_selectors_only_offer_the_own_scope(self):
        editor = self.cliente("editor_a")
        pagina = editor.get(reverse("core:evidencias_create"))
        opciones = {int(v) for v in re.findall(r'<option value="(\d+)"', pagina.content.decode())}
        sur = set(Activity.objects.filter(delegation=self.sur).values_list("pk", flat=True))
        norte = set(Activity.objects.filter(delegation=self.norte, deleted_at__isnull=True).values_list("pk", flat=True))
        self.assertFalse(opciones & sur)
        self.assertTrue(opciones & norte)

    def test_lists_search_and_exports_only_bring_the_own_scope(self):
        codigos = {}
        for nombre in ("lector_a", "lector_b"):
            cliente = self.cliente(nombre)
            codigos[nombre] = {fila[0] for fila in filas_exportadas(cliente.get(reverse("core:atencion"), {"formato": "xlsx"}))}
        self.assertTrue(codigos["lector_a"] and codigos["lector_b"])
        self.assertFalse(codigos["lector_a"] & codigos["lector_b"])
        sur = self.ajenos()["actividad"]
        self.assertEqual(self.cliente("lector_b").get(reverse("core:atencion"), {"q": f"ATN{sur.pk:05d}"}).context["page"].paginator.count, 1)
        self.assertEqual(self.cliente("lector_a").get(reverse("core:atencion"), {"q": f"ATN{sur.pk:05d}"}).context["page"].paginator.count, 0)


# --- Paso 7 ----------------------------------------------------------------------------------------------------


class EnsayoPaso7WebSocketTests(EnsayoTestCase):
    """Atención se actualiza por /ws/live/ (cualquier dato de la delegación) y su mantenedor por /ws/crud/actividades/."""

    RUTAS = ("/ws/live/", "/ws/crud/actividades/")

    def editar(self, actividad, **cambios):
        editor = self.cliente("editor_a")
        with self.captureOnCommitCallbacks(execute=True) as llamadas:
            respuesta = editor.post(reverse("core:actividades_update", args=[actividad.pk]) + "?modal=1", self.datos_de_edicion(actividad, **cambios))
        return respuesta, llamadas

    async def abrir_todos(self, usuario):
        sockets = {}
        for ruta in self.RUTAS:
            sockets[ruta], abierto = await open_socket(usuario, ruta)
            self.assertTrue(abierto, ruta)
        return sockets

    async def cerrar_todos(self, *grupos):
        for grupo in grupos:
            for socket in grupo.values():
                await socket.disconnect()

    async def silencio(self, sockets):
        return [await nothing_arrives(socket) for socket in sockets.values()]

    def test_the_edit_of_the_editor_a_reaches_the_reader_a_but_not_the_reader_b(self):
        actividad = self.de_norte().first()
        a, b = User.objects.get(username="lector_a"), User.objects.get(username="lector_b")

        async def escenario():
            lector_a, lector_b = await self.abrir_todos(a), await self.abrir_todos(b)
            respuesta, llamadas = await sync_to_async(self.editar)(actividad, contact_name="Cambio En Vivo")
            recibido = {ruta: json.loads(await socket.receive_from(timeout=2)) for ruta, socket in lector_a.items()}
            silencio_b = await self.silencio(lector_b)
            await self.cerrar_todos(lector_a, lector_b)
            return respuesta["X-Modal"], len(llamadas), recibido, silencio_b

        resultado, llamadas, recibido, silencio_b = async_to_sync(escenario)()
        self.assertEqual(resultado, "saved")
        self.assertGreaterEqual(llamadas, 1, "el aviso se registra para después del commit")
        self.assertEqual(recibido["/ws/live/"]["type"], "live_changed")
        self.assertEqual(recibido["/ws/crud/actividades/"], {"type": "crud_changed", "slug": "actividades"})
        self.assertEqual(silencio_b, [True, True], "el lector B no recibe nada del ámbito A")

    def test_a_change_in_the_other_scope_does_not_reach_the_reader_a_but_reaches_the_reader_b(self):
        sur = self.de_sur().first()
        a, b = User.objects.get(username="lector_a"), User.objects.get(username="lector_b")

        def cambiar_en_sur():
            with self.captureOnCommitCallbacks(execute=True):
                sur.action_taken = "Cambio hecho en la Delegación Sur."
                sur.save()

        async def escenario():
            lector_a, lector_b = await self.abrir_todos(a), await self.abrir_todos(b)
            await sync_to_async(cambiar_en_sur)()
            tipo_b = json.loads(await lector_b["/ws/live/"].receive_from(timeout=2))["type"]
            silencio_a = await self.silencio(lector_a)
            await self.cerrar_todos(lector_a, lector_b)
            return tipo_b, silencio_a

        tipo_b, silencio_a = async_to_sync(escenario)()
        self.assertEqual(tipo_b, "live_changed")
        self.assertEqual(silencio_a, [True, True])

    def test_an_invalid_save_announces_nothing(self):
        actividad = self.de_norte().first()
        a = User.objects.get(username="lector_a")

        async def escenario():
            lector_a = await self.abrir_todos(a)
            respuesta, llamadas = await sync_to_async(self.editar)(actividad, phone="abc")
            silencio = await self.silencio(lector_a)
            await self.cerrar_todos(lector_a)
            return respuesta["X-Modal"], len(llamadas), silencio

        resultado, llamadas, silencio = async_to_sync(escenario)()
        self.assertEqual(resultado, "form")
        self.assertEqual(llamadas, 0)
        self.assertEqual(silencio, [True, True])

    def test_a_rolled_back_change_announces_nothing(self):
        actividad = self.de_norte().first()
        a = User.objects.get(username="lector_a")

        def deshacer():
            from django.db import transaction

            with self.captureOnCommitCallbacks(execute=True) as llamadas:
                try:
                    with transaction.atomic():
                        actividad.action_taken = "Esto se deshace."
                        actividad.save()
                        raise RuntimeError("se deshace")
                except RuntimeError:
                    pass
            return len(llamadas)

        async def escenario():
            lector_a = await self.abrir_todos(a)
            llamadas = await sync_to_async(deshacer)()
            silencio = await self.silencio(lector_a)
            await self.cerrar_todos(lector_a)
            return llamadas, silencio

        llamadas, silencio = async_to_sync(escenario)()
        self.assertEqual(llamadas, 0)
        self.assertEqual(silencio, [True, True])

    def test_anonymous_and_foreign_origin_sockets_are_refused_by_the_asgi_application(self):
        lector = self.cliente("lector_a")
        cookie = f"{settings.SESSION_COOKIE_NAME}={lector.cookies[settings.SESSION_COOKIE_NAME].value}".encode()
        propio = [(b"origin", b"http://localhost"), (b"cookie", cookie)]
        ajeno = [(b"origin", b"http://sitio-ajeno.example"), (b"cookie", cookie)]
        anonimo = [(b"origin", b"http://localhost")]

        async def abrir(cabeceras):
            comunicador = WebsocketCommunicator(application, "/ws/live/", headers=cabeceras)
            conectado, _ = await comunicador.connect()
            if conectado:
                await comunicador.disconnect()
            return conectado

        with override_settings(ALLOWED_HOSTS=["localhost", "testserver"]):
            self.assertTrue(async_to_sync(abrir)(propio))
            self.assertFalse(async_to_sync(abrir)(ajeno))
            self.assertFalse(async_to_sync(abrir)(anonimo))

    def test_the_client_never_chooses_its_group_and_the_pages_are_marked_as_live(self):
        script = (BASE / "core/static/core/js/live-updates.js").read_text(encoding="utf-8")
        self.assertNotRegex(script, r"delegation|delegaci[óo]n=")
        self.assertIn("X-Live-Refresh", script)
        self.assertRegex(script, r"onclose")
        lector = self.cliente("lector_a")
        atencion = lector.get(reverse("core:atencion"))
        self.assertContains(atencion, "data-live-results")
        self.assertContains(atencion, "data-live-state")
        beneficiarios = lector.get(reverse("core:beneficiarios_list"))
        self.assertContains(beneficiarios, 'data-live-crud="beneficiarios"')

    def test_the_background_refresh_applies_the_same_filters_and_does_not_touch_the_saved_state(self):
        lector = self.cliente("lector_a")
        consulta = {"q": "a", "orden": "date", "dir": "desc", "filas": 5}
        pagina = lector.get(reverse("core:atencion"), consulta)
        guardado = dict(lector.session["list_state:actividades"])
        refresco = lector.get(reverse("core:atencion"), {**consulta, "page": 2}, HTTP_X_LIVE_REFRESH="1")
        self.assertEqual(refresco.status_code, 200)
        self.assertEqual(refresco.context["page"].paginator.count, pagina.context["page"].paginator.count)
        self.assertEqual(refresco.context["page"].number, 2)
        self.assertEqual(dict(lector.session["list_state:actividades"]), guardado)


# --- Paso 8 ----------------------------------------------------------------------------------------------------


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class EnsayoPaso8RecuperacionCropprYClientesTests(EnsayoTestCase):

    CORREO = "lector_b@revision.sgr.example"

    def pedir_enlace(self, correo=None):
        anonimo = Client(HTTP_HOST="localhost")
        respuesta = anonimo.post(reverse("accounts:recover"), {"email": correo or self.CORREO}, follow=True)
        return anonimo, respuesta

    def enlace_del_correo(self):
        cuerpo = mail.outbox[-1].body
        return re.search(r"https?://[^\s]+/recuperar/[^\s/]+/[^\s/]+/", cuerpo).group(0)

    def test_the_request_answers_the_same_for_an_existing_and_a_missing_email_and_does_not_repeat_it(self):
        _, existente = self.pedir_enlace()
        _, inexistente = self.pedir_enlace("nadie.existe@revision.sgr.example")
        self.assertEqual(existente.redirect_chain, inexistente.redirect_chain)
        self.assertNotContains(existente, self.CORREO)
        self.assertNotContains(inexistente, "nadie.existe")
        self.assertEqual(len(mail.outbox), 1)

    def test_the_link_changes_the_password_with_the_validators_and_only_works_once(self):
        self.pedir_enlace()
        enlace = self.enlace_del_correo()
        ruta = "/" + enlace.split("/", 3)[3]
        navegador = Client(HTTP_HOST="localhost")
        abierto = navegador.get(ruta, follow=True)
        self.assertEqual(abierto.status_code, 200)
        destino = abierto.redirect_chain[-1][0]
        debil = navegador.post(destino, {"new_password1": "12345678", "new_password2": "12345678"})
        self.assertEqual(debil.status_code, 200)
        self.assertContains(debil, "demasiado común")
        nueva = "Temporal-Ensayo-2026!"
        bien = navegador.post(destino, {"new_password1": nueva, "new_password2": nueva})
        self.assertEqual(bien.status_code, 302)
        usuario = User.objects.get(username="lector_b")
        self.assertTrue(usuario.check_password(nueva))
        self.assertFalse(usuario.check_password(CLAVE))
        reusado = Client(HTTP_HOST="localhost").get(ruta, follow=True)
        self.assertEqual(reusado.status_code, 400)
        self.assertNotContains(reusado, "Traceback", status_code=400)

    def test_an_invented_link_answers_400_without_internal_errors(self):
        for ruta in ("/recuperar/MQ/abc-def/", "/recuperar/zzz/token-inventado-123/", "/recuperar/NA/set-password/"):
            respuesta = Client(HTTP_HOST="localhost", raise_request_exception=False).get(ruta, follow=True)
            self.assertEqual(respuesta.status_code, 400, ruta)
            self.assertNotContains(respuesta, "new_password1", status_code=400)
            self.assertNotContains(respuesta, "Traceback", status_code=400)

    def test_the_profile_photo_is_cropped_to_a_square_of_up_to_512_pixels_with_the_real_croppr_library(self):
        from PIL import Image

        editor = self.cliente("editor_a")
        pagina = editor.get(reverse("core:profile"))
        self.assertContains(pagina, "core/vendor/croppr/croppr.min.js")
        self.assertContains(pagina, "core/vendor/croppr/croppr.min.css")
        self.assertContains(pagina, "data-photo-crop")
        for archivo in ("croppr.min.js", "croppr.min.css"):
            ruta = BASE / "core/static/core/vendor/croppr" / archivo
            self.assertGreater(ruta.stat().st_size, 500, archivo)
        self.assertIn("Croppr", (BASE / "core/static/core/vendor/croppr/croppr.min.js").read_text(encoding="utf-8"))
        respuesta = editor.post(reverse("core:profile"), {"accion": "foto", "photo": subida("recorte.png", png(600, 400), "image/png")})
        self.assertEqual(respuesta.status_code, 302)
        perfil = User.objects.get(username="editor_a").profile
        with Image.open(perfil.photo.path) as foto:
            self.assertEqual(foto.size[0], foto.size[1])
            self.assertLessEqual(foto.size[0], 512)

    def test_each_client_sees_only_their_own_attentions_and_manipulated_data_is_ignored(self):
        uno, dos = self.cliente("cliente1"), self.cliente("cliente2")
        propias_1 = set(Activity.objects.filter(beneficiary=User.objects.get(username="cliente1").profile.beneficiary).values_list("pk", flat=True))
        propias_2 = set(Activity.objects.filter(beneficiary=User.objects.get(username="cliente2").profile.beneficiary).values_list("pk", flat=True))
        self.assertTrue(propias_1 and propias_2 and not propias_1 & propias_2)
        self.assertEqual(uno.get(reverse("core:portal_activity", args=[min(propias_2)])).status_code, 404)
        self.assertEqual(dos.get(reverse("core:portal_activity", args=[min(propias_1)])).status_code, 404)
        ficha = User.objects.get(username="cliente1").profile.beneficiary
        nombre, rut = ficha.name, ficha.rut
        uno.post(reverse("core:profile"), {"accion": "datos", "phone": "+56 9 6150 0001", "address": "Calle Falsa 123", "name": "Intruso", "rut": "11111111-1", "beneficiary": "1", "groups": "1", "is_superuser": "on"})
        ficha.refresh_from_db()
        usuario = User.objects.get(username="cliente1")
        self.assertEqual((ficha.name, ficha.rut), (nombre, rut))
        self.assertFalse(usuario.is_superuser)
        self.assertEqual(set(usuario.groups.values_list("name", flat=True)), {"Cliente"})
        self.assertEqual(uno.get(reverse("core:atencion")).status_code, 403)


# --- Paso 9 ----------------------------------------------------------------------------------------------------


class EnsayoPaso9RamasYEventoTests(SimpleTestCase):

    def test_the_event_path_described_in_the_guide_exists_in_the_code(self):
        guia = (BASE / "docs/ENSAYO_REVISION.md").read_text(encoding="utf-8")
        recorrido = {
            "core/crud.py": ("notify_crud_change(",),
            "websocket/services.py": ("def notify_crud_change", "transaction.on_commit", "def publish_crud_changed", "group_send"),
            "websocket/consumers.py": ("class CrudChangesConsumer", "def crud_event", "group_add"),
            "websocket/routing.py": ("ws/crud/<slug:slug>/",),
            "sgr_project/asgi.py": ("AllowedHostsOriginValidator", "AuthMiddlewareStack"),
            "core/static/core/js/live-updates.js": ("X-Live-Refresh", "new WebSocket"),
        }
        for archivo, textos in recorrido.items():
            codigo = (BASE / archivo).read_text(encoding="utf-8")
            self.assertIn(archivo, guia, f"la guía no nombra {archivo}")
            for texto in textos:
                self.assertIn(texto, codigo, f"{archivo} no tiene «{texto}»")

    def test_the_guide_explains_how_to_show_branches_and_pull_requests(self):
        guia = (BASE / "docs/ENSAYO_REVISION.md").read_text(encoding="utf-8")
        for texto in ("Pull Request", "feature/", "main", "/salud/", "commit"):
            self.assertIn(texto, guia)


# --- Paso 10 ---------------------------------------------------------------------------------------------------


class EnsayoPaso10NavegacionYErroresTests(EnsayoTestCase):

    def enlaces_del_menu(self, pagina):
        html = pagina.content.decode()
        menu = html.split('aria-label="Menú principal"', 1)[1].split("</nav>", 1)[0]
        return re.findall(r'<a class="side-link(?: active)?"(?: aria-current="page")? href="([^"]+)"', menu)

    def test_every_menu_link_of_each_account_opens_with_title_active_module_and_skip_link(self):
        for nombre in ("admin_a", "editor_a", "lector_a", "lector_b", "cliente1", "cliente2"):
            cliente = self.cliente(nombre)
            inicio = cliente.get(reverse("core:portal_home") if nombre.startswith("cliente") else reverse("core:dashboard"))
            enlaces = self.enlaces_del_menu(inicio)
            self.assertGreaterEqual(len(enlaces), 3, nombre)
            for ruta in dict.fromkeys(enlaces):
                pagina = cliente.get(ruta, follow=True)
                html = pagina.content.decode()
                self.assertEqual(pagina.status_code, 200, (nombre, ruta))
                self.assertRegex(html, r"<title>[^<]+· SGR</title>", (nombre, ruta))
                self.assertEqual(len(re.findall(r"<h1[ >]", html)), 1, (nombre, ruta))
                self.assertIn('class="skip-link"', html)
                self.assertIn('aria-current="page"', html, (nombre, ruta))
                activos = re.findall(r'<a class="side-link active" aria-current="page" href="([^"]+)"', html)
                self.assertTrue(activos and activos[0].split("?")[0] == ruta.split("?")[0], (nombre, ruta, activos))

    def test_the_403_and_404_pages_of_the_review_accounts_are_comprehensible(self):
        lector = Client(HTTP_HOST="localhost", raise_request_exception=False)
        lector.force_login(User.objects.get(username="lector_a"))
        prohibida = lector.get(reverse("core:beneficiarios_create"))
        inexistente = lector.get("/esta-pantalla-no-existe/")
        self.assertEqual((prohibida.status_code, inexistente.status_code), (403, 404))
        for respuesta, codigo in ((prohibida, "403"), (inexistente, "404")):
            texto = respuesta.content.decode()
            self.assertIn(codigo, texto)
            self.assertIn('href="', texto)
            for tecnico in ("Traceback", "Request Method", "SECRET_KEY", "settings.py", "SELECT "):
                self.assertNotIn(tecnico, texto)
        cliente = Client(HTTP_HOST="localhost", raise_request_exception=False)
        cliente.force_login(User.objects.get(username="cliente1"))
        self.assertEqual(cliente.get(reverse("core:atencion")).status_code, 403)

    @override_settings(DEBUG=False)
    def test_the_400_and_the_500_are_controlled_with_debug_off(self):
        anonimo = Client(HTTP_HOST="sitio-ajeno.example", raise_request_exception=False)
        mala = anonimo.get("/")
        self.assertEqual(mala.status_code, 400)
        for tecnico in ("DisallowedHost", "ALLOWED_HOSTS", "sitio-ajeno", "Traceback"):
            self.assertNotContains(mala, tecnico, status_code=400)
        cliente = Client(HTTP_HOST="localhost", raise_request_exception=False)
        cliente.force_login(User.objects.get(username="admin_a"))
        with mock.patch("core.views.pick_period", side_effect=RuntimeError("SELECT password FROM auth_user")), self.assertLogs("django.request", level="ERROR"):
            caida = cliente.get(reverse("core:dashboard"))
        self.assertEqual(caida.status_code, 500)
        for tecnico in ("RuntimeError", "SELECT ", "auth_user", "Traceback"):
            self.assertNotContains(caida, tecnico, status_code=500)


# --- La herramienta y la guía ---------------------------------------------------------------------------------


class EnsayoHerramientaYGuiaTests(SimpleTestCase):

    HERRAMIENTA = BASE / "tools/ensayo/ensayo_revision.py"
    GUIA = BASE / "docs/ENSAYO_REVISION.md"

    def cargar(self):
        especificacion = importlib.util.spec_from_file_location("ensayo_revision", self.HERRAMIENTA)
        modulo = importlib.util.module_from_spec(especificacion)
        especificacion.loader.exec_module(modulo)
        return modulo

    def test_the_tool_has_one_function_per_step_and_every_account_is_used(self):
        arbol = ast.parse(self.HERRAMIENTA.read_text(encoding="utf-8"))
        clase = next(n for n in arbol.body if isinstance(n, ast.ClassDef) and n.name == "Ensayo")
        funciones = {n.name for n in clase.body if isinstance(n, ast.FunctionDef)}
        self.assertTrue({f"paso{n}" for n in range(1, 11)} <= funciones)
        modulo = self.cargar()
        self.assertEqual(modulo.CUENTAS, ["admin_a", "editor_a", "lector_a", "lector_b", "cliente1", "cliente2"])

    def test_the_tool_reads_the_passwords_from_the_environment_and_writes_none(self):
        texto = self.HERRAMIENTA.read_text(encoding="utf-8")
        self.assertIn("SGR_REVISION_PASSWORD", texto)
        self.assertIn("SGR_PASSWORD_", texto)
        self.assertFalse([linea for linea in texto.splitlines() if contrasena_escrita(linea)])
        with mock.patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(SystemExit):
                self.cargar().clave_de("admin_a")
        with mock.patch.dict("os.environ", {"SGR_REVISION_PASSWORD": "x", "SGR_PASSWORD_LECTOR_B": "propia"}, clear=True):
            modulo = self.cargar()
            self.assertEqual(modulo.clave_de("lector_b"), "propia")
            self.assertEqual(modulo.clave_de("admin_a"), "x")

    def test_the_helpers_build_valid_ruts_and_png_files_and_read_the_excel_title_block(self):
        from openpyxl import Workbook

        modulo = self.cargar()
        for numero in (90000000, 14001003, 12345678, 76543210):
            self.assertTrue(is_valid_rut(modulo.rut_valido(numero)), numero)
        self.assertTrue(modulo.png(10, 10).startswith(b"\x89PNG"))
        self.assertGreater(len(modulo.png(1000, 800, relleno=True)), 2 * 1024 * 1024)
        dos_colores = modulo.png_dos_colores(40, 20)
        self.assertTrue(dos_colores.startswith(b"\x89PNG"))
        libro = Workbook()
        hoja = libro.active
        hoja.append(["Atención"])
        hoja.append(["Generado el hoy"])
        hoja.append([])
        hoja.append(["Identificador", "Fecha", "Contacto"])
        hoja.append(["ATN00001", "30/10/2026", "Persona Uno"])
        buffer = io.BytesIO()
        libro.save(buffer)
        titulos, encabezados, datos = modulo.Ensayo.leer_excel(buffer.getvalue())
        self.assertEqual(titulos, ["Atención", "Generado el hoy"])
        self.assertEqual(encabezados, ["Identificador", "Fecha", "Contacto"])
        self.assertEqual(len(datos), 1)

    def test_the_guide_covers_the_ten_steps_with_accounts_what_to_show_and_the_expected_result(self):
        guia = self.GUIA.read_text(encoding="utf-8")
        for numero in range(1, 11):
            self.assertRegex(guia, rf"(?m)^### Paso {numero}\b", numero)
        for texto in ("admin_a", "editor_a", "lector_a", "lector_b", "cliente1", "cliente2", "Resultado esperado", "Qué mostrar", "tools/ensayo/ensayo_revision.py", "SGR_REVISION_PASSWORD", "core.test_ensayo_revision"):
            self.assertIn(texto, guia)

    def test_the_guide_writes_no_password_and_the_readme_points_to_it(self):
        guia = self.GUIA.read_text(encoding="utf-8")
        self.assertFalse([linea for linea in guia.splitlines() if contrasena_escrita(linea)])
        readme = (BASE / "README.md").read_text(encoding="utf-8")
        self.assertIn("docs/ENSAYO_REVISION.md", readme)
        self.assertIn("tools/ensayo/ensayo_revision.py", readme)

    def test_the_tool_clean_up_leaves_no_trace_in_the_lists_and_the_guide_says_how(self):
        guia = self.GUIA.read_text(encoding="utf-8")
        self.assertIn("ENSAYO", guia)
        self.assertIn("archivad", guia)
        texto = self.HERRAMIENTA.read_text(encoding="utf-8")
        self.assertIn("def limpiar", texto)
        self.assertIn("ENSAYO", texto)
