> Corrida local contra la versión 36 con Daphne y Chrome (64 comprobaciones correctas, 2 manuales). El código de la aplicación no cambió en la v37. No se hizo contra AWS.

# Ensayo de la revisión · 07-11-2026 21:59

Dirección: `http://127.0.0.1:8765` · salud: `{"servicio": "ok", "base_de_datos": "ok", "cache": "ok", "version": "v36", "commit": "v36-ensayo", "entorno": "producción"}`

| Paso | Comprobación | Resultado | Detalle |
|---|---|---|---|
| 1 | /salud/ muestra servicio, base de datos, versión, commit y entorno de producción | Aprobada | versión v36, commit v36-ensayo, base ok, entorno producción |
| 1 | Una ruta inexistente responde 404 sin trazas (DEBUG=False) | Aprobada | 404 sin trazas ni configuración (DEBUG=False) |
| 1 | Los listados traen datos suficientes (≥ 50 en cada CRUD evaluado) | Aprobada | atenciones: 334, beneficiarios: 402, gestiones: 335, evidencias: 112 (Norte para las atenciones) |
| 1 | El detalle de una atención muestra sus relaciones | Aprobada | el detalle /actividades/98/ muestra beneficiario, funcionario, delegación y estado relacionados |
| 1 | El administrador A no es superusuario | Aprobada | admin_a no entra al panel /admin/ (no es superusuario) |
| 2 | Beneficiarios · administrador crea con modal | Aprobada | creado con el modal y visible en el listado |
| 2 | Beneficiarios · administrador edita con modal | Aprobada | editado con el modal; el listado muestra el dato nuevo |
| 2 | Beneficiarios · SweetAlert2 cancela sin cambios y confirma archivando (borrado lógico) | Aprobada | SweetAlert2: «! ¿Archivar registro? «ENSAYO CBFEAJ Beneficiaria (90215409-4)» deja d…»; cancelar no cambió nada; confirmar lo archivó y quedó en «Archivados» |
| 2 | Beneficiarios · restaurar un archivado | Aprobada | restaurado desde «Archivados» |
| 2 | Beneficiarios · el editor edita pero no ve archivar ni eliminar | Aprobada | el editor ve Ver y Editar, y ningún botón de archivar ni eliminar |
| 2 | Atenciones · el editor crea con modal | Aprobada | atención creada con el modal y visible en el listado |
| 2 | Atenciones · el editor edita | Aprobada | atención editada con el modal; el detalle muestra el cambio |
| 2 | Atenciones · el editor no ve archivar ni eliminar | Aprobada | el editor no ve archivar ni eliminar en Atenciones |
| 2 | Atenciones · el administrador archiva con SweetAlert2 (cancelar y confirmar) | Aprobada | cancelar no cambia nada; confirmar archiva (borrado lógico) y aparece entre los archivados |
| 3 | Beneficiarios · RUT inválido: aviso claro y el modal permite corregir | Aprobada | aviso «Revisa el formulario Corrige esto para continuar: RUT: Escri…» y el modal sigue abierto para corregir |
| 3 | Beneficiarios · el servidor rechaza datos inválidos sin guardar (sin pasar por el navegador) | Aprobada | el servidor rechazó: RUT con dígito verificador incorrecto; nombre con números; campos obligatorios vacíos; RUT que ya existe. No se escribió ningún registro |
| 3 | Perfil · un archivo que no es JPEG/PNG válido de hasta 2 MiB no se guarda | Aprobada | la foto guardada no cambió con: texto.png, animada.png, pesada.png, programa.exe (texto con extensión .png, GIF, PNG de más de 2 MiB y un ejecutable); se quitó la foto de prueba |
| 3 | Evidencias · un archivo no permitido se rechaza y no se escribe nada | Aprobada | 3 archivos no permitidos rechazados; las evidencias siguen en 112 |
| 4 | Búsqueda por al menos dos campos en ambos listados | Aprobada | Beneficiarios por nombre (7) y por RUT (1); Atenciones por contacto (8) e identificador (1) |
| 4 | Atenciones · filtro de negocio (estado) | Aprobada | filtro «Estado = En proceso»: 116 de 334, todas las filas con ese estado |
| 4 | Orden ascendente y descendente por al menos dos columnas en ambos listados | Aprobada | orden ascendente y descendente distinto en atencion:contact_name, atencion:date, beneficiarios:name, beneficiarios:rut |
| 4 | Paginación con tamaños 5, 15 y 30 | Aprobada | tamaños 5, 15 y 30 (30 filas) y página 2 distinta de la 1 |
| 4 | La preferencia (búsqueda, orden, tamaño y página) se conserva al volver | Aprobada | tras abrir un detalle y pasar por otro módulo, volvió a {'q': 'a', 'orden': 'date', 'dir': 'desc', 'page': '3'} |
| 4 | Cambiar la búsqueda vuelve a la página 1 | Aprobada | al cambiar la búsqueda vuelve a la página 1 |
| 4 | Parámetros inválidos y resultados vacíos controlados | Aprobada | parámetros inválidos ignorados (200, sin errores internos) y «sin resultados» con mensaje propio |
| 4 | Exportar a Excel el conjunto filtrado completo, con encabezados legibles y sin campos internos | Aprobada | Atenciones: 8 filas (todo el filtrado, no solo 5), encabezados ['Identificador', 'Fecha', 'Contacto', 'RUT']…; Beneficiarios: 7 filas (todo el filtrado, no solo 5), encabezados ['Nombre', 'RUT', 'Teléfono', 'Dirección']… |
| 4 | La exportación excluye los registros archivados | Aprobada | el Excel no incluye la atención archivada del paso 2 |
| 5 | Escribir la URL de crear o editar responde 403 con una página comprensible | Aprobada | 403 con la página del portal (sin trazas) en: /actividades/nuevo/, /beneficiarios/nuevo/, /actividades/98/editar/, /beneficiarios/403/editar/ |
| 5 | Peticiones POST directas de crear, editar, archivar y eliminar responden 403 sin cambios | Aprobada | 7 peticiones POST directas (con sesión y token CSRF) respondieron 403 y los conteos no cambiaron ({'atenciones': 334, 'beneficiarios': 403}) |
| 5 | El lector no ve botones de escritura | Aprobada | el lector no ve botones de crear, editar, archivar ni eliminar |
| 5 | El editor no puede archivar ni eliminar por petición directa | Aprobada | el editor tampoco puede archivar ni eliminar: 403 y sin cambios |
| 5 | Sin iniciar sesión, las vistas privadas redirigen al ingreso | Aprobada | sin sesión, las pantallas privadas llevan al ingreso y los POST no se aceptan |
| 6 | Abrir por id un objeto del ámbito B desde el A responde 404 | Aprobada | detalle y edición de una atención, evidencia y gestión de Sur responden 404 desde Norte (lector, editor y administrador); el archivo de la evidencia también |
| 6 | Editar o archivar por petición directa un objeto del ámbito B responde 404 sin cambios | Aprobada | editar y archivar objetos de Sur desde Norte responde 404 y Sur queda igual |
| 6 | Asignar una relación del ámbito B desde el A se rechaza sin cambios | Aprobada | asignar una atención de Sur a una evidencia o gestión de Norte se rechaza y ninguna tabla cambia |
| 6 | Forzar en el formulario un funcionario, territorio o delegación ajenos se rechaza | Aprobada | con el formulario manipulado (funcionario 56, territorio 56, delegación 2, fuera de las opciones de Norte) el servidor rechazó el guardado y el modal explicó el error |
| 6 | Los selectores de relaciones solo ofrecen opciones del ámbito propio | Aprobada | el selector de atenciones de Norte ofrece 335 opciones y ninguna de Sur |
| 6 | Listados y exportación solo traen el ámbito propio | Aprobada | Excel de A (335 atenciones, Norte) y de B (333, Sur) sin ninguna en común |
| 6 | La búsqueda no devuelve datos del otro ámbito | Aprobada | buscar desde Norte el identificador ATN00475, de una atención de Sur, no devuelve resultados (Sur sí la encuentra) |
| 7 | Los lectores abren la tabla con la conexión en vivo | Aprobada | los dos lectores muestran «En vivo» (WebSocket conectado) |
| 7 | Crear con el editor: la tabla del lector A cambia sin F5 | Aprobada | el lector A vio aparecer la atención nueva sin F5 y sin recargar la página |
| 7 | Editar con el editor: la tabla del lector A refleja el dato nuevo | Aprobada | el nombre editado por el editor A apareció en la tabla del lector A sin F5 |
| 7 | Si el registro deja de cumplir el filtro, deja de mostrarse | Aprobada | al dejar de coincidir con la búsqueda del lector A, la fila desapareció de su tabla sin F5 |
| 7 | Un guardado inválido no anuncia un cambio exitoso | Aprobada | un guardado inválido no emitió ningún evento al lector |
| 7 | El lector B no recibe datos ni eventos del ámbito A | Aprobada | el lector B tiene el WebSocket abierto y no recibió ningún mensaje durante los cambios de Norte (A recibió 3) |
| 7 | El servidor rechaza WebSocket anónimos y de orígenes no permitidos | Aprobada | sin sesión: 403; con sesión y origen propio: 101; con origen ajeno: 403 |
| 8 | Recuperación · la solicitud responde igual exista o no el correo | Aprobada | con un correo registrado y con uno inexistente la respuesta es la misma, y no repite el correo |
| 8 | Recuperación · el enlace del correo cambia la contraseña con los validadores de Django | Aprobada | el enlace del correo pide una contraseña nueva, rechaza una débil con los validadores de Django y al cambiarla vuelve al ingreso |
| 8 | Recuperación · la clave anterior deja de funcionar y el perfil exige la clave actual | Aprobada | la clave anterior ya no entra y la nueva sí; el perfil rechazó una clave actual equivocada y devolvió la cuenta a su clave original |
| 8 | Recuperación · un enlace usado o inválido se rechaza sin errores internos | Aprobada | el enlace ya usado y dos enlaces inventados responden 400 con un aviso comprensible, sin errores internos |
| 8 | Croppr · se recorta, se previsualiza y se guarda la zona elegida | Aprobada | Croppr cargado: se eligió una zona arrastrando el cuadro y el servidor guardó un cuadrado de 320×320 px y con la zona que se arrastró en el recorte; se quitó la foto de prueba |
| 8 | Portal · cada cliente ve solo lo suyo y se rechaza lo ajeno | Aprobada | cliente1 ve 24 atenciones y cliente2 24, sin ninguna en común; abrir la del otro responde 404 y los módulos de gestión responden 403 |
| 8 | Portal · un cliente no puede cambiar su ficha ni su rol manipulando campos | Aprobada | enviar campos de más (RUT, beneficiario, grupos, superusuario) no cambia la ficha ni da acceso a otros módulos |
| 9 | Ramas, Pull Requests y explicación del evento WebSocket | Revisión manual | se muestra en GitHub, no en la aplicación: ramas feature/…, un Pull Request por integrante con descripción y revisión de otro integrante, y la versión final integrada en main. El recorrido del evento WebSocket está en docs/ENSAYO_REVISION.md (paso 9). |
| 9 | El commit desplegado se puede comparar con main (/salud/) | Aprobada | el commit desplegado es v36-ensayo; compáralo con el último commit de main en GitHub |
| 10 | Menú de admin_a: cada enlace abre su pantalla con título, módulo activo y sin errores | Aprobada | 19 enlaces recorridos sin escribir ninguna URL |
| 10 | Menú de editor_a: cada enlace abre su pantalla con título, módulo activo y sin errores | Aprobada | 11 enlaces recorridos sin escribir ninguna URL |
| 10 | Menú de lector_a: cada enlace abre su pantalla con título, módulo activo y sin errores | Aprobada | 13 enlaces recorridos sin escribir ninguna URL |
| 10 | Menú de lector_b: cada enlace abre su pantalla con título, módulo activo y sin errores | Aprobada | 13 enlaces recorridos sin escribir ninguna URL |
| 10 | Menú de cliente1: cada enlace abre su pantalla con título, módulo activo y sin errores | Aprobada | 3 enlaces recorridos sin escribir ninguna URL |
| 10 | Menú de cliente2: cada enlace abre su pantalla con título, módulo activo y sin errores | Aprobada | 3 enlaces recorridos sin escribir ninguna URL |
| 10 | Teclado: salto al contenido y foco visible | Aprobada | el primer Tab ofrece «Saltar al contenido» y 45 Tab seguidos mostraron el foco visible en casi todos los elementos |
| 10 | Teclado: el modal se abre y se cierra sin ratón y el foco vuelve | Fallida | AssertionError: al cerrar el modal con Escape el foco no volvió al botón que lo abrió @ modal_con_teclado:1442 |
| 10 | Teclado: el aviso de SweetAlert2 se maneja sin ratón | Aprobada | el aviso de confirmación recibe el foco y Escape lo cancela sin cambios |
| 10 | Páginas 403 y 404 comprensibles y con el código HTTP correcto | Aprobada | páginas con el diseño del portal, código visible, sin trazas y con enlace para volver: 403 en /beneficiarios/nuevo/, 404 en /esta-pantalla-no-existe/, 403 en /atencion/ |
| 10 | Página 400 controlada (host no permitido) sin detalles técnicos | Aprobada | un encabezado Host no permitido responde 400 con la página del portal, sin el texto de la excepción |
| 10 | Página 500 controlada (prueba automática con DEBUG=False) | Revisión manual | el 500 solo se provoca de forma controlada en las pruebas automáticas con DEBUG=False: python manage.py test core.test_errores (comprueba código 500, página del portal y ausencia de trazas, SQL y configuración) |
