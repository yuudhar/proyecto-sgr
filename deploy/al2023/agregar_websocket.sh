#!/usr/bin/env bash
# Para un servidor que ya estaba instalado con gunicorn (v11 a v23): deja a Apache pasando los WebSocket
# y cambia el servicio sgr a Daphne. Se puede correr más de una vez.
set -euo pipefail

[ "$(id -u)" -eq 0 ] || { echo "Ejecútalo con sudo: sudo bash $0" >&2; exit 1; }
APP_DIR=/opt/sgr/app
CONF=/etc/httpd/conf.d/00-sgr.conf

[ -f "$CONF" ] || { echo "No existe $CONF: este servidor no se instaló con deploy/al2023/instalar_al2023.sh." >&2; exit 1; }

if grep -q 'ProxyPass /ws/' "$CONF"; then
  echo "Apache ya pasa /ws/ al servicio."
else
  cp -a "$CONF" "$CONF.antes-websocket"
  # Antes de cada «ProxyPass / http://127.0.0.1:8000/» (HTTP y HTTPS) se agrega el paso de /ws/.
  sed -i 's|^\(\s*\)ProxyPass / http://127.0.0.1:8000/|\1ProxyPass /ws/ ws://127.0.0.1:8000/ws/\n\1ProxyPassReverse /ws/ ws://127.0.0.1:8000/ws/\n\1ProxyPass / http://127.0.0.1:8000/|' "$CONF"
  if ! httpd -t; then
    echo "La configuración de Apache no es válida: se deja la anterior." >&2
    cp -a "$CONF.antes-websocket" "$CONF"
    exit 1
  fi
fi

httpd -M 2>/dev/null | grep -q proxy_wstunnel || echo "Aviso: Apache no tiene cargado mod_proxy_wstunnel; sin él los WebSocket no pasan." >&2

cp "$APP_DIR/deploy/sgr.service" /etc/systemd/system/sgr.service
systemctl daemon-reload
systemctl reload httpd
echo "Listo. Ahora: cd $APP_DIR && sudo bash deploy/actualizar.sh <rama>"
