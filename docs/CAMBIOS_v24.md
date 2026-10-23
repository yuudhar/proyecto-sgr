# Cambios de la v24 respecto de la v23

La v24 aplica la **Clase 11 (Tiempo real en Django: Channels, WebSocket y Daphne)**. No cambia ninguna tabla ni columna y no trae migraciones.

La clase 11 usa un chat como ejercicio para entender WebSocket; **en el SGR no se incluye el chat**: la idea aplicada es que lo que cambia una persona se vea en la pantalla abierta de otra, sin F5.

La clase habla de una «organización»; en el SGR esa organización es la **delegación**.

## Qué se agregó

1. **Listados en vivo** (el laboratorio de la clase). Si otra persona crea, edita, archiva, restaura o elimina un registro, tu listado se actualiza solo, sin F5, **conservando tu búsqueda, filtros, orden y página**. Aparece un indicador «En vivo» junto al total de resultados y un aviso «Listado actualizado». Funciona en todos los mantenedores, porque está en el motor (`core/crud.py`). La vista «Usuarios eliminados» no se actualiza en vivo.
2. **Dashboard y pantallas de resumen en vivo**. Si la persona A hace un cambio y la persona B tiene abierto el **Dashboard**, el **Tablero de delegación** o **Validar evidencias** en la misma delegación, la pantalla de B se actualiza sola, sin F5: cambian los contadores de pendientes, las últimas actividades, los próximos compromisos y el semáforo de metas. Aparece el indicador «En vivo» y un aviso «Pantalla actualizada». Quien ve «Todas las delegaciones» recibe los cambios de todas; el dashboard de otra delegación no se entera. Recargar la pantalla en vivo no suma una visita al contador del inicio.
3. **Foto de perfil de otra persona (Super Usuario).** En **Control de usuarios**, la ficha del usuario muestra su foto («Sin dato» si no tiene) y el formulario **Editar** (y **Nuevo**) permite subir o reemplazar la foto, o marcar **Quitar la foto actual**. Valen las mismas reglas que en Mi perfil: PNG o JPG de hasta 2 MB, con el contenido verificado. La foto anterior se borra al confirmar el guardado, y queda en la auditoría quién la cambió o quitó y a quién. Cada persona sigue cambiando la suya desde Mi perfil. Como las pantallas de usuarios son solo del Super Usuario, nadie más puede tocar la foto de otra persona. Código: `core/photos.py`, `UserForm` (`core/forms.py`) y `UserCrud.save_photo` (`core/registry.py`).
4. **Daphne** reemplaza a gunicorn como servidor (ASGI), también en el servidor de AWS.

### Qué cambios actualizan esas pantallas

Atenciones, gestiones de seguimiento, compromisos, evidencias, validaciones, metas, indicadores, ajustes, períodos y funcionarios: cuando se **guardan, archivan, restauran o eliminan**, sea desde el mantenedor, desde la pantalla de validar, desde el cálculo de indicadores o desde el Django Admin. Se detectan con señales de Django (`post_save` / `post_delete`, en `websocket/signals.py`) y el aviso se publica **después del commit** (`transaction.on_commit`): si el guardado se deshace, nadie recibe nada. Si un registro cambia de delegación, se avisa a la anterior y a la nueva. Un dato general (por ejemplo el período) avisa a todas las delegaciones. Los cambios masivos que no pasan por `save()` ni `delete()` (`QuerySet.update`) y los hechos desde otro proceso (`manage.py shell`, comandos) no se avisan.

## Cómo funciona (el recorrido de la clase)

| Paso | Listado en vivo |
|---|---|
| 1. Navegador A | guarda el formulario del mantenedor (POST con CSRF) |
| 2. Vista Django | valida y guarda dentro de una transacción |
| 3. Servicio | `notify_crud_change` registra el aviso con `transaction.on_commit`: **solo se publica si el guardado se confirmó** |
| 4. Consumer | `CrudChangesConsumer` entrega `{"type": "crud_changed"}` a cada conexión del grupo |
| 5. Navegador B | `live-updates.js` pide **por HTTP** la tabla actual (misma URL, mismos filtros) y reemplaza la región de resultados |

Para el dashboard, el tablero y validar el recorrido es el mismo, con dos diferencias: el aviso lo publica una **señal** de Django (`websocket/signals.py`) en vez del motor de mantenedores, y lo entrega `LiveConsumer` (`ws/live/`) como `{"type": "live_changed", "model": "operations.activity"}`. Al recibirlo, `live-updates.js` pide por HTTP la **misma pantalla** (con `X-Requested-With: fetch`) y reemplaza la región `[data-live-region]`; el servidor vuelve a aplicar permisos y delegación.

Por qué el listado vuelve a pedir la tabla por HTTP en vez de recibirla por el socket: así se vuelven a aplicar permisos, delegación, filtros y paginación en el servidor, y por el WebSocket no viaja ningún dato del registro.

## Seguridad

- `AllowedHostsOriginValidator` (usa `ALLOWED_HOSTS`): una conexión desde otro origen es rechazada.
- `AuthMiddlewareStack`: el usuario sale de la sesión; un usuario anónimo no puede escuchar ningún aviso.
- Cada delegación escucha solo su grupo (`crud_<modulo>_d<id>`, `live_d<id>`, `live_all`); el formulario no elige autor ni delegación.
- Para escuchar los cambios de un mantenedor hace falta el permiso de **ver** ese mantenedor.
- `ws/live/` solo exige sesión, pero **no envía ningún dato**: solo avisa que algo cambió. Lo que B ve lo entrega la pantalla por HTTP, que aplica sus permisos y su delegación; un aviso de más solo provoca una nueva consulta.
- Los mensajes entran solo por HTTP (con CSRF); lo que el navegador escriba en el socket se ignora.

## Dónde está en el código

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

## Para correrlo en el computador

```
python -m pip install -r requirements.txt        # ahora incluye channels y daphne
python manage.py check
python manage.py runserver --noreload            # debe decir: Starting ASGI/Daphne ... development server
```

Prueba: inicia sesión con dos usuarios de la misma delegación (un navegador normal y una ventana privada) y abre en las dos el **Dashboard**; mira en Network → WS el `101 Switching Protocols`. En una, edita una atención: la otra cambia sola, sin F5. Lo mismo ocurre en cualquier mantenedor abierto en las dos ventanas. Usa **un solo servidor** (la capa de canales es de memoria: dos procesos no se hablan entre sí).

## En el servidor de AWS

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

## Límites a tener en cuenta

- La capa de canales es **en memoria**: sirve con un solo proceso (lo que usa el servidor). Con varios procesos habría que usar `channels_redis`.
- Django atiende las vistas síncronas por ASGI en un solo hilo por proceso: para el uso de este sistema alcanza, pero es más lento que varios hilos de gunicorn si hay mucha gente a la vez.
- Cada cambio de datos en esos modelos genera una consulta nueva de la pantalla en los navegadores que la tienen abierta (con una pausa de 0,3 s para juntar varios avisos seguidos). Con mucha gente trabajando a la vez en la misma delegación, el dashboard se recarga seguido.
- Daphne por sí solo no sirve los archivos estáticos (`/static/`): en local los sirve `runserver`; en el servidor, Apache.

## Para la defensa (preguntas de la clase)

- **¿Por qué responder al fetch de A no actualiza la pantalla de B?** Porque la respuesta HTTP va solo a quien hizo el POST. B se entera por su WebSocket, que el servidor mantiene abierto.
- **¿Diferencia entre `type` del evento y `payload.type`?** El primero (`type` del evento del grupo) es el nombre del método del Consumer que se ejecuta (`crud_event` o `live_event`); el segundo va dentro de lo que se envía al navegador (`crud_changed`, `live_changed`) y lo usa JavaScript para saber qué hacer.
- **¿Qué se cambia para aplicar el recorrido a otro módulo?** Un nombre de grupo propio, un evento y un servicio que publique; en el CRUD, avisar con `transaction.on_commit` después de guardar y que JavaScript vuelva a pedir la tabla.
- **¿Cómo se entera B de lo que hizo A en el dashboard?** A guarda (POST); una señal de Django registra el aviso con `transaction.on_commit`; tras el commit el servicio hace `group_send` al grupo `live_d<delegación>`; el `LiveConsumer` de B envía `live_changed` por su WebSocket; `live-updates.js` pide por HTTP el dashboard otra vez y reemplaza la región; el servidor lo recalcula con los permisos y la delegación de B.
- **¿Por qué una señal y no solo el mantenedor?** Porque el dashboard cambia también con acciones que no pasan por el motor de mantenedores (validar una evidencia, calcular un indicador, el Django Admin). La señal las cubre todas con un solo punto.
