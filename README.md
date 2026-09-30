# SGR · Programación Back End — Evaluación Sumativa II

Sistema de Gestión de Resultados (SGR) para delegaciones de la Ilustre
Municipalidad de La Serena. Este documento cubre la parte del proyecto
para **Programación Back End (TI3041)**: Django Admin, usuarios/roles,
seguridad (scoping) y auditoría, construida sobre el **modelo
relacional de 22 tablas** (`sql/sgr_v3_modelo_relacional_completo.sql`,
que es el `modelo_relacional_sgr_v2_completo.sql` entregado en Análisis y
Diseño más una columna: la dirección del beneficiario).

> **Cambio respecto al modelo original:** se agregó `Beneficiary.address`
> (columna `direccion` en la tabla `Beneficiario`): calle y número de la
> vivienda, un solo campo, opcional. El diagrama de base de datos es la
> referencia del proyecto: el cambio está primero en
> `sql/sgr_v3_modelo_relacional_completo.sql` (BD desde cero; se abre en
> DBeaver y de ahí se genera el diagrama ER) y en
> `sql/sgr_v1_a_v3_alter.sql` (para una BD ya creada con el script
> original). El modelo de Django calza con ese script. Como las
> migraciones aún no se generan, el `makemigrations` de la sección 4 ya
> incluye este campo en el `0001_initial`.

No se tocó nada de lo que ya existía en `core/views.py`, `core/urls.py`
ni los templates: son el mockup funcional previo (login, dashboard,
registrar actividad, cargar/validar evidencia, agenda colectiva,
tablero de delegación, catálogo de servicios). Todo lo nuevo vive en
modelos y en el Admin de Django.

> 📘 Este documento es la referencia rápida (instalación, cuentas de
> prueba, decisiones técnicas para la rúbrica). Para una explicación
> completa de cada archivo del código y de la semilla, pensada para
> poder defenderlo sin memorizar nada, ver **`GUIA_DEL_CODIGO.md`**.

## 1. Nomenclatura: inglés técnico + etiquetas en español

Los **modelos y atributos** usan nombres técnicos en **inglés**
(`Delegation`, `Officer`, `name`, `status`, `created_at`...). Lo que ve
el usuario final del Admin se mantiene en **español** mediante
`verbose_name` / `verbose_name_plural` y el texto visible de cada
`TextChoices` (lo que `get_FOO_display()` muestra). Por ejemplo:

```python
class Delegation(BaseModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Activa"      # código técnico en inglés, etiqueta en español
    name = models.CharField(max_length=100, verbose_name="nombre")
    status = models.CharField(choices=Status.choices, ...)
```

Los **datos de negocio** (nombres de roles/grupos como "Coordinación" o
"Funcionario", el catálogo de `ManagementType` como "Visita a terreno")
también se mantienen en español: son contenido, no nomenclatura técnica
del dominio.

## 2. Mapeo con el modelo relacional (22 tablas)

| Tabla SQL (Análisis y Diseño) | Modelo Django (Programación Back End) | App |
|---|---|---|
| Delegacion | `Delegation` | `organization` |
| Cargo | `Position` | `organization` |
| Funcionario | `Officer` | `organization` |
| Item | `Item` | `organization` |
| Servicio | `Service` | `organization` |
| Beneficiario | `Beneficiary` | `organization` |
| Territorio | `Territory` | `organization` |
| Cargo_Item | `PositionItem` | `organization` |
| Usuario | `auth.User` + `UserProfile` | `accounts` |
| Rol | `auth.Group` | `accounts` |
| Usuario_Rol_Delegacion | `user.groups` + `UserProfile.officer.delegation` | `accounts` |
| Periodo | `Period` | `planning` |
| Meta | `Goal` | `planning` |
| Indicador | `Indicator` | `planning` |
| Ajuste | `Adjustment` | `planning` |
| Tipo_Gestion | `ManagementType` | `operations` |
| Actividad | `Activity` | `operations` |
| Gestion_Atencion | `Followup` | `operations` |
| Compromiso | `Commitment` | `operations` |
| Evidencia | `Evidence` | `evidence` |
| Validacion | `Validation` | `evidence` |
| Auditoria | `AuditLog` | `core` |

`Meta` (SQL) se tradujo como `Goal` -y no como una clase `Meta`- para
evitar cualquier ambigüedad con la clase interna `class Meta` que usa
cada modelo de Django para sus opciones.

`Usuario`, `Rol` y `Usuario_Rol_Delegacion` no se reimplementan como
modelos propios: Django ya trae `auth.User` y `auth.Group`, y cada
`Officer` pertenece a una única `Delegation`, así que no hace falta una
tabla intermedia para la "delegación del usuario".

## 3. Arquitectura del proyecto

| App | Responsabilidad | Modelos |
|---|---|---|
| `core` | Modelo base (`BaseModel`: `created_at`/`updated_at`/`deleted_at`), auditoría, mixins de Admin (borrado lógico + scoping) reutilizados por el resto | `AuditLog` |
| `organization` | Datos maestros: delegaciones, cargos, funcionarios, catálogos | `Delegation`, `Position`, `Officer`, `Item`, `Service`, `Beneficiary`, `Territory`, `PositionItem` |
| `accounts` | Identidad: perfil de usuario, vínculo con `Officer` y roles (`Group`) | `UserProfile` |
| `planning` | Planificación y medición, a nivel de todo el proyecto (no se acota por delegación) | `Period`, `Goal`, `Indicator`, `Adjustment` |
| `operations` | Operación diaria, acotada por delegación | `ManagementType`, `Activity`, `Followup`, `Commitment` |
| `evidence` | Evidencia y su validación, acotada por delegación (vía la actividad) | `Evidence`, `Validation` |

Cada app sigue la misma estructura: `models.py`, `admin.py`,
`apps.py`, `migrations/`. `core/admin_mixins.py` y `core/admin_utils.py`
son las utilidades transversales (borrado lógico y scoping) que
importan el resto de las apps.

No hay `forms.py`: toda la gestión se hace desde el Django Admin, que
arma sus propios formularios a partir de los modelos, y las reglas de
validación viven en el `clean()` de cada modelo (sección 10 de este
documento y sección 7 de `GUIA_DEL_CODIGO.md`). Las únicas vistas y URLs
propias son las del mockup previo: `core/views.py`, `core/urls.py` y las
plantillas de `core/templates/` y `templates/`.

### Borrado lógico (`created_at` / `updated_at` / `deleted_at`)

Todos los modelos heredan de `core.models.BaseModel`. Ningún modelo
permite eliminar físicamente desde el Admin (`has_delete_permission`
devuelve `False`); en su lugar, todos tienen la acción **"Archivar
seleccionados"**, que marca `deleted_at` en vez de borrar la fila
(`core/admin_mixins.py::archive_selected`). `AuditLog` es de solo
lectura (ni se agrega, ni se edita, ni se archiva desde el Admin).

### Seguridad: scoping por delegación

`DelegationScopedAdminMixin` (`core/admin_mixins.py`) acota el Admin al
ámbito de la `Delegation` del usuario autenticado (`get_queryset`,
`formfield_for_foreignkey`, `save_model`, `has_change_permission`), a
partir de `core.admin_utils.get_user_delegation()`. Se aplica donde hay
un dueño claro por delegación: **Officer, Territory, Activity,
Commitment, Followup, Evidence y Validation**. Los superusuarios ven
todo (acceso técnico explícito); el resto solo ve/edita/archiva los
registros de su propia delegación — **excepto Coordinación**, que
también ve Officer y Territory de ambas delegaciones sin excepción,
porque administra el SGR completo, no una delegación puntual.

Los catálogos globales (Delegation, Position, Item, Service,
Beneficiary, PositionItem, ManagementType) y los datos de planificación
(Period, Goal, Indicator, Adjustment) NO se acotan por delegación: son
del SGR completo. Quién puede tocarlos lo define `seed_roles.py`: el
superusuario gestiona todo; Coordinación crea/edita Period, Goal y
Adjustment y solo consulta Indicator, Position, Item, Service y
PositionItem (Jefatura y Consulta solo consultan Indicator); Delegation,
Beneficiary y ManagementType los gestiona únicamente el superusuario.

## 4. Puesta en marcha (entorno limpio)

```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env              # y edita .env si necesitas otros valores
                                   # (por defecto usa SQLite, cero configuración)

python manage.py check
python manage.py makemigrations      # sin argumentos: detecta las 6 apps solo
python manage.py migrate

python manage.py seed_demo_data   # carga roles, catálogo y datos de demostración
                                   # (incluye las cuentas de prueba, ver sección 5)

python manage.py runserver
```

`seed_demo_data` ya crea un superusuario de prueba, así que
`createsuperuser` es opcional (solo si además quieres tu propia cuenta
personal de superusuario).

> ⚠️ **Paso obligatorio antes de entregar (Requisito 1 de la rúbrica,
> 10 pts):** este repositorio se entrega con `migrations/__init__.py`
> vacíos, sin migraciones generadas todavía, porque `makemigrations`
> necesita correr con Django realmente instalado y no se pudo verificar
> aquí. La rúbrica exige explícitamente **"migraciones versionadas"**
> como archivo, no solo poder generarlas. Antes de integrar tu rama a
> `main` o de entregar:
> 1. Corre `python manage.py makemigrations` (sin argumentos: detecta
>    las 6 apps solo).
>    Revisa que haya creado archivos `0001_initial.py` reales en cada
>    `*/migrations/`.
> 2. Corre `python manage.py migrate` y confirma que no hay errores.
> 3. Agrega esos archivos de migración al commit (`git add */migrations/*.py`)
>    y súbelos en tu rama — **sin esto, `migrate` en un computador
>    distinto al tuyo no crea las tablas y el proyecto no arranca**.

## 5. Cuentas de prueba (demostración / defensa en vivo)

**Estas son cuentas de prueba con contraseña fija para la demo, no las
credenciales reales de nadie.** Los usuarios llevan el nombre de
integrantes del equipo solo para que sea claro, en la defensa en vivo,
quién está "actuando" como cada rol — no comparten contraseña ni ningún
otro dato con ninguna cuenta personal real (correo, INACAP, etc.). Las
crea `seed_demo_data`:

| Usuario | Contraseña | Rol / contexto |
|---|---|---|
| `admin` | `Hola123!` | Superusuario, acceso completo a todas las delegaciones |
| `matias.cavieres` | `Hola123!` | Grupos "Funcionario" + "Verificador", `Officer` de **Delegación Norte** — solo ve/edita datos de Norte |
| `matias.quiroz` | `Hola123!` | Grupos "Funcionario" + "Verificador", `Officer` de **Delegación Sur** — solo ve/edita datos de Sur |
| `coordinacion1` | `Hola123!` | Grupo "Coordinación", **sin** `Officer` — ve catálogos/planificación y también Officer/Territory de **ambas** delegaciones |
| `jefatura1` | `Hola123!` | Grupo "Jefatura", `Officer` de **Delegación Norte** — igual que Funcionario, acotado a una sola delegación |

Cada usuario tiene ambos grupos para poder demostrar, dentro de su
propia delegación, los 7 modelos acotados (Officer, Territory,
Activity, Commitment, Followup, Evidence **y** Validation) sin
necesitar una cuarta cuenta. `coordinacion1` y `jefatura1` cubren los 2
roles que, si no, quedarían sin ningún usuario de demostración; a
diferencia de los otros cuatro, Coordinación no necesita un `Officer`
porque no lo acota ninguna delegación (ver "Seguridad: scoping por
delegación" más arriba).

De los 5 roles, "Consulta" (de solo lectura) es el único sin cuenta de
demostración ya creada; tampoco hay una segunda cuenta de Jefatura para
Delegación Sur. `seed_demo_data` sí deja listos los `Officer` que
corresponden a ambos casos, sin usuario vinculado a propósito:

| `institutional_id` | Nombre | Delegación | Pensado para el grupo |
|---|---|---|---|
| `F-1004` | Consulta Norte | Norte | Consulta |
| `F-2004` | Consulta Sur | Sur | Consulta |
| `F-2005` | Jefatura Sur | Sur | Jefatura |

Sirven para practicar el alta manual de un usuario (Admin > Auth >
Users > Add user, tildar "Staff status", asignar el grupo que
corresponda y vincular uno de estos `Officer` en "Perfil de usuario").
Si el campo "Perfil de usuario" queda sin `Officer`, el usuario puede
entrar al Admin pero recibe un 403 al abrir cualquier modelo acotado
por delegación (`get_user_delegation` no encuentra a qué delegación
pertenece) — solo ve Indicador, que no está acotado.

### Cómo comprobar el scoping (Requisito 7 de la rúbrica)

1. Inicia sesión como `matias.cavieres` en `/admin/`: en Actividad,
   Compromiso, Gestión de atención, Evidencia y Validación solo deben
   aparecer registros de **Delegación Norte**.
2. Cierra sesión e inicia como `matias.quiroz`: los mismos listados
   deben mostrar solo **Delegación Sur**, sin ningún registro de Norte.
3. Inicia sesión como `admin`: debe ver los registros de ambas
   delegaciones sin restricción.

`seed_demo_data` también deja un ejemplo de `updated_at` distinto de
`created_at` (una Actividad de Delegación Norte se modifica después de
creada) y dos ejemplos ya archivados (`deleted_at` poblado), en dos
modelos distintos: una Actividad y una Evidencia, ambas de Delegación
Norte — para dejar claro que el borrado lógico es un mecanismo genérico
de `BaseModel`, no algo propio de un solo modelo.

### Cómo ver un registro archivado (`deleted_at`)

Por diseño, el Admin oculta por defecto los registros archivados (es el
punto del borrado lógico: no estorban en el listado normal). Para
verlos, agrega `?show_archived=1` al final de la URL del listado, por
ejemplo `/admin/operations/activity/?show_archived=1`: aparece también
la actividad archivada, con una columna `deleted_at` adicional mostrando
la fecha. Esto aplica a cualquier modelo con borrado lógico, respetando
igual el scoping por delegación si el usuario no es superusuario.

## 6. Comandos de carga de datos

| Comando | Qué hace |
|---|---|
| `python manage.py seed_roles` | Crea los 5 grupos/roles (Coordinación, Jefatura, Funcionario, Verificador, Consulta) con sus permisos |
| `python manage.py seed_management_types` | Carga el catálogo `ManagementType` (igual al INSERT del script SQL) |
| `python manage.py seed_demo_data` | Ejecuta los dos anteriores y además crea delegaciones, catálogos, las cuentas de prueba y registros operacionales en ambos contextos (ver sección 5) |

Los tres comandos son **idempotentes**: se pueden volver a ejecutar sin
duplicar datos ni fallar por registros ya existentes.

## 7. Conexión a base de datos (`.env`)

`sgr_project/settings.py` lee `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS` y
los datos de conexión desde variables de entorno (vía `python-dotenv`,
cargando `BASE_DIR/.env`); ningún valor sensible queda escrito en el
código. Por defecto (`DB_ENGINE=sqlite` en `.env.example`) no requiere
ningún servidor de base de datos. Para usar MySQL/MariaDB (acercándose
a `sql/sgr_v3_modelo_relacional_completo.sql`), cambia `DB_ENGINE=mysql` y
completa `DB_NAME`/`DB_USER`/`DB_PASSWORD`/`DB_HOST`/`DB_PORT` en tu
`.env`, e instala `mysqlclient` (línea comentada en
`requirements.txt`) — no se toca `settings.py` para cambiar de motor.

`.env` está en `.gitignore` y nunca se sube al repositorio; solo
`.env.example` (sin secretos reales) va en el repositorio.

## 8. Gestión Git

Recuerda el flujo del curso: el primer commit de creación/configuración
puede ir directo a `main`; todo el desarrollo posterior (como este
cambio) debe hacerse en una rama y llegar a `main` por merge o Pull
Request. Evita subir `.env`, `.venv/` o `db.sqlite3` (ya están en
`.gitignore`).

## 9. Relación con el resto del proyecto

Este trabajo no reemplaza ni contradice los artefactos ya entregados
para Análisis y Diseño (diagrama entidad-relación / mermaid, casos de
uso, script SQL de 22 tablas): los usa como base y los implementa en
Django con nomenclatura técnica en inglés, tal como pide la Evaluación
Sumativa II de Programación Back End. Si comparas el diagrama mermaid
con las apps de este proyecto, vas a notar que `TIPO_ACTIVIDAD` no
aparece aquí -esa entidad era de un borrador temprano y no llegó a la
versión final de 22 tablas (fue reemplazada por `Item` con
auto-referencia para el par Tipo de Atención → Sub Atención)-; todo lo
demás del diagrama final está presente, con su nombre en inglés.

## 10. Decisiones técnicas relevantes

El código fuente se mantiene sin comentarios ni docstrings a propósito
(decisión del alumno); el razonamiento de las decisiones no obvias vive
acá, que es donde la rúbrica pide documentar "decisiones técnicas
relevantes" (sección Documentación de los entregables).

- **`BaseModel` es un agregado de Django, no del modelo relacional.**
  `created_at`/`updated_at`/`deleted_at` no existen en
  `sql/sgr_v3_modelo_relacional_completo.sql` (22 tablas): se agregaron
  solo en esta capa de Django para cumplir la auditoría que pide
  Programación Back End. Las tablas y relaciones son las del modelo de
  Análisis y Diseño más una columna: la dirección del beneficiario.
- **Todas las FK usan `on_delete=PROTECT`, incluso las opcionales
  (`null=True`).** El script SQL no declara `ON DELETE` en ninguna
  restricción, por lo que el comportamiento por defecto de InnoDB
  (`RESTRICT`) es el que corresponde replicar en Django.
- **Scoping por delegación es la excepción, no la regla.** Solo los 7
  modelos con dueño claro por delegación (Officer, Territory, Activity,
  Commitment, Followup, Evidence, Validation) usan
  `DelegationScopedAdminMixin`. Los catálogos (Position, Item, Service,
  etc.) y la planificación (Period, Goal, Indicator, Adjustment) no se
  acotan: son del SGR completo, no de una delegación (Coordinación, que
  supervisa el SGR entero, edita la planificación y consulta los
  catálogos). Por esa misma razón, `DelegationScopedAdminMixin.get_queryset`
  deja pasar sin filtrar tanto a los superusuarios como a cualquier
  usuario del grupo "Coordinación" -de los modelos acotados, ese grupo
  solo tiene permiso de *ver* Officer/Territory, así que la excepción
  nunca abre un camino de escritura.
- **`PositionItem.Kind` distingue Normal de Bonificación/Penalización.**
  Cuando `kind` no es `NORMAL`, el modelo exige `max_cap` (`clean()`
  levanta `ValidationError` si falta) -replica la regla de negocio real
  de que una bonificación o penalización siempre tiene un tope.
- **La tabla `Meta` del script SQL se llama `Goal` en Django, no
  `Meta`.** Se evitó ese nombre para no chocar con la clase interna
  `class Meta` que Django usa en cada modelo para sus opciones
  (`ordering`, `verbose_name`, etc.).
- **`seed_demo_data` es idempotente vía `get_or_create()`.** Cada
  registro se busca primero por su clave lógica (nombre, código único,
  combinación de FKs) y solo se crea si no existe; se puede correr el
  comando muchas veces sin duplicar datos ni romper nada. Por eso
  cambiar los `defaults` de un `get_or_create()` no actualiza registros
  que ya existían en una base de datos previa -solo aplica a los que se
  crean de ahí en adelante. La única excepción, a propósito, es la
  dirección de los beneficiarios: si uno ya existía con la dirección
  vacía (base cargada antes de agregar `address`), la semilla se la
  completa.
- **Los datos de carga cubren todos los estados/choices de cada
  modelo operativo**, no solo el "camino feliz": Evidence tiene un
  ejemplo Pendiente, uno Aprobado y uno Rechazado; Validation tiene
  Aprobado, Rechazado y Observado; Commitment tiene Ingresado, En
  proceso y Cumplido, externo e interno; hay dos registros archivados
  (`deleted_at` poblado) en dos modelos distintos (Activity y
  Evidence), para dejar claro que el borrado lógico es un mecanismo
  genérico y no algo específico de un solo modelo.
