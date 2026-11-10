# Despliegue del SGR en Amazon Linux 2023 (AMI LAMP) con HTTPS

Para una instancia EC2 con Amazon Linux 2023 que ya tiene Apache, PHP, MariaDB y phpMyAdmin (tutorial LAMP de AWS). Los archivos están en `deploy/al2023/`. Los scripts **no se pudieron ejecutar en una cuenta real de AWS** desde el entorno de desarrollo (solo se revisó su sintaxis); la primera ejecución es la prueba real.

## Cómo encaja cada pieza

| Pieza | Para qué |
|---|---|
| Apache (el de la AMI) | Recibe 80 y 443, pone el certificado, sirve `/static/` y `/phpMyAdmin`, y le pasa el resto a Daphne (`/ws/` por WebSocket) |
| Daphne (servicio `sgr`) | Ejecuta Django por ASGI, con HTTP y WebSocket (Apache con PHP no ejecuta Python). Desde la v24 reemplaza a gunicorn |
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
4. **Migrar y arrancar:** `cd /opt/sgr/app && sudo bash deploy/actualizar.sh <rama>`. `actualizar.sh` hace `check --deploy`, `migrate` y `collectstatic` y reinicia el servicio, pero **no ejecuta** `seed_roles` ni `seed_management_types` y no carga datos: un servidor recién migrado queda sin roles. El paso 5 lo resuelve.
5. **Roles, datos y cuentas de prueba:** para la revisión, `cargar_datos_revision` (ver más abajo). Ejecuta por su cuenta `seed_roles` y `seed_management_types`. Si solo se quiere la base mínima y no los datos de revisión: `set -a; . /etc/sgr/sgr.env; set +a; sudo -E -u sgr /opt/sgr/venv/bin/python manage.py seed_roles`, lo mismo con `seed_management_types` y `createsuperuser`. Si la base ya tiene datos (se administra desde phpMyAdmin), no se hace nada.
6. **HTTPS:** `sudo bash deploy/al2023/https_certificado.sh <ip-o-dominio> <correo>`. Con `--prueba` ensaya contra el entorno de pruebas de Let's Encrypt sin tocar el sitio. Deja HTTPS=True, redirige 80 a 443 y crea el temporizador `sgr-certbot.timer`.
7. **Comprobar:** `curl https://<ip-o-dominio>/salud/` y `systemctl list-timers sgr-certbot.timer`. Renovación de ensayo: `sudo /opt/certbot/bin/certbot renew --dry-run`.
8. **Correo de la recuperación de contraseña** (la evaluación exige ver llegar el correo con el enlace; mostrarlo solo en la consola no sirve). Completa `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS` y `DEFAULT_FROM_EMAIL` en `/etc/sgr/sgr.env` (Gmail con contraseña de aplicación, Mailtrap o Amazon SES: datos exactos en el README, sección *Recuperar la contraseña*), reinicia con `sudo systemctl restart sgr` y prueba el envío:
   ```bash
   cd /opt/sgr/app; set -a; . /etc/sgr/sgr.env; set +a
   sudo -E -u sgr /opt/sgr/venv/bin/python manage.py sendtestemail destinatario@ejemplo.cl
   ```
   Luego repite el flujo en el navegador (pedir el enlace, abrirlo, elegir la clave, comprobar que el mismo enlace ya no abre nada). El enlace se arma con la dirección con la que se abre el sitio, así que `ALLOWED_HOSTS` debe tener la IP o el dominio reales y Apache debe conservar el `Host` (`ProxyPreserveHost On`, ya incluido en `apache-http.conf` y `apache-https.conf`). El puerto 25 está bloqueado por defecto en EC2: usa 587 o 2525.

## Datos y cuentas de la revisión

El comando `cargar_datos_revision` carga más de 3.000 registros ficticios en dos ámbitos (Delegación Norte = organización A, Delegación Sur = organización B) y crea las seis cuentas de prueba (`admin_a`, `editor_a`, `lector_a`, `lector_b`, `cliente1` y `cliente2`). Se ejecuta **después de `migrate`** y se puede repetir sin duplicar nada:

```bash
cd /opt/sgr/app; set -a; . /etc/sgr/sgr.env; set +a
read -rs -p "Contraseña de las cuentas de prueba: " SGR_REVISION_PASSWORD; export SGR_REVISION_PASSWORD
sudo -E -u sgr /opt/sgr/venv/bin/python manage.py cargar_datos_revision
unset SGR_REVISION_PASSWORD
```

- Las contraseñas **no están en el repositorio**: se leen de `SGR_REVISION_PASSWORD`, de `SGR_PASSWORD_<ALIAS>` (una sola cuenta), de `--password` o se piden por pantalla. Solo se asignan al crear la cuenta (`--reasignar-claves` las cambia en las existentes).
- Ejecuta antes `seed_roles` y `seed_management_types`, y al final imprime el total por modelo y comprueba los mínimos (2.000 registros y 50 en cada CRUD evaluado) y los permisos de las cuentas; si algo falla, termina con error.
- Después de cada `actualizar.sh` no hace falta volver a cargarlo: `actualizar.sh` no ejecuta ni carga datos, y lo cargado queda en la base.
- `core/datos_prueba.py` es solo para las pruebas automáticas y no se carga en el servidor.
- Se probó con SQLite y con las pruebas automáticas; no se pudo probar contra MariaDB en el entorno de desarrollo. La primera ejecución en la instancia es la prueba real: conviene hacerla (y repetirla, para comprobar que no duplica) **antes** de la revisión.
- Detalle de las cuentas, distribución de los datos y total por modelo: README, sección *Datos y cuentas para la revisión en AWS*. Diagrama de modelos: `docs/DIAGRAMA_MODELOS.md`.

## Notas

- Un certificado para IP exige certbot 5.4 o más y el perfil `shortlived`; el script lo instala en su propio entorno.
- Un solo proceso de Daphne con caché local y capa de canales en memoria (los avisos en vivo solo llegan entre conexiones del mismo proceso), porque la capa de canales en memoria no se comparte entre procesos. Con más procesos hace falta Redis (`CACHE_BACKEND=redis` y `channels_redis`). El tope de enlaces de recuperación por hora sale de la base de datos, así que no depende de la caché.
- phpMyAdmin queda detrás del mismo HTTPS. Para dejarlo solo para tu IP, descomenta el bloque `<Location /phpMyAdmin>` de `/etc/httpd/conf.d/00-sgr.conf`.
- Actualizar: `cd /opt/sgr/app && sudo bash deploy/actualizar.sh <rama-o-etiqueta>`.
- **Pasar un servidor instalado con gunicorn (v11 a v23) a la v24**, una sola vez: `cd /opt/sgr/app && sudo -u sgr git fetch --all && sudo -u sgr git checkout <rama> && sudo bash deploy/al2023/agregar_websocket.sh && sudo bash deploy/actualizar.sh <rama>`. El primer script deja a Apache pasando `/ws/` y cambia el servicio a Daphne; el segundo instala Channels y Daphne y reinicia. Para ver el WebSocket: abre el Dashboard en dos navegadores y mira Network → WS (101 Switching Protocols); al editar una atención en uno, el otro se actualiza solo.
- Daphne no sirve los estáticos: los sirve Apache (`/static/`), como hasta ahora.
