#!/usr/bin/env bash
# Activa HTTPS en Amazon Linux 2023: pide el certificado a Let's Encrypt, pone el sitio en el puerto 443, manda el 80 al 443
# y deja la renovación automática. Funciona con una IP pública (certificado de 6 días, se renueva solo) o con un dominio.
# Antes: instalar_al2023.sh ya corrió y el grupo de seguridad deja abiertos los puertos 80 y 443.
# Uso (como root):
#   sudo bash deploy/al2023/https_certificado.sh <ip-o-dominio> <correo> [--prueba]
# Con --prueba usa el entorno de ensayo de Let's Encrypt (certificado no confiable, sin límites) y no cambia el sitio.
set -euo pipefail

[ "$(id -u)" -eq 0 ] || { echo "Ejecútalo con sudo: sudo bash $0 ..." >&2; exit 1; }
HOST="${1:?Falta la IP pública o el dominio}"
CORREO="${2:?Falta un correo para los avisos del certificado}"
PRUEBA="${3:-}"
APP_DIR=/opt/sgr/app
ENV_FILE=/etc/sgr/sgr.env
WEBROOT=/var/www/acme
CERTBOT=/opt/certbot/bin/certbot

fijar() { sed -i "s|^$1=.*|$1=$2|" "$ENV_FILE"; }

if [[ "$HOST" =~ ^[0-9]{1,3}(\.[0-9]{1,3}){3}$ ]]; then ES_IP=1; else ES_IP=0; fi

# certbot 5.4 o más: es la primera versión que entrega certificados para IP con --webroot.
if [ ! -x "$CERTBOT" ]; then
  python3.13 -m venv /opt/certbot
  /opt/certbot/bin/pip install --upgrade pip 'certbot>=5.4,<6'
fi

NOMBRE="$HOST"; [ "$PRUEBA" = "--prueba" ] && NOMBRE="$HOST-prueba"
ARGS=(certonly --non-interactive --agree-tos -m "$CORREO" --webroot -w "$WEBROOT" --cert-name "$NOMBRE" --deploy-hook "systemctl reload httpd")
if [ "$ES_IP" -eq 1 ]; then ARGS+=(--ip-address "$HOST" --preferred-profile shortlived); else ARGS+=(-d "$HOST"); fi
[ "$PRUEBA" = "--prueba" ] && ARGS+=(--staging)
"$CERTBOT" "${ARGS[@]}"

if [ "$PRUEBA" = "--prueba" ]; then
  echo "El ensayo con Let's Encrypt funcionó. Repite sin --prueba para el certificado de verdad."
  exit 0
fi

cp /etc/httpd/conf.d/00-sgr.conf /etc/httpd/conf.d/00-sgr.conf.antes
sed "s|__HOST__|$HOST|g" "$APP_DIR/deploy/al2023/apache-https.conf" > /etc/httpd/conf.d/00-sgr.conf
if ! httpd -t; then
  cp /etc/httpd/conf.d/00-sgr.conf.antes /etc/httpd/conf.d/00-sgr.conf
  echo "La configuración de Apache falló; quedó la anterior." >&2
  exit 1
fi
rm -f /etc/httpd/conf.d/00-sgr.conf.antes   # un .conf.antes en conf.d no se lee, pero así no queda basura
systemctl reload httpd

fijar HTTPS True
fijar CSRF_TRUSTED_ORIGINS "https://$HOST"
systemctl restart sgr

# Renovación: dos veces al día; certbot renueva solo cuando toca (los certificados de IP duran 6 días).
RENOVAR="$CERTBOT renew --quiet"
[ "$ES_IP" -eq 1 ] && RENOVAR="$RENOVAR --preferred-profile shortlived"
cat > /etc/systemd/system/sgr-certbot.service <<UNIT
[Unit]
Description=Renovar el certificado de Let's Encrypt del SGR

[Service]
Type=oneshot
ExecStart=$RENOVAR
UNIT
cat > /etc/systemd/system/sgr-certbot.timer <<UNIT
[Unit]
Description=Revisar dos veces al día si el certificado del SGR necesita renovarse

[Timer]
OnCalendar=*-*-* 03,15:23:00
RandomizedDelaySec=900
Persistent=true

[Install]
WantedBy=timers.target
UNIT
systemctl daemon-reload
systemctl enable --now sgr-certbot.timer

sleep 2
curl -fsS --max-time 20 "https://$HOST/salud/" && echo " <- https://$HOST/ responde"
echo "Renovación automática: systemctl list-timers sgr-certbot.timer   (prueba: sudo $CERTBOT renew --dry-run)"
