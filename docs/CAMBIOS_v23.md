# Cambios de la v23 respecto de la v22

La v23 no cambia ninguna tabla ni columna, y no trae migraciones nuevas: usa el campo `deleted_at` que ya tenía `UserProfile`.

## Eliminar usuarios: «Usuarios eliminados»

Hasta la v22 un usuario solo se podía **desactivar** (casilla «Activo» en Editar); seguía mezclado en el listado y no había forma de «borrarlo».

Desde la v23, en **Control de usuarios** cada fila (y la ficha del usuario) tiene el botón **Eliminar**:

- El usuario **no se borra de la base** (su historial, sus actividades y la auditoría quedan intactos). Pasa a estar *eliminado*: se marca con fecha en `UserProfile.deleted_at`, la cuenta queda **inactiva** y ya no puede ingresar.
- Sale del listado normal y aparece en **«Usuarios eliminados»** (enlace sobre la tabla, o `usuarios/?archivados=solo`). Esa vista tiene buscador, filtros, paginación y exportación a Excel como el resto.
- Desde ahí se puede **Restaurar**. El usuario vuelve al listado, pero **sigue inactivo**: hay que activarlo en Editar cuando deba volver a ingresar.
- Un usuario eliminado no se puede editar (la ficha lo indica con la fecha).
- Queda en la auditoría («Registro archivado» / «Registro restaurado»).
- La confirmación usa SweetAlert2, como los demás mantenedores; si no se puede (por ejemplo, tu propia cuenta) avisa el motivo.

## Solo el Super Usuario

Eliminar, ver los eliminados y restaurar **solo lo puede hacer el Super Usuario**, aunque otro perfil tenga el permiso de eliminar usuarios:

- Para los demás no aparecen los botones «Eliminar» ni el enlace «Usuarios eliminados».
- En el servidor, intentar eliminar da 403; los usuarios eliminados responden 404 (ni siquiera existen para ellos), con cualquier combinación de filtros.
- Nadie puede eliminar **su propia cuenta**.

## Detalles a tener en cuenta

- El nombre de usuario y el correo de un usuario eliminado siguen ocupados: crear otro con el mismo nombre dará el aviso de «ya existe». Hay que restaurar al eliminado.
- El funcionario asociado queda reservado a ese usuario (un funcionario solo puede tener una cuenta) hasta que se restaure.

## Dónde está en el código

- `core/crud.py`: el motor ahora admite que la marca de «archivado» viva en otra tabla (`archive_lookup`, `archived_at()`, `set_archived()`), un permiso extra por usuario (`archive_guard()`, `can_see_archived()`) y la vista «solo archivados» (`?archivados=solo`). Los demás mantenedores no cambian.
- `core/registry.py`, `UserCrud`: `archive_lookup = "profile__deleted_at"`, exige `is_superuser`, desactiva la cuenta al eliminar y oculta los eliminados a quien no es Super Usuario.
- `core/templates/core/crud/list.html`, `detail.html`, `archive_confirm.html`: textos de «Usuarios eliminados».
- Pruebas: `core/test_v23.py` (`DeletedUsersTests`, `OnlySuperuserDeletesUsersTests`), registradas en `core/qa/`.
