# Cambios de la v16

Parte de la v15 (escudo oficial y arreglo de una prueba). No toca las versiones anteriores.

## Qué cambió

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

## Cambios en la base de datos

Los aplica `python manage.py migrate` (lo corre `deploy/actualizar.sh`). Ningún dato se borra ni se cambia.

| Tabla | Cambio | Migración |
|---|---|---|
| `evidence_validation` | `reviewer_officer_id` admite vacío (revisión del Super Usuario) | evidence 0002 |
| `evidence_evidence` | `file_link` sigue siendo `varchar(255)`; ahora guarda la ruta del archivo subido | evidence 0003 |
| `accounts_userprofile` | columna nueva `photo varchar(255)` vacía por defecto | accounts 0005 |

El diagrama en inglés actualizado es `sql/sgr_v10_modelo_relacional_completo_en.sql`; el detalle de los cambios sobre la base del servidor, en `sql/sgr_v13_a_v16_alter.sql`.

## En el servidor

- Los archivos subidos se guardan en `/opt/sgr/app/media` (o en `MEDIA_ROOT` si se define en `/etc/sgr/sgr.env`). `actualizar.sh` crea la carpeta. No está en Git ni se pierde al actualizar: **respáldala junto con la base de datos**.
- Apache y nginx aceptan envíos de hasta 12 MB (antes 5 MB en Apache).
- Las evidencias que ya estaban cargadas (solo con un nombre de archivo escrito) siguen visibles: muestran el nombre y «el archivo no está en el sistema» hasta que alguien suba el archivo.
- Los archivos viejos no se borran al reemplazar una evidencia (queda el rastro); la foto anterior sí se borra al cambiarla.

## Decisiones que quedan para el equipo

1. ¿Coordinación puede editar todo en cualquier delegación o solo ver y administrar catálogos?
2. ¿Quién puede archivar o eliminar evidencias y atenciones (hoy: quien tenga el permiso *delete*)?
3. ¿Se cambia el rojo del sistema (`#920000`) por el del escudo oficial (`#990100`)?
4. ¿Se borra el archivo físico cuando una evidencia se archiva? (hoy se conserva).
