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
| `core/test_v24.py`, `core/test_v27.py`, `core/test_v28.py` | `core/test_realtime.py` (y `DaphneDeployTests` en `core/test_deploy.py`, `UserPhotoByAdminTests` en `core/test_uploads_photos_attention.py`) |
| `core/test_v25.py` | `core/test_pace_and_commitments.py` |
| `core/test_v26.py` | `core/test_results_and_calculation.py` |
| `core/qa/esperado_vNN.py` | `core/qa/esperado_<tema>.py` (mismo tema que su archivo de pruebas) |
| `sql/*.sql` (todos) | `sql/sgr_django.sql` (estructura vigente) |

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
