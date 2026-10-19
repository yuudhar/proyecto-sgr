#!/usr/bin/env bash
# Pone al día una instalación existente: baja la versión indicada, instala dependencias, migra, junta los estáticos y
# reinicia el servicio.   Uso (desde /opt/sgr/app):   bash deploy/actualizar.sh entrega-2
set -euo pipefail

VERSION="${1:-main}"
APP_DIR=/opt/sgr/app
PY=/opt/sgr/venv/bin/python

sudo -u sgr git -C "$APP_DIR" fetch --tags --prune
sudo -u sgr git -C "$APP_DIR" checkout "$VERSION"
# Si la versión es una rama (no una etiqueta), la deja al día
sudo -u sgr git -C "$APP_DIR" pull --ff-only 2>/dev/null || true

sudo -u sgr /opt/sgr/venv/bin/pip install -r "$APP_DIR/requirements.txt" -r "$APP_DIR/deploy/requirements-produccion.txt"

# Anota qué versión quedó desplegada (la muestra /salud/)
sudo -u sgr git -C "$APP_DIR" describe --tags --always > /tmp/sgr_commit && sudo install -o sgr -g sgr -m 644 /tmp/sgr_commit "$APP_DIR/COMMIT" && rm -f /tmp/sgr_commit

# Las variables de /etc/sgr/sgr.env se cargan para los comandos de Django
set -a; . /etc/sgr/sgr.env; set +a
cd "$APP_DIR"
# Carpeta de los archivos que suben las personas (evidencias y fotos); no se borra al actualizar
sudo -u sgr mkdir -p "${MEDIA_ROOT:-$APP_DIR/media}"
sudo -E -u sgr "$PY" manage.py check --deploy
sudo -E -u sgr "$PY" manage.py migrate --noinput
sudo -E -u sgr "$PY" manage.py collectstatic --noinput
# Solo la primera vez (datos de demostración y cuentas de prueba):  sudo -E -u sgr $PY manage.py seed_demo_data
sudo systemctl restart sgr
sleep 2
curl -fsS http://127.0.0.1:8000/salud/ -H "Host: ${ALLOWED_HOSTS%%,*}" && echo " <- el servicio responde"
git -C "$APP_DIR" log -1 --format="Versión desplegada: %h %s (%cd)" --date=short
