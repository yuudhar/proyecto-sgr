# SGR · Sistema de Gestión de Resultados

Aplicación web hecha en Django para registrar y dar seguimiento al trabajo de las delegaciones municipales: atención de público, actividades, compromisos, evidencias, planificación e informes. Cada persona ve solo lo que su rol y sus delegaciones le permiten.

Es un proyecto académico de Programación Back End. Todos los datos son ficticios y no representa un sitio oficial de la Municipalidad de La Serena.

## Integrantes

- Matías Quiroz
- Matías Cavieres
- Sakty Argandoña

## Qué permite hacer

- **Atención:** buscar a una persona por RUT o nombre e ingresar una atención con su tipo y sub atención.
- **Dashboard, tablero de delegación e informes:** indicadores del período, semáforo de metas y exportación a Excel.
- **Mantenedores:** delegaciones, funcionarios, cargos, territorios, beneficiarios, catálogo de servicios, períodos, metas, ítems, tipos de atención y sub atención.
- **Operación y evidencias:** actividades, compromisos, seguimientos, evidencias y su validación.
- **Usuarios y permisos:** roles con permisos por módulo, delegaciones autorizadas por usuario y recuperación de contraseña con código de seis dígitos.
- **Auditoría:** cada cambio queda registrado con quién, cuándo y qué se modificó.

Todos los listados incluyen búsqueda (sin distinguir mayúsculas ni tildes), paginador, filtros y exportación a Excel. Los formularios se abren en ventanas modales, validan los datos y avisan con SweetAlert2.

## Tecnologías

- Python 3.12 o superior y Django
- SQLite (MySQL opcional)
- Bootstrap 5 y SweetAlert2 (incluidos en el proyecto, funciona sin internet)
- openpyxl para los archivos de Excel
- gunicorn y nginx para el despliegue en un servidor

## Instalación

Necesitas Python 3.12 o superior. Abre Git Bash dentro de la carpeta del proyecto (la que contiene `manage.py`) y ejecuta:

```bash
python -m venv venv
source venv/Scripts/activate
python -m pip install -r requirements.txt

cp .env.example .env

python manage.py migrate
python manage.py seed_demo_data
python manage.py runserver
```

Luego abre `http://127.0.0.1:8000/` en el navegador.

En Linux o macOS la activación del entorno es `source venv/bin/activate` y el comando de Python es `python3`.

Las próximas veces solo hacen falta dos comandos:

```bash
source venv/Scripts/activate
python manage.py runserver
```

## Cuentas de prueba

Las crea `seed_demo_data`. Se ingresa con el **usuario** (no con el correo) y todas tienen la contraseña `Hola123!`.

| Usuario | Rol |
|---|---|
| `admin` | Super Usuario, ve todo |
| `coordinacion1` | Coordinación: catálogos y planificación |
| `jefatura1` | Jefatura de la Delegación Norte |
| `supervision1` | Jefatura con las delegaciones Norte y Sur |
| `matias.cavieres` | Funcionario y Verificador, Delegación Norte |
| `matias.quiroz` | Funcionario y Verificador, Delegación Sur |
| `consulta1` | Solo lectura |

Para recuperar una contraseña, cada cuenta tiene un correo con la forma `usuario@sgr.example`. Como ese dominio no existe, el código no se envía: aparece en la ventana de Git Bash donde corre el servidor.

## Estructura del proyecto

```
sgr_project/    configuración de Django
core/           portal, menús, búsqueda, exportación a Excel y auditoría
accounts/       ingreso, recuperación de contraseña, roles y delegaciones
organization/   delegaciones, funcionarios, cargos, territorios y beneficiarios
planning/       períodos, metas e indicadores
operations/     atenciones, actividades, compromisos y seguimientos
evidence/       evidencias y su validación
templates/      plantillas HTML
sql/            scripts de la base de datos
deploy/         archivos para publicar en un servidor
docs/           documentación y evidencias
tools/          herramientas de pruebas
```

## Configuración

La configuración se lee desde el archivo `.env`, que se crea a partir de `.env.example` y no se sube al repositorio. Las variables principales son:

| Variable | Uso |
|---|---|
| `DEBUG` | `True` en desarrollo y `False` en producción |
| `SECRET_KEY` | clave secreta propia; en producción es obligatoria |
| `ALLOWED_HOSTS` | dominios o IP desde los que se accede |
| `DB_ENGINE` y `DB_*` | base de datos: `sqlite` (por defecto) o `mysql` |
| `EMAIL_HOST` y `EMAIL_*` | servidor de correo para la recuperación de contraseña |

## Base de datos

El esquema se crea con las migraciones de Django (`python manage.py migrate`), que vienen incluidas en el repositorio. La carpeta `sql/` guarda además los scripts y el diagrama entidad-relación de versiones anteriores del modelo.

Para usar MySQL en lugar de SQLite, completa las variables `DB_*` del `.env` y activa `mysqlclient` en `requirements.txt`.

## Estado del proyecto

Todos los módulos descritos arriba funcionan con base de datos real, permisos por rol y alcance por delegación. Los datos de demostración son ficticios, y mientras no se configure un servidor de correo el código de recuperación se muestra en la consola.

Quedan pendientes la aplicación de las normas gráficas oficiales (escudo y código de color), la publicación del sistema en AWS y el envío de correos reales.
