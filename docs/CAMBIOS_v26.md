# Cambios de la v26 respecto de la v25

La v26 implementa del **Informe de la Etapa 2** los requisitos que se podían hacer sin información del cliente: el **cálculo automático** de indicadores (**RF-022, RF-023, RF-024, RF-014**), **RF-006** (ponderadores), **RF-008** (ficha del funcionario), **RF-030** (actividad reciente), **RF-019** (plazos), **RF-028 y RF-031** (inicio personal y vista por cargos) y **RF-034 / RNF-003** (ediciones simultáneas).

**Base de datos:** se agrega **una columna**: `planning_indicator.officer_id` (acepta nulo). Trae la migración `planning/migrations/0002_indicator_officer.py` (y, desde la v25, `operations/migrations/0002_commitment_status_pending.py`). Con `sudo bash deploy/actualizar.sh <rama>` se aplican solas. Quien actualice la base a mano tiene `sql/sgr_v25_a_v26_alter.sql`. **El diagrama relacional (DER) y el informe de la base deben agregar `officer_id` a `indicator`.**

Parámetro nuevo (opcional): `SGR_DIAS_POR_VENCER` en la configuración, por defecto **7**.

## 1. Cálculo automático de indicadores (RF-022, RF-023, RF-024, RF-014)

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

## 2. Ponderadores (RF-006)

Los ponderadores de un funcionario en un período (metas personales y de su cargo) deben sumar **100 %**. Al guardar una meta, si la suma del funcionario (o de alguien de su cargo) no llega o pasa de 100 % el sistema **avisa, pero guarda**: las metas se crean de a una y bloquear dejaría el flujo trabado (y los datos de prueba tienen un caso de 180 %). El aviso nombra a quién afecta. El formulario explica la regla, la ficha de la meta muestra la suma y el inicio, el tablero y la ficha del funcionario marcan los ponderadores que no suman 100 %.

## 3. Ficha del funcionario (RF-008)

La ficha de un funcionario (Organización → Funcionarios) ahora trae **«Ficha del período»**: sus metas con objetivo, avance, esperado hoy, cumplimiento, ponderador, ponderado y semáforo; el total ponderado, la suma de ponderadores, su último ingreso y sus registros. Se puede elegir el período (`?periodo=`).

## 4. Actividad reciente (RF-030)

Por funcionario: **último ingreso**, **días sin ingreso**, **registros del período** y **promedio diario** (registros ÷ días computables transcurridos). Más de 7 días sin ingresar (o nunca) queda en alerta. Aparece como cuadro «Actividad reciente» en el tablero de delegación (con el resumen de la delegación, lámina 18), en la ficha del funcionario, en la vista por cargos y en el inicio de cada funcionario.

## 5. Plazos de compromisos (RF-019)

Cada compromiso tiene un estado de plazo: **Vencido** (abierto y con la fecha pasada), **Por vencer** (vence dentro de 7 días), **En plazo**, **Realizado en plazo** y **Realizado fuera de plazo**. Lo de «realizado» se juzga por el día en que quedó Realizado según el **historial de estados** (v25); si el compromiso es anterior al historial se usa la fecha de su última modificación.

- Listado de la agenda: columna **Plazo**. Ficha: «Detalle del plazo» («Vencido hace 4 días», «Realizado el …, 2 días después de la fecha comprometida»).
- Resumen colectivo: columnas **Vencidos, Por vencer y Fuera de plazo** por funcionario y en el total.
- Dashboard: «Compromisos abiertos» indica cuántos están por vencer, y el panel personal cuenta los vencidos, por vencer y fuera de plazo del funcionario.

## 6. Inicio personal (RF-028)

En el inicio de un funcionario: selector de **período**; cada meta con su **ponderador**, su **aporte ponderado** y el enlace «Ver las actividades» (filtradas por ítem y autor); el **total ponderado**; y el panel «Mis evidencias, compromisos y actividad» (evidencias por estado de revisión, compromisos por estado con vencidos y por vencer, y su actividad reciente).

## 7. Vista por cargos (RF-031)

Nueva pantalla **Resultados → Vista por cargos** (`/resultados/cargos/`): los funcionarios agrupados por cargo, con sus metas, promedio de cumplimiento, ponderado y último ingreso, y por cargo las **cifras logradas por el equipo** (suma de objetivos y de avance por ítem). Filtros de delegación y período. Cada funcionario y cada cargo enlaza a su ficha. Requiere el permiso de ver indicadores y respeta el alcance por delegación.

## 8. Ediciones simultáneas (RF-034, RNF-003)

El control de versión que ya existía se reforzó:

- Al guardar, la fila se **bloquea** y la versión se compara **dentro de la transacción**, así que si alguien guarda en el último instante tampoco se pisa.
- El aviso dice **quién, cuándo y qué** cambió, según la auditoría («Otra persona modificó este registro mientras lo editabas: coordinacion1 hizo «Registro modificado» el …»).
- Un dato que la base rechaza por repetido (código, nombre) se informa en el formulario y no como error del servidor.
- **Validar evidencias** también lleva la versión: si otra persona modificó la evidencia mientras se revisaba, la revisión se rechaza con aviso y no se guarda.

## Pruebas

`core/test_v26.py`: **116 pruebas nuevas** (`AutomaticCalculationTests`, `AutomaticTriggersTests`, `IndicatorIndexTests`, `RecalculateScreenTests`, `WeightRuleTests`, `OfficerSheetTests`, `RecentActivityTests`, `DeadlineTests`, `DeadlineScreensTests`, `PersonalDashboardTests`, `PositionOverviewTests`, `ConcurrencyTests`), registradas en el catálogo de pruebas funcionales con los requisitos correspondientes.

## Decisiones que conviene conocer

- **Tope sobre el cumplimiento:** se aplica al cumplimiento (150 %), y el ponderado se calcula desde el cumplimiento ya con tope. La guía no lo dice con esa precisión.
- **Ponderadores:** se avisa en vez de bloquear (ver punto 2).
- **Períodos cerrados:** no se recalculan solos.

## Qué sigue pendiente del informe

- **RF-020** (compromisos que alimentan el indicador) y **RF-035** (comentarios, necesita una tabla nueva): faltan definiciones del cliente.
- **RF-038**, el **bloqueo de ediciones en períodos cerrados** (RN-013), el antivirus de archivos, HTTPS, respaldos automáticos y la API.
- **Tubo de trabajo:** al marcar una atención «ingresa al tubo» falta decidir si el compromiso se crea con fecha y territorio por defecto o se pide al usuario.
