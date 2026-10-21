# Cambios de la v22 respecto de la v21

La v22 no cambia ninguna tabla ni columna, y no trae migraciones nuevas.

Se ajusta el proyecto a la Pre-evaluación Sumativa III (CRUD individual: listar, crear, editar y **eliminar**; Create y Update con Modal Bootstrap; eliminación con SweetAlert2; buscador, al menos un filtro y paginación).

## Eliminar de verdad (con confirmación de SweetAlert2)

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

## Buscador y filtros que faltaban (Clase 10)

| Mantenedor | Antes | Ahora |
|---|---|---|
| Beneficiarios | Solo buscador | Buscador + filtro de **Estado** (Activo / Inactivo) |
| Cargos | Solo buscador | Buscador + filtro de **Estado** |
| Tipos de gestión | Solo buscador | Buscador + filtro de **Estado** |
| Ítems y metas | Solo filtros | **Buscador** por nombre y descripción + filtros |

Con esto, los seis mantenedores con eliminación real tienen buscador, al menos un filtro y paginación de 5, 15 o 30 filas. Períodos sigue sin buscador (no tiene ningún campo de texto).

## Verificación

- Pruebas nuevas en `core/test_v22.py` (18), con su descripción en `core/qa/esperado_v22.py`: eliminación real y por mantenedor, registros en uso, botones «Archivar» y «Eliminar», ventana de edición, página sin JavaScript, permisos, solo POST, filtro de estado, filtros con paginación y buscador de Ítems.
- Después de actualizar no hace falta migrar. El registro `docs/pruebas/` sigue siendo el de la v20 hasta volver a generarlo.
