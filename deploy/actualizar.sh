#!/usr/bin/env bash
set -euo pipefail

VERSION="${1:-main}"
APP_DIR=/opt/sgr/app
PY=/opt/sgr/venv/bin/python

sudo -u sgr git -C "$APP_DIR" fetch --tags --prune
sudo -u sgr git -C "$APP_DIR" checkout "$VERSION"
sudo -u sgr git -C "$APP_DIR" pull --ff-only 2>/dev/null || true

sudo -u sgr /opt/sgr/venv/bin/pip install -r "$APP_DIR/requirements.txt" -r "$APP_DIR/deploy/requirements-produccion.txt"

sudo -u sgr git -C "$APP_DIR" describe --tags --always > /tmp/sgr_commit && sudo install -o sgr -g sgr -m 644 /tmp/sgr_commit "$APP_DIR/COMMIT" && rm -f /tmp/sgr_commit

set -a; . /etc/sgr/sgr.env; set +a
cd "$APP_DIR"
sudo -u sgr mkdir -p "${MEDIA_ROOT:-$APP_DIR/media}"
sudo -E -u sgr "$PY" manage.py check --deploy
sudo -E -u sgr "$PY" manage.py migrate --noinput
sudo -E -u sgr "$PY" manage.py collectstatic --noinput
sudo chmod -R a+rX "$APP_DIR/staticfiles"

# Las pantallas en vivo necesitan que Apache pase /ws/ y que el servicio sea Daphne. Si el servidor se instaló antes
# (gunicorn, v11 a v23) y nadie corrió agregar_websocket.sh, no se actualizaban solas: aquí se deja listo siempre.
if [ -f /etc/httpd/conf.d/00-sgr.conf ]; then
  sudo bash "$APP_DIR/deploy/al2023/agregar_websocket.sh" || echo "Aviso: no se pudo dejar a Apache pasando los WebSocket." >&2
else
  sudo install -m 644 "$APP_DIR/deploy/sgr.service" /etc/systemd/system/sgr.service && sudo systemctl daemon-reload
fi

sudo systemctl restart sgr
sleep 2
curl -fsS http://127.0.0.1:8000/salud/ -H "Host: ${ALLOWED_HOSTS%%,*}" && echo " <- el servicio responde"
echo "Prueba del WebSocket:"
python3 "$APP_DIR/deploy/probar_websocket.py" "${ALLOWED_HOSTS%%,*}" || echo "Aviso: las pantallas igual se actualizan, pero cada 8 segundos y no al instante." >&2
git -C "$APP_DIR" log -1 --format="Versión desplegada: %h %s (%cd)" --date=short
