# Despliegue del SGR en AWS

Guía para dejar el SGR funcionando en una instancia EC2 y para actualizarlo. Todo lo que se menciona está en la carpeta `deploy/` del repositorio. Los pasos se escribieron y se verificaron en un entorno Linux equivalente (gunicorn, Redis local, colección de estáticos, `/salud/`), pero **no se ejecutaron en una cuenta real de AWS**: el despliegue y su URL los debe hacer el equipo (ver «Qué falta por hacer»).

## 1. Servicios y componentes

| Componente | Servicio AWS / programa | Para qué |
|---|---|---|
| Servidor | EC2 (Ubuntu 22.04/24.04; t3.small o superior) | Ejecuta la aplicación |
| Aplicación | Django 6 + gunicorn (`deploy/gunicorn.conf.py`) bajo systemd (`deploy/sgr.service`) | Sirve el portal |
| Proxy web | nginx (`deploy/nginx-sgr.conf`) | Recibe el tráfico en 80/443, sirve `/static/` y traspasa el resto a gunicorn |
| Base de datos | SQLite en modo WAL (por defecto) o MySQL en RDS (`DB_ENGINE=mysql`) | Datos del sistema |
| Caché compartida | Redis local (paquete `redis-server`) o ElastiCache | Contador de intentos de la recuperación de contraseña con varios procesos |
| Red | Grupo de seguridad: 22 (solo tu IP), 80 y 443 (público). La base RDS, si se usa, solo acepta tráfico del grupo de la instancia | Aislamiento |
| IP | Elastic IP (y un dominio o subdominio si se dispone) | Dirección estable |
| HTTPS | Certificado Let's Encrypt (`certbot`) o ACM con un balanceador | Cifrado |
| Monitoreo | CloudWatch (CPU, memoria con el agente) y `journalctl -u sgr` | Estado y pruebas de estrés |

## 2. Primera instalación

1. **Crear la instancia** EC2 (Ubuntu, t3.small), asociar una Elastic IP y abrir el grupo de seguridad (22 solo a tu IP; 80 y 443 al mundo).
2. **Entrar por SSH** y ejecutar:
   ```bash
   git clone https://github.com/yuudhar/proyecto-sgr.git && cd proyecto-sgr
   bash deploy/instalar_ec2.sh https://github.com/yuudhar/proyecto-sgr.git v10
   ```
   El script instala Python, nginx y Redis, crea el usuario `sgr`, deja el código en `/opt/sgr/app` (en la etiqueta indicada), crea el entorno virtual e instala `requirements.txt` y `deploy/requirements-produccion.txt`.
3. **Configurar** `/etc/sgr/sgr.env` (el script deja una copia de `deploy/sgr.env.example`, con permisos 600). Valores mínimos:
   - `DEBUG=False`
   - `SECRET_KEY=` una clave propia: `python3 -c "import secrets; print(secrets.token_urlsafe(64))"`
   - `ALLOWED_HOSTS=` la IP o el dominio (separados por coma)
   - `CSRF_TRUSTED_ORIGINS=https://tu-dominio` (o `http://IP` mientras no haya HTTPS)
   - `CACHE_BACKEND=redis` y `REDIS_URL=redis://127.0.0.1:6379/1`
   - Correo real: `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL` (por ejemplo, SES o un buzón de pruebas).
   - Con HTTPS: `HTTPS=True` y, una vez comprobado, `SECURE_HSTS_SECONDS=3600` (subirlo después).
   - Si se usa RDS: `DB_ENGINE=mysql`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` (y `pip install mysqlclient`, que requiere `libmysqlclient-dev`). El esquema se crea con `migrate`; los scripts de `sql/` son alternativos.
4. **Instalar los archivos del servicio:**
   ```bash
   sudo cp deploy/sgr.service /etc/systemd/system/
   sudo cp deploy/nginx-sgr.conf /etc/nginx/sites-available/sgr   # cambia server_name por tu dominio/IP
   sudo ln -sf /etc/nginx/sites-available/sgr /etc/nginx/sites-enabled/sgr && sudo rm -f /etc/nginx/sites-enabled/default
   sudo systemctl daemon-reload && sudo systemctl enable --now sgr
   sudo nginx -t && sudo systemctl reload nginx
   ```
5. **Migrar, juntar estáticos y cargar datos de prueba** (con las variables de `sgr.env` cargadas, lo hace `actualizar.sh`):
   ```bash
   bash deploy/actualizar.sh v10
   set -a; . /etc/sgr/sgr.env; set +a
   sudo -E -u sgr /opt/sgr/venv/bin/python manage.py seed_demo_data     # solo la primera vez
   ```
   `seed_demo_data` crea los roles y las cuentas de demostración (ver README). Para la evaluación, cambia la contraseña `Hola123!` o entrega las cuentas solo al docente.
6. **HTTPS (recomendado):** `sudo apt install certbot python3-certbot-nginx && sudo certbot --nginx -d tu-dominio`. Luego `HTTPS=True` en `sgr.env` y `sudo systemctl restart sgr`.
7. **Comprobar:**
   - `curl https://tu-dominio/salud/` responde `{"servicio": "ok", "base_de_datos": "ok", "cache": "ok", "version": "v10", "commit": "...", "entorno": "producción"}` (código 503 si la base o la caché fallan).
   - `python manage.py check --deploy` (lo corre `actualizar.sh`) no debe mostrar advertencias graves.

## 3. Actualizar a otra versión

```bash
cd /opt/sgr/app && bash deploy/actualizar.sh <etiqueta-o-rama>
```
El script baja los cambios, instala dependencias, corre `check --deploy`, `migrate` y `collectstatic`, anota la versión en `COMMIT`, reinicia el servicio y consulta `/salud/`. Para volver atrás: `bash deploy/actualizar.sh <etiqueta-anterior>` (si hubo migraciones nuevas, restáuralas antes con un respaldo de la base).

## 4. Cómo demostrar que lo desplegado es lo entregado

`/salud/` devuelve el contenido del archivo `VERSION` («v10») y el `COMMIT` (salida de `git describe --tags --always`, o el hash). Debe coincidir con la etiqueta del repositorio. Esa respuesta y la pantalla de `git tag` son la evidencia 7.

## 5. Secretos

- Los secretos viven solo en `/etc/sgr/sgr.env` (permiso 600, dueño `sgr`). El repositorio incluye únicamente `.env.example` y `deploy/sgr.env.example`, sin valores reales; `.env` está en `.gitignore`.
- Sin `SECRET_KEY` propia, con `DEBUG=False`, la aplicación **no arranca** (falla a propósito).
- Antes de publicar capturas, revisa que no aparezcan claves, tokens ni el contenido de `sgr.env`.

## 6. Respaldos

SQLite: detener o usar `sqlite3 db.sqlite3 ".backup '/ruta/copia.db'"` con el servicio en marcha. RDS: instantáneas automáticas.

## 7. Qué falta por hacer (no se pudo hacer desde el entorno de desarrollo)

1. Crear la instancia, aplicar esta guía y anotar la **URL**.
2. Repetir en esa URL: `tools/evidencias/capturar.py` (evidencias 1–6) y `tools/estres/estres.py` (ver `docs/pruebas/estres/PLAN_ESTRES.md`).
3. Probar el correo real y la caché Redis con varios procesos (PEN-04 y PEN-05).
4. Entregar al docente la URL, las cuentas de evaluación y el acceso al repositorio.
