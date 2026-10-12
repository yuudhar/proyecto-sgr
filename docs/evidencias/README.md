# Evidencias de la entrega (A4) y guion de la demostración de roles

Esta carpeta junta lo necesario para la lista de verificación de la entrega. Las capturas que ya están en `capturas/` se tomaron con `tools/evidencias/capturar.py` sobre un servidor **local** con datos de demostración; para la entrega hay que **repetirlas sobre la URL de AWS** (ver el final de este archivo).

## Cómo se toman las capturas

```bash
pip install playwright && playwright install chromium        # en tu equipo, no en el servidor
python tools/evidencias/capturar.py --url https://<tu-url-aws>
```

El script entra con las cuentas de demostración, hace el recorrido, deja las capturas en `docs/evidencias/capturas/`, la matriz de menús por rol en `docs/evidencias/matriz_menus_por_rol.md` y el resultado de cada comprobación en `docs/pruebas/resultados/navegador.json` (alimenta la hoja «Navegador» del registro). En AWS con correo real, el paso del código de recuperación se hace a mano (ver evidencia 1).

## Lista de verificación

| N.º | Evidencia requerida | Dónde está | Qué mostrar |
|---|---|---|---|
| 1 | Login y flujo completo de recuperación | `capturas/EV1_*` | Ingreso correcto e incorrecto; solicitar código (mensaje genérico, también con un correo inexistente); código de seis casillas (incluido pegado); nueva contraseña con confirmación; la clave anterior ya no sirve. |
| 2 | Seis CRUD | `capturas/EV2_*` | Formulario y listado de Delegaciones, Roles (con matriz de permisos), Usuarios, Ítems y metas, Tipo de Atención y Sub Atención, con el registro nuevo en la tabla. |
| 3 | Ingreso de atención con dependencias y contexto | `capturas/EV3_*` | Pantalla de Atención; Tipo y Sub Atención dependientes; cancelar sin crear nada; confirmación con identificador; delegación del contexto. |
| 4 | Tabla, paginador, búsqueda y Exportar a Excel | `capturas/EV4_*` | Tabla con paginador y buscador; búsqueda parcial sin mayúsculas ni tildes; página 2; archivo `EV4_04_exportacion_delegaciones.xlsx`. |
| 5 | Normas gráficas; identificación de delegación, usuario y rol; alcance por perfil | `capturas/EV5_*` y `matriz_menus_por_rol.md` | Cada rol con su cabecera (delegación, usuario, perfil); 403 en una pantalla no autorizada; consulta sin botones de cambio; alcance de la Delegación Sur; selector de delegaciones. **Las normas gráficas oficiales siguen pendientes** (escudo y código de color oficiales; ver PEN-02). |
| 6 | Validaciones y SweetAlert2 | `capturas/EV6_*` | Validación de login vacío, de delegación y de ingreso de atención; confirmación de eliminar; bloqueo de un tipo con sub atenciones; confirmación del cambio de contraseña. |
| 7 | URL AWS, repositorio Git y versión inequívoca | **Por hacer** | Captura de la URL en el navegador, de `https://<url>/salud/` (muestra `version` y `commit`), de `git tag` / `git log -1` y de la página del repositorio con la etiqueta `v10`. Ver `docs/aws/DESPLIEGUE_AWS.md`. |
| 8 | Resultados de pruebas funcionales y de estrés, evidencias y correcciones | `docs/pruebas/` | `registro_pruebas_funcionales.xlsx` (hojas Resumen, Pruebas, Requisitos, Navegador, Estrés, Defectos, Pendientes), `estres/PLAN_ESTRES.md` y los resultados de `estres/`. La prueba de estrés definitiva debe correrse en AWS. |
| 9 | Resumen de funciones operativas, simuladas y pendientes | `README.md` (sección «Estado de cada módulo»), `docs/pruebas/…xlsx` (hoja Pendientes) | Tabla de estado por módulo. |

**Cuidado con los secretos:** antes de publicar o entregar capturas, comprueba que no aparezcan claves, `SECRET_KEY`, el contenido de `/etc/sgr/sgr.env` ni datos reales. Todas las cuentas y datos de demostración son ficticios.

## Guion de la demostración de roles y permisos

Dura unos 10 minutos. Todas las cuentas de demostración usan la contraseña `Hola123!` (cámbiala para la entrega si el sitio es público). La matriz completa, con lo que muestra el menú de cada cuenta, está en `matriz_menus_por_rol.md`.

**Idea que se debe dejar clara:** el sistema aplica los permisos en el servidor (no solo esconde botones), y cada persona ve únicamente los módulos, las opciones y las delegaciones de su perfil.

| Paso | Cuenta | Qué hacer | Qué se debe ver |
|---|---|---|---|
| 1 | `admin` (Super Usuario) | Entrar, mostrar la cabecera y el menú completo. Abrir Roles y permisos y mostrar la matriz de permisos por módulo. | «Todas las delegaciones»; todos los grupos del menú (Operación, Resultados, Administración); la matriz con un permiso por opción y módulo. |
| 2 | `admin` | Abrir Control de usuarios, mostrar que cada usuario tiene rol y funcionario (de ahí sale su delegación). Abrir Auditoría. | Usuarios con su perfil; registro de quién cambió qué. |
| 3 | `coordinacion1` (Coordinación) | Entrar. Mostrar el menú: ve los catálogos y la planificación (Cargos, Períodos, Metas, Tipos de Atención) pero no Control de usuarios, Roles ni Auditoría. | Menú reducido; Funcionarios y Territorios de las dos delegaciones. |
| 4 | `coordinacion1` | Intentar abrir `/usuarios/` escribiendo la dirección. | Página 403 («acceso prohibido»): el bloqueo es del servidor, no solo del menú. |
| 5 | `matias.cavieres` (Funcionario y Verificador, Delegación Norte) | Entrar. Mostrar «Delegación Norte» en la cabecera. Registrar una atención. | Solo datos de Norte; ingreso con Tipo y Sub Atención dependientes; confirmación con identificador. |
| 6 | `matias.quiroz` (Funcionario y Verificador, Delegación Sur) | Entrar y mostrar el listado de actividades y atenciones. | Solo datos de la Delegación Sur: no aparece lo que registró `matias.cavieres` (alcance por delegación). |
| 7 | `jefatura1` / `supervision1` (Jefatura) | Entrar con `supervision1` y usar el selector de delegaciones de la franja de arriba. Mostrar Tablero de delegación e Informes. | `supervision1` tiene autorizadas Norte y Sur y puede alternar entre ellas; `jefatura1` solo Norte. Ambos ven indicadores e informes. |
| 8 | `consulta1` (Consulta, solo lectura) | Entrar, abrir Actividades y mostrar que no hay Nuevo, Editar ni Archivar. Intentar abrir `/delegaciones/` escribiendo la dirección. | Sin botones de cambio; 403 en pantallas no autorizadas. |
| 9 | `admin` | Cerrar sesión e intentar abrir `/dashboard/` sin sesión. | Redirección al ingreso: sin sesión no se ve nada. |

Respaldo automático de este guion: las pruebas `RoleTests`, `SweepTests`, `SidebarTests`, `RoleMatrixTests` y `ReviewScopeTests` (todas las pantallas por rol) y las capturas `EV5_*`.
