# Historial de cambios

Una sección por versión, de la más nueva a la más antigua.

Nombres que cambiaron en la v27 (los textos antiguos los mencionan con el nombre de entonces):

| Antes | Ahora |
|---|---|
| `core/test_a1.py` | `core/test_roles_delegations_items.py` |
| `core/test_a2.py` | `core/test_context_and_norms.py` |
| `core/test_v16.py` | `core/test_uploads_photos_attention.py` |
| `core/test_v22.py` | `core/test_delete_and_list_tools.py` |
| `core/test_v23.py` | `core/test_deleted_users.py` |
| `core/test_v24.py`, `core/test_v27.py`, `core/test_v28.py` (el de la v27) | `core/test_realtime.py` (y `DaphneDeployTests` en `core/test_deploy.py`, `UserPhotoByAdminTests` en `core/test_uploads_photos_attention.py`) |
| `core/test_v25.py` | `core/test_pace_and_commitments.py` |
| `core/test_v26.py` | `core/test_results_and_calculation.py` |
| `core/qa/esperado_vNN.py` | `core/qa/esperado_<tema>.py` (mismo tema que su archivo de pruebas) |
| `sql/*.sql` (todos) | `sql/sgr_django.sql` (estructura vigente) |

## Versión 40

Lo último pendiente de la lista de la clienta: el **cambio de trimestre de una atención** (por ejemplo, una atención de diciembre que pasa a enero), que **pide el funcionario y aprueba o rechaza la jefatura**. Se arma sobre la v39.

### Cómo funciona

- Un trimestre es un **período** y una atención pertenece al período que contiene su fecha. Pasarla a otro trimestre es cambiarle la fecha, y para eso hace falta que la jefatura lo apruebe.
- Pantalla nueva **Cambios de trimestre** en *Operación* (`/cambios-trimestre/`), en vista de tarjetas con tres columnas, **Pendiente**, **Aprobada** y **Rechazada**, indicadores arriba y códigos `TRI00001`…
- **El funcionario pide** el cambio: elige la atención (solo de su delegación, sin archivadas), el modo y escribe el motivo.
  - **Automático**: la atención pasa al **primer día del trimestre siguiente**.
  - **Manual**: elige la fecha nueva, que tiene que caer en otro trimestre. La fecha solo aparece en este modo.
- **La jefatura resuelve**: abre la solicitud con «Editar», ve un resumen de lo pedido (quién, la atención, fechas con su trimestre y motivo) y elige **Aprobada** o **Rechazada**. Al rechazar tiene que escribir la respuesta; al aprobar es opcional.
- Mientras está pendiente, la atención **conserva su fecha**. Al aprobar toma la fecha nueva y queda en el otro trimestre; el cambio queda en la auditoría de la atención («Cambio de trimestre aprobado») y en la de la solicitud, y se avisa en vivo a las pantallas abiertas. Una solicitud resuelta ya no se edita: queda como registro.
- La ficha de la atención lista sus solicitudes de cambio de trimestre.

### Reglas

- La fecha nueva **no puede ser futura** (una atención no puede tener fecha futura): el modo automático solo se puede pedir cuando el trimestre siguiente ya empezó.
- El trimestre de destino tiene que existir y **no estar cerrado**. El de origen sí puede estar cerrado: ese es justamente el caso que necesita la aprobación.
- Una atención con una solicitud pendiente no puede tener otra; después de un rechazo se puede pedir de nuevo.
- Al aprobar se revisa todo otra vez, porque pasó tiempo: la atención sigue sin archivar y con la misma fecha, el trimestre de destino sigue abierto y el funcionario no supera el máximo de 7 atenciones por día en la fecha nueva. Si algo cambió, la solicitud sigue pendiente y se explica por qué.
- Un archivado no se ofrece y una atención de otra delegación tampoco; la jefatura de otra delegación no ve ni resuelve solicitudes ajenas.

### Permisos

- Fila nueva «Cambios de trimestre» en la matriz de Roles (`operations.*_quarterchangerequest`). **Funcionario** puede ver y crear; **Jefatura** puede ver y editar (editar es resolver). `seed_roles` los entrega a los roles base; las cuentas de revisión los reciben por su rol (`admin_a` es Jefatura y Funcionario; `editor_a`, Funcionario; los lectores no tienen el módulo).

### Base de datos

- Migración `operations/0008_cambio_de_trimestre_v40`: tabla nueva `operations_quarterchangerequest`.
- `sql/sgr_django.sql` y `docs/DIAGRAMA_MODELOS.md` quedan al día. Se corrige además el número de tablas de los documentos (37 en la base, 27 del proyecto), que seguía en el de versiones anteriores.

### Datos de la revisión

- `cargar_datos_revision` carga además **110 solicitudes** (55 por delegación: 20 pendientes, 25 aprobadas y 10 rechazadas, con automáticas y manuales, respuestas y quién resolvió), cada una con **su propia atención** (110 atenciones más, sin tocar las demás). Los datos de la revisión tienen un solo período por año, así que el cambio posible es el de **fines de 2025 (período cerrado) a enero de 2026**: las pendientes y rechazadas tienen su atención en diciembre y las aprobadas ya la tienen en enero. Con su propio azar, el resto de los datos sale igual que en la v39. Total sobre una base recién migrada: 3.925 registros (3.873 vigentes); repetirlo no duplica.
- Para probarlo en el servidor: `admin_a` (Jefatura) abre una solicitud pendiente de Norte en *Cambios de trimestre* con «Editar» y la aprueba o la rechaza (con respuesta); la atención aprobada pasa a enero. `editor_a` ve las solicitudes de su delegación y puede pedir un cambio nuevo, pero con estos datos solo hay un trimestre distinto del vigente (el de diciembre de 2025), así que para pedir uno nuevo hay que crear antes otro trimestre en *Períodos*.
- `datos_prueba` (demostración local) agrega una solicitud pendiente sobre una atención que ya existía (sin atenciones nuevas).

### Pruebas

- Nuevo `core/test_cambio_de_trimestre.py` (41 pruebas, registradas en el catálogo QA como V40-01): trimestre de una fecha y trimestre siguiente, pedir (automático, manual, todas las fechas rechazadas, duplicadas, alcance), resolver (aprobar, rechazar, una sola vez, día lleno, fecha cambiada, destino cerrado, permisos) y pantalla (tarjetas, indicadores, botones, ficha, roles y aviso en vivo).

### ❓ Para confirmar con la clienta o el grupo

- **Quién puede pedir:** hoy cualquier funcionario puede pedirlo para cualquier atención de su delegación. ¿Solo para las atenciones que registró él?
- **Quién resuelve:** la jefatura de la delegación. ¿También Coordinación, o la jefatura no puede aprobar lo que pidió ella misma?
- **Fecha futura:** no se permite. ¿Se necesita mover una atención a una fecha que aún no llega (por ejemplo, desde diciembre a una fecha de enero cuando todavía es diciembre)?
- **Modo automático:** pasa al primer día del trimestre siguiente. ¿Prefiere conservar el día y el mes, o el primer día hábil?
- **Compromisos de la atención:** el compromiso que nace de una atención con visita conserva su fecha comprometida; no se mueve con la atención. ¿Debería moverse?
- **Período cerrado:** hoy se puede sacar una atención de un trimestre cerrado con aprobación. ¿La jefatura puede aprobarlo o hace falta Coordinación?

## Versión 39

Dos cambios que pidió la clienta: la **directiva de las organizaciones** y el **tipo de solicitante** (persona natural u organización) en la atención. Se arma sobre la v38.

### Directiva de las organizaciones

- Registro propio, **no es un beneficiario**: cada integrante de la directiva pertenece a una organización y lleva **cargo** (presidente, secretario, tesorero, directivo u otro cargo), **nombre**, **RUT** y **correo** (opcional). Con «Otro cargo» se escribe cuál (por ejemplo, *Delegado de calle*).
- Reglas: una organización tiene a lo más **un presidente, un secretario y un tesorero** vigentes, puede tener varios directivos y no repite el RUT; la misma persona sí puede estar en la directiva de dos organizaciones. Archivar a alguien libera su cargo; no se puede restaurar mientras otra persona lo ocupe.
- Pantalla nueva **Directivas** en *Administración › Catálogos* (`/directivas/`), con búsqueda, filtros por cargo y organización, archivo y Excel como los demás catálogos. Es un catálogo compartido entre delegaciones, como las organizaciones.
- En la **ficha de cada organización** aparece el bloque **Directiva**, con el enlace para agregar a alguien con la organización ya elegida.
- Permisos: fila nueva «Directivas de organizaciones» en la matriz de Roles (`organization.*_organizationleader`). Las cuentas de revisión: administrador A todo; editor A y lectores, solo ver.

### Tipo de solicitante en la atención

- La atención lleva un selector **Tipo de solicitante**: **Persona natural** (como hasta ahora: RUT o nombre, con búsqueda en Beneficiarios) u **Organización**.
- Con **Organización** se elige la organización y **quién de su directiva viene** (la lista ofrece solo a los de esa organización, con su cargo). El contacto de la atención queda con el nombre de esa persona (si no se elige a nadie, con el de la organización) y no se pide RUT ni nombre del solicitante.
- Cada grupo de campos aparece solo para su tipo (`data-show-if` y `data-required-if`, piezas nuevas de `widgets.js`) y el servidor revisa lo mismo: la organización es obligatoria para ese tipo y la persona tiene que ser de su directiva. Con persona natural la organización sigue siendo opcional, como antes (la junta con la que se relaciona la atención), y se descarta el integrante de la directiva.
- Al **editar** una atención se puede pasar de un tipo a otro.
- El listado de Atención filtra por tipo de solicitante y la ficha muestra el tipo y a la persona de la directiva. El puntaje no cambia: sigue exigiendo nombre y teléfono del contacto.

### Corrección de un fallo que ya existía

- `widgets.js` se cargaba dos veces (desde la página y desde `crud-modal.js`, que lo importa sin el `?v=` de la versión) y la segunda preparación de las listas que dependen de otra las dejaba vacías: en el navegador, **Sub atención** mostraba «Este tipo no tiene sub atenciones» aunque el tipo las tuviera. Ahora cada lista se prepara una sola vez (`dataset.dependentReady`). La misma corrección hace funcionar la lista «quién de la directiva viene».

### Base de datos

- Migración `organization/0006_directiva_organizaciones_v39`: tabla nueva `organization_organizationleader`.
- Migración `operations/0007_tipo_de_solicitante_v39`: columnas `requester_kind` (por defecto «persona natural») y `organization_leader` en `operations_activity`. Las atenciones que ya estaban a nombre de una organización y sin persona quedan como «Organización».
- `sql/sgr_django.sql` y `docs/DIAGRAMA_MODELOS.md` quedan al día.

### Datos de la revisión

- `cargar_datos_revision` carga además la directiva de las 80 organizaciones (375 integrantes: siempre un presidente, y con secretario, tesorero, directivos y otros cargos variados; con su propio azar para que el resto de los datos salga igual que en la v38) y deja a cada atención de organización con quién de la directiva vino. Las atenciones de organización nuevas nacen con el tipo «Organización». Total sobre una base recién migrada: 3.705 registros; repetirlo no duplica.
- `datos_prueba` (datos de demostración locales) agrega cuatro integrantes a la junta de vecinos de demostración.

### Pruebas

- Nuevo `core/test_directiva_y_solicitante.py` (38 pruebas, registradas en el catálogo QA como V39-01 y V39-02): directiva (alta, cargos únicos, RUT repetido, otro cargo, archivar y restaurar, permisos, ficha de la organización) y tipo de solicitante (persona natural como antes, organización con su directivo, validaciones, edición, listado, puntaje y migración de los datos antiguos).

### ❓ Para confirmar con la clienta o el grupo

- **Correo de la directiva:** hoy es opcional. ¿Debe ser obligatorio?
- **Cargos:** presidente, secretario, tesorero, directivo y «otro cargo» con detalle. ¿Falta alguno fijo (por ejemplo, vicepresidente)?
- **Quién viene:** al elegir una organización, elegir a la persona de la directiva es opcional (si no se elige, el contacto es la organización). ¿Debe ser obligatorio cuando la organización ya tiene directiva?
- **Teléfono de la organización:** la atención de una organización pide el teléfono de contacto escrito en la atención; la directiva todavía no guarda teléfono. ¿Se agrega?
- **Pendiente de la lista de la clienta** (v40): el cambio de trimestre de una atención (por ejemplo, una actividad de diciembre que pasa a enero), pedido por el funcionario y aprobado o rechazado por la jefatura.

## Versión 38

Dos cambios que pidió la clienta, ambos con la vista de tarjetas (canvas) de su modelo «Tubo»: **Cartas** (antes *Felicitaciones y reclamos*) y una sección nueva, **Compromisos**, para lo físico.

### Vista canvas

- Pieza común del motor de listados (`Canvas` en `core/crud.py`, plantilla `core/templates/core/partials/canvas.html`, estilos al final de `sgr.css`). Muestra los indicadores arriba y una columna por valor de un campo; cada tarjeta lleva código, título, datos clave, «Ver» y «Editar».
- Es el mismo listado de siempre: la búsqueda, los filtros, «Incluir archivados», el Excel, el alcance por delegación y la actualización en vivo por WebSocket funcionan igual. Solo cambia cómo se dibujan los resultados.
- Si un módulo lo permite (`movable`), cada tarjeta trae botones para pasar el registro al estado siguiente, con un solo clic (`CrudMoveView`, `POST /<módulo>/<id>/estado/`). El servidor valida el cambio con las reglas del modelo, deja el historial y la auditoría y avisa por WebSocket; un lector recibe 403 y una tarjeta de otra delegación, 404.

### Cartas

- *Felicitaciones y reclamos* pasa a llamarse **Cartas** en el menú, la matriz de permisos de Roles, la pantalla y la tabla. La dirección cambia de `/felicitaciones-y-reclamos/` a **`/cartas/`** (la antigua ya no existe).
- Se ve en canvas con dos columnas, **Felicitación** y **Reclamo**, y tres indicadores (cartas, felicitaciones y reclamos con su porcentaje). Cada tarjeta muestra a quién involucra, la fecha, quién escribe, el medio, el efecto sobre el funcionario y si tiene respaldo. Los códigos son `CAR00001`…
- No cambian las reglas: solo el delegado las registra, el ajuste (suma o resta) se genera solo y cada delegación ve lo suyo.
- El módulo «Tubo de cartas» que se había armado aparte para esta versión se descartó: *Cartas* es este.

### Compromisos

- Sección nueva en *Operación*, junto a *Agenda colectiva*. Es **lo físico**: cuando una atención **requiere visita a terreno**, al registrarla se piden la fecha comprometida y el territorio, y el compromiso se crea solo en Compromisos (estado inicial «Ingresado», con su historial). Si la atención solo marca «ingresa al tubo de trabajo», sigue yendo a la Agenda colectiva. Con las dos casillas marcadas se crea un solo compromiso, de terreno.
- Se ve en canvas con las cuatro columnas **Ingresado, Pendiente, En proceso y Realizado**, cuatro indicadores (compromisos, realizados con la tasa de resolución, en proceso activo, pendientes) y los botones para pasar cada tarjeta de estado (*A Pendiente*, *A Proceso*, *Realizar*). Los códigos son `COM00001`…
- Comparte la tabla de la Agenda colectiva: `operations_commitment` tiene una columna nueva, `physical` (de terreno). La Agenda lista los que no son de terreno y Compromisos los que sí; la ficha abre desde cualquiera de las dos. El **resumen colectivo**, el dashboard y el tablero siguen contando todos.
- También se puede crear un compromiso a mano desde Compromisos; queda marcado como de terreno.
- Los permisos son los de la Agenda (`operations.*_commitment`); en la matriz de Roles la fila se llama «Agenda colectiva y compromisos».

### Base de datos

- Migración `operations/0006_compromisos_de_terreno_v38`: columna `physical` en `operations_commitment`, con índice.
- Migración `planning/0006_cartas_v38`: solo cambia los nombres de la tabla de felicitaciones y reclamos (opciones del modelo); no toca datos.
- `sql/sgr_django.sql` y `docs/DIAGRAMA_MODELOS.md` quedan al día.

### Datos de la revisión

- `cargar_datos_revision` carga además 55 compromisos de terreno por delegación (lo último que carga, así que el resto sale igual que en la v37; repetirlo no duplica). Total sobre una base recién migrada: 3.330 registros. Las 110 cartas son las mismas felicitaciones y reclamos de antes.
- `datos_prueba` (datos de demostración locales) deja un compromiso de terreno por delegación.

### Pruebas

- Nuevo `core/test_cartas_y_compromisos.py` (27 pruebas, registradas en el catálogo QA como V38-01 y V38-02): cartas en canvas, compromisos en canvas, cambio de estado desde la tarjeta (permitido, rechazado, lector, otra delegación), atención con visita y resumen que cuenta todo.
- Se ajustaron pruebas existentes al cambio: nombre y dirección de Cartas, la fila de la matriz de Roles, el listado de la Agenda (ya no trae los de terreno), los módulos que se pueden eliminar y la casilla que muestra la fecha y el territorio.

### ❓ Para confirmar con la clienta o el grupo

- **Cartas en canvas:** hoy las columnas son por tipo (Felicitación y Reclamo). ¿Se esperan columnas por estado de seguimiento, como en el Tubo de compromisos?
- **Qué es «físico»:** hoy lo define la casilla «requiere visita» de la atención. ¿Hay otros casos?
- **Atenciones marcadas «requiere visita» de antes** no tienen compromiso: al editarlas, la fecha y el territorio son opcionales (igual que con el tubo de trabajo).
- **Permisos de Compromisos:** comparte los de la Agenda colectiva. ¿Se necesita separarlos?
- **Resumen colectivo:** cuenta los compromisos de terreno junto con los de la agenda. ¿Debe separarlos?
- **Pendiente de la lista de la clienta** (para versiones siguientes): organizaciones comunitarias con presidente, tesorero y secretario (nombre, RUT, correo), persona natural u organización en la atención, y el cambio de trimestre con aprobación.

## Versión 37

Ensayo de los diez pasos de la revisión de la Evaluación Sumativa III y revisión final antes del Pull Request. No cambia la aplicación ni la base de datos: agrega pruebas, una herramienta de ensayo con navegador y la guía para repetirlo en AWS.

### Qué se ensayó y cómo

- **Ensayo local con navegador real** (Daphne + Chrome, una sesión por cuenta) sobre los datos que deja `cargar_datos_revision`: 64 comprobaciones correctas, 0 fallas de la aplicación y 2 que quedan manuales (el correo real y la página 500). Un rastreo de todos los enlaces del menú de las seis cuentas tampoco encontró errores. **No se pudo ensayar en AWS** desde el entorno de desarrollo: la herramienta y la guía quedan para repetirlo allí.
- **`tools/ensayo/ensayo_revision.py`**: recorre los diez pasos contra una dirección (`--url`), con una función por paso, una sesión de navegador por cuenta y las contraseñas solo del entorno (`SGR_REVISION_PASSWORD` o `SGR_PASSWORD_<ALIAS>`). Los datos que crea llevan la marca «ENSAYO» y se archivan al terminar; imprime `OK`, `FALLÓ` o `MANUAL` y puede escribir un informe (`--informe`) y capturas (`--capturas`). Termina con código 1 si algo falló. Se puede importar sin Playwright (solo lo exige al abrir el navegador).
- **`core/test_ensayo_revision.py`** (54 pruebas, una clase por paso más una de herramienta y guía): lo mismo que se hizo con el navegador, sin navegador y sobre la misma carga de datos, con el cliente de pruebas de Django y `WebsocketCommunicator`. Cubre, entre otras cosas, tres reglas de negocio que rechazan el guardado, el Excel con el conjunto filtrado, el 403 del lector por URL y petición directa, el 404 entre organizaciones (detalle, edición, archivo, relaciones ajenas y Excel), los avisos por WebSocket después del commit (y ninguno si el guardado es inválido o la transacción se deshace), la recuperación de contraseña con enlace de un solo uso, el recorte cuadrado de la foto y las dos cuentas cliente.
- **`docs/ENSAYO_REVISION.md`**: por cada paso, la cuenta, qué mostrar y el resultado esperado; el recorrido del evento en vivo con los archivos (`core/crud.py` → `websocket/services.py` → `websocket/consumers.py` → `core/static/core/js/live-updates.js`); cómo correr la herramienta y repetir todo en AWS; ramas y Pull Request; y lo que falta decidir.
- README: fila nueva en *Registro de pruebas, estrés y evidencias*, enlace desde *Datos y cuentas para la revisión* y `tools/ensayo/` en la estructura.

### Lo que el ensayo encontró (no se cambió, porque son decisiones del grupo)

- **Atención se actualiza en vivo por `/ws/live/`** (cualquier dato de la delegación) y Beneficiarios por `/ws/crud/beneficiarios/`. Los avisos de Beneficiarios no se separan por delegación, porque ese catálogo es común: `lector_b` también los recibiría. Es consistente con el catálogo compartido, pero hay que tenerlo presente al explicar el paso 7.
- **Beneficiarios no tiene un filtro de negocio ni aislamiento por delegación**, así que como segundo CRUD evaluado cumple menos que Atención. Ver «Para confirmar con el grupo».
- El botón que archiva en la lista de Atención se llama «Eliminar», pero archiva y la confirmación pregunta «¿Archivar registro?».
- El **commit en `/salud/`** solo aparece si el servidor se actualizó con `deploy/actualizar.sh` (lo escribe con `git describe`); un `git pull` a mano deja «sin definir».
- La recuperación de contraseña se limita a **5 enlaces por hora** por cuenta: repetir el ensayo varias veces seguidas se detiene por ese límite (comportamiento correcto; la guía lo explica).
- El ensayo deja unas pocas atenciones y beneficiarios archivados marcados «ENSAYO». No aparecen en los listados normales.

### Ajustes menores

- `VERSION` pasa a `v37` y se vuelven a generar `docs/pruebas/registro_pruebas_funcionales.csv` y `.xlsx` (estaban desactualizados desde antes de la v34).

### Base de datos

Sin cambios: no hay migraciones nuevas ni cambia `sql/sgr_django.sql`.

### Pruebas

Nuevo `core/test_ensayo_revision.py` (54 pruebas), registrado en el catálogo QA como V37-01 (diez pasos), V37-02 (herramienta) y V37-03 (guía y documentación).

### ❓ Para confirmar con el grupo

- Los **dos CRUD evaluados** (sigue sin respuesta): con el ensayo hecho, Beneficiarios no sirve para demostrar filtro de negocio ni aislamiento. Opciones: cambiarlo por **Agenda colectiva** en `CRUDS_EVALUADOS`, o agregarle un filtro de negocio y un ámbito.
- Si el botón de Atención debe decir «Archivar» en vez de «Eliminar».
- Cuándo se ensaya en AWS, y con qué casilla real se prueba el correo de recuperación (`lector_b` usa `lector_b@revision.sgr.example`, que no existe: en AWS hay que poner un correo real a esa cuenta antes de la prueba).

## Versión 36

Datos y cuentas para la revisión de la Evaluación Sumativa III: comando de carga reproducible, las seis cuentas de prueba, el README de la revisión y el diagrama de modelos. Siguen pendientes el ensayo de la revisión completa en AWS (los diez pasos) y los puntos abiertos de las versiones 30 a 33.

### Comando `cargar_datos_revision`

- **Más de 3.000 registros ficticios** (3.220 sobre una base recién migrada) repartidos entre los 25 modelos del proyecto: sin sesiones, permisos ni tablas internas de Django. Al terminar imprime el **total por modelo** (la misma tabla que está en el README) y verifica los mínimos.
- **Al menos 50 en cada CRUD evaluado**, y también por delegación cuando el CRUD se filtra por ella. Los CRUD evaluados son una constante (`CRUDS_EVALUADOS`): Atenciones (`actividades`) y Beneficiarios. Los demás módulos de negocio también quedan con 50 o más por delegación.
- **Dos ámbitos**: Delegación Norte = organización A y Delegación Sur = organización B, con funcionarios, territorios, atenciones, gestiones, compromisos, evidencias, felicitaciones y reclamos y ausencias de cada una. Beneficiarios y organizaciones comunitarias son un catálogo compartido.
- **Variado**: tres estados de atención, cinco ítems, cuatro servicios, fechas en 240 días hábiles, atenciones con y sin puntaje, evidencias pendientes, aprobadas y rechazadas, y una fracción archivada (6 % de las atenciones, 7 % de los compromisos). Más de dos páginas de 30 por delegación.
- **No duplica**: cada registro tiene una clave natural y solo se crea lo que falta (RUT, identificador de funcionario, N.º de registro, código de evidencia, funcionario + fecha + persona de la atención, etc.). Todo sale de `random.Random(2026)` y de una **fecha base fija** (30-10-2026), no de la fecha de hoy; los valores se sortean siempre, exista o no el registro, así que dos ejecuciones generan lo mismo. No pisa lo que alguien editó o archivó después. Comprobado: la segunda y la tercera ejecución dejan todas las tablas y los archivos idénticos, también sobre una base con los datos de demostración.
- **Reglas del negocio**: la delegación de la atención es la de su funcionario, nunca más de 7 atenciones por funcionario y día, solo días hábiles, puntaje calculado con la regla del modelo, evidencias con archivo PDF real y una validación por evidencia revisada. Los **indicadores** salen de `planning.calculation` y los **ajustes** de `planning.feedback.sync`: no hay cifras escritas a mano.
- **Orden de reciente a antiguo**: las fechas de creación se fijan con la fecha del negocio, para que los listados ordenados por creación sigan el orden de las atenciones.
- **Contraseñas**: nunca en el repositorio ni en el README. Se leen de `SGR_PASSWORD_<ALIAS>`, `--password`, `SGR_REVISION_PASSWORD` o se piden por terminal, pasan los validadores de Django y solo se asignan al crear la cuenta (`--reasignar-claves` las cambia en las existentes). Sin contraseña el comando se detiene antes de escribir nada.
- **Roles**: ejecuta `seed_roles` y `seed_management_types` por su cuenta. `deploy/actualizar.sh` **no** los ejecuta ni carga datos: un servidor recién migrado queda sin roles (documentado en el README y en `docs/aws/DESPLIEGUE_AL2023.md`).
- **`core/datos_prueba.py` no se usa ni se carga en el servidor.**
- Funciona con MariaDB por diseño (sin SQL propio; los identificadores se vuelven a leer tras `bulk_create`, porque MySQL no los devuelve), pero **solo se probó en SQLite**: la primera ejecución en la instancia es la prueba real.

### Seis cuentas de prueba

| Alias | Rol | Ámbito |
|---|---|---|
| `admin_a` | Administrador A (Jefatura y Funcionario, con permisos propios; **no** es Super Usuario) | Norte (organización A) |
| `editor_a` | Editor A (Funcionario, con beneficiarios; sin permisos de eliminar) | Norte (organización A) |
| `lector_a` | Lector A (Consulta, con beneficiarios y organizaciones en lectura) | Norte (organización A) |
| `lector_b` | Lector B (igual, en la Sur) | Sur (organización B) |
| `cliente1`, `cliente2` | Cliente: su portal y sus 24 atenciones propias, distintas entre sí | Norte y Sur |

- **Archivar y eliminar exigen `delete_<modelo>`** y ningún rol base lo trae, así que el administrador A lo recibe como permiso propio de la cuenta (en los módulos operativos), junto con ver, crear y editar usuarios. No cambia `seed_roles` ni los roles existentes.
- El comando **comprueba los permisos** al terminar y falla si una cuenta quedó con más o con menos: el administrador no es superusuario, el editor no puede eliminar ni archivar en ningún módulo, los lectores solo ven y exportan.
- Limitaciones que se dejan dichas: el listado de usuarios no se filtra por delegación (el administrador A ve todas las cuentas) y eliminar usuarios sigue siendo solo del Super Usuario.

### README y guía de AWS

Sección nueva del README, *Datos y cuentas para la revisión en AWS*: dirección de acceso, cómo arrancan HTTP y WebSocket (Daphne, `sgr_project.asgi:application`, servicio `sgr`, capa de canales en memoria y su límite de un solo proceso), cómo se ejecuta el comando, distribución de los datos, total por modelo, tabla de cuentas (alias, rol, ámbito, responsabilidad, permitido, restringido y prueba con resultado esperado, sin contraseñas) y recorrido por pasos de la revisión. `docs/aws/DESPLIEGUE_AL2023.md` incorpora el requisito de los comandos de carga.

### Diagrama de modelos

`docs/DIAGRAMA_MODELOS.md`: diagrama entidad-relación en Mermaid (`erDiagram`) **generado** por `tools/diagrama_modelos.py` a partir de `apps.get_models()` (25 modelos propios más `User` y `Group`, 47 relaciones). Las multiplicidades salen del tipo de campo y se **revisaron a mano**: la tabla «Revisión manual» recoge lo que el diagrama no puede decir (atención de una persona u organización, meta personal o del cargo, delegación igual a la del funcionario, hasta tres gestiones por atención, etc.). `python tools/diagrama_modelos.py --verificar` falla si el documento está desactualizado, y una prueba lo comprueba. El bloque se validó con el analizador de Mermaid.

### Base de datos

Sin cambios: no hay migraciones nuevas ni cambia `sql/sgr_django.sql`.

### Pruebas

Nuevo `core/test_carga_revision.py` (49 pruebas): volumen, mínimos por CRUD y por delegación, variedad, reglas del negocio, idempotencia (repetir, editar y repetir, reponer filas faltantes, sobre datos de demostración), contraseñas, las seis cuentas con sus permisos y el aislamiento por URL, exportación y portal, README y guía de AWS, y el diagrama. Están en el catálogo QA como V36-01, V36-02 y V36-03.

### ❓ Para confirmar con el grupo

- Cuáles son los **dos CRUD evaluados**: esta versión usa Atenciones y Beneficiarios. Beneficiarios es un catálogo compartido entre delegaciones; si se prefiere demostrar el aislamiento en ambos CRUD, conviene cambiar el segundo por un módulo con delegación (por ejemplo Agenda colectiva) en `CRUDS_EVALUADOS`.
- Que el **reparto de roles** sea el esperado (administrador A = Jefatura Norte con eliminar y archivar y gestión de usuarios; editor A = Funcionario Norte sin eliminar; lector A y B = Consulta).
- La **dirección de AWS** del README (`http://32.198.200.215/`) y la cuenta técnica de superusuario, que no forma parte de las seis.

## Versión 35

Estado de los listados en la sesión y perfil editable, de la Evaluación Sumativa III. Siguen pendientes las demás exigencias de esa evaluación (2.000 registros de prueba, las seis cuentas y la tabla del README, y el diagrama de modelos) y los puntos abiertos de las versiones 30 a 33.

### Estado del listado en la sesión, por módulo

- **Una sola vez, en el motor (`core/crud.py`)**: lo heredan los 26 mantenedores y la pantalla Atención. Cada módulo guarda en `request.session["list_state:<slug>"]` su página, tamaño de página, búsqueda, filtros y orden.
- **Regla fácil de explicar**: si la URL llega **con** parámetros de listado, se usan y se guardan; si llega **sin** ninguno (el menú, «Volver», cancelar, guardar, volver desde otro módulo), se restaura lo último guardado **redirigiendo a la misma URL con esos parámetros**. «Limpiar» (`?limpiar=1`) lo borra y vuelve al listado sin parámetros (conserva el tamaño de página elegido).
- Por qué se restaura con una redirección y no en silencio: la barra de direcciones siempre dice lo que se ve, así que el **Excel** exporta lo que se está viendo, el **WebSocket** vuelve a pedir esa misma URL y los enlaces de página y de orden parten de los mismos parámetros. Los enlaces «Volver al listado», las migas de pan, cancelar y guardar ya apuntaban a la URL sin parámetros, así que restauran solos.
- **Cambiar la búsqueda, un filtro o el orden vuelve a la página 1** (esos enlaces y el formulario nunca llevan `page`). Una **página que ya no existe se ajusta** a la última (y se guarda la ajustada); `page=abc`, `0` o negativo es la página 1.
- **Parámetros inválidos se ignoran**: tamaño distinto de 5, 15 o 30, orden fuera de las columnas permitidas, dirección que no es asc/desc, filtro que no es una opción, `archivados` no permitido. Un valor alterado en la sesión se revalida y nunca rompe el listado; los filtros guardados se vuelven a validar contra lo que la persona puede usar (delegación, archivados).
- **WebSocket**: la consulta de fondo de `live-updates.js` manda la cabecera `X-Live-Refresh`; el servidor no restaura ni guarda el estado con ella, así que una pestaña olvidada no pisa lo último que se hizo en otra. La exportación a Excel tampoco guarda.
- **Tamaño de página por módulo**: los botones de filas por página (5, 15, 30) ahora indican el módulo; el tamaño vale para ese módulo y lo manda a su página 1. `/filas/` sin módulo sigue valiendo para todos los listados, como antes.
- **Orden por defecto**: lo más recién **creado** primero (`created_at` descendente) con el id descendente de desempate; editar un registro no lo mueve (antes cada módulo usaba su fecha de negocio o su nombre). Roles y Usuarios: Roles no tiene fecha de creación y se ordena por nombre; Usuarios por `date_joined` descendente.
- Cambia el comportamiento de dos pruebas existentes (`PageSizeTests` y la auditoría de descargas): una visita sin parámetros después de una con parámetros ahora restaura, así que usan «Limpiar» antes.

### Mi perfil: nombre y correo editables

- **Todos los perfiles** editan su nombre, apellido y correo en *Mi perfil* (formulario `ProfileDataForm`, acción `perfil`). Es un `ModelForm` con **lista blanca de tres campos** (nunca `__all__`) y la instancia siempre es la cuenta de quien tiene la sesión (se vuelve a leer de la base): enviar `groups`, `is_superuser`, `is_staff`, `is_active`, `username`, `officer`, `beneficiary`, delegaciones, `id` o `user` ajenos no cambia nada, ni a la persona ni a otra.
- **Validación**: nombre y apellido con la regla `person_name`; correo con la regla `email`; el correo no puede ser el de otra cuenta (sin distinguir mayúsculas); no se puede vaciar el nombre ni el correo si ya existen (sin correo no hay recuperación de contraseña); largos máximos de la base. El navegador valida con los mismos atributos.
- **Auditoría**: «Datos de perfil actualizados» con lo anterior y lo nuevo, solo de los campos que cambiaron; si no se cambió nada, se avisa y no se registra.
- **Cliente**: se edita el **nombre de la cuenta** (`User`), no el de la ficha del beneficiario, que es el dato oficial y se muestra como «Nombre en tu ficha», solo lectura. Así no se rompe el vínculo cuenta–ficha ni lo que ve en su portal. El correo, que antes se editaba en «Mis datos», pasa al formulario común; «Mis datos» queda con teléfono y dirección de su ficha.
- ❓ Para confirmar con el grupo: que «nombre del Cliente» sea el de la cuenta (esta versión) y no el de la ficha.

### Base de datos

Sin cambios: no hay migraciones nuevas ni cambia `sql/sgr_django.sql`. El estado de los listados vive en la sesión (`django_session`).

### Pruebas

Nuevos `core/test_listados_sesion.py` (71 pruebas: reglas, validación de parámetros, página 1, navegación detalle/edición/otro módulo, el mismo recorrido en **todos** los módulos, Excel, consulta de fondo del WebSocket, tamaño por módulo y orden por defecto) y `core/test_perfil_editable.py` (38 pruebas: validación, auditoría, campos manipulados, Cliente). Están en el catálogo QA como V35-01 y V35-02 (`core/qa/esperado_listado_y_perfil.py`). La comprobación en dos navegadores (WebSocket entre dos sesiones con el estado restaurado) no se puede hacer desde el entorno de desarrollo: queda para la revisión en AWS.

## Versión 34

Recuperación de contraseña por enlace con token y página 400, de la Evaluación Sumativa III. Siguen pendientes las demás exigencias de esa evaluación (estado de los listados en sesión, perfil editable, 2.000 registros de prueba, las seis cuentas y la tabla del README, y el diagrama de modelos) y los puntos abiertos de las versiones 30 a 33.

### Recuperación de contraseña por enlace

- **Reemplaza al código de 6 dígitos.** Se escribe el correo y llega un correo (texto y HTML, con botón) con un **enlace firmado por Django** (`default_token_generator`). Al abrirlo se elige la contraseña nueva. Ya no hay código, casillas, cuenta regresiva ni reenvío.
- **Un solo uso**: el token depende de la contraseña, el último ingreso y el correo de la cuenta; al guardar la contraseña nueva, ese enlace y los demás pendientes de la cuenta dejan de servir. **Vence a la hora** (`PASSWORD_RESET_TIMEOUT = 3600`).
- **Respuesta genérica**: la solicitud siempre termina en «Revisa tu correo», exista o no el correo, esté activa o no la cuenta, haya pedido demasiados enlaces o haya fallado el envío (el error queda solo en el registro del servidor). No se guarda ni se repite el correo.
- **Tope**: 5 enlaces por cuenta por hora, contados en la auditoría (base de datos). Un envío que falla no gasta el cupo.
- **Contraseña nueva** con los validadores de Django y la política del SGR, con la misma confirmación de SweetAlert2. Las demás sesiones abiertas de la cuenta se cierran. Después se vuelve al ingreso con un aviso.
- **Enlace inválido** (inventado, vencido, ya usado, de otra cuenta, cuenta desactivada o correo cambiado): pantalla «Este enlace ya no sirve» con código **400**, sin detalles técnicos, y botón para pedir otro. Al abrir un enlace vigente, el token sale de la barra de direcciones (Django lo guarda en la sesión).
- Las rutas de contraseña olvidada que trae Django (`/accounts/password_reset/done/`, `/accounts/reset/…`) llevan a las pantallas del portal. Se retiraron `/recuperar/codigo/`, `/recuperar/reenviar/` y `/recuperar/nueva/`.
- **Correo real**: el SMTP se sigue leyendo del `.env`. El README documenta cómo configurar Gmail (contraseña de aplicación), Mailtrap o Amazon SES y cómo probarlo en AWS con `manage.py sendtestemail`; la guía AL2023 suma ese paso.
- Se retiraron `RECOVERY_CODE_SECONDS`, `RECOVERY_MAX_ATTEMPTS`, `RECOVERY_RESEND_SECONDS` y `RECOVERY_PASSWORD_SECONDS`, la regla `recovery_code`, `code-boxes.js`, `countdown.js` y sus estilos. Con ello desaparece el defecto DEF-004 (los intentos del código dependían de una caché compartida) y el pendiente PEN-05. `CACHE_BACKEND` sigue existiendo (lo usa el chequeo de `/salud/`).
- Código: `accounts/recovery.py`, `RecoveryRequestForm`, `RecoveryConfirmView`, plantillas `recover_request.html`, `recover_done.html`, `recover_confirm.html` y `recovery_*`.

### Páginas de error

- **Página 400 nueva** (`templates/400.html`) con el mismo diseño que 403 y 404: explica que no se pudo procesar la solicitud y ofrece volver al inicio. `handler400` (`core/errors.py`) nunca muestra el texto de la excepción y, si la plantilla no se puede dibujar, entrega una página mínima igual con código 400.
- **Página 500 rediseñada** con el estilo del sitio (sigue siendo independiente de sesión, menú y base de datos): mensaje de problema temporal que no culpa a la persona, con salida al inicio.
- Revisión de 403, 404 y 500: no muestran trazas, SQL, rutas ni configuración; la 403 solo imprime los mensajes que escribió el portal.
- **Pruebas controladas con `DEBUG=False`** (`core/test_errores.py`): 400 por host no permitido, cuerpo sobre el límite, subida mal formada y demasiados campos; 500 por falla en una vista y por caída de la base de datos (con `raise_request_exception=False`, para ver la respuesta como la vería el navegador); 403 por permiso, por Cliente fuera de su portal y por token CSRF vencido; 404. Se comprueba código HTTP, mensaje, que no se filtre nada técnico y que no cambien datos. Para verlas: `python manage.py test core.test_errores -v 2`.

### Base de datos

Sin cambios: no hay migraciones nuevas ni cambia `sql/sgr_django.sql`. Al desplegar solo hace falta configurar el correo en `/etc/sgr/sgr.env` y reiniciar el servicio (`sudo systemctl restart sgr`).

### Pruebas

`accounts/test_recovery.py` se reescribió para el flujo con enlace (49 pruebas, con las clases `RecoveryRequestTests`, `RecoveryLinkTests`, `RecoveryPasswordTests`, `RecoveryRoutesTests`, `RecoveryHelperTests` y `RecoveryBlankEmailTests`) y `core/test_errores.py` es nuevo (28 pruebas). Están en el catálogo QA como V34-01 y V34-02. El script `tools/evidencias/capturar.py` sigue el flujo nuevo (lee el enlace del log del servidor). El correo con SMTP real y las capturas en AWS no se pueden probar desde el entorno de desarrollo: quedan en «Pendientes» (PEN-04).

## Versión 33

Foto de perfil con recorte (Croppr) y portal del Cliente, de la Evaluación Sumativa III. Siguen pendientes las demás exigencias de esa evaluación (página 400, 2.000 registros de prueba y tabla de cuentas en el README, recuperación de contraseña por enlace, estado de los listados) y los puntos abiertos de las versiones 30 a 32.

### Foto de perfil con recorte

- En **Mi perfil**, al elegir una imagen se abre un panel con **Croppr**: cuadro de recorte cuadrado, **vista previa** de cómo quedará y los botones **Guardar foto** y **Cancelar**.
- El recorte es real, no con CSS: el navegador corta los píxeles elegidos en un canvas (hasta 512 px por lado), deja ese archivo en el campo y envía el formulario. **Cancelar** descarta todo y la foto anterior queda igual.
- El servidor valida lo que llega (PNG o JPG, 2 MB, que sea una imagen real), lo deja cuadrado y de a lo más 512 px, y lo asocia a **quien tiene la sesión**: el formulario no recibe ningún identificador de usuario, así que nadie reemplaza la foto de otra persona. Al recargar, la foto sigue ahí.
- Sin JavaScript o sin la librería, el formulario funciona como una subida normal y el servidor centra y recorta a cuadrado.
- **Croppr no viene incluido**: hay que copiar `croppr.min.js` y `croppr.min.css` a `core/static/core/vendor/croppr/` (comandos en la entrega). Mientras no estén, las pantallas no los enlazan y la subida funciona sin recorte.
- Código: `core/static/core/js/photo-crop.js`, `uploads.square_photo`, `ProfilePhotoForm.clean_photo`, etiqueta `vendor_url`.

### Portal del Cliente

- Perfil nuevo **Cliente**: un beneficiario con cuenta. La cuenta se vincula a su beneficiario (`UserProfile.beneficiary`, uno a uno; un beneficiario tiene a lo más una cuenta). Se crea en Control de usuarios: el perfil Cliente va solo, con su beneficiario, y sin funcionario, delegaciones, Super Usuario ni acceso al panel.
- Al ingresar, el Cliente llega a **Mi portal**: sus datos, un resumen de sus atenciones por estado y las últimas. **Mis atenciones** es el listado (con búsqueda y filtro por estado) y cada atención tiene su **detalle** con sus gestiones.
- **Solo ve lo suyo, filtrado en el servidor** con el usuario autenticado, aunque otro cliente sea de la misma delegación. El detalle de una atención ajena responde 404, igual que una que no existe. No se muestran datos internos (puntaje, evidencias, compromiso del tubo).
- **No sale de su portal**: un middleware deja pasar solo el portal, el perfil, su foto y la salida. Listados, fichas, edición, exportaciones a Excel, tablero y `/admin/` responden 403 sin mostrar contenido y quedan en la auditoría («Acceso de cliente rechazado»). El dashboard lo lleva a su portal. Los avisos en vivo (WebSocket) se cierran para el Cliente. Su menú tiene solo Mi portal, Mis atenciones y Mi perfil, y no ve la franja de delegación.
- En **Mi perfil** edita su correo, teléfono y dirección, su foto y su contraseña. No puede cambiar su nombre, RUT, perfil, permisos ni el dueño de la cuenta, y solo puede abrir su propia foto.
- Cuentas de prueba: `cliente1` (María Pérez) y `cliente2` (Carla Muñoz), clave `Hola123!`, las dos de la Delegación Norte y con atenciones distintas (María Pérez y Carla Muñoz ya existían como beneficiarias de ejemplo).
- Código: `core/clients.py`, `core/portal_cliente.py`, `core/templates/core/portal/`, `client_menu` (`core/menus.py`), `ClientDataForm` y `UserForm.check_client`.

### Base de datos

Migración nueva `accounts/0007_cliente_beneficiario_v33.py` (columna `beneficiary_id` del perfil de usuario, única, con su llave foránea). `sql/sgr_django.sql` quedó al día. El perfil Cliente lo crea `seed_roles` (sin permisos de módulos).

### Pruebas

`core/test_cliente_y_recorte.py` (91 pruebas), registradas en el catálogo QA como V33-01, V33-02 y V33-03. El comportamiento de Croppr en el navegador no se puede probar sin la librería: las pruebas revisan el script y las pantallas, y la prueba real es abrir Mi perfil y recortar una imagen.

## Versión 32

Cuarto avance sobre los requisitos nuevos de la clienta: el tubo de trabajo. Sigue pendiente la lista de ítems que no otorgan punto (no hay una lista en lo recibido).

### Tubo de trabajo: la atención crea su compromiso

- Antes, marcar «Ingresa al tubo de trabajo» solo dejaba una marca en la atención. Ahora, al marcarla, el formulario muestra y pide **«Fecha comprometida»** y **«Territorio del compromiso»**, y al guardar se crea el compromiso en la Agenda colectiva.
- El compromiso toma de la atención el solicitante, la descripción, la fecha (como fecha de solicitud), la delegación y el funcionario responsable; el origen dice «Atención ATN00012». Nace en estado «Ingresado», con su historial y su registro de auditoría. Después se sigue en la Agenda como cualquier compromiso (Ingresado, Pendiente, En proceso, Realizado).
- Reglas: la fecha comprometida no puede ser anterior a la fecha de la atención (el mismo día sirve) y el territorio debe ser de la delegación de la atención. Si la atención se rechaza, no se crea nada.
- Los dos campos solo existen con la casilla marcada: `widgets.js` los muestra o los oculta, y el servidor ignora lo que traigan si la casilla no está marcada.
- Al **editar** una atención pasa lo mismo si se marca la casilla y no tiene compromiso. Una atención que ya tiene su compromiso no vuelve a pedir los datos ni crea otro. Desmarcar la casilla después **no borra** el compromiso de la Agenda.
- Atenciones que quedaron marcadas antes de la v32 sin compromiso: se pueden seguir editando sin pedirles los datos; si se completan los dos, se crea el compromiso (si se da solo uno, se pide el otro). No se crean compromisos de golpe para esas atenciones, porque faltaría la fecha y el territorio.
- Código: `operations/pipeline.py`, formulario base `PipelineForm` (`core/forms.py`) y `ActivityCrud.after_save` (`core/registry.py`).

### Puntos abiertos

- No se modelaron el código de verificación con foto de las hojas TUBO ni el tubo de cartas (`TUBO CARTAS`, con otras columnas).
- «Interno o externo» del compromiso queda en «Externo» (el valor por defecto): se cambia en la Agenda.

### Base de datos

Migración nueva `operations/0005_tubo_de_trabajo_v32.py` (columna `commitment_id` de la atención, única). `sql/sgr_django.sql` quedó al día.

### Pruebas

`core/test_tubo_de_trabajo.py` (30 pruebas), registradas en el catálogo QA como V32-01 y V32-02.

## Versión 31

Tercer avance sobre los requisitos nuevos de la clienta: felicitaciones y reclamos, puntaje de equipo e importación de juntas de vecinos. Siguen pendientes el tubo de trabajo y la lista de ítems que no otorgan punto.

### Felicitaciones y reclamos (RF-046)

- Mantenedor «Felicitaciones y reclamos» (Operación). Cada registro lleva: tipo, fecha, quién reclama o felicita (nombre y contacto), medio (correo al delegado, WhatsApp al delegado o libro de observaciones), profesional involucrado, descripción y **respaldo obligatorio** (captura o foto, con las mismas validaciones de archivo que las evidencias).
- Lo registran Jefatura (de su delegación) y los usuarios globales (eligiendo una delegación); Coordinación solo lo ve. El registro debe caer en un período abierto y el funcionario debe estar activo.
- Valores según la matriz, **configurables en cada período**: felicitación **+10 %** con un máximo de **3 por persona** (las siguientes quedan registradas «sin efecto») y reclamo **−30 %** (el valor de las hojas de cada cargo; el −20 % que aparece en las consideraciones de la hoja RECLAMOS es solo texto).
- El efecto es **solo de la persona aludida**. El sistema genera solo el ajuste (bonificación o penalización) y lo mantiene al día si el registro se cambia, se archiva o se elimina. La ficha, el dashboard y el tablero muestran «Ajustes» y «total con ajustes»; el cumplimiento ponderado no cambia.
- Reclamos en **más de dos períodos seguidos** (3 o más): el listado muestra el aviso «informar a Recursos Humanos».
- Código: `planning/feedback.py`, modelo `Feedback`, señales en `planning/signals.py`.

### Puntaje de equipo (RF-048)

- Se muestra en el tablero de la delegación, en el dashboard y en la vista por cargo, junto al promedio individual y la diferencia entre ambos.
- **Decisión de desarrollo** (el cliente dejó el método abierto): por cada ítem se suman las metas ajustadas por ausencias y el avance válido de todos los integrantes; el cumplimiento del equipo es avance ÷ meta × 100 con el mismo tope del período (120 %); el aporte ponderado es el ponderador promedio × cumplimiento ÷ 100; el puntaje es la suma de los aportes en base 100. Lo que una persona logra de más compensa lo que a otra le falta, sin pasar del tope. Cada persona aporta su parte del avance y los aportes suman el puntaje.
- Los ajustes de felicitaciones y reclamos no entran al equipo. Código: `planning/team.py`.

### Importación de juntas de vecinos (RF-049)

- Modelo `CommunityOrganization` (mantenedor «Organizaciones», solo Super Usuario como beneficiarios) y campo opcional `organización` en la atención.
- Comando: `python manage.py importar_jjvv <archivo.xlsx> [--simular] [--delegacion "Nombre"]`.
- Es idempotente por N.º de registro. `--simular` entrega el informe sin escribir. Las organizaciones nuevas quedan **sin verificar** y una importación posterior no cambia la marca de las existentes.
- **Crea los territorios que falten**, en la delegación cuyo nombre contiene el del territorio; si ninguna calza (o calzan varias) usa `--delegacion`; sin ninguna, deja la organización sin territorio enlazado (guarda el texto) y el informe lo avisa.

### Puntos abiertos

- Lo de la v30 sigue pendiente de confirmar: semana de lunes a domingo, si las gestiones de la atención social y el tubo de trabajo siguen el cierre, y que los feriados no se descuentan de las ausencias.
- Puntaje de equipo: confirmar con la clienta que el método elegido es el que esperan.

### Base de datos

Migraciones nuevas: `planning/0005_felicitaciones_y_reclamos_v31.py` (tabla `planning_feedback` y tres campos del período), `organization/0005_organizaciones_jjvv_v31.py` (tabla `organization_communityorganization`) y `operations/0004_organizaciones_jjvv_v31.py` (campo `organization` de la atención). `sql/sgr_django.sql` quedó al día.

### Pruebas

`core/test_felicitaciones_equipo_y_jjvv.py` (85 pruebas), registradas en el catálogo QA como V31-01 a V31-04.

## Versión 30

Segundo avance sobre los requisitos nuevos de la clienta: cierre semanal de ingresos y ausencias con meta ajustada. Siguen pendientes (necesitan definiciones) felicitaciones y reclamos, puntaje de equipo, importación de juntas de vecinos y la lista de ítems que no otorgan punto.

### Cierre semanal (regla 4)

- La semana va de lunes a domingo: una fecha pertenece a la semana que la contiene.
- Las atenciones de una semana se ingresan hasta el **lunes siguiente**; desde el martes ya no se ingresan las de la semana pasada (hora de Santiago). Código en `core/entry_rules.py`.
- Se revisa al crear una atención y al cambiarle la fecha; editar otros datos de una atención antigua no se bloquea. La validación está en `Activity.clean()` (`check_week_open`), igual que el límite diario.
- Sin excepciones: el cierre y el límite diario valen para todos los roles, incluido el Super Usuario.
- El formulario de ingreso muestra «Hoy llevas X de 7 atenciones.» y «La semana del … al … se puede ingresar hasta el lunes …».
- Punto abierto: lo recibido de la clienta no dice nada de sábado y domingo; se tomó la semana de lunes a domingo. Tampoco se definió si las tres gestiones de la atención social y el tubo de trabajo siguen el mismo cierre (hoy el cierre vale para toda atención).

### Ausencias y meta ajustada (regla 9)

- Modelo nuevo `Absence` (`planning/models.py`): funcionario, tipo (licencia, vacaciones, día administrativo, emergencia, compensatorio), desde, hasta, observación y quién la registró. Las ausencias de una misma persona no se traslapan y «hasta» no puede ser anterior a «desde».
- Mantenedor «Ausencias» (Administración › Planificación). Lo registran Jefatura (solo de su delegación) y Coordinación (eligiendo una delegación); el funcionario, el verificador y consulta no pueden. Los permisos están en `seed_roles` y en la matriz de roles.
- Regla elegida: los días hábiles (lunes a viernes) de las ausencias dentro del período se descuentan de los días computables y la meta baja en esa proporción: **meta ajustada = meta × días efectivos ÷ días computables**. Todos los tipos descuentan igual. Código en `planning/absences.py`.
- El cumplimiento (`calculation.compute`) usa la meta ajustada. Al registrar, cambiar o archivar una ausencia se recalculan solos los indicadores del funcionario en los períodos que toca (`planning/signals.py`).
- El ritmo esperado (`pace_of(period, today, absence)`) y la actividad reciente (promedio diario y días sin ingreso) no cuentan los días de ausencia.
- El tablero de la delegación tiene el bloque «Ausencias del equipo» (días por tipo, días de ausencia y días efectivos, con el botón «Registrar ausencia»). La ficha personal, el dashboard y el tablero muestran la meta original junto a la ajustada.
- Los feriados no se descuentan de las ausencias: solo cuentan los días de lunes a viernes.

### Base de datos

Migración nueva `planning/0004_ausencias_v30.py` (tabla `planning_absence`). `sql/sgr_django.sql` quedó al día.

### Pruebas

`core/test_cierre_y_ausencias.py` (48 pruebas), registradas en el catálogo QA como V30-01 a V30-04. `core/testing.py` toma `portal_today` desde `core/entry_rules.py`.

## Versión 29

Primer avance sobre los requisitos nuevos de la clienta (plan por etapas: etapa 1, etapa 2 y límite diario). Lo que depende de definiciones que faltan (cierre semanal, ausencias, felicitaciones y reclamos, puntaje por equipo, qué ítems no otorgan punto) queda para una versión posterior.

### Atenciones que no puntúan

Una atención se guarda siempre, pero solo suma al avance si cumple las tres reglas. Al guardarla el sistema anota si puntúa (`counts_for_score`) y, si no, el motivo (`no_score_reason`):

| Motivo | Regla |
|---|---|
| «El solicitante es el delegado (otra gestión)» | Casilla nueva «El solicitante es el delegado» en el formulario de ingreso |
| «Falta el nombre o el teléfono del usuario» | Sin nombre de contacto o sin teléfono (se aceptan los de la persona vinculada) |
| «El ítem no otorga punto (gestión previa)» | Casilla nueva «Otorga punto» en ítems, tipos de atención y sub atenciones |

- Todos los ítems parten otorgando punto; nadie decidió una lista distinta. Una sub atención sigue lo que decida su tipo.
- Si cambia la casilla de un ítem, sus atenciones se reclasifican y el avance se recalcula (`planning/signals.py`).
- Las atenciones anteriores a la v29 no se tocan (sin recálculo hacia atrás): se reclasifican cuando se editan.
- La lista de Atención tiene la columna «Puntaje» y el filtro «Puntúa»; el detalle dice el motivo.
- `calculation.valid_activities` solo cuenta atenciones con `counts_for_score=True`.

### Tope de 120 % y panel «Ítems con menor puntaje»

- El tope del cumplimiento por ítem pasa de 150 % a 120 % (`Period.weighted_cap`). La migración `planning/0003` lo baja solo en los períodos que no están cerrados; los cerrados conservan su 150 %. Los períodos nuevos parten con 120 %.
- La ficha del funcionario y el dashboard muestran «Tope alcanzado» en el ítem que llegó al tope y el panel «Ítems con menor puntaje» (hasta tres, del peor al mejor, sin los que ya están al tope). Código en `core/results.py` (`lowest_lines`) y `core/templates/core/partials/lowest_items.html`.

### Límite diario

Un funcionario no puede registrar más de 7 atenciones con la misma fecha (`settings.DAILY_ENTRY_LIMIT`). Se cuenta por la fecha de la atención, sin las archivadas, y la validación está en `Activity.clean()`, así vale para el ingreso y para la edición. El mensaje dice: «Ya hay 7 atenciones registradas con esta fecha: el máximo es 7 por día. Hay que ingresar todos los días y no dejar un día para llenar la matriz.». Editar una atención de un día completo no se bloquea. Lo que se crea desde código (semillas, pruebas) no pasa por este control.

### Números de pocas opciones se eligen de una lista

Todo campo numérico con un rango de 10 valores o menos (por ejemplo el número de gestión, de 1 a 3) se dibuja como lista desplegable en lugar de caja de texto: se aprieta y se elige, sin escribir. Si llega un valor fuera del rango, el mensaje dice «Debe ser un número entre 1 y 3». Los campos con rangos amplios siguen siendo numéricos. Código en `CrudForm.pick_small_ranges()` (`core/forms.py`).

### Base de datos

Migraciones nuevas: `organization/0004` (`item.scores`), `operations/0003` (`activity.requester_is_delegate`, `activity.counts_for_score`, `activity.no_score_reason`) y `planning/0003` (nuevo valor por defecto y baja del tope). `sql/sgr_django.sql` quedó al día.

### Pruebas

`core/test_reglas_puntaje.py` (reglas de puntaje, pantallas, tope, límite diario, listas de pocas opciones), registradas en el catálogo QA como V29-01 a V29-04. Las pruebas que crean atenciones a mano ahora les ponen teléfono, porque sin él no puntúan.

## Versión 28

### Pantallas en vivo aunque el WebSocket no conecte

En las capturas de la v27 un navegador decía «Reconectando…» y el otro «Sin actualización en vivo»: el WebSocket no llegaba a Daphne (Apache sin `ProxyPass /ws/` o servicio todavía en gunicorn). El código funciona (probado con dos navegadores reales), pero `actualizar.sh` no dejaba el servidor listo. Ahora:

- `deploy/actualizar.sh` corre `deploy/al2023/agregar_websocket.sh` (Apache pasa `/ws/`, el servicio es Daphne) antes de reiniciar, y al terminar corre `deploy/probar_websocket.py`, que prueba el WebSocket directo y a través de Apache y dice qué revisar si falla.
- `live-updates.js` tiene respaldo: sin WebSocket revisa la pantalla cada 8 s; con WebSocket, cada 60 s por si se perdió un aviso. Solo con la pestaña visible, y solo reemplaza la pantalla si el contenido cambió.

### Códigos y números automáticos

| Dato | Antes | Ahora |
|---|---|---|
| Código de evidencia | Se escribía (venía sugerido) | Lo asigna el sistema al guardar: `EVD-<DELEGACIÓN>-0001`… (cuenta también las archivadas; reintenta si dos personas guardan a la vez). No aparece al crear y no cambia al editar |
| Número de gestión | Se escribía (1 a 3) | Lo asigna el sistema (primer número libre); con las tres hechas se rechaza la cuarta |
| Código de funcionario | Automático desde la v20 | Sin cambios |

### Selector con buscador

Los selectores de un solo registro (actividad, funcionario, territorio…) y los filtros de los listados con 8 opciones o más muestran una caja para escribir y filtrar (`core/static/core/js/searchable-select.js`). Ignora tildes, mayúsculas y orden de palabras, dibuja como máximo 60 filas y se maneja con teclado. Las actividades ahora muestran también su ítem para poder buscar por él, y se traen en una sola consulta.

### Gráficos

Anillos, barras y columnas con SVG y CSS (sin librerías), siempre con los números escritos: dashboard (semáforo de metas, evidencias y compromisos propios, cumplimiento por meta, atenciones de los últimos 14 días), tablero de delegación, resumen colectivo e informes. Código en `core/charts.py`.

### Pruebas

`core/test_codes_search_and_charts.py` (códigos automáticos, buscador, gráficos, respaldo del tiempo real, prueba del WebSocket). Las pruebas que dependían de la fecha de hoy ahora usan la fecha de Santiago (`core.testing.portal_today`), así no fallan entre las 21:00 y la medianoche.

## Versión 27

### Tiempo real en todas las pantallas compartidas

En la v24 solo se actualizaban solos los listados de los mantenedores, el dashboard, el tablero, Validar, el resumen colectivo y la vista por cargos. Desde la v27 también:

| Pantalla | Qué se actualiza solo | Plantilla |
|---|---|---|
| Atención | Los resultados (el buscador no se toca, para no borrar lo que la persona escribe) | `core/templates/core/atencion.html` (`data-live-results`) |
| Ficha de cualquier registro (funcionario, actividad, evidencia, territorio…), con su historial de estados y su ficha del período | Toda la ficha | `core/templates/core/crud/detail.html` (`data-live-page`, `data-live-slug`) |
| Informes | El informe del período | `core/templates/core/reports.html` |
| Administración | El período vigente y los accesos | `core/templates/core/administration.html` |
| Listados de los mantenedores | Ahora escuchan su mantenedor **y** los cambios hechos desde otras pantallas (por ejemplo, una atención registrada desde Atención o una evidencia validada) | `core/crud/list.html` + `live-updates.js` |

**Regla:** toda pantalla de consulta (listados, fichas, dashboards, tableros, informes, administración, Atención) se actualiza sola cuando otra persona cambia datos; los formularios de registro y edición no, porque se perdería lo que la persona está escribiendo. Siguen sin actualizarse solos: alta y edición de cualquier registro (usuario, funcionario…), Mi perfil, validar una evidencia, las confirmaciones de archivar y eliminar y la recuperación de contraseña. Para dos personas editando lo mismo sigue valiendo el aviso de edición simultánea de la v26.

La vista «Usuarios eliminados» (y cualquier listado de archivados «solo») también se actualiza en vivo; en la v24 se había dejado fuera.

#### Qué avisa ahora

- Además de atenciones, gestiones, compromisos, evidencias, validaciones, metas, indicadores, ajustes, períodos y funcionarios, avisan a todas las delegaciones los catálogos: tipos de atención, delegaciones, cargos, ítems de cargo, ítems, servicios, territorios, beneficiarios, usuarios y roles (`websocket/signals.py`, `LIVE_MODELS`).
- Una entrada nueva de auditoría avisa solo a quien tiene abierto el listado de Auditoría (no a los dashboards).

#### JavaScript

`core/static/core/js/live-updates.js` ahora acepta varias fuentes de avisos por pantalla: `/ws/live/` (cualquier dato de la delegación) y `/ws/crud/<slug>/` (el mantenedor). Un solo temporizador junta los avisos seguidos en una sola actualización.

### Estilos y scripts viejos en el navegador

El panel «Ritmo del período» podía verse sin estilos si el navegador conservaba un `sgr.css` de una entrega anterior. Ahora los CSS y JS propios llevan `?v=<VERSION>-<COMMIT>` en su dirección (`templates/base.html`, `core/context_processors.py#assets`), así cada entrega o despliegue obliga a descargarlos de nuevo. Además, el panel tiene un poco de espacio sobre sus cifras.

### Corrección

La auditoría fallaba al guardarse fuera de la web (por ejemplo al cargar los datos de prueba) por un aviso en tiempo real que buscaba los mantenedores antes de registrarlos; ahora los registra y nunca impide guardar.

### Base de datos y despliegue

Sin cambios en la base de datos ni en el servidor: no hay migraciones nuevas. Se despliega con `sudo bash deploy/actualizar.sh proyecto-sgr-v27`.

### Limpieza del código

- Las pruebas se agruparon por tema, sin versiones en el nombre (ver la tabla de nombres al inicio de este archivo); no se perdió ninguna.
- `sql/` quedó con un solo archivo, `sgr_django.sql`: la estructura vigente de la base `sgr_django` (la de la v19 más la columna `officer_id` de la v26). Se retiraron los scripts de versiones anteriores y los ALTER.
- Los archivos `docs/CAMBIOS_vNN.md` se juntaron en este `docs/CAMBIOS.md`.

### Pruebas

`LiveEverywhereTests`, `LiveCatalogChangesTests`, `EveryScreenIsLiveExceptFormsTests` (en `core/test_realtime.py`) y `AssetVersionTests` (en `core/test_deploy.py`). Se ajustó `test_the_deleted_users_view_is_live_too` y `test_data_the_summary_screens_do_not_show_stays_quiet`, que ahora usa la auditoría como dato que los dashboards no muestran (los territorios sí avisan).

## Versión 26

La v26 implementa del **Informe de la Etapa 2** los requisitos que se podían hacer sin información del cliente: el **cálculo automático** de indicadores (**RF-022, RF-023, RF-024, RF-014**), **RF-006** (ponderadores), **RF-008** (ficha del funcionario), **RF-030** (actividad reciente), **RF-019** (plazos), **RF-028 y RF-031** (inicio personal y vista por cargos) y **RF-034 / RNF-003** (ediciones simultáneas).

**Base de datos:** se agrega **una columna**: `planning_indicator.officer_id` (acepta nulo). Trae la migración `planning/migrations/0002_indicator_officer.py` (y, desde la v25, `operations/migrations/0002_commitment_status_pending.py`). Con `sudo bash deploy/actualizar.sh <rama>` se aplican solas. Quien actualice la base a mano tiene `sql/sgr_v25_a_v26_alter.sql`. **El diagrama relacional (DER) y el informe de la base deben agregar `officer_id` a `indicator`.**

Parámetro nuevo (opcional): `SGR_DIAS_POR_VENCER` en la configuración, por defecto **7**.

### 1. Cálculo automático de indicadores (RF-022, RF-023, RF-024, RF-014)

Antes los indicadores se cargaban a mano. Ahora el sistema los calcula con la regla de la guía (RN-003 a RN-005 y RN-009):

- **Avance** = actividades **válidas** del funcionario en el ítem de la meta (o en una de sus sub atenciones) con fecha dentro del período. Una actividad es válida (RF-014) **solo si tiene una evidencia aprobada**; pendiente, rechazada o eliminada no suma, y una actividad con dos evidencias aprobadas cuenta una vez. Las actividades archivadas no cuentan.
- **Cumplimiento** = avance ÷ objetivo × 100, con tope en el «tope ponderado» del período (150 %).
- **Cumplimiento ponderado** = ponderador × cumplimiento ÷ 100.
- **Semáforo**: verde desde el umbral colectivo del período, ámbar desde el umbral ámbar, rojo bajo eso.

Cuándo se recalcula, solo (al terminar de guardar): al registrar, mover, cambiar de autor o archivar una actividad; al guardar, aprobar, rechazar o eliminar una evidencia o una validación; al crear o cambiar una meta o un período. Si cambia el autor o la fecha de una actividad se recalcula la situación anterior y la nueva.

- Cada cálculo se guarda como un **indicador nuevo solo si cambió algún valor**: queda el historial sin llenar la tabla de filas iguales.
- Una **meta del cargo** se calcula **por funcionario** (cada uno con su avance sobre el mismo objetivo). Por eso el indicador lleva ahora el funcionario («calculado para»).
- Los indicadores que ya existían (sin funcionario) siguen mostrándose hasta que haya uno calculado para la persona; los conteos no los repiten.
- Un **período cerrado no se recalcula** (RN-013), salvo con `--incluir-cerrados`.
- **Recalcular a mano:** botón «Recalcular indicadores» en el tablero de delegación (solo quien puede agregar indicadores) y comando `python manage.py recalcular_indicadores [--periodo ID] [--incluir-cerrados]`. Conviene correrlo una vez después de actualizar el servidor.
- Los datos de prueba se cargan con el cálculo pausado, así que quedan como siempre; el cálculo corre al primer cambio o con el comando.

Código: `planning/calculation.py`, `planning/signals.py`, `planning/management/commands/recalcular_indicadores.py`.

### 2. Ponderadores (RF-006)

Los ponderadores de un funcionario en un período (metas personales y de su cargo) deben sumar **100 %**. Al guardar una meta, si la suma del funcionario (o de alguien de su cargo) no llega o pasa de 100 % el sistema **avisa, pero guarda**: las metas se crean de a una y bloquear dejaría el flujo trabado (y los datos de prueba tienen un caso de 180 %). El aviso nombra a quién afecta. El formulario explica la regla, la ficha de la meta muestra la suma y el inicio, el tablero y la ficha del funcionario marcan los ponderadores que no suman 100 %.

### 3. Ficha del funcionario (RF-008)

La ficha de un funcionario (Organización → Funcionarios) ahora trae **«Ficha del período»**: sus metas con objetivo, avance, esperado hoy, cumplimiento, ponderador, ponderado y semáforo; el total ponderado, la suma de ponderadores, su último ingreso y sus registros. Se puede elegir el período (`?periodo=`).

### 4. Actividad reciente (RF-030)

Por funcionario: **último ingreso**, **días sin ingreso**, **registros del período** y **promedio diario** (registros ÷ días computables transcurridos). Más de 7 días sin ingresar (o nunca) queda en alerta. Aparece como cuadro «Actividad reciente» en el tablero de delegación (con el resumen de la delegación, lámina 18), en la ficha del funcionario, en la vista por cargos y en el inicio de cada funcionario.

### 5. Plazos de compromisos (RF-019)

Cada compromiso tiene un estado de plazo: **Vencido** (abierto y con la fecha pasada), **Por vencer** (vence dentro de 7 días), **En plazo**, **Realizado en plazo** y **Realizado fuera de plazo**. Lo de «realizado» se juzga por el día en que quedó Realizado según el **historial de estados** (v25); si el compromiso es anterior al historial se usa la fecha de su última modificación.

- Listado de la agenda: columna **Plazo**. Ficha: «Detalle del plazo» («Vencido hace 4 días», «Realizado el …, 2 días después de la fecha comprometida»).
- Resumen colectivo: columnas **Vencidos, Por vencer y Fuera de plazo** por funcionario y en el total.
- Dashboard: «Compromisos abiertos» indica cuántos están por vencer, y el panel personal cuenta los vencidos, por vencer y fuera de plazo del funcionario.

### 6. Inicio personal (RF-028)

En el inicio de un funcionario: selector de **período**; cada meta con su **ponderador**, su **aporte ponderado** y el enlace «Ver las actividades» (filtradas por ítem y autor); el **total ponderado**; y el panel «Mis evidencias, compromisos y actividad» (evidencias por estado de revisión, compromisos por estado con vencidos y por vencer, y su actividad reciente).

### 7. Vista por cargos (RF-031)

Nueva pantalla **Resultados → Vista por cargos** (`/resultados/cargos/`): los funcionarios agrupados por cargo, con sus metas, promedio de cumplimiento, ponderado y último ingreso, y por cargo las **cifras logradas por el equipo** (suma de objetivos y de avance por ítem). Filtros de delegación y período. Cada funcionario y cada cargo enlaza a su ficha. Requiere el permiso de ver indicadores y respeta el alcance por delegación.

### 8. Ediciones simultáneas (RF-034, RNF-003)

El control de versión que ya existía se reforzó:

- Al guardar, la fila se **bloquea** y la versión se compara **dentro de la transacción**, así que si alguien guarda en el último instante tampoco se pisa.
- El aviso dice **quién, cuándo y qué** cambió, según la auditoría («Otra persona modificó este registro mientras lo editabas: coordinacion1 hizo «Registro modificado» el …»).
- Un dato que la base rechaza por repetido (código, nombre) se informa en el formulario y no como error del servidor.
- **Validar evidencias** también lleva la versión: si otra persona modificó la evidencia mientras se revisaba, la revisión se rechaza con aviso y no se guarda.

### Pruebas

`core/test_v26.py`: **116 pruebas nuevas** (`AutomaticCalculationTests`, `AutomaticTriggersTests`, `IndicatorIndexTests`, `RecalculateScreenTests`, `WeightRuleTests`, `OfficerSheetTests`, `RecentActivityTests`, `DeadlineTests`, `DeadlineScreensTests`, `PersonalDashboardTests`, `PositionOverviewTests`, `ConcurrencyTests`), registradas en el catálogo de pruebas funcionales con los requisitos correspondientes.

### Decisiones que conviene conocer

- **Tope sobre el cumplimiento:** se aplica al cumplimiento (150 %), y el ponderado se calcula desde el cumplimiento ya con tope. La guía no lo dice con esa precisión.
- **Ponderadores:** se avisa en vez de bloquear (ver punto 2).
- **Períodos cerrados:** no se recalculan solos.

### Qué sigue pendiente del informe

- **RF-020** (compromisos que alimentan el indicador) y **RF-035** (comentarios, necesita una tabla nueva): faltan definiciones del cliente.
- **RF-038**, el **bloqueo de ediciones en períodos cerrados** (RN-013), el antivirus de archivos, HTTPS, respaldos automáticos y la API.
- **Tubo de trabajo:** al marcar una atención «ingresa al tubo» falta decidir si el compromiso se crea con fecha y territorio por defecto o se pide al usuario.

## Versión 25

La v25 implementa tres requisitos del **Informe de la Etapa 2** que estaban sin hacer o a medias: **RF-026** (meta esperada al día), **RF-018** (estados de compromisos con historial) y **RF-021** (resumen colectivo). Se apoyan en la guía del proyecto (reglas RN-007 y RN-008) y en la presentación del cliente (láminas 13, 14 y 17).

**Base de datos:** no se agrega ninguna tabla ni columna. Trae **una migración** (`operations/migrations/0002_commitment_status_pending.py`) que solo cambia las opciones del estado del compromiso; en MariaDB no modifica la estructura. Al actualizar el servidor basta con `sudo bash deploy/actualizar.sh <rama>`.

### 1. Meta esperada al día (RF-026)

Regla de la guía (RN-007): **meta esperada al día = días computables transcurridos ÷ días computables totales × 100**.

Cómo se resolvió lo que la guía deja abierto («tratamiento definido para fecha inicial y final»):

- Un día es computable si es de **lunes a viernes**. Sábado y domingo no avanzan la meta.
- **Hoy ya cuenta como transcurrido**: el primer día del período aporta 1 día y el último completa el 100 %.
- Antes del inicio se espera **0 %**; después del término, o con el período **cerrado**, **100 %**. Nunca pasa de 100 %.
- El total de días que se muestra es el de **«días computables»** que declara el período (así se descuentan feriados); el porcentaje se calcula sobre los días hábiles del calendario del período y se reparte sobre ese total.
- La comparación del avance logrado con lo esperado sigue RN-008: **verde** si alcanza lo esperado, **ámbar** desde el umbral ámbar del período (60 %) de lo esperado y **rojo** bajo eso.

Dónde se ve:

- **Dashboard** (personal y general) y **Tablero de delegación**: cuadro **«Ritmo del período»** con la lámina 17 de la presentación: hoy, inicio, término, días computables totales, días de avance, % diario esperado, **meta esperada al día**, % de avance logrado, la diferencia en puntos porcentuales y el estado frente a lo esperado.
- Cada meta muestra su **valor esperado hoy** (objetivo × % esperado): «Esperado hoy» en el tablero y en «Mis metas del período».

El semáforo de cada meta no cambió: sigue usando los umbrales colectivo y ámbar del período sobre el cumplimiento. El estado «frente a lo esperado» es un dato aparte del cuadro de ritmo.

Código: `planning/pace.py` (`pace_of`, `weekdays_between`), `pace_summary` en `core/views.py` y `core/templates/core/partials/pace_panel.html`.

### 2. Estados de compromisos con historial (RF-018)

Los compromisos pasan por **Ingresado → Pendiente → En proceso → Realizado** (lámina 13). Se agregó el estado **Pendiente** («cuando no podemos cumplir en fecha, informando al usuario») y el estado «Cumplido» pasó a llamarse **Realizado**, como en el informe y en la presentación (el valor guardado sigue siendo `fulfilled`).

Transiciones permitidas (`Commitment.TRANSITIONS`):

| Desde | Puede pasar a |
|---|---|
| Ingresado | Pendiente, En proceso, Realizado |
| Pendiente | En proceso, Realizado |
| En proceso | Pendiente, Realizado |
| Realizado | En proceso (reapertura; queda en el historial) |

«Ingresado» es solo el estado inicial: nadie vuelve a él. Al **editar**, el campo Estado ofrece solo el actual y los estados a los que se puede pasar, y el servidor rechaza cualquier otro con el mensaje «Un compromiso «Pendiente» solo puede pasar a: …». Al **crear** se puede elegir cualquier estado.

**Historial:** cada cambio de estado (y el estado inicial) se guarda en la auditoría con el estado anterior, el nuevo, quién lo hizo y cuándo, y la ficha del compromiso muestra el panel **«Historial de estados»**. Guardar sin cambiar el estado no agrega nada. Un compromiso Pendiente sigue contando como **abierto** en el dashboard y en el tablero.

Código: `Commitment.Status`, `TRANSITIONS` y `can_move` (`operations/models.py`), `CommitmentForm.customize_fields` (`core/forms.py`), `core/commitments.py` (`record_status`, `history_of`), `CommitmentCrud.after_save` y `core/templates/core/crud/commitment_history.html`.

### 3. Resumen colectivo (RF-021)

Nueva pantalla **Operación → Resumen colectivo** (`/agenda/resumen/`, lámina 14): por cada funcionario, cuántos compromisos tiene en cada estado, el total, el **% realizado** (Realizado ÷ total × 100) y el **% por realizar** (el resto: Ingresado, Pendiente y En proceso), más una fila con el total de la delegación y un resumen arriba.

- Filtros: **delegación** (quien ve varias; incluye «Todas las delegaciones») y **período** según la fecha comprometida (por defecto «Todos los períodos»).
- La barra de % realizado usa los umbrales del período (80 % colectivo, 60 % ámbar) como referencia visual, como pide la lámina («se exige un cumplimiento del 80 %»). **No afecta el puntaje:** eso es el RF-020, que sigue pendiente de una definición del cliente.
- Muestra también a los funcionarios activos que aún no tienen compromisos («Sin compromisos»).
- Respeta el alcance: un funcionario solo ve su delegación aunque pida otra. Requiere el permiso de ver compromisos (si no, 403).
- Se actualiza **en vivo** como el dashboard: cuando otra persona guarda un compromiso, la pantalla cambia sola.

Código: `commitment_summary` (`core/views.py`), `collective_summary` (`core/commitments.py`) y `core/templates/core/commitment_summary.html`.

### Datos de prueba

Se agregó el compromiso «Centro de Madres Sector Norte» en estado **Pendiente**, de modo que los datos de prueba tengan compromisos en los cuatro estados.

### Pruebas

`core/test_v25.py`: **40 pruebas nuevas** (`PaceRuleTests`, `PaceScreensTests`, `CommitmentStatusTests`, `CollectiveSummaryTests`), todas registradas en el catálogo de pruebas funcionales (requisitos `RF-026`, `RF-018` y `RF-021`).

### Qué sigue pendiente del informe

RF-020 (compromisos que alimentan el indicador: falta la definición del cliente), RF-030 (actividad reciente), RF-035 (comentarios), el cálculo automático de avance y cumplimiento (RF-022 a RF-024), y los requisitos no funcionales parciales (respaldo automático, monitoreo, etc.).

## Versión 24

La v24 aplica la **Clase 11 (Tiempo real en Django: Channels, WebSocket y Daphne)**. No cambia ninguna tabla ni columna y no trae migraciones.

La clase 11 usa un chat como ejercicio para entender WebSocket; **en el SGR no se incluye el chat**: la idea aplicada es que lo que cambia una persona se vea en la pantalla abierta de otra, sin F5.

La clase habla de una «organización»; en el SGR esa organización es la **delegación**.

### Qué se agregó

1. **Listados en vivo** (el laboratorio de la clase). Si otra persona crea, edita, archiva, restaura o elimina un registro, tu listado se actualiza solo, sin F5, **conservando tu búsqueda, filtros, orden y página**. Aparece un indicador «En vivo» junto al total de resultados y un aviso «Listado actualizado». Funciona en todos los mantenedores, porque está en el motor (`core/crud.py`). La vista «Usuarios eliminados» no se actualiza en vivo.
2. **Dashboard y pantallas de resumen en vivo**. Si la persona A hace un cambio y la persona B tiene abierto el **Dashboard**, el **Tablero de delegación** o **Validar evidencias** en la misma delegación, la pantalla de B se actualiza sola, sin F5: cambian los contadores de pendientes, las últimas actividades, los próximos compromisos y el semáforo de metas. Aparece el indicador «En vivo» y un aviso «Pantalla actualizada». Quien ve «Todas las delegaciones» recibe los cambios de todas; el dashboard de otra delegación no se entera. Recargar la pantalla en vivo no suma una visita al contador del inicio.
3. **Foto de perfil de otra persona (Super Usuario).** En **Control de usuarios**, la ficha del usuario muestra su foto («Sin dato» si no tiene) y el formulario **Editar** (y **Nuevo**) permite subir o reemplazar la foto, o marcar **Quitar la foto actual**. Valen las mismas reglas que en Mi perfil: PNG o JPG de hasta 2 MB, con el contenido verificado. La foto anterior se borra al confirmar el guardado, y queda en la auditoría quién la cambió o quitó y a quién. Cada persona sigue cambiando la suya desde Mi perfil. Como las pantallas de usuarios son solo del Super Usuario, nadie más puede tocar la foto de otra persona. Código: `core/photos.py`, `UserForm` (`core/forms.py`) y `UserCrud.save_photo` (`core/registry.py`).
4. **Daphne** reemplaza a gunicorn como servidor (ASGI), también en el servidor de AWS.

#### Qué cambios actualizan esas pantallas

Atenciones, gestiones de seguimiento, compromisos, evidencias, validaciones, metas, indicadores, ajustes, períodos y funcionarios: cuando se **guardan, archivan, restauran o eliminan**, sea desde el mantenedor, desde la pantalla de validar, desde el cálculo de indicadores o desde el Django Admin. Se detectan con señales de Django (`post_save` / `post_delete`, en `websocket/signals.py`) y el aviso se publica **después del commit** (`transaction.on_commit`): si el guardado se deshace, nadie recibe nada. Si un registro cambia de delegación, se avisa a la anterior y a la nueva. Un dato general (por ejemplo el período) avisa a todas las delegaciones. Los cambios masivos que no pasan por `save()` ni `delete()` (`QuerySet.update`) y los hechos desde otro proceso (`manage.py shell`, comandos) no se avisan.

### Cómo funciona (el recorrido de la clase)

| Paso | Listado en vivo |
|---|---|
| 1. Navegador A | guarda el formulario del mantenedor (POST con CSRF) |
| 2. Vista Django | valida y guarda dentro de una transacción |
| 3. Servicio | `notify_crud_change` registra el aviso con `transaction.on_commit`: **solo se publica si el guardado se confirmó** |
| 4. Consumer | `CrudChangesConsumer` entrega `{"type": "crud_changed"}` a cada conexión del grupo |
| 5. Navegador B | `live-updates.js` pide **por HTTP** la tabla actual (misma URL, mismos filtros) y reemplaza la región de resultados |

Para el dashboard, el tablero y validar el recorrido es el mismo, con dos diferencias: el aviso lo publica una **señal** de Django (`websocket/signals.py`) en vez del motor de mantenedores, y lo entrega `LiveConsumer` (`ws/live/`) como `{"type": "live_changed", "model": "operations.activity"}`. Al recibirlo, `live-updates.js` pide por HTTP la **misma pantalla** (con `X-Requested-With: fetch`) y reemplaza la región `[data-live-region]`; el servidor vuelve a aplicar permisos y delegación.

Por qué el listado vuelve a pedir la tabla por HTTP en vez de recibirla por el socket: así se vuelven a aplicar permisos, delegación, filtros y paginación en el servidor, y por el WebSocket no viaja ningún dato del registro.

### Seguridad

- `AllowedHostsOriginValidator` (usa `ALLOWED_HOSTS`): una conexión desde otro origen es rechazada.
- `AuthMiddlewareStack`: el usuario sale de la sesión; un usuario anónimo no puede escuchar ningún aviso.
- Cada delegación escucha solo su grupo (`crud_<modulo>_d<id>`, `live_d<id>`, `live_all`); el formulario no elige autor ni delegación.
- Para escuchar los cambios de un mantenedor hace falta el permiso de **ver** ese mantenedor.
- `ws/live/` solo exige sesión, pero **no envía ningún dato**: solo avisa que algo cambió. Lo que B ve lo entrega la pantalla por HTTP, que aplica sus permisos y su delegación; un aviso de más solo provoca una nueva consulta.
- Los mensajes entran solo por HTTP (con CSRF); lo que el navegador escriba en el socket se ignora.

### Dónde está en el código

| Pieza de la clase | Archivo |
|---|---|
| `INSTALLED_APPS` (`daphne` primero, `channels`, `websocket`), `ASGI_APPLICATION`, `CHANNEL_LAYERS` | `sgr_project/settings.py` |
| `asgi.py` (`ProtocolTypeRouter`, `AllowedHostsOriginValidator`, `AuthMiddlewareStack`, `URLRouter`) | `sgr_project/asgi.py` |
| `routing.py` (`ws/crud/<slug>/` y `ws/live/`) | `websocket/routing.py` |
| Consumers | `websocket/consumers.py` |
| `services.py` (publicar, grupos, `on_commit`) | `websocket/services.py` |
| JavaScript de las pantallas en vivo | `core/static/core/js/live-updates.js` |
| Aviso tras guardar, archivar, restaurar o eliminar (listados) | `core/crud.py` (`notify_crud_change`) |
| Aviso de cambio de datos (dashboard, tablero, validar) | `websocket/signals.py` (modelos en `LIVE_MODELS`), `websocket/services.py` (`publish_live_changed`, `live_groups_for`), `LiveConsumer` en `websocket/consumers.py` |
| Regiones en vivo de las pantallas | `[data-live-region]` en `core/templates/core/dashboard.html`, `delegation_board.html` y `validate_list.html`; indicador en `core/templates/core/partials/live_chip.html` |
| Pruebas | `core/test_v24.py` |

### Para correrlo en el computador

```
python -m pip install -r requirements.txt        # ahora incluye channels y daphne
python manage.py check
python manage.py runserver --noreload            # debe decir: Starting ASGI/Daphne ... development server
```

Prueba: inicia sesión con dos usuarios de la misma delegación (un navegador normal y una ventana privada) y abre en las dos el **Dashboard**; mira en Network → WS el `101 Switching Protocols`. En una, edita una atención: la otra cambia sola, sin F5. Lo mismo ocurre en cualquier mantenedor abierto en las dos ventanas. Usa **un solo servidor** (la capa de canales es de memoria: dos procesos no se hablan entre sí).

### En el servidor de AWS

Daphne reemplaza a gunicorn y Apache debe dejar pasar los WebSocket. En un servidor instalado antes de la v24:

```
cd /opt/sgr/app
sudo -u sgr git fetch --all
sudo -u sgr git checkout proyecto-sgr-v24
sudo bash deploy/al2023/agregar_websocket.sh        # Apache pasa /ws/ y el servicio queda con Daphne
sudo bash deploy/actualizar.sh proyecto-sgr-v24     # instala channels y daphne, y reinicia
```

`agregar_websocket.sh` guarda una copia de la configuración de Apache (`00-sgr.conf.antes-websocket`), valida con `httpd -t` y se puede repetir. Un servidor nuevo ya queda con todo al correr `instalar_al2023.sh`.

**Qué no se pudo probar:** los scripts de `deploy/` no se ejecutaron en Amazon Linux ni con Apache real (solo se revisó su sintaxis y su contenido, y la inserción en la configuración de Apache sobre una copia). Daphne, los listados y el dashboard en vivo sí se probaron en un servidor Daphne real y en un navegador Chromium con dos sesiones.

### Límites a tener en cuenta

- La capa de canales es **en memoria**: sirve con un solo proceso (lo que usa el servidor). Con varios procesos habría que usar `channels_redis`.
- Django atiende las vistas síncronas por ASGI en un solo hilo por proceso: para el uso de este sistema alcanza, pero es más lento que varios hilos de gunicorn si hay mucha gente a la vez.
- Cada cambio de datos en esos modelos genera una consulta nueva de la pantalla en los navegadores que la tienen abierta (con una pausa de 0,3 s para juntar varios avisos seguidos). Con mucha gente trabajando a la vez en la misma delegación, el dashboard se recarga seguido.
- Daphne por sí solo no sirve los archivos estáticos (`/static/`): en local los sirve `runserver`; en el servidor, Apache.

### Para la defensa (preguntas de la clase)

- **¿Por qué responder al fetch de A no actualiza la pantalla de B?** Porque la respuesta HTTP va solo a quien hizo el POST. B se entera por su WebSocket, que el servidor mantiene abierto.
- **¿Diferencia entre `type` del evento y `payload.type`?** El primero (`type` del evento del grupo) es el nombre del método del Consumer que se ejecuta (`crud_event` o `live_event`); el segundo va dentro de lo que se envía al navegador (`crud_changed`, `live_changed`) y lo usa JavaScript para saber qué hacer.
- **¿Qué se cambia para aplicar el recorrido a otro módulo?** Un nombre de grupo propio, un evento y un servicio que publique; en el CRUD, avisar con `transaction.on_commit` después de guardar y que JavaScript vuelva a pedir la tabla.
- **¿Cómo se entera B de lo que hizo A en el dashboard?** A guarda (POST); una señal de Django registra el aviso con `transaction.on_commit`; tras el commit el servicio hace `group_send` al grupo `live_d<delegación>`; el `LiveConsumer` de B envía `live_changed` por su WebSocket; `live-updates.js` pide por HTTP el dashboard otra vez y reemplaza la región; el servidor lo recalcula con los permisos y la delegación de B.
- **¿Por qué una señal y no solo el mantenedor?** Porque el dashboard cambia también con acciones que no pasan por el motor de mantenedores (validar una evidencia, calcular un indicador, el Django Admin). La señal las cubre todas con un solo punto.

## Versión 23

La v23 no cambia ninguna tabla ni columna, y no trae migraciones nuevas: usa el campo `deleted_at` que ya tenía `UserProfile`.

### Eliminar usuarios: «Usuarios eliminados»

Hasta la v22 un usuario solo se podía **desactivar** (casilla «Activo» en Editar); seguía mezclado en el listado y no había forma de «borrarlo».

Desde la v23, en **Control de usuarios** cada fila (y la ficha del usuario) tiene el botón **Eliminar**:

- El usuario **no se borra de la base** (su historial, sus actividades y la auditoría quedan intactos). Pasa a estar *eliminado*: se marca con fecha en `UserProfile.deleted_at`, la cuenta queda **inactiva** y ya no puede ingresar.
- Sale del listado normal y aparece en **«Usuarios eliminados»** (enlace sobre la tabla, o `usuarios/?archivados=solo`). Esa vista tiene buscador, filtros, paginación y exportación a Excel como el resto.
- Desde ahí se puede **Restaurar**. El usuario vuelve al listado, pero **sigue inactivo**: hay que activarlo en Editar cuando deba volver a ingresar.
- Un usuario eliminado no se puede editar (la ficha lo indica con la fecha).
- Queda en la auditoría («Registro archivado» / «Registro restaurado»).
- La confirmación usa SweetAlert2, como los demás mantenedores; si no se puede (por ejemplo, tu propia cuenta) avisa el motivo.

### Solo el Super Usuario

Eliminar, ver los eliminados y restaurar **solo lo puede hacer el Super Usuario**, aunque otro perfil tenga el permiso de eliminar usuarios:

- Para los demás no aparecen los botones «Eliminar» ni el enlace «Usuarios eliminados».
- En el servidor, intentar eliminar da 403; los usuarios eliminados responden 404 (ni siquiera existen para ellos), con cualquier combinación de filtros.
- Nadie puede eliminar **su propia cuenta**.

### Detalles a tener en cuenta

- El nombre de usuario y el correo de un usuario eliminado siguen ocupados: crear otro con el mismo nombre dará el aviso de «ya existe». Hay que restaurar al eliminado.
- El funcionario asociado queda reservado a ese usuario (un funcionario solo puede tener una cuenta) hasta que se restaure.

### Dónde está en el código

- `core/crud.py`: el motor ahora admite que la marca de «archivado» viva en otra tabla (`archive_lookup`, `archived_at()`, `set_archived()`), un permiso extra por usuario (`archive_guard()`, `can_see_archived()`) y la vista «solo archivados» (`?archivados=solo`). Los demás mantenedores no cambian.
- `core/registry.py`, `UserCrud`: `archive_lookup = "profile__deleted_at"`, exige `is_superuser`, desactiva la cuenta al eliminar y oculta los eliminados a quien no es Super Usuario.
- `core/templates/core/crud/list.html`, `detail.html`, `archive_confirm.html`: textos de «Usuarios eliminados».
- Pruebas: `core/test_v23.py` (`DeletedUsersTests`, `OnlySuperuserDeletesUsersTests`), registradas en `core/qa/`.

## Versión 22

La v22 no cambia ninguna tabla ni columna, y no trae migraciones nuevas.

Se ajusta el proyecto a la Pre-evaluación Sumativa III (CRUD individual: listar, crear, editar y **eliminar**; Create y Update con Modal Bootstrap; eliminación con SweetAlert2; buscador, al menos un filtro y paginación).

### Eliminar de verdad (con confirmación de SweetAlert2)

Hasta la v21 el botón «Eliminar» de casi todos los mantenedores archivaba el registro: dejaba de verse, pero seguía en la base. Desde la v22, seis mantenedores permiten además **borrarlo de la base**:

| Mantenedor | Se bloquea si… |
|---|---|
| Beneficiarios | tiene actividades |
| Territorios | tiene compromisos |
| Servicios | tiene actividades |
| Cargos | tiene funcionarios, ítems de cargo o metas |
| Tipos de gestión | tiene gestiones |
| Agenda (compromisos) | no se bloquea |

Cómo funciona:

- En estos mantenedores hay dos acciones distintas: **Archivar** (el registro se oculta y se puede restaurar desde «Incluir archivados») y **Eliminar** (se borra para siempre). En los demás mantenedores no cambia nada: su único botón «Eliminar» sigue archivando.
- Eliminar pide confirmación con SweetAlert2 («¿Eliminar definitivamente?»). Si el registro está en uso, SweetAlert2 avisa por qué no se puede y no se envía nada. Sin JavaScript queda la página de confirmación de siempre.
- El motivo del bloqueo sale de `Crud.delete_blockers()` (`core/crud.py`): revisa los registros que usan al que se quiere borrar, incluidos los archivados. Si igual hubiera uno, la vista captura el `ProtectedError` y no borra nada.
- Un registro ya archivado también se puede eliminar de verdad.
- El borrado queda en la auditoría («Registro eliminado», con el nombre del registro).
- No se activó en Gestiones (cada actividad numera sus gestiones, y borrar una dejaría la secuencia con huecos), ni en Actividades, Evidencias, Validaciones ni Metas, que son registros de trabajo con historial.

Dónde está en el código: `deletable = True` en cada mantenedor de `core/registry.py`; `CrudDeleteView` y `Crud.delete_blockers()` en `core/crud.py`; `partials/delete_link.html` y `static/core/js/confirm.js` para los botones y SweetAlert2.

### Buscador y filtros que faltaban (Clase 10)

| Mantenedor | Antes | Ahora |
|---|---|---|
| Beneficiarios | Solo buscador | Buscador + filtro de **Estado** (Activo / Inactivo) |
| Cargos | Solo buscador | Buscador + filtro de **Estado** |
| Tipos de gestión | Solo buscador | Buscador + filtro de **Estado** |
| Ítems y metas | Solo filtros | **Buscador** por nombre y descripción + filtros |

Con esto, los seis mantenedores con eliminación real tienen buscador, al menos un filtro y paginación de 5, 15 o 30 filas. Períodos sigue sin buscador (no tiene ningún campo de texto).

### Verificación

- Pruebas nuevas en `core/test_v22.py` (18), con su descripción en `core/qa/esperado_v22.py`: eliminación real y por mantenedor, registros en uso, botones «Archivar» y «Eliminar», ventana de edición, página sin JavaScript, permisos, solo POST, filtro de estado, filtros con paginación y buscador de Ítems.
- Después de actualizar no hace falta migrar. El registro `docs/pruebas/` sigue siendo el de la v20 hasta volver a generarlo.

## Versión 21

La v21 no cambia ninguna tabla ni columna. Trae una migración nueva (`accounts 0006`), pero solo cambia el tipo de campo de la foto en Django; la columna sigue siendo `varchar(255)`.

Se ajusta el proyecto a lo visto en clases: **Clase 9** (archivos e imágenes con `FileField`, `ImageField` y `MEDIA`) y **Clase 10** (buscador, filtros, ordenamiento y paginación).

### Filas por página: 5, 15 y 30 (Clase 10)

| Antes | Ahora |
|---|---|
| Opciones 10, 20 y 50; por defecto 20 | Opciones 5, 15 y 30; por defecto 15 |

- Cambia en `PAGE_SIZES` y `PAGE_SIZE` de `core/crud.py`. Todos los listados y la pantalla Atención usan esos valores.
- La elección sigue guardándose en `request.session` y sigue validándose contra la lista permitida, así que se mantiene al refrescar y al cambiar de página. Un valor que no esté en la lista (por ejemplo 10, 20 o 50, que antes eran válidos) se rechaza.
- El buscador, los filtros, el orden y la paginación no cambian: ya conservaban el alcance por delegación y los parámetros de la URL.

### Foto de perfil con `ImageField` (Clase 9)

| Antes | Ahora |
|---|---|
| `UserProfile.photo` era un `FileField`; solo se revisaba que el archivo empezara con la firma de un PNG o JPG | `UserProfile.photo` es un `ImageField`; Pillow comprueba además que sea una imagen real |

- Hay una dependencia nueva: `pillow==12.3.0` en `requirements.txt`. En el servidor, `actualizar.sh` la instala junto con las demás (`pip install -r requirements.txt`).
- El formulario `ProfilePhotoForm` usa `forms.ImageField`, con mensaje en español para el archivo dañado. Se mantiene `check_upload` (extensión, tamaño de 2 MB, archivo vacío y firma del contenido).
- Las evidencias siguen siendo `FileField`, porque aceptan PDF, Word y Excel además de imágenes.
- Las fotos ya guardadas siguen funcionando: no se mueve ni se renombra ningún archivo.

### Política de archivos reemplazados y huérfanos (Clase 9)

Queda documentada en el README, sección «Archivos subidos: límites y política»: límites y tipos aceptados, cómo se entregan los archivos y qué pasa con cada uno al reemplazar, quitar, archivar o quedar sin registro. El comportamiento no cambia: la foto anterior se borra y los archivos de evidencia se conservan.

### Verificación

- Pruebas ajustadas: `PageSizeTests` (`core/test_access_flow.py`), `NoticeMarkupTests` (`core/test_flash.py`), `PagerTests` (`core/test_search.py`) y `ProfilePhotoTests` (`core/test_v16.py`, que ahora sube imágenes reales hechas con Pillow).
- Pruebas nuevas: `test_the_chosen_size_survives_a_refresh` y `test_the_photo_is_an_image_field_and_a_file_with_only_the_signature_is_rejected`, con su descripción en `core/qa/`.
- Después de actualizar: `pip install -r requirements.txt`, `python manage.py migrate` y `python manage.py check`.
- El registro `docs/pruebas/registro_pruebas_funcionales.csv` y `.xlsx` y los resultados de `docs/pruebas/resultados/` siguen siendo los de la v20 hasta volver a correr la suite y regenerarlos (ver «Registro de pruebas» en el README).

## Versión 20

La v20 no cambia la base de datos: no hay migraciones nuevas ni tablas distintas.

### Identificador institucional del funcionario

| Antes | Ahora |
|---|---|
| Se escribía a mano al crear el funcionario (por ejemplo `F-1007`) | Se genera solo al guardar |
| Se podía cambiar al editar | No se puede cambiar: al crear el campo no aparece; al editar se ve, pero solo para leerlo. En el listado y en la ficha se ve y se puede buscar (por ejemplo `F-1005`) |

Cómo se arma el número:

- El formato es `F-NNNN`.
- Sigue el bloque de miles que ya usa la delegación del funcionario: si Delegación Norte tiene de `F-1001` a `F-1006`, el siguiente es `F-1007`; si Delegación Sur llega a `F-2005`, el siguiente es `F-2006`.
- Una delegación que todavía no tiene funcionarios abre el bloque siguiente (`F-3001`).
- Los funcionarios archivados cuentan: su identificador sigue ocupado y no se reutiliza.
- Si dos personas guardan al mismo tiempo y toparían con el mismo número, el sistema lo vuelve a calcular.
- Un funcionario creado desde el código o desde el Django Admin con identificador propio lo conserva.

Dónde está en el código: `Officer.next_institutional_id()` y `Officer.save()` en `organization/models.py`; lo quita del formulario de alta y lo deja de solo lectura en el de edición, en `OfficerForm.customize_fields()` en `core/forms.py`.

### Búsqueda mientras se escribe

No cambia en esta versión: viene desde la v18. Los listados y la pantalla Atención filtran solos unos 0,35 segundos después de dejar de escribir y al cambiar un filtro. Si una pestaña sigue abierta de antes de actualizar el servidor, hay que recargarla (Ctrl+Shift+R) para que cargue el script.

### Despliegue

`deploy/actualizar.sh` ahora deja los archivos estáticos legibles para Apache después de `collectstatic`. Sin eso, los archivos que cambiaban en una actualización quedaban sin permiso de lectura para otros usuarios y el sitio se veía sin estilos.

### Verificación

- `python manage.py check` y `makemigrations --check`: sin cambios.
- Suite completa: 837 pruebas aprobadas (827 de la v19 más 10 nuevas). El registro `docs/pruebas/registro_pruebas_funcionales.csv` y `.xlsx` se generó de nuevo.
- Pruebas nuevas en `core/test_officer_id.py` (bloque por delegación, archivados, delegación nueva, identificador propio, choque de números, formulario de alta sin el campo, edición de solo lectura, búsqueda y ficha). Se ajustaron dos pruebas de `core/test_v16.py` y una de `core/test_rules.py` que escribían el identificador a mano.

## Versión 19

La v19 no cambia el sistema ni la base de datos: no hay migraciones nuevas ni pantallas distintas. Cambia cómo se trabajan los datos.

### Se trabaja sobre la base real, sin semillas

- Se quitó el comando `seed_demo_data` (cargaba usuarios, delegaciones y registros ficticios). Los datos viven en la base del servidor (MariaDB, administrada desde phpMyAdmin).
- Para una base vacía quedan solo los comandos de arranque: `seed_roles`, `seed_management_types` y `createsuperuser`.
- Los datos que necesitan las pruebas automáticas pasaron a `core/datos_prueba.py` y solo se cargan en la base temporal de las pruebas; ya no son un comando de `manage.py`.
- `cargar_volumen_estres` se conserva (con `--limpiar`), pero ahora pide que la base ya tenga funcionarios e ítems.
- `deploy/actualizar.sh`, `deploy/al2023/instalar_al2023.sh`, el README y las guías de despliegue ya no mencionan los datos de demostración.

### Scripts de la base (carpeta `sql/`)

- `sgr_django_v19.sql`: estructura real de `sgr_django` (32 tablas), reemplaza a `sgr_django_estructura_mariadb.sql` (que era de la v13).
- `sgr_django_v19_dbeaver.sql`: el mismo esquema en una base aparte (`sgr_django_der`) para abrirlo en DBeaver y sacar los diagramas ER.
- `sgr_v19_modelo_relacional_completo_en.sql`: diseño de 22 tablas en inglés, reemplaza a `sgr_v10_...`.

### Verificación

- `python manage.py check` y `makemigrations --check`: sin cambios.
- Suite completa: 827 pruebas aprobadas. El registro `docs/pruebas/registro_pruebas_funcionales.csv` y `.xlsx` se generó de nuevo.

## Versión 16

Parte de la v15 (escudo oficial y arreglo de una prueba). No toca las versiones anteriores.

### Qué cambió

| Tema | Antes | Ahora |
|---|---|---|
| Validar evidencia | Se elegía el funcionario verificador y se volvía a la lista | El verificador es el funcionario de quien tiene la sesión (no se elige) y al guardar se vuelve a la página de la evidencia revisada |
| Quién valida | Cualquiera con permiso, incluso su propia evidencia | Nadie valida la evidencia que subió: no le aparece en su lista ni el botón, y el servidor lo rechaza |
| Super Usuario al validar | Tenía que elegir un funcionario | Valida sin elegir; la revisión queda sin funcionario y se muestra como «Super Usuario» |
| Evidencias | Se escribía el nombre del archivo y los metadatos | Se sube el archivo (PDF, PNG, JPG, Word o Excel, hasta 10 MB). Los metadatos (nombre original, tipo, tamaño y huella SHA-256) los arma el sistema |
| Descarga de archivos | No había archivo | Solo por una dirección que revisa sesión, permiso y delegación; no hay dirección pública |
| Foto de perfil | No existía | En *Mi perfil* se sube, cambia o quita (PNG o JPG, hasta 2 MB); se ve en la franja de arriba |
| Funcionario y usuario | Dos altas separadas | *Nuevo funcionario* trae la sección «Acceso al sistema» (opcional): usuario, correo, contraseña y perfil; crea las dos cosas en un paso. En *Usuarios* el nombre se toma del funcionario |
| Atención y Actividades | Dos pantallas con casi lo mismo | Una sola: *Atención* (búsqueda por RUT o nombre, filtros, archivados, Excel). La dirección `/actividades/` lleva a Atención |

### Cambios en la base de datos

Los aplica `python manage.py migrate` (lo corre `deploy/actualizar.sh`). Ningún dato se borra ni se cambia.

| Tabla | Cambio | Migración |
|---|---|---|
| `evidence_validation` | `reviewer_officer_id` admite vacío (revisión del Super Usuario) | evidence 0002 |
| `evidence_evidence` | `file_link` sigue siendo `varchar(255)`; ahora guarda la ruta del archivo subido | evidence 0003 |
| `accounts_userprofile` | columna nueva `photo varchar(255)` vacía por defecto | accounts 0005 |

El diagrama en inglés actualizado es `sql/sgr_v19_modelo_relacional_completo_en.sql`; el detalle de los cambios sobre la base del servidor, en `sql/sgr_v13_a_v16_alter.sql`.

### En el servidor

- Los archivos subidos se guardan en `/opt/sgr/app/media` (o en `MEDIA_ROOT` si se define en `/etc/sgr/sgr.env`). `actualizar.sh` crea la carpeta. No está en Git ni se pierde al actualizar: **respáldala junto con la base de datos**.
- Apache y nginx aceptan envíos de hasta 12 MB (antes 5 MB en Apache).
- Las evidencias que ya estaban cargadas (solo con un nombre de archivo escrito) siguen visibles: muestran el nombre y «el archivo no está en el sistema» hasta que alguien suba el archivo.
- Los archivos viejos no se borran al reemplazar una evidencia (queda el rastro); la foto anterior sí se borra al cambiarla.

### Decisiones que quedan para el equipo

1. ¿Coordinación puede editar todo en cualquier delegación o solo ver y administrar catálogos?
2. ¿Quién puede archivar o eliminar evidencias y atenciones (hoy: quien tenga el permiso *delete*)?
3. ¿Se cambia el rojo del sistema (`#920000`) por el del escudo oficial (`#990100`)?
4. ¿Se borra el archivo físico cuando una evidencia se archiva? (hoy se conserva).
