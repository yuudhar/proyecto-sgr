#!/usr/bin/env bash
# Deja listo el respaldo diario: instala el temporizador de systemd, la carpeta de respaldos y hace uno de inmediato.
# Se puede correr las veces que haga falta (actualizar.sh lo corre en cada despliegue).
set -euo pipefail

APP_DIR=/opt/sgr/app
PY=/opt/sgr/venv/bin/python

set -a; . /etc/sgr/sgr.env; set +a
BACKUP_DIR="${BACKUP_DIR:-/opt/sgr/respaldos}"

# El volcado de MariaDB lo hace mysqldump, que viene en el cliente de MariaDB.
if [ "${DB_ENGINE:-sqlite}" != "sqlite" ] && ! command -v mysqldump >/dev/null 2>&1; then
  dnf install -y mariadb105
fi

install -d -o sgr -g sgr -m 700 "$BACKUP_DIR"
install -m 644 "$APP_DIR/deploy/sgr-respaldo.service" /etc/systemd/system/sgr-respaldo.service
install -m 644 "$APP_DIR/deploy/sgr-respaldo.timer" /etc/systemd/system/sgr-respaldo.timer
systemctl daemon-reload
systemctl enable --now sgr-respaldo.timer

# Si la carpeta de respaldos no es la de siempre, el servicio tiene que verla en su .env: se avisa en vez de adivinar.
if ! grep -q '^BACKUP_DIR=' /etc/sgr/sgr.env && [ "$BACKUP_DIR" != "/opt/sgr/respaldos" ]; then
  echo "Aviso: define BACKUP_DIR=$BACKUP_DIR en /etc/sgr/sgr.env para que el temporizador use esa carpeta." >&2
fi

# Primer respaldo ahora, para comprobar que funciona (si falla, el despliegue lo muestra).
sudo -E -u sgr env BACKUP_DIR="$BACKUP_DIR" "$PY" "$APP_DIR/manage.py" respaldar
systemctl list-timers sgr-respaldo.timer --no-pager | head -3
