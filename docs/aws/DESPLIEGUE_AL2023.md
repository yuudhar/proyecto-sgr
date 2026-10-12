# Despliegue del SGR en Amazon Linux 2023 (AMI LAMP) con HTTPS

Para una instancia EC2 con Amazon Linux 2023 que ya tiene Apache, PHP, MariaDB y phpMyAdmin (tutorial LAMP de AWS). Los archivos están en `deploy/al2023/`. Los scripts **no se pudieron ejecutar en una cuenta real de AWS** desde el entorno de desarrollo (solo se revisó su sintaxis); la primera ejecución es la prueba real.

## Cómo encaja cada pieza

| Pieza | Para qué |
|---|---|
| Apache (el de la AMI) | Recibe 80 y 443, pone el certificado, sirve `/static/` y `/phpMyAdmin`, y le pasa el resto a gunicorn |
| gunicorn (servicio `sgr`) | Ejecuta Django (Apache con PHP no ejecuta Python) |
| MariaDB 10.11 o más | Base de datos; Django 6.1 no se conecta a la 10.5 que instala el tutorial |
| certbot (en `/opt/certbot`) | Certificado de Let's Encrypt para la IP pública (dura 6 días, se renueva solo) o para un dominio |

Grupo de seguridad: 22 solo desde tu IP; 80 y 443 abiertos. El 3306 no se abre.

## Pasos

1. **MariaDB 10.11** en vez de `mariadb105-server`: `sudo dnf install -y mariadb1011-server`, `sudo systemctl enable --now mariadb`, `sudo mysql_secure_installation`. Si ya estaba la 10.5 y está vacía: `sudo systemctl stop mariadb && sudo dnf remove -y 'mariadb105*' && sudo rm -rf /var/lib/mysql` antes de instalar.
2. **En phpMyAdmin** (pestaña SQL): `CREATE DATABASE sgr_django CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;`, `CREATE USER 'sgr_user'@'localhost' IDENTIFIED BY '<clave>';`, `GRANT ALL PRIVILEGES ON sgr_django.* TO 'sgr_user'@'localhost';`. La clave solo con letras, números, `-` y `_`.
3. **Instalar** (pide la clave del paso 2 y deja `/etc/sgr/sgr.env` con una `SECRET_KEY` nueva):
   ```bash
   git clone -b <rama> --single-branch https://github.com/yuudhar/proyecto-sgr.git && cd proyecto-sgr
   sudo bash deploy/al2023/instalar_al2023.sh https://github.com/yuudhar/proyecto-sgr.git <rama> <ip-o-dominio>
   ```
4. **Migrar y arrancar:** `cd /opt/sgr/app && sudo bash deploy/actualizar.sh <rama>`. Datos de demostración, solo la primera vez: `set -a; . /etc/sgr/sgr.env; set +a; sudo -E -u sgr /opt/sgr/venv/bin/python manage.py seed_demo_data`, y después cambiar las claves de las cuentas (`manage.py changepassword`).
5. **HTTPS:** `sudo bash deploy/al2023/https_certificado.sh <ip-o-dominio> <correo>`. Con `--prueba` ensaya contra el entorno de pruebas de Let's Encrypt sin tocar el sitio. Deja HTTPS=True, redirige 80 a 443 y crea el temporizador `sgr-certbot.timer`.
6. **Comprobar:** `curl https://<ip-o-dominio>/salud/` y `systemctl list-timers sgr-certbot.timer`. Renovación de ensayo: `sudo /opt/certbot/bin/certbot renew --dry-run`.

## Notas

- Un certificado para IP exige certbot 5.4 o más y el perfil `shortlived`; el script lo instala en su propio entorno.
- Un solo proceso de gunicorn con 8 hilos y caché local, para que el contador de intentos de la recuperación de contraseña sea válido. Con más procesos hace falta Redis (`CACHE_BACKEND=redis`).
- phpMyAdmin queda detrás del mismo HTTPS. Para dejarlo solo para tu IP, descomenta el bloque `<Location /phpMyAdmin>` de `/etc/httpd/conf.d/00-sgr.conf`.
- Actualizar: `cd /opt/sgr/app && sudo bash deploy/actualizar.sh <rama-o-etiqueta>`.
