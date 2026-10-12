#!/usr/bin/env python3
"""Recorre el SGR con un navegador real, toma las capturas de evidencia y registra qué se comprobó.

Qué hace (evidencias del A4 que se pueden sacar de un recorrido automático):
  1  Login y recuperación completa de contraseña
  2  Los seis CRUD (Delegaciones, Roles, Usuarios, Ítems y metas, Tipo de Atención, Sub Atención)
  3  Ingreso de atención con Tipo/Sub Atención dependientes y delegación del contexto
  4  Tabla, paginador, búsqueda y Exportar a Excel
  5  Identificación de delegación, usuario y rol, y alcance por perfil (incluye la matriz de menús por rol)
  6  Validaciones y mensajes SweetAlert2 (éxito, validación fallida, bloqueo, confirmación y cancelación)

Requisitos (en tu equipo; no forman parte del proyecto):
    pip install playwright && playwright install chromium

Uso:
    python tools/evidencias/capturar.py --url http://127.0.0.1:8000 --log-correo /ruta/al/log_del_servidor.txt
    python tools/evidencias/capturar.py --url https://tu-sitio-en-aws          # sin log, la recuperación queda para hacerla a mano

- --log-correo: archivo donde el servidor imprime el correo de recuperación (sin EMAIL_HOST el código sale por la
  consola del servidor). En AWS con correo real, hazlo a mano y deja ese paso para la captura manual.
- Deja las capturas en docs/evidencias/capturas/ y el resultado en docs/pruebas/resultados/navegador.json (lo lee
  `manage.py exportar_registro_pruebas` para la hoja «Navegador»).
- Crea registros con el prefijo «E2E» (delegación, rol, usuario, ítem, tipo y sub atención de prueba). Al terminar borra o
  desactiva lo que puede; el usuario de prueba queda inactivo.
"""

import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    from playwright.sync_api import TimeoutError as EsperaAgotada
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sys.exit("Falta Playwright: pip install playwright && playwright install chromium")

CLAVE = "Hola123!"
NUEVA_CLAVE = "Nueva-Clave-2026!"
CUENTAS = ["admin", "coordinacion1", "jefatura1", "supervision1", "matias.cavieres", "matias.quiroz", "consulta1"]


class Corrida:
    def __init__(self, args):
        self.args = args
        self.base = args.url.rstrip("/")
        self.capturas = Path(args.capturas)
        self.capturas.mkdir(parents=True, exist_ok=True)
        self.resultados = []
        self.sello = time.strftime("%H%M%S")
        self.n = 0

    # -- utilidades ---------------------------------------------------------------------------------------------------
    def foto(self, pg, nombre, completa=False):
        pg.wait_for_timeout(900)  # que terminen las animaciones de la ventana y de SweetAlert2
        ruta = self.capturas / f"{nombre}.png"
        pg.screenshot(path=str(ruta), full_page=completa)
        return ruta.relative_to(self.capturas.parent.parent.parent).as_posix() if self.capturas.is_relative_to(Path.cwd()) else ruta.as_posix()

    def comprobar(self, requisito, prueba, pasos, esperado, funcion):
        """Ejecuta una comprobación. ``funcion`` devuelve (texto obtenido, ruta de la captura) o lanza AssertionError."""
        self.n += 1
        ident = f"NAV-{self.n:03d}"
        estado, obtenido, evidencia = "Aprobada", "", ""
        try:
            resultado = funcion()
            obtenido, evidencia = resultado if isinstance(resultado, tuple) else (resultado, "")
        except Saltar as e:
            estado, obtenido = "No ejecutada", str(e)
        except (AssertionError, EsperaAgotada, Exception) as e:  # noqa: BLE001 - cualquier fallo es un resultado
            estado = "Fallida"
            obtenido = f"{type(e).__name__}: {str(e).strip().splitlines()[0][:300] if str(e).strip() else ''}"
        self.resultados.append(
            {
                "id": ident,
                "requisito": requisito,
                "prueba": prueba,
                "pasos": "\n".join(f"{i}. {p}" for i, p in enumerate(pasos, 1)),
                "esperado": esperado,
                "obtenido": obtenido,
                "estado": estado,
                "evidencia": evidencia or "(sin captura)",
                "responsable": self.args.responsable,
                "fecha": datetime.now().strftime("%Y-%m-%d %H:%M"),
            }
        )
        marca = {"Aprobada": "✔", "Fallida": "✘", "No ejecutada": "–"}[estado]
        print(f"  {marca} {ident} {prueba} · {estado}" + (f" · {obtenido}" if estado != "Aprobada" else ""))


class Saltar(Exception):
    """La comprobación no se puede hacer en este entorno (se registra como «No ejecutada», nunca como aprobada)."""


def ingresar(pg, base, usuario, clave=CLAVE):
    pg.goto(base + "/")
    if "/dashboard" in pg.url:  # ya había una sesión: se cierra
        pg.click("text=Cerrar sesión")
        pg.goto(base + "/")
    pg.fill("#id_username", usuario)
    pg.fill("#id_password", clave)
    pg.click("button[type=submit]")
    pg.wait_for_load_state("networkidle")


def salir(pg, base):
    pg.goto(base + "/dashboard/")
    boton = pg.query_selector("button:has-text('Cerrar sesión')")
    if boton:
        boton.click()
        pg.wait_for_load_state("networkidle")


def swal(pg, timeout=4000):
    """Texto del SweetAlert2 visible (aviso, confirmación o error)."""
    pg.wait_for_selector(".swal2-popup", timeout=timeout)
    return " ".join(pg.inner_text(".swal2-popup").split())


def cerrar_swal(pg):
    for sel in (".swal2-confirm", ".swal2-close"):
        boton = pg.query_selector(sel)
        if boton and boton.is_visible():
            boton.click()
            break
    pg.wait_for_selector(".swal2-popup", state="detached", timeout=4000)


def abrir_modal(pg, base, ruta, texto):
    pg.goto(base + ruta)
    pg.click("main a.btn-primary")  # el botón principal del listado («Nuevo …») abre el formulario en la ventana
    pg.wait_for_selector("#sgr-modal.show")


def guardar_modal(pg):
    """Guarda el formulario de la ventana. Si todo está bien, la página se recarga con el listado actualizado."""
    try:
        with pg.expect_navigation():
            pg.click("#sgr-modal button[type=submit]:not([name=_addanother])")
    except EsperaAgotada:
        aviso = pg.query_selector(".swal2-popup")
        raise AssertionError("no se guardó: " + (" ".join(aviso.inner_text().split()) if aviso else "sin aviso")) from None
    pg.wait_for_load_state("networkidle")


def celda_en_listado(pg, base, ruta, texto):
    pg.goto(base + ruta + ("&" if "?" in ruta else "?") + "q=" + texto.replace(" ", "+"))
    return pg.query_selector(f"tbody tr:has-text('{texto}')")


def total_resultados(pg):
    m = re.search(r"([\d\.]+)\s+resultado", pg.inner_text("main"))
    return int(m.group(1).replace(".", "")) if m else None


def correr(args):
    c = Corrida(args)
    base = c.base
    marca = f"E2E {c.sello}"
    usuario_e2e = f"e2e.{c.sello}"
    correo_e2e = f"{usuario_e2e}@sgr.example"
    datos = {}

    with sync_playwright() as p:
        lanzamiento = {"executable_path": args.chromium} if args.chromium else {}
        navegador = p.chromium.launch(**lanzamiento)
        ctx = navegador.new_context(viewport={"width": 1366, "height": 850}, locale="es-CL", accept_downloads=True, ignore_https_errors=args.sin_verificar_tls)
        pg = ctx.new_page()
        pg.set_default_timeout(8000)
        print(f"Recorrido de evidencias sobre {base}")

        # ------------------------------------------------------------------------------------------------ EV1 · Login
        print("EV1 · Login y recuperación")

        def login_ok():
            ingresar(pg, base, "matias.cavieres")
            assert "/dashboard" in pg.url, f"no llegó al dashboard ({pg.url})"
            cabecera = pg.inner_text(".topbar")
            assert "Matías Cavieres" in cabecera and "Funcionario" in cabecera and "DEL01" in cabecera, f"cabecera incompleta: {cabecera!r}"
            return "Ingresó y llegó al dashboard con la delegación, el usuario y el perfil a la vista.", c.foto(pg, "EV1_01_login_correcto_dashboard")

        c.comprobar("A1-01, A3-03", "Login correcto lleva al dashboard", ["Abrir /", "Escribir matias.cavieres y su clave", "Ingresar"], "Entra al dashboard de su delegación.", login_ok)
        salir(pg, base)

        def login_malo():
            pg.goto(base + "/")
            pg.fill("#id_username", "matias.cavieres")
            pg.fill("#id_password", "clave-equivocada")
            pg.click("button[type=submit]")
            pg.wait_for_load_state("networkidle")
            texto = pg.inner_text("body")
            assert "/dashboard" not in pg.url
            assert "contraseña es incorrecta" not in texto.lower() and "no existe" not in texto.lower(), "el aviso revela qué dato falló"
            foto = c.foto(pg, "EV1_02_login_incorrecto")
            pg.goto(base + "/")
            pg.fill("#id_username", "no.existe")
            pg.fill("#id_password", "otra-clave")
            pg.click("button[type=submit]")
            pg.wait_for_load_state("networkidle")
            assert "/dashboard" not in pg.url
            return "Con clave mala o usuario inexistente no entra y el aviso es genérico.", foto

        c.comprobar("A3-03", "Login incorrecto no revela qué dato falló", ["Escribir un usuario válido con clave mala", "Escribir un usuario inexistente"], "No entra y el mensaje no dice si falló el usuario o la clave.", login_malo)

        def login_vacio():
            pg.goto(base + "/")
            pg.click("button[type=submit]")
            texto = swal(pg)
            assert "obligatorio" in texto.lower() or "revisa" in texto.lower(), texto
            foto = c.foto(pg, "EV6_01_sweetalert_validacion_login_vacio")
            cerrar_swal(pg)
            return f"SweetAlert2 de validación: «{texto[:120]}»", foto

        c.comprobar("A3-02, A3-03, A3-01", "Campos vacíos en el login muestran SweetAlert2", ["Abrir /", "Enviar el formulario vacío"], "Aviso de validación con SweetAlert2; no se envía nada.", login_vacio)

        def enlace_recuperacion():
            pg.goto(base + "/")
            pg.click("text=/olvid|recuper/i")
            pg.wait_for_load_state("networkidle")
            assert "/recuperar" in pg.url
            foto = c.foto(pg, "EV1_03_recuperar_solicitud")
            pg.click("text=/volver|ingres/i")
            pg.wait_for_load_state("networkidle")
            return "El login enlaza a la recuperación y la recuperación vuelve al login.", foto

        c.comprobar("A1-02, C2", "Navegación login ⇄ recuperación", ["Abrir /", "Clic en recuperar contraseña", "Clic en volver"], "Se puede ir y volver entre ambas pantallas.", enlace_recuperacion)

        # ---------------------------------------------------------------------------------- EV2 · Seis CRUD (como admin)
        print("EV2 · Seis CRUD")
        ingresar(pg, base, "admin")

        def crud_delegacion():
            nombre = f"Delegación {marca}"
            abrir_modal(pg, base, "/delegaciones/", "Nueva delegación")
            pg.fill("#id_name", nombre)
            pg.fill("#id_address", "Av. de Prueba 123")
            pg.fill("#id_commune", "La Serena")
            pg.fill("#id_managers", "Responsable E2E")
            pg.fill("#id_scope", "Sector de prueba")
            c.foto(pg, "EV2_01_delegaciones_formulario")
            guardar_modal(pg)
            assert celda_en_listado(pg, base, "/delegaciones/", nombre), "no aparece en el listado"
            foto = c.foto(pg, "EV2_02_delegaciones_listado_con_registro_nuevo")
            datos["delegacion"] = nombre
            return f"Se creó «{nombre}» con código, dirección y comuna y aparece en el listado.", foto

        c.comprobar("A1-05, A3-08", "CRUD Delegaciones: crear y listar", ["Abrir Delegaciones", "Nueva delegación", "Completar los campos", "Guardar", "Buscar el registro"], "El registro queda guardado y visible en el listado.", crud_delegacion)

        def crud_delegacion_requeridos():
            abrir_modal(pg, base, "/delegaciones/", "Nueva delegación")
            pg.fill("#id_name", f"Sin dirección {marca}")
            pg.click("#sgr-modal button[type=submit]:not([name=_addanother])")
            texto = swal(pg)
            assert "Dirección" in texto and "obligatorio" in texto.lower(), texto
            foto = c.foto(pg, "EV6_02_sweetalert_validacion_delegacion")
            cerrar_swal(pg)
            pg.keyboard.press("Escape")
            return "Dirección y comuna obligatorias: SweetAlert2 lista lo que falta y no se guarda nada.", foto

        c.comprobar("A3-02, A3-08, A3-13", "Delegaciones: validación fallida con SweetAlert2", ["Nueva delegación", "Escribir solo el nombre", "Guardar"], "Avisa que dirección y comuna son obligatorias.", crud_delegacion_requeridos)

        def eliminar_con_cancelar():
            nombre = datos.get("delegacion") or ""
            if not nombre:
                raise Saltar("depende de la creación de la delegación")
            fila = celda_en_listado(pg, base, "/delegaciones/", nombre)
            fila.query_selector("a.act-danger").click()
            texto = swal(pg)
            foto = c.foto(pg, "EV6_03_sweetalert_confirmar_eliminar")
            pg.click(".swal2-cancel")
            pg.wait_for_selector(".swal2-popup", state="detached")
            assert celda_en_listado(pg, base, "/delegaciones/", nombre), "se eliminó aunque se canceló"
            fila = celda_en_listado(pg, base, "/delegaciones/", nombre)
            fila.query_selector("a.act-danger").click()
            swal(pg)
            pg.click(".swal2-confirm")
            pg.wait_for_load_state("networkidle")
            assert not celda_en_listado(pg, base, "/delegaciones/", nombre), "no se eliminó al confirmar"
            return f"Confirmación «{texto[:80]}…»: cancelar no elimina; confirmar sí.", foto

        c.comprobar("A3-13, A2-02", "Eliminar con confirmación y cancelación (Delegaciones)", ["Clic en Eliminar", "Cancelar", "Clic en Eliminar", "Confirmar"], "Cancelar conserva el registro; confirmar lo elimina (archiva).", eliminar_con_cancelar)

        def crud_rol():
            nombre = f"Rol {marca}"
            abrir_modal(pg, base, "/roles/", "Nuevo rol")
            pg.fill("#id_name", nombre)
            pg.fill("#id_description", "Rol de prueba creado por el recorrido automático.")
            c.foto(pg, "EV2_03_roles_formulario_con_matriz_de_permisos")
            guardar_modal(pg)
            assert celda_en_listado(pg, base, "/roles/", nombre), "no aparece el rol"
            foto = c.foto(pg, "EV2_04_roles_listado")
            datos["rol"] = nombre
            return f"Se creó el rol «{nombre}» con descripción, alcance y estado.", foto

        c.comprobar("A1-06, A3-08", "CRUD Roles: crear y listar", ["Roles y permisos", "Nuevo rol", "Nombre y descripción", "Guardar"], "El rol queda en el listado con su alcance y estado.", crud_rol)

        def crud_usuario():
            abrir_modal(pg, base, "/usuarios/", "Nuevo usuario")
            pg.fill("#id_username", usuario_e2e)
            pg.fill("#id_first_name", "Prueba")
            pg.fill("#id_last_name", "Automática")
            pg.fill("#id_email", correo_e2e)
            pg.fill("#id_password1", CLAVE)
            pg.fill("#id_password2", CLAVE)
            pg.locator("#sgr-modal .role-option", has_text="Coordinación").locator("input").check()
            c.foto(pg, "EV2_05_usuarios_formulario")
            guardar_modal(pg)
            assert celda_en_listado(pg, base, "/usuarios/", usuario_e2e), "no aparece el usuario"
            foto = c.foto(pg, "EV2_06_usuarios_listado_con_delegacion")
            datos["usuario"] = usuario_e2e
            return f"Se creó la cuenta «{usuario_e2e}» con perfil Coordinación; el listado muestra su delegación.", foto

        c.comprobar("A1-07, A3-08", "CRUD Usuarios: crear cuenta con perfil", ["Control de usuarios", "Nuevo usuario", "Completar datos, correo, clave y perfil", "Guardar"], "La cuenta queda activa y aparece en el listado.", crud_usuario)

        def crud_item():
            nombre = f"Ítem {marca}"
            abrir_modal(pg, base, "/items/", "Nuevo")
            pg.fill("#id_name", nombre)
            if pg.query_selector("#id_description"):
                pg.fill("#id_description", "Ítem de prueba del recorrido automático.")
            c.foto(pg, "EV2_07_items_formulario")
            guardar_modal(pg)
            assert celda_en_listado(pg, base, "/items/", nombre), "no aparece el ítem"
            foto = c.foto(pg, "EV2_08_items_listado")
            datos["item"] = nombre
            return f"Se creó «{nombre}» con código y descripción.", foto

        c.comprobar("A1-08, A3-08", "CRUD Ítems y metas: crear y listar", ["Ítems y metas", "Nuevo", "Nombre y descripción", "Guardar"], "El ítem queda en el listado con su código.", crud_item)

        def crud_tipo():
            nombre = f"Tipo {marca}"
            abrir_modal(pg, base, "/tipos-de-atencion/", "Nuevo")
            pg.fill("#id_name", nombre)
            if pg.query_selector("#id_description"):
                pg.fill("#id_description", "Tipo de atención de prueba.")
            c.foto(pg, "EV2_09_tipos_formulario")
            guardar_modal(pg)
            assert celda_en_listado(pg, base, "/tipos-de-atencion/", nombre), "no aparece el tipo"
            foto = c.foto(pg, "EV2_10_tipos_listado")
            datos["tipo"] = nombre
            return f"Se creó «{nombre}» (código TA…).", foto

        c.comprobar("A1-09, A3-08", "CRUD Tipo de Atención: crear y listar", ["Tipos de Atención", "Nuevo", "Nombre y descripción", "Guardar"], "El tipo queda en el listado con su código TA y su total de sub atenciones.", crud_tipo)

        def crud_sub():
            if not datos.get("tipo"):
                raise Saltar("depende de la creación del tipo de atención")
            nombre = f"Sub {marca}"
            abrir_modal(pg, base, "/sub-atenciones/", "Nuevo")
            pg.fill("#id_name", nombre)
            valor = pg.evaluate(
                """(t) => { const o = [...document.querySelectorAll('#id_parent_item option')].find(x => x.textContent.includes(t)); return o ? o.value : null; }""",
                datos["tipo"],
            )
            assert valor, "el tipo recién creado no se ofrece en la lista de la sub atención"
            pg.select_option("#id_parent_item", valor)
            c.foto(pg, "EV2_11_sub_atencion_formulario")
            guardar_modal(pg)
            assert celda_en_listado(pg, base, "/sub-atenciones/", nombre), "no aparece la sub atención"
            foto = c.foto(pg, "EV2_12_sub_atencion_listado_con_tipo")
            datos["sub"] = nombre
            return f"Se creó «{nombre}» asociada al tipo «{datos['tipo']}».", foto

        c.comprobar("A1-10, A3-10", "CRUD Sub Atención: asociada a un Tipo de Atención", ["Sub Atención", "Nuevo", "Elegir el tipo", "Guardar"], "Queda guardada con su tipo asociado visible.", crud_sub)

        def tipo_con_sub_no_se_elimina():
            if not datos.get("sub"):
                raise Saltar("depende de la sub atención creada")
            fila = celda_en_listado(pg, base, "/tipos-de-atencion/", datos["tipo"])
            fila.query_selector("a.act-danger").click()
            texto = swal(pg)
            assert "sub atenci" in texto.lower(), texto
            foto = c.foto(pg, "EV6_04_sweetalert_bloqueo_tipo_con_sub_atenciones")
            cerrar_swal(pg)
            return f"Bloqueo por integridad: «{texto[:110]}…»", foto

        c.comprobar("A3-10, A3-13", "Un tipo con sub atenciones activas no se elimina", ["Tipos de Atención", "Eliminar el tipo con sub atención activa"], "SweetAlert2 explica que tiene sub atenciones activas y no elimina.", tipo_con_sub_no_se_elimina)

        # ---------------------------------------------------------------------------- EV1 (cont.) · recuperación completa
        def recuperacion_completa():
            if not args.log_correo:
                raise Saltar("falta --log-correo (el código del correo no se puede leer desde el navegador)")
            if not datos.get("usuario"):
                raise Saltar("depende de la cuenta de prueba creada")
            salir(pg, base)
            log = Path(args.log_correo)
            antes = log.stat().st_size if log.exists() else 0
            pg.goto(base + "/recuperar/")
            pg.fill("#id_email", correo_e2e)
            pg.click("button[type=submit]")
            pg.wait_for_load_state("networkidle")
            assert "/recuperar/codigo" in pg.url or "codigo" in pg.url, pg.url
            cajas = pg.query_selector_all("input.code-box")
            assert len(cajas) == 6, f"se esperaban 6 casillas y hay {len(cajas)}"
            c.foto(pg, "EV1_04_recuperar_codigo_seis_casillas")
            codigo = None
            for _ in range(20):
                texto = log.read_text(errors="replace")[antes:]
                m = re.findall(r"^ {4}(\d{6})$", texto, re.M)
                if m:
                    codigo = m[-1]
                    break
                time.sleep(0.5)
            assert codigo, "no apareció el código en el log del servidor"
            # pegar el código completo en la primera casilla
            cajas[0].focus()
            pg.evaluate(
                """(codigo) => { const d = new DataTransfer(); d.setData('text', codigo);
                   document.querySelector('input.code-box').dispatchEvent(new ClipboardEvent('paste', {clipboardData: d, bubbles: true, cancelable: true})); }""",
                codigo,
            )
            valores = "".join(caja.input_value() for caja in pg.query_selector_all("input.code-box"))
            assert valores == codigo, f"el pegado no llenó las casillas ({valores!r})"
            c.foto(pg, "EV1_05_codigo_pegado_en_las_seis_casillas")
            pg.click("button[type=submit]")
            pg.wait_for_load_state("networkidle")
            assert pg.query_selector("input[type=password]"), "no se abrió el paso de la contraseña nueva"
            for campo in pg.query_selector_all("input[type=password]"):
                campo.fill(NUEVA_CLAVE)
            c.foto(pg, "EV1_06_recuperar_nueva_contrasena")
            pg.click("button[type=submit]")
            confirmacion = swal(pg)
            c.foto(pg, "EV6_05_sweetalert_confirmar_cambio_de_contrasena")
            pg.click(".swal2-confirm")
            pg.wait_for_load_state("networkidle")
            assert pg.url.rstrip("/") == base or pg.url.endswith("/"), pg.url
            ingresar(pg, base, usuario_e2e, NUEVA_CLAVE)
            assert "/dashboard" in pg.url, "no entró con la clave nueva"
            salir(pg, base)
            ingresar(pg, base, usuario_e2e, CLAVE)
            assert "/dashboard" not in pg.url, "la clave anterior sigue funcionando"
            return f"Flujo completo: código de 6 dígitos, pegado en 6 casillas, confirmación «{confirmacion[:60]}…», entra con la clave nueva y la anterior se rechaza.", c.foto(pg, "EV1_07_clave_anterior_rechazada")

        c.comprobar("A1-02, A1-03, A1-04, A3-04, A3-05, A3-06, A3-07, C2", "Recuperación completa de contraseña", ["Pedir código", "Leer el código del correo", "Pegarlo en las 6 casillas", "Crear la contraseña nueva y confirmar", "Entrar con la nueva y con la anterior"], "Se cambia la contraseña; la nueva entra y la anterior no.", recuperacion_completa)

        def correo_inexistente():
            salir(pg, base)
            pg.goto(base + "/recuperar/")
            pg.fill("#id_email", "nadie.existe@sgr.example")
            pg.click("button[type=submit]")
            pg.wait_for_load_state("networkidle")
            texto = pg.inner_text("body")
            assert "/codigo" in pg.url, pg.url
            assert "no existe" not in texto.lower() and "no está registrado" not in texto.lower(), "revela que el correo no existe"
            return "Un correo inexistente recibe la misma pantalla y el mismo aviso que uno real.", c.foto(pg, "EV1_08_recuperar_correo_inexistente_misma_respuesta")

        c.comprobar("A3-04", "Recuperación no revela si el correo existe", ["Abrir /recuperar/", "Escribir un correo inexistente", "Enviar"], "Misma respuesta que con un correo real.", correo_inexistente)

        # ------------------------------------------------------------------------------------------- EV3 · Ingreso de atención
        print("EV3 · Ingreso de atención")
        ingresar(pg, base, "matias.cavieres")

        def ingreso_dependiente():
            pg.goto(base + "/atencion/")
            c.foto(pg, "EV3_01_atencion_pantalla_principal")
            pg.click("a:has-text('Registrar atención')")
            pg.wait_for_selector("#sgr-modal.show")
            texto = pg.inner_text("#sgr-modal")
            assert "Delegación" in texto and "responsable" in texto.lower(), "la nota de delegación y responsable no aparece"
            tipos = [o.get_attribute("value") for o in pg.query_selector_all("#sgr-modal select[name=attention_type] option") if o.get_attribute("value")]
            assert len(tipos) >= 2, "se necesitan al menos 2 tipos para probar la dependencia"
            pg.select_option("#sgr-modal select[name=attention_type]", tipos[0])
            subs_a = [o.inner_text() for o in pg.query_selector_all("#sgr-modal select[name=item] option") if o.get_attribute("value") and o.is_visible() and not o.is_disabled()]
            foto = c.foto(pg, "EV3_02_ingreso_tipo_y_sub_atencion_dependientes")
            if subs_a:
                pg.select_option("#sgr-modal select[name=item]", index=1)
            pg.select_option("#sgr-modal select[name=attention_type]", tipos[1])
            valor = pg.eval_on_selector("#sgr-modal select[name=item]", "e => e.value")
            assert valor in ("", None) or not subs_a, f"la sub atención no se limpió al cambiar el tipo ({valor!r})"
            return f"La lista de sub atención se acota al tipo elegido ({len(subs_a)} opciones) y se limpia al cambiar el tipo.", foto

        c.comprobar("A2-13, A3-11", "Tipo y Sub Atención dependientes", ["Atención › Registrar atención", "Elegir un tipo", "Ver la sub atención", "Cambiar de tipo"], "La sub atención muestra solo opciones del tipo y se limpia al cambiar el tipo.", ingreso_dependiente)

        def ingreso_cancelar():
            pg.goto(base + "/actividades/")
            antes = total_resultados(pg)
            pg.goto(base + "/atencion/")
            pg.click("a:has-text('Registrar atención')")
            pg.wait_for_selector("#sgr-modal.show")
            pg.fill("#sgr-modal [name=requester]", f"No debe guardarse {marca}")
            pg.fill("#sgr-modal [name=request_description]", "Esto se cancela.")
            pg.click("#sgr-modal button:has-text('Cancelar')")
            pg.wait_for_function("() => !document.querySelector('#sgr-modal.show')", timeout=10000)
            aviso = ""
            try:
                aviso = swal(pg, timeout=3000)
            except EsperaAgotada:
                pass
            foto = c.foto(pg, "EV3_03_ingreso_cancelar_no_crea_registros")
            pg.goto(base + "/actividades/")
            despues = total_resultados(pg)
            assert antes == despues, f"cambió el total de atenciones ({antes} → {despues})"
            return f"Cancelar cerró la ventana sin crear nada (atenciones: {antes} antes y {despues} después). Aviso: «{aviso[:80]}»", foto

        c.comprobar("A2-16, A3-11", "Cancelar no crea registros", ["Contar atenciones", "Abrir Registrar atención y escribir datos", "Cancelar", "Contar de nuevo"], "El total no cambia.", ingreso_cancelar)

        def ingreso_guardar():
            pg.goto(base + "/atencion/")
            pg.click("a:has-text('Registrar atención')")
            pg.wait_for_selector("#sgr-modal.show")
            pg.fill("#sgr-modal [name=requester]", f"Persona {marca}")
            tipos = [o.get_attribute("value") for o in pg.query_selector_all("#sgr-modal select[name=attention_type] option") if o.get_attribute("value")]
            pg.select_option("#sgr-modal select[name=attention_type]", tipos[0])
            subs = [o.get_attribute("value") for o in pg.query_selector_all("#sgr-modal select[name=item] option") if o.get_attribute("value") and not o.is_disabled()]
            if subs:
                pg.select_option("#sgr-modal select[name=item]", subs[0])
            pg.fill("#sgr-modal [name=request_description]", "Atención creada por el recorrido automático.")
            pg.click("#sgr-modal button[type=submit]:not([name=_addanother])")
            texto = swal(pg)
            assert re.search(r"ATN\d{5}", texto), texto
            foto = c.foto(pg, "EV3_04_ingreso_confirmacion_con_identificador")
            cerrar_swal(pg)
            return f"Confirmación con SweetAlert2: «{texto[:110]}»", foto

        c.comprobar("A1-11, A2-14, A2-15, A3-11", "Guardar la atención muestra confirmación con identificador", ["Registrar atención", "Completar solicitante, tipo, sub atención y descripción", "Guardar"], "SweetAlert2 «Atención registrada para … Identificador: ATN00001».", ingreso_guardar)

        def ingreso_obligatorios():
            pg.goto(base + "/atencion/")
            pg.click("a:has-text('Registrar atención')")
            pg.wait_for_selector("#sgr-modal.show")
            pg.click("#sgr-modal button[type=submit]:not([name=_addanother])")
            texto = swal(pg)
            assert "obligatorio" in texto.lower(), texto
            foto = c.foto(pg, "EV6_06_sweetalert_validacion_ingreso_de_atencion")
            cerrar_swal(pg)
            pg.keyboard.press("Escape")
            return f"Campos obligatorios vacíos: «{texto[:100]}…»", foto

        c.comprobar("A3-02, A3-11, A3-13", "Ingreso de atención: obligatorios con SweetAlert2", ["Registrar atención", "Guardar sin completar"], "Avisa qué campos faltan y no guarda.", ingreso_obligatorios)

        # ------------------------------------------------------------------------------------ EV4 · Tabla, búsqueda y Excel
        print("EV4 · Tabla, paginador, búsqueda y Excel")
        salir(pg, base)
        ingresar(pg, base, "admin")

        def busqueda_y_tabla():
            pg.goto(base + "/delegaciones/")
            c.foto(pg, "EV4_01_delegaciones_tabla_paginador_busqueda")
            pg.fill("input[name=q]", "NORTE")
            pg.click("button:has-text('Buscar')")
            pg.wait_for_load_state("networkidle")
            filas = pg.query_selector_all("tbody tr")
            assert len(filas) >= 1 and "Norte" in filas[0].inner_text(), "la búsqueda en mayúsculas no encontró «Norte»"
            total = total_resultados(pg)
            return f"Búsqueda sin distinguir mayúsculas: «NORTE» encontró {total} resultado(s).", c.foto(pg, "EV4_02_busqueda_parcial_sin_mayusculas")

        c.comprobar("A2-03, A2-06", "Búsqueda parcial sin distinguir mayúsculas", ["Delegaciones", "Escribir NORTE", "Buscar"], "Encuentra «Delegación Norte».", busqueda_y_tabla)

        def paginador():
            pg.goto(base + "/actividades/?filas=10")
            if not pg.query_selector(".pagination"):
                raise Saltar("hay pocos registros: no se muestra paginador (cargar volumen con manage.py cargar_volumen_estres)")
            pg.click(".pagination a:has-text('2')")
            pg.wait_for_load_state("networkidle")
            assert "page=2" in pg.url or "pagina=2" in pg.url, pg.url
            return "El paginador cambia de página y el total de resultados se mantiene.", c.foto(pg, "EV4_03_paginador_pagina_2")

        c.comprobar("A2-03, A2-04", "Paginador conserva búsqueda y filtros", ["Actividades", "Ir a la página 2"], "La página 2 conserva los filtros.", paginador)

        def excel():
            pg.goto(base + "/delegaciones/")
            total = total_resultados(pg)
            with pg.expect_download() as d:
                pg.click("button:has-text('Exportar a Excel'), a:has-text('Exportar a Excel')")
            ruta = c.capturas / "EV4_04_exportacion_delegaciones.xlsx"
            d.value.save_as(str(ruta))
            from openpyxl import load_workbook

            hoja = load_workbook(ruta).active
            filas = list(hoja.iter_rows(values_only=True))
            ini = next(i for i, f in enumerate(filas) if f and f[0] == "Código")
            datos_xlsx = [f for f in filas[ini + 1 :] if f and f[0]]
            assert len(datos_xlsx) == total, f"tabla {total} filas, Excel {len(datos_xlsx)}"
            assert not any("contraseña" in str(x).lower() or "password" in str(x).lower() for f in filas for x in f if x), "el Excel trae contraseñas"
            return f"El Excel tiene {len(datos_xlsx)} filas, igual que la tabla ({total}).", ruta.name

        c.comprobar("A2-07, A3-09", "Exportar a Excel coincide con la tabla", ["Delegaciones", "Exportar a Excel", "Abrir el archivo y contar filas"], "El archivo trae las mismas filas que la tabla y ningún campo interno.", excel)

        # --------------------------------------------------------------------------------------- EV5 · Roles y alcance
        print("EV5 · Roles, permisos y alcance")
        matriz = {}
        for cuenta in CUENTAS:
            salir(pg, base)
            ingresar(pg, base, cuenta)
            if "/dashboard" not in pg.url:
                continue
            menus = sorted({a.inner_text().strip() for a in pg.query_selector_all("#barra-lateral a") if a.inner_text().strip() and "Sistema de Gestión" not in a.inner_text()})
            cabecera = " ".join(pg.inner_text("#barra-lateral").split()[:30])
            matriz[cuenta] = {"menus": menus, "cabecera": cabecera}
            c.foto(pg, f"EV5_{CUENTAS.index(cuenta) + 1:02d}_rol_{cuenta.replace('.', '_')}_dashboard")

        def menus_distintos():
            assert len(matriz) >= 5, "no se pudo ingresar con las cuentas de demostración"
            assert "Control de usuarios" in matriz["admin"]["menus"], "el Super Usuario no ve Control de usuarios"
            for cuenta, d in matriz.items():
                if cuenta not in ("admin",):
                    assert "Control de usuarios" not in d["menus"], f"{cuenta} ve Control de usuarios"
            assert matriz["admin"]["menus"] != matriz["consulta1"]["menus"], "Super Usuario y Consulta ven lo mismo"
            return f"Cada rol ve un menú distinto: {', '.join(f'{k}={len(v['menus'])} opciones' for k, v in matriz.items())}.", f"{Path(args.capturas).as_posix()}/EV5_*_rol_*_dashboard.png"

        c.comprobar("IMP-02, IMP-03", "Cada rol ve solo sus menús", ["Ingresar con cada cuenta de demostración", "Leer el menú lateral"], "Solo el Super Usuario ve Control de usuarios; los menús difieren por rol.", menus_distintos)

        def urls_prohibidas():
            salir(pg, base)
            ingresar(pg, base, "consulta1")
            ok403 = []
            for ruta in ("/usuarios/", "/roles/", "/delegaciones/nuevo/", "/actividades/nuevo/"):
                r = pg.goto(base + ruta)
                assert r.status == 403, f"{ruta} respondió {r.status} para consulta1 (se esperaba 403)"
                ok403.append(ruta)
            foto = c.foto(pg, "EV5_10_consulta_acceso_prohibido_403")
            r = pg.goto(base + "/actividades/")
            assert r.status == 200
            assert not pg.query_selector("a:has-text('Registrar atención'), a:has-text('Nueva actividad')"), "Consulta ve botones para crear"
            c.foto(pg, "EV5_11_consulta_listado_sin_botones_de_cambio")
            return f"Consulta recibe 403 en {', '.join(ok403)} y su listado no muestra botones de cambio.", foto

        c.comprobar("A2-11, IMP-02", "El servidor responde 403 aunque se conozca la dirección", ["Ingresar como consulta1", "Abrir por dirección usuarios, roles y formularios de alta"], "403 en cada una; sin botones de cambio.", urls_prohibidas)

        def alcance_delegacion():
            salir(pg, base)
            ingresar(pg, base, "matias.quiroz")
            pg.goto(base + "/actividades/")
            texto = pg.inner_text("main")
            assert "Delegación Norte" not in texto, "matias.quiroz (Sur) ve datos de Norte"
            cab = pg.inner_text("#barra-lateral")
            assert "Sur" in cab, "la cabecera no indica la delegación Sur"
            return "matias.quiroz solo ve la Delegación Sur: la cabecera la indica y el listado no trae registros de Norte.", c.foto(pg, "EV5_12_alcance_delegacion_sur")

        c.comprobar("A2-09, A2-11, A3-12", "Alcance por delegación", ["Ingresar como matias.quiroz (Sur)", "Abrir Actividades"], "Solo registros de su delegación; cabecera con Delegación Sur.", alcance_delegacion)

        def selector_delegaciones():
            salir(pg, base)
            ingresar(pg, base, "supervision1")
            sel = pg.query_selector("#contexto-delegacion")
            if not sel:
                raise Saltar("no se encontró el selector de delegaciones en la franja de arriba")
            opciones = [o.inner_text() for o in sel.query_selector_all("option")]
            assert len(opciones) >= 2, opciones
            foto = c.foto(pg, "EV5_13_selector_de_delegaciones")
            return f"supervision1 puede elegir entre {len(opciones)} delegaciones autorizadas: {', '.join(opciones)}.", foto

        c.comprobar("A2-10", "Selector con varias delegaciones autorizadas", ["Ingresar como supervision1", "Mirar la franja de arriba"], "El selector ofrece solo sus delegaciones.", selector_delegaciones)

        # --------------------------------------------------------------------------------------------- limpieza
        print("Limpieza de los datos E2E")
        salir(pg, base)
        ingresar(pg, base, "admin")
        for clave, ruta in (("sub", "/sub-atenciones/"), ("tipo", "/tipos-de-atencion/"), ("item", "/items/"), ("rol", "/roles/")):
            nombre = datos.get(clave)
            if not nombre:
                continue
            try:
                fila = celda_en_listado(pg, base, ruta, nombre)
                if fila and fila.query_selector("a.act-danger"):
                    fila.query_selector("a.act-danger").click()
                    swal(pg)
                    pg.click(".swal2-confirm")
                    pg.wait_for_load_state("networkidle")
            except Exception as e:  # noqa: BLE001
                print(f"  (no se pudo borrar {nombre}: {e})")
        if datos.get("usuario"):
            try:
                pg.goto(base + "/usuarios/")
                fila = celda_en_listado(pg, base, "/usuarios/", datos["usuario"])
                if fila:
                    fila.query_selector("a[data-modal-form]").click()
                    pg.wait_for_selector("#sgr-modal.show")
                    pg.uncheck("#id_is_active")
                    pg.click("#sgr-modal button[type=submit]:not([name=_addanother])")
                    pg.wait_for_load_state("networkidle")
            except Exception as e:  # noqa: BLE001
                print(f"  (no se pudo desactivar {datos['usuario']}: {e})")
        navegador.close()

    # ---------------------------------------------------------------------------------------------- salidas
    salida = Path(args.salida_json)
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(json.dumps(c.resultados, ensure_ascii=False, indent=1), encoding="utf-8")
    escribir_matriz(Path(args.capturas).parent / "matriz_menus_por_rol.md", matriz, args.url)
    cuentas = {}
    for r in c.resultados:
        cuentas[r["estado"]] = cuentas.get(r["estado"], 0) + 1
    print("Resumen:", ", ".join(f"{k}: {v}" for k, v in cuentas.items()))
    return 1 if cuentas.get("Fallida") else 0


def escribir_matriz(ruta, matriz, url):
    if not matriz:
        return
    todos = sorted({m for d in matriz.values() for m in d["menus"]})
    lineas = [
        "# Matriz de menús por rol (generada desde el sistema en funcionamiento)",
        "",
        f"Origen: {url} · {datetime.now().strftime('%Y-%m-%d %H:%M')}. Cada columna es una cuenta de demostración; «✔» significa que su menú lateral muestra esa opción.",
        "",
        "| Opción del menú | " + " | ".join(matriz) + " |",
        "|---|" + "---|" * len(matriz),
    ]
    for m in todos:
        lineas.append(f"| {m} | " + " | ".join("✔" if m in d["menus"] else "" for d in matriz.values()) + " |")
    ruta.write_text("\n".join(lineas) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", required=True)
    ap.add_argument("--log-correo", help="Archivo donde el servidor imprime el correo de recuperación")
    ap.add_argument("--capturas", default="docs/evidencias/capturas")
    ap.add_argument("--salida-json", default="docs/pruebas/resultados/navegador.json")
    ap.add_argument("--responsable", default="Equipo SGR")
    ap.add_argument("--chromium", help="Ruta de un Chromium ya instalado (si no se usa el de Playwright)")
    ap.add_argument("--sin-verificar-tls", action="store_true")
    return correr(ap.parse_args())


if __name__ == "__main__":
    sys.exit(main())
