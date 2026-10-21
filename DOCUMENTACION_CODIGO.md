# SGR — Documentación del código

**Sistema de Gestión de Resultados (SGR)** para la Ilustre Municipalidad de La Serena. Este documento explica qué hace cada parte del código del proyecto: cada módulo, clase, función y método, además de las plantillas, el JavaScript, los estilos, los archivos de despliegue y los scripts de la base de datos. El código fuente no lleva comentarios; todo lo que antes iba como comentario está aquí.

## 1. Qué hace el sistema

- Las **delegaciones** (sectores de trabajo en terreno) registran **atenciones** a personas (beneficiarios), con gestiones de seguimiento, **compromisos** de la agenda colectiva y **evidencias** (archivos que respaldan cada atención).
- Una persona distinta a quien subió la evidencia la **revisa** (aprueba, observa o rechaza).
- Cada período de medición tiene **metas** por funcionario o por cargo; sus **indicadores** miden el cumplimiento y se muestran con un **semáforo** (verde, ámbar, rojo). Los **ajustes** suman bonificaciones o penalizaciones.
- Hay un **dashboard** por persona, un **tablero de delegación** e **informes** descargables (Excel, CSV) por período.
- Cada persona ve solo lo que su rol permite y, salvo los roles con alcance global, solo la información de su delegación.
- Todo cambio hecho desde las pantallas queda en el **registro de auditoría**.

## 2. Tecnologías

| Parte | Tecnología |
|---|---|
| Lenguaje y framework | Python y Django 6.1.1 |
| Base de datos | SQLite en desarrollo; MariaDB 10.11 / MySQL en el servidor (`DB_ENGINE`) |
| Caché | Memoria local, Redis o tabla de la base (`CACHE_BACKEND`) |
| Interfaz | Plantillas de Django, Bootstrap 5, Bootstrap Icons y SweetAlert2 |
| Exportar a Excel | openpyxl |
| Servidor | gunicorn detrás de Apache (Amazon Linux 2023) o nginx (Ubuntu), servicio `systemd` |

## 3. Estructura de carpetas

```
manage.py                 comandos de Django
requirements.txt          dependencias de Python
VERSION                   versión que muestra /salud/
sgr_project/              configuración (settings, rutas, WSGI/ASGI)
core/                     motor de pantallas, acceso, formularios, utilidades, menú y estáticos
accounts/                 usuarios, perfiles, roles, delegaciones adicionales y recuperación de contraseña
organization/             delegaciones, cargos, ítems, servicios, beneficiarios, territorios, funcionarios
planning/                 períodos, metas, indicadores y ajustes
operations/               atenciones, gestiones de seguimiento y compromisos
evidence/                 evidencias y validaciones
templates/                marco general, errores y pantallas sin sesión
deploy/                   archivos para instalar y actualizar en el servidor
sql/                      scripts de la base de datos
docs/                     documentos del proyecto
```

Cada app tiene `models.py` (tablas), `admin.py` (Django Admin), `apps.py` y `migrations/`. `core` y `accounts` agregan además pantallas, formularios y reglas propias.

## 4. Modelo de datos

32 tablas en la base `sgr_django`: 22 del proyecto, 6 del framework (usuarios, grupos, permisos, tipos de contenido, sesiones y registro del Admin), 3 de unión (usuario–grupo, usuario–permisos, grupo–permisos) y `django_migrations`.

| App | Tablas del proyecto |
|---|---|
| `core` | `AuditLog` (auditoría) |
| `organization` | `Delegation`, `Position`, `Item`, `Service`, `Beneficiary`, `Territory`, `Officer`, `PositionItem` |
| `accounts` | `UserProfile`, `RoleProfile`, `UserRoleDelegation` |
| `planning` | `Period`, `Goal`, `Indicator`, `Adjustment` |
| `operations` | `ManagementType`, `Activity`, `Followup`, `Commitment` |
| `evidence` | `Evidence`, `Validation` |

Todas las tablas del proyecto heredan de `BaseModel` (`core/models.py`), que agrega `created_at`, `updated_at` y `deleted_at`. **Borrado lógico:** un registro con `deleted_at` lleno está *archivado*: no sale en los listados normales, pero se puede restaurar. Solo se elimina de verdad lo que no está en uso.

## 5. Cómo viaja una petición

1. **Rutas** (`sgr_project/urls.py`, `core/urls.py`, `accounts/urls.py`): deciden qué vista atiende cada dirección. Las rutas de los mantenedores las genera `Registry.urls()` (`core/crud.py`) a partir de `core/registry.py`.
2. **Middleware** (`core/middleware.py`): fuera de `/admin/` aplica el idioma y la zona horaria del portal y manda cabeceras para que el navegador no guarde las pantallas.
3. **Vista**: las pantallas de mantenedor son vistas de clase (`CrudListView`, `CrudDetailView`, `CrudCreateView`, `CrudUpdateView`, `CrudArchiveView`, `CrudRestoreView`, `CrudDeleteView`) que piden el permiso de Django de cada acción. Las pantallas especiales (inicio, validación, tablero, informes, perfil, Atención) están en `core/views.py`.
4. **Alcance por delegación** (`core/access.py`): el superusuario y los roles con alcance global ven todas las delegaciones; el resto, solo la suya (o las que tenga autorizadas y elija en la franja de arriba). Cada `Crud` filtra su consulta con esta regla.
5. **Formularios** (`core/forms.py`): `CrudForm` es la base de todos. Aplica el estilo, acota las listas a la delegación activa y valida los formatos con las reglas de `core/rules.py`, que el navegador comprueba antes con `validation.js`.
6. **Guardado**: en una transacción, `CrudFormView.save` prepara el objeto, lo guarda, ejecuta lo que sigue al guardado y escribe la auditoría (`core/audit.py`).
7. **Plantillas y contexto**: `core/context_processors.py` entrega el menú (`core/menus.py`), la persona, su delegación y sus roles a todas las plantillas.

## 6. Roles del sistema

Los roles son grupos de Django que crea el comando `seed_roles` (`accounts/management/commands/seed_roles.py`); el superusuario no es un grupo y aparece como «Super Usuario».

| Rol | Qué puede hacer |
|---|---|
| Super Usuario | Acceso completo: administra usuarios, delegaciones y todos los datos. |
| Coordinación | Define períodos, metas y ajustes, y consulta todas las delegaciones (alcance global). |
| Jefatura | Consulta la gestión de su delegación y actualiza los compromisos. |
| Funcionario | Registra atenciones, gestiones, evidencias y compromisos de su delegación. |
| Verificador | Revisa las evidencias de su delegación y registra la validación. |
| Consulta | Solo consulta la información de su delegación. |

Cada rol tiene una ficha (`RoleProfile`) con descripción, alcance (su delegación o todas) y estado, que se edita en el mantenedor de roles.

## 7. Mantenedores registrados

`core/registry.py` declara un `Crud` por cada una de estas pantallas (`slug` = parte de la dirección): `actividades`, `gestiones`, `agenda`, `evidencias`, `validaciones`, `periodos`, `metas`, `indicadores`, `ajustes`, `delegaciones`, `territorios`, `funcionarios`, `cargos`, `items-de-cargo`, `servicios`, `items`, `tipos-de-atencion`, `sub-atenciones`, `tipos-de-gestion`, `beneficiarios`, `usuarios`, `roles` y `auditoria`.

## 8. Cómo leer el resto del documento

- **Código Python**: por app y por archivo. De cada clase se explica qué es y qué hace cada método; de cada modelo se listan sus campos.
- **Migraciones**, **Plantillas**, **JavaScript**, **Hoja de estilos**, **Despliegue y configuración** y **Scripts de la base de datos**.
- Las librerías de terceros incluidas en `core/static/core/vendor/` conservan sus propios encabezados y no se documentan aquí.


## 9. Código Python

### Configuración del proyecto (`sgr_project`)

#### `manage.py`

Punto de entrada de la línea de comandos de Django: fija el módulo de configuración (`sgr_project.settings`) y ejecuta el comando que se pida (`runserver`, `migrate`, `check`, etc.).

**Funciones**

- **`main()`**: Fija el módulo de configuración y ejecuta la línea de comandos de Django con los argumentos recibidos.

#### `sgr_project/settings.py`

Configuración del proyecto. Lee las variables de entorno (archivo `.env` en desarrollo, `/etc/sgr/sgr.env` en el servidor) y define aplicaciones instaladas, middleware, base de datos (SQLite o MySQL/MariaDB), caché (memoria local o Redis), validación de contraseñas, correo, archivos estáticos y subidos, seguridad HTTPS, registro de eventos (logging) y los límites de archivos.

| Variable | Qué hace |
|---|---|
| `BASE_DIR` | Carpeta raíz del proyecto. |
| `SECRET_KEY` | Clave secreta de Django (variable `SECRET_KEY`). En producción es obligatoria y no puede ser la de desarrollo. |
| `DEBUG` | Modo de desarrollo (variable `DEBUG`, `True` por defecto). |
| `ALLOWED_HOSTS` | Dominios e IP desde los que se atiende el sitio (variable `ALLOWED_HOSTS`, separados por coma). |
| `INSTALLED_APPS` | Aplicaciones de Django y del proyecto: `core`, `organization`, `accounts`, `planning`, `operations` y `evidence`. |
| `MIDDLEWARE` | Cadena de middleware, incluidos `PortalLocaleMiddleware` (idioma y zona horaria del portal) y `PortalNoCacheMiddleware` (sin caché en las pantallas). Con `USE_WHITENOISE` se agrega WhiteNoise. |
| `ROOT_URLCONF` | Módulo con las rutas principales (`sgr_project.urls`). |
| `TEMPLATES` | Motor de plantillas: carpeta `templates/` más las de cada app, con el procesador de contexto `core.context_processors.portal`. |
| `WSGI_APPLICATION` | Punto de entrada WSGI que usa gunicorn. |
| `DB_ENGINE` | Motor de base de datos (`DB_ENGINE`): `sqlite` por defecto o `mysql`/`mariadb`. |
| `DATABASES` | Conexión a la base de datos. Con MySQL/MariaDB usa `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST` y `DB_PORT`, con juego de caracteres utf8mb4; con SQLite usa el archivo `DB_NAME`. `DB_CONN_MAX_AGE` fija cuánto se mantiene abierta la conexión. |
| `AUTH_PASSWORD_VALIDATORS` | Validadores de contraseña: parecido a los datos personales, largo mínimo, contraseñas comunes, solo números y la política propia `PasswordPolicyValidator`. |
| `LANGUAGE_CODE` | Idioma general de Django. |
| `TIME_ZONE` | Zona horaria general de Django (UTC). |
| `USE_I18N` | Activa la traducción. |
| `USE_TZ` | Guarda las fechas con zona horaria. |
| `STATIC_URL` | Dirección de los archivos estáticos. |
| `DEFAULT_AUTO_FIELD` | Tipo de la clave primaria por defecto (`BigAutoField`). |
| `EMAIL_HOST` | Servidor de correo (`EMAIL_HOST`). |
| `EMAIL_BACKEND` | Forma de enviar correos: SMTP si hay servidor, o consola si no. |
| `EMAIL_PORT` | Puerto del servidor de correo (587 por defecto). |
| `EMAIL_HOST_USER` | Usuario del servidor de correo. |
| `EMAIL_HOST_PASSWORD` | Contraseña del servidor de correo. |
| `EMAIL_USE_SSL` | Conexión SSL al servidor de correo. |
| `EMAIL_USE_TLS` | Conexión TLS al servidor de correo (se desactiva si se usa SSL). |
| `EMAIL_TIMEOUT` | Segundos de espera al enviar un correo (10). |
| `DEFAULT_FROM_EMAIL` | Remitente de los correos del sistema. |
| `PORTAL_LANGUAGE` | Idioma de las pantallas del portal (`es`). |
| `PORTAL_TIME_ZONE` | Zona horaria de las pantallas del portal (`America/Santiago`). |
| `AUTHENTICATION_BACKENDS` | Forma de autenticar: `EmailOrUsernameBackend` (usuario o correo). |
| `LOGIN_URL` | Ruta del ingreso. |
| `LOGIN_REDIRECT_URL` | A dónde se va después de ingresar (el dashboard). |
| `LOGOUT_REDIRECT_URL` | A dónde se va después de salir (el ingreso). |
| `SESSION_ENGINE` | Las sesiones se guardan en la base de datos. |
| `RECOVERY_CODE_SECONDS` | Segundos que vale el código de recuperación (120). |
| `RECOVERY_MAX_ATTEMPTS` | Intentos permitidos al escribir el código (5). |
| `RECOVERY_MAX_REQUESTS` | Veces que se puede pedir un código (5). |
| `RECOVERY_RESEND_SECONDS` | Espera entre un envío y otro del código (45 segundos). |
| `RECOVERY_PASSWORD_SECONDS` | Segundos disponibles para elegir la contraseña nueva una vez validado el código (600). |
| `_env_bool` | Lee una variable de entorno como verdadero o falso. |
| `_env_int` | Lee una variable de entorno como número entero y avisa si no lo es. |
| `STATIC_ROOT` | Carpeta donde `collectstatic` junta los estáticos. |
| `MEDIA_ROOT` | Carpeta de los archivos que suben las personas (`MEDIA_ROOT`, `media/` por defecto). |
| `MEDIA_URL` | Dirección base de los archivos subidos. |
| `EVIDENCE_MAX_MB` | Tamaño máximo de una evidencia, en MB (10). |
| `PHOTO_MAX_MB` | Tamaño máximo de una foto de perfil, en MB (2). |
| `DATA_UPLOAD_MAX_MEMORY_SIZE` | Tamaño máximo de los datos de una petición sin archivos (2 MB). |
| `FILE_UPLOAD_PERMISSIONS` | Permisos con que se guardan los archivos subidos (0o640). |
| `CSRF_TRUSTED_ORIGINS` | Orígenes de confianza para los formularios (`CSRF_TRUSTED_ORIGINS`). |
| `CACHE_BACKEND` | Caché: `locmem` (memoria) por defecto, `redis` o `db`. |
| `CACHES` | Caché compartida: Redis (`REDIS_URL`) si `CACHE_BACKEND=redis` o tabla de la base si es `db`; con otro valor distinto de `locmem` el sistema no parte. |
| `LOGGING` | En producción registra en consola con el nivel `LOG_LEVEL`. |

Comportamientos según las variables de entorno:

- Con `USE_WHITENOISE` agrega WhiteNoise para servir los estáticos desde gunicorn.
- Con `BEHIND_PROXY` confía en la cabecera `X-Forwarded-Proto` del servidor web.
- Con `HTTPS` activa las cookies seguras, la redirección a HTTPS (salvo `/salud/`) y HSTS (`SECURE_HSTS_SECONDS`).
- Si `DEBUG` es falso, exige una `SECRET_KEY` propia; si no, el sistema no parte.
- Con SQLite y `DEBUG` falso, abre la base con espera de 20 segundos, modo WAL y transacciones inmediatas.

#### `sgr_project/urls.py`

Rutas de primer nivel: la revisión de estado `/salud/`, el Django Admin en `/admin/`, el ingreso y la salida del sistema, la redirección de las rutas antiguas de cambio y restablecimiento de contraseña hacia las pantallas del sistema, el resto de las rutas de `django.contrib.auth` y la inclusión de las rutas de `accounts` y de `core`.

| Ruta | Vista | Nombre |
|---|---|---|
| `/salud/` | `salud` | `salud` |
| `/admin/` | `admin.site.urls` |  |
| `/accounts/login/` | `PortalLoginView.as_view()` |  |
| `/accounts/logout/` | `PortalLogoutView.as_view()` |  |
| `/accounts/password_change/` | `RedirectView.as_view(pattern_name='core:profile')` |  |
| `/accounts/password_reset/` | `RedirectView.as_view(pattern_name='accounts:recover')` |  |
| `/accounts/` | `include('django.contrib.auth.urls')` |  |
| `/` | `include('accounts.urls')` |  |
| `/` | `include('core.urls')` |  |

#### `sgr_project/wsgi.py`

Entrada WSGI del proyecto. Es la que usa gunicorn en el servidor (`sgr_project.wsgi:application`).

#### `sgr_project/asgi.py`

Entrada ASGI del proyecto, para servidores asíncronos. Expone la aplicación `application`.

#### `deploy/gunicorn.conf.py`

Configuración de gunicorn para el SGR (se usa con: gunicorn -c deploy/gunicorn.conf.py sgr_project.wsgi).

Todo se puede cambiar con variables de entorno (en /etc/sgr/sgr.env o en el .env); los valores por defecto sirven para una instancia pequeña de EC2 (2 vCPU).

### App `core`: motor de pantallas, acceso y utilidades

#### `core/apps.py`

Configuración de la aplicación `core`.

##### `CoreConfig` — hereda de `AppConfig`

Configuración de la aplicación `core`.

#### `core/models.py`

Modelo base abstracto con las tres fechas de auditoría que heredan todas las tablas del proyecto, y la tabla del registro de auditoría de cambios.

##### `BaseModel` — hereda de `models.Model`

Modelo abstracto del que heredan todas las tablas. Agrega `created_at` (se llena al crear), `updated_at` (se actualiza en cada guardado) y `deleted_at` (borrado lógico: si tiene fecha, el registro está archivado y no se muestra en los listados normales). La propiedad `is_active` indica si no está archivado.

| Campo | Nombre visible | Tipo | Detalle |
|---|---|---|---|
| `created_at` | creado el | DateTimeField |  |
| `updated_at` | actualizado el | DateTimeField |  |
| `deleted_at` | eliminado el | DateTimeField | admite nulo; opcional — Borrado lógico: si tiene fecha, el registro está archivado. |

Opciones del modelo (`Meta`): `abstract` = `True`.

- **`is_active()`** *(propiedad)*: Es verdadero cuando el registro no está archivado (`deleted_at` vacío).

##### `AuditLog` — hereda de `BaseModel`

Registro de auditoría: guarda qué evento ocurrió, sobre qué entidad y registro, el valor anterior y el nuevo, el usuario que lo hizo y la fecha. Se ordena del más reciente al más antiguo.

| Campo | Nombre visible | Tipo | Detalle |
|---|---|---|---|
| `event` | evento | CharField | largo 100 |
| `date` | fecha | DateTimeField |  |
| `affected_entity` | entidad afectada | CharField | largo 50 |
| `record_id` | identificador del registro | PositiveIntegerField |  |
| `previous_value` | valor anterior | TextField | admite nulo; opcional |
| `new_value` | valor nuevo | TextField | admite nulo; opcional |
| `user` | usuario | ForeignKey | relación con `settings.AUTH_USER_MODEL`; nombre inverso `audit_logs`; PROTECT |

Opciones del modelo (`Meta`): `verbose_name` = `'Auditoría'`; `verbose_name_plural` = `'Auditorías'`; `ordering` = `('-date',)`.

- **`__str__()`**: Texto del registro: el evento y la entidad con su identificador.

#### `core/access.py`

Reglas de acceso de las pantallas web: roles, delegación y funcionario.

Son las mismas reglas del Django Admin (core/admin_mixins.py): el superusuario y los roles con alcance sobre todas las delegaciones (el de fábrica es Coordinación) las ven todas; el resto solo ve la delegación de su funcionario. Los resultados se guardan en el request para no repetir consultas dentro de una misma petición.

La persona puede trabajar en más de una delegación. Cuál es la delegación activa se guarda en la sesión (estado temporal de quien tiene la sesión iniciada) y se vuelve a comprobar en el servidor en cada petición (ocultar un botón no es control de acceso): una delegación que ya no está autorizada se olvida sola.

**Funciones**

- **`request_roles(request)`**: Nombres de los perfiles del usuario ("Super Usuario" primero si lo es), ya ordenados.
- **`has_global_role(user)`**: True si alguno de los roles del usuario está activo y da alcance sobre todas las delegaciones.
  
  El alcance sale de la ficha del rol (accounts.RoleProfile), que se edita en el mantenedor de Roles. Un grupo que todavía no tiene ficha se reconoce como siempre, por su nombre: «Coordinación».
- **`is_global_user(request)`**: True si el usuario puede ver todas las delegaciones (superusuario o un rol con ese alcance, como Coordinación).
  
  Es lo que la persona tiene autorizado, no lo que está mirando ahora: quien puede ver todas elige en la franja de arriba si trabaja con todas o con una (ver active_delegation).
- **`request_officer(request)`**: Funcionario vinculado al usuario, o None si no tiene.
- **`home_delegation(request)`**: Delegación de su funcionario, o None si no tiene funcionario.
- **`authorized_delegations(request)`**: Delegaciones entre las que la persona puede elegir en la franja de arriba, en el orden de sus códigos.
  
  Quien ve todas, las ve todas (las que no están archivadas). El resto, la de su funcionario más las que se le agregaron en Control de usuarios (tabla Usuario_Rol_Delegacion, ver accounts/delegations.py).
- **`can_choose_delegation(request)`**: True si hay algo que elegir: más de una delegación autorizada, o «Todas» además de una.
- **`active_delegation(request)`**: Delegación en la que trabaja la persona ahora (la del selector o, si no eligió, la suya); None si ve todas.
  
  Solo quien tiene autorizadas todas las delegaciones puede quedar en None. Para el resto siempre hay una: la de su funcionario o, si no tiene funcionario, la primera que se le agregó. Lanza PermissionDenied si no tiene ninguna (el mismo mensaje que usa el Admin).
  
  Lo guardado en la sesión se revisa cada vez contra lo que hoy está autorizado: si a la persona le quitaron la delegación (o se archivó) mientras tenía la sesión abierta, vuelve a la suya sin que haga nada.
- **`request_delegation(request)`**: Delegación en la que la persona actúa: donde puede cambiar registros y la que ve fija en los formularios.
  
  Es la delegación activa. Quien ve todas y no eligió una (Coordinación, el superusuario) conserva la regla de siempre: la de su funcionario, y None para el superusuario. Lanza PermissionDenied si no tiene delegación (la misma regla y el mismo mensaje que usa el Admin).
- **`default_delegation(request)`**: Delegación con la que parte algo nuevo: en la que trabaja la persona o, si ve todas y no eligió una, la de su funcionario. None si no hay ninguna (el superusuario sin funcionario que ve todas).
- **`delegation_choice(request, raw)`**: Lo que se pidió en el selector: (True, delegación) si está autorizado, (True, None) para «todas» si puede verlas todas, y (False, None) en cualquier otro caso, incluso si alguien envía un id a mano.
- **`remember_delegation(request, delegation)`**: Guarda en la sesión la delegación elegida (None = todas) y olvida lo que este request ya había calculado.
- **`delegation_id_of(obj, lookup)`**: Id de la delegación de un objeto según un lookup como "activity__delegation".
  
  Recorre los pasos intermedios y en el último lee solo el id, para no cargar la delegación completa por cada fila de un listado.

#### `core/roles.py`

Perfiles (roles) del sistema: nombre, ícono y qué puede hacer cada uno.

Los perfiles son los grupos de Django que crea seed_roles; el superusuario no es un grupo y aparece como "Super Usuario". Los textos resumen lo que dan los permisos de accounts/management/commands/seed_roles.py.

También define la matriz de permisos del mantenedor de Roles: qué módulos se muestran, con qué acciones (Ver, Crear, Editar, Eliminar) y cómo se leen esos permisos en la pantalla.

**Funciones**

- **`role_info(name)`**: Datos para mostrar un perfil. Un grupo que no está en la lista sale con un ícono genérico.
- **`sort_key(name)`**: Orden de los perfiles: primero los conocidos, en el orden de la lista; luego el resto.
- **`managed_permissions()`**: Los permisos que muestra la matriz: cada acción de cada módulo que exista en la base de datos.
  
  Los demás permisos que pudiera tener un perfil (de una app que se agregue después, por ejemplo) no se muestran, pero tampoco se pierden al guardar el perfil (ver RoleForm en core/forms.py).
- **`permission_key(permission)`**: ("app.modelo", "acción") de un permiso, por ejemplo ("organization.item", "view").
- **`permission_text(permission)`**: El permiso como se lee en pantalla: "Ver Períodos", "Eliminar Ítems, tipos y sub atenciones".

#### `core/rules.py`

Reglas de formato para los campos de los formularios (RUT, teléfono, correo, nombres, etc.).

Cada regla tiene una expresión regular que debe calzar con todo el texto y el mensaje que ve la persona. Antes de comparar, el texto se arregla con un "normalizador" (quitar espacios de más, quitar los puntos del RUT) y algunas reglas tienen una comprobación extra (el dígito verificador del RUT).

Los formularios aplican estas reglas al guardar (core/forms.py) y además las entregan al navegador en atributos data-* del campo, para avisar antes de enviar el formulario (core/static/core/js/validation.js). Las expresiones, los normalizadores y las comprobaciones tienen el mismo nombre y hacen lo mismo en Python y en JavaScript.

##### `Rule`

Una regla de validación de un campo: nombre, patrón (expresión regular), mensaje, forma de normalizar el texto y una comprobación adicional opcional.

- **`normalize(text)`**: Aplica al texto el normalizador de la regla (quitar espacios sobrantes, dejar el RUT sin puntos, etc.).
- **`apply(text)`**: Devuelve (texto arreglado, mensaje de error o None).
- **`attrs()`**: Atributos data-* que se agregan al campo para que el navegador aplique la misma regla.

**Funciones**

- **`collapse_spaces(text)`**: Quita los espacios de los extremos y deja un solo espacio entre palabras.
- **`normalize_lines(text)`**: Texto de varias líneas: saltos de línea iguales en todos los sistemas (\n) y sin espacios en los extremos.
  
  El navegador envía cada salto de un cuadro de texto como \r\n; aquí queda \n, que es como lo cuenta el navegador al limitar el largo.
- **`rut_check_digit(body)`**: Dígito verificador (módulo 11) de la parte numérica de un RUT, como texto: 0-9 o K.
- **`normalize_rut(text)`**: RUT sin puntos y con guion antes del dígito verificador: 12.345.678-5 queda 12345678-5.
- **`is_valid_rut(text)`**: True si el RUT (ya normalizado) tiene un dígito verificador que calza.
- **`get_rule(name)`**: Entrega la regla con ese nombre.
- **`rut_with_wrong_digit(text)`**: True si el texto está escrito como RUT con guion (11.111.111-2) pero el dígito no calza.

#### `core/forms.py`

Formularios de las pantallas web.

CrudForm es el formulario base de todos los mantenedores: aplica el estilo de Bootstrap, valida los formatos (RUT, teléfono, correo...) con las reglas de core/rules.py y acota las listas desplegables igual que el Admin (formfield_for_foreignkey en core/admin_mixins.py): quien trabaja en una delegación (la suya o la que eligió en la franja de arriba) solo elige registros de esa delegación.

##### `BootstrapFormMixin`

Agrega las clases de Bootstrap a los campos y marca los que traen errores.

- **`style_fields()`**: Pone a cada campo la clase de Bootstrap que le corresponde (casilla, lista o campo de texto), el máximo de los campos decimales según sus dígitos y reduce el alto de las áreas de texto.
- **`is_long_text(field)`** *(método estático)*: True si es un cuadro de texto de varias líneas.
- **`set_text_limits()`**: Largo máximo en el servidor y en el navegador (maxlength) de todos los campos de texto.
  
  Un campo cuya columna es de texto largo (TextField) no trae máximo: se le pone LONG_TEXT_MAX. Y un campo al que un formulario le cambió el widget vuelve a llevar el maxlength de su columna, que el cambio había perdido. Los saltos de línea se cuentan como los cuenta el navegador (uno solo), no como los envía (\r\n).
- **`polish_choices()`**: Textos en español para la opción vacía y fechas legibles en los nombres.
- **`mark_invalid(name)`**: Marca el campo como inválido (una sola vez) para que la página lo pinte y lo avise.
- **`add_error(field, error)`**: Además de registrar el error, marca el campo como inválido en la plantilla.
- **`full_clean()`**: Después de validar el formulario, marca como inválidos los campos que tienen errores.

##### `PortalAuthenticationForm` — hereda de `BootstrapFormMixin`, `AuthenticationForm`

Formulario de inicio de sesión con el estilo de las pantallas.

- **`__init__(*args, **kwargs)`**: Pone los textos del formulario de ingreso («Usuario o correo»), el largo máximo y el enfoque automático.

##### `CrudForm` — hereda de `BootstrapFormMixin`, `forms.ModelForm`

Formulario base de los mantenedores (ver core/crud.py).

- **`__init__(*args, request, crud, **kwargs)`**: Recibe la petición y el CRUD. Oculta las opciones archivadas, limita las listas a la delegación activa, aplica los títulos, ayudas y campos de solo lectura del CRUD y, al final, ejecuta `customize_fields`, los límites de texto, las reglas de validación, las fechas y el estilo.
- **`customize_fields()`**: Gancho: un formulario puede cambiar aquí sus campos antes de que se les dé estilo.
- **`effective_rules()`**: Campo -> regla: las del mantenedor, más la regla «text» para los cuadros de varias líneas que no tengan una.
- **`apply_rules()`**: Pasa a cada campo con regla de formato los atributos data-* que lee core/js/validation.js.
- **`bounds()`**: Gancho: límites propios de este formulario (fechas que dependen de otra, por ejemplo): campo -> {atributo: valor}.
- **`apply_bounds()`**: Agrega al campo los atributos min, max y data-* con que el navegador avisa antes de enviar.
  
  Los límites fijos vienen del mantenedor (Crud.bounds) y los que dependen de otros datos, del gancho bounds(). El servidor repite cada uno en el clean del formulario: esto solo adelanta el aviso.
- **`clean()`**: Aplica las reglas de formato: arregla el texto (espacios, puntos del RUT) o marca el error.
- **`check_unique_names(cleaned)`**: Los campos de crud.unique_names no pueden repetirse sin distinguir mayúsculas ni espacios de más.
  
  La base de datos solo detecta el repetido exacto: «Norte» y «norte» entrarían los dos. Aquí se comparan sin mayúsculas (casefold, que también entiende la Ñ y las tildes) y contra todos los registros, también los archivados, porque restaurar un repetido rompería la regla. Una entrada como ("name", "delegation") pide que el nombre sea único solo dentro de la misma delegación; si el campo de alcance no está en el formulario se toma del registro (el tipo de atención no tiene tipo padre).
- **`not_before(name, other, message)`**: Atributos del navegador: la fecha `name` no puede ser anterior a la del campo `other`.
- **`check_not_before(cleaned, name, other, message)`**: Servidor: la fecha `name` no puede ser anterior a `other` (si están las dos).
- **`until_today(message)`** *(método estático)*: Atributos del navegador: la fecha no puede ser posterior a hoy (el día de Chile, que arma el servidor).
- **`check_not_future(cleaned, name, message)`**: Servidor: la fecha no puede ser posterior a hoy.
- **`check_not_before_day(cleaned, name, day, label)`**: Servidor: la fecha `name` no puede ser anterior a un día dado (el de la atención, por ejemplo).
- **`use_date_inputs()`**: Los campos de fecha usan el selector de fecha del navegador.
- **`current_value(name)`**: Valor actual (pk) de una clave foránea del registro que se edita.
- **`allowed(queryset, name)`**: Registros no archivados, más el que ya tiene guardado el objeto.
- **`hide_archived_choices()`**: Las listas desplegables no ofrecen registros archivados.
- **`limit_to_delegation(delegation)`**: Acota las listas a la delegación en la que trabaja el usuario (misma regla del Admin).

##### `DelegationForm` — hereda de `CrudForm`

Delegación: nombre, dirección, comuna, encargado (se elige de los funcionarios o se escribe), color y estado.

La dirección y la comuna se piden siempre; en la base pueden estar vacías porque hay delegaciones antiguas que no las tenían.

- **`customize_fields()`**: Hace obligatorias la dirección y la comuna, convierte el campo de responsables en un buscador de funcionarios activos y el de color en un selector de color.

##### `RoleForm` — hereda de `CrudForm`

Rol (perfil): nombre, descripción, alcance autorizado, estado y la matriz de permisos.

La matriz tiene una fila por módulo y una columna por acción. Los perfiles del sistema (los que crea seed_roles) no cambian de nombre, de alcance ni de estado: las reglas de acceso cuentan con ellos («Coordinación» ve todas las delegaciones). Para crear, editar o eliminar en un módulo el perfil también debe poder verlo, si no, la pantalla a la que lo lleva al guardar le respondería 403. Los permisos que el perfil tenga y la matriz no muestre se conservan al guardar.

La descripción, el alcance y el estado no son columnas del grupo de Django: se guardan en su ficha (accounts.RoleProfile) cuando el mantenedor termina de guardar el rol (RoleCrud.after_save).

- **`customize_fields()`**: Bloquea el nombre de los roles del sistema y ordena los campos.
- **`clean_permissions()`**: Conserva los permisos que la matriz no maneja y reemplaza solo los que se pueden marcar.
- **`clean()`**: Comprueba que cada permiso de crear, editar o eliminar venga con «Ver» y que el alcance y el estado sean coherentes.
- **`check_scope_and_status(cleaned)`**: No se desactiva un rol que tiene usuarios ni se le quita el alcance a quien lo necesita.
  
  - Desactivar: el rol sigue asignado a esos usuarios; primero hay que cambiárselo (igual que para eliminarlo).
  - Pasar de «Todas las delegaciones» a «Su delegación»: un usuario sin funcionario solo puede existir si algún
    rol o su condición de Super Usuario le da todas las delegaciones; si no, quedaría sin delegación y
    todas las pantallas le responderían 403.

##### `ItemForm` — hereda de `CrudForm`

Ítem, tipo de atención o sub atención: el ítem padre solo puede ser un tipo (un ítem sin padre).

Las reglas entre campos (no ser su propio padre, no cambiar el tipo de un ítem en uso) las revisa ItemRules en core/registry.py.

- **`customize_fields()`**: Pone la descripción como área de texto de dos líneas y limita el ítem padre a los tipos de atención (ítems sin padre) que no estén archivados, sin incluir al propio ítem.

##### `SubAttentionForm` — hereda de `ItemForm`

Sub atención: siempre pertenece a un Tipo de Atención activo.

- **`customize_fields()`**: Hace obligatorio el tipo de atención al que pertenece.

##### `EvidenceForm` — hereda de `CrudForm`

Formulario de evidencias: se sube el archivo, no se escribe su nombre ni sus metadatos.

Los metadatos (nombre original, tipo, tamaño y huella SHA-256) los arma el sistema al guardar.

- **`customize_fields()`**: Cambia el campo de archivo: acepta solo los tipos permitidos, indica el tamaño máximo y, al editar, muestra el nombre del archivo actual.
- **`clean_file_link()`**: Si se subió un archivo, revisa su tipo, su tamaño y que el contenido corresponda a la extensión.

##### `ActivityIntakeForm` — hereda de `CrudForm`

Ingreso de atención : lo que se pide al registrar una atención nueva.

Se pide solo lo que quien atiende sabe en ese momento: quién es la persona (RUT o nombre), el tipo y la sub atención, y lo que pidió. Lo demás se completa solo y no se puede cambiar desde aquí: la fecha es la de hoy, la delegación es en la que trabaja quien atiende (la de su funcionario o la que eligió en la franja de arriba), el responsable es su funcionario y el estado parte en «Registrada». Si trabaja en una delegación que no es la de su funcionario, el responsable se elige entre los funcionarios de esa delegación, porque una actividad exige que el responsable sea de la misma delegación. El identificador (ATN00012) sale del id al guardar. Editar una atención usa el formulario completo de siempre.

El solicitante se escribe en un solo campo: si es el RUT de alguien que está en Beneficiarios, o su nombre exacto, la atención queda vinculada a esa persona; si es un nombre que no está, se guarda como contacto escrito a mano. El Tipo de atención y la Sub atención son dos listas: la segunda solo ofrece las del tipo elegido y, si el tipo no tiene sub atenciones, la atención se guarda con el tipo mismo (el modelo guarda un solo ítem).

- **`customize_fields()`**: Prepara el formulario de ingreso de atención: lista de tipos de atención, texto de ayuda del solicitante y los demás campos (solicitante, sub atención, descripción y datos fijos del perfil).
- **`set_up_description()`**: La descripción es obligatoria al registrar. En la base de datos sigue siendo opcional (editar una atención existente no la exige), así que esta regla vive solo en este formulario.
- **`set_up_requester()`**: Convierte el campo del solicitante en un buscador de beneficiarios por RUT, nombre o dirección.
- **`set_up_sub_attention()`**: Convierte la sub atención en una lista que depende del tipo de atención elegido y muestra cada opción con el nombre de su tipo.
- **`set_up_profile()`**: Perfil fijo: la delegación es el contexto en que trabaja quien atiende y la fecha es la de hoy.
  
  La delegación es la activa: la de su funcionario o la que eligió en la franja de arriba. El responsable es su funcionario cuando este es de esa delegación; si no, se elige uno de la delegación (el modelo exige que coincidan).
- **`clean()`**: Comprueba el solicitante y la combinación de tipo y sub atención.
- **`check_requester(cleaned)`**: Busca al beneficiario con lo escrito (RUT o nombre). Si no lo encuentra o el RUT es inválido agrega el error; si lo encuentra, vincula la atención a esa persona y guarda su nombre como contacto.
- **`check_attention(cleaned)`**: Comprueba que la sub atención pertenezca al tipo elegido. Si el tipo tiene sub atenciones, es obligatoria; si no tiene, la atención queda con el propio tipo como ítem.

##### `UserForm` — hereda de `CrudForm`

Usuario del sistema: cuenta, perfiles, funcionario (que define su delegación) y contraseña.

La contraseña se pide al crear; al editar, dejarla en blanco la conserva. El superusuario no puede quitarse a sí mismo el acceso ni los permisos, para no quedar fuera del sistema.

Las delegaciones adicionales (tabla Usuario_Rol_Delegacion) son las otras delegaciones, además de la de su funcionario, entre las que la persona puede elegir en la franja de arriba.

- **`customize_fields()`**: Arma el formulario de usuario: ofrece los roles activos, hace obligatorias las contraseñas solo al crear, ofrece los funcionarios activos que aún no tienen cuenta, las delegaciones adicionales y deja los campos en orden.
- **`check_extra_delegations(cleaned, sees_everything)`**: Las delegaciones adicionales solo tienen sentido para quien no ve todas; la propia no se repite.
- **`_post_clean()`**: Si se escribió una contraseña, la valida con las reglas de contraseña de Django.
- **`clean()`**: Comprueba usuario y correo repetidos (sin distinguir mayúsculas), que las dos contraseñas coincidan, que tenga al menos un perfil y un funcionario (salvo el Super Usuario y los perfiles con alcance sobre todas las delegaciones), las delegaciones adicionales y que nadie se desactive ni se quite el perfil de Super Usuario a sí mismo.

##### `OfficerForm` — hereda de `CrudForm`

Funcionario, con su acceso al sistema en el mismo formulario (al crear, o al editar si aún no tiene usuario).

Una persona nueva se da de alta una sola vez: sus datos de funcionario y, si va a ingresar al sistema, su usuario, correo, contraseña y perfiles. Si no se llena nada de «Acceso al sistema», solo se crea el funcionario. El nombre de la cuenta sale del nombre del funcionario.

- **`customize_fields()`**: Al crear, quita el identificador institucional del formulario (se genera solo al guardar); al editar lo muestra como campo de solo lectura. Sigue visible y se puede buscar en el listado y en la ficha. Agrega los campos de acceso al sistema solo si el funcionario aún no tiene cuenta y la persona puede crear usuarios; en otro caso los quita.
- **`wants_access()`**: Verdadero si se llenó algún campo de acceso.
- **`clean()`**: Si se pidió acceso, comprueba que el funcionario esté activo, que estén el usuario, el correo, la contraseña y un perfil, que usuario y correo no estén repetidos y que la contraseña cumpla las reglas.

##### `ProfilePhotoForm` — hereda de `BootstrapFormMixin`, `forms.Form`

Foto de perfil de quien tiene la sesión iniciada (pantalla Mi perfil).

- **`__init__(*args, **kwargs)`**: Pone la ayuda con el tamaño máximo de la foto y aplica el estilo.
- **`clean_photo()`**: Revisa la foto: PNG o JPG, tamaño máximo y que el contenido corresponda a la extensión.

  El campo `photo` es un `forms.ImageField`: antes de `clean_photo()`, Pillow comprueba que el archivo sea una imagen real (un archivo que solo imita la firma de un PNG se rechaza con «El archivo no es una imagen válida»).

##### `PortalPasswordChangeForm` — hereda de `BootstrapFormMixin`, `PasswordChangeForm`

Cambio de contraseña de quien tiene la sesión iniciada (pantalla Mi perfil).

- **`__init__(*args, **kwargs)`**: Pone los textos del cambio de contraseña, la ayuda de la política y las reglas de validación del campo nuevo.
- **`validate_password_for_user(user, password_field_name)`**: Aplica las reglas de contraseña al campo `new_password1`.

##### `PeriodForm` — hereda de `CrudForm`

Período: fechas con sentido, umbrales entre 0 y 100 y un solo período vigente a la vez.

- **`bounds()`**: Límite de fecha para el navegador: el término no puede ser anterior al inicio.
- **`clean()`**: Comprueba que el término no sea anterior al inicio, que los días computables vayan de 1 a los días del período, que el umbral colectivo esté entre 0 (sin incluir) y 100, que el ámbar esté entre 0 y 100 y sea menor que el colectivo, que el tope ponderado sea mayor que 0 y que no haya otro período vigente.

##### `GoalForm` — hereda de `CrudForm`

Meta: se asigna a un funcionario o a un cargo, con ponderador válido y sin repetirse.

- **`__init__(*args, **kwargs)`**: Quita del campo del valor objetivo el validador de mínimo del modelo, porque el mínimo se revisa en `clean` con un mensaje propio.
- **`_get_validation_exclusions()`**: Saca el valor objetivo de la validación automática del modelo.
- **`clean()`**: Comprueba que el valor objetivo sea al menos 0,01, que la meta sea de un funcionario o de un cargo (uno solo), que el ponderador esté entre 0 y 100, que la versión parta en 1 y que no exista ya una meta igual (ítem, período y funcionario o cargo).

##### `IndicatorForm` — hereda de `CrudForm`

Indicador: el avance, el cumplimiento y la ponderación no pueden ser negativos.

- **`clean()`**: Comprueba que avance, cumplimiento y ponderación no sean negativos.

##### `AdjustmentForm` — hereda de `CrudForm`

Ajuste: el valor es un porcentaje mayor que 0 y de hasta 100.

- **`clean_percentage_value()`**: El valor del ajuste debe ser mayor que 0 y como máximo 100.

##### `ActivityEditForm` — hereda de `CrudForm`

Actividad (edición): la fecha de una atención ya ocurrida no puede ser futura.

- **`bounds()`**: Límite para el navegador: la fecha de la actividad no puede ser futura.
- **`clean()`**: Comprueba que la fecha de la actividad no sea futura.

##### `CommitmentForm` — hereda de `CrudForm`

Compromiso: se pide en una fecha que ya pasó (o es hoy) y su fecha comprometida no es anterior a esa.

- **`bounds()`**: Límites para el navegador: la fecha de solicitud no es futura y el vencimiento no es anterior a ella.
- **`clean()`**: Comprueba que la fecha de solicitud no sea futura y que el vencimiento no sea anterior a ella.

##### `FollowupForm` — hereda de `CrudForm`

Gestión de atención: sus fechas tienen sentido entre sí y con la fecha de la atención.

- Las fechas de lo que ya ocurrió (la gestión, la visita, la entrega del informe y del beneficio) no son futuras;
  la visita programada sí puede serlo.
- Ninguna fecha es anterior a la de la atención. Esa comparación es solo del servidor: el navegador no conoce la
  fecha de la atención elegida en la lista.
- El informe y el beneficio no se entregan antes de la visita, cuando hay visita.

- **`bounds()`**: Límites para el navegador: las fechas de la gestión no son futuras y las entregas no son anteriores a la visita.
- **`clean()`**: Comprueba que las fechas no sean futuras, que las entregas no sean anteriores a la visita y que ninguna fecha sea anterior a la de la actividad.

##### `PositionForm` — hereda de `CrudForm`

Cargo: la vigencia hasta no es anterior a la vigencia desde.

- **`bounds()`**: Límite para el navegador: la vigencia hasta no es anterior a la vigencia desde.
- **`clean()`**: Comprueba que la vigencia hasta no sea anterior a la vigencia desde.

##### `PositionItemForm` — hereda de `PositionForm`

Ítem de cargo: ponderador entre 0 y 100, tope máximo positivo y vigencia con sentido.

- **`clean()`**: Además de la vigencia, comprueba que el ponderador esté entre 0 y 100 y que el tope máximo sea mayor que 0.

##### `ValidationForm` — hereda de `BootstrapFormMixin`, `forms.ModelForm`

Formulario para revisar una evidencia: decisión, resultado y observación.

La evidencia y el funcionario verificador no se piden aquí: los define la vista (quien revisa es el funcionario de la persona que inició sesión).

- **`__init__(*args, **kwargs)`**: Ordena las decisiones (aprobar, observar, rechazar), hace obligatorio el resultado, pone los límites de texto y aplica el estilo.
- **`clean()`**: Arregla los textos con sus reglas y exige las observaciones cuando la decisión es observar o rechazar.

**Funciones**

- **`password_help()`**: Lista de requisitos de una contraseña nueva: los mismos que revisan los validadores de settings.py.
- **`fold(text)`**: El texto sin mayúsculas, tildes ni espacios de más: «  María  PÉREZ » y «maria perez» quedan iguales.
- **`looks_like_rut(text)`**: True si el texto son números, puntos y guiones (con la K del dígito verificador al final), como un RUT.
- **`find_beneficiary(text)`**: Busca a la persona que escribió quien atiende: por RUT (con o sin puntos y guion) o por su nombre completo.
  
  Devuelve (beneficiario, mensaje de error). Hay tres resultados posibles:
    - la persona está en Beneficiarios: (beneficiario, "");
    - el texto es un nombre que no está: (None, ""). Es un contacto escrito a mano y la atención se guarda
      con ese nombre, sin beneficiario;
    - no se puede decidir: (None, "motivo"). Un RUT mal escrito, un RUT que no está registrado o un nombre que
      tienen varias personas. Con un RUT no se adivina: no se guarda la atención a nombre de otra persona.
- **`delegation_label(delegation)`**: «DEL02 · Nombre» (el código sale del id, igual que en el mantenedor de Delegaciones).
- **`officer_has_account(officer)`**: ¿Este funcionario ya tiene un usuario para ingresar? Un funcionario nuevo (sin guardar) no.
- **`registry_can_add_user(user)`**: ¿Puede esta persona crear usuarios? (permiso de «Control de usuarios»).
- **`split_person_name(name)`**: «María José Pérez Soto» -> («María José», «Pérez Soto»): las dos primeras palabras son el nombre si hay cuatro o más.

#### `core/widgets.py`

Campos de formulario propios: selector de color, buscador de una lista, perfiles con su descripción, delegaciones de un usuario, matriz de permisos y lista que depende de otra.

##### `ColorWidget` — hereda de `forms.TextInput`

Texto #RRGGBB con una muestra del color y, con JavaScript, el selector de color del navegador.

Sin JavaScript queda el campo de texto con su muestra, que también sirve.

- **`get_context(name, value, attrs)`**: Agrega la muestra del color escrito (solo si es un color hexadecimal válido).

##### `LookupWidget` — hereda de `forms.TextInput`

Texto libre con sugerencias y un botón de lupa que abre la lista para elegir de ahí.

options es una lista de (texto a escribir en el campo, detalle que se ve junto a él). search_label es lo que dice el cuadro de búsqueda de la ventana de la lupa ("Buscar por RUT, nombre o dirección").

- **`__init__(attrs, options, search_label)`**: Guarda las opciones de la lista y el texto de la búsqueda.
- **`get_context(name, value, attrs)`**: Enlaza el campo con su lista de opciones (`list`) y entrega las opciones y el texto de la búsqueda.

##### `RolesWidget` — hereda de `forms.CheckboxSelectMultiple`

Casillas de los perfiles de un usuario, cada una con lo que permite hacer ese perfil.

- **`get_context(name, value, attrs)`**: Agrega a cada opción de rol su información (descripción y alcance); si el rol tiene una descripción propia guardada, usa esa.

##### `DelegationsWidget` — hereda de `forms.CheckboxSelectMultiple`

Casillas de las delegaciones adicionales de un usuario, cada una con su color y su código.

Sin JavaScript sirve igual: son casillas normales. El color solo acompaña: la delegación se reconoce por su código y su nombre, que son lo que dice cada casilla.

- **`get_context(name, value, attrs)`**: Agrega a cada opción de delegación su color.

##### `PermissionMatrixWidget` — hereda de `forms.CheckboxSelectMultiple`

Matriz de permisos de un perfil: una fila por módulo y una columna por acción (Ver, Crear, Editar, Eliminar).

Cada casilla es un permiso de Django. Si un módulo no tiene una acción (por ejemplo, la auditoría no se edita), esa celda queda con una raya. Sin JavaScript sirve igual: son casillas normales.

- **`get_context(name, value, attrs)`**: Ordena los permisos en secciones: una fila por módulo y una columna por acción (ver, crear, editar, eliminar), marcando los elegidos y los que no existen.

##### `DependentSelect` — hereda de `forms.Select`

Lista desplegable que depende de otra: solo muestra las opciones del valor elegido en la primera.

depends_on es el id de la lista de la que depende y parent_attr, el atributo de cada registro que dice de cuál depende (por ejemplo "parent_item_id"). Cada opción lleva data-parent (la opción de la primera lista a la que pertenece) y data-name (su nombre corto); con JavaScript solo se ven las del valor elegido (core/static/core/js/widgets.js) y sin JavaScript se ven todas, cada una con el nombre de su padre.

choose_if_options dice que hay que elegir una opción solo cuando la primera lista deja alguna para elegir (la Sub Atención de un Tipo que no tiene sub atenciones se deja vacía). Eso lo hace el navegador con JavaScript; sin JavaScript la lista no marca nada como obligatorio y el servidor revisa lo que corresponde.

- **`__init__(attrs, choices, depends_on, parent_attr, empty_parent, empty_children, cleared_message, choose_if_options)`**: Guarda de qué campo depende la lista, el atributo del padre en cada opción y los mensajes para cuando no hay opciones.
- **`get_context(name, value, attrs)`**: Agrega los atributos `data-*` que usa el JavaScript para filtrar las opciones según el campo del que depende.
- **`create_option(name, value, label, selected, index, subindex, attrs)`**: Agrega a cada opción el identificador de su padre y su nombre.

#### `core/crud.py`

Motor de las pantallas de gestión (listado, ficha, formulario y archivo).

Cada modelo se describe una sola vez con una clase Crud (ver core/registry.py), parecido a un ModelAdmin pero con pantallas propias en Bootstrap. Las reglas de acceso son las mismas del Django Admin:

- cada acción pide el permiso del modelo (view, add, change y delete);
- quien no es superusuario ni de Coordinación solo ve registros de su delegación;
- «Eliminar» pide el permiso delete del modelo: los registros con historia se archivan con deleted_at
  (y se pueden restaurar) y los que no la tienen (los perfiles) se borran de verdad, con confirmación;
- antes de archivar o eliminar se revisan las relaciones: un registro en uso no se toca;
- las listas desplegables de los formularios se acotan a la delegación.

Todos los listados traen búsqueda por palabras (core/search.py), filtros, orden, paginador y el botón para exportar lo que se ve a Excel (core/export.py).

##### `Cell`

Un valor ya formateado para mostrarlo en una tabla o en una ficha.

##### `Row`

Una fila de tabla: el objeto, sus celdas y los enlaces de sus acciones.

##### `Column`

Columna ya resuelta: etiqueta, tipo y la clave con que se puede ordenar.

##### `FilterSpec`

Un filtro del listado: nombre, opciones y valor elegido.

##### `Related`

Tabla de registros relacionados que se muestra en la ficha de un objeto.

##### `RelatedBlock`

Bloque de registros relacionados que se muestra en el detalle de un registro (título, columnas, filas, total y enlace para agregar).

##### `Col`

Columna del listado: un campo del modelo o una ruta como "item__name".

kind puede ser text, badge, bool, date, datetime, number, percent, color o code; si no se indica, se deduce del campo. sort=False desactiva el orden por esa columna. La ruta CODE_COLUMN es la columna del código del registro (ver Crud.code_prefix).

- **`__init__(path, label, sort, kind, link)`**: Guarda la ruta del dato, el título, si se puede ordenar, el tipo de celda y si la celda enlaza al detalle.

##### `Crud`

Describe las pantallas de un modelo. Se subclasea en core/registry.py.

- **`__init__()`**: Completa título, plural y título del listado a partir del modelo, detecta si el modelo usa borrado lógico (hereda de `BaseModel`) y prepara las columnas.
- **`label_of(model_field, fallback)`**: Etiqueta de un campo: la de `labels` si se indicó, y si no la del modelo.
- **`resolve_columns(specs)`**: Convierte la lista de columnas del CRUD en objetos `Col` listos, con título, orden y enlace al detalle en la primera columna.
- **`route_name(action)`**: Nombre de la ruta dentro de core/urls.py, como "actividades_list".
- **`url(action, pk)`**: Dirección de una acción (listado, detalle, nuevo, editar, archivar, eliminar) de este CRUD.
- **`perm(action)`**: Nombre del permiso de Django que pide una acción (por ejemplo `organization.view_officer`).
- **`has_perm(user, action)`**: Verdadero si el usuario tiene el permiso de esa acción.
- **`can_add(user)`**: Verdadero si el CRUD permite crear y el usuario tiene el permiso.
- **`can_archive(user)`**: Archivar y restaurar son parte de «Eliminar»: piden el permiso delete del modelo, no el de editar.
- **`can_delete(user)`**: Borrar de verdad (solo los mantenedores con deletable) también pide el permiso delete.
- **`in_own_delegation(request, obj)`**: True si el registro es de la delegación en la que trabaja el usuario.
  
  Es la delegación activa (la que eligió en la franja de arriba o, si no eligió, la de su funcionario). El superusuario y los mantenedores sin delegación no se limitan. Lanza PermissionDenied si el usuario no tiene delegación, con el mismo mensaje que usa el Admin.
- **`can_change_object(request, obj)`**: Misma regla que has_change_permission del Admin.
  
  Además del permiso del modelo, quien no es superusuario solo puede modificar registros de su propia delegación. Lanza PermissionDenied si el usuario no tiene funcionario (y por lo tanto delegación).
- **`can_archive_object(request, obj)`**: Permiso delete del modelo y, además, que el registro sea de la delegación del usuario.
- **`can_delete_object(request, obj)`**: Verdadero si el usuario puede eliminar y el registro es de su delegación.
- **`can_edit(request, obj)`**: Igual que can_change_object, pero responde False en vez de lanzar PermissionDenied.
  
  Sirve para decidir qué botones mostrar sin romper la pantalla.
- **`can_archive_here(request, obj)`**: can_archive_object sin lanzar PermissionDenied: decide si se muestra el botón Archivar o Restaurar.
- **`can_delete_here(request, obj)`**: can_delete_object sin lanzar PermissionDenied: decide si se muestra el botón Eliminar.
- **`archive_blockers(obj)`**: Motivos (textos) por los que el registro no se puede archivar; una lista vacía si se puede.
  
  Se redefine en cada mantenedor que tiene registros que dependen de otros (un tipo de atención con sub atenciones activas, por ejemplo). Lo revisa el servidor al archivar y la pantalla lo avisa antes.
- **`restore_blockers(obj)`**: Motivos por los que un registro archivado no se puede restaurar todavía.
- **`archive_guard(request, obj)`** (v23): Motivos que dependen de quién archiva, no del registro; en usuarios, «No puedes eliminar tu propia cuenta». `archive_problems(request, obj)` junta estos con `archive_blockers`.
- **`archived_at(obj)` / `set_archived(obj, when)`** (v23): Leen y guardan la marca de archivado. Por defecto es el campo `deleted_at` del modelo; `UserCrud` la guarda en `UserProfile.deleted_at` (`archive_lookup = "profile__deleted_at"`), porque `User` de Django no hereda de `BaseModel`, y además deja la cuenta inactiva.
- **`can_see_archived(request)`** (v23): Quién puede ver los archivados; en usuarios solo el Super Usuario. Habilita la vista `?archivados=solo` («Usuarios eliminados»).
- **`delete_blockers(obj)`**: Motivos por los que el registro no se puede eliminar de verdad. Por defecto revisa las relaciones inversas del modelo (`PROTECT`, `RESTRICT` y `CASCADE`) y, si otros registros lo usan, devuelve «Está en uso en N …»; así el listado puede avisar con SweetAlert2 antes de intentar el borrado. Un mantenedor puede sumar sus propios motivos (los roles: un perfil del sistema, uno con usuarios).
- **`duplicate_message(label, archived)`**: Frase cuando el nombre ya existe sin distinguir mayúsculas; archived dice si el que existe está archivado.
- **`validate_form(form, cleaned)`**: Reglas de negocio entre campos de un formulario de este mantenedor; se agregan con form.add_error.
- **`filter_choices(request, name, model_field)`**: Opciones de un filtro del listado, como lista de (valor, texto); None usa las de siempre.
  
  Sirve para mostrar solo una parte de los registros (en Sub Atención el filtro ofrece solo tipos).
- **`panel_context(request, obj)`**: Datos de la plantilla detail_panel de la ficha.
- **`code_of(obj)`**: Código del registro con su prefijo y su id (DEL02, ROL01...); vacío si el mantenedor no los usa.
- **`get_queryset(request, include_archived)`**: Registros que el usuario puede ver (misma regla de get_queryset del Admin).
- **`is_archived(obj)`**: Verdadero si el registro está archivado.
- **`apply_search(qs, text)`**: Busca cada palabra en alguno de los search_fields.
  
  Todas las palabras deben aparecer (en el mismo campo o en distintos). No importan las mayúsculas ni las tildes ("nunez" encuentra a "Núñez") y un RUT se encuentra se escriba con o sin puntos y guion; ver core/search.py. Si el mantenedor tiene códigos, "DEL02" encuentra el registro con ese código.
  
  Solo se usan las primeras SEARCH_WORDS palabras: cada una agrega condiciones a la consulta y un texto larguísimo la dejaría demasiado grande para la base de datos.
- **`filter_field(name)`**: Campo de un filtro. Puede ser una ruta, como «role_profile__status» (el estado en la ficha de un rol).
- **`build_filters(request)`**: Filtros del listado con sus opciones; ignora valores que no sean opciones válidas.
- **`apply_filters(qs, specs)`**: Aplica al listado los filtros elegidos en la barra de filtros.
- **`scope_summary(request)`**: «Delegación: DEL02 · Delegación Norte» si el listado se limita a una delegación; vacío si trae todas.
- **`filter_summary(text, filters, archived)`**: Texto con la búsqueda y los filtros aplicados, para el encabezado del archivo de Excel.
- **`raw_value(obj, path_)`**: Valor de una columna: el código, el calculado si la columna es de `computed`, y si no, el del modelo.
- **`badge_label(column, raw)`**: Texto de una insignia: el de las opciones del campo del modelo o, en una columna calculada, el de computed_choices.
- **`make_cell(obj, column)`**: Arma la celda de una columna según su tipo: sí/no, etiqueta con color, código, fecha, fecha y hora, número, porcentaje, color o texto. Un valor vacío da una celda vacía.
- **`make_row(request, obj, columns, actions)`**: Arma la fila de un registro: sus celdas (la primera enlazada al detalle cuando corresponde), el enlace al detalle, si está archivado y, si se piden, los enlaces de editar, archivar o restaurar y eliminar según los permisos, con los motivos cuando una acción está bloqueada.
- **`detail_cells(obj)`**: Pares (etiqueta, celda) para la ficha: los campos del modelo en su orden.
  
  Cada valor se muestra igual que en el listado cuando el modelo lo tiene como columna.
- **`extra_detail(obj)`**: Pares (etiqueta, celda) que se agregan al final de la ficha. Se redefine por modelo.
- **`record_meta(obj)`**: Línea de abajo de la ficha: cuándo se creó, se cambió o se archivó el registro.
- **`export_value(obj, column)`**: Valor de una celda para Excel: números y fechas conservan su tipo; el resto sale como texto.
- **`form_class()`** *(propiedad)*: Clase de formulario del CRUD, generada con `modelform_factory` a partir del modelo, la base `form_base` y los campos `form_fields`.
- **`form_class_for(creating)`**: Formulario de alta si el mantenedor tiene uno propio (el ingreso de atención) y, si no, el de siempre.
- **`initial_for(request)`**: Valores iniciales al crear. Acepta ?campo=id para claves foráneas.
  
  Así, desde la ficha de una actividad se abre el formulario de gestión con la actividad ya elegida. El formulario igual valida que el usuario pueda usarla.
- **`initial_values(request)`**: Valores iniciales propios de cada modelo; se redefine en core/registry.py.
- **`extra_actions(request, obj)`**: Botones extra en la ficha: lista de (texto, url, ícono). Se redefine por modelo.
- **`prepare_object(request, obj, creating, form)`**: Último ajuste antes de guardar; la delegación nunca la decide el formulario.
  
  Es la delegación en la que trabaja la persona (la del selector de la franja de arriba). Solo el superusuario que no eligió ninguna puede elegirla en el formulario.
- **`after_save(request, obj, form, creating)`**: Trabajo extra justo después de guardar, dentro de la misma transacción.
- **`new_label()`** *(propiedad)*: Texto de los botones para crear: "Nueva actividad", "Nuevo servicio".
- **`say(kind, obj)`**: Frase de confirmación en femenino o masculino: "Servicio «Vivienda» creado.".

##### `Registry`

Guarda los Crud por slug y arma sus direcciones.

- **`__init__()`**: Crea el diccionario de CRUD por nombre corto (`slug`).
- **`register(crud_class)`**: Registra una clase de CRUD (se usa como decorador).
- **`get(slug)`**: Devuelve el CRUD de un `slug`.
- **`all()`**: Lista todos los CRUD registrados.
- **`urls()`**: Genera las rutas de cada CRUD: listado (o redirección), nuevo, detalle, editar, archivar, restaurar y eliminar, según lo que el CRUD permita.

##### `CrudView` — hereda de `LoginRequiredMixin`, `View`

Base de las vistas: exige sesión iniciada y el permiso del modelo.

- **`dispatch(request, *args, **kwargs)`**: Si la persona ya inició sesión y no tiene el permiso de la acción, responde 403.
- **`get_object(request, pk)`**: Busca el registro solo entre los que el usuario puede ver (404 si no).
- **`breadcrumbs(*extra)`**: Migas de pan: Inicio, el listado (si puede verlo) y los pasos extra.

##### `CrudListView` — hereda de `CrudView`

Listado con búsqueda, filtros, orden, paginador y descarga a Excel (?formato=xlsx).

- **`get_columns(request)`**: Columnas del listado: las de la vista o las del CRUD.
- **`extra_context(request)`**: Datos que una pantalla basada en este listado agrega a la plantilla.
- **`get(request)`**: Arma el listado: lee los filtros, decide si se muestran archivados, aplica búsqueda, filtros y orden (por la columna pedida o el orden del CRUD), descarga Excel si se pide `formato=xlsx`, pagina, prepara los enlaces de orden y las filas, y dibuja la plantilla.
- **`download(request, qs, columns, summary)`**: Descarga en Excel lo mismo que muestra el listado (con su búsqueda, filtros y orden).

##### `CrudDetailView` — hereda de `CrudView`

Pantalla de detalle de un registro con sus datos y los bloques de registros relacionados.

- **`get(request, pk)`**: Arma el detalle: datos del registro, bloques relacionados, qué acciones están permitidas (editar, archivar, restaurar, eliminar) y por qué se bloquean, el panel extra del CRUD, los datos de creación y actualización y las migas de pan.
- **`related_blocks(request, obj)`**: Arma los bloques de registros relacionados que la persona puede ver (por ejemplo las evidencias de una actividad): hasta el límite de filas, con el total y el botón de agregar cuando el registro no está archivado y puede crear.

##### `CrudFormView` — hereda de `CrudView`

Parte común de crear y editar.

Con ?modal=1 el formulario se pide desde la ventana modal de la pantalla (core/static/core/js/crud-modal.js): se responde solo con el contenido de la ventana y, al guardar, con un JSON en vez de una redirección. La cabecera X-Modal le dice al navegador qué llegó: "form" (el formulario) o "saved" (se guardó). Sin JavaScript (o abriendo el enlace en otra pestaña) todo sigue funcionando como páginas normales.

- **`in_modal(request)`**: Verdadero si el formulario se pide para mostrarse en la ventana modal (`?modal=1`).
- **`make_form(request, instance, data, initial)`**: Crea el formulario del CRUD (de creación o de edición) con los datos, los archivos, el registro, los valores iniciales, la petición y el CRUD.
- **`render_form(request, form, obj)`**: Dibuja el formulario: página completa o, si viene `?modal=1`, solo el contenido de la ventana modal. Incluye el título, los botones, la versión del registro (para detectar ediciones simultáneas) y los enlaces de archivar y eliminar según permisos.
- **`finish(request, obj, text)`**: Avisa que se guardó y decide a dónde ir: a la ficha, o a un formulario nuevo si se pidió "agregar otro".
- **`save(request, form, creating)`**: Guarda en una transacción: prepara el objeto (`prepare_object`), lo guarda junto con las relaciones muchos a muchos, ejecuta `after_save` y deja el registro de auditoría (creado, o modificado con los campos que cambiaron).

##### `CrudCreateView` — hereda de `CrudFormView`

Pantalla de «Nuevo».

- **`get(request)`**: Muestra el formulario vacío con los valores iniciales del CRUD y los de la dirección.
- **`post(request)`**: Valida y guarda un registro nuevo; si hay errores vuelve a mostrar el formulario.

##### `ChangeObjectMixin`

Carga un registro visible para el usuario y comprueba que pueda modificarlo.

- **`load(request, pk)`**: Carga el registro y comprueba que la persona pueda cambiarlo.

##### `CrudUpdateView` — hereda de `ChangeObjectMixin`, `CrudFormView`

Pantalla de «Editar».

- **`get(request, pk)`**: Muestra el formulario con los datos del registro; un registro archivado no se edita.
- **`post(request, pk)`**: Valida y guarda los cambios. Un registro archivado no se modifica. Si la versión que la persona abrió ya no es la actual, no guarda y avisa que otra persona lo modificó.

##### `ArchiveObjectMixin`

Carga un registro visible para el usuario y comprueba que pueda archivarlo o restaurarlo.

Archivar y restaurar son parte de «Eliminar»: piden el permiso delete del modelo (no el de editar) y, como todo, solo se alcanzan los registros de la propia delegación (404 si es de otra).

- **`load(request, pk)`**: Carga el registro y comprueba que la persona pueda archivarlo.
- **`blocked_text(verb, obj, reasons)`**: Frase de por qué no se pudo: «No se puede archivar el tipo de atención «Social»: tiene 2 sub atenciones activas.»

##### `CrudArchiveView` — hereda de `ArchiveObjectMixin`, `CrudView`

Pantalla de confirmación para archivar.

- **`get(request, pk)`**: Muestra la confirmación de archivar con los motivos que lo impiden, si los hay. Si ya estaba archivado, avisa y vuelve al detalle.
- **`post(request, pk)`**: Archiva el registro (le pone la fecha de eliminación) y deja la auditoría y el aviso; si hay motivos que lo impiden, no lo hace y los informa.

##### `CrudRestoreView` — hereda de `CrudArchiveView`

Restaura un registro archivado.

- **`post(request, pk)`**: Quita la fecha de eliminación del registro y deja la auditoría y el aviso; si hay motivos que lo impiden, no lo hace y los informa.

##### `CrudDeleteView` — hereda de `CrudView`

Elimina de verdad un registro (solo en los mantenedores con deletable: Roles, Beneficiarios, Territorios, Servicios, Cargos, Tipos de gestión y Agenda). Estos, salvo Roles, también se pueden archivar: el botón de archivar se llama «Archivar» y el de eliminar «Eliminar» (partials/delete_link.html y confirm.js).

GET pide la confirmación y POST elimina. Pide el permiso delete del modelo y se niega si el registro está en uso (delete_blockers). La eliminación queda en la auditoría, y si la base de datos la rechaza porque otros registros dependen de este, no queda nada anotado ni se avisa un éxito falso.

- **`load(request, pk)`**: Carga el registro y comprueba que la persona pueda eliminarlo.
- **`get(request, pk)`**: Muestra la confirmación de eliminación con los motivos que la impiden, si los hay.
- **`post(request, pk)`**: Elimina el registro de verdad si no está en uso; deja la auditoría y el aviso. Si hay motivos o registros que dependen de él (`ProtectedError`), no lo elimina y avisa.

**Funciones**

- **`is_id(text)`**: True si el texto es un número escrito solo con dígitos 0-9 (un id válido en la URL).
- **`number_in_code(word, prefix)`**: El número de un código escrito en la búsqueda ("del02", "DEL2" -> 2); None si la palabra no es un código.
  
  Sirve para encontrar un registro por su código aunque el código no se guarde: se calcula con el id.
- **`version_of(obj)`**: Marca de la última modificación de un registro.
  
  El formulario de edición la lleva escondida; si al guardar ya no coincide, alguien más modificó el registro mientras se editaba. Un modelo sin updated_at (los usuarios de Django) no la lleva y no revisa esto.
- **`field_for_path(model, path_)`**: Último campo de una ruta como "activity__delegation"; None si no es un campo.
- **`detect_kind(model_field)`**: Decide cómo mostrar un campo según su tipo: sí/no, etiqueta (si tiene opciones), fecha y hora, fecha, número o texto.
- **`get_raw(obj, path_)`**: Valor de una ruta como "author_officer__name" (None si algún paso es nulo o no existe).
  
  Si un paso es un método sin parámetros ("get_full_name"), se llama.
- **`query_string(request, drop, **updates)`**: Parámetros actuales de la URL con cambios, para armar enlaces de orden y páginas.
- **`page_size_of(request)`**: Filas por página de los listados: las que la persona eligió en esta sesión, o PAGE_SIZE.
  
  La elección se guarda en request.session (ver set_page_size en core/views.py). Aquí se revisa otra vez contra PAGE_SIZES por si la sesión trajera otro valor. Las opciones son 5, 15 y 30 filas (`PAGE_SIZES`), y 15 el valor por defecto (`PAGE_SIZE`).

#### `core/registry.py`

Mantenedores de las pantallas web: una clase Crud por modelo.

Aquí se define qué columnas, búsquedas, filtros y campos de formulario tiene cada modelo, igual que en los admin.py de cada app. El motor está en core/crud.py.

##### `ActivityCrud` — hereda de `Crud`

CRUD de Atención (actividades): listado, filtros, columnas y reglas de edición.

Atributos principales: `model` = `Activity`; `slug` = `'actividades'`; `icon` = `'bi-clipboard-check'`; `title` = `'Atención'`; `title_plural` = `'Atenciones'`; `gender` = `'f'`; `description` = `'Atenciones y gestiones que cada funcionario registra en terreno.'`; `list_redirect` = `'core:atencion'`; `list_display` = `CODE_COLUMN, date, contact_name, attention_type, sub_attention, author_officer, delegation, status, requires_visit`; `search_fields` = `contact_name, phone, request_description, beneficiary__name, beneficiary__rut`; `form_fields` = `date, item, service, beneficiary, contact_name, phone, request_description, action_taken, status, requires_visit, added_to_pipeline, delegation, author_officer`.

- **`new_label()`** *(propiedad)*: Texto del botón de nuevo: «Registrar atención».
- **`initial_values(request)`**: Con ?beneficiary=<id> (el botón «Nueva» de una fila de Atención) el formulario parte con esa persona.
- **`say(kind, obj)`**: Al crear una atención, el aviso incluye el nombre del contacto y el identificador de la atención.

##### `FollowupCrud` — hereda de `Crud`

CRUD de las gestiones de seguimiento de una actividad.

Atributos principales: `model` = `Followup`; `slug` = `'gestiones'`; `icon` = `'bi-chat-left-text'`; `gender` = `'f'`; `description` = `'Hasta tres gestiones de seguimiento por cada actividad.'`; `list_display` = `activity, sequence_number, management_type, date, result`; `search_fields` = `result, activity__contact_name, activity__beneficiary__name`; `form_fields` = `activity, sequence_number, management_type, date, result, scheduled_visit_date, visit_date, report_delivery_date, benefit_delivery_date`.

- **`initial_values(request)`**: Valores de partida de una gestión nueva: la fecha de hoy y, si viene una actividad visible para la persona, el primer número de gestión (1, 2 o 3) que aún no se usa.

##### `CommitmentCrud` — hereda de `Crud`

CRUD de compromisos de la agenda colectiva.

Atributos principales: `model` = `Commitment`; `slug` = `'agenda'`; `icon` = `'bi-calendar-check'`; `title` = `'Compromiso'`; `title_plural` = `'Compromisos'`; `description` = `'Compromisos con vecinos, organizaciones y la propia municipalidad.'`; `list_display` = `requester, territory, responsible_officer, due_date, status, requester_type`; `search_fields` = `requester, territory__name, description`; `form_fields` = `requester, requester_type, source, request_date, description, territory, due_date, support, status, notes, responsible_officer, delegation`.

- **`initial_values(request)`**: Valores de partida: fecha de solicitud de hoy, el funcionario responsable de la persona y su delegación.

##### `EvidenceCrud` — hereda de `Crud`

CRUD de evidencias: sube el archivo, calcula sus metadatos y muestra su estado de revisión.

Atributos principales: `model` = `Evidence`; `slug` = `'evidencias'`; `icon` = `'bi-file-earmark-check'`; `gender` = `'f'`; `description` = `'Archivos que respaldan cada actividad y su estado de revisión.'`; `list_display` = `unique_code, activity, author_officer, review_status, uploaded_at`; `search_fields` = `unique_code, file_link, activity__contact_name`; `form_fields` = `activity, unique_code, file_link, author_officer`.

- **`initial_values(request)`**: Valores de partida de una evidencia: el funcionario autor y un código único sugerido para la actividad.
- **`prepare_object(request, obj, creating, form)`**: Antes de guardar, si cambió el archivo calcula sus metadatos (nombre, tipo, tamaño, huella). Si se edita una evidencia ya revisada y cambia el archivo o la actividad, la deja otra vez pendiente y avisa.
- **`make_cell(obj, column)`**: Celda del archivo: nombre con enlace para verlo o descargarlo (o aviso si el archivo no está en el sistema) y celda de los metadatos en una sola línea.
- **`extra_actions(request, obj)`**: Agrega el botón «Validar evidencia» cuando la evidencia no está archivada, no la subió la propia persona y esta tiene permiso para validar.

##### `ValidationCrud` — hereda de `Crud`

CRUD del historial de validaciones.

Atributos principales: `model` = `Validation`; `slug` = `'validaciones'`; `icon` = `'bi-patch-check'`; `gender` = `'f'`; `description` = `'Historial de revisiones de las evidencias. Se agregan desde Validar evidencias.'`; `allow_add` = `False`; `allow_change` = `False`; `archivable` = `False`; `list_display` = `evidence, decision, reviewer_officer, result, date`; `search_fields` = `evidence__unique_code, result, notes`.

##### `PeriodCrud` — hereda de `Crud`

CRUD de períodos de medición con sus umbrales.

Atributos principales: `model` = `Period`; `slug` = `'periodos'`; `icon` = `'bi-calendar-range'`; `title` = `'Período'`; `description` = `'Ventanas de medición con sus umbrales de semáforo.'`; `list_display` = `__str__, status, computable_days, collective_threshold, amber_threshold, weighted_cap`; `form_fields` = `start_date, end_date, computable_days, status, collective_threshold, amber_threshold, weighted_cap, parameters_version`.

##### `GoalCrud` — hereda de `Crud`

CRUD de metas de un funcionario o de un cargo.

Atributos principales: `model` = `Goal`; `slug` = `'metas'`; `icon` = `'bi-bullseye'`; `gender` = `'f'`; `description` = `'Objetivos por funcionario o por cargo dentro de un período.'`; `list_display` = `item, officer, position, period, target_value, unit, weight`; `search_fields` = `item__name, officer__name, position__name`; `form_fields` = `item, period, officer, position, target_value, unit, weight, version`.

##### `IndicatorCrud` — hereda de `Crud`

CRUD de indicadores (avance, cumplimiento, semáforo).

Atributos principales: `model` = `Indicator`; `slug` = `'indicadores'`; `icon` = `'bi-speedometer2'`; `description` = `'Avance y cumplimiento de cada meta, con su semáforo.'`; `list_display` = `goal, goal__officer, goal__position, progress, compliance, weighting, status_light, calculated_at`; `search_fields` = `goal__item__name, goal__officer__name`; `form_fields` = `goal, progress, compliance, weighting`.

- **`get_queryset(request, include_archived)`**: Solo se ven los indicadores de metas de la delegación en que se trabaja (la de la franja de arriba).
  
  Las metas por cargo (sin funcionario) las ven todas las delegaciones. Quien ve todas y no eligió una las ve todas.
- **`prepare_object(request, obj, creating, form)`**: Calcula el semáforo del indicador a partir del cumplimiento y los umbrales del período de la meta.

##### `AdjustmentCrud` — hereda de `Crud`

CRUD de ajustes de bonificación o penalización.

Atributos principales: `model` = `Adjustment`; `slug` = `'ajustes'`; `icon` = `'bi-plus-slash-minus'`; `description` = `'Bonificaciones y penalizaciones sobre el resultado de un funcionario.'`; `list_display` = `officer, kind, percentage_value, period, responsible_user, date`; `search_fields` = `officer__name, reason`; `form_fields` = `officer, kind, percentage_value, period, reason`.

- **`prepare_object(request, obj, creating, form)`**: Al crear, deja a quien lo registra como usuario responsable del ajuste.

##### `DelegationCrud` — hereda de `Crud`

CRUD de delegaciones.

Atributos principales: `model` = `Delegation`; `slug` = `'delegaciones'`; `icon` = `'bi-building'`; `gender` = `'f'`; `description` = `'Sectores en que se organiza el trabajo en terreno.'`; `list_display` = `CODE_COLUMN, name, address, commune, managers, scope, color, status`; `search_fields` = `name, address, commune, scope, managers`; `form_fields` = `name, address, commune, managers, scope, color, status`.

- **`initial_values(request)`**: Las delegaciones de la municipalidad parten en la comuna de La Serena; se puede cambiar.
- **`archive_blockers(obj)`**: Una delegación con funcionarios o territorios activos no se archiva: quedarían colgando de una archivada.

##### `TerritoryCrud` — hereda de `Crud`

CRUD de territorios.

Atributos principales: `model` = `Territory`; `slug` = `'territorios'`; `icon` = `'bi-geo-alt'`; `description` = `'Territorios de cada delegación.'`; `list_display` = `name, delegation`; `search_fields` = `name, delegation__name`; `form_fields` = `name, delegation`.

##### `OfficerCrud` — hereda de `Crud`

CRUD de funcionarios; en el alta se puede crear también su acceso al sistema.

Atributos principales: `model` = `Officer`; `slug` = `'funcionarios'`; `icon` = `'bi-person-vcard'`; `description` = `'Personas que registran actividades y responden por metas.'`; `list_display` = `name, institutional_id, delegation, position, access, status`; `search_fields` = `name, institutional_id, delegation__name`; `form_fields` = `institutional_id, name, status, delegation, position`.

- **`extra_detail(obj)`**: Agrega al detalle si el funcionario tiene acceso al sistema y con qué usuario ingresa.
- **`after_save(request, obj, form, creating)`**: Si en el formulario se llenó «Acceso al sistema», crea también la cuenta de esa persona.

##### `PositionCrud` — hereda de `Crud`

CRUD de cargos.

Atributos principales: `model` = `Position`; `slug` = `'cargos'`; `icon` = `'bi-person-badge'`; `description` = `'Cargos con su período de vigencia.'`; `list_display` = `name, valid_from, valid_until`; `search_fields` = `name`; `form_fields` = `name, valid_from, valid_until`.

##### `PositionItemCrud` — hereda de `Crud`

CRUD de ítems de cargo (ponderación por cargo).

Atributos principales: `model` = `PositionItem`; `slug` = `'items-de-cargo'`; `icon` = `'bi-diagram-3'`; `description` = `'Ponderación de cada ítem para cada cargo, con bonificaciones y penalizaciones.'`; `list_display` = `position, item, kind, weight, max_cap, valid_from, valid_until`; `search_fields` = `position__name, item__name`; `form_fields` = `position, item, kind, weight, max_cap, valid_from, valid_until`.

##### `ServiceCrud` — hereda de `Crud`

CRUD de servicios.

Atributos principales: `model` = `Service`; `slug` = `'servicios'`; `icon` = `'bi-card-checklist'`; `description` = `'Servicios municipales que se pueden asociar a una actividad.'`; `list_display` = `name, status`; `search_fields` = `name`; `form_fields` = `name, status`.

##### `ItemRules`

Reglas de integridad de los ítems, comunes a los tres mantenedores (Ítems, Tipo de Atención y Sub Atención).

Un ítem es un tipo de atención (sin ítem padre) o una sub atención (con un tipo como padre). Antes de archivar o cambiar un ítem se mira lo que depende de él, para no dejar registros colgando de algo que ya no está.

- **`archive_blockers(obj)`**: Razones por las que un ítem no se puede archivar: tiene sub atenciones activas, metas activas o está en ítems de cargo.
- **`restore_blockers(obj)`**: Un ítem no se restaura mientras su tipo de atención (ítem padre) siga archivado.
- **`validate_form(form, cleaned)`**: El padre es otro ítem que sea un tipo, y un ítem que ya tiene historia no cambia de padre.

##### `ItemColumns`

Columnas y búsqueda que comparten los mantenedores de ítems.

Atributos principales: `gender` = `'m'`; `search_fields` = `name, description, parent_item__name`; `form_fields` = `name, description, parent_item, calculation_type`.

- **`extra_detail(obj)`**: Agrega al detalle la clase del ítem (tipo o sub atención), su estado y, en los tipos de atención, la cantidad de sub atenciones activas.

##### `ItemCrud` — hereda de `ItemRules`, `ItemColumns`, `Crud`

CRUD de ítems.

Atributos principales: `model` = `Item`; `slug` = `'items'`; `icon` = `'bi-tags'`; `title` = `'Ítem'`; `title_plural` = `'Ítems'`; `description` = `'Todos los ítems que se miden en las metas: tipos de atención y sus sub atenciones.'`; `list_display` = `CODE_COLUMN, name, description, item_class, parent_item, calculation_type, state`.

- **`filter_choices(request, name, model_field)`**: En el filtro por ítem padre ofrece los tipos de atención activos.

##### `AttentionTypeCrud` — hereda de `ItemRules`, `ItemColumns`, `Crud`

Tipo de Atención: los ítems sin padre, con el número de sub atenciones activas que tiene cada uno.

Atributos principales: `model` = `Item`; `slug` = `'tipos-de-atencion'`; `icon` = `'bi-diagram-2'`; `title` = `'Tipo de Atención'`; `title_plural` = `'Tipos de Atención'`; `description` = `'Clases de atención que se ofrecen a los vecinos. Cada una puede tener sus sub atenciones.'`; `list_display` = `CODE_COLUMN, name, description, calculation_type, sub_total, state`; `search_fields` = `name, description`; `form_fields` = `name, description, calculation_type`.

- **`get_queryset(request, include_archived)`**: Solo los ítems sin padre (tipos de atención), con la cantidad de sub atenciones activas.

##### `SubAttentionCrud` — hereda de `ItemRules`, `ItemColumns`, `Crud`

Sub Atención: los ítems que tienen un Tipo de Atención como padre.

Atributos principales: `model` = `Item`; `slug` = `'sub-atenciones'`; `icon` = `'bi-diagram-3'`; `title` = `'Sub Atención'`; `title_plural` = `'Sub Atenciones'`; `description` = `'Atenciones concretas de cada tipo. Cada una pertenece a un Tipo de Atención.'`; `gender` = `'f'`; `list_display` = `CODE_COLUMN, name, parent_item, calculation_type, state`; `form_fields` = `name, parent_item, calculation_type`; `search_fields` = `name, parent_item__name`.

- **`get_queryset(request, include_archived)`**: Solo los ítems que tienen padre (sub atenciones).
- **`filter_choices(request, name, model_field)`**: En el filtro por ítem padre ofrece los tipos de atención activos.

##### `ManagementTypeCrud` — hereda de `Crud`

CRUD de tipos de gestión.

Atributos principales: `model` = `ManagementType`; `slug` = `'tipos-de-gestion'`; `icon` = `'bi-signpost-split'`; `description` = `'Tipos de gestión que se usan en el seguimiento de una actividad.'`; `list_display` = `name`; `search_fields` = `name`; `form_fields` = `name`.

##### `BeneficiaryCrud` — hereda de `Crud`

CRUD de beneficiarios (catálogo compartido entre delegaciones).

Atributos principales: `model` = `Beneficiary`; `slug` = `'beneficiarios'`; `icon` = `'bi-person-lines-fill'`; `description` = `'Personas atendidas. Es un catálogo compartido entre delegaciones.'`; `list_display` = `name, rut, phone, address`; `search_fields` = `name, rut, address`; `form_fields` = `rut, name, phone, address`.

##### `UserCrud` — hereda de `Crud`

Control de usuarios: cuentas, perfiles y funcionario. Solo lo ve quien tiene permisos sobre usuarios.

Atributos principales: `model` = `User`; `slug` = `'usuarios'`; `icon` = `'bi-people'`; `title` = `'Usuario'`; `title_plural` = `'Usuarios'`; `description` = `'Cuentas del sistema con su perfil y su delegación.'`; `archivable` = `False`; `ordering` = `username`; `list_display` = `username, full_name, email, roles, delegation_name, is_active, last_login`; `search_fields` = `username, first_name, last_name, email, groups__name, profile__officer__name, profile__officer__delegation__name`; `form_fields` = `username, first_name, last_name, email, groups, is_active, is_staff, is_superuser`.

- **`extra_detail(obj)`**: Agrega al detalle los perfiles (roles), el funcionario, su delegación, las delegaciones autorizadas y el cargo.
- **`record_meta(obj)`**: Texto con la fecha de creación de la cuenta y su último ingreso (o que todavía no ha ingresado).
- **`prepare_object(request, obj, creating, form)`**: Al editar, guarda los perfiles, el funcionario y las delegaciones que tenía el usuario para la auditoría. Si se escribió una contraseña, la guarda con el hash de Django.
- **`after_save(request, obj, form, creating)`**: Crea o actualiza el perfil del usuario (funcionario y estado), guarda las delegaciones adicionales y, al editar, deja en la auditoría los cambios de perfiles o funcionario y el restablecimiento de contraseña.
- **`save_extra_delegations(request, obj, form, creating)`**: Guarda las delegaciones adicionales marcadas (tabla Usuario_Rol_Delegacion) y deja el cambio en la auditoría.
  
  Se hace después de guardar los perfiles porque hay una fila por cada perfil del usuario y cada delegación.

##### `RoleCrud` — hereda de `Crud`

Roles y permisos: los perfiles (grupos de Django) con la matriz de lo que puede hacer cada uno.

Es el mantenedor de roles: el perfil agrupa permisos (ver, crear, editar y eliminar por módulo) y las vistas preguntan a Django si el usuario los tiene. Un rol no tiene historia propia: se elimina de verdad, salvo los perfiles del sistema y los que todavía tienen usuarios.

Atributos principales: `model` = `Group`; `slug` = `'roles'`; `icon` = `'bi-shield-check'`; `title` = `'Rol'`; `title_plural` = `'Roles'`; `description` = `'Perfiles del sistema y lo que puede hacer cada uno: ver, crear, editar y eliminar por módulo.'`; `archivable` = `False`; `deletable` = `True`; `ordering` = `name`; `list_display` = `CODE_COLUMN, name, scope, status, user_total, permission_total`; `search_fields` = `name, role_profile__description`; `form_fields` = `name, permissions`; `detail_panel` = `'core/crud/role_permissions.html'`.

- **`get_queryset(request, include_archived)`**: Agrega la cantidad de usuarios y de permisos de cada rol.
- **`duplicate_message(label, archived)`**: Mensaje cuando ya existe un rol con ese nombre, aunque cambien mayúsculas o espacios.
- **`delete_blockers(obj)`**: Un rol del sistema no se elimina y uno que tienen usuarios asignados tampoco.
- **`extra_detail(obj)`**: Agrega al detalle la descripción, el alcance autorizado, el estado y si es un perfil del sistema o un rol propio.
- **`record_meta(obj)`**: Aviso de que los roles no se archivan: se eliminan solo si ningún usuario los tiene.
- **`panel_context(request, obj)`**: Los permisos del rol como los muestra la ficha: una fila por módulo con las acciones que tiene.
- **`prepare_object(request, obj, creating, form)`**: Guarda los permisos y los datos que tenía el rol para compararlos en la auditoría.
- **`details_text(details)`** *(método estático)*: Texto con la descripción, el alcance y el estado de un rol, para la auditoría.
- **`after_save(request, obj, form, creating)`**: Crea o actualiza la ficha del rol (descripción, alcance y estado) y deja en la auditoría los datos y los permisos que cambiaron.

##### `AuditLogCrud` — hereda de `Crud`

CRUD de solo lectura del registro de auditoría.

Atributos principales: `model` = `AuditLog`; `slug` = `'auditoria'`; `icon` = `'bi-shield-check'`; `gender` = `'f'`; `title` = `'Registro de auditoría'`; `title_plural` = `'Registros de auditoría'`; `description` = `'Eventos que quedaron registrados en el sistema. Solo consulta.'`; `allow_add` = `False`; `allow_change` = `False`; `archivable` = `False`; `list_display` = `date, event, affected_entity, record_id, user`; `search_fields` = `event, affected_entity, user__username`.

**Funciones**

- **`count_text(total, one, many)`**: «1 meta» o «3 metas».
- **`own_officer_defaults(request, *fields)`**: Valores iniciales con el funcionario del usuario en los campos que se indiquen.
  
  Solo si trabaja en la delegación de su funcionario: con otra delegación elegida en la franja de arriba, las listas de funcionarios son las de esa delegación y su funcionario no está entre ellas.
- **`visible_activity(request, pk)`**: Actividad con ese id solo si el usuario puede verla; None en otro caso.
- **`visible_beneficiary(request, pk)`**: Beneficiario con ese id si el usuario puede verlo: tiene permiso sobre Beneficiarios o ya lo atendió.
- **`attention_type_name(activity)`**: Tipo de atención de una actividad: su ítem padre o, si el ítem es un tipo, el ítem mismo.
- **`sub_attention_name(activity)`**: Sub atención de una actividad: su ítem, si es una sub atención; si es un tipo, queda vacía.
- **`suggest_evidence_code(request, activity)`**: Código sugerido como EVD-NORTE-0003: delegación en mayúsculas y número correlativo.
- **`officer_access_text(officer)`**: Con qué usuario ingresa el funcionario, o «Sin acceso».
- **`item_state(item)`**: Estado de un ítem: no se guarda, sale de deleted_at (archivado = Inactivo).
- **`item_class(item)`**: «Tipo de atención» si el ítem no tiene padre y «Sub atención» si lo tiene.
- **`roles_text(user)`**: Perfiles de un usuario en una línea: "Super Usuario" primero si lo es, y luego sus grupos.
- **`officer_of(user)`**: Funcionario vinculado a un usuario, o None.
- **`full_name_text(user)`**: Nombre y apellido del usuario; si no los tiene, el nombre de su funcionario.
- **`sees_everything(user)`**: True si el usuario ve todas las delegaciones: es Super Usuario o tiene un perfil activo con ese alcance.
- **`delegation_text(user)`**: Delegación del usuario: la de su funcionario (más cuántas otras puede elegir) o, si no tiene funcionario, «Todas» cuando ve todas o las que se le agregaron.
- **`authorized_text(user)`**: Delegaciones entre las que el usuario puede elegir en la franja de arriba, con su código: «DEL01 · Centro, ...».
- **`role_scope(group)`**: Alcance autorizado del rol: «Todas las delegaciones» o «Su delegación» (la de su funcionario).
  
  Sale de la ficha del rol (accounts.RoleProfile), que se edita en este mantenedor; es lo que leen las reglas de acceso (core/access.py). Los perfiles del sistema vienen con el alcance de fábrica: Coordinación ve todas.
- **`role_description(group)`**: Qué puede hacer quien tiene el rol, tal como quedó escrito en su ficha.
- **`role_status(group)`**: «active» o «inactive», según la ficha del rol.

#### `core/views.py`

Pantallas especiales: ingreso, perfil, atención, inicio, validación de evidencias, tablero e informes.

Las pantallas de listado, ficha y formulario de cada modelo están en core/crud.py; aquí van las que no calzan con ese esquema. Todas respetan las mismas reglas de acceso del Django Admin: permisos por modelo y alcance por delegación.

##### `PortalLoginView` — hereda de `auth_views.LoginView`

Ingreso. Usa la plantilla por defecto de LoginView: templates/registration/login.html.

##### `PortalLogoutView` — hereda de `auth_views.LogoutView`

Cierra la sesión. Solo acepta POST, así que el botón de arriba es un formulario.

Cerrar la sesión borra todo lo que había en request.session: otra persona que use el mismo navegador no hereda nada. El aviso se agrega después, ya con la sesión vacía, y se muestra en la pantalla de ingreso a la que se redirige.

- **`post(request, *args, **kwargs)`**: Cierra la sesión y deja el aviso «Cerraste tu sesión.».

##### `AtencionView` — hereda de `CrudListView`

Atención: se busca a la persona por RUT, nombre u otro dato y salen sus atenciones.

Es el listado de Actividades con una pantalla pensada para atender: un cuadro de búsqueda grande, el botón para registrar una atención nueva y, en cada fila, otro para volver a atender a la misma persona. Sin búsqueda muestra las últimas atenciones.

- **`get_columns(request)`**: Columnas del listado de Atención: código, fecha, contacto, RUT, tipo, sub atención, funcionario y estado. Agrega la delegación cuando no hay una delegación activa elegida.
- **`extra_context(request)`**: Entrega el aviso de RUT con dígito verificador incorrecto (según lo escrito en el buscador) y las migas de pan.

**Funciones**

- **`profile(request)`**: Mi perfil: los datos de la cuenta, la foto de perfil y el cambio de contraseña.
- **`profile_photo(request, user_id)`**: Entrega la foto de perfil de un usuario a cualquier persona con la sesión iniciada.
- **`set_page_size(request)`**: Guarda en la sesión cuántas filas por página quiere ver la persona y la devuelve a donde estaba.
  
  Es un dato temporal de la sesión: no es un dato permanente (no va a la base de datos), vale para todos los listados y se olvida al cerrar sesión. Después de guardar, el aviso de éxito (messages) se muestra en la página a la que se redirige.
- **`context_label(delegation)`**: «DEL01 · Delegación Norte», o «Todas las delegaciones» si no hay una delegación.
- **`context_return_url(request)`**: A dónde volver después de cambiar de delegación.
  
  A la misma pantalla de donde se vino, sin su búsqueda ni su página (eran de la delegación anterior). Si la persona estaba mirando o editando un registro, ese registro puede no existir en la delegación nueva: vuelve al listado del módulo. Solo se aceptan direcciones de este mismo sitio y del portal.
- **`set_context(request)`**: Cambia la delegación en la que trabaja la persona (el selector de la franja de arriba).
  
  La elegida se guarda en la sesión (estado temporal de quien inició sesión, como las filas por página), pero a diferencia de ese ajuste decide qué datos se ven y dónde se puede cambiar algo, así que el servidor comprueba cada vez que esté autorizada para esta persona (ocultar una opción no es control de acceso). Un id enviado a mano que no corresponda responde 403 y queda en la auditoría. Todas las pantallas leen la delegación activa desde core/access.py, de modo que listados, filtros, exportaciones y formularios cambian juntos.
- **`current_period()`**: Período vigente; si no hay ninguno, el más reciente.
- **`latest_indicators(goal_ids)`**: Último indicador calculado de cada meta: {id de meta: indicador}.
- **`goals_of(officer, goals)`**: Metas que le corresponden a un funcionario: las suyas y las de su cargo.
- **`mean(values)`**: Promedio sin redondear; None si no hay valores. Con este valor se decide el semáforo.
- **`rounded(value)`**: El valor con un decimal (.05 sube), tal como se muestra en pantalla; None se queda en None.
- **`light_of(value, period)`**: Semáforo de un promedio con los umbrales del período; vacío si no hay promedio.
- **`pick_period(request)`**: Período elegido con ?periodo=<id>; por defecto el vigente. Devuelve (período, opciones).
- **`pick_delegation(request, allow_all)`**: Delegación a mostrar. Devuelve (delegación o None, opciones, puede_elegir).
  
  Sigue la delegación en que trabaja la persona (el selector de la franja de arriba). Solo quien mira todas las delegaciones elige además aquí con ?delegacion=<id> (o "todas" si allow_all); sin delegación asignada se responde el 403 del Admin.
- **`mini_table(crud, request, queryset, paths, limit)`**: Columnas y filas de un listado corto, con las mismas celdas del mantenedor.
- **`goal_lines(goals, indicators)`**: Una línea por meta con su último indicador, lista para dibujar.
- **`dashboard(request)`**: Pantalla de inicio. Cuenta las visitas de la sesión. Si la persona no tiene delegación, avisa. Si tiene funcionario y hay período vigente, muestra el avance de sus metas; si es de alcance global y puede ver indicadores, cuenta los semáforos (verde, ámbar, rojo) y las metas sin indicador. Arma las tarjetas de pendientes (atenciones del mes, visitas por realizar, evidencias por revisar, compromisos abiertos y vencidos), los accesos directos según permisos y las tablas de atenciones recientes y compromisos próximos.
- **`reviewable_evidence(request, exclude_own)`**: Mantenedor de evidencias y las evidencias que el usuario puede revisar.
  
  Quien revisa solo ve las de la delegación en que trabaja: la que eligió arriba o, si no eligió, la de su funcionario, aunque además sea de Coordinación (así lo hace el formulario de validación del Admin). El superusuario que mira todas las ve todas. Sin delegación se responde 403.
- **`evidence_file(request, pk)`**: Entrega el archivo de una evidencia. Solo a quien puede ver esa evidencia (permiso y delegación).
- **`validate_list(request)`**: Lista las evidencias pendientes de revisión que la persona puede revisar (ordenadas por fecha de subida), marca las que ya fueron observadas y muestra las últimas validaciones registradas.
- **`validate_evidence(request, pk)`**: Formulario para revisar una evidencia. Rechaza a quien no tiene funcionario asociado (salvo superusuario) y a quien intenta validar una evidencia que él mismo subió. Al guardar, en una transacción registra la validación, cambia el estado de la evidencia según la decisión y deja el registro de auditoría. Si no, muestra la evidencia, su archivo y el historial de validaciones.
- **`officer_results(officers, goals, indicators, period)`**: Resultados por funcionario: sus metas, el cumplimiento promedio y el semáforo.
- **`delegation_board(request)`**: Tablero de una delegación para un período: toma los funcionarios activos de la delegación, calcula el resultado de cada uno con el último indicador de sus metas, el promedio de la delegación con su semáforo, el conteo por semáforo y las tarjetas de evidencias pendientes, compromisos abiertos y actividades del período (según permisos).
- **`safe_cell(value)`**: Evita que Excel interprete como fórmula un texto que parte con =, +, - o @.
- **`report_rows(delegation, period, with_adjustment)`**: Una fila por funcionario activo: actividades, evidencias, cumplimiento y, si se pide, ajuste.
- **`report_csv(rows, period, with_adjustment)`**: Informe en CSV listo para Excel en español: separador «;» y coma decimal.
- **`report_xlsx(request, rows, period, delegation, with_adjustment)`**: Informe en Excel con los mismos datos que la tabla de la pantalla.
- **`reports(request)`**: Informe de un período por delegación (o todas): una fila por funcionario con sus actividades y evidencias aprobadas, pendientes y rechazadas, y el ajuste cuando la persona puede verlo. Con `?formato=csv` o `?formato=xlsx` descarga el informe en ese formato; si no, lo muestra con totales.
- **`administration(request)`**: Portada de Administración: los mantenedores a los que el usuario puede entrar.

#### `core/urls.py`

Rutas de las pantallas web: ingreso y salida, perfil, Atención, dashboard, filas por página, cambio de delegación, archivo y validación de evidencias, tablero de delegación, informes y administración, junto con las redirecciones a los formularios de «Nuevo» más usados y todas las rutas de los mantenedores que genera el registro de CRUD.

| Ruta | Vista | Nombre |
|---|---|---|
| `/` | `views.PortalLoginView.as_view()` | `login` |
| `/salir/` | `views.PortalLogoutView.as_view()` | `logout` |
| `/perfil/` | `views.profile` | `profile` |
| `/perfil/foto/<int:user_id>/` | `views.profile_photo` | `profile_photo` |
| `/atencion/` | `views.AtencionView.as_view(crud=registry.get('actividades'))` | `atencion` |
| `/dashboard/` | `views.dashboard` | `dashboard` |
| `/filas/` | `views.set_page_size` | `page_size` |
| `/contexto/` | `views.set_context` | `set_context` |
| `/evidencias/<int:pk>/archivo/` | `views.evidence_file` | `evidence_file` |
| `/evidencias/validar/` | `views.validate_list` | `validate_list` |
| `/evidencias/<int:pk>/validar/` | `views.validate_evidence` | `validate_evidence` |
| `/tablero/delegacion/` | `views.delegation_board` | `delegation_board` |
| `/informes/` | `views.reports` | `reports` |
| `/administracion/` | `views.administration` | `administration` |
| `/actividades/registrar/` | `RedirectView.as_view(pattern_name='core:actividades_create')` | `registrar_actividad` |
| `/evidencias/cargar/` | `RedirectView.as_view(pattern_name='core:evidencias_create')` | `cargar_evidencia` |
| `/catalogo/servicios/` | `RedirectView.as_view(pattern_name='core:servicios_list')` | `catalogo_servicios` |

Además agrega, al final, las rutas de todos los mantenedores registrados en `core/registry.py` (listado, nuevo, detalle, editar, archivar, restaurar y eliminar de cada uno).

#### `core/menus.py`

Menú lateral: solo muestra lo que el usuario tiene permiso de abrir.

Arriba van "Atención" y "Dashboard"; después, los grupos (Operación, Resultados y Administración). Cada entrada apunta a un mantenedor (por su slug en core/registry.py) o a una pantalla especial (por el nombre de su ruta). Las entradas sin permiso no se dibujan y los grupos que quedan vacíos tampoco.

##### `MenuItem`

Una entrada del menú: texto, dirección, ícono, descripción y si está activa.

##### `MenuGroup`

Un grupo del menú lateral: título, ícono, secciones con sus entradas y si está abierto.

- **`items()`** *(propiedad)*: Todas las entradas del grupo, sin las secciones.
- **`open()`** *(propiedad)*: Verdadero si el grupo tiene la página actual o está abierto por defecto.

**Funciones**

- **`crud_entry(slug, label)`**: Entrada de un mantenedor; se muestra si el usuario puede ver ese modelo.
- **`page_entry(route, label, icon, perm)`**: Entrada de una pantalla especial; se muestra si el usuario tiene el permiso.
- **`admin_site_entry(user)`**: Entrada «Panel de administración» (Django Admin) para quienes son personal (`is_staff`).
- **`dashboard_entry(user)`**: Entrada «Dashboard».
- **`hub_item()`**: Portada de Administración, que reúne todo lo que el usuario puede administrar.
- **`visible_entries(user)`**: Las entradas de arriba y los grupos del menú, solo con lo que el usuario puede abrir.
- **`build_menu(request)`**: Menú del usuario con la entrada actual marcada (la de dirección más específica).

#### `core/context_processors.py`

Datos que todas las plantillas necesitan: menú, usuario, delegación y perfiles.

**Funciones**

- **`photo_url(user)`**: Dirección de la foto de perfil, o vacío si la persona no subió una. El número de versión evita ver la foto vieja.
- **`delegation_scope(request)`**: La delegación en la que trabaja la persona, lista para la franja de arriba y la barra lateral.
  
  Devuelve un diccionario con el código y el nombre de la delegación activa (o «Todas las delegaciones»), si la persona puede elegir otra (el selector muestra solo las autorizadas), las opciones del selector y los colores. Nunca lanza PermissionDenied: las pantallas de error también la usan y una persona sin delegación asignada solo ve «Sin delegación asignada».
- **`portal(request)`**: Datos que ven todas las plantillas: nombre, subtítulo e institución. Con sesión iniciada agrega el menú, el usuario, su funcionario, su foto, su delegación, sus roles y su alcance.

#### `core/middleware.py`

Middleware de las pantallas web.

##### `PortalLocaleMiddleware`

Deja las pantallas web en español y con la hora de Chile.

Solo actúa fuera de /admin/: el Django Admin sigue con el idioma y la zona horaria de settings.py.

- **`__init__(get_response)`**: Guarda la función que sigue en la cadena de middleware.
- **`__call__(request)`**: Fuera de `/admin/` atiende la petición con el idioma y la zona horaria del portal.

##### `PortalNoCacheMiddleware`

Pide al navegador que no guarde las pantallas web.

Muestran datos de la sesión iniciada: así, después de cerrar sesión, el botón «Atrás» no vuelve a mostrar una pantalla con datos. No toca /admin/ (que ya lo hace por su cuenta) ni los archivos estáticos.

- **`__init__(get_response)`**: Guarda la función que sigue en la cadena de middleware.
- **`__call__(request)`**: Fuera de `/admin/` y de los archivos estáticos, agrega a la respuesta las cabeceras para que el navegador no guarde las pantallas.

#### `core/ui.py`

Ayudas de presentación: colores de estado, íconos y formato de fechas y números.

**Funciones**

- **`tone_for(value)`**: Tono e ícono de un valor guardado; gris sin ícono si no está en la tabla.
- **`light_for_compliance(compliance, collective_threshold, amber_threshold)`**: Color de semáforo para un porcentaje, con los umbrales del período.
  
  Verde desde el umbral colectivo, ámbar desde el umbral ámbar y rojo bajo eso.
- **`fmt_date(value)`**: Fecha como 06/10/2026.
- **`fmt_datetime(value)`**: Fecha y hora local como 06/10/2026 14:35.
- **`fmt_number(value)`**: Número con coma decimal y punto para los miles (1.250,5); sin ceros de más.
- **`humanize_dates(text)`**: Cambia las fechas 2026-10-06 de un texto por 06/10/2026.
  
  Los __str__ de los modelos (Actividad, Período, Meta) escriben la fecha en formato ISO; en pantalla se muestran igual que el resto de las fechas.
- **`initial_capital(text)`**: Pone en mayúscula solo la primera letra, sin tocar el resto (RUT sigue siendo RUT).

#### `core/colors.py`

Colores de las delegaciones: valida el formato y elige un texto legible sobre el fondo.

**Funciones**

- **`clean_color(value)`**: El color escrito como #RRGGBB en minúsculas; si el valor no sirve, el color por defecto.
  
  Los colores se usan dentro de estilos en las páginas, así que nunca se escribe en ellas un texto que no sea exactamente un color.
- **`luminance(color)`**: Luminancia relativa (de 0 a 1) de un color #RRGGBB, según la fórmula de WCAG 2.
- **`contrast(color_a, color_b)`**: Razón de contraste entre dos colores (de 1 a 21). Para texto normal se pide 4,5 o más.
- **`palette(value)`**: Fondo, texto y sombreado de un bloque que lleva el color de una delegación.
  
  El texto es blanco u oscuro, el que más contraste tenga con el fondo. El sombreado sirve para las etiquetas que van encima: oscurece los fondos con texto blanco y aclara los que llevan texto oscuro, de modo que el texto no pierde contraste.

#### `core/search.py`

Búsqueda por palabras: no distingue mayúsculas ni tildes y entiende RUT y teléfonos.

Cada palabra se convierte en una expresión regular que se compara con los campos de búsqueda de la pantalla (iregex). Así "nunez" encuentra a "Núñez", y "11111111" o "11.111.111-1" encuentran el mismo RUT, escrito con o sin puntos y guion. La expresión solo usa clases de caracteres y signos de interrogación, que entienden igual SQLite, MySQL y PostgreSQL.

**Funciones**

- **`plain_letter(char)`**: La letra sin tilde y en minúscula ("É" -> "e", "ñ" -> "n").
- **`letter_pattern(char)`**: Cómo se busca una letra: con todas sus variantes si las tiene, y si no, tal cual.
- **`number_like(word)`**: Los números del texto si la palabra es un RUT o un teléfono (solo dígitos, puntos y guion).
- **`word_pattern(word)`**: Expresión regular de una palabra de búsqueda.

#### `core/export.py`

Exportación de listados a Excel (.xlsx) con openpyxl.

**Funciones**

- **`sheet_title(text)`**: Nombre de hoja válido para Excel: hasta 31 caracteres y sin \ / ? * [ ] :
- **`file_name(slug)`**: Nombre del archivo, por ejemplo actividades-2026-10-06.xlsx.
- **`as_excel_value(value)`**: Valor listo para una celda: fechas y números quedan como tales, no como texto.
- **`build_workbook(title, headers, kinds, rows, summary, user, total)`**: Arma el libro: título, quién lo generó y con qué filtros, y la tabla con sus encabezados.
  
  headers y kinds van en el orden de las columnas; rows es una lista de listas de valores; summary es el texto de los filtros aplicados y total la cantidad de filas del resultado (si es mayor que las filas exportadas, se avisa).

#### `core/uploads.py`

Archivos que suben las personas: evidencias y fotos de perfil.

Se aceptan pocos tipos, se revisa que el contenido corresponda a la extensión (no basta con el nombre) y se limita el tamaño. Los archivos se guardan en MEDIA_ROOT con un nombre propio, sin usar el que trae el computador de quien sube, y se entregan solo mediante una vista que revisa el permiso (core/views.py), nunca por una URL pública.

Qué pasa con un archivo reemplazado o sin registro: la foto anterior se borra al cambiarla o quitarla; el archivo anterior de una evidencia no se borra (queda como rastro) y archivar una evidencia no toca su archivo. No hay limpieza automática. La política completa está en el README, sección «Archivos subidos: límites y política».

**Funciones**

- **`extension_of(name)`**: Extensión de un nombre de archivo en minúsculas y sin el punto.
- **`is_image(name)`**: Es verdadero si el archivo es PNG o JPG.
- **`content_type_of(name)`**: Tipo de contenido (MIME) según la extensión.
- **`type_label(name)`**: Nombre corto del tipo de archivo («PDF», «Imagen», etc.).
- **`readable_size(size)`**: Tamaño en bytes escrito como bytes, KB o MB.
- **`accepted_text(types)`**: Lista de tipos aceptados escrita como texto («DOCX, PDF, PNG o XLSX»).
- **`check_upload(uploaded, types, max_mb)`**: Revisa extensión, tamaño y contenido de un archivo subido. Lanza ValidationError con el motivo.
- **`sha256_of(uploaded)`**: Huella SHA-256 del contenido de un archivo subido.
- **`describe_file(uploaded)`**: Texto de metadatos que se guarda solo con la evidencia: nombre original, tipo, tamaño y huella.
- **`evidence_path(instance, filename)`**: evidencias/2026/EV-0001-ab12cd34.pdf: el nombre lo arma el sistema.
- **`photo_path(instance, filename)`**: Ruta con la que se guarda la foto de perfil: carpeta `fotos/` y un nombre con el id del usuario y un código al azar.

#### `core/audit.py`

Registro de auditoría de las acciones que se hacen desde las pantallas web.

**Funciones**

- **`log_event(user, event, obj, previous, new)`**: Guarda un evento sobre un registro: quién, qué pasó y cómo quedó.
  
  affected_entity lleva el nombre de la clase del modelo ("Activity", "Evidence"). Devuelve el registro de auditoría creado (su id sirve para reconocer un evento más adelante).
- **`log_export(user, source, rows, summary)`**: Deja anotado que alguien descargó un listado: de qué, cuántas filas y con qué filtros.
  
  source es el modelo del listado (o un nombre, como "Informe"). No hay un registro puntual, así que el número de registro queda en 0.
- **`describe(field, value)`**: Texto de un valor guardado tal como se lee en pantalla ("Pendiente", "Delegación Norte").
- **`changed_fields(before, after)`**: Compara dos copias del mismo registro y lista lo que cambió.
  
  Devuelve tuplas (nombre del campo, valor anterior, valor nuevo), con los valores ya escritos como texto.

#### `core/health.py`

Revisión de estado del servicio (/salud/): para el balanceador, para una persona o para las evidencias.

No pide sesión ni muestra secretos: solo dice si el servicio, la base de datos y la caché responden, y qué versión está desplegada (archivo VERSION del proyecto y, si existe, COMMIT, que escribe deploy/actualizar.sh).

**Funciones**

- **`_leer(nombre)`**: Lee el texto de un archivo de la carpeta del proyecto (por ejemplo `VERSION` o `COMMIT`); devuelve vacío si no existe.
- **`salud(request)`**: Vista `/salud/`: responde en JSON si el servicio, la base de datos y la caché funcionan, con la versión, el commit y el entorno. Responde 503 si algo falla.

#### `core/templatetags/core_ui.py`

Etiquetas y filtros de plantilla para las pantallas web.

**Funciones**

- **`escudo_url()`**: Dirección del escudo oficial si su archivo ya está en core/static/core/img/; vacío si todavía no.
- **`fdate(value)`**: Fecha como 06/10/2026.
- **`fdatetime(value)`**: Fecha y hora local como 06/10/2026 14:35.
- **`fnumber(value)`**: Número con coma decimal y punto de miles.
- **`hd(value)`**: Texto de un registro con sus fechas como 06/10/2026.
- **`tone(value)`**: Tono de color (ok, warn, bad, info, neutral) de un valor guardado.
- **`tone_icon(value)`**: Ícono de Bootstrap Icons de un valor guardado.
- **`light_label(value)`**: Verde, Ámbar o Rojo a partir del valor guardado del semáforo.
- **`_to_decimal(value, default)`**: Convierte un valor en número decimal; si no se puede, devuelve el valor por defecto.
- **`meter(value, light, collective, amber, label, compact)`**: Barra de cumplimiento con marcas en los umbrales ámbar y colectivo del período.
  
  El ancho se limita a 0-100 %, pero el texto muestra el valor real (puede pasar de 100). Los valores salen como texto para que el idioma no les cambie el punto por coma dentro de los estilos.

#### `core/admin_mixins.py`

Piezas comunes de los Django Admin: filtro de registros archivados, acción de archivar, y dos mixins (borrado lógico y alcance por delegación).

##### `ArchivedRecordsFilter` — hereda de `admin.SimpleListFilter`

Filtro de la lista del Admin para incluir los registros archivados.

- **`lookups(request, model_admin)`**: Opción «Incluir archivados».
- **`choices(changelist)`**: Opciones del filtro: ocultar archivados (por defecto) o incluirlos.
- **`queryset(request, queryset)`**: No filtra aquí; el mixin de borrado lógico decide qué filas se ven.

##### `SoftDeleteAdminMixin`

Mixin del Admin para tablas con borrado lógico: oculta los archivados, ofrece la acción de archivar, muestra las fechas de creación y actualización de solo lectura y quita el permiso de eliminar de verdad.

- **`_showing_archived(request)`**: Es verdadero si la persona pidió ver también los archivados.
- **`get_list_filter(request)`**: Agrega el filtro de archivados a los filtros de la lista.
- **`get_queryset(request)`**: Oculta los registros archivados salvo que se pida verlos.
- **`get_list_display(request)`**: Agrega la columna de fecha de eliminación cuando se ven los archivados.
- **`has_delete_permission(request, obj)`**: Siempre falso: los registros se archivan, no se borran.

##### `DelegationScopedAdminMixin` — hereda de `SoftDeleteAdminMixin`

Mixin del Admin que limita lo que se ve y se edita a la delegación del usuario (salvo el superusuario y los roles con alcance sobre todas).

- **`get_queryset(request)`**: Si la persona no es superusuaria ni tiene un rol con alcance sobre todas las delegaciones, filtra los registros por su delegación.
- **`formfield_for_foreignkey(db_field, request, **kwargs)`**: En los campos de relación ofrece solo las opciones de la delegación de la persona (delegación, funcionarios, territorios, actividades y evidencias).
- **`save_model(request, obj, form, change)`**: Al guardar, si la persona no es superusuaria, deja su delegación en el registro que tenga ese campo.
- **`has_change_permission(request, obj)`**: Permite cambiar un registro solo si pertenece a la delegación de la persona.

**Funciones**

- **`archive_selected(modeladmin, request, queryset)`**: Acción del Admin: archiva los registros elegidos poniéndoles fecha de eliminación.

#### `core/admin_utils.py`

**Funciones**

- **`get_user_delegation(request)`**: Delegación de la persona según su funcionario; None para el superusuario.
  
  La usa el Django Admin, que no tiene selector de delegación: allí cada persona trabaja en la de su funcionario. Las pantallas web usan core.access.request_delegation, que además respeta la delegación elegida en la franja de arriba.

#### `core/admin.py`

Registro de la tabla de auditoría en el Django Admin, solo de lectura.

##### `AuditLogAdmin` — hereda de `admin.ModelAdmin`

Muestra la auditoría con búsqueda y filtros, solo de lectura: no se puede agregar, cambiar ni eliminar.

- **`has_add_permission(request)`**: Siempre falso: la auditoría la escribe el sistema.
- **`has_change_permission(request, obj)`**: Siempre falso.
- **`has_delete_permission(request, obj)`**: Siempre falso.

### App `accounts`: usuarios, perfiles y recuperación de contraseña

#### `accounts/apps.py`

Configuración de la aplicación `accounts`; al iniciar registra las señales (`accounts.signals`).

##### `AccountsConfig` — hereda de `AppConfig`

Configuración de la aplicación; en `ready()` importa las señales.

- **`ready()`**: Al arrancar, carga las señales de `accounts/signals.py`.

#### `accounts/models.py`

Modelos de acceso: el perfil de cada usuario (vínculo con su funcionario y su foto), la ficha de cada rol (descripción, alcance y estado) y la tabla que asigna roles a un usuario por delegación. Incluye ayudas para leer los datos de un rol.

##### `UserProfile` — hereda de `BaseModel`

Perfil de un usuario de Django. Lo une con su funcionario (uno a uno, vacío solo en cuentas técnicas como el superusuario), guarda su estado (activo o inactivo) y su foto de perfil.

| Campo | Nombre visible | Tipo | Detalle |
|---|---|---|---|
| `user` | usuario | OneToOneField | relación con `settings.AUTH_USER_MODEL`; nombre inverso `profile`; CASCADE |
| `officer` | funcionario | OneToOneField | relación con `Officer`; nombre inverso `user_profile`; PROTECT; admite nulo; opcional — Vacío solo para cuentas técnicas (superusuario) sin un funcionario asociado en terreno. |
| `status` | estado | CharField | largo 20; con opciones; por defecto `Status.ACTIVE` |
| `photo` | foto de perfil | ImageField | largo 255; admite nulo; opcional; sube archivo; requiere Pillow |

Opciones del modelo (`Meta`): `verbose_name` = `'Perfil de usuario'`; `verbose_name_plural` = `'Perfiles de usuario'`.

Opciones de `Status`: `active` (Activo), `inactive` (Inactivo).

- **`clean()`**: No permite vincular un usuario a un funcionario que no esté activo.
- **`__str__()`**: Nombre de usuario y funcionario vinculado.

##### `RoleProfile` — hereda de `BaseModel`

Ficha de un rol (un `Group` de Django): descripción, alcance autorizado (su delegación o todas) y estado. El alcance es lo que decide si un rol ve todas las delegaciones.

| Campo | Nombre visible | Tipo | Detalle |
|---|---|---|---|
| `group` | rol | OneToOneField | relación con `Group`; nombre inverso `role_profile`; CASCADE |
| `description` | descripción | CharField | largo 255; por defecto `''`; opcional |
| `scope` | alcance autorizado | CharField | largo 10; con opciones; por defecto `Scope.OWN` |
| `status` | estado | CharField | largo 20; con opciones; por defecto `Status.ACTIVE` |

Opciones del modelo (`Meta`): `verbose_name` = `'Ficha de rol'`; `verbose_name_plural` = `'Fichas de roles'`.

Opciones de `Scope`: `own` (Su delegación), `all` (Todas las delegaciones).

Opciones de `Status`: `active` (Activo), `inactive` (Inactivo).

- **`__str__()`**: Nombre del rol y su alcance.

##### `UserRoleDelegation` — hereda de `BaseModel`

Asigna un rol de un usuario a una delegación. Permite que una persona trabaje en más de una delegación con el mismo rol. Es única por usuario, rol y delegación.

| Campo | Nombre visible | Tipo | Detalle |
|---|---|---|---|
| `user` | usuario | ForeignKey | relación con `settings.AUTH_USER_MODEL`; nombre inverso `role_delegations`; CASCADE |
| `role` | rol | ForeignKey | relación con `Group`; nombre inverso `user_delegations`; CASCADE |
| `delegation` | delegación | ForeignKey | relación con `Delegation`; nombre inverso `user_roles`; CASCADE; admite nulo |

Opciones del modelo (`Meta`): `verbose_name` = `'Usuario, rol y delegación'`; `verbose_name_plural` = `'Usuarios, roles y delegaciones'`; `ordering` = `('user_id', 'role_id', 'delegation_id')`; `constraints` = `[models.UniqueConstraint(fields=('user', 'role', 'delegation'), name='uq_usuario_rol_delegacion')]`.

- **`clean()`**: Comprueba que el usuario tenga el rol antes de asignarle una delegación con él.
- **`__str__()`**: Usuario, rol y delegación.

**Funciones**

- **`role_defaults(name)`**: Valores de partida de la ficha de un rol según su nombre: descripción de fábrica, alcance (todas las delegaciones solo para el rol global) y estado activo.
- **`role_details(group)`**: Devuelve los datos de un rol: los de su ficha si existe o, si todavía no tiene ficha, los de fábrica según su nombre.
- **`group_is_global(group)`**: Es verdadero si el rol está activo y tiene alcance sobre todas las delegaciones.

#### `accounts/signals.py`

Señales de las cuentas: cada rol (grupo de Django) nace con su ficha, y cada ingreso parte con su delegación.

**Funciones**

- **`create_role_profile(sender, instance, created, raw, **kwargs)`**: Al crearse un grupo (desde Roles, el Admin o seed_roles) se le crea su ficha con los valores de siempre.
  
  Si el rol se crea desde el mantenedor de Roles, el formulario guarda enseguida la descripción, el alcance y el estado que eligió la persona (ver RoleCrud.after_save en core/registry.py).
- **`start_in_own_delegation(sender, request, **kwargs)`**: Cada ingreso parte con la delegación de siempre (el estado temporal de la sesión no pasa de un ingreso a otro). La que se elige en la franja de arriba vale mientras dure la sesión.

#### `accounts/delegations.py`

Delegaciones adicionales de un usuario: lectura y escritura de la tabla Usuario_Rol_Delegacion.

Las lee core/access.py para armar el selector de delegaciones de la franja de arriba y las escribe Control de usuarios (core/registry.py) con la lista que se marca en el formulario.

**Funciones**

- **`effective_rows(user)`**: Filas de la tabla que hoy le dan una delegación al usuario.
  
  Cuenta la fila de un rol que el usuario todavía tiene y que está activo (un rol inactivo no da alcance), sobre una delegación que no está archivada ni inactiva. Una fila antigua de un rol que ya no tiene no da nada.
- **`extra_delegations(user)`**: Delegaciones adicionales del usuario (sin la de su funcionario), en el orden de sus códigos.
- **`listed_extra_delegations(user)`**: Lo mismo que extra_delegations, calculado con lo que un listado ya trajo (prefetch_related de «role_delegations__delegation» y «groups__role_profile»), para no consultar la base por cada usuario.
  
  Sigue la misma regla de effective_rows: fila vigente, de un rol que el usuario tiene y que está activo, sobre una delegación activa y no archivada.
- **`stored_delegation_ids(user)`**: Ids de las delegaciones guardadas para el usuario, tal como las dejó el formulario (para volver a mostrarlas).
- **`sync_extra_delegations(user, delegations)`**: Deja una fila por cada rol del usuario y cada delegación indicada, y ninguna más.
  
  Una fila que sobra se borra de verdad (es un dato derivado de lo que se marca en el formulario, no una historia). Una que existía archivada se revive en vez de crearla otra vez, porque la combinación es única. Devuelve (agregadas, quitadas) para la auditoría: cantidades de combinaciones rol-delegación.

#### `accounts/backends.py`

Ingreso con el nombre de usuario o con el correo de la cuenta.

Es el backend de Django (ModelBackend) con una sola diferencia: si lo escrito no es un nombre de usuario y parece un correo, se busca la cuenta por su correo. Todo lo demás es igual: el usuario debe estar activo, la contraseña se comprueba con el mismo hash y los permisos salen de los mismos grupos.

Reglas para no abrir huecos:
  - Un nombre de usuario exacto siempre gana: si alguien tiene el usuario «ana@correo.cl», no se le puede quitar el
    ingreso porque el correo de otra persona sea ese texto.
  - Por correo se ingresa solo si hay exactamente una cuenta con ese correo (sin importar mayúsculas). Si hay dos o
    más, no se adivina cuál es: no se entra por correo y cada una puede ingresar con su usuario.
  - Cuando no se encuentra la cuenta se calcula igualmente un hash, para que no se note por el tiempo de respuesta si
    el usuario o el correo existen. El mensaje de error tampoco lo dice.

##### `EmailOrUsernameBackend` — hereda de `ModelBackend`

Forma de autenticar que acepta el usuario o el correo. Ver detalle abajo.

- **`authenticate(request, username, password, **kwargs)`**: Busca al usuario por nombre de usuario o por correo y comprueba la contraseña y que la cuenta esté activa. Si no existe, hace igual el cálculo del hash para que el tiempo de respuesta no delate si la cuenta existe. Devuelve el usuario o `None`.
- **`find_user(text)`**: La cuenta que corresponde a lo escrito (usuario o correo), o None si no hay una sola.

#### `accounts/validators.py`

Política de contraseñas del SGR.

Se suma a los validadores de Django (parecido a los datos personales, largo mínimo, uso común, solo números) y se configura en AUTH_PASSWORD_VALIDATORS (sgr_project/settings.py). La revisan todos los formularios que piden una contraseña nueva: Control de usuarios, Mi perfil y la recuperación de contraseña. Las contraseñas que ya existen no se revisan al ingresar: solo se exige al elegir una nueva.

La misma exigencia se avisa en el navegador con la regla «password» de core/rules.py, que repite validation.js. Cada mensaje dice exactamente qué le falta a la contraseña escrita.

##### `PasswordPolicyValidator`

Largo máximo y variedad de caracteres: minúscula, mayúscula, número y símbolo.

El largo mínimo lo revisa MinimumLengthValidator, que sigue activo, para no repetir el mensaje.

- **`__init__(max_length)`**: Guarda el largo máximo permitido.
- **`validate(password, user)`**: Comprueba el largo máximo y los requisitos de la política (`REQUIREMENTS`: minúscula, mayúscula, número y símbolo); junta todos los problemas en un solo error.
- **`get_help_text()`**: Texto que explica la política de contraseña.

#### `accounts/recovery.py`

Recuperación de contraseña con un código temporal que llega por correo.

Son tres pantallas (accounts/views.py) y este módulo hace el trabajo de cada una:

  1. La persona escribe su correo   -> send_codes() crea un código de 6 dígitos y lo envía.
  2. Escribe el código que le llegó -> check() revisa que calce, que esté vigente y que no se haya usado.
  3. Elige su contraseña nueva      -> el código ya quedó usado, así que no sirve una segunda vez.

Reglas del código: 6 dígitos, vale RECOVERY_CODE_SECONDS (120), se usa una sola vez, falla tras RECOVERY_MAX_ATTEMPTS intentos equivocados y pedir uno nuevo deja sin efecto los anteriores de la misma cuenta, se hayan pedido desde este navegador o desde otro. Reenviar el código se puede cada RECOVERY_RESEND_SECONDS (45) y hasta RECOVERY_MAX_REQUESTS (5) veces por hora. Los números están en settings.py.

Dónde queda cada cosa (no se agrega ninguna tabla al modelo de datos):

  - En request.session va lo que hay que recordar entre una pantalla y otra: el correo escrito, la hora en
    que vence el código, la hora del último envío y la huella del código. La sesión vive en el servidor (la
    tabla django_session que ya trae Django) y el navegador solo lleva una cookie con su clave, así que la
    persona no puede cambiar esos valores.
  - El código no se guarda: se guarda su huella (un HMAC con la SECRET_KEY). Para comparar se calcula la
    huella del código que escribió la persona.
  - Los intentos de cada código se cuentan en la caché de Django. Cada intento se anota antes de revisar el
    código y la suma es atómica, así que mandar muchos intentos a la vez no sirve para saltarse el límite.
  - Cada código enviado y cada código aceptado dejan un evento en la auditoría (Audit_Log). Ahí se cuentan los
    códigos enviados a una cuenta en la última hora y ahí se sabe cuál es el código vigente: el último evento
    de la cuenta, si es un envío. Un código nuevo (pedido desde donde sea) deja de ser el último y los
    anteriores dejan de servir; un código aceptado queda como último evento y tampoco sirve de nuevo.

##### `Result`

Lo que devuelve check(): la cuenta si el código era válido, o el motivo del rechazo.

**Funciones**

- **`new_code()`**: Seis dígitos al azar. Se usa secrets (pensado para claves); random se puede adivinar.
- **`fingerprint(user_pk, code, nonce)`**: Huella de un código. Incluye la cuenta y el envío: el mismo número en otra cuenta o en otro envío da otra huella.
- **`users_for(email)`**: Cuentas activas con ese correo, sin distinguir mayúsculas. Un correo vacío no calza con nadie.
- **`mask_email(email)`**: Esconde casi todo el correo (ma***@dominio.cl): alcanza para que la persona reconozca el suyo.
- **`clear(session)`**: Borra de la sesión todo lo de la recuperación.
- **`pending(session)`**: True si la persona ya escribió su correo (paso 1) y le corresponde escribir el código.
- **`seconds_left(session)`**: Segundos que le quedan al código; 0 cuando venció.
- **`cooldown_left(session)`**: Segundos que faltan para poder pedir otro código desde esta sesión; 0 cuando ya se puede.
  
  La espera corre desde el último envío y vale igual exista o no una cuenta con ese correo, así que tampoco delata qué correos están registrados.
- **`_count(key, timeout)`**: Suma 1 a un contador de la caché y devuelve el valor nuevo. La suma es atómica.
- **`_attempts_key(session)`**: Clave de la caché donde se cuentan los intentos de código de esa sesión de recuperación.
- **`failures(session)`**: Intentos que lleva el código actual (los equivocados y, si lo hubo, el que lo aceptó).
- **`sent_last_hour(user)`**: Cuántos códigos se le enviaron a la cuenta en la última hora, según la auditoría.
- **`live_code_id(user)`**: Id, en la auditoría, del envío cuyo código sigue vigente para la cuenta; None si no hay ninguno.
  
  Manda el último evento de recuperación de la cuenta (código enviado o código aceptado):
    - si es un envío, ese es el único código vigente. Los anteriores quedaron sin efecto, aunque se
      hayan pedido desde otro navegador u otro computador;
    - si es una validación, el código ya se usó y no queda ninguno vigente.
- **`describe_duration(seconds)`**: Cuánto dura el código dicho como lo diría una persona: 120 -> «2 minutos», 60 -> «1 minuto», 45 -> «45 segundos».
- **`send_code(user, code, expires_at)`**: Envía el correo con el código. Con el correo de consola (sin EMAIL_HOST) sale en la terminal.
  
  Va en dos versiones dentro del mismo mensaje: el texto simple (lo que muestra un lector que no sabe de HTML y lo que se ve en la consola) y la versión con los colores del portal, con el código grande al centro. El lector de correo elige la que sepa mostrar.
- **`send_codes(session, email)`**: Paso 1 (y reenvío): envía un código a cada cuenta activa con ese correo y deja la sesión lista para el paso 2.
  
  La sesión queda igual exista o no una cuenta con ese correo, haya pedido demasiados códigos o haya fallado el envío: así la respuesta no deja averiguar qué correos están registrados. Cada envío queda anotado en la auditoría, y eso es lo que deja sin efecto los códigos anteriores de la cuenta.
- **`check(session, code)`**: Paso 2: revisa el código que escribió la persona y devuelve un Result.
  
  Es válido si calza con el que se envió, no venció, es el último que se pidió para la cuenta y no tiene demasiados intentos. Al aceptarlo se borra de la sesión y queda anotado en la auditoría, así que sirve una sola vez, y queda anotado hasta cuándo puede elegir su contraseña nueva. El vencimiento se revisa contra la hora del servidor, no contra la cuenta regresiva de la pantalla.
- **`verification_expired(session)`**: True si la persona ya validó su código pero se le acabó el tiempo para elegir la contraseña.
- **`verified_user(session)`**: Cuenta cuyo código se validó hace poco, o None si no corresponde estar en el paso 3.

#### `accounts/forms.py`

Formularios de la recuperación de contraseña (uno por pantalla).

##### `RecoveryEmailForm` — hereda de `BootstrapFormMixin`, `forms.Form`

Paso 1: el correo de la cuenta.

- **`__init__(*args, **kwargs)`**: Aplica el estilo de los campos.
- **`clean_email()`**: Valida el formato del correo con la regla `email` y lo devuelve en minúsculas.

##### `RecoveryCodeForm` — hereda de `BootstrapFormMixin`, `forms.Form`

Paso 2: el código de 6 dígitos que llegó por correo.

- **`__init__(*args, **kwargs)`**: Aplica el estilo de los campos.
- **`clean_code()`**: Valida que el código sean seis dígitos (regla `recovery_code`).

##### `RecoveryPasswordForm` — hereda de `BootstrapFormMixin`, `SetPasswordForm`

Paso 3: la contraseña nueva, con las mismas exigencias de siempre (AUTH_PASSWORD_VALIDATORS).

- **`__init__(*args, **kwargs)`**: Pone los textos del formulario de contraseña nueva, la ayuda con la política de contraseña y el atributo de enfoque automático.
- **`validate_password_for_user(user, password_field_name)`**: Aplica los validadores de contraseña de Django al campo `new_password1`.

#### `accounts/views.py`

Pantallas de la recuperación de contraseña con código (la lógica está en accounts/recovery.py).

Entre una pantalla y otra se guarda en request.session lo que hay que recordar: el correo escrito, la huella del código y cuándo vence. La sesión vive en el servidor y el navegador solo lleva la cookie con su clave, así que la persona no puede cambiar esos valores.

**Funciones**

- **`sent_text(new)`**: Aviso que sigue a un envío. Es el mismo exista o no una cuenta con ese correo.
- **`wait_text(seconds)`**: Aviso cuando se pide otro código antes de que termine la espera.
- **`request_code(request)`**: Paso 1: la persona escribe su correo y se le envía el código.
- **`enter_code(request)`**: Paso 2: la persona escribe el código que le llegó.
- **`resend_code(request)`**: Reenvío: se pide otro código para el mismo correo; los anteriores de la cuenta dejan de servir.
  
  Hay que esperar RECOVERY_RESEND_SECONDS desde el último envío y no se pasan de RECOVERY_MAX_REQUESTS por hora. El servidor es el que hace respetar la espera: la cuenta regresiva del botón es solo un aviso.
- **`rejection_text(result)`**: Lo que se le dice a la persona cuando el código no sirvió.
- **`new_password(request)`**: Paso 3: con el código ya validado, la persona elige su contraseña nueva.

#### `accounts/urls.py`

Rutas de la recuperación de contraseña: pedir el código, escribirlo, reenviarlo y elegir la contraseña nueva.

| Ruta | Vista | Nombre |
|---|---|---|
| `/recuperar/` | `views.request_code` | `recover` |
| `/recuperar/codigo/` | `views.enter_code` | `recover_code` |
| `/recuperar/reenviar/` | `views.resend_code` | `recover_resend` |
| `/recuperar/nueva/` | `views.new_password` | `recover_password` |

#### `accounts/admin.py`

Django Admin de usuarios (con su perfil y su delegación), perfiles de usuario y asignaciones de rol por delegación.

##### `UserProfileInline` — hereda de `admin.StackedInline`

Muestra el perfil del usuario dentro de la pantalla del usuario del Django Admin, con el funcionario como campo de búsqueda.

##### `UserAdmin` — hereda de `DjangoUserAdmin`

Usuario del Django Admin con el perfil en línea y una columna con la delegación de su funcionario.

- **`get_delegation(obj)`**: Delegación del funcionario vinculado al usuario, para la columna de la lista.

##### `UserProfileAdmin` — hereda de `SoftDeleteAdminMixin`, `admin.ModelAdmin`

Lista de perfiles con usuario, funcionario y estado; búsqueda por usuario y funcionario; filtro por estado.

##### `UserRoleDelegationAdmin` — hereda de `SoftDeleteAdminMixin`, `admin.ModelAdmin`

Lista de asignaciones de rol por delegación, con búsqueda y filtros por rol y delegación.

#### `accounts/management/commands/seed_roles.py`

Comando `python manage.py seed_roles`: crea o actualiza los cinco roles (Coordinación, Jefatura, Funcionario, Verificador y Consulta) con sus permisos, y la ficha de cada uno.

Permisos que da cada rol:

| Rol | Modelo | Permisos |
|---|---|---|
| Coordinación | `Period` | add period, change period, view period |
| Coordinación | `Goal` | add goal, change goal, view goal |
| Coordinación | `Indicator` | view indicator |
| Coordinación | `Adjustment` | add adjustment, change adjustment, view adjustment |
| Coordinación | `Position` | view position |
| Coordinación | `Item` | view item |
| Coordinación | `Service` | view service |
| Coordinación | `PositionItem` | view positionitem |
| Coordinación | `Officer` | view officer |
| Coordinación | `Territory` | view territory |
| Jefatura | `Activity` | view activity |
| Jefatura | `Commitment` | view commitment, change commitment |
| Jefatura | `Followup` | view followup |
| Jefatura | `Indicator` | view indicator |
| Jefatura | `Evidence` | view evidence |
| Jefatura | `Validation` | view validation |
| Jefatura | `Officer` | view officer |
| Jefatura | `Territory` | view territory |
| Funcionario | `Activity` | add activity, change activity, view activity |
| Funcionario | `Followup` | add followup, change followup, view followup |
| Funcionario | `Evidence` | add evidence, change evidence, view evidence |
| Funcionario | `Commitment` | add commitment, change commitment, view commitment |
| Funcionario | `Officer` | view officer |
| Funcionario | `Territory` | view territory |
| Verificador | `Evidence` | view evidence |
| Verificador | `Activity` | view activity |
| Verificador | `Validation` | add validation, change validation, view validation |
| Consulta | `Activity` | view activity |
| Consulta | `Commitment` | view commitment |
| Consulta | `Indicator` | view indicator |
| Consulta | `Evidence` | view evidence |
| Consulta | `Validation` | view validation |
| Consulta | `Followup` | view followup |

##### `Command` — hereda de `BaseCommand`

Comando que crea o actualiza los roles base.

- **`handle(*args, **options)`**: Para cada rol de `core.roles.ROLES` crea el grupo, le deja los permisos que corresponden y crea su ficha.

**Funciones**

- **`permissions_for(model, codenames)`**: Permisos de un modelo a partir de sus nombres de código.

### App `organization`: delegaciones, cargos, ítems y personas

#### `organization/apps.py`

Configuración de la aplicación `organization`.

##### `OrganizationConfig` — hereda de `AppConfig`

Configuración de la aplicación `organization`.

#### `organization/models.py`

Modelos de la estructura de la organización: delegaciones, cargos, ítems medibles (tipos y sub atenciones), servicios, beneficiarios, territorios, funcionarios y la ponderación de cada ítem por cargo.

##### `Delegation` — hereda de `BaseModel`

Delegación: sector en que se organiza el trabajo en terreno, con su estado, encargados, alcance, dirección, comuna y color.

| Campo | Nombre visible | Tipo | Detalle |
|---|---|---|---|
| `name` | nombre | CharField | largo 100; único |
| `status` | estado | CharField | largo 20; con opciones; por defecto `Status.ACTIVE` |
| `managers` | responsables | CharField | largo 255; admite nulo; opcional |
| `scope` | ámbito | CharField | largo 100; admite nulo; opcional |
| `address` | dirección | CharField | largo 200; por defecto `''`; opcional — Calle y número de la oficina de la delegación. |
| `commune` | comuna | CharField | largo 100; por defecto `''`; opcional |
| `color` | color | CharField | largo 7; por defecto `'#920000'`; con validadores — Formato #RRGGBB. Identifica a la delegación en las pantallas. |

Opciones del modelo (`Meta`): `ordering` = `('name',)`; `verbose_name` = `'Delegación'`; `verbose_name_plural` = `'Delegaciones'`.

Opciones de `Status`: `active` (Activa), `inactive` (Inactiva).

- **`__str__()`**: Texto con que se muestra el registro.

##### `Position` — hereda de `BaseModel`

Cargo de los funcionarios, con su período de vigencia.

| Campo | Nombre visible | Tipo | Detalle |
|---|---|---|---|
| `name` | nombre | CharField | largo 100 |
| `valid_from` | vigencia desde | DateField |  |
| `valid_until` | vigencia hasta | DateField | admite nulo; opcional |

Opciones del modelo (`Meta`): `ordering` = `('name',)`; `verbose_name` = `'Cargo'`; `verbose_name_plural` = `'Cargos'`.

- **`__str__()`**: Texto con que se muestra el registro.

##### `Item` — hereda de `BaseModel`

Ítem de atención. Sin ítem padre es un tipo de atención; con ítem padre es una sub atención. Tiene un tipo de cálculo.

| Campo | Nombre visible | Tipo | Detalle |
|---|---|---|---|
| `parent_item` | ítem padre (tipo de atención) | ForeignKey | relación con `self`; nombre inverso `sub_items`; PROTECT; admite nulo; opcional |
| `name` | nombre | CharField | largo 150 |
| `description` | descripción | CharField | largo 255; por defecto `''`; opcional |
| `calculation_type` | tipo de cálculo | CharField | largo 20; con opciones; por defecto `CalculationType.QUANTITATIVE` |

Opciones del modelo (`Meta`): `ordering` = `('name',)`; `verbose_name` = `'Ítem'`; `verbose_name_plural` = `'Ítems'`.

Opciones de `CalculationType`: `quantitative` (Cuantitativo), `qualitative` (Cualitativo).

- **`__str__()`**: Texto con que se muestra el registro.

##### `Service` — hereda de `BaseModel`

Catálogo de servicios municipales que se pueden asociar a una actividad.

| Campo | Nombre visible | Tipo | Detalle |
|---|---|---|---|
| `name` | nombre | CharField | largo 100 |
| `status` | estado | CharField | largo 20; con opciones; por defecto `Status.ACTIVE` |

Opciones del modelo (`Meta`): `ordering` = `('name',)`; `verbose_name` = `'Servicio'`; `verbose_name_plural` = `'Servicios'`.

Opciones de `Status`: `active` (Activo), `inactive` (Inactivo).

- **`__str__()`**: Texto con que se muestra el registro.

##### `Beneficiary` — hereda de `BaseModel`

Persona atendida (RUT, nombre, teléfono y dirección). Es un catálogo compartido entre delegaciones.

| Campo | Nombre visible | Tipo | Detalle |
|---|---|---|---|
| `rut` | RUT | CharField | largo 12; único |
| `name` | nombre | CharField | largo 150 |
| `phone` | teléfono | CharField | largo 20; admite nulo; opcional |
| `address` | dirección | CharField | largo 200; opcional — Calle y número de la vivienda (ej.: Los Aromos 1234). |

Opciones del modelo (`Meta`): `ordering` = `('name',)`; `verbose_name` = `'Beneficiario'`; `verbose_name_plural` = `'Beneficiarios'`.

- **`__str__()`**: Texto con que se muestra el registro.

##### `Territory` — hereda de `BaseModel`

Territorio que pertenece a una delegación.

| Campo | Nombre visible | Tipo | Detalle |
|---|---|---|---|
| `name` | nombre | CharField | largo 100 |
| `delegation` | delegación | ForeignKey | relación con `Delegation`; nombre inverso `territories`; PROTECT |

Opciones del modelo (`Meta`): `ordering` = `('delegation__name', 'name')`; `verbose_name` = `'Territorio'`; `verbose_name_plural` = `'Territorios'`; `constraints` = `[models.UniqueConstraint(fields=('name', 'delegation'), name='uq_territory_delegation')]`.

- **`__str__()`**: Texto con que se muestra el registro.

##### `Officer` — hereda de `BaseModel`

Funcionario: código institucional, nombre, estado, delegación y cargo. Registra actividades y responde por metas.

| Campo | Nombre visible | Tipo | Detalle |
|---|---|---|---|
| `institutional_id` | identificador institucional | CharField | largo 20; único; se genera solo al guardar si viene vacío |
| `name` | nombre | CharField | largo 150 |
| `status` | estado | CharField | largo 20; con opciones; por defecto `Status.ACTIVE` |
| `delegation` | delegación | ForeignKey | relación con `Delegation`; nombre inverso `officers`; PROTECT |
| `position` | cargo | ForeignKey | relación con `Position`; nombre inverso `officers`; PROTECT |

Opciones del modelo (`Meta`): `ordering` = `('delegation__name', 'name')`; `verbose_name` = `'Funcionario'`; `verbose_name_plural` = `'Funcionarios'`.

Opciones de `Status`: `active` (Activo), `inactive` (Inactivo).

- **`__str__()`**: Texto con que se muestra el registro.
- **`id_numbers(queryset)`**: Saca los números de los identificadores con formato `F-NNNN` de un conjunto de funcionarios.
- **`next_institutional_id()`**: Calcula el siguiente identificador. Sigue el bloque de miles que ya usa la delegación del funcionario (Delegación Norte `F-1xxx`, Delegación Sur `F-2xxx`); una delegación sin funcionarios abre el bloque siguiente (`F-3001`). Cuenta también a los funcionarios archivados, porque su identificador sigue ocupado.
- **`save(*args, **kwargs)`**: Si el funcionario no trae identificador, lo genera al guardar; si otro guardado simultáneo tomó el mismo número, lo vuelve a calcular (hasta 5 intentos). Un identificador que ya existe no se cambia.

##### `PositionItem` — hereda de `BaseModel`

Ponderación de un ítem para un cargo: peso, vigencia, tipo (normal, bonificación o penalización) y tope máximo.

| Campo | Nombre visible | Tipo | Detalle |
|---|---|---|---|
| `position` | cargo | ForeignKey | relación con `Position`; nombre inverso `position_items`; PROTECT |
| `item` | ítem | ForeignKey | relación con `Item`; nombre inverso `position_items`; PROTECT |
| `weight` | ponderador | DecimalField | 5 dígitos, 2 decimales |
| `valid_from` | vigencia desde | DateField |  |
| `valid_until` | vigencia hasta | DateField | admite nulo; opcional |
| `kind` | tipo | CharField | largo 20; con opciones; por defecto `Kind.NORMAL` |
| `max_cap` | tope máximo | DecimalField | 10 dígitos, 2 decimales; admite nulo; opcional |

Opciones del modelo (`Meta`): `verbose_name` = `'Ítem de cargo'`; `verbose_name_plural` = `'Ítems de cargo'`; `ordering` = `('position__name', 'item__name')`.

Opciones de `Kind`: `NORMAL` (Normal), `BONUS` (Bonificación), `PENALTY` (Penalización).

- **`clean()`**: Las bonificaciones y penalizaciones deben tener un tope máximo.
- **`__str__()`**: Texto con que se muestra el registro.

#### `organization/admin.py`

Django Admin de delegaciones (con sus funcionarios en línea), cargos, ítems, servicios, beneficiarios, ítems de cargo, territorios y funcionarios.

##### `OfficerInline` — hereda de `admin.TabularInline`

##### `DelegationAdmin` — hereda de `SoftDeleteAdminMixin`, `admin.ModelAdmin`

Configuración del Django Admin para `Delegation`. Columnas: 'name', 'status', 'scope', 'managers'. Búsqueda por: 'name', 'scope'. Filtros: 'status',.

##### `PositionAdmin` — hereda de `SoftDeleteAdminMixin`, `admin.ModelAdmin`

Configuración del Django Admin para `Position`. Columnas: 'name', 'valid_from', 'valid_until'. Búsqueda por: 'name',.

##### `ItemAdmin` — hereda de `SoftDeleteAdminMixin`, `admin.ModelAdmin`

Configuración del Django Admin para `Item`. Columnas: 'name', 'parent_item', 'calculation_type'. Búsqueda por: 'name',. Filtros: 'calculation_type',.

##### `ServiceAdmin` — hereda de `SoftDeleteAdminMixin`, `admin.ModelAdmin`

Configuración del Django Admin para `Service`. Columnas: 'name', 'status'. Búsqueda por: 'name',. Filtros: 'status',.

##### `BeneficiaryAdmin` — hereda de `SoftDeleteAdminMixin`, `admin.ModelAdmin`

Configuración del Django Admin para `Beneficiary`. Columnas: 'name', 'rut', 'phone', 'address'. Búsqueda por: 'name', 'rut', 'address'.

##### `PositionItemAdmin` — hereda de `SoftDeleteAdminMixin`, `admin.ModelAdmin`

Configuración del Django Admin para `PositionItem`. Columnas: 'position', 'item', 'kind', 'weight', 'max_cap', 'valid_from', 'valid_until'. Búsqueda por: 'position__name', 'item__name'. Filtros: 'position', 'kind'.

##### `TerritoryAdmin` — hereda de `DelegationScopedAdminMixin`, `admin.ModelAdmin`

Configuración del Django Admin para `Territory`. Columnas: 'name', 'delegation'. Búsqueda por: 'name', 'delegation__name'. Filtros: 'delegation',.

##### `OfficerAdmin` — hereda de `DelegationScopedAdminMixin`, `admin.ModelAdmin`

Configuración del Django Admin para `Officer`. Columnas: 'name', 'institutional_id', 'delegation', 'position', 'status'. Búsqueda por: 'name', 'institutional_id', 'delegation__name'. Filtros: 'delegation', 'position', 'status'.

### App `planning`: períodos, metas, indicadores y ajustes

#### `planning/apps.py`

Configuración de la aplicación `planning`.

##### `PlanningConfig` — hereda de `AppConfig`

Configuración de la aplicación `planning`.

#### `planning/models.py`

Modelos de planificación: períodos de medición con sus umbrales de semáforo, metas, indicadores (avance, cumplimiento y semáforo) y ajustes de bonificación o penalización.

##### `Period` — hereda de `BaseModel`

Período de medición: ventana de fechas con sus días computables, su estado (planificado, vigente o cerrado), los umbrales del semáforo (colectivo y ámbar), el tope ponderado y la versión de los parámetros. Solo puede haber un período vigente.

| Campo | Nombre visible | Tipo | Detalle |
|---|---|---|---|
| `start_date` | fecha de inicio | DateField |  |
| `end_date` | fecha de término | DateField |  |
| `computable_days` | días computables | PositiveIntegerField |  |
| `status` | estado | CharField | largo 20; con opciones; por defecto `Status.PLANNED` |
| `collective_threshold` | umbral colectivo | DecimalField | 5 dígitos, 2 decimales; por defecto `80` |
| `amber_threshold` | umbral ámbar | DecimalField | 5 dígitos, 2 decimales; por defecto `60` |
| `weighted_cap` | tope ponderado | DecimalField | 5 dígitos, 2 decimales; por defecto `150` |
| `parameters_version` | versión de parámetros | CharField | largo 20; por defecto `'1'` |

Opciones del modelo (`Meta`): `ordering` = `('-start_date',)`; `verbose_name` = `'Período'`; `verbose_name_plural` = `'Períodos'`.

Opciones de `Status`: `planned` (Planificado), `active` (Vigente), `closed` (Cerrado).

- **`__str__()`**: Texto con que se muestra el registro.

##### `Goal` — hereda de `BaseModel`

Meta de un ítem para un período: valor objetivo, unidad, ponderador y versión. Es de un funcionario o de un cargo (uno solo de los dos).

| Campo | Nombre visible | Tipo | Detalle |
|---|---|---|---|
| `target_value` | valor objetivo | DecimalField | 10 dígitos, 2 decimales; con validadores — Debe ser mayor a 0 (equivale al CHECK del script SQL). |
| `unit` | unidad | CharField | largo 50 |
| `weight` | ponderador | DecimalField | 5 dígitos, 2 decimales |
| `version` | versión | PositiveIntegerField | por defecto `1` |
| `item` | ítem | ForeignKey | relación con `Item`; nombre inverso `goals`; PROTECT |
| `officer` | funcionario | ForeignKey | relación con `Officer`; nombre inverso `goals`; PROTECT; admite nulo; opcional |
| `position` | cargo | ForeignKey | relación con `Position`; nombre inverso `goals`; PROTECT; admite nulo; opcional |
| `period` | período | ForeignKey | relación con `Period`; nombre inverso `goals`; PROTECT |

Opciones del modelo (`Meta`): `verbose_name` = `'Meta'`; `verbose_name_plural` = `'Metas'`; `ordering` = `('-period__start_date',)`.

- **`__str__()`**: Texto con que se muestra el registro.

##### `Indicator` — hereda de `BaseModel`

Medición de una meta: avance, cumplimiento, ponderación, color del semáforo y fecha de cálculo.

| Campo | Nombre visible | Tipo | Detalle |
|---|---|---|---|
| `progress` | avance | DecimalField | 10 dígitos, 2 decimales |
| `compliance` | cumplimiento | DecimalField | 5 dígitos, 2 decimales |
| `weighting` | ponderación | DecimalField | 5 dígitos, 2 decimales |
| `status_light` | semáforo | CharField | largo 20; con opciones |
| `calculated_at` | fecha de cálculo | DateTimeField |  |
| `goal` | meta | ForeignKey | relación con `Goal`; nombre inverso `indicators`; PROTECT |

Opciones del modelo (`Meta`): `ordering` = `('-calculated_at',)`; `verbose_name` = `'Indicador'`; `verbose_name_plural` = `'Indicadores'`.

Opciones de `StatusLight`: `green` (Verde), `amber` (Ámbar), `red` (Rojo).

- **`__str__()`**: Texto con que se muestra el registro.

##### `Adjustment` — hereda de `BaseModel`

Bonificación o penalización (en porcentaje) que se aplica al resultado de un funcionario en un período, con su motivo y el usuario responsable.

| Campo | Nombre visible | Tipo | Detalle |
|---|---|---|---|
| `kind` | tipo | CharField | largo 20; con opciones |
| `reason` | motivo | CharField | largo 255 |
| `percentage_value` | valor (%) | DecimalField | 5 dígitos, 2 decimales |
| `date` | fecha | DateTimeField |  |
| `officer` | funcionario | ForeignKey | relación con `Officer`; nombre inverso `adjustments`; PROTECT |
| `period` | período | ForeignKey | relación con `Period`; nombre inverso `adjustments`; PROTECT |
| `responsible_user` | usuario responsable | ForeignKey | relación con `settings.AUTH_USER_MODEL`; nombre inverso `responsible_adjustments`; PROTECT |

Opciones del modelo (`Meta`): `ordering` = `('-date',)`; `verbose_name` = `'Ajuste'`; `verbose_name_plural` = `'Ajustes'`.

Opciones de `Kind`: `bonus` (Bonificación), `penalty` (Penalización).

- **`__str__()`**: Texto con que se muestra el registro.

#### `planning/admin.py`

Django Admin de períodos, metas, indicadores y ajustes.

##### `PeriodAdmin` — hereda de `SoftDeleteAdminMixin`, `admin.ModelAdmin`

Configuración del Django Admin para `Period`. Columnas: '__str__', 'status', 'computable_days', 'collective_threshold', 'amber_threshold', 'weighted_cap'. Filtros: 'status',.

##### `GoalAdmin` — hereda de `SoftDeleteAdminMixin`, `admin.ModelAdmin`

Configuración del Django Admin para `Goal`. Columnas: 'item', 'officer', 'position', 'period', 'target_value', 'unit', 'weight'. Búsqueda por: 'item__name', 'officer__name', 'position__name'. Filtros: 'period', 'position'.

##### `IndicatorAdmin` — hereda de `SoftDeleteAdminMixin`, `admin.ModelAdmin`

Configuración del Django Admin para `Indicator`. Columnas: 'goal', 'progress', 'compliance', 'weighting', 'status_light', 'calculated_at'. Filtros: 'status_light',. Solo lectura: 'created_at', 'updated_at', 'calculated_at'.

##### `AdjustmentAdmin` — hereda de `SoftDeleteAdminMixin`, `admin.ModelAdmin`

Configuración del Django Admin para `Adjustment`. Columnas: 'officer', 'kind', 'percentage_value', 'period', 'responsible_user', 'date'. Búsqueda por: 'officer__name', 'reason'. Filtros: 'kind', 'period'.

### App `operations`: atenciones, gestiones y compromisos

#### `operations/apps.py`

Configuración de la aplicación `operations`.

##### `OperationsConfig` — hereda de `AppConfig`

Configuración de la aplicación `operations`.

#### `operations/models.py`

Modelos de la operación diaria: tipos de gestión, actividades (atenciones), gestiones de seguimiento (hasta tres por actividad) y compromisos de la agenda colectiva.

##### `ManagementType` — hereda de `BaseModel`

Catálogo de tipos de gestión que se usan en el seguimiento de una actividad.

| Campo | Nombre visible | Tipo | Detalle |
|---|---|---|---|
| `name` | nombre | CharField | largo 80; único |

Opciones del modelo (`Meta`): `verbose_name` = `'Tipo de gestión'`; `verbose_name_plural` = `'Tipos de gestión'`; `ordering` = `('name',)`.

- **`__str__()`**: Texto con que se muestra el registro.

##### `Activity` — hereda de `BaseModel`

Atención registrada por un funcionario: fecha, solicitud, acción realizada, datos de contacto, beneficiario, ítem atendido, servicio, estado, si requiere visita y si pasó a cartera.

| Campo | Nombre visible | Tipo | Detalle |
|---|---|---|---|
| `date` | fecha | DateField |  |
| `request_description` | solicitud / problema | TextField | opcional |
| `action_taken` | acción | TextField | opcional |
| `contact_name` | contacto | CharField | largo 100; opcional |
| `phone` | teléfono | CharField | largo 20; opcional |
| `beneficiary` | beneficiario | ForeignKey | relación con `Beneficiary`; nombre inverso `activities`; PROTECT; admite nulo; opcional |
| `status` | estado | CharField | largo 30; con opciones; por defecto `Status.REGISTERED` |
| `requires_visit` | requiere visita | BooleanField | por defecto `False` |
| `added_to_pipeline` | ingresa al tubo de trabajo | BooleanField | por defecto `False` — Si queda marcado, la actividad se refleja como Commitment en la agenda colectiva (tubo de trabajo). |
| `item` | ítem | ForeignKey | relación con `Item`; nombre inverso `activities`; PROTECT |
| `service` | servicio | ForeignKey | relación con `Service`; nombre inverso `activities`; PROTECT; admite nulo; opcional |
| `delegation` | delegación | ForeignKey | relación con `Delegation`; nombre inverso `activities`; PROTECT |
| `author_officer` | funcionario autor | ForeignKey | relación con `Officer`; nombre inverso `authored_activities`; PROTECT |

Opciones del modelo (`Meta`): `ordering` = `('-date',)`; `verbose_name` = `'Actividad'`; `verbose_name_plural` = `'Actividades'`.

Opciones de `Status`: `registered` (Registrada), `in_progress` (En proceso), `closed` (Cerrada).

- **`clean()`**: Comprueba que la delegación de la actividad sea la del funcionario que la registra.
- **`__str__()`**: Texto con que se muestra el registro.

##### `Followup` — hereda de `BaseModel`

Gestión de seguimiento de una actividad (hasta tres): número, tipo de gestión, fecha, resultado y fechas de visita y de entrega de informe y de beneficio.

| Campo | Nombre visible | Tipo | Detalle |
|---|---|---|---|
| `sequence_number` | número de gestión | PositiveSmallIntegerField | con validadores — 1ra, 2da o 3ra gestión sobre la misma actividad. |
| `management_type` | tipo de gestión | ForeignKey | relación con `ManagementType`; nombre inverso `followups`; PROTECT; admite nulo; opcional |
| `date` | fecha | DateField |  |
| `result` | resultado | CharField | largo 255 |
| `scheduled_visit_date` | fecha programada de visita | DateField | admite nulo; opcional |
| `visit_date` | fecha de visita | DateField | admite nulo; opcional |
| `report_delivery_date` | fecha de entrega de informe | DateField | admite nulo; opcional |
| `benefit_delivery_date` | fecha de entrega de beneficio | DateField | admite nulo; opcional |
| `activity` | actividad | ForeignKey | relación con `Activity`; nombre inverso `followups`; PROTECT |

Opciones del modelo (`Meta`): `verbose_name` = `'Gestión de atención'`; `verbose_name_plural` = `'Gestiones de atención'`; `ordering` = `('-date',)`; `constraints` = `[models.UniqueConstraint(fields=('activity', 'sequence_number'), name='uq_activity_followup')]`.

- **`__str__()`**: Texto con que se muestra el registro.

##### `Commitment` — hereda de `BaseModel`

Compromiso de la agenda colectiva: origen, solicitud, solicitante, territorio, fecha de vencimiento, apoyo, estado, notas, funcionario responsable y delegación.

| Campo | Nombre visible | Tipo | Detalle |
|---|---|---|---|
| `source` | origen | CharField | largo 100; admite nulo; opcional |
| `request_date` | fecha de solicitud | DateField | admite nulo; opcional |
| `description` | descripción | TextField | admite nulo; opcional |
| `requester` | solicitante | CharField | largo 100 |
| `requester_type` | tipo de solicitante | CharField | largo 10; con opciones; por defecto `RequesterType.EXTERNAL` |
| `territory` | territorio | ForeignKey | relación con `Territory`; nombre inverso `commitments`; PROTECT |
| `due_date` | fecha comprometida | DateField |  |
| `support` | apoyo | CharField | largo 100; admite nulo; opcional |
| `status` | estado | CharField | largo 30; con opciones; por defecto `Status.SUBMITTED` |
| `notes` | observación | TextField | admite nulo; opcional |
| `responsible_officer` | funcionario responsable | ForeignKey | relación con `Officer`; nombre inverso `responsible_commitments`; PROTECT |
| `delegation` | delegación | ForeignKey | relación con `Delegation`; nombre inverso `commitments`; PROTECT |

Opciones del modelo (`Meta`): `ordering` = `('-due_date',)`; `verbose_name` = `'Compromiso'`; `verbose_name_plural` = `'Compromisos'`.

Opciones de `RequesterType`: `INTERNAL` (Interno), `EXTERNAL` (Externo).

Opciones de `Status`: `submitted` (Ingresado), `in_progress` (En proceso), `fulfilled` (Cumplido).

- **`clean()`**: Comprueba que el territorio pertenezca a la delegación elegida.
- **`__str__()`**: Texto con que se muestra el registro.

#### `operations/admin.py`

Django Admin de tipos de gestión, actividades (con sus gestiones en línea), gestiones y compromisos.

##### `FollowupInline` — hereda de `admin.TabularInline`

##### `ManagementTypeAdmin` — hereda de `SoftDeleteAdminMixin`, `admin.ModelAdmin`

Configuración del Django Admin para `ManagementType`. Columnas: 'name',. Búsqueda por: 'name',.

##### `ActivityAdmin` — hereda de `DelegationScopedAdminMixin`, `admin.ModelAdmin`

Configuración del Django Admin para `Activity`. Columnas: 'date', 'item', 'delegation', 'author_officer', 'status', 'requires_visit', 'added_to_pipeline'. Búsqueda por: 'contact_name', 'phone', 'beneficiary__name', 'beneficiary__rut'. Filtros: 'delegation', 'status', 'requires_visit', 'added_to_pipeline', 'item'.

##### `FollowupAdmin` — hereda de `DelegationScopedAdminMixin`, `admin.ModelAdmin`

Configuración del Django Admin para `Followup`. Columnas: 'activity', 'sequence_number', 'management_type', 'date', 'result'. Filtros: 'management_type', 'sequence_number'.

##### `CommitmentAdmin` — hereda de `DelegationScopedAdminMixin`, `admin.ModelAdmin`

Configuración del Django Admin para `Commitment`. Columnas: 'requester', 'territory', 'delegation', 'requester_type', 'responsible_officer', 'due_date', 'status'. Búsqueda por: 'requester', 'territory__name', 'description'. Filtros: 'delegation', 'status', 'requester_type'.

#### `operations/management/commands/seed_management_types.py`

Comando `python manage.py seed_management_types`: crea el catálogo inicial de tipos de gestión.

Tipos de gestión que crea: «Atención a usuario presencial»; «Visita a terreno»; «Entrega de informe»; «Entrega de beneficio»; «Emergencia»; «Otras gestiones». Si ya existen, no los duplica.

##### `Command` — hereda de `BaseCommand`

Comando que crea los tipos de gestión iniciales.

- **`handle(*args, **options)`**: Crea cada tipo de gestión que falte e informa cuántos eran nuevos.

### App `evidence`: evidencias y validaciones

#### `evidence/apps.py`

Configuración de la aplicación `evidence`.

##### `EvidenceConfig` — hereda de `AppConfig`

Configuración de la aplicación `evidence`.

#### `evidence/models.py`

Modelos de evidencias: el archivo que respalda una actividad y las validaciones (decisiones de revisión) que recibe.

##### `Evidence` — hereda de `BaseModel`

Archivo que respalda una actividad: código único, archivo, fecha de subida, estado de revisión, metadatos del archivo y funcionario autor.

| Campo | Nombre visible | Tipo | Detalle |
|---|---|---|---|
| `unique_code` | código único | CharField | largo 50; único |
| `file_link` | archivo | FileField | largo 255; sube archivo — PDF, imagen (PNG o JPG), Word o Excel de hasta 10 MB. |
| `uploaded_at` | fecha de carga | DateTimeField |  |
| `review_status` | estado de revisión | CharField | largo 30; con opciones; por defecto `ReviewStatus.PENDING` |
| `metadata` | metadatos | TextField | admite nulo; opcional |
| `activity` | actividad | ForeignKey | relación con `Activity`; nombre inverso `evidence_records`; PROTECT |
| `author_officer` | funcionario autor | ForeignKey | relación con `Officer`; nombre inverso `authored_evidence`; PROTECT |

Opciones del modelo (`Meta`): `verbose_name` = `'Evidencia'`; `verbose_name_plural` = `'Evidencias'`; `ordering` = `('-uploaded_at',)`.

Opciones de `ReviewStatus`: `pending` (Pendiente), `approved` (Aprobada), `rejected` (Rechazada).

- **`__str__()`**: Texto con que se muestra el registro.

##### `Validation` — hereda de `BaseModel`

Revisión de una evidencia: decisión, fecha, notas, resultado, versión y funcionario que revisó.

| Campo | Nombre visible | Tipo | Detalle |
|---|---|---|---|
| `decision` | decisión | CharField | largo 30; con opciones |
| `date` | fecha | DateTimeField |  |
| `notes` | observación | TextField | admite nulo; opcional |
| `result` | resultado | CharField | largo 50; admite nulo; opcional |
| `version` | versión | CharField | largo 20; por defecto `'1'` |
| `evidence` | evidencia | ForeignKey | relación con `Evidence`; nombre inverso `validations`; PROTECT |
| `reviewer_officer` | funcionario verificador | ForeignKey | relación con `Officer`; nombre inverso `performed_validations`; PROTECT; admite nulo; opcional |

Opciones del modelo (`Meta`): `verbose_name` = `'Validación'`; `verbose_name_plural` = `'Validaciones'`; `ordering` = `('-date',)`.

Opciones de `Decision`: `approved` (Aprobado), `rejected` (Rechazado), `flagged` (Observado).

- **`reviewer_name()`** *(propiedad)*: Nombre de quien revisó: el funcionario o «Super Usuario» si no hay funcionario.
- **`__str__()`**: Texto con que se muestra el registro.

#### `evidence/admin.py`

Django Admin de evidencias (con sus validaciones en línea) y de validaciones, limitado por delegación.

##### `ValidationInline` — hereda de `admin.TabularInline`

- **`formfield_for_foreignkey(db_field, request, **kwargs)`**: Si la persona no es superusuaria, en el campo del funcionario revisor ofrece solo los funcionarios activos de su delegación.

##### `EvidenceAdmin` — hereda de `DelegationScopedAdminMixin`, `admin.ModelAdmin`

Configuración del Django Admin para `Evidence`. Columnas: 'unique_code', 'activity', 'author_officer', 'review_status', 'uploaded_at'. Búsqueda por: 'unique_code', 'activity__contact_name'. Filtros: 'review_status',.

##### `ValidationAdmin` — hereda de `DelegationScopedAdminMixin`, `admin.ModelAdmin`

Configuración del Django Admin para `Validation`. Columnas: 'evidence', 'decision', 'reviewer_officer', 'date'. Filtros: 'decision',.

## 10. Migraciones

Las migraciones crean y modifican las tablas de cada app.

### `accounts`

- `0001_initial.py`: crea la tabla de `UserProfile`.
- `0002_roleprofile.py`: crea la tabla de `RoleProfile`.
- `0003_create_role_profiles.py`: crea la ficha de los roles que ya existían.
- `0004_userroledelegation.py`: crea la tabla de `UserRoleDelegation`.
- `0005_userprofile_photo.py`: agrega el campo `userprofile.photo`.
- `0006_userprofile_photo_imagefield.py`: cambia `userprofile.photo` de `FileField` a `ImageField`; la columna no cambia.

### `core`

- `0001_initial.py`: crea la tabla de `AuditLog`.

### `evidence`

- `0001_initial.py`: crea la tabla de `Evidence`; crea la tabla de `Validation`.
- `0002_validation_reviewer_optional.py`: modifica el campo `validation.reviewer_officer`.
- `0003_evidence_file_upload.py`: modifica el campo `evidence.file_link`.

### `operations`

- `0001_initial.py`: crea la tabla de `ManagementType`; crea la tabla de `Activity`; crea la tabla de `Commitment`; crea la tabla de `Followup`.

### `organization`

- `0001_initial.py`: crea la tabla de `Beneficiary`; crea la tabla de `Delegation`; crea la tabla de `Position`; crea la tabla de `Service`; crea la tabla de `Item`; crea la tabla de `Officer`; crea la tabla de `PositionItem`; crea la tabla de `Territory`.
- `0002_delegation_color.py`: agrega el campo `delegation.color`.
- `0003_delegation_address_commune_item_description.py`: agrega el campo `delegation.address`; agrega el campo `delegation.commune`; agrega el campo `item.description`.

### `planning`

- `0001_initial.py`: crea la tabla de `Period`; crea la tabla de `Goal`; crea la tabla de `Indicator`; crea la tabla de `Adjustment`.

## 11. Plantillas

Plantillas de Django. Las de `templates/` son el marco general, los errores y las pantallas sin sesión; las de `core/templates/core/` son las pantallas del sistema, los fragmentos reutilizables (`partials/`), los mantenedores (`crud/`) y los campos especiales (`widgets/`).

| Plantilla | Qué muestra |
|---|---|
| `templates/base.html` | Marco de todas las pantallas con sesión: cabecera HTML, barra lateral, franja de arriba, avisos, bloque de contenido y pie. Carga los módulos JavaScript. |
| `templates/403.html` | Error 403: no tiene permiso para esa pantalla, con enlace al dashboard. |
| `templates/403_csrf.html` | Error 403 por token CSRF vencido: la pantalla ya no es válida. |
| `templates/404.html` | Error 404: la página no existe. |
| `templates/500.html` | Error 500: algo salió mal en el servidor. Es una página independiente. |
| `templates/registration/auth_base.html` | Marco de las pantallas sin sesión (ingreso y recuperación de contraseña). |
| `templates/registration/login.html` | Pantalla de ingreso (la usa `LoginView`). |
| `templates/registration/recover_request.html` | Recuperación, paso 1: se escribe el correo. |
| `templates/registration/recover_code.html` | Recuperación, paso 2: se escribe el código de seis dígitos, con el reloj del código y el reenvío. |
| `templates/registration/recover_password.html` | Recuperación, paso 3: se elige la contraseña nueva. |
| `templates/registration/recovery_email.html` | Correo con el código de recuperación (versión HTML). |
| `templates/registration/recovery_email.txt` | Correo con el código de recuperación (versión texto). |
| `core/templates/core/dashboard.html` | Dashboard: saludo, metas del período del funcionario, semáforo, pendientes, accesos directos, atenciones recientes y compromisos próximos. |
| `core/templates/core/atencion.html` | Pantalla de Atención: listado de actividades con buscador, filtros, tabla, filas por página y paginación. |
| `core/templates/core/profile.html` | Mi perfil: datos de la cuenta, foto, delegación y cambio de contraseña. |
| `core/templates/core/administration.html` | Administración: período vigente y accesos a los mantenedores de organización, planificación y catálogos. |
| `core/templates/core/delegation_board.html` | Tablero de delegación: promedio, semáforo, resultado de cada funcionario y tarjetas de pendientes. |
| `core/templates/core/reports.html` | Informes: filtros de período y delegación, tabla por funcionario y botones para exportar a Excel, CSV o imprimir. |
| `core/templates/core/validate_list.html` | Evidencias por revisar y últimas validaciones. |
| `core/templates/core/validate_form.html` | Revisión de una evidencia: sus datos, el archivo, el formulario de decisión y las revisiones anteriores. |
| `core/templates/core/crud/list.html` | Listado de un mantenedor: buscador, filtros, tabla, filas por página y paginación. |
| `core/templates/core/crud/detail.html` | Ficha de un registro: datos, bloques relacionados, panel extra y acciones. |
| `core/templates/core/crud/form.html` | Formulario de nuevo o editar, como página completa. |
| `core/templates/core/crud/form_modal.html` | El mismo formulario como contenido de la ventana modal. |
| `core/templates/core/crud/_form_body.html` | Contenido del formulario sin los botones; lo comparten la página y la ventana modal. |
| `core/templates/core/crud/archive_confirm.html` | Confirmación de archivar un registro, con los motivos si no se puede. |
| `core/templates/core/crud/delete_confirm.html` | Confirmación de eliminar un registro, con los motivos si no se puede. |
| `core/templates/core/crud/role_permissions.html` | Panel de permisos en la ficha de un rol: una fila por módulo con las acciones que tiene. |
| `core/templates/core/partials/cell.html` | Dibuja una celda según su tipo: etiqueta, sí/no, archivo con vista previa, color, enlace o texto. |
| `core/templates/core/partials/check.html` | Casilla de verificación de un formulario. |
| `core/templates/core/partials/data_table.html` | Tabla de resultados de un listado: columnas con orden, filas y botones de cada fila. |
| `core/templates/core/partials/delete_link.html` | Enlace «Eliminar» o «Archivar»; con JavaScript abre la confirmación en una ventana. |
| `core/templates/core/partials/escudo.html` | Escudo de la institución (se muestra si su archivo está en `core/static/core/img/`). |
| `core/templates/core/partials/field.html` | Un campo de formulario con su etiqueta, ayuda y errores. |
| `core/templates/core/partials/flash.html` | Avisos de la sesión (mensajes de Django); con JavaScript los muestra SweetAlert2. |
| `core/templates/core/partials/footer.html` | Pie de página de todas las pantallas. |
| `core/templates/core/partials/meter.html` | Barra de cumplimiento con sus marcas de umbral. |
| `core/templates/core/partials/mini_table.html` | Listado corto con la primera celda enlazada a la ficha. |
| `core/templates/core/partials/page_size.html` | Selector de filas por página (se guarda en la sesión). |
| `core/templates/core/partials/pagination.html` | Paginación con páginas anterior, siguiente y saltos. |
| `core/templates/core/partials/public_head.html` | Cabecera simple de las páginas sin sesión. |
| `core/templates/core/partials/sidebar.html` | Barra lateral: marca, delegación con su color, perfiles y menú. |
| `core/templates/core/partials/topbar.html` | Franja de arriba: delegación, persona con sesión, perfil y cerrar sesión; con varias delegaciones, el selector. |
| `core/templates/core/widgets/color.html` | Campo de color: muestra, texto `#RRGGBB` y selector de color del navegador. |
| `core/templates/core/widgets/delegations.html` | Delegaciones adicionales de un usuario: una casilla por delegación con su color. |
| `core/templates/core/widgets/lookup.html` | Campo de texto con lista de sugerencias y lupa para buscar. |
| `core/templates/core/widgets/permissions.html` | Matriz de permisos de un rol: una fila por módulo y una columna por acción. |
| `core/templates/core/widgets/roles.html` | Perfiles de un usuario: una casilla por perfil con su descripción. |

## 12. JavaScript

Módulos en `core/static/core/js/`. Todo funciona también sin JavaScript: estos scripts solo agregan comodidad (el servidor siempre vuelve a validar y a comprobar permisos). Las librerías de `core/static/core/vendor/` (Bootstrap, Bootstrap Icons y SweetAlert2) se usan tal como vienen.

### `core/static/core/js/alerts.js`

```text
Ventanas de SweetAlert2 del sistema: una sola configuración, con los textos en español, que usan la
validación de formularios, las confirmaciones, los avisos de resultado y los de error.
```

Funciones:

- **`keepFocus(popup)`**: Cuando hay una ventana modal de Bootstrap abierta, su trampa de foco le quita el foco a cualquier cosa que esté fuera de ella. Aquí se corta el aviso de foco antes de que llegue (willOpen corre antes de que la ventana tome el foco), para que sus botones se puedan usar con el teclado.

### `core/static/core/js/busy.js`

```text
Estados de carga: mientras se envía un formulario, se busca en un listado o llega la ventana de un formulario, el
botón (o enlace) que se apretó muestra un indicador de progreso y queda desactivado. Así se ve que algo está
pasando y un doble clic no envía dos veces lo mismo.

  form[data-once]       formulario que se envía (POST): los botones de enviar quedan desactivados
  form[data-loading]    formulario de consulta (GET: buscar, filtrar): igual, y el panel de resultados queda «ocupado»
  button[data-no-busy]  este botón no cambia (por ejemplo «Exportar a Excel»: descarga un archivo y la página no cambia)

Sin JavaScript todo funciona igual, solo que sin el indicador. Si otro script frena el envío (la validación del
formulario, una confirmación), los botones se dejan como estaban: el indicador solo sale cuando de verdad se envía.
```

Funciones:

- **`spinner()`**
- **`start(control)`**: Marca un botón o enlace como ocupado: indicador en lugar de su ícono, desactivado y con aria-busy.
- **`stop(control)`**: Deja el botón o enlace como estaba.
- **`lock(form, submitter = null)`**: Un formulario que se está enviando: todos sus botones de enviar se desactivan y el que se apretó (o el primero) muestra el indicador. Un lector de pantalla recibe un aviso de «Procesando…».
- **`unlock(form)`**: Vuelve el formulario a como estaba (el envío no llegó al servidor, o se volvió con el botón «atrás»).

### `core/static/core/js/code-boxes.js`

```text
Seis casillas para escribir el código de recuperación, una por dígito.

El campo de texto del formulario (name="code") sigue siendo el que se envía y el que revisa validation.js:
este script solo lo esconde y lo mantiene al día con lo que se escribe en las casillas. Así el servidor
recibe lo mismo de siempre y, sin JavaScript, la persona ve el campo de texto normal.

Se puede escribir, pegar el código completo (con espacios o sin ellos), borrar con retroceso y moverse con
las flechas. Solo se aceptan dígitos.
```

Funciones:

- **`digitsOf(text)`**
- **`sync()`**: Lo escrito en las casillas pasa al campo de verdad, y validation.js se entera como si se hubiera escrito en él.
- **`fill(start, digits)`**: Pone los dígitos desde la casilla start y deja el cursor en la siguiente a la última escrita.
- **`target()`**: Dónde parte el cursor: la primera casilla vacía o, si están todas llenas, la última.
- **`mirrorErrors()`**: Si el servidor devolvió el campo con un error, las casillas se marcan igual; validation.js cambia la clase del campo y aquí se copia a las casillas.

### `core/static/core/js/confirm.js`

```text
Confirmaciones y cancelaciones con SweetAlert2. SweetAlert2 solo pregunta o avisa: quien decide y quien guarda
es siempre el servidor, que vuelve a comprobar el permiso, el token CSRF y los datos.

1. Eliminar con confirmación. El enlace «Eliminar» (data-delete trae el nombre del registro) abre una ventana y,
   si se confirma, envía un POST normal con su token CSRF; así Django comprueba el permiso, elimina, redirige y
   muestra su aviso de siempre. Sin JavaScript el enlace lleva a una página de confirmación que hace lo mismo.

     data-delete-kind="archive"  el registro queda inactivo (borrado lógico) y se puede restaurar
     data-delete-kind="remove"   el registro se borra de verdad (los roles)
     data-blocked="..."          el registro está en uso: se explica por qué y no se ofrece eliminar

2. Confirmar un envío (data-confirm-submit en el formulario), por ejemplo al cambiar la contraseña. Si se
   cancela, el formulario no se envía y un aviso lo dice. Los textos salen de los atributos data-confirm-*.

3. Cancelar un formulario (data-cancel-form="create" o "edit"): no se guarda nada y un aviso lo dice.
```

Funciones:

- **`isPlainClick(event)`**: Un clic normal, sin teclas: abrir el enlace en otra pestaña sigue funcionando.
- **`post(url)`**

### `core/static/core/js/context.js`

```text
Selector de delegación de la franja de arriba . Con JavaScript el selector cambia la delegación en cuanto se
elige una y el botón «Cambiar» se oculta; sin JavaScript queda el botón y todo funciona igual.

SweetAlert2 solo avisa: la delegación elegida la guarda y la comprueba el servidor (POST a «contexto/»), que
responde 403 si no está autorizada para la persona. Aquí solo se evita perder lo escrito sin querer:

  data-unsaved-guard   en un <form> de la página: si tiene datos escritos que no se guardaron, cambiar de delegación
                       pregunta antes, porque la pantalla se vuelve a cargar con los datos de la delegación nueva.
                       Con el valor «dirty» el formulario ya llega con datos (por ejemplo, tras un error).
```

Funciones:

- **`markDirty(event)`**
- **`formsWithUnsavedChanges()`**: Formularios de la página con datos escritos que todavía no se guardan.
- **`optionText(value)`**

### `core/static/core/js/countdown.js`

```text
Relojes de la pantalla donde se escribe el código de recuperación.

 1. Cuánto le queda al código (data-countdown).
 2. Cuánto falta para poder reenviarlo (data-resend): el botón queda desactivado mientras corre la espera.

Solo avisan cuánto falta: quien decide es el servidor (accounts/recovery.py), que revisa el vencimiento
del código y la espera del reenvío con su propia hora. Sin JavaScript la pantalla funciona igual; se ve el
tiempo que quedaba al cargar la página y, si se aprieta "Reenviar" antes de tiempo, el servidor avisa cuánto falta.
```

Funciones:

- **`remaining(end)`**: Los dos relojes se cuentan contra la hora del navegador y no sumando de a uno, para que no se atrasen si la pestaña queda en segundo plano.
- **`codeClock()`**
- **`format(seconds)`**
- **`tick()`**
- **`resendWait()`**
- **`tick()`**

### `core/static/core/js/crud-modal.js`

```text
Nuevo y Editar en una ventana modal (Bootstrap), sin salir del listado.

Los enlaces con data-modal-form siguen siendo enlaces normales: sin JavaScript, o abriéndolos en otra
pestaña, llevan a la página del formulario. Con JavaScript:
  1. se le pide a Django el formulario con ?modal=1 (solo el contenido de la ventana);
  2. se muestra en la ventana y se le agregan la validación y los campos especiales;
  3. al guardar se envía con fetch. Si el servidor devuelve errores, se muestra otra vez el formulario
     con sus mensajes y la ventana de SweetAlert2; si se guardó, se recarga la página para ver el cambio.
```

Funciones:

- **`isPlainClick(event)`**: Un clic normal, sin teclas: abrir el enlace en otra pestaña sigue funcionando.
- **`modalUrl(url)`**: La misma dirección con ?modal=1 (conserva lo que ya traía, como ?beneficiary=3).
- **`failed(text)`**
- **`toForm(html)`**: Convierte el HTML que mandó Django en un formulario con sus campos especiales listos.
- **`openForm(url, notice = "")`**: Pide el formulario y lo abre en la ventana. Devuelve false si no llegó (permiso, sesión vencida...).
- **`show(html, notice = "")`**
- **`send(form, button)`**

### `core/static/core/js/dialog.js`

```text
Ventana modal compartida (Bootstrap 5): aquí se abren los formularios de Nuevo y Editar y el buscador
de las listas (por ejemplo, el del Encargado de una delegación).

Bootstrap no permite dos modales abiertos a la vez, así que hay una sola ventana. Cuando algo se abre
encima de otra cosa (el buscador sobre un formulario), lo de abajo se guarda tal como está, con lo que
se alcanzó a escribir, y vuelve cuando se cierra lo de arriba.
```

Funciones:

- **`focusFirst(content)`**: Pone el cursor en el primer campo del contenido.
- **`place(content)`**
- **`open(content, returnTo = null)`**: Abre la ventana con un contenido (un elemento con la clase modal-content). Lo que hubiera, se descarta. returnTo es lo que recibe el foco al cerrar la ventana (por defecto, lo que lo tenía al abrirla).
- **`push(content, returnTo = null)`**: Muestra otro contenido encima del actual; el actual vuelve con back().
- **`back()`**: Vuelve al contenido de abajo; si no hay ninguno, cierra la ventana.
- **`close()`**
- **`onClosed(listener)`**: Pide que se ejecute una función cada vez que la ventana termina de cerrarse.

### `core/static/core/js/flash.js`

```text
Avisos de Django (el framework de mensajes) como ventanas de SweetAlert2.

Quien dice qué pasó es el servidor: solo manda «éxito» cuando la operación se hizo, y manda «error» cuando no.
Aquí solo se muestran:
  éxito          ventana con el ícono verde que se cierra sola a los 4 segundos (o con «Entendido»)
  error          ventana roja que espera a que la persona la cierre
  advertencia    ventana amarilla que espera a que la persona la cierre
  información    aviso corto en la esquina, que se cierra solo (también lo que traiga la etiqueta «toast»)

Sin JavaScript, o si este script no llega a correr, los mismos avisos se ven como siempre arriba de la página
(core/partials/flash.html): sgr.js los vuelve a mostrar si flash.js no avisó que está listo.
```

Funciones:

- **`showOnNextPage(notice)`**: Avisos pendientes para la página que sigue: por ejemplo «Registro cancelado» al volver de un formulario. El almacenamiento del navegador puede no estar disponible (ventana privada, bloqueado): sin él no hay aviso y listo.
- **`takeStored()`**
- **`takeInline()`**: Los avisos que Django dejó en la página. Se leen y se quitan de ella: desde ahora los muestra SweetAlert2.
- **`show({ level, tags, text })`**
- **`whenFree()`**: Si otra ventana ya está abierta (la de los errores de un formulario, por ejemplo), se espera a que se cierre: SweetAlert2 muestra una sola a la vez y abrir otra cerraría la primera.
- **`run()`**

### `core/static/core/js/has-js.js`

```text
Avisa a las hojas de estilo que hay JavaScript. Va en el <head> para que se aplique antes de dibujar la página:
así los avisos de Django, que flash.js muestra como ventanas de SweetAlert2, no parpadean arriba de la página.
Sin JavaScript esta marca no existe y los avisos se ven como siempre.
```

### `core/static/core/js/live-search.js`

```text
Búsqueda en vivo: en los listados, al escribir en el buscador (con una pausa breve) o al cambiar un filtro, los
resultados se actualizan solos, sin apretar «Buscar» ni recargar la página.

  form[data-live-search]     formulario de consulta (GET) que se consulta solo
  [data-live-target="x"]     parte de la página que se reemplaza con la que llega del servidor; el formulario no
                             se toca, así que el cursor y lo escrito se quedan donde estaban
  [data-live-status]         aviso para lector de pantalla con la cantidad de resultados
  [data-live-count]          cantidad de resultados, dentro del bloque «resultados»

El servidor es el mismo y responde lo mismo que al apretar «Buscar»; aquí solo se toma la parte que cambia.
Sin JavaScript, o si algo falla, el botón «Buscar» y la tecla Enter siguen funcionando como siempre. Al enviar
el formulario de la forma normal se cancela cualquier búsqueda pendiente.
```

Funciones:

- **`setup(form)`**
- **`serialize(source)`**
- **`announce()`**
- **`run()`**
- **`schedule(delay)`**

### `core/static/core/js/sgr.js`

```text
Pequeños ajustes de las pantallas. Todo sigue funcionando sin JavaScript.
```

### `core/static/core/js/validation.js`

```text
Validación de formularios en el navegador.

Un formulario con el atributo data-validate se revisa antes de enviarse: campos obligatorios en
blanco, formatos (RUT, teléfono, correo...), largos, números y fechas. Si hay problemas, el envío
se detiene, cada campo muestra su mensaje y una ventana de SweetAlert2 los lista todos.

Las reglas de formato llegan en atributos data-* del campo (los arma core/rules.py) y se
comprueban con expresiones regulares. El servidor vuelve a validar todo al guardar: esto solo
avisa antes. Si el servidor devuelve errores, la misma ventana los muestra al cargar la página
(o al volver a mostrar el formulario dentro de la ventana modal, ver crud-modal.js).
```

Funciones:

- **`rutDigit(body)`**: Dígito verificador de un RUT (módulo 11): un número del 0 al 9 o la letra K.
- **`labelOf(field)`**: Texto de la etiqueta del campo, sin el asterisco de obligatorio. data-label lo reemplaza.
- **`decimalsOf(step)`**: Cuántos decimales permite un campo numérico según su atributo step ("0.01" -> 2).
- **`dayText(iso)`**: 2026-10-12 -> 12/10/2026, como se ven las fechas en las pantallas.
- **`plural(count, one, many)`**
- **`fileProblem(field)`**: Mensaje del primer problema del campo, o "" si está bien. De paso arregla el texto escrito. Un archivo elegido: tipo y tamaño. El servidor repite la revisión (también mira el contenido del archivo).
- **`problemOf(field, form)`**
- **`errorBoxOf(field)`**: Cuadro donde va el mensaje de error de un campo: el del propio campo o, en un grupo de radios, el del grupo.
- **`paint(field, message)`**: Muestra (o quita) el mensaje de error de un campo.
- **`radioProblems(form)`**: Opciones obligatorias en botones de radio: hay que marcar una de cada grupo.
- **`problemsOf(form)`**: Revisa todos los campos del formulario y devuelve la lista de problemas.
- **`listOf(problems)`**: La lista de problemas para la ventana se arma con texto plano, nunca con HTML.
- **`showProblems(problems, title)`**
- **`setUp(form, scope = document)`**: scope es la parte de la página donde se buscan los avisos de error que trajo el servidor.
- **`showServerErrors(form, title, scope)`**: Si el servidor devolvió el formulario con errores, la misma ventana los muestra al cargar la página.

### `core/static/core/js/widgets.js`

```text
Campos especiales de los formularios: selector de color, buscador de una lista, matriz de permisos y lista
que depende de otra. Sin JavaScript siguen funcionando como campos normales.
```

Funciones:

- **`setUpColor(box)`**: Color: el texto #RRGGBB, la muestra y el selector de color del navegador se mantienen iguales.
- **`showColor()`**: Muestra el color escrito; si el texto todavía no es un color completo, la muestra queda vacía.
- **`plain(text)`**: Sin tildes ni mayúsculas, para que "nunez" encuentre a "Núñez".
- **`matches(haystack, wanted)`**: ¿El texto de la opción contiene lo que se escribió? Un RUT se encuentra con o sin puntos: "12.345.678-5" y "12345678-5" son lo mismo.
- **`lookupView(title, options, onChoose, searchLabel = "Buscar por nombre o cargo")`**: Contenido de la ventana del buscador: un cuadro para filtrar y la lista de opciones. Al elegir una, se llama a onChoose con el texto que va en el campo.
- **`draw()`**
- **`setUpLookup(box, root)`**: Buscador: la lupa abre la ventana con la lista; al elegir un nombre, queda escrito en el campo.
- **`setUpPermissions(box)`**: Matriz de permisos de un rol: atajos (solo consulta, marcar todo, quitar todo) y coherencia entre casillas. Para crear, editar o eliminar en un módulo hace falta poder verlo: al marcar una de esas acciones se marca «Ver» de la fila, y al quitar «Ver» se quitan las demás. El servidor vuelve a comprobarlo al guardar.
- **`checks()`**
- **`setUpDependent(select, root)`**: Lista que depende de otra (la Sub Atención depende del Tipo de Atención): solo muestra las opciones del valor elegido en la primera y, si la opción elegida deja de ser válida al cambiar la primera, la limpia y lo avisa. Sin JavaScript se ven todas las opciones, cada una con el nombre de su padre.
- **`refresh(announce)`**
- **`setUpPasswordToggle(input)`**: Contraseña: un botón con un ojo para ver lo escrito y volver a ocultarlo. La contraseña vuelve a ocultarse sola al enviar el formulario y al salir de la página, para que no quede a la vista en el historial de la pestaña. Sin JavaScript el campo es una contraseña normal. Un campo con data-no-reveal no lleva el botón.
- **`show(visible)`**
- **`initWidgets(root = document)`**: Prepara los campos especiales que hay dentro de root (la página entera o un formulario recién cargado).

## 13. Hoja de estilos

`core/static/core/css/sgr.css` es la única hoja de estilos propia (sobre Bootstrap). Sus secciones, en orden:

- **Tipografía**: fuentes del sistema.
- **Variables**: colores, espacios y tamaños.
- **Base**: estilos generales.
- **Botones de Bootstrap**: ajuste de los botones.
- **Estructura: barra lateral y franja de arriba**: marca, barra lateral, bloque de la delegación, menú, franja de arriba y selector de delegación.
- **Página**: encabezados y estructura de cada pantalla.
- **Paneles**: tarjetas de contenido.
- **Filtros**: barra de búsqueda y filtros.
- **Tablas**: listados y acciones de cada fila.
- **Etiquetas de estado y sí/no**: chips de estado.
- **Barra de cumplimiento**: medidor con marcas de umbral.
- **Inicio**: dashboard.
- **Ficha**: detalle de un registro.
- **Formularios**: campos, ayudas y errores.
- **Tablero e informes**: tablero de delegación e informes.
- **Administración**: pantalla de administración.
- **Ingreso**: pantallas sin sesión.
- **Errores**: páginas de error.
- **Color, buscador de lista y perfiles en formularios**: campos especiales.
- **Matriz de permisos**: permisos de un rol.
- **Atención y Mi perfil**: pantallas de atención y de perfil.
- **Ventana modal**: formularios y buscador en ventana.
- **Ventanas de SweetAlert2**: avisos y confirmaciones.
- **Impresión**: estilos al imprimir.

## 14. Despliegue y configuración

| Archivo | Qué hace |
|---|---|
| `deploy/actualizar.sh` | Pone al día una instalación existente. Recibe la rama o etiqueta (por defecto `main`): baja la versión (`fetch`, `checkout`, `pull`), instala las dependencias, anota la versión desplegada en `COMMIT`, carga las variables de `/etc/sgr/sgr.env`, crea la carpeta de archivos subidos, ejecuta `check --deploy`, `migrate` y `collectstatic`, reinicia el servicio `sgr` y consulta `/salud/`. |
| `deploy/instalar_ec2.sh` | Primera instalación en una instancia EC2 con Ubuntu: instala los paquetes (Python, git, nginx y redis), crea el usuario `sgr`, clona el repositorio en `/opt/sgr/app`, crea el entorno virtual, instala las dependencias y deja `/etc/sgr/sgr.env` para completar. |
| `deploy/gunicorn.conf.py` | Configuración de gunicorn: dirección, procesos, hilos (clase `gthread`), tiempos y registro de acceso, con valores cambiables por variables de entorno. |
| `deploy/nginx-sgr.conf` | Sitio de nginx que pasa el tráfico a gunicorn (puerto 8000), con límite de 12 MB por petición. |
| `deploy/sgr.service` | Servicio de systemd que ejecuta gunicorn con el usuario `sgr`, desde `/opt/sgr/app` y con las variables de `/etc/sgr/sgr.env`. |
| `deploy/sgr.env.example` | Modelo de las variables de entorno para un servidor (copiar a `/etc/sgr/sgr.env`). |
| `deploy/requirements-produccion.txt` | Dependencias extra para el servidor: gunicorn, WhiteNoise y redis (y mysqlclient si la base es MySQL). |
| `deploy/al2023/instalar_al2023.sh` | Primera instalación en Amazon Linux 2023 (Apache, MariaDB y phpMyAdmin): recibe repositorio, rama y dirección del sitio; crea el usuario y las carpetas, el entorno virtual, el servicio y el sitio de Apache. |
| `deploy/al2023/https_certificado.sh` | Activa HTTPS en Amazon Linux 2023: pide el certificado a Let's Encrypt, pasa el sitio al puerto 443, redirige el 80 al 443 y deja la renovación automática. |
| `deploy/al2023/apache-http.conf` | Sitio de Apache por HTTP (fase 1): pasa el tráfico a gunicorn y deja fuera phpMyAdmin. |
| `deploy/al2023/apache-https.conf` | Sitio de Apache por HTTPS (fase 2): el puerto 80 solo verifica el certificado y redirige; el 443 sirve el sistema. |
| `deploy/al2023/sgr.env.example` | Modelo de variables de entorno para Amazon Linux 2023: modo, claves, HTTPS y proxy, base de datos, caché, correo y nivel de registro. |
| `requirements.txt` | Dependencias de Python: Django 6.1.1, asgiref, sqlparse, python-dotenv y openpyxl (exportar a Excel); `mysqlclient` opcional para MySQL/MariaDB. |
| `VERSION` | Versión del sistema que muestra `/salud/`. |
| `manage.py` | Punto de entrada de los comandos de Django. |

## 15. Scripts de la base de datos

| Archivo | Qué hace |
|---|---|
| `sql/sgr_django_v19.sql` | Estructura completa de la base `sgr_django` (32 tablas: 22 del proyecto, 6 del framework, 3 de unión y `django_migrations`) para MariaDB 10.11 / MySQL 8. |
| `sql/sgr_django_v19_dbeaver.sql` | El mismo esquema, pero crea una base aparte llamada `sgr_django_der` para abrirla en DBeaver y generar el diagrama. |
| `sql/sgr_v19_modelo_relacional_completo_en.sql` | Modelo relacional completo con nombres en inglés (`sgr_db`). |
| `sql/sgr_v13_a_v16_alter.sql` | Cambios de la base entre la v13 y la v16 (equivalen a las migraciones de `evidence` 0002 y 0003 y `accounts` 0005). |
| `sql/sgr_v3_modelo_relacional_completo.sql` | Modelo relacional de la v3. |
| `sql/sgr_v3_a_v5_alter.sql` | Agrega el color de la delegación a una base de la v3. |
| `sql/sgr_v5_a_v3_revertir.sql` | Quita el color de la delegación (deshace el anterior). |
| `sql/sgr_v5_modelo_relacional_completo.sql` | Modelo relacional de la v5 (la v3 más el color de la delegación). |
| `sql/sgr_v9_modelo_relacional_completo_en.sql` | Modelo relacional de la v9 con nombres en inglés. |
