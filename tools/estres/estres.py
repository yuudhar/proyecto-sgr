#!/usr/bin/env python3
"""Pruebas de estrés del SGR: concurrencia creciente sobre las operaciones integradas.

Solo usa la biblioteca estándar de Python (no hay que instalar nada). Ejemplos:

    # Ensayo local (servidor de desarrollo o gunicorn en tu equipo):
    python tools/estres/estres.py --url http://127.0.0.1:8000 --etapas 1,2,5,10,20 --duracion 20 --medir-local

    # Prueba definitiva contra AWS (etapas de 60 s):
    python tools/estres/estres.py --url https://tu-sitio --etapas 1,5,10,20,40,60,80 --duracion 60 \\
        --entorno "EC2 t3.small, gunicorn 4x2, SQLite, Redis local"

Cada «usuario virtual» ingresa una vez y luego repite, sin pausa (o con --pausa segundos), una mezcla de operaciones:
dashboard, búsqueda en Atención, listados con búsqueda, ficha, exportación a Excel y, con --escritura, el registro de
una atención (deja filas con el contacto «[ESTRES]»; se borran con `manage.py cargar_volumen_estres --limpiar`
si se cargó volumen, o desde Atención). Termina con una etapa de recuperación a 1 usuario.

Escribe, en --salida: estres_<fecha>.json, estres_<fecha>.csv y estres_<fecha>.md. Los umbrales de aceptación se fijan
ANTES de probar (ver docs/pruebas/estres/PLAN_ESTRES.md) y se pasan con --umbral-p95 y --umbral-errores.
"""

import argparse
import csv
import http.cookiejar
import json
import math
import os
import re
import statistics
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

ESCENARIO = [
    # (nombre, método, ruta, peso, categoría)
    ("Dashboard", "GET", "/dashboard/", 20, "lectura"),
    ("Atención: últimas", "GET", "/atencion/", 15, "lectura"),
    ("Atención: búsqueda", "GET", "/atencion/?q=Rosa", 15, "lectura"),
    ("Listado de atenciones", "GET", "/actividades/", 15, "lectura"),
    ("Listado con búsqueda y página 2", "GET", "/actividades/?q=visita&page=2", 10, "lectura"),
    ("Listado de funcionarios", "GET", "/funcionarios/", 4, "lectura"),
    ("Listado de territorios", "GET", "/territorios/", 4, "lectura"),
    ("Mi perfil", "GET", "/perfil/", 5, "lectura"),
    ("Exportar atenciones a Excel", "GET", "/actividades/?formato=xlsx", 4, "exportación"),
]
# Perfil «admin»: recorre los mantenedores del A1 (necesita una cuenta de Super Usuario)
ESCENARIO_ADMIN = [
    ("Dashboard", "GET", "/dashboard/", 10, "lectura"),
    ("CRUD Delegaciones: listado", "GET", "/delegaciones/", 10, "lectura"),
    ("CRUD Delegaciones: búsqueda", "GET", "/delegaciones/?q=serena", 8, "lectura"),
    ("CRUD Roles: listado", "GET", "/roles/", 10, "lectura"),
    ("CRUD Usuarios: listado", "GET", "/usuarios/", 12, "lectura"),
    ("CRUD Usuarios: búsqueda", "GET", "/usuarios/?q=matias", 8, "lectura"),
    ("CRUD Ítems y metas: listado", "GET", "/items/", 10, "lectura"),
    ("CRUD Ítems y metas: búsqueda", "GET", "/items/?q=visita", 6, "lectura"),
    ("Atención: búsqueda", "GET", "/atencion/?q=Rosa", 10, "lectura"),
    ("Exportar usuarios a Excel", "GET", "/usuarios/?formato=xlsx", 3, "exportación"),
    ("Exportar ítems a Excel", "GET", "/items/?formato=xlsx", 3, "exportación"),
]
ESCRITURA = ("Registrar atención", "POST", "/actividades/nuevo/", 10, "escritura")


def percentil(valores, p):
    if not valores:
        return 0.0
    orden = sorted(valores)
    k = max(0, min(len(orden) - 1, math.ceil(p / 100 * len(orden)) - 1))
    return orden[k]


class Usuario(threading.Thread):
    """Un usuario virtual con su propia sesión."""

    def __init__(self, base, usuario, clave, escenario, fin, pausa, medidas, verificar_tls, escritura, listo, salida):
        super().__init__(daemon=True)
        self.base, self.usuario, self.clave = base.rstrip("/"), usuario, clave
        self.escenario, self.fin, self.pausa, self.medidas = escenario, fin, pausa, medidas
        self.listo, self.salida = listo, salida  # listo: este usuario ya ingresó; salida: se puede empezar a medir
        self.escritura = escritura
        jar = http.cookiejar.CookieJar()
        handlers = [urllib.request.HTTPCookieProcessor(jar)]
        if not verificar_tls:
            import ssl

            contexto = ssl.create_default_context()
            contexto.check_hostname = False
            contexto.verify_mode = ssl.CERT_NONE
            handlers.append(urllib.request.HTTPSHandler(context=contexto))
        self.opener = urllib.request.build_opener(*handlers)
        self.jar = jar
        self.azar = __import__("random").Random()

    def pedir(self, metodo, ruta, datos=None, cabeceras=None):
        url = self.base + ruta
        cuerpo = urllib.parse.urlencode(datos).encode() if datos is not None else None
        pedido = urllib.request.Request(url, data=cuerpo, method=metodo, headers=cabeceras or {})
        if cuerpo is not None:
            pedido.add_header("Referer", self.base + "/")
        inicio = time.perf_counter()
        try:
            with self.opener.open(pedido, timeout=60) as r:
                contenido = r.read()
                estado = r.status
        except urllib.error.HTTPError as e:
            contenido, estado = e.read(), e.code
        except Exception as e:  # conexión rechazada, tiempo agotado...
            return 0, (time.perf_counter() - inicio) * 1000, b"", str(e)
        return estado, (time.perf_counter() - inicio) * 1000, contenido, ""

    def token(self):
        for c in self.jar:
            if c.name == "csrftoken":
                return c.value
        return ""

    def ingresar(self):
        estado, _, html, err = self.pedir("GET", "/")
        if estado != 200:
            return False
        token = self.token()
        estado, _, html, err = self.pedir(
            "POST", "/", {"username": self.usuario, "password": self.clave, "csrfmiddlewaretoken": token}
        )
        return estado == 200 and any(c.name == "sessionid" for c in self.jar)

    def datos_atencion(self):
        """Lee el formulario de «Registrar atención» y arma un envío válido (primer tipo con sub atención o sin ella)."""
        estado, _, html, _ = self.pedir("GET", "/actividades/nuevo/")
        if estado != 200:
            return None
        texto = html.decode("utf-8", "replace")
        token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', texto)
        tipos = re.search(r'<select[^>]*name="attention_type"[^>]*>(.*?)</select>', texto, re.S)
        subs = re.search(r'<select[^>]*name="item"[^>]*>(.*?)</select>', texto, re.S)
        if not (token and tipos):
            return None
        opciones_tipo = re.findall(r'<option value="(\d+)"', tipos.group(1))
        datos = {
            "csrfmiddlewaretoken": token.group(1),
            "requester": "[ESTRES] Persona de prueba",
            "attention_type": opciones_tipo[0] if opciones_tipo else "",
            "request_description": "Atención creada por la prueba de estrés.",
        }
        if subs:
            for valor, atributos in re.findall(r'<option value="(\d+)"([^>]*)>', subs.group(1)):
                m = re.search(r'data-(?:type|parent|tipo)="(\d+)"', atributos)
                if m and m.group(1) == datos["attention_type"]:
                    datos["item"] = valor
                    break
        return datos

    def run(self):
        # El ingreso (que cuesta CPU por el cifrado de la contraseña) se hace antes de medir: no cuenta en la etapa.
        entro = self.ingresar()
        self.listo.set()
        self.salida.wait()
        if not entro:
            self.medidas.append(("Ingreso", 0, 0.0, time.time(), "no se pudo ingresar"))
            return
        pesos = [e[3] for e in self.escenario]
        while time.time() < self.fin[0]:
            nombre, metodo, ruta, _, _ = self.azar.choices(self.escenario, weights=pesos)[0]
            if metodo == "POST":
                datos = self.datos_atencion()
                if datos is None:
                    estado, ms, err = 0, 0.0, "no se pudo leer el formulario"
                    self.medidas.append((nombre, estado, ms, time.time(), err))
                    continue
                estado, ms, _, err = self.pedir("POST", ruta, datos)
                # Un envío bueno redirige (302) y urllib lo sigue hasta una página 200.
            else:
                estado, ms, _, err = self.pedir("GET", ruta)
            self.medidas.append((nombre, estado, ms, time.time(), err))
            if self.pausa:
                time.sleep(self.pausa)


def leer_local():
    """Carga del equipo (solo Linux): carga promedio de 1 minuto y memoria disponible en %."""
    try:
        carga = float(Path("/proc/loadavg").read_text().split()[0])
        memoria = {l.split(":")[0]: int(l.split()[1]) for l in Path("/proc/meminfo").read_text().splitlines()}
        usada = 100 - 100 * memoria["MemAvailable"] / memoria["MemTotal"]
        return carga, round(usada, 1)
    except Exception:
        return None, None


def cpu_local():
    """Porcentaje de CPU del equipo entre dos lecturas de /proc/stat (solo Linux)."""
    def leer():
        partes = [int(x) for x in Path("/proc/stat").read_text().splitlines()[0].split()[1:]]
        return sum(partes), partes[3] + partes[4]
    try:
        t1, i1 = leer()
        return lambda: round(100 * (1 - (leer()[1] - i1) / max(1, leer()[0] - t1)), 1)
    except Exception:
        return lambda: None


def etapa(args, concurrencia, duracion, escenario):
    medidas = []
    fin = [0.0]
    salida = threading.Event()
    usuarios = [
        Usuario(args.url, args.usuario, args.clave, escenario, fin, args.pausa, medidas, not args.sin_verificar_tls, args.escritura, threading.Event(), salida)
        for _ in range(concurrencia)
    ]
    for u in usuarios:
        u.start()
    for u in usuarios:  # todos ingresan primero; la medición parte cuando el último está listo
        u.listo.wait(timeout=180)
    time.sleep(1)
    cpu = cpu_local() if args.medir_local else (lambda: None)
    inicio = time.time()
    fin[0] = inicio + duracion
    salida.set()
    maxima_carga = maxima_mem = 0.0
    while any(u.is_alive() for u in usuarios):
        time.sleep(1)
        if args.medir_local:
            carga, mem = leer_local()
            maxima_carga, maxima_mem = max(maxima_carga, carga or 0), max(maxima_mem, mem or 0)
    for u in usuarios:
        u.join()
    transcurrido = time.time() - inicio
    pedidos = [m for m in medidas if m[0] != "Ingreso"]
    fallos_ingreso = sum(1 for m in medidas if m[0] == "Ingreso")
    lat = [m[2] for m in pedidos if m[1]]
    errores = sum(1 for m in pedidos if m[1] == 0 or m[1] >= 400) + fallos_ingreso
    por_escenario = {}
    for nombre, estado, ms, _, _ in pedidos:
        por_escenario.setdefault(nombre, []).append((estado, ms))
    detalle = {
        n: {
            "solicitudes": len(v),
            "promedio_ms": round(statistics.fmean(ms for _, ms in v), 1),
            "p95_ms": round(percentil([ms for _, ms in v], 95), 1),
            "errores": sum(1 for e, _ in v if e == 0 or e >= 400),
        }
        for n, v in por_escenario.items()
    }
    total = len(pedidos)
    return {
        "concurrencia": concurrencia,
        "duracion_s": round(transcurrido, 1),
        "solicitudes": total,
        "rps": round(total / transcurrido, 2) if transcurrido else 0,
        "promedio_ms": round(statistics.fmean(lat), 1) if lat else 0,
        "p50_ms": round(percentil(lat, 50), 1),
        "p95_ms": round(percentil(lat, 95), 1),
        "p99_ms": round(percentil(lat, 99), 1),
        "max_ms": round(max(lat), 1) if lat else 0,
        "errores": errores,
        "errores_pct": round(100 * errores / max(1, total + fallos_ingreso), 2),
        "cpu_pct": cpu(),
        "carga_max": maxima_carga or None,
        "memoria_usada_pct_max": maxima_mem or None,
        "por_escenario": detalle,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", required=True, help="Dirección base del sitio, por ejemplo http://127.0.0.1:8000")
    ap.add_argument("--perfil", choices=("funcionario", "admin"), default="funcionario", help="Mezcla de operaciones: funcionario (atención diaria) o admin (mantenedores)")
    ap.add_argument("--usuario", help="Cuenta de prueba (por defecto matias.cavieres, o admin con --perfil admin)")
    ap.add_argument("--clave", default=os.environ.get("ESTRES_CLAVE", "Hola123!"), help="Contraseña (o variable ESTRES_CLAVE)")
    ap.add_argument("--etapas", default="1,2,5,10,20,40", help="Concurrencia de cada etapa, separada por comas")
    ap.add_argument("--duracion", type=int, default=30, help="Segundos por etapa")
    ap.add_argument("--pausa", type=float, default=0.0, help="Segundos de espera entre solicitudes de cada usuario")
    ap.add_argument("--escritura", action="store_true", help="Incluye el registro de atenciones (escribe en la base)")
    ap.add_argument("--umbral-p95", type=float, default=1500.0, help="p95 máximo aceptado, en milisegundos")
    ap.add_argument("--umbral-errores", type=float, default=1.0, help="Porcentaje máximo de errores aceptado")
    ap.add_argument("--medir-local", action="store_true", help="Mide CPU y memoria del equipo donde corre el servidor (mismo equipo)")
    ap.add_argument("--sin-verificar-tls", action="store_true", help="No verifica el certificado HTTPS (solo para ensayos)")
    ap.add_argument("--entorno", default="", help="Descripción del entorno que se está probando (queda en el informe)")
    ap.add_argument("--herramienta", default="tools/estres/estres.py (Python, biblioteca estándar)")
    ap.add_argument("--salida", default="docs/pruebas/estres", help="Carpeta de los resultados")
    args = ap.parse_args()

    args.usuario = args.usuario or ("admin" if args.perfil == "admin" else "matias.cavieres")
    escenario = list(ESCENARIO_ADMIN if args.perfil == "admin" else ESCENARIO) + ([ESCRITURA] if args.escritura and args.perfil != "admin" else [])
    etapas = [int(x) for x in args.etapas.split(",") if x.strip()]
    sello = datetime.now().strftime("%Y-%m-%d_%H%M")
    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)

    print(f"Estrés sobre {args.url} · etapas {etapas} · {args.duracion} s cada una · umbrales p95 ≤ {args.umbral_p95} ms, errores ≤ {args.umbral_errores}%")
    resultados = []
    for c in etapas:
        r = etapa(args, c, args.duracion, escenario)
        r["cumple"] = r["p95_ms"] <= args.umbral_p95 and r["errores_pct"] <= args.umbral_errores and r["solicitudes"] > 0
        resultados.append(r)
        print(
            f"  {c:>3} usuarios: {r['solicitudes']:>6} solicitudes · {r['rps']:>7.1f} req/s · prom {r['promedio_ms']:>7.1f} ms · "
            f"p95 {r['p95_ms']:>7.1f} ms · errores {r['errores']} ({r['errores_pct']}%) · {'CUMPLE' if r['cumple'] else 'NO CUMPLE'}"
        )

    print("  Recuperación: 1 usuario durante 15 s…")
    time.sleep(3)
    recup = etapa(args, 1, 15, escenario)
    base = resultados[0] if resultados else None
    recup["recuperado"] = bool(base) and recup["errores"] == 0 and recup["p95_ms"] <= max(args.umbral_p95, 1.5 * base["p95_ms"])
    print(f"  Recuperación: p95 {recup['p95_ms']} ms, errores {recup['errores']} → {'RECUPERADO' if recup['recuperado'] else 'NO RECUPERADO'}")

    cumplen = [r for r in resultados if r["cumple"]]
    primera_mala = next((r for r in resultados if not r["cumple"]), None)
    informe = {
        "fecha": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "url": args.url,
        "herramienta": args.herramienta,
        "entorno": args.entorno or "(no indicado)",
        "usuario": args.usuario,
        "umbrales": {"p95_ms": args.umbral_p95, "errores_pct": args.umbral_errores},
        "mezcla": [{"escenario": e[0], "peso": e[3], "tipo": e[4]} for e in escenario],
        "etapas": resultados,
        "recuperacion": recup,
        "limite_seguro_usuarios": max((r["concurrencia"] for r in cumplen), default=0),
        "primera_etapa_con_degradacion": primera_mala["concurrencia"] if primera_mala else None,
    }
    (salida / f"estres_{sello}.json").write_text(json.dumps(informe, ensure_ascii=False, indent=1), encoding="utf-8")
    with open(salida / f"estres_{sello}.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["Concurrencia", "Duración (s)", "Solicitudes", "Req/s", "Prom. (ms)", "p50 (ms)", "p95 (ms)", "p99 (ms)", "Máx (ms)", "Errores", "Errores %", "CPU %", "Carga máx", "Mem. usada % máx", "Veredicto"])
        for r in resultados:
            w.writerow([r["concurrencia"], r["duracion_s"], r["solicitudes"], r["rps"], r["promedio_ms"], r["p50_ms"], r["p95_ms"], r["p99_ms"], r["max_ms"], r["errores"], r["errores_pct"], r["cpu_pct"], r["carga_max"], r["memoria_usada_pct_max"], "Cumple" if r["cumple"] else "No cumple"])
    escribir_md(salida / f"estres_{sello}.md", informe)
    print(f"\nLímite seguro (cumple umbrales): {informe['limite_seguro_usuarios']} usuarios · primera degradación: {informe['primera_etapa_con_degradacion']}")
    print(f"Resultados en {salida}/estres_{sello}.(json|csv|md)")
    return 0


def escribir_md(ruta, inf):
    lineas = [
        f"# Resultado de la prueba de estrés · {inf['fecha']}",
        "",
        f"- **Dirección probada:** {inf['url']}",
        f"- **Entorno:** {inf['entorno']}",
        f"- **Herramienta:** {inf['herramienta']}",
        f"- **Cuenta usada:** {inf['usuario']}",
        f"- **Umbrales de aceptación (fijados antes de probar):** p95 ≤ {inf['umbrales']['p95_ms']} ms · errores ≤ {inf['umbrales']['errores_pct']} %",
        "",
        "## Mezcla de operaciones",
        "",
        "| Operación | Peso | Tipo |",
        "|---|---|---|",
        *[f"| {m['escenario']} | {m['peso']} | {m['tipo']} |" for m in inf["mezcla"]],
        "",
        "## Resultados por etapa de concurrencia",
        "",
        "| Usuarios | Duración (s) | Solicitudes | Req/s | Prom. (ms) | p95 (ms) | p99 (ms) | Errores | CPU % | Mem. usada % | Veredicto |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for r in inf["etapas"]:
        lineas.append(
            f"| {r['concurrencia']} | {r['duracion_s']} | {r['solicitudes']} | {r['rps']} | {r['promedio_ms']} | {r['p95_ms']} | {r['p99_ms']} | "
            f"{r['errores']} ({r['errores_pct']} %) | {r['cpu_pct'] if r['cpu_pct'] is not None else 'n/d'} | "
            f"{r['memoria_usada_pct_max'] if r['memoria_usada_pct_max'] is not None else 'n/d'} | {'Cumple' if r['cumple'] else 'No cumple'} |"
        )
    rec = inf["recuperacion"]
    lineas += [
        "",
        f"**Recuperación (1 usuario tras la carga máxima):** p95 {rec['p95_ms']} ms, {rec['errores']} errores → "
        f"{'recuperado' if rec['recuperado'] else 'NO recuperado'}.",
        "",
        f"**Límite seguro observado:** {inf['limite_seguro_usuarios']} usuarios concurrentes. "
        f"**Primera etapa con degradación:** {inf['primera_etapa_con_degradacion'] or 'ninguna dentro del rango probado'}.",
        "",
        "CPU y memoria: «n/d» significa que no se midieron desde la herramienta (en AWS se toman de CloudWatch: CPUUtilization y, con el agente, mem_used_percent).",
        "",
        "## Detalle por operación (última etapa)",
        "",
        "| Operación | Solicitudes | Prom. (ms) | p95 (ms) | Errores |",
        "|---|---:|---:|---:|---:|",
        *[f"| {n} | {d['solicitudes']} | {d['promedio_ms']} | {d['p95_ms']} | {d['errores']} |" for n, d in inf["etapas"][-1]["por_escenario"].items()],
        "",
    ]
    ruta.write_text("\n".join(lineas), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
