# Cambios de la v21 respecto de la v20

La v21 no cambia ninguna tabla ni columna. Trae una migración nueva (`accounts 0006`), pero solo cambia el tipo de campo de la foto en Django; la columna sigue siendo `varchar(255)`.

Se ajusta el proyecto a lo visto en clases: **Clase 9** (archivos e imágenes con `FileField`, `ImageField` y `MEDIA`) y **Clase 10** (buscador, filtros, ordenamiento y paginación).

## Filas por página: 5, 15 y 30 (Clase 10)

| Antes | Ahora |
|---|---|
| Opciones 10, 20 y 50; por defecto 20 | Opciones 5, 15 y 30; por defecto 15 |

- Cambia en `PAGE_SIZES` y `PAGE_SIZE` de `core/crud.py`. Todos los listados y la pantalla Atención usan esos valores.
- La elección sigue guardándose en `request.session` y sigue validándose contra la lista permitida, así que se mantiene al refrescar y al cambiar de página. Un valor que no esté en la lista (por ejemplo 10, 20 o 50, que antes eran válidos) se rechaza.
- El buscador, los filtros, el orden y la paginación no cambian: ya conservaban el alcance por delegación y los parámetros de la URL.

## Foto de perfil con `ImageField` (Clase 9)

| Antes | Ahora |
|---|---|
| `UserProfile.photo` era un `FileField`; solo se revisaba que el archivo empezara con la firma de un PNG o JPG | `UserProfile.photo` es un `ImageField`; Pillow comprueba además que sea una imagen real |

- Hay una dependencia nueva: `pillow==12.3.0` en `requirements.txt`. En el servidor, `actualizar.sh` la instala junto con las demás (`pip install -r requirements.txt`).
- El formulario `ProfilePhotoForm` usa `forms.ImageField`, con mensaje en español para el archivo dañado. Se mantiene `check_upload` (extensión, tamaño de 2 MB, archivo vacío y firma del contenido).
- Las evidencias siguen siendo `FileField`, porque aceptan PDF, Word y Excel además de imágenes.
- Las fotos ya guardadas siguen funcionando: no se mueve ni se renombra ningún archivo.

## Política de archivos reemplazados y huérfanos (Clase 9)

Queda documentada en el README, sección «Archivos subidos: límites y política»: límites y tipos aceptados, cómo se entregan los archivos y qué pasa con cada uno al reemplazar, quitar, archivar o quedar sin registro. El comportamiento no cambia: la foto anterior se borra y los archivos de evidencia se conservan.

## Verificación

- Pruebas ajustadas: `PageSizeTests` (`core/test_access_flow.py`), `NoticeMarkupTests` (`core/test_flash.py`), `PagerTests` (`core/test_search.py`) y `ProfilePhotoTests` (`core/test_v16.py`, que ahora sube imágenes reales hechas con Pillow).
- Pruebas nuevas: `test_the_chosen_size_survives_a_refresh` y `test_the_photo_is_an_image_field_and_a_file_with_only_the_signature_is_rejected`, con su descripción en `core/qa/`.
- Después de actualizar: `pip install -r requirements.txt`, `python manage.py migrate` y `python manage.py check`.
- El registro `docs/pruebas/registro_pruebas_funcionales.csv` y `.xlsx` y los resultados de `docs/pruebas/resultados/` siguen siendo los de la v20 hasta volver a correr la suite y regenerarlos (ver «Registro de pruebas» en el README).
