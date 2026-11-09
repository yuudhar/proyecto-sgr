#!/usr/bin/env python3
"""Ensayo de la revisión de la Evaluación Sumativa III: recorre los diez pasos con un navegador real.

Cada cuenta usa su propio contexto de navegador (sesiones independientes), igual que en la revisión.
Sirve contra el servidor local o contra AWS; las contraseñas se leen del entorno y no se escriben en ningún archivo.

    export SGR_REVISION_PASSWORD='<la contraseña con que cargaste las cuentas>'
    python tools/ensayo/ensayo_revision.py --url http://127.0.0.1:8000

Hace cambios reales (crea y archiva registros marcados «ENSAYO») y deja el resto de los datos como estaban.
"""

import argparse
import io
import json
import os
import re
import struct
import sys
import time
import zlib
from datetime import datetime
from pathlib import Path

try:
    from playwright.sync_api import Error as ErrorNavegador
    from playwright.sync_api import TimeoutError as EsperaAgotada
    from playwright.sync_api import sync_playwright
except ImportError:  # el módulo se puede importar sin Playwright (pruebas, --help); se exige al abrir el navegador
    sync_playwright = None

    class ErrorNavegador(Exception):
        pass

    class EsperaAgotada(ErrorNavegador):
        pass

CUENTAS = ["admin_a", "editor_a", "lector_a", "lector_b", "cliente1", "cliente2"]


class Saltar(Exception):
    """El paso no se puede comprobar desde aquí (por ejemplo, correo real): queda como revisión manual."""


def clave_de(alias):
    clave = os.environ.get(f"SGR_PASSWORD_{alias.upper()}") or os.environ.get("SGR_REVISION_PASSWORD")
    if not clave:
        sys.exit(f"Falta la contraseña de {alias}: define SGR_REVISION_PASSWORD (o SGR_PASSWORD_{alias.upper()}).")
    return clave


def rut_valido(numero):
    suma, factor = 0, 2
    for digito in reversed(str(numero)):
        suma += int(digito) * factor
        factor = 2 if factor == 7 else factor + 1
    resto = 11 - suma % 11
    dv = "0" if resto == 11 else "K" if resto == 10 else str(resto)
    return f"{numero}-{dv}"


def png(ancho, alto, relleno=False):
    """PNG válido de color liso. Con relleno=True pesa más de 2 MiB (datos aleatorios incompresibles)."""
    filas = b"".join(b"\x00" + (os.urandom(ancho * 3) if relleno else bytes([180, 40, 40]) * ancho) for _ in range(alto))

    def trozo(tipo, datos):
        cuerpo = tipo + datos
        return struct.pack(">I", len(datos)) + cuerpo + struct.pack(">I", zlib.crc32(cuerpo) & 0xFFFFFFFF)

    return (
        b"\x89PNG\r\n\x1a\n"
        + trozo(b"IHDR", struct.pack(">IIBBBBB", ancho, alto, 8, 2, 0, 0, 0))
        + trozo(b"IDAT", zlib.compress(filas, 0 if relleno else 6))
        + trozo(b"IEND", b"")
    )


def png_dos_colores(ancho, alto):
    """PNG con la mitad izquierda roja y la derecha azul: sirve para saber qué zona se recortó."""
    filas = b""
    for _ in range(alto):
        filas += b"\x00" + bytes([200, 30, 30]) * (ancho // 2) + bytes([30, 30, 200]) * (ancho - ancho // 2)

    def trozo(tipo, datos):
        cuerpo = tipo + datos
        return struct.pack(">I", len(datos)) + cuerpo + struct.pack(">I", zlib.crc32(cuerpo) & 0xFFFFFFFF)

    return (
        b"\x89PNG\r\n\x1a\n"
        + trozo(b"IHDR", struct.pack(">IIBBBBB", ancho, alto, 8, 2, 0, 0, 0))
        + trozo(b"IDAT", zlib.compress(filas, 6))
        + trozo(b"IEND", b"")
    )


class Ensayo:
    def __init__(self, args):
        self.args = args
        self.base = args.url.rstrip("/")
        self.sello = time.strftime("%H%M%S")
        # Los nombres solo admiten letras: el sello de la hora se escribe con letras para que el marcador sea válido.
        self.marca = "ENSAYO " + self.sello.translate(str.maketrans("0123456789", "ABCDEFGHIJ"))
        self.resultados = []
        self.paso_actual = 0
        self.capturas = Path(args.capturas) if args.capturas else None
        if self.capturas:
            self.capturas.mkdir(parents=True, exist_ok=True)
        self.contextos = {}
        self.nav = None
        self.paginas = {}
        self.datos = {}

    # --- infraestructura -------------------------------------------------------------------------------------
    def abrir(self, navegador, alias):
        ctx = navegador.new_context(
            viewport={"width": 1366, "height": 850},
            locale="es-CL",
            accept_downloads=True,
            ignore_https_errors=self.args.sin_verificar_tls,
        )
        pg = ctx.new_page()
        pg.set_default_timeout(10000)
        self.contextos[alias], self.paginas[alias] = ctx, pg
        self.ingresar(pg, alias)
        return pg

    def ingresar(self, pg, alias):
        pg.goto(self.base + "/")
        pg.fill("#id_username", alias)
        pg.fill("#id_password", clave_de(alias))
        pg.click("button[type=submit]")
        pg.wait_for_load_state("networkidle")
        assert "/accounts/login" not in pg.url and pg.query_selector("#id_password") is None, f"{alias} no pudo ingresar"

    def foto(self, pg, nombre):
        if not self.capturas:
            return ""
        pg.wait_for_timeout(500)
        ruta = self.capturas / f"{nombre}.png"
        pg.screenshot(path=str(ruta))
        return ruta.as_posix()

    def comprobar(self, paso, descripcion, funcion):
        estado, detalle = "Aprobada", ""
        try:
            detalle = funcion() or ""
        except Saltar as e:
            estado, detalle = "Revisión manual", str(e)
        except (AssertionError, EsperaAgotada, ErrorNavegador, KeyError, ValueError, TypeError) as e:
            estado = "Fallida"
            texto = str(e).strip().splitlines()[0] if str(e).strip() else ""
            detalle = f"{type(e).__name__}: {texto[:400]}"
            if self.args.depurar:
                import traceback

                detalle += " @ " + " > ".join(f"{f.name}:{f.lineno}" for f in traceback.extract_tb(e.__traceback__)[1:])
        self.resultados.append({"paso": paso, "prueba": descripcion, "estado": estado, "detalle": detalle})
        marca = {"Aprobada": "✔", "Fallida": "✘", "Revisión manual": "–"}[estado]
        print(f"  {marca} {descripcion}" + (f" · {detalle}" if detalle else ""))

    def titulo(self, numero, texto):
        self.paso_actual = numero
        print(f"\nPaso {numero} · {texto}")

    # --- utilidades de pantalla ------------------------------------------------------------------------------
    def ir(self, pg, ruta):
        respuesta = pg.goto(self.base + ruta)
        pg.wait_for_load_state("networkidle")
        return respuesta.status if respuesta else None

    def total(self, pg):
        m = re.search(r"([\d\.]+)\s+resultado", pg.inner_text("main"))
        return int(m.group(1).replace(".", "")) if m else 0

    def contar(self, pg, ruta, texto="", extra=""):
        pg.goto(self.base + f"{ruta}?limpiar=1")
        pg.wait_for_load_state("networkidle")
        url = f"{ruta}?q={texto.replace(' ', '+')}{extra}"
        pg.goto(self.base + url)
        pg.wait_for_load_state("networkidle")
        return self.total(pg)

    def por_menu(self, pg, href):
        """Entra a un módulo desde el menú lateral, como lo haría una persona: abre el grupo si está plegado."""
        enlace = pg.locator(f"aside a[href='{href}']").first
        if not enlace.is_visible():
            for boton in pg.query_selector_all("aside button[aria-expanded=false]"):
                boton.click()
                if enlace.is_visible():
                    break
        with pg.expect_navigation():
            enlace.click()
        pg.wait_for_load_state("networkidle")

    def cerrar_swal(self, pg):
        """Cierra el aviso SweetAlert2 si hay uno abierto (una persona lo cerraría antes de seguir)."""
        if pg.query_selector(".swal2-popup"):
            boton = pg.query_selector(".swal2-confirm")
            if boton and boton.is_visible():
                boton.click()
            pg.wait_for_selector(".swal2-popup", state="detached", timeout=5000)

    def cambiar_clave(self, pg, actual, nueva):
        """Formulario «Cambiar contraseña» del perfil, con su confirmación SweetAlert2 cuando la hay."""
        self.cerrar_swal(pg)
        pg.fill("#id_old_password", actual)
        pg.fill("#id_new_password1", nueva)
        pg.fill("#id_new_password2", nueva)
        pg.click("main button:has-text('Cambiar contraseña')")
        pg.wait_for_selector(".swal2-popup", timeout=5000)
        if "¿" in pg.inner_text(".swal2-popup"):
            with pg.expect_navigation():
                pg.click(".swal2-confirm")
            pg.wait_for_load_state("networkidle")

    def swal(self, pg):
        pg.wait_for_selector(".swal2-popup", timeout=5000)
        return " ".join(pg.inner_text(".swal2-popup").split())

    def peticion(self, alias, metodo, ruta, datos=None, archivos=None):
        """Petición directa con la sesión de la cuenta (como una herramienta externa, con su cookie y su token CSRF)."""
        ctx = self.contextos[alias]
        cookies = {c["name"]: c["value"] for c in ctx.cookies()}
        cabeceras = {"Referer": self.base + "/", "X-CSRFToken": cookies.get("csrftoken", "")}
        if metodo == "POST" and archivos:
            partes = dict(datos or {})
            partes.update({campo: {"name": nombre, "mimeType": tipo, "buffer": contenido} for campo, (nombre, tipo, contenido) in archivos.items()})
            return ctx.request.post(self.base + ruta, multipart=partes, headers=cabeceras, max_redirects=0)
        if metodo == "POST":
            return ctx.request.post(self.base + ruta, form=datos or {}, headers=cabeceras, max_redirects=0)
        return ctx.request.get(self.base + ruta, max_redirects=0)

    # --- paso 1 ----------------------------------------------------------------------------------------------
    def paso1(self):
        self.titulo(1, "Aplicación, commit desplegado, conexión, datos y relaciones")
        pg = self.paginas["admin_a"]

        def salud():
            r = self.contextos["admin_a"].request.get(self.base + "/salud/")
            assert r.status == 200, f"/salud/ responde {r.status}"
            d = r.json()
            assert d.get("servicio") == "ok" and d.get("base_de_datos") == "ok", d
            assert d.get("entorno") == "producción", f"el entorno dice {d.get('entorno')!r}: DEBUG tiene que estar en False"
            self.datos["salud"] = d
            return f"versión {d.get('version')}, commit {d.get('commit')}, base {d.get('base_de_datos')}, entorno {d.get('entorno')}"

        self.comprobar(1, "/salud/ muestra servicio, base de datos, versión, commit y entorno de producción", salud)

        def sin_traza():
            r = self.contextos["admin_a"].request.get(self.base + "/esta-ruta-no-existe-ensayo/")
            cuerpo = r.text()
            assert r.status == 404, f"respondió {r.status}"
            for prohibido in ("Traceback", "Request Method", "SECRET_KEY", "Django tried these URL patterns", "settings.py"):
                assert prohibido not in cuerpo, f"la página 404 muestra «{prohibido}»"
            return "404 sin trazas ni configuración (DEBUG=False)"

        self.comprobar(1, "Una ruta inexistente responde 404 sin trazas (DEBUG=False)", sin_traza)

        def datos():
            conteo = {}
            for nombre, ruta in (("atenciones", "/atencion/"), ("beneficiarios", "/beneficiarios/"), ("gestiones", "/gestiones/"), ("evidencias", "/evidencias/")):
                conteo[nombre] = self.contar(pg, ruta)
            assert conteo["atenciones"] >= 300 and conteo["beneficiarios"] >= 50, conteo
            self.datos["conteo"] = conteo
            return ", ".join(f"{k}: {v}" for k, v in conteo.items()) + " (Norte para las atenciones)"

        self.comprobar(1, "Los listados traen datos suficientes (≥ 50 en cada CRUD evaluado)", datos)

        def relaciones():
            pg.goto(self.base + "/atencion/?limpiar=1")
            pg.wait_for_load_state("networkidle")
            enlace = pg.query_selector("tbody tr a.cell-link")
            href = enlace.get_attribute("href")
            pg.goto(self.base + href)
            pg.wait_for_load_state("networkidle")
            texto = pg.inner_text("main")
            for rotulo in ("Beneficiario", "Funcionario autor", "Delegación", "Estado"):
                assert rotulo.lower() in texto.lower(), f"el detalle no muestra «{rotulo}»"
            self.datos["detalle"] = href
            self.foto(pg, "P1_detalle_atencion")
            return f"el detalle {href} muestra beneficiario, funcionario, delegación y estado relacionados"

        self.comprobar(1, "El detalle de una atención muestra sus relaciones", relaciones)

        def no_superusuario():
            r = self.contextos["admin_a"].request.get(self.base + "/admin/", max_redirects=0)
            location = r.headers.get("location", "")
            assert r.status in (302, 403) and (r.status == 403 or "login" in location), f"/admin/ respondió {r.status}"
            pg.goto(self.base + "/admin/")
            assert "Administración de Django" not in pg.inner_text("body") or pg.query_selector("#id_password"), "admin_a entra al panel de Django"
            return "admin_a no entra al panel /admin/ (no es superusuario)"

        self.comprobar(1, "El administrador A no es superusuario", no_superusuario)

    # --- paso 2 ----------------------------------------------------------------------------------------------
    def fila(self, pg, texto):
        return pg.query_selector(f"tbody tr:has-text('{texto}')")

    def guardar_modal(self, pg, boton="Guardar"):
        with pg.expect_navigation():
            pg.click(f"#sgr-modal button[type=submit]:has-text('{boton}'):not([name=_addanother])")
        pg.wait_for_load_state("networkidle")

    def paso2(self):
        self.titulo(2, "Ambos CRUD con administrador y editor: modal, cancelar SweetAlert2 y borrado lógico")
        admin, editor = self.paginas["admin_a"], self.paginas["editor_a"]
        nombre = f"{self.marca} Beneficiaria"
        rut = rut_valido(90000000 + int(self.sello))
        self.datos["benef"] = {"nombre": nombre, "rut": rut}

        def crear_beneficiario():
            self.ir(admin, "/beneficiarios/?limpiar=1")
            admin.click("main a.btn-primary")
            admin.wait_for_selector("#sgr-modal.show")
            admin.fill("#sgr-modal #id_rut", rut)
            admin.fill("#sgr-modal #id_name", nombre)
            admin.fill("#sgr-modal #id_phone", "+56 9 5555 0000")
            self.foto(admin, "P2_modal_beneficiario")
            self.guardar_modal(admin)
            assert self.contar(admin, "/beneficiarios/", nombre) == 1, "el beneficiario no aparece en el listado"
            return "creado con el modal y visible en el listado"

        self.comprobar(2, "Beneficiarios · administrador crea con modal", crear_beneficiario)

        def editar_beneficiario():
            self.contar(admin, "/beneficiarios/", nombre)
            admin.click(f"tbody tr:has-text('{nombre}') a:has-text('Editar')")
            admin.wait_for_selector("#sgr-modal.show")
            admin.fill("#sgr-modal #id_phone", "+56 9 5555 1111")
            self.guardar_modal(admin)
            self.contar(admin, "/beneficiarios/", nombre)
            assert "5555 1111" in self.fila(admin, nombre).inner_text(), "el teléfono nuevo no se ve"
            return "editado con el modal; el listado muestra el dato nuevo"

        self.comprobar(2, "Beneficiarios · administrador edita con modal", editar_beneficiario)

        def cancelar_y_archivar():
            self.contar(admin, "/beneficiarios/", nombre)
            admin.click(f"tbody tr:has-text('{nombre}') a[data-delete-kind=archive]")
            texto = self.swal(admin)
            self.foto(admin, "P2_sweetalert_archivar")
            admin.click(".swal2-cancel")
            admin.wait_for_selector(".swal2-popup", state="detached")
            assert self.contar(admin, "/beneficiarios/", nombre) == 1, "al cancelar el registro cambió"
            self.contar(admin, "/beneficiarios/", nombre)
            admin.click(f"tbody tr:has-text('{nombre}') a[data-delete-kind=archive]")
            self.swal(admin)
            with admin.expect_navigation():
                admin.click(".swal2-confirm")
            admin.wait_for_load_state("networkidle")
            assert self.contar(admin, "/beneficiarios/", nombre) == 0, "archivado y sigue en el listado"
            assert self.contar(admin, "/beneficiarios/", nombre, "&archivados=1") == 1, "no aparece entre los archivados"
            return f"SweetAlert2: «{texto[:70]}…»; cancelar no cambió nada; confirmar lo archivó y quedó en «Archivados»"

        self.comprobar(2, "Beneficiarios · SweetAlert2 cancela sin cambios y confirma archivando (borrado lógico)", cancelar_y_archivar)

        def restaurar():
            self.contar(admin, "/beneficiarios/", nombre, "&archivados=1")
            boton = admin.query_selector(f"tbody tr:has-text('{nombre}') [data-delete-kind=restore], tbody tr:has-text('{nombre}') :text('Restaurar')")
            assert boton is not None, "la fila archivada no ofrece restaurar"
            boton.click()
            try:
                self.swal(admin)
                with admin.expect_navigation():
                    admin.click(".swal2-confirm")
            except EsperaAgotada:
                pass
            admin.wait_for_load_state("networkidle")
            assert self.contar(admin, "/beneficiarios/", nombre) == 1, "no se restauró"
            return "restaurado desde «Archivados»"

        self.comprobar(2, "Beneficiarios · restaurar un archivado", restaurar)

        def editor_beneficiarios():
            self.contar(editor, "/beneficiarios/", nombre)
            acciones = [a.inner_text().strip() for a in self.fila(editor, nombre).query_selector_all("a,button")]
            assert "Editar" in acciones, acciones
            assert not any(x in acciones for x in ("Archivar", "Eliminar")), f"el editor ve acciones de borrado: {acciones}"
            return "el editor ve Ver y Editar, y ningún botón de archivar ni eliminar"

        self.comprobar(2, "Beneficiarios · el editor edita pero no ve archivar ni eliminar", editor_beneficiarios)

        asunto = f"{self.marca} solicitud"

        def crear_atencion():
            self.ir(editor, "/atencion/?limpiar=1")
            editor.click("main a.btn-primary")
            editor.wait_for_selector("#sgr-modal.show")
            editor.fill("#sgr-modal [name=requester]", f"{self.marca} Persona")
            editor.fill("#sgr-modal [name=phone]", "+56 9 4444 0000")
            for campo in ("attention_type", "item", "service"):
                opciones = editor.eval_on_selector_all(f"#sgr-modal select[name={campo}] option", "o => o.map(x => x.value).filter(v => v)")
                if opciones:
                    editor.eval_on_selector(f"#sgr-modal select[name={campo}]", f"(s, v) => {{ s.value = v; s.dispatchEvent(new Event('change', {{bubbles: true}})); }}", opciones[0])
            editor.fill("#sgr-modal [name=request_description]", asunto)
            editor.fill("#sgr-modal [name=action_taken]", "Se orientó a la persona (prueba de ensayo).")
            self.foto(editor, "P2_modal_atencion")
            self.guardar_modal(editor, "Registrar atención")
            assert self.contar(editor, "/atencion/", f"{self.marca} Persona") == 1, "la atención no aparece"
            return "atención creada con el modal y visible en el listado"

        self.comprobar(2, "Atenciones · el editor crea con modal", crear_atencion)

        def editar_atencion():
            self.contar(editor, "/atencion/", f"{self.marca} Persona")
            editor.click(f"tbody tr:has-text('{self.marca} Persona') a:has-text('Editar')")
            editor.wait_for_selector("#sgr-modal.show")
            editor.fill("#sgr-modal [name=action_taken]", "Se corrigió la acción (ensayo).")
            with editor.expect_navigation():
                editor.click("#sgr-modal button[type=submit]:not([name=_addanother])")
            editor.wait_for_load_state("networkidle")
            editor.click(f"tbody tr:has-text('{self.marca} Persona') a:has-text('Ver')")
            editor.wait_for_load_state("networkidle")
            assert "Se corrigió la acción" in editor.inner_text("main"), "el detalle no muestra la edición"
            return "atención editada con el modal; el detalle muestra el cambio"

        self.comprobar(2, "Atenciones · el editor edita", editar_atencion)

        def editor_sin_borrado():
            self.contar(editor, "/atencion/", f"{self.marca} Persona")
            acciones = [a.inner_text().strip() for a in self.fila(editor, f"{self.marca} Persona").query_selector_all("a,button")]
            assert not any(x in acciones for x in ("Archivar", "Eliminar")), acciones
            return "el editor no ve archivar ni eliminar en Atenciones"

        self.comprobar(2, "Atenciones · el editor no ve archivar ni eliminar", editor_sin_borrado)

        def admin_archiva_atencion():
            self.contar(admin, "/atencion/", f"{self.marca} Persona")
            admin.click(f"tbody tr:has-text('{self.marca} Persona') a[data-delete]")
            self.swal(admin)
            admin.click(".swal2-cancel")
            admin.wait_for_selector(".swal2-popup", state="detached")
            assert self.contar(admin, "/atencion/", f"{self.marca} Persona") == 1, "cancelar cambió algo"
            self.contar(admin, "/atencion/", f"{self.marca} Persona")
            admin.click(f"tbody tr:has-text('{self.marca} Persona') a[data-delete]")
            self.swal(admin)
            with admin.expect_navigation():
                admin.click(".swal2-confirm")
            admin.wait_for_load_state("networkidle")
            assert self.contar(admin, "/atencion/", f"{self.marca} Persona") == 0, "sigue en el listado"
            assert self.contar(admin, "/atencion/", f"{self.marca} Persona", "&archivados=1") == 1, "no está entre los archivados"
            return "cancelar no cambia nada; confirmar archiva (borrado lógico) y aparece entre los archivados"

        self.comprobar(2, "Atenciones · el administrador archiva con SweetAlert2 (cancelar y confirmar)", admin_archiva_atencion)

    # --- paso 3 ----------------------------------------------------------------------------------------------
    def paso3(self):
        self.titulo(3, "Datos inválidos y archivos no permitidos: mensajes y ausencia de escrituras")
        admin, editor = self.paginas["admin_a"], self.paginas["editor_a"]
        malo = f"{self.marca} Invalido"

        def modal_con_rut_malo():
            self.ir(admin, "/beneficiarios/?limpiar=1")
            admin.click("main a.btn-primary")
            admin.wait_for_selector("#sgr-modal.show")
            admin.fill("#sgr-modal #id_rut", "12345678-9")
            admin.fill("#sgr-modal #id_name", malo)
            admin.click("#sgr-modal button[type=submit]:not([name=_addanother])")
            texto = self.swal(admin)
            self.foto(admin, "P3_modal_rut_invalido")
            assert "RUT" in texto, texto
            admin.click(".swal2-confirm")
            admin.wait_for_selector(".swal2-popup", state="detached")
            assert admin.query_selector("#sgr-modal.show") is not None, "el modal se cerró: el error no se puede corregir dentro del modal"
            admin.fill("#sgr-modal #id_rut", rut_valido(91000000 + int(self.sello)))
            return f"aviso «{texto[:60]}…» y el modal sigue abierto para corregir"

        self.comprobar(3, "Beneficiarios · RUT inválido: aviso claro y el modal permite corregir", modal_con_rut_malo)
        self.ir(admin, "/beneficiarios/?limpiar=1")

        def servidor_rechaza():
            malos = [
                ({"rut": "12345678-9", "name": malo}, "RUT con dígito verificador incorrecto"),
                ({"rut": rut_valido(92000000 + int(self.sello)), "name": f"{malo} 123"}, "nombre con números"),
                ({"rut": "", "name": ""}, "campos obligatorios vacíos"),
                ({"rut": "14001003-0", "name": malo}, "RUT que ya existe"),
            ]
            detalles = []
            for datos, motivo in malos:
                r = self.peticion("admin_a", "POST", "/beneficiarios/nuevo/", datos)
                assert r.status == 200, f"{motivo}: respondió {r.status} (se esperaba el formulario con errores)"
                detalles.append(motivo)
            assert self.contar(admin, "/beneficiarios/", malo) == 0, "alguna petición inválida escribió un registro"
            return "el servidor rechazó: " + "; ".join(detalles) + ". No se escribió ningún registro"

        self.comprobar(3, "Beneficiarios · el servidor rechaza datos inválidos sin guardar (sin pasar por el navegador)", servidor_rechaza)

        def foto_ajena():
            # Control positivo: un PNG válido sí se guarda; así «la foto no cambió» después significa algo.
            ok = self.peticion("admin_a", "POST", "/perfil/", {"accion": "foto"}, {"photo": ("valida.png", "image/png", png(60, 60))})
            assert ok.status == 302, f"un PNG válido respondió {ok.status}"
            self.ir(admin, "/perfil/")
            fuente = admin.get_attribute("main img[src*='perfil/foto']", "src")
            assert fuente, "la foto válida no se ve en el perfil"
            antes = self.contextos["admin_a"].request.get(self.base + fuente).body()
            assert antes[:4] == b"\x89PNG" or antes[:2] == b"\xff\xd8", "la foto guardada no es una imagen"
            casos = [
                ("texto.png", "image/png", b"esto no es una imagen, es texto", "no es una imagen válida"),
                ("animada.png", "image/png", b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;", None),
                ("pesada.png", "image/png", png(1000, 800, relleno=True), "el máximo es 2 MB"),
                ("programa.exe", "application/octet-stream", b"MZ\x90\x00\x03\x00\x00\x00 programa falso", None),
            ]
            rechazos = []
            for nombre, tipo, contenido, mensaje in casos:
                r = self.peticion("admin_a", "POST", "/perfil/", {"accion": "foto"}, {"photo": (nombre, tipo, contenido)})
                assert r.status == 200, f"{nombre}: respondió {r.status} (se esperaba el formulario con el error)"
                if mensaje:
                    assert mensaje in r.text(), f"{nombre}: el mensaje no dice «{mensaje}»"
                despues = self.contextos["admin_a"].request.get(self.base + fuente.split("?")[0]).body()
                assert despues == antes, f"{nombre}: la foto de perfil cambió"
                rechazos.append(nombre)
            self.peticion("admin_a", "POST", "/perfil/", {"accion": "quitar_foto"})
            return "la foto guardada no cambió con: " + ", ".join(rechazos) + " (texto con extensión .png, GIF, PNG de más de 2 MiB y un ejecutable); se quitó la foto de prueba"

        self.comprobar(3, "Perfil · un archivo que no es JPEG/PNG válido de hasta 2 MiB no se guarda", foto_ajena)

        def evidencia_ajena():
            href = self.datos.get("detalle", "/actividades/98/")
            id_atencion = re.search(r"/actividades/(\d+)/", href).group(1)
            antes = self.contar(editor, "/evidencias/")
            casos = [
                ("informe.exe", "application/octet-stream", b"MZ\x90\x00 programa falso"),
                ("informe.pdf", "application/pdf", b"esto es texto, no un PDF"),
                ("script.html", "text/html", b"<script>alert(1)</script>"),
            ]
            for nombre, tipo, contenido in casos:
                r = self.peticion("editor_a", "POST", "/evidencias/nuevo/", {"activity": id_atencion}, {"file_link": (nombre, tipo, contenido)})
                assert r.status == 200, f"{nombre}: respondió {r.status}; se esperaba el formulario con el error"
                assert "no se acepta" in r.text() or "no es un" in r.text().lower() or "no es válido" in r.text().lower(), f"{nombre}: el mensaje no explica el rechazo"
            despues = self.contar(editor, "/evidencias/")
            assert antes == despues, f"se escribieron evidencias ({antes} → {despues})"
            return f"{len(casos)} archivos no permitidos rechazados; las evidencias siguen en {despues}"

        self.comprobar(3, "Evidencias · un archivo no permitido se rechaza y no se escribe nada", evidencia_ajena)

    # --- paso 4 ----------------------------------------------------------------------------------------------
    def parametros(self, pg):
        from urllib.parse import parse_qs, urlparse

        return {k: v[0] for k, v in parse_qs(urlparse(pg.url).query).items()}

    def filas_visibles(self, pg):
        return [tr.inner_text().split("\t")[0].strip() for tr in pg.query_selector_all("tbody tr")]

    @staticmethod
    def leer_excel(contenido):
        """Devuelve (títulos, encabezados, filas de datos): el libro trae un bloque de título antes de la tabla."""
        from openpyxl import load_workbook

        hoja = load_workbook(io.BytesIO(contenido)).active
        filas = [[c.value for c in fila] for fila in hoja.iter_rows()]
        indice = next(i for i, fila in enumerate(filas) if sum(c is not None for c in fila) >= 3)
        encabezados = [str(c) if c is not None else "" for c in filas[indice]]
        datos = [fila for fila in filas[indice + 1 :] if any(c is not None for c in fila)]
        titulos = [str(f[0]) for f in filas[:indice] if f[0]]
        return titulos, encabezados, datos

    def exportar(self, pg):
        """Descarga el Excel con el botón del listado, tal como lo haría una persona."""
        with pg.expect_download() as descarga:
            pg.click("main button[name=formato][value=xlsx]")
        destino = Path(self.args.descargas or "/tmp") / f"ensayo_{self.sello}_{self.paso_actual}.xlsx"
        destino.parent.mkdir(parents=True, exist_ok=True)
        descarga.value.save_as(str(destino))
        contenido = destino.read_bytes()
        destino.unlink(missing_ok=True)
        return self.leer_excel(contenido)

    def paso4(self):
        self.titulo(4, "Buscar, filtrar, ordenar, paginar, mantener la preferencia y exportar")
        lector = self.paginas["lector_a"]
        pg = lector

        def busqueda_dos_campos():
            todos = self.contar(pg, "/beneficiarios/")
            por_nombre = self.contar(pg, "/beneficiarios/", "Hugo")
            por_rut = self.contar(pg, "/beneficiarios/", "14006783")
            assert 0 < por_nombre < todos, "la búsqueda por nombre no filtra"
            assert 0 < por_rut < todos, "la búsqueda por RUT no filtra"
            atenciones = self.contar(pg, "/atencion/")
            por_contacto = self.contar(pg, "/atencion/", "Raúl")
            por_id = self.contar(pg, "/atencion/", "ATN00098")
            assert 0 < por_contacto < atenciones and por_id == 1, (por_contacto, por_id)
            return f"Beneficiarios por nombre ({por_nombre}) y por RUT ({por_rut}); Atenciones por contacto ({por_contacto}) e identificador ({por_id})"

        self.comprobar(4, "Búsqueda por al menos dos campos en ambos listados", busqueda_dos_campos)

        def filtro_negocio():
            todos = self.contar(pg, "/atencion/")
            pg.goto(self.base + "/atencion/?limpiar=1")
            pg.wait_for_load_state("networkidle")
            pg.eval_on_selector("#filtro-status", "s => { s.value = 'in_progress'; s.dispatchEvent(new Event('change', {bubbles: true})); }")
            pg.click("main form[method=get] button:has-text('Buscar')")
            pg.wait_for_load_state("networkidle")
            en_proceso = self.total(pg)
            assert 0 < en_proceso < todos, (en_proceso, todos)
            estados = {tr.query_selector_all("td")[8].inner_text().strip() for tr in pg.query_selector_all("tbody tr")}
            assert estados == {"En proceso"}, f"el filtro deja pasar otros estados: {estados}"
            return f"filtro «Estado = En proceso»: {en_proceso} de {todos}, todas las filas con ese estado"

        self.comprobar(4, "Atenciones · filtro de negocio (estado)", filtro_negocio)

        def orden():
            detalle = []
            for ruta, columnas in (("/atencion/", ("contact_name", "date")), ("/beneficiarios/", ("name", "rut"))):
                for columna in columnas:
                    primeras = {}
                    for sentido in ("asc", "desc"):
                        pg.goto(self.base + f"{ruta}?limpiar=1")
                        pg.goto(self.base + f"{ruta}?orden={columna}&dir={sentido}&filas=30")
                        pg.wait_for_load_state("networkidle")
                        filas = self.filas_visibles(pg)
                        assert len(filas) >= 5, f"{ruta} {columna}: pocas filas"
                        primeras[sentido] = filas[0]
                    assert primeras["asc"] != primeras["desc"], f"{ruta} ordenar por {columna} no cambia el orden"
                    detalle.append(f"{ruta.strip('/')}:{columna}")
            return "orden ascendente y descendente distinto en " + ", ".join(detalle)

        self.comprobar(4, "Orden ascendente y descendente por al menos dos columnas en ambos listados", orden)

        def paginacion():
            pg.goto(self.base + "/atencion/?limpiar=1")
            pg.wait_for_load_state("networkidle")
            tam = {}
            for n in (5, 15, 30):
                with pg.expect_navigation():
                    pg.click(f"button[name=filas][value='{n}']")
                pg.wait_for_load_state("networkidle")
                tam[n] = len(pg.query_selector_all("tbody tr"))
            assert tam == {5: 5, 15: 15, 30: 30}, tam
            primera = self.filas_visibles(pg)
            pg.click(".pagination a:has-text('2')")
            pg.wait_for_load_state("networkidle")
            segunda = self.filas_visibles(pg)
            assert segunda and not set(primera) & set(segunda), "la página 2 repite filas de la 1"
            self.foto(pg, "P4_listado_pagina_2")
            return "tamaños 5, 15 y 30 (30 filas) y página 2 distinta de la 1"

        self.comprobar(4, "Paginación con tamaños 5, 15 y 30", paginacion)

        def mantener():
            pg.goto(self.base + "/atencion/?limpiar=1")
            pg.goto(self.base + "/atencion/?q=a&orden=date&dir=desc&filas=5")
            pg.wait_for_load_state("networkidle")
            pg.goto(self.base + "/atencion/?q=a&orden=date&dir=desc&filas=5&page=3")
            pg.wait_for_load_state("networkidle")
            antes, filas_antes = self.parametros(pg), self.filas_visibles(pg)
            antes.pop("filas", None)
            pg.click("tbody tr a:has-text('Ver')")
            pg.wait_for_load_state("networkidle")
            self.por_menu(pg, "/beneficiarios/")
            self.por_menu(pg, "/atencion/")
            despues, filas_despues = self.parametros(pg), self.filas_visibles(pg)
            despues.pop("filas", None)
            assert pg.query_selector("button[name=filas][value='5'].btn-primary") is not None, "el tamaño de página guardado no se restauró"
            assert despues == antes, f"no se restauró el estado: {antes} → {despues}"
            assert filas_despues == filas_antes, "las filas no son las mismas"
            return f"tras abrir un detalle y pasar por otro módulo, volvió a {despues}"

        self.comprobar(4, "La preferencia (búsqueda, orden, tamaño y página) se conserva al volver", mantener)

        def pagina_uno():
            pg.goto(self.base + "/atencion/?q=a&filas=5&page=3")
            pg.wait_for_load_state("networkidle")
            pg.fill("main input[name=q]", "o")
            pg.click("main form[method=get] button:has-text('Buscar')")
            pg.wait_for_load_state("networkidle")
            assert self.parametros(pg).get("page", "1") == "1", self.parametros(pg)
            return "al cambiar la búsqueda vuelve a la página 1"

        self.comprobar(4, "Cambiar la búsqueda vuelve a la página 1", pagina_uno)

        def invalidos():
            for ruta in ("/atencion/", "/beneficiarios/"):
                for consulta in ("page=abc", "page=99999", "filas=999", "orden=drop_table&dir=sideways", "q=%27%3B--&estado=zzz"):
                    r = self.contextos["lector_a"].request.get(self.base + f"{ruta}?{consulta}")
                    assert r.status == 200, f"{ruta}?{consulta} respondió {r.status}"
                    texto = r.text()
                    for prohibido in ("Traceback", "ValueError", "OperationalError"):
                        assert prohibido not in texto, f"{ruta}?{consulta} muestra {prohibido}"
            pg.goto(self.base + "/beneficiarios/?q=zzzzzzzz")
            assert "No hay beneficiarios que coincidan" in pg.inner_text("main"), "falta el mensaje de búsqueda sin resultados"
            return "parámetros inválidos ignorados (200, sin errores internos) y «sin resultados» con mensaje propio"

        self.comprobar(4, "Parámetros inválidos y resultados vacíos controlados", invalidos)

        def exportar_filtrado():
            detalle = []
            for ruta, consulta, nombre in (("/atencion/", "?q=Raúl&filas=5", "Atenciones"), ("/beneficiarios/", "?q=Hugo&filas=5", "Beneficiarios")):
                pg.goto(self.base + ruta + "?limpiar=1")
                pg.goto(self.base + ruta + consulta)
                pg.wait_for_load_state("networkidle")
                esperado = self.total(pg)
                assert esperado > 5, f"{nombre}: el filtro no pasa de una página"
                titulos, encabezados, datos = self.exportar(pg)
                assert len(datos) == esperado, f"{nombre}: el Excel trae {len(datos)} filas y el listado dice {esperado}"
                prohibidos = [h for h in encabezados if re.search(r"password|contraseñ|token|deleted|hash|_id$", h, re.I)]
                assert not prohibidos, f"{nombre}: columnas sensibles o internas {prohibidos}"
                assert all(h for h in encabezados), f"{nombre}: hay encabezados vacíos"
                detalle.append(f"{nombre}: {esperado} filas (todo el filtrado, no solo 5), encabezados {encabezados[:4]}…")
            return "; ".join(detalle)

        self.comprobar(4, "Exportar a Excel el conjunto filtrado completo, con encabezados legibles y sin campos internos", exportar_filtrado)

        def exportar_sin_archivados():
            pg.goto(self.base + "/atencion/?limpiar=1")
            pg.goto(self.base + f"/atencion/?q={self.marca.replace(' ', '+')}")
            pg.wait_for_load_state("networkidle")
            r = self.contextos["lector_a"].request.get(self.base + f"/atencion/?q={self.marca.replace(' ', '+')}&formato=xlsx")
            assert r.status == 200, f"la exportación respondió {r.status}"
            _, _, datos = self.leer_excel(r.body())
            assert not datos, f"el Excel trae {len(datos)} atenciones archivadas del ensayo"
            return "el Excel no incluye la atención archivada del paso 2"

        self.comprobar(4, "La exportación excluye los registros archivados", exportar_sin_archivados)

    # --- utilidades de los pasos 5 a 7 -----------------------------------------------------------------------
    def ids_de(self, alias, ruta, patron, cuantos=1):
        pg = self.paginas[alias]
        self.ir(pg, ruta + "?limpiar=1")
        encontrados = []
        for a in pg.query_selector_all("tbody tr a.cell-link"):
            m = re.fullmatch(patron, a.get_attribute("href") or "")
            if m and m.group(1) not in encontrados:
                encontrados.append(m.group(1))
        assert encontrados, f"{alias} no ve filas en {ruta}"
        return encontrados[:cuantos]

    def pagina_de_error(self, alias, ruta, codigo):
        pg = self.paginas[alias]
        respuesta = pg.goto(self.base + ruta)
        pg.wait_for_load_state("networkidle")
        assert respuesta.status == codigo, f"{ruta} respondió {respuesta.status} y se esperaba {codigo}"
        texto = pg.inner_text("body")
        for prohibido in ("Traceback", "Request Method", "SECRET_KEY", "settings.py", "SELECT "):
            assert prohibido not in texto, f"la página {codigo} muestra «{prohibido}»"
        assert pg.query_selector("a[href='/dashboard/'], a[href='/portal/'], a[href='/']"), f"la página {codigo} no ofrece cómo volver"
        return texto

    def registrar_atencion(self, pg, requester):
        self.ir(pg, "/atencion/")
        pg.click("main a.btn-primary")
        pg.wait_for_selector("#sgr-modal.show")
        pg.fill("#sgr-modal [name=requester]", requester)
        pg.fill("#sgr-modal [name=phone]", "+56 9 4444 0000")
        for campo in ("attention_type", "item", "service"):
            opciones = pg.eval_on_selector_all(f"#sgr-modal select[name={campo}] option", "o => o.map(x => x.value).filter(v => v)")
            if opciones:
                pg.eval_on_selector(f"#sgr-modal select[name={campo}]", "(s, v) => { s.value = v; s.dispatchEvent(new Event('change', {bubbles: true})); }", opciones[0])
        pg.fill("#sgr-modal [name=request_description]", "Consulta de prueba del ensayo.")
        pg.fill("#sgr-modal [name=action_taken]", "Se orientó a la persona (ensayo).")
        with pg.expect_navigation():
            pg.click("#sgr-modal button[type=submit]:not([name=_addanother])")
        pg.wait_for_load_state("networkidle")

    # --- paso 5 ----------------------------------------------------------------------------------------------
    def paso5(self):
        self.titulo(5, "Lector: intentar crear o eliminar por URL o petición directa")
        lector = self.paginas["lector_a"]
        id_atencion = self.ids_de("lector_a", "/atencion/", r"/actividades/(\d+)/")[0]
        id_benef = self.ids_de("lector_a", "/beneficiarios/", r"/beneficiarios/(\d+)/")[0]
        antes = {"atenciones": self.contar(lector, "/atencion/"), "beneficiarios": self.contar(lector, "/beneficiarios/")}
        nombre = f"{self.marca} Lector"

        def por_url():
            detalle = []
            for ruta in ("/actividades/nuevo/", "/beneficiarios/nuevo/", f"/actividades/{id_atencion}/editar/", f"/beneficiarios/{id_benef}/editar/"):
                texto = self.pagina_de_error("lector_a", ruta, 403)
                detalle.append(ruta)
            self.foto(lector, "P5_403_lector")
            assert "permiso" in texto.lower() or "no puedes" in texto.lower() or "acceso" in texto.lower(), "la página 403 no explica el motivo"
            return "403 con la página del portal (sin trazas) en: " + ", ".join(detalle)

        self.comprobar(5, "Escribir la URL de crear o editar responde 403 con una página comprensible", por_url)

        def por_peticion():
            peticiones = [
                ("/actividades/nuevo/", {"requester": nombre, "phone": "+56 9 1111 1111"}),
                ("/beneficiarios/nuevo/", {"rut": rut_valido(93000000 + int(self.sello)), "name": nombre}),
                (f"/actividades/{id_atencion}/editar/", {"requester": nombre}),
                (f"/beneficiarios/{id_benef}/editar/", {"name": nombre, "rut": "1-9"}),
                (f"/actividades/{id_atencion}/archivar/", {}),
                (f"/beneficiarios/{id_benef}/archivar/", {}),
                (f"/beneficiarios/{id_benef}/eliminar/", {}),
            ]
            for ruta, datos in peticiones:
                r = self.peticion("lector_a", "POST", ruta, datos)
                assert r.status == 403, f"POST {ruta} respondió {r.status} y se esperaba 403"
            despues = {"atenciones": self.contar(lector, "/atencion/"), "beneficiarios": self.contar(lector, "/beneficiarios/")}
            assert despues == antes, f"cambió la base: {antes} → {despues}"
            assert self.contar(lector, "/atencion/", nombre) == 0 and self.contar(lector, "/beneficiarios/", nombre) == 0
            return f"{len(peticiones)} peticiones POST directas (con sesión y token CSRF) respondieron 403 y los conteos no cambiaron ({despues})"

        self.comprobar(5, "Peticiones POST directas de crear, editar, archivar y eliminar responden 403 sin cambios", por_peticion)

        def sin_botones():
            self.ir(lector, "/atencion/?limpiar=1")
            botones = [x.inner_text().strip() for x in lector.query_selector_all("main a.btn-primary, tbody a.act")]
            malos = [b for b in botones if re.search(r"Registrar|Nueva|Editar|Eliminar|Archivar", b)]
            assert not malos, f"el lector ve botones de escritura: {malos}"
            return "el lector no ve botones de crear, editar, archivar ni eliminar"

        self.comprobar(5, "El lector no ve botones de escritura", sin_botones)

        def editor_sin_borrar():
            antes_editor = self.contar(self.paginas["editor_a"], "/atencion/")
            r1 = self.peticion("editor_a", "POST", f"/actividades/{id_atencion}/archivar/", {})
            r2 = self.peticion("editor_a", "POST", f"/beneficiarios/{id_benef}/archivar/", {})
            r3 = self.peticion("editor_a", "POST", f"/beneficiarios/{id_benef}/eliminar/", {})
            assert (r1.status, r2.status, r3.status) == (403, 403, 403), (r1.status, r2.status, r3.status)
            assert self.contar(self.paginas["editor_a"], "/atencion/") == antes_editor
            return "el editor tampoco puede archivar ni eliminar: 403 y sin cambios"

        self.comprobar(5, "El editor no puede archivar ni eliminar por petición directa", editor_sin_borrar)

        def sin_sesion():
            ctx = self.nav.new_context(ignore_https_errors=self.args.sin_verificar_tls)
            try:
                for ruta in ("/atencion/", "/beneficiarios/", f"/actividades/{id_atencion}/", "/perfil/"):
                    r = ctx.request.get(self.base + ruta, max_redirects=0)
                    assert r.status in (302, 301) and "login" in r.headers.get("location", "").lower() or r.status in (302, 301), f"{ruta} sin sesión respondió {r.status}"
                    assert "/dashboard" not in r.headers.get("location", ""), ruta
                r = ctx.request.post(self.base + "/beneficiarios/nuevo/", form={"rut": "1-9", "name": "x"}, max_redirects=0)
                assert r.status in (302, 403), f"POST sin sesión respondió {r.status}"
            finally:
                ctx.close()
            return "sin sesión, las pantallas privadas llevan al ingreso y los POST no se aceptan"

        self.comprobar(5, "Sin iniciar sesión, las vistas privadas redirigen al ingreso", sin_sesion)

    # --- paso 6 ----------------------------------------------------------------------------------------------
    PDF_MINIMO = b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"

    def paso6(self):
        self.titulo(6, "Objeto y relación de otro ámbito: aislamiento")
        sur_atencion = self.ids_de("lector_b", "/atencion/", r"/actividades/(\d+)/")[0]
        sur_evidencia = self.ids_de("lector_b", "/evidencias/", r"/evidencias/(\d+)/")[0]
        sur_gestion = self.ids_de("lector_b", "/gestiones/", r"/gestiones/(\d+)/")[0]
        norte_atencion = self.ids_de("lector_a", "/atencion/", r"/actividades/(\d+)/")[0]
        editor, lector_a, lector_b = self.paginas["editor_a"], self.paginas["lector_a"], self.paginas["lector_b"]
        self.datos["sur"] = {"atencion": sur_atencion, "evidencia": sur_evidencia, "gestion": sur_gestion}

        def objeto_ajeno():
            detalle = []
            for alias in ("lector_a", "editor_a", "admin_a"):
                for ruta in (f"/actividades/{sur_atencion}/", f"/evidencias/{sur_evidencia}/", f"/gestiones/{sur_gestion}/"):
                    self.pagina_de_error(alias, ruta, 404)
            self.foto(self.paginas["lector_a"], "P6_404_ambito_ajeno")
            for ruta in (f"/actividades/{sur_atencion}/editar/", f"/evidencias/{sur_evidencia}/editar/", f"/gestiones/{sur_gestion}/editar/"):
                self.pagina_de_error("editor_a", ruta, 404)
                detalle.append(ruta)
            r = self.contextos["lector_a"].request.get(self.base + f"/evidencias/{sur_evidencia}/archivo/", max_redirects=0)
            assert r.status == 404, f"el archivo de una evidencia de Sur respondió {r.status}"
            return "detalle y edición de una atención, evidencia y gestión de Sur responden 404 desde Norte (lector, editor y administrador); el archivo de la evidencia también"

        self.comprobar(6, "Abrir por id un objeto del ámbito B desde el A responde 404", objeto_ajeno)

        def escritura_ajena():
            antes = self.contar(self.paginas["lector_b"], "/atencion/")
            r1 = self.peticion("editor_a", "POST", f"/actividades/{sur_atencion}/editar/", {"requester": f"{self.marca} Intruso"})
            r2 = self.peticion("admin_a", "POST", f"/actividades/{sur_atencion}/archivar/", {})
            r3 = self.peticion("admin_a", "POST", f"/gestiones/{sur_gestion}/archivar/", {})
            r4 = self.peticion("admin_a", "POST", f"/evidencias/{sur_evidencia}/archivar/", {})
            assert (r1.status, r2.status, r3.status, r4.status) == (404, 404, 404, 404), (r1.status, r2.status, r3.status, r4.status)
            despues = self.contar(self.paginas["lector_b"], "/atencion/")
            assert antes == despues, f"cambió el listado de Sur: {antes} → {despues}"
            assert self.contar(self.paginas["lector_b"], "/atencion/", f"{self.marca} Intruso") == 0, "se escribió el nombre ajeno"
            return "editar y archivar objetos de Sur desde Norte responde 404 y Sur queda igual"

        self.comprobar(6, "Editar o archivar por petición directa un objeto del ámbito B responde 404 sin cambios", escritura_ajena)

        def relacion_ajena():
            antes_n = self.contar(editor, "/evidencias/")
            antes_s = self.contar(lector_b, "/evidencias/")
            r = self.peticion("editor_a", "POST", "/evidencias/nuevo/", {"activity": sur_atencion}, {"file_link": ("respaldo.pdf", "application/pdf", self.PDF_MINIMO)})
            assert r.status in (200, 404), f"asignar una atención de Sur respondió {r.status}"
            assert r.status != 200 or "opción válida" in r.text() or "no existe" in r.text().lower() or "no es una" in r.text().lower(), "el formulario no rechazó la relación ajena con un mensaje"
            g = self.peticion("editor_a", "POST", "/gestiones/nuevo/", {"activity": sur_atencion})
            assert g.status in (200, 404), f"una gestión sobre una atención de Sur respondió {g.status}"
            assert self.contar(editor, "/evidencias/") == antes_n and self.contar(lector_b, "/evidencias/") == antes_s, "se escribió una evidencia"
            return "asignar una atención de Sur a una evidencia o gestión de Norte se rechaza y ninguna tabla cambia"

        self.comprobar(6, "Asignar una relación del ámbito B desde el A se rechaza sin cambios", relacion_ajena)

        def formulario_manipulado():
            """Edita una atención de Norte y fuerza en el formulario un funcionario, un territorio y una delegación que no se ofrecen."""
            nombre_edit = f"{self.marca} Manipulada"
            self.registrar_atencion(editor, nombre_edit)
            self.contar(editor, "/atencion/", nombre_edit)
            editor.click(f"tbody tr:has-text('{nombre_edit}') a:has-text('Editar')")
            editor.wait_for_selector("#sgr-modal.show")
            forzados = {}
            for campo in ("author_officer", "territory", "delegation"):
                ofrecidos = editor.eval_on_selector_all(f"#sgr-modal select[name={campo}] option", "o => o.map(x => x.value)")
                ajeno = next((str(n) for n in range(1, 400) if str(n) not in ofrecidos), None)
                forzados[campo] = ajeno
                editor.eval_on_selector(
                    f"#sgr-modal select[name={campo}]",
                    "(s, v) => { const o = document.createElement('option'); o.value = v; o.text = 'ajena'; s.appendChild(o); s.value = v; }",
                    ajeno,
                )
            editor.click("#sgr-modal button[type=submit]:not([name=_addanother])")
            editor.wait_for_timeout(1500)
            editor.wait_for_selector("#sgr-modal.show")
            texto = editor.inner_text("#sgr-modal") + " " + (editor.inner_text(".swal2-popup") if editor.query_selector(".swal2-popup") else "")
            assert "opción válida" in texto or "no pertenece" in texto.lower() or "ámbito" in texto.lower() or "delegación" in texto.lower(), f"el modal no explicó el rechazo: {texto[:200]}"
            self.foto(editor, "P6_relacion_ajena_rechazada")
            if editor.query_selector(".swal2-popup"):
                editor.click(".swal2-confirm")
            editor.click("#sgr-modal [data-bs-dismiss=modal], #sgr-modal a:has-text('Cancelar'), #sgr-modal button:has-text('Cancelar')")
            self.ir(editor, "/atencion/?limpiar=1")
            return f"con el formulario manipulado (funcionario {forzados['author_officer']}, territorio {forzados['territory']}, delegación {forzados['delegation']}, fuera de las opciones de Norte) el servidor rechazó el guardado y el modal explicó el error"

        self.comprobar(6, "Forzar en el formulario un funcionario, territorio o delegación ajenos se rechaza", formulario_manipulado)

        def selectores():
            self.ir(editor, "/evidencias/nuevo/")
            valores = editor.eval_on_selector_all("select[name=activity] option", "o => o.map(x => x.value)")
            assert valores, "el selector de atenciones está vacío"
            assert sur_atencion not in valores, "el selector de Norte ofrece una atención de Sur"
            assert norte_atencion in valores or len(valores) > 1
            return f"el selector de atenciones de Norte ofrece {len(valores) - 1} opciones y ninguna de Sur"

        self.comprobar(6, "Los selectores de relaciones solo ofrecen opciones del ámbito propio", selectores)

        def tablas_y_excel():
            ident = {}
            for alias in ("lector_a", "lector_b"):
                r = self.contextos[alias].request.get(self.base + "/atencion/?q=&formato=xlsx")
                assert r.status == 200, r.status
                titulos, _, datos = self.leer_excel(r.body())
                ident[alias] = {fila[0] for fila in datos}
                ambito = next((t for t in titulos if t.startswith("Delegación")), "")
                ident[alias + "_ambito"] = ambito
            assert ident["lector_a"] and ident["lector_b"], "un Excel salió vacío"
            assert not ident["lector_a"] & ident["lector_b"], "los Excel de A y B comparten atenciones"
            assert "Norte" in ident["lector_a_ambito"] and "Sur" in ident["lector_b_ambito"], (ident["lector_a_ambito"], ident["lector_b_ambito"])
            return f"Excel de A ({len(ident['lector_a'])} atenciones, Norte) y de B ({len(ident['lector_b'])}, Sur) sin ninguna en común"

        self.comprobar(6, "Listados y exportación solo traen el ámbito propio", tablas_y_excel)

        def busqueda_no_filtra():
            sur = self.paginas["lector_b"]
            self.ir(sur, f"/actividades/{sur_atencion}/")
            ident = re.search(r"Identificador\s+(\S+)", sur.inner_text("main"))
            assert ident, "no se pudo leer el identificador de la atención de Sur"
            codigo = ident.group(1)
            assert self.contar(sur, "/atencion/", codigo) == 1, f"Sur no encuentra su propia atención {codigo}"
            assert self.contar(lector_a, "/atencion/", codigo) == 0, f"la búsqueda de Norte encuentra {codigo}, que es de Sur"
            return f"buscar desde Norte el identificador {codigo}, de una atención de Sur, no devuelve resultados (Sur sí la encuentra)"

        self.comprobar(6, "La búsqueda no devuelve datos del otro ámbito", busqueda_no_filtra)

    # --- paso 7 ----------------------------------------------------------------------------------------------
    def apreton_ws(self, ruta, cookie="", origen=None):
        """Intento de abrir un WebSocket a mano (sin navegador): devuelve el código HTTP de la respuesta al «Upgrade»."""
        import base64
        import socket
        import ssl
        from urllib.parse import urlparse

        url = urlparse(self.base)
        puerto = url.port or (443 if url.scheme == "https" else 80)
        conexion = socket.create_connection((url.hostname, puerto), timeout=10)
        if url.scheme == "https":
            conexion = ssl.create_default_context().wrap_socket(conexion, server_hostname=url.hostname)
        cabeceras = [
            f"GET {ruta} HTTP/1.1",
            f"Host: {url.netloc}",
            "Upgrade: websocket",
            "Connection: Upgrade",
            f"Sec-WebSocket-Key: {base64.b64encode(os.urandom(16)).decode()}",
            "Sec-WebSocket-Version: 13",
            f"Origin: {origen or self.base}",
        ]
        if cookie:
            cabeceras.append(f"Cookie: {cookie}")
        conexion.sendall(("\r\n".join(cabeceras) + "\r\n\r\n").encode())
        respuesta = conexion.recv(4096).decode("latin-1")
        conexion.close()
        return int(respuesta.split(" ")[1])

    def paso7(self):
        self.titulo(7, "Editar con el editor A y observar al lector A sin F5; el lector B no recibe nada")
        editor, lector_a, lector_b = self.paginas["editor_a"], self.paginas["lector_a"], self.paginas["lector_b"]
        recibidos = {"lector_a": [], "lector_b": []}

        def vigilar(alias, pagina):
            def al_abrir(ws):
                if "/ws/" in ws.url:
                    ws.on("framereceived", lambda carga: recibidos[alias].append(str(carga)[:200]))

            pagina.on("websocket", al_abrir)

        vigilar("lector_a", lector_a)
        vigilar("lector_b", lector_b)
        persona = f"{self.marca} Vivo"
        self.ir(lector_a, "/atencion/?limpiar=1")
        self.ir(lector_a, f"/atencion/?q={persona.replace(' ', '+')}")
        self.ir(lector_b, "/atencion/?limpiar=1")
        lector_a.evaluate("window.__sin_recarga = 'intacta'")
        lector_b.evaluate("window.__sin_recarga = 'intacta'")
        lector_a.wait_for_selector(".chip-ok", timeout=10000)
        lector_b.wait_for_selector(".chip-ok", timeout=10000)
        lector_a.wait_for_timeout(1500)
        base_b = len(recibidos["lector_b"])

        def conectado():
            texto_a = lector_a.inner_text(".chip-ok")
            texto_b = lector_b.inner_text(".chip-ok")
            assert "vivo" in texto_a.lower() and "vivo" in texto_b.lower(), (texto_a, texto_b)
            return "los dos lectores muestran «En vivo» (WebSocket conectado)"

        self.comprobar(7, "Los lectores abren la tabla con la conexión en vivo", conectado)

        def aparece_sin_f5():
            self.registrar_atencion(editor, persona)
            lector_a.wait_for_selector(f"tbody tr:has-text('{persona}')", timeout=15000)
            assert lector_a.evaluate("window.__sin_recarga") == "intacta", "la página del lector se recargó entera"
            self.foto(lector_a, "P7_lector_ve_el_cambio")
            return "el lector A vio aparecer la atención nueva sin F5 y sin recargar la página"

        self.comprobar(7, "Crear con el editor: la tabla del lector A cambia sin F5", aparece_sin_f5)

        def edicion_en_vivo():
            self.contar(editor, "/atencion/", persona)
            editor.click(f"tbody tr:has-text('{persona}') a:has-text('Editar')")
            editor.wait_for_selector("#sgr-modal.show")
            editor.fill("#sgr-modal [name=contact_name]", f"{persona} Editada")
            with editor.expect_navigation():
                editor.click("#sgr-modal button[type=submit]:not([name=_addanother])")
            editor.wait_for_load_state("networkidle")
            lector_a.wait_for_function("t => document.querySelector('tbody').innerText.includes(t)", arg="Editada", timeout=15000)
            assert lector_a.evaluate("window.__sin_recarga") == "intacta", "la página del lector se recargó entera"
            return "el nombre editado por el editor A apareció en la tabla del lector A sin F5"

        self.comprobar(7, "Editar con el editor: la tabla del lector A refleja el dato nuevo", edicion_en_vivo)

        def deja_de_cumplir_el_filtro():
            self.contar(editor, "/atencion/", persona)
            editor.click(f"tbody tr:has-text('{persona}') a:has-text('Editar')")
            editor.wait_for_selector("#sgr-modal.show")
            editor.fill("#sgr-modal [name=contact_name]", f"{self.marca} Otra")
            with editor.expect_navigation():
                editor.click("#sgr-modal button[type=submit]:not([name=_addanother])")
            editor.wait_for_load_state("networkidle")
            lector_a.wait_for_function("t => !document.querySelector('tbody') || !document.querySelector('tbody').innerText.includes(t)", arg=persona, timeout=15000)
            assert lector_a.evaluate("window.__sin_recarga") == "intacta"
            return "al dejar de coincidir con la búsqueda del lector A, la fila desapareció de su tabla sin F5"

        self.comprobar(7, "Si el registro deja de cumplir el filtro, deja de mostrarse", deja_de_cumplir_el_filtro)

        def guardado_invalido():
            # Se espera a que lleguen los avisos pendientes del guardado anterior (puede emitir más de uno) antes de medir.
            previo = -1
            while previo != len(recibidos["lector_a"]):
                previo = len(recibidos["lector_a"])
                lector_a.wait_for_timeout(2500)
            antes = len(recibidos["lector_a"])
            self.contar(editor, "/atencion/", f"{self.marca} Otra")
            editor.click(f"tbody tr:has-text('{self.marca} Otra') a:has-text('Editar')")
            editor.wait_for_selector("#sgr-modal.show")
            editor.fill("#sgr-modal [name=phone]", "abc")
            editor.click("#sgr-modal button[type=submit]:not([name=_addanother])")
            editor.wait_for_selector(".swal2-popup", timeout=5000)
            assert "teléfono" in editor.inner_text(".swal2-popup").lower(), "no apareció el error del teléfono"
            editor.click(".swal2-confirm")
            editor.wait_for_timeout(2500)
            assert len(recibidos["lector_a"]) == antes, f"un guardado inválido avisó un cambio al lector: {recibidos['lector_a'][antes:]}"
            return "un guardado inválido no emitió ningún evento al lector"

        self.comprobar(7, "Un guardado inválido no anuncia un cambio exitoso", guardado_invalido)

        def lector_b_nada():
            assert len(recibidos["lector_b"]) == base_b, f"el lector B recibió {len(recibidos['lector_b']) - base_b} mensajes del ámbito A"
            assert persona not in lector_b.inner_text("main") and f"{self.marca} Otra" not in lector_b.inner_text("main")
            assert lector_b.evaluate("window.__sin_recarga") == "intacta"
            return f"el lector B tiene el WebSocket abierto y no recibió ningún mensaje durante los cambios de Norte (A recibió {len(recibidos['lector_a'])})"

        self.comprobar(7, "El lector B no recibe datos ni eventos del ámbito A", lector_b_nada)

        def rechaza_anonimos_y_origenes():
            anonimo = self.apreton_ws("/ws/crud/actividades/")
            assert anonimo in (403, 401), f"un WebSocket sin sesión respondió {anonimo} (se esperaba rechazo)"
            cookies = "; ".join(f"{c['name']}={c['value']}" for c in self.contextos["lector_a"].cookies())
            propio = self.apreton_ws("/ws/crud/actividades/", cookie=cookies)
            ajeno = self.apreton_ws("/ws/crud/actividades/", cookie=cookies, origen="http://sitio-ajeno.example")
            assert propio == 101, f"con sesión y origen propio respondió {propio}"
            assert ajeno in (403, 401), f"con un origen ajeno respondió {ajeno} (se esperaba rechazo)"
            return f"sin sesión: {anonimo}; con sesión y origen propio: {propio}; con origen ajeno: {ajeno}"

        self.comprobar(7, "El servidor rechaza WebSocket anónimos y de orígenes no permitidos", rechaza_anonimos_y_origenes)

    # --- paso 8 ----------------------------------------------------------------------------------------------
    TEMPORAL = "Temporal-Ensayo-2026!"

    def contexto_anonimo(self):
        ctx = self.nav.new_context(viewport={"width": 1366, "height": 850}, locale="es-CL", ignore_https_errors=self.args.sin_verificar_tls)
        pg = ctx.new_page()
        pg.set_default_timeout(10000)
        return ctx, pg

    def enlace_del_correo(self, correo):
        carpeta = Path(self.args.bandeja)
        archivos = sorted(carpeta.glob("*"), key=lambda a: a.stat().st_mtime)
        assert archivos, f"la bandeja {carpeta} no tiene correos"
        texto = archivos[-1].read_text(encoding="utf-8", errors="replace")
        trozo = texto[texto.rindex(f"To: {correo}") :] if f"To: {correo}" in texto else ""
        assert trozo, f"no hay un correo para {correo} en la bandeja"
        enlace = re.search(r"https?://[^\s\"'<>]+/recuperar/[^\s/]+/[^\s/]+/", trozo.replace("=\n", ""))
        assert enlace, "el correo no trae el enlace de recuperación"
        from urllib.parse import urlparse

        return self.base + urlparse(enlace.group(0)).path

    def paso8(self):
        self.titulo(8, "Recuperar contraseña, recorte con Croppr y portal con dos clientes")
        alias = "lector_b"
        correo = f"{alias}@revision.sgr.example"
        original = clave_de(alias)
        estado = {}

        def solicitud_generica():
            ctx, pg = self.contexto_anonimo()
            textos = []
            try:
                for texto_correo in (correo, "nadie.existe.ensayo@revision.sgr.example"):
                    pg.goto(self.base + "/recuperar/")
                    pg.fill("#id_email", texto_correo)
                    with pg.expect_navigation():
                        pg.click("main button[type=submit]")
                    pg.wait_for_load_state("networkidle")
                    assert "/recuperar/enviado" in pg.url, pg.url
                    textos.append(pg.inner_text("main"))
                    if texto_correo == correo:
                        self.foto(pg, "P8_recuperar_enviado")
                assert textos[0] == textos[1], "la respuesta cambia según el correo exista o no"
                assert correo not in textos[0], "la pantalla repite el correo"
            finally:
                ctx.close()
            return "con un correo registrado y con uno inexistente la respuesta es la misma, y no repite el correo"

        self.comprobar(8, "Recuperación · la solicitud responde igual exista o no el correo", solicitud_generica)

        def cambio_con_enlace():
            if not self.args.bandeja:
                raise Saltar("con correo real, abre el mensaje en la bandeja de la cuenta, usa el enlace y comprueba a mano: clave nueva válida, clave vieja rechazada, enlace usado rechazado")
            enlace = self.enlace_del_correo(correo)
            estado["enlace"] = enlace
            ctx, pg = self.contexto_anonimo()
            try:
                pg.goto(enlace)
                pg.wait_for_load_state("networkidle")
                assert pg.query_selector("#id_new_password1"), "el enlace no muestra el formulario de contraseña nueva"
                pg.fill("#id_new_password1", "12345678")
                pg.fill("#id_new_password2", "12345678")
                pg.click("main form[method=post] button[type=submit]", timeout=3000) if not pg.query_selector(".swal2-popup") else None
                pg.wait_for_timeout(800)
                avisado_en_pantalla = pg.query_selector(".swal2-popup") is not None
                self.foto(pg, "P8_recuperar_clave_debil")
                if avisado_en_pantalla:
                    pg.click(".swal2-confirm")
                    pg.wait_for_selector(".swal2-popup", state="detached")
                # El navegador ya avisó; se envía igual saltándose ese control para comprobar que el servidor también la rechaza.
                with pg.expect_navigation():
                    pg.evaluate("HTMLFormElement.prototype.submit.call(document.querySelector('main form[method=post]'))")
                pg.wait_for_load_state("networkidle")
                assert pg.query_selector("#id_new_password1") is not None and "ingresa" not in pg.url, "el servidor aceptó una contraseña débil"
                self.cerrar_swal(pg)
                pg.fill("#id_new_password1", self.TEMPORAL)
                pg.fill("#id_new_password2", self.TEMPORAL)
                pg.click("main form[method=post] button[type=submit]")
                self.swal(pg)
                with pg.expect_navigation():
                    pg.click(".swal2-confirm")
                pg.wait_for_load_state("networkidle")
                assert pg.query_selector("#id_username"), f"después de cambiar la clave no volvió al ingreso ({pg.url})"
            finally:
                ctx.close()
            return "el enlace del correo pide una contraseña nueva, rechaza una débil con los validadores de Django y al cambiarla vuelve al ingreso"

        self.comprobar(8, "Recuperación · el enlace del correo cambia la contraseña con los validadores de Django", cambio_con_enlace)

        def clave_vieja_y_nueva():
            if "enlace" not in estado:
                raise Saltar("depende del paso anterior (correo real): comprueba a mano que la clave vieja ya no entra y la nueva sí")
            ctx, pg = self.contexto_anonimo()
            try:
                pg.goto(self.base + "/")
                pg.fill("#id_username", alias)
                pg.fill("#id_password", original)
                pg.click("button[type=submit]")
                pg.wait_for_load_state("networkidle")
                assert pg.query_selector("#id_password") is not None, "la clave anterior sigue entrando"
                self.cerrar_swal(pg)
                pg.fill("#id_username", alias)
                pg.fill("#id_password", self.TEMPORAL)
                pg.click("button[type=submit]")
                pg.wait_for_load_state("networkidle")
                assert pg.query_selector("#id_password") is None, "la clave nueva no entra"
                estado["sesion"] = True
                # Se vuelve a la clave original por el perfil: pide la clave actual y rechaza una equivocada.
                self.ir(pg, "/perfil/")
                self.cambiar_clave(pg, "esta-no-es-la-clave", original)
                texto = pg.inner_text("main")
                assert "no es correcta" in texto, "no explicó que la clave actual es incorrecta"
                self.cerrar_swal(pg)
                self.cambiar_clave(pg, self.TEMPORAL, original)
                pg.wait_for_load_state("networkidle")
                assert "no es correcta" not in pg.inner_text("main"), "no se pudo volver a la clave original"
            finally:
                ctx.close()
            return "la clave anterior ya no entra y la nueva sí; el perfil rechazó una clave actual equivocada y devolvió la cuenta a su clave original"

        self.comprobar(8, "Recuperación · la clave anterior deja de funcionar y el perfil exige la clave actual", clave_vieja_y_nueva)

        def enlace_usado():
            if "enlace" not in estado:
                raise Saltar("depende del paso con correo real: comprueba a mano que el mismo enlace, abierto otra vez, se rechaza")
            ctx, pg = self.contexto_anonimo()
            try:
                respuestas = []
                for url in (estado["enlace"], estado["enlace"].rsplit("/", 2)[0] + "/token-inventado-123/", self.base + "/recuperar/MQ/abc-def/"):
                    r = pg.goto(url)
                    pg.wait_for_load_state("networkidle")
                    cuerpo = pg.inner_text("body")
                    assert r.status == 400, f"{url[-30:]} respondió {r.status}"
                    assert pg.query_selector("#id_new_password1") is None, "un enlace inválido muestra el formulario"
                    for prohibido in ("Traceback", "Exception", "SECRET_KEY"):
                        assert prohibido not in cuerpo
                    respuestas.append(r.status)
            finally:
                ctx.close()
            return "el enlace ya usado y dos enlaces inventados responden 400 con un aviso comprensible, sin errores internos"

        self.comprobar(8, "Recuperación · un enlace usado o inválido se rechaza sin errores internos", enlace_usado)

        def croppr():
            pg = self.paginas["editor_a"]
            self.ir(pg, "/perfil/")
            assert pg.evaluate("typeof Croppr") == "function", "la librería Croppr no está cargada"
            pg.set_input_files("#id_photo", {"name": "foto.png", "mimeType": "image/png", "buffer": png_dos_colores(600, 400)})
            pg.wait_for_selector("[data-crop-panel]:not([hidden])", timeout=10000)
            pg.wait_for_selector(".croppr-container", timeout=10000)
            region = pg.query_selector(".croppr-region")
            caja = region.bounding_box()
            pg.mouse.move(caja["x"] + caja["width"] / 2, caja["y"] + caja["height"] / 2)
            pg.mouse.down()
            pg.mouse.move(caja["x"] + caja["width"] / 2 + 400, caja["y"] + caja["height"] / 2, steps=8)
            pg.mouse.up()
            self.foto(pg, "P8_croppr_recorte")
            with pg.expect_navigation():
                pg.click("[data-crop-panel] button:has-text('Guardar foto')")
            pg.wait_for_load_state("networkidle")
            fuente = pg.get_attribute("main img[src*='perfil/foto']", "src")
            assert fuente, "después de guardar no se ve la foto"
            imagen = self.contextos["editor_a"].request.get(self.base + fuente).body()
            try:
                from PIL import Image

                with Image.open(io.BytesIO(imagen)) as foto:
                    ancho, alto = foto.size
                    assert ancho == alto and ancho <= 512, f"la foto guardada mide {ancho}×{alto}: no es un cuadrado de hasta 512 px"
                    rojo, _, azul = foto.convert("RGB").getpixel((ancho // 2, alto // 2))
                    assert azul > rojo, "la foto guardada no es la zona que se eligió en el recorte"
                detalle = f"{ancho}×{alto} px y con la zona que se arrastró en el recorte"
            except ImportError:
                detalle = "se guardó (sin Pillow no se midió el tamaño)"
            self.peticion("editor_a", "POST", "/perfil/", {"accion": "quitar_foto"})
            return f"Croppr cargado: se eligió una zona arrastrando el cuadro y el servidor guardó un cuadrado de {detalle}; se quitó la foto de prueba"

        self.comprobar(8, "Croppr · se recorta, se previsualiza y se guarda la zona elegida", croppr)

        def dos_clientes():
            c1, c2 = self.paginas["cliente1"], self.paginas["cliente2"]
            datos = {}
            for alias_c, pg in (("cliente1", c1), ("cliente2", c2)):
                self.ir(pg, "/portal/atenciones/")
                ids = [a.get_attribute("href") for a in pg.query_selector_all("tbody a.cell-link, tbody tr a")]
                datos[alias_c] = {"total": self.total_texto(pg), "ids": list(dict.fromkeys(i for i in ids if re.fullmatch(r"/portal/atenciones/\d+/", i or "")))}
                assert datos[alias_c]["ids"], f"{alias_c} no ve atenciones"
            assert datos["cliente1"]["total"] and datos["cliente2"]["total"], datos
            assert not set(datos["cliente1"]["ids"]) & set(datos["cliente2"]["ids"]), "los clientes comparten atenciones"
            self.foto(c1, "P8_portal_cliente1")
            ajena = datos["cliente2"]["ids"][0]
            self.pagina_de_error("cliente1", ajena, 404)
            self.pagina_de_error("cliente2", datos["cliente1"]["ids"][0], 404)
            for ruta in ("/atencion/", "/beneficiarios/", "/evidencias/", "/usuarios/"):
                r = self.contextos["cliente1"].request.get(self.base + ruta, max_redirects=0)
                assert r.status in (403, 404), f"el cliente abre {ruta} (respondió {r.status})"
            return f"cliente1 ve {datos['cliente1']['total']} atenciones y cliente2 {datos['cliente2']['total']}, sin ninguna en común; abrir la del otro responde 404 y los módulos de gestión responden 403"

        self.comprobar(8, "Portal · cada cliente ve solo lo suyo y se rechaza lo ajeno", dos_clientes)

        def cliente_datos_ajenos():
            c1 = self.paginas["cliente1"]
            self.ir(c1, "/perfil/")
            antes = c1.inner_text("main")
            r = self.peticion("cliente1", "POST", "/perfil/", {"accion": "datos", "first_name": "Intruso", "last_name": "Ajeno", "email": "cliente1@revision.sgr.example", "phone": "+56 9 6150 0001", "address": "Calle falsa 123", "beneficiary": "1", "rut": "11111111-1", "groups": "1", "is_superuser": "on"})
            self.ir(c1, "/perfil/")
            despues = c1.inner_text("main")
            self.ir(c1, "/portal/")
            portal = c1.inner_text("main")
            assert "11111111-1" not in portal, "el RUT enviado a la fuerza aparece en el portal"
            assert "Marta Villarroel Cáceres" in portal, "el nombre oficial de la ficha cambió"
            assert "16500001-3" in portal, "el RUT de la ficha cambió"
            for ruta in ("/atencion/", "/usuarios/"):
                assert self.contextos["cliente1"].request.get(self.base + ruta, max_redirects=0).status in (403, 404), f"tras manipular el POST el cliente abre {ruta}"
            return "enviar campos de más (RUT, beneficiario, grupos, superusuario) no cambia la ficha ni da acceso a otros módulos"

        self.comprobar(8, "Portal · un cliente no puede cambiar su ficha ni su rol manipulando campos", cliente_datos_ajenos)

    @staticmethod
    def total_texto(pg):
        m = re.search(r"(\d[\d\.]*)\s+atenciones?", pg.inner_text("main"))
        return int(m.group(1).replace(".", "")) if m else 0

    # --- paso 9 ----------------------------------------------------------------------------------------------
    def paso9(self):
        self.titulo(9, "Ramas y Pull Requests; recorrido del evento WebSocket")

        def manual_git():
            raise Saltar(
                "se muestra en GitHub, no en la aplicación: ramas feature/…, un Pull Request por integrante con descripción y revisión de otro integrante, "
                "y la versión final integrada en main. El recorrido del evento WebSocket está en docs/ENSAYO_REVISION.md (paso 9)."
            )

        self.comprobar(9, "Ramas, Pull Requests y explicación del evento WebSocket", manual_git)

        def commit_desplegado():
            r = self.contextos["admin_a"].request.get(self.base + "/salud/")
            d = r.json()
            assert d.get("commit") not in (None, "", "sin definir"), (
                f"/salud/ dice commit «{d.get('commit')}»: el despliegue no registró el commit (usa deploy/actualizar.sh para que quede escrito)"
            )
            return f"el commit desplegado es {d['commit']}; compáralo con el último commit de main en GitHub"

        self.comprobar(9, "El commit desplegado se puede comparar con main (/salud/)", commit_desplegado)

    # --- paso 10 ---------------------------------------------------------------------------------------------
    def enlaces_del_menu(self, pg):
        """Enlaces del menú lateral, con los grupos abiertos."""
        for boton in pg.query_selector_all("aside button[aria-expanded=false]"):
            boton.click()
            pg.wait_for_timeout(250)
        hrefs = []
        for a in pg.query_selector_all("aside nav a.side-link"):
            href = a.get_attribute("href")
            if href and href.startswith("/") and href not in hrefs:
                hrefs.append(href)
        return hrefs

    def http_crudo(self, ruta, host):
        import socket
        import ssl
        from urllib.parse import urlparse

        url = urlparse(self.base)
        puerto = url.port or (443 if url.scheme == "https" else 80)
        conexion = socket.create_connection((url.hostname, puerto), timeout=10)
        if url.scheme == "https":
            conexion = ssl.create_default_context().wrap_socket(conexion, server_hostname=url.hostname)
        conexion.sendall(f"GET {ruta} HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n".encode())
        datos = b""
        while True:
            trozo = conexion.recv(65536)
            if not trozo:
                break
            datos += trozo
        conexion.close()
        cabecera, _, cuerpo = datos.partition(b"\r\n\r\n")
        return int(cabecera.split(b" ")[1]), cuerpo.decode("utf-8", errors="replace")

    def paso10(self):
        self.titulo(10, "Navegación sin escribir URL, teclado, páginas 403/404 y pruebas controladas de 400/500")

        def recorrer(alias):
            pg = self.paginas[alias]
            self.ir(pg, "/dashboard/" if not alias.startswith("cliente") else "/portal/")
            hrefs = self.enlaces_del_menu(pg)
            assert len(hrefs) >= 3, f"{alias}: el menú tiene muy pocos enlaces ({hrefs})"
            malos = []
            for href in hrefs:
                self.ir(pg, "/dashboard/" if not alias.startswith("cliente") else "/portal/")
                enlace = pg.locator(f"aside a.side-link[href='{href}']").first
                if not enlace.is_visible():
                    for boton in pg.query_selector_all("aside button[aria-expanded=false]"):
                        boton.click()
                        pg.wait_for_timeout(250)
                with pg.expect_navigation() as nav:
                    enlace.click()
                pg.wait_for_load_state("networkidle")
                estado = nav.value.status if nav.value else None
                actual = pg.query_selector("aside a.side-link[aria-current=page]")
                h1 = pg.query_selector("main h1, h1")
                titulo = pg.title()
                if estado != 200:
                    malos.append(f"{href} → HTTP {estado}")
                elif not h1 or not h1.inner_text().strip():
                    malos.append(f"{href} sin título de pantalla")
                elif not titulo.endswith("SGR") or titulo.startswith(" "):
                    malos.append(f"{href}: título del navegador «{titulo}»")
                elif actual is None or actual.get_attribute("href") != href.split("?")[0] and not pg.url.endswith(href):
                    malos.append(f"{href}: el menú no resalta el módulo activo")
            assert not malos, "; ".join(malos)
            return len(hrefs)

        for alias in ("admin_a", "editor_a", "lector_a", "lector_b", "cliente1", "cliente2"):
            self.comprobar(10, f"Menú de {alias}: cada enlace abre su pantalla con título, módulo activo y sin errores", lambda a=alias: f"{recorrer(a)} enlaces recorridos sin escribir ninguna URL")

        def teclado():
            pg = self.paginas["editor_a"]
            self.ir(pg, "/beneficiarios/?limpiar=1")
            pg.evaluate("document.activeElement && document.activeElement.blur()")
            pg.keyboard.press("Tab")
            primero = pg.evaluate("document.activeElement.textContent.trim()")
            assert "saltar" in primero.lower(), f"el primer Tab no ofrece «Saltar al contenido» (ofrece «{primero[:40]}»)"
            sin_marca = []
            for _ in range(45):
                info = pg.evaluate(
                    """() => { const e = document.activeElement; const c = getComputedStyle(e);
                    return { etiqueta: e.tagName, texto: (e.getAttribute('aria-label') || e.textContent || e.value || '').trim().slice(0, 30),
                    marca: (c.outlineStyle !== 'none' && parseFloat(c.outlineWidth) > 0) || (c.boxShadow && c.boxShadow !== 'none') } }"""
                )
                if not info["marca"]:
                    sin_marca.append(f"{info['etiqueta']} «{info['texto']}»")
                pg.keyboard.press("Tab")
            assert len(sin_marca) <= 2, f"elementos sin foco visible: {sin_marca[:6]}"
            return "el primer Tab ofrece «Saltar al contenido» y 45 Tab seguidos mostraron el foco visible en casi todos los elementos"

        self.comprobar(10, "Teclado: salto al contenido y foco visible", teclado)

        def modal_con_teclado():
            pg = self.paginas["admin_a"]
            self.ir(pg, "/beneficiarios/?limpiar=1")
            boton = pg.locator("main a.btn-primary").first
            boton.focus()
            pg.keyboard.press("Enter")
            pg.wait_for_selector("#sgr-modal.show")
            pg.wait_for_timeout(400)
            dentro = pg.evaluate("document.activeElement.closest('#sgr-modal') !== null")
            assert dentro, "al abrir el modal el foco no pasó a su interior"
            pg.keyboard.press("Escape")
            pg.wait_for_selector("#sgr-modal", state="hidden", timeout=5000)
            pg.wait_for_timeout(600)  # el foco vuelve cuando termina la animación de cierre
            vuelve = pg.evaluate("document.activeElement.matches('main a.btn-primary')")
            quien = pg.evaluate("document.activeElement.tagName + ' ' + (document.activeElement.className || '')")
            assert vuelve, f"al cerrar el modal con Escape el foco no volvió al botón que lo abrió (quedó en {quien})"
            return "Enter abre el modal con el foco dentro; Escape lo cierra y el foco vuelve al botón"

        self.comprobar(10, "Teclado: el modal se abre y se cierra sin ratón y el foco vuelve", modal_con_teclado)

        def sweetalert_con_teclado():
            pg = self.paginas["admin_a"]
            self.ir(pg, "/beneficiarios/?limpiar=1")
            pg.locator("tbody a[data-delete-kind=archive]").first.focus()
            pg.keyboard.press("Enter")
            self.swal(pg)
            dentro = pg.evaluate("document.activeElement.closest('.swal2-popup') !== null")
            assert dentro, "el foco no pasó al aviso de confirmación"
            pg.keyboard.press("Escape")
            pg.wait_for_selector(".swal2-popup", state="detached", timeout=5000)
            return "el aviso de confirmación recibe el foco y Escape lo cancela sin cambios"

        self.comprobar(10, "Teclado: el aviso de SweetAlert2 se maneja sin ratón", sweetalert_con_teclado)

        def paginas_403_404():
            detalles = []
            for alias, ruta, codigo in (("lector_a", "/beneficiarios/nuevo/", 403), ("lector_a", "/esta-pantalla-no-existe/", 404), ("cliente1", "/atencion/", 403)):
                texto = self.pagina_de_error(alias, ruta, codigo)
                assert str(codigo) in texto, f"la página no dice el código {codigo}"
                detalles.append(f"{codigo} en {ruta}")
            self.foto(self.paginas["cliente1"], "P10_403")
            return "páginas con el diseño del portal, código visible, sin trazas y con enlace para volver: " + ", ".join(detalles)

        self.comprobar(10, "Páginas 403 y 404 comprensibles y con el código HTTP correcto", paginas_403_404)

        def pagina_400():
            estado, cuerpo = self.http_crudo("/", "sitio-ajeno.example")
            assert estado == 400, f"un Host no permitido respondió {estado} y se esperaba 400"
            for prohibido in ("Traceback", "DisallowedHost", "ALLOWED_HOSTS", "sitio-ajeno", "SECRET_KEY"):
                assert prohibido not in cuerpo, f"la página 400 muestra «{prohibido}»"
            assert "<html" in cuerpo.lower(), "la respuesta 400 no es una página"
            return "un encabezado Host no permitido responde 400 con la página del portal, sin el texto de la excepción"

        self.comprobar(10, "Página 400 controlada (host no permitido) sin detalles técnicos", pagina_400)

        def pagina_500():
            raise Saltar(
                "el 500 solo se provoca de forma controlada en las pruebas automáticas con DEBUG=False: "
                "python manage.py test core.test_errores (comprueba código 500, página del portal y ausencia de trazas, SQL y configuración)"
            )

        self.comprobar(10, "Página 500 controlada (prueba automática con DEBUG=False)", pagina_500)

    # --- ejecución -------------------------------------------------------------------------------------------
    def limpiar(self):
        """Deja los datos casi como estaban: el beneficiario de la prueba se elimina y las atenciones quedan archivadas."""
        admin = self.paginas["admin_a"]
        print("\nLimpieza")
        try:
            for _ in range(10):  # atenciones: borrado lógico (no hay eliminación definitiva)
                if self.contar(admin, "/atencion/", self.marca) == 0:
                    break
                admin.click(f"tbody tr:has-text('{self.marca}') a[data-delete]")
                self.swal(admin)
                with admin.expect_navigation():
                    admin.click(".swal2-confirm")
                admin.wait_for_load_state("networkidle")
            for _ in range(5):  # beneficiario: se archiva y luego se elimina definitivamente (no tiene relaciones)
                if self.contar(admin, "/beneficiarios/", self.marca, "&archivados=1") == 0:
                    break
                fila = f"tbody tr:has-text('{self.marca}')"
                if admin.query_selector(f"{fila} a[data-delete-kind=archive]"):
                    admin.click(f"{fila} a[data-delete-kind=archive]")
                else:
                    admin.click(f"{fila} a[data-delete-kind=remove]")
                self.swal(admin)
                with admin.expect_navigation():
                    admin.click(".swal2-confirm")
                admin.wait_for_load_state("networkidle")
            print("  ✔ el beneficiario de la prueba se eliminó y las atenciones quedaron archivadas (no salen en listados ni en Excel)")
        except Exception as e:  # la limpieza no debe tapar los resultados del ensayo
            print(f"  – no se pudo terminar la limpieza ({type(e).__name__}): archiva a mano los registros que dicen «{self.marca}»")

    def correr(self, pasos):
        if sync_playwright is None:
            sys.exit("Falta Playwright: pip install playwright && playwright install chromium")
        with sync_playwright() as p:
            lanzamiento = {"executable_path": self.args.chromium} if self.args.chromium else {}
            self.nav = p.chromium.launch(args=["--no-sandbox"], **lanzamiento)
            try:
                print(f"Ensayo de la revisión sobre {self.base} · marca de los datos de prueba: «{self.marca}»")
                for alias in CUENTAS:
                    self.abrir(self.nav, alias)
                for numero in pasos:
                    getattr(self, f"paso{numero}")()
                    if numero == 8:
                        self.ingresar(self.paginas["lector_b"], "lector_b")  # la clave se cambió y se devolvió: su sesión se cerró
                self.limpiar()
            finally:
                self.nav.close()
        return self.informe()

    def informe(self):
        total = len(self.resultados)
        fallidas = [r for r in self.resultados if r["estado"] == "Fallida"]
        manuales = [r for r in self.resultados if r["estado"] == "Revisión manual"]
        print(f"\nResultado: {total - len(fallidas) - len(manuales)} aprobadas, {len(fallidas)} fallidas, {len(manuales)} para revisar a mano.")
        for r in fallidas:
            print(f"  ✘ Paso {r['paso']} · {r['prueba']}: {r['detalle']}")
        if self.args.informe:
            lineas = [
                f"# Ensayo de la revisión · {datetime.now().strftime('%d-%m-%Y %H:%M')}",
                "",
                f"Dirección: `{self.base}` · salud: `{json.dumps(self.datos.get('salud', {}), ensure_ascii=False)}`",
                "",
                "| Paso | Comprobación | Resultado | Detalle |",
                "|---|---|---|---|",
            ]
            for r in self.resultados:
                lineas.append(f"| {r['paso']} | {r['prueba']} | {r['estado']} | {r['detalle'].replace('|', '/')} |")
            Path(self.args.informe).write_text("\n".join(lineas) + "\n", encoding="utf-8")
            print(f"Informe escrito en {self.args.informe}")
        return 1 if fallidas else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", required=True, help="Dirección de la aplicación, por ejemplo http://127.0.0.1:8000")
    ap.add_argument("--pasos", default="1,2,3,4,5,6,7,8,9,10", help="Pasos a correr, separados por coma (por defecto, los diez)")
    ap.add_argument("--chromium", default="", help="Ruta de Chrome o Chromium si Playwright no trae el suyo")
    ap.add_argument("--capturas", default="", help="Carpeta donde guardar capturas de pantalla (opcional)")
    ap.add_argument("--informe", default="", help="Archivo .md donde escribir el resultado (opcional)")
    ap.add_argument("--bandeja", default="", help="Carpeta con los correos del servidor (EMAIL_BACKEND de archivos); sin ella, el paso 8 deja el correo como revisión manual")
    ap.add_argument("--descargas", default="", help="Carpeta temporal para los Excel descargados")
    ap.add_argument("--sin-verificar-tls", action="store_true", help="Acepta un certificado que el navegador no reconoce")
    ap.add_argument("--depurar", action="store_true", help="Agrega la línea de código a cada fallo")
    args = ap.parse_args()
    for alias in CUENTAS:
        clave_de(alias)
    sys.exit(Ensayo(args).correr([int(n) for n in args.pasos.split(",") if n.strip()]))


if __name__ == "__main__":
    main()
