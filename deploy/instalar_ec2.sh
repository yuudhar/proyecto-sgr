#!/usr/bin/env bash
# Primera instalación del SGR en una instancia EC2 con Ubuntu 22.04/24.04.
# Uso (como un usuario con sudo):   bash deploy/instalar_ec2.sh https://github.com/yuudhar/proyecto-sgr.git entrega-2
# El segundo argumento es la etiqueta (tag) o rama de la entrega. Después hay que completar /etc/sgr/sgr.env.
set -euo pipefail

REPO="${1:?Falta la URL del repositorio Git}"
VERSION="${2:-main}"
APP_DIR=/opt/sgr/app

sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip git nginx redis-server
sudo id sgr >/dev/null 2>&1 || sudo useradd --system --create-home --home-dir /opt/sgr --shell /usr/sbin/nologin sgr
sudo mkdir -p /etc/sgr
sudo chown -R sgr:sgr /opt/sgr

if [ ! -d "$APP_DIR/.git" ]; then
  sudo -u sgr git clone "$REPO" "$APP_DIR"
fi
sudo -u sgr git -C "$APP_DIR" fetch --tags --prune
sudo -u sgr git -C "$APP_DIR" checkout "$VERSION"

sudo -u sgr python3 -m venv /opt/sgr/venv
sudo -u sgr /opt/sgr/venv/bin/pip install --upgrade pip
sudo -u sgr /opt/sgr/venv/bin/pip install -r "$APP_DIR/requirements.txt" -r "$APP_DIR/deploy/requirements-produccion.txt"

if [ ! -f /etc/sgr/sgr.env ]; then
  sudo cp "$APP_DIR/deploy/sgr.env.example" /etc/sgr/sgr.env
  sudo chown sgr:sgr /etc/sgr/sgr.env
  sudo chmod 600 /etc/sgr/sgr.env
  echo
  echo ">>> Edita /etc/sgr/sgr.env (SECRET_KEY, ALLOWED_HOSTS, correo...) y luego ejecuta:  bash deploy/actualizar.sh"
  echo ">>> También copia deploy/sgr.service a /etc/systemd/system/ y deploy/nginx-sgr.conf a nginx (ver docs/aws/DESPLIEGUE_AWS.md)."
fi
