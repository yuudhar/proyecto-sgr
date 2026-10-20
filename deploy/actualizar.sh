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
sudo systemctl restart sgr
sleep 2
curl -fsS http://127.0.0.1:8000/salud/ -H "Host: ${ALLOWED_HOSTS%%,*}" && echo " <- el servicio responde"
git -C "$APP_DIR" log -1 --format="Versión desplegada: %h %s (%cd)" --date=short
