#!/usr/bin/env bash
# Primera instalación del SGR en Amazon Linux 2023 (AMI LAMP: Apache, MariaDB y phpMyAdmin).
# Antes: la base y su usuario ya están creados en phpMyAdmin (MariaDB 10.11 o más; ver docs/aws/DESPLIEGUE_AL2023.md).
# Uso (como root):
#   sudo bash deploy/al2023/instalar_al2023.sh <repositorio> <rama-o-etiqueta> <ip-pública-o-dominio>
# Ejemplo:
#   sudo bash deploy/al2023/instalar_al2023.sh https://github.com/yuudhar/proyecto-sgr.git proyecto-sgr-v11 32.198.200.215
set -euo pipefail

[ "$(id -u)" -eq 0 ] || { echo "Ejecútalo con sudo: sudo bash $0 ..." >&2; exit 1; }
REPO="${1:?Falta la URL del repositorio Git}"
VERSION="${2:?Falta la rama o etiqueta a instalar}"
HOST="${3:?Falta la IP pública (o el dominio) con la que se entrará al sitio}"
APP_DIR=/opt/sgr/app
ENV_FILE=/etc/sgr/sgr.env

# fijar CLAVE VALOR: reemplaza la línea CLAVE= de sgr.env (el valor no puede llevar espacios ni «|»).
fijar() { sed -i "s|^$1=.*|$1=$2|" "$ENV_FILE"; }

# Django 6.1 no se conecta a MariaDB 10.5, que es la que instala el tutorial LAMP de AWS (mariadb105-server).
if rpm -q mariadb105-server >/dev/null 2>&1; then
  echo "ERROR: está instalado mariadb105-server (MariaDB 10.5). Django 6.1 pide 10.11 o más: usa mariadb1011-server." >&2
  echo "       Pasos en docs/aws/DESPLIEGUE_AL2023.md, paso 1." >&2
  exit 1
fi
rpm -q mariadb1011-server >/dev/null 2>&1 || echo "Aviso: no hay mariadb1011-server en este equipo (¿la base está en otro servidor?). Debe ser MariaDB 10.11 o MySQL 8.4 como mínimo."

dnf install -y git gcc pkgconf-pkg-config python3.13 python3.13-devel mariadb1011-devel httpd mod_ssl || {
  echo "Si dnf dice «No match for argument», la imagen es antigua: sudo dnf upgrade --releasever=latest y vuelve a correr este script." >&2
  exit 1
}

id sgr >/dev/null 2>&1 || useradd --system --create-home --home-dir /opt/sgr --shell /usr/sbin/nologin sgr
mkdir -p /etc/sgr /var/www/acme/.well-known/acme-challenge
chown -R sgr:sgr /opt/sgr

if [ ! -d "$APP_DIR/.git" ]; then
  sudo -u sgr git clone "$REPO" "$APP_DIR"
fi
sudo -u sgr git -C "$APP_DIR" fetch --tags --prune
sudo -u sgr git -C "$APP_DIR" checkout "$VERSION"
sudo -u sgr git -C "$APP_DIR" pull --ff-only 2>/dev/null || true

sudo -u sgr python3.13 -m venv /opt/sgr/venv
sudo -u sgr /opt/sgr/venv/bin/pip install --upgrade pip
sudo -u sgr /opt/sgr/venv/bin/pip install -r "$APP_DIR/requirements.txt" -r "$APP_DIR/deploy/requirements-produccion.txt"
sudo -u sgr /opt/sgr/venv/bin/pip install mysqlclient

# Apache corre como «apache» y tiene que poder llegar a los archivos estáticos (el home de sgr es 700 por defecto).
chmod 711 /opt/sgr
chmod 755 "$APP_DIR"

if [ ! -f "$ENV_FILE" ]; then
  cp "$APP_DIR/deploy/al2023/sgr.env.example" "$ENV_FILE"
  chown sgr:sgr "$ENV_FILE"
  chmod 600 "$ENV_FILE"
  fijar SECRET_KEY "$(python3.13 -c 'import secrets; print(secrets.token_urlsafe(64))')"
  fijar ALLOWED_HOSTS "$HOST"
  fijar CSRF_TRUSTED_ORIGINS "http://$HOST"
  if [ -t 0 ]; then
    read -r -s -p "Clave del usuario sgr_user de MariaDB (la que pusiste en phpMyAdmin): " CLAVE_BD; echo
    [[ "$CLAVE_BD" =~ ^[A-Za-z0-9_-]{8,}$ ]] || { echo "La clave debe tener 8 o más letras, números, - o _ (sin otros símbolos). Complétala a mano en $ENV_FILE." >&2; CLAVE_BD=""; }
    [ -z "$CLAVE_BD" ] || fijar DB_PASSWORD "$CLAVE_BD"
  else
    echo "Completa DB_PASSWORD en $ENV_FILE."
  fi
fi

cp "$APP_DIR/deploy/sgr.service" /etc/systemd/system/sgr.service
systemctl daemon-reload
systemctl enable sgr

sed "s|__HOST__|$HOST|g" "$APP_DIR/deploy/al2023/apache-http.conf" > /etc/httpd/conf.d/00-sgr.conf
httpd -t
systemctl enable --now httpd
systemctl reload httpd

cat <<MSG

Listo la primera parte. Siguen, en este orden:
  1) cd $APP_DIR && sudo bash deploy/actualizar.sh $VERSION        (migra, junta los estáticos y arranca el servicio)
  2) Solo la primera vez, los datos de demostración:
       set -a; . $ENV_FILE; set +a; sudo -E -u sgr /opt/sgr/venv/bin/python manage.py seed_demo_data
  3) HTTP ya funciona en http://$HOST/ ; para HTTPS:
       sudo bash deploy/al2023/https_certificado.sh $HOST tu-correo@ejemplo.cl
MSG
