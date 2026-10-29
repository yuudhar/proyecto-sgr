#!/usr/bin/env python3
"""Prueba de verdad si el WebSocket llega a Daphne, directo y a través de Apache.

Uso: python3 deploy/probar_websocket.py <host> [puerto-directo]
Hace un «handshake» a /ws/live/ sin sesión. Daphne responde 101 (acepta) o «403 Access denied» (rechaza por no haber sesión):
las dos respuestas prueban que la ruta llega a la aplicación. Cualquier otra cosa (404, 502,
200 con HTML, sin respuesta) significa que Apache o el servicio no están dejando pasar los WebSocket.
Termina con código 0 si todo pasa, 1 si algo falla. Solo usa la biblioteca estándar.
"""
import base64
import os
import socket
import ssl
import sys


def handshake(host, port, use_tls, header_host, origin, path="/ws/live/"):
    key = base64.b64encode(os.urandom(16)).decode()
    request = (
        f"GET {path} HTTP/1.1\r\nHost: {header_host}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\nOrigin: {origin}\r\n\r\n"
    )
    raw = socket.create_connection((host, port), timeout=8)
    conn = ssl.create_default_context().wrap_socket(raw, server_hostname=header_host) if use_tls else raw
    try:
        conn.sendall(request.encode())
        data = b""
        while b"\r\n\r\n" not in data and len(data) < 8192:
            chunk = conn.recv(2048)
            if not chunk:
                break
            data += chunk
    finally:
        conn.close()
    head = data.decode("latin-1", "replace").split("\r\n\r\n")[0]
    lines = head.split("\r\n")
    status = lines[0] if lines and lines[0] else "(sin respuesta)"
    return status, head.lower()


def reaches_daphne(status, head):
    # Sin sesión, Daphne rechaza con «403 Access denied» (Apache diría «Forbidden»).
    return " 101 " in status or (" 403 " in status and ("access denied" in status.lower() or "daphne" in head))


def check(name, host, port, use_tls, header_host, origin):
    try:
        status, head = handshake(host, port, use_tls, header_host, origin)
    except (OSError, ssl.SSLError) as error:
        print(f"  [FALLA] {name}: no se pudo conectar ({error})")
        return False
    good = reaches_daphne(status, head)
    print(f"  [{'OK' if good else 'FALLA'}] {name}: {status}")
    return good


def main():
    host = sys.argv[1] if len(sys.argv) > 1 else "localhost"
    direct = int(sys.argv[2]) if len(sys.argv) > 2 else 8000
    ok_direct = check("Daphne directo (127.0.0.1:%d)" % direct, "127.0.0.1", direct, False, host, f"https://{host}")
    results = [ok_direct]
    for port, tls in ((443, True), (80, False)):
        try:
            status, head = handshake(host, port, tls, host, f"{'https' if tls else 'http'}://{host}")
        except (OSError, ssl.SSLError):
            continue
        if " 301 " in status or " 302 " in status:
            print(f"  [--] Apache en el puerto {port}: redirige a HTTPS (normal), se prueba el 443.")
            continue
        good = reaches_daphne(status, head)
        print(f"  [{'OK' if good else 'FALLA'}] Apache puerto {port}: {status}")
        results.append(good)
        break
    if all(results):
        print("WebSocket OK: las pantallas se actualizan solas.")
        return 0
    print("El WebSocket NO está llegando completo. Revisa:")
    if not ok_direct:
        print("  - El servicio sgr debe correr Daphne:  systemctl cat sgr | grep ExecStart  (debe decir daphne, no gunicorn)")
    print("  - Apache debe pasar /ws/:  grep -n 'ProxyPass /ws/' /etc/httpd/conf.d/00-sgr.conf")
    print("  - Y tener el módulo:  httpd -M | grep proxy_wstunnel")
    print("  Corrige con:  sudo bash deploy/al2023/agregar_websocket.sh && sudo bash deploy/actualizar.sh <rama>")
    return 1


if __name__ == "__main__":
    sys.exit(main())
