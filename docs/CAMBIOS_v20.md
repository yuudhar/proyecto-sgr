# Cambios de la v20 respecto de la v19

La v20 no cambia la base de datos: no hay migraciones nuevas ni tablas distintas.

## Identificador institucional del funcionario

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

## Búsqueda mientras se escribe

No cambia en esta versión: viene desde la v18. Los listados y la pantalla Atención filtran solos unos 0,35 segundos después de dejar de escribir y al cambiar un filtro. Si una pestaña sigue abierta de antes de actualizar el servidor, hay que recargarla (Ctrl+Shift+R) para que cargue el script.

## Despliegue

`deploy/actualizar.sh` ahora deja los archivos estáticos legibles para Apache después de `collectstatic`. Sin eso, los archivos que cambiaban en una actualización quedaban sin permiso de lectura para otros usuarios y el sitio se veía sin estilos.

## Verificación

- `python manage.py check` y `makemigrations --check`: sin cambios.
- Suite completa: 837 pruebas aprobadas (827 de la v19 más 10 nuevas). El registro `docs/pruebas/registro_pruebas_funcionales.csv` y `.xlsx` se generó de nuevo.
- Pruebas nuevas en `core/test_officer_id.py` (bloque por delegación, archivados, delegación nueva, identificador propio, choque de números, formulario de alta sin el campo, edición de solo lectura, búsqueda y ficha). Se ajustaron dos pruebas de `core/test_v16.py` y una de `core/test_rules.py` que escribían el identificador a mano.
