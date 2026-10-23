# Cambios de la v25 respecto de la v24

La v25 implementa tres requisitos del **Informe de la Etapa 2** que estaban sin hacer o a medias: **RF-026** (meta esperada al día), **RF-018** (estados de compromisos con historial) y **RF-021** (resumen colectivo). Se apoyan en la guía del proyecto (reglas RN-007 y RN-008) y en la presentación del cliente (láminas 13, 14 y 17).

**Base de datos:** no se agrega ninguna tabla ni columna. Trae **una migración** (`operations/migrations/0002_commitment_status_pending.py`) que solo cambia las opciones del estado del compromiso; en MariaDB no modifica la estructura. Al actualizar el servidor basta con `sudo bash deploy/actualizar.sh <rama>`.

## 1. Meta esperada al día (RF-026)

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

## 2. Estados de compromisos con historial (RF-018)

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

## 3. Resumen colectivo (RF-021)

Nueva pantalla **Operación → Resumen colectivo** (`/agenda/resumen/`, lámina 14): por cada funcionario, cuántos compromisos tiene en cada estado, el total, el **% realizado** (Realizado ÷ total × 100) y el **% por realizar** (el resto: Ingresado, Pendiente y En proceso), más una fila con el total de la delegación y un resumen arriba.

- Filtros: **delegación** (quien ve varias; incluye «Todas las delegaciones») y **período** según la fecha comprometida (por defecto «Todos los períodos»).
- La barra de % realizado usa los umbrales del período (80 % colectivo, 60 % ámbar) como referencia visual, como pide la lámina («se exige un cumplimiento del 80 %»). **No afecta el puntaje:** eso es el RF-020, que sigue pendiente de una definición del cliente.
- Muestra también a los funcionarios activos que aún no tienen compromisos («Sin compromisos»).
- Respeta el alcance: un funcionario solo ve su delegación aunque pida otra. Requiere el permiso de ver compromisos (si no, 403).
- Se actualiza **en vivo** como el dashboard: cuando otra persona guarda un compromiso, la pantalla cambia sola.

Código: `commitment_summary` (`core/views.py`), `collective_summary` (`core/commitments.py`) y `core/templates/core/commitment_summary.html`.

## Datos de prueba

Se agregó el compromiso «Centro de Madres Sector Norte» en estado **Pendiente**, de modo que los datos de prueba tengan compromisos en los cuatro estados.

## Pruebas

`core/test_v25.py`: **40 pruebas nuevas** (`PaceRuleTests`, `PaceScreensTests`, `CommitmentStatusTests`, `CollectiveSummaryTests`), todas registradas en el catálogo de pruebas funcionales (requisitos `RF-026`, `RF-018` y `RF-021`).

## Qué sigue pendiente del informe

RF-020 (compromisos que alimentan el indicador: falta la definición del cliente), RF-030 (actividad reciente), RF-035 (comentarios), el cálculo automático de avance y cumplimiento (RF-022 a RF-024), y los requisitos no funcionales parciales (respaldo automático, monitoreo, etc.).
