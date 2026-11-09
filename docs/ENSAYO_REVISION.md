# Ensayo de la revisión (v37)

Guía para ensayar, antes de la defensa, los diez pasos de la revisión de la Evaluación Sumativa III con las seis cuentas de prueba y los datos que deja `cargar_datos_revision`. El ensayo se hace en tres capas, de la más rápida a la más real:

| Capa | Qué es | Cuándo |
|---|---|---|
| Pruebas automáticas | `python manage.py test core.test_ensayo_revision`: una clase por paso, sin navegador, sobre los mismos datos de la revisión | En cada versión y antes de cada Pull Request |
| Herramienta con navegador | `tools/ensayo/ensayo_revision.py`: abre Chrome de verdad, una sesión por cuenta, y recorre los diez pasos contra una dirección (local o AWS) | Una vez que el servidor de AWS está actualizado y con los datos cargados |
| Paso a paso a mano | Esta guía: qué cuenta usar, qué mostrar y qué resultado esperar en cada paso | El día de la revisión, o para practicar la exposición |

Las contraseñas **no están en ningún archivo**: las cuentas se crearon con la contraseña que diste a `cargar_datos_revision` y la herramienta la lee de `SGR_REVISION_PASSWORD`.

## Cuentas

| Cuenta | Perfil | Ámbito |
|---|---|---|
| `admin_a` | Administrador (no es superusuario) | Delegación Norte (organización A) |
| `editor_a` | Editor: crea y edita, no archiva ni elimina | Delegación Norte |
| `lector_a` | Solo consulta y exporta | Delegación Norte |
| `lector_b` | Solo consulta y exporta | Delegación Sur (organización B) |
| `cliente1` | Cliente: portal con sus propios datos | Su ficha de beneficiario |
| `cliente2` | Cliente: portal con sus propios datos | Su ficha de beneficiario |

Los dos CRUD que se muestran son **Atención** (`actividades`) y **Beneficiarios**. Atención aísla por delegación; Beneficiarios es un catálogo común (ver «Qué falta» al final).

## Cómo correr la herramienta con navegador

En tu computador (o en el servidor, si tiene Chrome), con Playwright instalado (`pip install playwright && playwright install chromium`):

```bash
read -rs -p "Contraseña de las cuentas de prueba: " SGR_REVISION_PASSWORD; export SGR_REVISION_PASSWORD
python tools/ensayo/ensayo_revision.py --url https://<ip-o-dominio> --informe ensayo.md --capturas capturas
unset SGR_REVISION_PASSWORD
```

- `--pasos 1,2` corre solo algunos pasos; `--chromium <ruta>` usa un Chrome ya instalado; `--sin-verificar-tls` acepta un certificado que el navegador no reconoce (por ejemplo el de ensayo de Let's Encrypt); `--depurar` agrega la línea de código a cada fallo.
- Si una cuenta tiene otra contraseña, defínela con `SGR_PASSWORD_<ALIAS>` (por ejemplo `SGR_PASSWORD_LECTOR_B`); esa reemplaza a `SGR_REVISION_PASSWORD` solo para esa cuenta.
- El resultado de cada comprobación sale como `OK`, `FALLÓ` o `MANUAL`, y el código de salida es 1 si algo falló.
- **Deja rastro, marcado:** crea registros cuyo nombre dice «ENSAYO» y los archiva al terminar. Quedan unas pocas atenciones y beneficiarios archivados con esa marca; no aparecen en los listados normales y se pueden dejar. Los datos de la revisión no se tocan.
- **Recuperación de contraseña:** el paso 8 pide enlaces de recuperación y la aplicación limita a 5 por hora (se cuentan en el registro de auditoría). Si repites el ensayo varias veces seguidas, espera una hora entre corridas o el paso 8 se detiene por ese límite, que es el comportamiento correcto. El paso 8 devuelve la contraseña de `lector_b` a la original.
- **Correo:** `--bandeja <carpeta>` solo sirve cuando el servidor escribe los correos en archivos (EMAIL_BACKEND de archivos, como en el ensayo local). En AWS el correo es real: la herramienta pide el enlace y deja como `MANUAL` el abrir la bandeja, que haces tú con la casilla de `lector_b`.
- Los pasos 9 y 10 incluyen puntos que no se pueden hacer desde el navegador (ramas y Pull Requests, página 500): quedan como `MANUAL` y están explicados más abajo.

## Los diez pasos

### Paso 1 — La aplicación abre y tiene datos

- **Cuenta:** `admin_a` (y anónimo para `/salud/`).
- **Qué mostrar:** abre `/salud/` y muestra servicio, base de datos, caché, versión, commit y entorno; entra con `admin_a`, abre Atención y Beneficiarios y muestra el total de registros; abre el detalle de una atención con su beneficiario, funcionario y delegación; intenta `/admin/` y muestra que no hay acceso. Una dirección inexistente muestra la página 404 sin rastros técnicos.
- **Resultado esperado:** `/salud/` responde 200 con `entorno` «producción» cuando `DEBUG` está apagado; el commit aparece cuando el servidor se actualizó con `deploy/actualizar.sh` (si dice «sin definir», actualiza con el script); cada CRUD evaluado tiene más de 50 registros y cada atención tiene sus relaciones.
- **Pruebas:** `EnsayoPaso1AplicacionYDatosTests`.

### Paso 2 — CRUD con modal y borrado lógico

- **Cuentas:** `admin_a` y `editor_a`.
- **Qué mostrar:** con `admin_a`, crea un beneficiario en el modal, edítalo, archívalo con la confirmación de SweetAlert (primero cancela y luego confirma), míralo en «Archivados» y restáuralo. Con `editor_a`, crea y edita una atención y muestra que no tiene botones de archivar ni eliminar. De vuelta con `admin_a`, archiva una atención.
- **Resultado esperado:** el modal se cierra al guardar y la lista se actualiza; cancelar no cambia nada; archivar no borra de la base (borrado lógico) y restaurar devuelve el registro; el editor no ve esas acciones.
- **Pruebas:** `EnsayoPaso2CrudConModalYBorradoLogicoTests`.

### Paso 3 — Datos inválidos y archivos

- **Cuentas:** `admin_a` y `editor_a`.
- **Qué mostrar:** en el modal de Beneficiarios, un RUT con dígito verificador incorrecto, un nombre con números, campos vacíos y un RUT repetido; en Atención, al menos tres reglas de negocio (sub atención de otro tipo, RUT de solicitante no registrado, teléfono inválido). En el perfil, una imagen PNG válida y luego un texto con extensión `.png`, una imagen animada, una imagen de más de 2 MB y un `.exe`. En Evidencias, un `.exe`, un falso PDF y un `.html`.
- **Resultado esperado:** cada intento muestra su mensaje junto al campo, el modal sigue abierto, no se guarda nada y la foto anterior se conserva.
- **Pruebas:** `EnsayoPaso3DatosInvalidosYArchivosTests`.

### Paso 4 — Listados, filtros, orden, paginación y Excel

- **Cuenta:** `lector_a`.
- **Qué mostrar:** en Atención y en Beneficiarios, buscar por dos campos distintos (identificador y nombre), filtrar por estado, ordenar por dos columnas en ambos sentidos, cambiar el tamaño de página (5, 15 y 30), salir y volver para ver restaurada la preferencia, y exportar a Excel con un filtro puesto.
- **Resultado esperado:** al cambiar la búsqueda se vuelve a la página 1; un parámetro inválido en la dirección (`page=abc`, `filas=999`, un orden inventado) no rompe nada; el orden por defecto es el más reciente primero; el Excel trae todo el conjunto filtrado (no solo la página), sin archivados y sin columnas internas.
- **Pruebas:** `EnsayoPaso4ListadosYExcelTests`.

### Paso 5 — El lector no puede escribir

- **Cuentas:** `lector_a` y `editor_a`.
- **Qué mostrar:** con `lector_a` no hay botones de crear, editar, archivar ni eliminar; escribir la dirección de «Nueva atención» o «Nuevo beneficiario» a mano da la página 403; un envío directo tampoco cambia nada. Con `editor_a`, intenta archivar por petición directa. Sin sesión, las pantallas privadas llevan al ingreso.
- **Resultado esperado:** 403 comprensible y sin datos técnicos, y los registros intactos.
- **Pruebas:** `EnsayoPaso5LectorSinPermisosTests`.

### Paso 6 — Aislamiento entre organizaciones

- **Cuentas:** `lector_a`, `editor_a`, `admin_a` (organización A) y `lector_b` (organización B).
- **Qué mostrar:** el lector B abre una atención de su ámbito y copia su dirección; el A la abre y recibe 404. Lo mismo con evidencias y gestiones, con editar y archivar, y con el Excel. Una evidencia o una gestión de una atención ajena se rechaza; un formulario manipulado con un funcionario, territorio o delegación ajenos no se guarda. Los selectores solo ofrecen datos propios y buscar por un código de la otra organización no devuelve nada.
- **Resultado esperado:** 404 (no 403, para no confirmar que existe), sin cambios, y los conjuntos de cada organización no se cruzan en ningún listado ni exportación.
- **Pruebas:** `EnsayoPaso6AislamientoTests`.

### Paso 7 — Cambios en vivo por WebSocket

- **Cuentas:** `editor_a` (edita), `lector_a` (mira) y `lector_b` (no debe recibir nada). Abre dos navegadores o dos ventanas privadas.
- **Qué mostrar:** con la lista de Atención abierta con `lector_a`, edita una atención con `editor_a` y muestra que la fila cambia sin recargar; crea una y muestra que aparece; cambia una para que salga del filtro y muestra que desaparece. Un guardado inválido no mueve nada. En el navegador (herramientas del desarrollador, Network, WS) se ve la conexión con estado 101. El lector B no recibe nada.
- **Recorrido del evento** (para explicarlo): el formulario guarda en `core/crud.py` y llama a `notify_crud_change`; `websocket/services.py` registra el aviso con `transaction.on_commit` (si la transacción se deshace, no se avisa) y lo publica con `publish_crud_changed` al grupo de la delegación; `websocket/consumers.py` (`CrudChangesConsumer`) lo entrega a las conexiones de ese grupo, que `websocket/routing.py` recibe en `ws/crud/<slug>/`; la conexión pasa antes por `sgr_project/asgi.py` (`AllowedHostsOriginValidator` y `AuthMiddlewareStack`, que rechazan orígenes ajenos y anónimos); el aviso no lleva datos, y `core/static/core/js/live-updates.js` vuelve a pedir la misma pantalla por HTTP con la cabecera `X-Live-Refresh`, así que permisos, delegación, filtros y paginación se aplican igual que en una carga normal.
- **Resultado esperado:** el lector A se actualiza solo; el B y quien tenga un origen ajeno o no haya iniciado sesión, nada.
- **Pruebas:** `EnsayoPaso7WebSocketTests`.

### Paso 8 — Recuperación de contraseña, recorte de foto y clientes

- **Cuentas:** `lector_b` (recuperación), `editor_a` (foto), `cliente1` y `cliente2`.
- **Qué mostrar:** pedir el enlace con el correo de una cuenta y con uno inexistente (misma respuesta); abrir el enlace del correo; probar una contraseña débil (el navegador y el servidor la rechazan); poner una nueva; volver a abrir el mismo enlace (ya no sirve); entrar con la nueva y comprobar que la anterior falla. En el perfil, recortar la foto arrastrando el recuadro de Croppr y mostrar que se guarda cuadrada y de hasta 512 píxeles; quitar la foto. Los clientes: cada uno ve solo sus atenciones y, si se manipula el envío del perfil (RUT, beneficiario, grupos, superusuario), la ficha no cambia ni se abre otro módulo.
- **Resultado esperado:** los enlaces inventados o ya usados dan 400 sin errores internos; la foto queda cuadrada; el portal del cliente 1 nunca muestra datos del cliente 2.
- **Pruebas:** `EnsayoPaso8RecuperacionCropprYClientesTests`.

### Paso 9 — Ramas, Pull Requests y commit

- **Cuenta:** ninguna; se muestra en GitHub y en el servidor.
- **Qué mostrar:** el trabajo está en ramas `feature/…` y no en `main`; cada una entra a `main` con su Pull Request, con la descripción de qué cambia y cómo se probó; el commit que corre en el servidor aparece en `/salud/` (lo escribe `deploy/actualizar.sh` con `git describe`). Para el evento en vivo, el recorrido del paso 7 en el código.
- **Resultado esperado:** el commit de `/salud/` coincide con el último de la rama o etiqueta desplegada.
- **Pruebas:** `EnsayoPaso9RamasYEventoTests` (revisa que los archivos nombrados en esta guía existan y tengan lo descrito) y la prueba del commit en el paso 1. La parte de GitHub es manual.

### Paso 10 — Navegación, teclado y errores

- **Cuentas:** las seis.
- **Qué mostrar:** recorrer el menú de cada cuenta: cada enlace abre con su título, el módulo activo marcado y un único `h1`. Teclado: el enlace «Saltar al contenido», el foco visible, abrir un modal con Enter, cerrarlo con Escape y ver que el foco vuelve al botón que lo abrió, y manejar un diálogo de SweetAlert con el teclado. Las páginas 403 y 404 y la 400 (se obtiene con la cabecera `Host` de un sitio ajeno). La 500 no se puede provocar sin tocar el código; está comprobada en `core.test_errores` y en `EnsayoPaso10NavegacionYErroresTests`.
- **Resultado esperado:** ninguna pantalla del menú falla; los errores muestran una página comprensible, con un enlace para volver, sin trazas, rutas internas ni consultas SQL.
- **Pruebas:** `EnsayoPaso10NavegacionYErroresTests`.

## Cómo repetir el ensayo en AWS

1. En el servidor: `cd /opt/sgr/app && sudo bash deploy/actualizar.sh <rama-o-etiqueta>` y, si la base es nueva, `cargar_datos_revision` (ver `docs/aws/DESPLIEGUE_AL2023.md`).
2. Comprueba `/salud/`: versión, commit y entorno «producción».
3. Corre la herramienta contra la dirección pública (arriba) y revisa el informe: todo `OK`, salvo los `MANUAL`.
4. Haz a mano lo manual: el correo real de la recuperación, las ramas y el Pull Request.
5. Corre las pruebas automáticas (`core.test_ensayo_revision`) antes de cerrar la rama.

## Ramas y Pull Requests

```bash
git checkout -b feature/v37-ensayo-revision
git add -A && git commit -m "v37: ensayo de la revisión"
git push -u origin feature/v37-ensayo-revision
```

Abre el Pull Request hacia `main` en GitHub, describe qué cambia y cómo se probó, y recién después de la revisión de tu compañero se hace el merge. Cada versión va en su propia rama.

## Qué falta (para decidir con el equipo)

- **Dos CRUD evaluados:** hoy son Atención y Beneficiarios. Beneficiarios no tiene un filtro de negocio (solo búsqueda y orden) ni aislamiento por delegación. Si la pauta exige filtro y aislamiento en ambos, conviene cambiar Beneficiarios por **Agenda colectiva** o agregarle un filtro y un ámbito (se define en `CRUDS_EVALUADOS` de `cargar_datos_revision`).
- En la lista de Atención el botón que archiva se llama «Eliminar», pero archiva (borrado lógico) y la confirmación de SweetAlert pregunta «¿Archivar registro?». Conviene que el texto del botón diga «Archivar» para no confundir en la revisión.
- MariaDB: la carga de datos se probó con SQLite; ejecútala dos veces en AWS para comprobar que no duplica.
