# SGR · Sistema de Gestión de Resultados

Aplicación web hecha en Django para registrar y dar seguimiento al trabajo de las delegaciones municipales: atención de público, actividades, compromisos, evidencias, planificación e informes. Cada persona ve solo lo que su rol y sus delegaciones le permiten.

Es un proyecto académico de **Programación Back End / Proyecto Integrado (INACAP)**. Todos los datos son ficticios y no representa un sitio oficial de la Municipalidad de La Serena.

Qué hace cada parte del código (módulos, clases, funciones, modelos, plantillas, JavaScript, estilos y despliegue) está explicado en [`DOCUMENTACION_CODIGO.md`](DOCUMENTACION_CODIGO.md); el código fuente no lleva comentarios.

## Índice

1. [Integrantes](#integrantes)
2. [Descripción](#descripción)
3. [Requisitos](#requisitos)
4. [Instalación](#instalación)
5. [Configuración](#configuración)
6. [Base de datos: migraciones y scripts](#base-de-datos-migraciones-y-scripts)
7. [Despliegue en Amazon Linux 2023](#despliegue-en-amazon-linux-2023)
8. [Estado de cada módulo](#estado-de-cada-módulo)
9. [Funciones operativas, simuladas y pendientes](#funciones-operativas-simuladas-y-pendientes)
10. [Instrucciones de pruebas](#instrucciones-de-pruebas)
11. [Entrega y evidencias (A4)](#entrega-y-evidencias-a4)
12. [Estructura del proyecto](#estructura-del-proyecto)

## Integrantes

- Matías Cavieres
- Matías Quiroz
- Sakty Argandoña

Asignatura: Programación Back End · Proyecto Integrado, INACAP. Repositorio: `yuudhar/proyecto-sgr` en GitHub.

## Descripción

El SGR reemplaza las planillas sueltas de las delegaciones municipales por un sistema único con base de datos real:

- **Atención:** buscar a una persona por RUT o nombre e ingresar una atención con su tipo y sub atención. La delegación, el responsable y la fecha se completan solos.
- **Dashboard, tablero de delegación e informes:** indicadores del período, semáforo de metas y exportación a Excel.
- **Mantenedores:** delegaciones, funcionarios, cargos, territorios, beneficiarios, catálogo de servicios, períodos, metas, ítems, tipos de atención y sub atención.
- **Operación y evidencias:** la pantalla *Atención* reúne las atenciones (actividades) con su búsqueda, filtros y exportación; además gestiones (compromisos), agenda colectiva y evidencias con archivo real (PDF, imagen, Word o Excel de hasta 10 MB) y su validación.
- **Usuarios y permisos:** roles con permisos por módulo, delegaciones autorizadas por usuario y recuperación de contraseña con código de seis dígitos enviado por correo.
- **Auditoría:** cada alta, edición, archivo, exportación y recuperación queda registrada con quién, cuándo y qué valor tenía antes y después.

Todos los listados incluyen búsqueda (sin distinguir mayúsculas ni tildes), paginador, filtros, orden y exportación a Excel. Los formularios se abren en ventanas modales, validan los datos en la pantalla y otra vez en el servidor, y avisan con SweetAlert2.

### Reglas de los datos

- **Contraseñas:** de 8 a 128 caracteres, con al menos una minúscula, una mayúscula, un número y un símbolo (por ejemplo `! # $ %`); además, que no sea de uso común, que no sea solo de números y que no se parezca a los datos del usuario. El mensaje dice exactamente qué le falta. Se revisan al crear un usuario, al cambiar la contraseña desde *Mi perfil* y al recuperarla.
- **Formatos:** RUT con dígito verificador, teléfono, correo, nombres, códigos, usuario y color (`#RRGGBB`) tienen una regla propia en `core/rules.py`, que usan igual el servidor y el navegador.

Los cambios de la versión 16 (archivos de evidencia, foto de perfil, alta única de funcionario y pantalla Atención única) están resumidos en [`docs/CAMBIOS_v16.md`](docs/CAMBIOS_v16.md). En la versión 17, a un funcionario que todavía no tiene usuario se le puede dar el acceso desde su propia pantalla «Editar», sin pasar por Control de usuarios, y su ficha indica con qué usuario ingresa. En la versión 18 los listados y la pantalla Atención buscan mientras se escribe (con una pausa breve) y al cambiar un filtro, sin apretar «Buscar»; el botón y la tecla Enter siguen funcionando. La versión 19 no cambia el sistema ni la base: quita los datos de demostración y deja los scripts de la base al día (ver [`docs/CAMBIOS_v19.md`](docs/CAMBIOS_v19.md)). En la versión 20 el identificador institucional del funcionario se genera solo al guardar y ya no se escribe a mano (ver [`docs/CAMBIOS_v20.md`](docs/CAMBIOS_v20.md)). En la versión 21 los listados ofrecen 5, 15 o 30 filas por página (por defecto 15), la foto de perfil pasa a `ImageField` (ahora requiere Pillow) y se documenta la política de archivos reemplazados (ver [`docs/CAMBIOS_v21.md`](docs/CAMBIOS_v21.md)). En la versión 22 seis mantenedores (Beneficiarios, Territorios, Servicios, Cargos, Tipos de gestión y Agenda) se pueden **eliminar de verdad**, con confirmación de SweetAlert2 y bloqueo si el registro está en uso, y quienes no tenían filtro o buscador lo reciben (ver [`docs/CAMBIOS_v22.md`](docs/CAMBIOS_v22.md)). En la versión 23 el Super Usuario puede **eliminar usuarios**: pasan a «Usuarios eliminados» (no se borran de la base, quedan inactivos y se pueden restaurar) y nadie más ve ni usa esa opción (ver [`docs/CAMBIOS_v23.md`](docs/CAMBIOS_v23.md)). La versión 24 aplica la Clase 11 (Django Channels): los **listados de los mantenedores se actualizan solos** cuando otra persona guarda un cambio y el **dashboard, el tablero de delegación y Validar evidencias también** (si A cambia un dato, B lo ve en su pantalla abierta sin F5); además, el Super Usuario puede ver, cambiar y quitar la foto de perfil de cualquier usuario desde Control de usuarios; el servidor pasa de gunicorn a Daphne (ver [`docs/CAMBIOS_v24.md`](docs/CAMBIOS_v24.md)). La versión 25 implementa tres requisitos del informe: la **meta esperada al día** (cuadro «Ritmo del período» en el dashboard y el tablero), los **estados de compromisos Ingresado, Pendiente, En proceso y Realizado con su historial** y la pantalla **Resumen colectivo** de la agenda (ver [`docs/CAMBIOS_v25.md`](docs/CAMBIOS_v25.md)).

## Requisitos

| Qué | Versión |
|---|---|
| Python | 3.12 o superior (en el servidor se usa 3.13) |
| Django | 6.1.1 |
| Pillow | 12.3.0 (lo exige `ImageField` de la foto de perfil; se instala con `requirements.txt`) |
| Base de datos | SQLite (desarrollo, no necesita instalar nada) o MariaDB 10.11 / MySQL 8.4 o superior (producción) |
| `mysqlclient` | 2.2.1 o superior, solo si se usa MariaDB o MySQL |
| Navegador | Chrome, Edge o Firefox actualizados |
| Channels y Daphne | 4.3.2 y 4.2.3 (tiempo real: listados y dashboard en vivo; Daphne es el servidor ASGI, también en local con `runserver`) |
| Servidor (despliegue) | Amazon Linux 2023, Apache, Daphne y certbot |

Las dependencias de Python están en `requirements.txt` (desarrollo) y `deploy/requirements-produccion.txt` (servidor). Bootstrap 5 y SweetAlert2 vienen incluidos en el proyecto: funciona sin internet.

## Instalación

Abre una terminal (Git Bash en Windows) dentro de la carpeta del proyecto, la que contiene `manage.py`.

**Windows (Git Bash):**

```bash
python -m venv venv
source venv/Scripts/activate
python -m pip install -r requirements.txt

cp .env.example .env

python manage.py migrate
python manage.py seed_roles              # crea los 5 roles con sus permisos
python manage.py seed_management_types   # crea los tipos de gestión
python manage.py createsuperuser         # tu propia cuenta de administrador
python manage.py runserver
```

**Linux o macOS:**

```bash
python3 -m venv venv
source venv/bin/activate
python -m pip install -r requirements.txt

cp .env.example .env

python manage.py migrate
python manage.py seed_roles              # crea los 5 roles con sus permisos
python manage.py seed_management_types   # crea los tipos de gestión
python manage.py createsuperuser         # tu propia cuenta de administrador
python manage.py runserver
```

Luego abre `http://127.0.0.1:8000/`. Las próximas veces solo hacen falta la activación del entorno y `python manage.py runserver`.

### Sin datos de demostración

`migrate` solo crea las tablas, sin datos. El sistema no trae datos ficticios ni cuentas de partida: los roles, los tipos de gestión y tu superusuario se crean con los tres comandos de arriba, y todo lo demás se registra desde el portal o directamente en la base (phpMyAdmin). Los datos que usan las pruebas automáticas están en `core/datos_prueba.py` y solo se cargan en la base temporal de las pruebas.

### Cuentas

Las cuentas son registros de la base (en el servidor, MariaDB: phpMyAdmin, base `sgr_django`, tabla `auth_user`; la contraseña se guarda cifrada, nunca en texto). Se ingresa con el **usuario** (o con el correo). Se crean, se editan y se desactivan en *Control de usuarios*, y cada persona cambia su contraseña en *Mi perfil*. **La política de contraseña solo se exige en los formularios: las cuentas creadas con `createsuperuser`, `set_password` o `changepassword` no pasan por ella.**

Los roles de la tabla siguiente son los que usan las pruebas automáticas y la guía de pruebas por rol (en el servidor existen las cuentas que el equipo haya creado):

| Usuario | Rol |
|---|---|
| `admin` | Super Usuario, ve todo |
| `coordinacion1` | Coordinación: catálogos y planificación |
| `jefatura1` | Jefatura de la Delegación Norte |
| `supervision1` | Jefatura con las delegaciones Norte y Sur |
| `matias.cavieres` | Funcionario y Verificador, Delegación Norte |
| `matias.quiroz` | Funcionario y Verificador, Delegación Sur |
| `consulta1` | Solo lectura |

### Recuperar la contraseña

En la pantalla de ingreso, *¿Olvidaste tu contraseña?*: escribes el correo de la cuenta, llega un código de 6 dígitos que vale **2 minutos** y se usa una sola vez (reenvío cada 45 segundos, 5 intentos por código y hasta 5 códigos por hora), y después eliges la contraseña nueva.

- Sin `EMAIL_HOST` en el `.env`, el correo no sale: se imprime en la terminal donde corre el servidor (las cuentas demo tienen un correo `usuario@sgr.example`).
- Con `EMAIL_HOST` configurado, llega un correo HTML con los colores del portal y el código en grande. Cada cuenta necesita un correo propio y distinto (se edita en *Control de usuarios*).

## Configuración

La configuración se lee desde el archivo `.env`, que se crea a partir de `.env.example` y **nunca se sube al repositorio** (está en `.gitignore`). Las variables principales:

| Variable | Uso |
|---|---|
| `DEBUG` | `True` en desarrollo y `False` en producción |
| `SECRET_KEY` | clave secreta propia; con `DEBUG=False` es obligatoria (el sistema no arranca con la de ejemplo) |
| `ALLOWED_HOSTS` | dominios o IP desde los que se accede, separados por coma |
| `DB_ENGINE` | `sqlite` (por defecto) o `mysql` (sirve para MariaDB) |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` | conexión a MariaDB/MySQL |
| `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`, `DEFAULT_FROM_EMAIL` | correo de la recuperación de contraseña |
| `CSRF_TRUSTED_ORIGINS`, `HTTPS`, `BEHIND_PROXY` | publicación detrás de Apache o nginx con HTTPS |
| `CACHE_BACKEND`, `REDIS_URL` | caché de los intentos de recuperación (`locmem`, `redis` o `db`) |
| `MEDIA_ROOT` | carpeta de los archivos subidos (evidencias y fotos); vacío = carpeta `media/` del proyecto |

### Ejemplo de configuración sin secretos

Para desarrollo (`.env`):

```ini
DEBUG=True
SECRET_KEY=cambia-esto-por-una-clave-secreta-propia
ALLOWED_HOSTS=localhost,127.0.0.1
DB_ENGINE=sqlite
DB_NAME=db.sqlite3
EMAIL_HOST=
```

Para MariaDB/MySQL, reemplaza el bloque de base de datos:

```ini
DB_ENGINE=mysql
DB_NAME=sgr_django
DB_USER=sgr_user
DB_PASSWORD=<la-clave-de-tu-base>
DB_HOST=localhost
DB_PORT=3306
```

y descomenta `mysqlclient` en `requirements.txt`. Para enviar el correo de recuperación con Gmail (la contraseña es una *contraseña de aplicación* de la misma cuenta, no la de ingreso):

```ini
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=<tu-cuenta>@gmail.com
EMAIL_HOST_PASSWORD=<contraseña-de-aplicación>
DEFAULT_FROM_EMAIL=<tu-cuenta>@gmail.com
```

Las plantillas completas para el servidor están en `deploy/sgr.env.example` y `deploy/al2023/sgr.env.example`, siempre con los secretos en blanco.

### Archivos subidos: límites y política

El sistema recibe dos tipos de archivos. Ninguno se guarda dentro de la base de datos: la tabla guarda solo la ruta (`varchar(255)`) y el archivo queda en `MEDIA_ROOT`.

| Qué se sube | Campo | Tipos aceptados | Máximo | Carpeta dentro de `MEDIA_ROOT` |
|---|---|---|---|---|
| Archivo de una evidencia | `Evidence.file_link` (`FileField`) | PDF, PNG, JPG, Word (`.docx`) o Excel (`.xlsx`) | 10 MB | `evidencias/AAAA/` |
| Foto de perfil | `UserProfile.photo` (`ImageField`, requiere Pillow) | PNG o JPG | 2 MB | `fotos/` |

Qué se revisa en el servidor (`check_upload` en `core/uploads.py`): que la extensión esté permitida, que el archivo no pese más del máximo, que no esté vacío y que el contenido corresponda a la extensión (no basta con que el nombre termine en `.pdf`). En la foto, además, `ImageField` con Pillow comprueba que sea una imagen real, no solo que empiece con la firma de una. El atributo `accept` del navegador solo orienta; la decisión es del servidor. El archivo se guarda con un nombre propio (el código de la evidencia o el usuario, más un número al azar), nunca con el que trae el computador de quien sube; el nombre original queda anotado en los metadatos de la evidencia.

Cómo se entregan: no hay ninguna URL pública hacia `media/`. Los archivos se abren solo por `evidence_file` y `profile_photo` (`core/views.py`), que piden sesión iniciada; la evidencia, además, el permiso de ver evidencias y estar dentro de la delegación activa. La carpeta `media/` está en `.gitignore`: no se sube a Git. En el servidor queda en `/opt/sgr/app/media` (o en `MEDIA_ROOT` si se define) y hay que respaldarla junto con la base de datos.

**Qué pasa con un archivo cuando se reemplaza, se archiva o queda sin registro**

El registro y su archivo tienen ciclos de vida distintos: cambiar o archivar el registro no limpia por sí solo el archivo. Estas son las decisiones del equipo:

| Situación | Qué pasa con el archivo | Por qué |
|---|---|---|
| Cambiar la foto de perfil | Se borra la foto anterior | Una foto vieja no tiene valor para el registro y no conviene dejar fotos de personas sin uso |
| Quitar la foto de perfil | Se borra el archivo | Lo mismo |
| Reemplazar el archivo de una evidencia (Editar) | El archivo anterior **no se borra**: queda en `MEDIA_ROOT` como rastro. Los metadatos de la evidencia pasan a describir el archivo nuevo (nombre original, tipo, tamaño y huella SHA-256) y, si ya estaba revisada, vuelve a «Pendiente» para una nueva revisión | Se conserva lo que alguien pudo haber revisado antes; la edición queda en la auditoría |
| Archivar una evidencia | El archivo se conserva. Desde las pantallas del sistema las evidencias solo se archivan, no se eliminan, y un archivado se puede restaurar | Archivar no es borrar |
| Archivo que quedó sin registro (huérfano) | Sigue en el disco, pero el sistema no lo puede abrir ni mostrar, porque cada archivo se entrega solo a partir de un registro | Un archivo suelto no se expone a nadie |
| Limpieza | No hay limpieza automática. Si hace falta liberar espacio, se revisa a mano comparando la carpeta `media/evidencias/` con la columna `file_link` de `evidence_evidence` antes de borrar algo | Borrar sin revisar podría eliminar una evidencia que sigue en uso |

En resumen: las fotos se limpian solas; los archivos de evidencia se conservan hasta que el equipo decida borrarlos a mano.

## Base de datos: migraciones y scripts

El esquema se crea con las **migraciones de Django**, que vienen en el repositorio (`python manage.py migrate`):

| Aplicación | Migraciones |
|---|---|
| `core` | `0001_initial` (auditoría) |
| `accounts` | `0001_initial`, `0002_roleprofile`, `0003_create_role_profiles`, `0004_userroledelegation` |
| `organization` | `0001_initial`, `0002_delegation_color`, `0003_delegation_address_commune_item_description` |
| `planning` | `0001_initial` |
| `operations` | `0001_initial` |
| `evidence` | `0001_initial` |

Comandos de datos (`python manage.py <comando>`):

| Comando | Para qué |
|---|---|
| `seed_roles` | Crea los roles Coordinación, Jefatura, Funcionario, Verificador y Consulta con sus permisos |
| `seed_management_types` | Crea los tipos de gestión |
| `cargar_volumen_estres` | Carga un volumen grande de registros marcados como prueba (`--limpiar` los borra); necesita funcionarios e ítems ya creados |
| `exportar_registro_pruebas` | Genera `docs/pruebas/registro_pruebas_funcionales.csv` y `.xlsx` |

La carpeta `sql/` guarda los scripts SQL de la base. **`sgr_django_v19.sql`** es la estructura real de la base del servidor (`sgr_django`, 32 tablas, MariaDB 10.11, exportada desde phpMyAdmin y puesta al día; sin datos ni contraseñas). **`sgr_django_v19_dbeaver.sql`** es el mismo esquema, pero crea una base aparte (`sgr_django_der`) y la vuelve a crear si ya existe: se abre en DBeaver con *Ejecutar script* (Alt+X) para generar los diagramas ER sin tocar la base real. `sgr_v19_modelo_relacional_completo_en.sql` es el diseño relacional de 22 tablas en inglés (el v9 se conserva sin cambios), y `sgr_v3_modelo_relacional_completo.sql` y `sgr_v5_modelo_relacional_completo.sql` (con su diagrama `sgr_v5_mer.png`) son los diseños originales, con los scripts de paso `sgr_v3_a_v5_alter.sql` y `sgr_v5_a_v3_revertir.sql`. Los cambios de la v16 sobre la base del servidor están en `sgr_v13_a_v16_alter.sql`, que no hace falta ejecutar porque `migrate` los aplica. **Cuidado:** el script en inglés borra y vuelve a crear una base llamada `sgr_db` (no `sgr_django`), así que sirve para el diagrama y para pruebas, no para actualizar la base del servidor: ahí las tablas las crea `migrate`. La v17, la v18, la v19 y la v20 no cambian ninguna tabla. La v22, la v23 y la v24 tampoco cambian ninguna tabla. La v21 tampoco: su migración `accounts 0006` solo cambia el tipo de campo de la foto en Django (de `FileField` a `ImageField`) y la columna `photo` sigue siendo `varchar(255)`.

**Zonas horarias en MariaDB:** los informes agrupan por fecha en hora de Chile y necesitan las tablas de zonas horarias del motor. Se cargan una vez con:

```bash
mysql_tzinfo_to_sql /usr/share/zoneinfo | mysql -u root -p mysql
```

## Despliegue en Amazon Linux 2023

El sistema se publica en una instancia EC2 con Amazon Linux 2023 (la AMI LAMP de AWS, con Apache, PHP, MariaDB y phpMyAdmin). La guía completa, con los comandos paso a paso, está en [`docs/aws/DESPLIEGUE_AL2023.md`](docs/aws/DESPLIEGUE_AL2023.md). La versión genérica con nginx está en `docs/aws/DESPLIEGUE_AWS.md`.

### Cómo encaja cada pieza

| Pieza | Para qué |
|---|---|
| Apache | Recibe los puertos 80 y 443, pone el certificado, sirve `/static/` y `/phpMyAdmin`, y le pasa el resto a Daphne; `/ws/` pasa por WebSocket (`deploy/al2023/apache-http.conf` y `apache-https.conf`) |
| Daphne (servicio `sgr`) | Ejecuta Django por ASGI en `127.0.0.1:8000`: atiende HTTP y WebSocket con un solo proceso (`deploy/sgr.service`). Reemplaza a gunicorn desde la v24 |
| MariaDB 10.11 | Base de datos `sgr_django` con el usuario `sgr_user`. Django 6.1 no se conecta a la 10.5 que instala el tutorial LAMP: hay que instalar `mariadb1011-server` |
| certbot (`/opt/certbot`) | Certificado de Let's Encrypt para la IP pública o un dominio, con renovación automática (`sgr-certbot.timer`) |

Rutas en el servidor: aplicación en `/opt/sgr/app`, entorno virtual en `/opt/sgr/venv`, variables en `/etc/sgr/sgr.env` (permiso 600, dueño `sgr`).

Grupo de seguridad: puerto 22 solo desde tu IP; 80 y 443 abiertos; el 3306 no se abre.

### Pasos resumidos

1. **MariaDB 10.11:** `sudo dnf install -y mariadb1011-server mariadb1011-devel`, `sudo systemctl enable --now mariadb`, `sudo mysql_secure_installation`.
2. **Base de datos** (en phpMyAdmin, pestaña SQL):
   ```sql
   CREATE DATABASE sgr_django CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
   CREATE USER 'sgr_user'@'localhost' IDENTIFIED BY '<clave>';
   GRANT ALL PRIVILEGES ON sgr_django.* TO 'sgr_user'@'localhost';
   ```
3. **Instalar** (clona el repositorio, crea el usuario `sgr`, el entorno virtual, `/etc/sgr/sgr.env` con una `SECRET_KEY` nueva, el servicio y Apache):
   ```bash
   git clone -b <rama> --single-branch https://github.com/yuudhar/proyecto-sgr.git && cd proyecto-sgr
   sudo bash deploy/al2023/instalar_al2023.sh https://github.com/yuudhar/proyecto-sgr.git <rama> <ip-o-dominio>
   ```
4. **Migrar y arrancar:** `cd /opt/sgr/app && sudo bash deploy/actualizar.sh <rama>`. Hace `check --deploy`, `migrate`, `collectstatic` y reinicia el servicio.
5. **Cuentas:** solo si la base está vacía, `seed_roles`, `seed_management_types` y `createsuperuser` (como root, con las variables de `/etc/sgr/sgr.env` cargadas). Si la base ya tiene datos, no se hace nada.
6. **HTTPS:** `sudo bash deploy/al2023/https_certificado.sh <ip-o-dominio> <correo>`. Con `--prueba` ensaya contra el entorno de pruebas de Let's Encrypt sin tocar el sitio. Deja `HTTPS=True`, redirige el 80 al 443 y crea el temporizador de renovación.
7. **Comprobar:** `curl https://<ip-o-dominio>/salud/` (responde con la versión desplegada) y `systemctl list-timers sgr-certbot.timer`.

### Actualizar a una versión nueva

```bash
cd /opt/sgr/app && sudo bash deploy/actualizar.sh <rama-o-etiqueta>
```

### Producción: lo que ya está configurado

`DEBUG=False`, `SECRET_KEY` propia, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, cookies seguras y redirección a HTTPS, archivos estáticos servidos por Apache, y una sola instancia de Daphne para que el límite de intentos de la recuperación y la capa de canales en memoria sean válidos (con más procesos harían falta Redis para la caché, `CACHE_BACKEND=redis`, y `channels_redis` para el tiempo real). phpMyAdmin queda detrás del mismo HTTPS y se puede limitar a una IP en `/etc/httpd/conf.d/00-sgr.conf`.

## Estado de cada módulo

Todos los módulos leen y escriben en la base de datos real, con permisos por rol y alcance por delegación.

| Módulo | Dónde está en el menú | Estado | Notas |
|---|---|---|---|
| Ingreso, login y sesión | Pantalla de ingreso | Operativo | Usuario o correo; rechaza cuentas inactivas sin decir qué dato falló |
| Recuperar contraseña | Pantalla de ingreso | Operativo | Código de 6 dígitos de 120 s; correo real por SMTP |
| Atención (ingreso y listado) | Atención | Operativo | Tipo y sub atención dependientes; identificador `ATN00001`…; el listado de actividades es esta misma pantalla, con filtros y Excel |
| Dashboard | Dashboard | Operativo | Promedios y semáforo con las metas guardadas |
| Gestiones, Agenda colectiva | Operación | Operativo | Ligadas a la atención y a la delegación de quien las crea (las actividades se ven en Atención) |
| Evidencias y validación | Operación | Operativo | Se sube el archivo; el verificador (su propio funcionario, sin elegirlo) aprueba, rechaza u observa, y vuelve a la evidencia revisada. Nadie valida la evidencia que subió |
| Tablero de delegación, Informes, Indicadores | Resultados | Operativo | Informes en CSV y Excel |
| Delegaciones, Funcionarios, Territorios, Cargos, Ítems de cargo | Administración › Organización | Operativo | Ver, crear, editar y archivar en ventana modal |
| Períodos, Metas, Ajustes | Administración › Planificación | Operativo | Semáforo con los umbrales del período |
| Servicios, Ítems y metas, Tipos de atención, Sub atención, Tipos de gestión, Beneficiarios | Administración › Catálogos | Operativo | Todos con búsqueda, filtros y Excel |
| Control de usuarios y Roles | Administración › Sistema | Operativo | Matriz de permisos, alcance y delegaciones adicionales por usuario |
| Auditoría | Administración › Sistema | Operativo | Quién, cuándo y valor anterior y nuevo |
| Selector de delegaciones | Franja superior | Operativo | Solo ofrece las autorizadas; el servidor lo revalida en cada petición (403 si lo alteran) |
| Exportar a Excel | Todos los listados | Operativo | `.xlsx`, hasta 10.000 filas, queda en la auditoría |
| Despliegue en AWS | `deploy/` | Operativo en HTTP; HTTPS con script listo | Ver la sección de despliegue |

## Funciones operativas, simuladas y pendientes

### Operativas: funcionan con datos reales

Todo lo de esta tabla lee y escribe en la base de datos del proyecto; nada es una maqueta.

| Función | Qué hace de verdad | Dónde comprobarlo |
|---|---|---|
| Login y sesión | Entra con usuario o correo y contraseña; rechaza la cuenta inactiva y no dice cuál dato falló. La sesión queda en la tabla `django_session` y al salir se borra. | Pantalla de ingreso; `accounts/test_backends.py`, `core/test_access_flow.py` |
| Recuperar contraseña | Código de 6 dígitos que vale 120 s, se reenvía cada 45 s, falla a los 5 intentos y se pide hasta 5 veces por hora. El código no se guarda, solo su huella, y cada envío queda en la auditoría. | Tres pantallas de recuperación; `accounts/test_recovery.py` |
| Contraseñas | Las revisan los validadores de Django (largo mínimo, no común, no solo números, no parecida a los datos del usuario) al crear usuarios, al cambiarla en *Mi perfil* y al recuperarla. | *Mi perfil*, *Control de usuarios*; `core/test_users.py`, `core/test_workspace.py` |
| Roles y alcance | Cada rol trae su descripción, su alcance (su delegación o todas), su estado y su matriz de permisos. El menú, los botones y el servidor (403) siguen esa matriz. | Roles y permisos; `core/test_a1.py`, `core/test_permissions.py` |
| Selector de delegaciones | Cada usuario trabaja en la delegación de su funcionario y, si tiene filas en `Usuario_Rol_Delegacion` (se marcan en Control de usuarios), elige otras en la franja de arriba; quienes ven todas pueden elegir también «Todas». Al cambiar se actualizan listados, filtros, exportaciones y formularios. | Franja de arriba con `supervision1`; `core/test_a2.py` |
| Mantenedores | Delegaciones, Roles, Usuarios, Ítems y metas, Tipo de Atención y Sub Atención, más Funcionarios, Territorios, Cargos, Períodos, Metas, Ajustes, Servicios, Tipos de gestión y Beneficiarios: ver, crear, editar y eliminar en ventana modal. «Eliminar» archiva el registro y se puede restaurar; solo Roles se borra de verdad. | Menú Administración; `core/test_catalogs.py`, `core/test_edits.py` |
| Tabla, búsqueda y Excel | Cada listado tiene búsqueda por palabras, filtros, orden, paginador y Exportar a Excel (`.xlsx`, hasta 10.000 filas, queda en la auditoría). | Cualquier listado; `core/test_search.py`, `core/test_export.py` |
| Ingreso de atención | Solicitante por RUT o nombre, tipo y sub atención, descripción obligatoria; la delegación sale del contexto activo y el responsable es el funcionario del usuario (en otra delegación se elige uno de ella), la fecha es automática y el identificador es `ATN00001`. | Atención; `core/test_intake.py` |
| Gestiones, Agenda y Evidencias | Registros ligados a la atención y a la delegación de quien los crea. | Menú Operación; `core/test_portal.py` |
| Validar evidencias | El verificador aprueba, rechaza u observa la evidencia y puede dejar una observación; queda su decisión (con su funcionario, o «Super Usuario» si revisó el Super Usuario) y la evidencia cambia de estado. No puede revisar la evidencia que él mismo subió. | Validar evidencias; `core/test_portal.py` |
| Dashboard, Tablero e Informes | Calculan promedios y semáforos con las metas y los indicadores guardados; los informes se bajan en CSV o Excel. | Menú Resultados; `core/test_scope.py`, `core/test_portal.py` |
| Auditoría | Cada alta, edición, archivo, exportación y recuperación guarda quién, cuándo y el valor anterior y el nuevo. | Menú Sistema, Auditoría; `core/test_edits.py`, `core/test_scope.py` |
| Validaciones | Cada regla se revisa en la pantalla, con aviso de SweetAlert2, y otra vez en el servidor. | `core/test_rules.py`, `core/test_flash.py` |

### Simuladas o limitadas

Estas funciones existen y se pueden mostrar, pero con menos alcance que en un sistema en producción.

| Función | Cómo funciona hoy | Para que sea real |
|---|---|---|
| Correo de recuperación | Sin `EMAIL_HOST` en el `.env` el mensaje no sale: se imprime en la consola donde corre el servidor. Con `EMAIL_HOST` (Gmail, Mailtrap u otro SMTP) se envía de verdad, en HTML con los colores del portal. Las pruebas automáticas revisan el mensaje en memoria. | Configurar el SMTP en el `.env` del servidor |
| Datos de la base | El sistema no trae datos ficticios: lo que hay en la base (usuarios, delegaciones, atenciones, evidencias, indicadores) son registros normales que se ven y editan en el portal o en phpMyAdmin. Las pruebas automáticas usan sus propios datos (`core/datos_prueba.py`) en una base temporal. | Respaldar la base con la exportación de phpMyAdmin |
| Archivos de evidencia y fotos | Se suben a la carpeta de archivos del servidor (`MEDIA_ROOT`, por defecto `media/`; en AWS `/opt/sgr/app/media`), con un nombre propio. Se aceptan PDF, PNG, JPG, Word y Excel de hasta 10 MB (fotos: PNG o JPG de hasta 2 MB) y se revisa que el contenido corresponda a la extensión. Los metadatos (nombre original, tipo, tamaño y huella SHA-256) los arma el sistema. Los archivos no tienen dirección pública: se entregan solo a quien puede ver esa evidencia. | Respaldar la carpeta de archivos junto con la base de datos |
| Indicadores | El avance, el cumplimiento y la ponderación se ingresan a mano en Indicadores. El semáforo sí se calcula con los umbrales del período. No se calculan solos desde las atenciones registradas. | Definir la fórmula de cada ítem |
| Límite de intentos del código | El contador usa la caché de Django, que por defecto vive en la memoria de cada proceso. Con varios procesos el límite no se comparte. | Una caché compartida (Redis), o un solo proceso |
| Base de datos | SQLite por defecto; MariaDB o MySQL se activa con `DB_ENGINE` en el `.env`. Las pruebas automáticas corren sobre SQLite. | Probar con el motor que use AWS (ya es MariaDB en el servidor) |
| Diseño del municipio | Estilo inspirado en la Municipalidad de La Serena, con Arial, el rojo `#920000` que declara su sitio y el escudo oficial (en el ingreso, la recuperación y la franja de arriba). El pie de página dice que no es un sitio oficial. | Confirmar el código exacto del color con el manual de normas gráficas |

### Pendientes

- **Entrega (A4):** HTTPS con certificado en la URL final, etiqueta Git de la entrega, evidencias (capturas o video) tomadas sobre la URL real y pruebas de estrés sobre el servidor desplegado.
- **Diagrama de la base de datos:** pasar los campos nuevos al diagrama; el script SQL en inglés v10 ya los trae, solo falta ejecutarlo en DBeaver.

| Tabla del diagrama | Campo nuevo | Tipo | En el proyecto |
|---|---|---|---|
| Delegacion (Delegation) | `direccion` (address) | `VARCHAR(200) NOT NULL DEFAULT ''` | `organization_delegation.address` |
| Delegacion (Delegation) | `comuna` (commune) | `VARCHAR(100) NOT NULL DEFAULT ''` | `organization_delegation.commune` |
| Item | `descripcion` (description) | `VARCHAR(255) NOT NULL DEFAULT ''` | `organization_item.description` |
| Rol (Role) | `descripcion` (description) | `VARCHAR(255) NOT NULL DEFAULT ''` | `accounts_roleprofile.description` |
| Rol (Role) | `alcance` (scope): `own` = su delegación, `all` = todas | `VARCHAR(10) NOT NULL DEFAULT 'own'` | `accounts_roleprofile.scope` |
| Rol (Role) | `estado` (status): `active` o `inactive` | `VARCHAR(20) NOT NULL DEFAULT 'active'` | `accounts_roleprofile.status` |
| Usuario (User) | `foto` (photo), v16: ruta del PNG o JPG subido | `VARCHAR(255) NULL` | `accounts_userprofile.photo` |
| Validación (Validation) | `Funcionario_id_verificador` ahora admite vacío, v16: lo deja vacío una revisión del Super Usuario | `INT NULL` | `evidence_validation.reviewer_officer_id` |
| Evidencia (Evidence) | `file_link`, v16: sin cambio de tipo; ahora guarda la ruta del archivo subido | `VARCHAR(255) NOT NULL` | `evidence_evidence.file_link` |

El nombre del rol sigue en el grupo de Django, así que Role equivale a la suma de `auth_group` y `accounts_roleprofile`. La tabla `Usuario_Rol_Delegacion` ya estaba en el diagrama; en Django suma las columnas técnicas `id`, `created_at`, `updated_at` y `deleted_at`, igual que las otras tablas.

## Instrucciones de pruebas

### Pruebas automáticas

```bash
python manage.py test                 # toda la suite
python manage.py test --parallel 4    # más rápido
python manage.py test accounts        # una aplicación
python manage.py test core.test_rules # un archivo
```

Son más de 700 pruebas sobre SQLite en memoria, sin tocar tu base de datos. Cada prueba tiene su descripción y el requisito que cubre en `core/qa/`; una prueba sin registrar hace fallar la suite.

### Probar a mano por rol

1. Entra con una cuenta de cada rol (créalas en *Control de usuarios* si no existen; ver la tabla de cuentas).
2. Con `admin` revisa todos los menús; con `consulta1` comprueba que solo ve y no puede crear (los botones no aparecen y las rutas devuelven 403).
3. Con `supervision1` cambia de delegación en la franja de arriba y mira cómo cambian los listados.
4. Con `matias.cavieres` ingresa una atención en *Atención* y sube una evidencia con un archivo PDF. La valida otra persona (`matias.cavieres` revisa las evidencias de su delegación que subió el otro funcionario, porque nadie revisa la suya).
5. En *Funcionarios › Nuevo funcionario* llena «Acceso al sistema»: se crean el funcionario y su cuenta en un solo paso. En *Mi perfil* sube tu foto.
6. Prueba la recuperación de contraseña con una cuenta que tenga correo propio.

La matriz de menús por rol está en `docs/evidencias/matriz_menus_por_rol.md`.

### Registro de pruebas, estrés y evidencias

| Qué | Cómo |
|---|---|
| Registro de pruebas funcionales | `python manage.py exportar_registro_pruebas` → `docs/pruebas/registro_pruebas_funcionales.csv` y `.xlsx` |
| Pruebas de estrés | `python tools/estres/estres.py --url <URL> --etapas 1,5,10,20 --duracion 60` (solo biblioteca estándar); opcionalmente `python manage.py cargar_volumen_estres` para tener volumen de datos. El plan y los resultados están en `docs/pruebas/estres/` |
| Capturas de evidencia | `python tools/evidencias/capturar.py --url <URL>` (requiere `pip install playwright && playwright install chromium`); salen en `docs/evidencias/capturas/` |
| Revisión de despliegue | `python manage.py check --deploy` con las variables de producción cargadas |

## Entrega y evidencias (A4)

| Dato | Valor |
|---|---|
| URL de AWS | `http://32.198.200.215/` (IP elástica de la instancia EC2); pasa a `https://32.198.200.215/` al activar el certificado |
| Versión desplegada | `https://<url>/salud/` muestra el commit y la etiqueta que está corriendo, para comprobar que es la versión entregada |
| Repositorio | `https://github.com/yuudhar/proyecto-sgr` (rama `main` y la etiqueta `entrega-2`) |
| Acceso de evaluación | Cuentas de la tabla de cuentas de prueba (el docente recibe la contraseña por el canal acordado) |
| Secretos | Ninguno en el repositorio: `.env` y `db.sqlite3` están fuera de Git; el servidor guarda sus claves en `/etc/sgr/sgr.env` |

Dónde está cada punto de la lista de verificación:

| N° | Evidencia requerida | Dónde está |
|---|---|---|
| 1 | Login y recuperación completa de contraseña | `docs/evidencias/capturas/EV1_*`; sección de recuperación |
| 2 | Seis CRUD (Delegaciones, Roles, Usuarios, Ítems y metas, Tipo de Atención, Sub Atención) | `docs/evidencias/capturas/EV2_*` |
| 3 | Ingreso de atención con catálogos dependientes y contexto de delegación | `docs/evidencias/capturas/EV3_*` |
| 4 | Tabla, paginador, búsqueda y Exportar a Excel | `docs/evidencias/capturas/EV4_*` |
| 5 | Normas gráficas, identificación de delegación, usuario y rol, alcance por perfil | `docs/evidencias/capturas/EV5_*` y `docs/evidencias/matriz_menus_por_rol.md` |
| 6 | Validaciones y mensajes SweetAlert2 | `docs/evidencias/capturas/EV6_*` |
| 7 | URL AWS, repositorio Git y versión inequívoca | Esta sección y `/salud/` |
| 8 | Resultados de pruebas funcionales y de estrés, evidencias y correcciones | `docs/pruebas/` (registro de pruebas, estrés y resultados) |
| 9 | Resumen de funciones operativas, simuladas y pendientes | La sección [Funciones operativas, simuladas y pendientes](#funciones-operativas-simuladas-y-pendientes) |

## Estructura del proyecto

```
sgr_project/    configuración de Django
core/           portal, menús, búsqueda, reglas de validación, exportación a Excel y auditoría
accounts/       ingreso, recuperación de contraseña, roles y delegaciones
organization/   delegaciones, funcionarios, cargos, territorios y beneficiarios
planning/       períodos, metas e indicadores
operations/     atenciones, actividades, compromisos y seguimientos
evidence/       evidencias y su validación
templates/      plantillas HTML (incluye el correo de recuperación)
sql/            scripts de la base de datos
deploy/         archivos para publicar en un servidor (nginx y Amazon Linux 2023 con Apache)
docs/           documentación del despliegue, registro de pruebas y evidencias
tools/          herramientas de pruebas de estrés y de capturas
```
