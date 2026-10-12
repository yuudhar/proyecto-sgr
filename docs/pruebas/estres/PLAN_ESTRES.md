# Plan de pruebas de estrés · SGR

Este plan se definió **antes** de ejecutar las pruebas (carga y umbrales fijados de antemano, como pide el requisito A3). Lo que se midió después está en los archivos `estres_<fecha>.*` de esta carpeta y en la hoja «Estrés» del registro de pruebas.

## 1. Objetivo

Saber cuántos usuarios simultáneos aguanta el sistema desplegado en AWS con un tiempo de respuesta aceptable, qué operación se degrada primero y si el sistema se recupera al terminar la carga.

## 2. Qué se prueba

Cada «usuario virtual» ingresa una vez (login con CSRF, como un navegador) y después repite, sin pausa, una mezcla de operaciones que representa el uso real. Las proporciones son fijas y están en `tools/estres/estres.py` (lista `ESCENARIO`).

| Operación | Peso | Tipo |
|---|---:|---|
| Dashboard | 20 | lectura |
| Atención: últimas | 15 | lectura |
| Atención: búsqueda | 15 | lectura |
| Listado de atenciones | 15 | lectura |
| Listado con búsqueda y página 2 | 10 | lectura |
| Listado de funcionarios | 4 | lectura |
| Listado de territorios | 4 | lectura |
| Mi perfil | 5 | lectura |
| Exportar atenciones a Excel | 4 | exportación |
| Registrar atención (con `--escritura`) | 10 | escritura |

## 3. Carga

- **Datos:** `python manage.py cargar_volumen_estres` deja un volumen realista (unas 5.000 atenciones y 1.000 beneficiarios, marcados como carga de prueba). Se retira con `--limpiar`.
- **Concurrencia creciente (etapas):** 1, 5, 10, 20, 40, 60 y 80 usuarios simultáneos.
- **Duración por etapa:** 60 s en AWS (20 s en el ensayo local).
- **Recuperación:** al final, una etapa de 1 usuario para comprobar que el sistema vuelve a responder como al comienzo.
- **Cuenta usada:** un Funcionario de la delegación Norte (perfil que más usará el sistema). La variante `--perfil admin` mide además los listados globales.

## 4. Umbrales de aceptación (fijados antes de probar)

| Métrica | Umbral | Razón |
|---|---|---|
| Latencia p95 por etapa | ≤ 1.500 ms | El 95 % de las pantallas responde en menos de 1,5 s: un uso fluido para atención de público. |
| Errores (5xx, 4xx inesperados, tiempos agotados) | ≤ 1,0 % | Un error de cada cien solicitudes es lo máximo tolerable. |
| Recuperación | p95 de la etapa final ≤ 1.500 ms y 0 errores | El sistema no queda dañado tras la carga. |

Una etapa **cumple** si cumple ambos umbrales. El **límite seguro** es la mayor concurrencia con todas las etapas anteriores cumpliendo. La **primera etapa con degradación** es la primera que no cumple.

## 5. Cómo se ejecuta

En AWS, desde otra máquina (idealmente otra instancia, para que el generador no compita por CPU con el servidor):

```bash
python tools/estres/estres.py --url https://<tu-url> --usuario <cuenta> --clave <clave> \
    --etapas 1,5,10,20,40,60,80 --duracion 60 --escritura \
    --umbral-p95 1500 --umbral-errores 1 \
    --entorno "EC2 t3.small, gunicorn 2x2, SQLite WAL, Redis local"
```

Mientras corre se observa en CloudWatch: `CPUUtilization` (y `mem_used_percent` si está el agente), y en la instancia `journalctl -u sgr -f`.

La herramienta escribe `estres_<fecha>.json/.csv/.md` en `docs/pruebas/estres/`. Para llevar las etapas a la hoja «Estrés» del registro, genera `docs/pruebas/resultados/estres.json` (mismo formato que el que ya existe) y vuelve a correr `python manage.py exportar_registro_pruebas --resultados docs/pruebas/resultados/ejecucion_<fecha>.json`.

## 6. Qué se hace con los resultados

- Si una etapa no cumple, se registra en la hoja **Defectos** (observación de rendimiento) con la operación más lenta de esa etapa, y se repite la prueba tras la corrección o el ajuste (más procesos de gunicorn, un tamaño de instancia mayor, un índice, caché).
- Los resultados que no cumplen **no se ocultan**: se informan tal cual, con el límite seguro observado.

## 7. Resultado del ensayo local (línea base, no es AWS)

El 2026-10-11 se ensayó el procedimiento en el contenedor de desarrollo (2 vCPU compartidos con el generador de carga, 2 procesos × 2 hilos, SQLite WAL). Detalle en `estres_2026-10-11_2123.md`.

| Usuarios | p95 (ms) | Errores | Veredicto |
|---:|---:|---:|---|
| 1 | 89 | 0 % | Cumple |
| 2 | 1.473 | 0 % | Cumple |
| 5 | 1.170 | 0 % | Cumple |
| 10 | 2.840 | 0 % | No cumple |
| 20 | 4.880 | 0 % | No cumple |
| 40 | 10.015 | 0 % | No cumple |

Lectura: en ese equipo, con el generador en la misma máquina, el límite seguro fue de 5 usuarios y no hubo errores en ninguna etapa (la degradación es de latencia, no de fallas); el sistema se recuperó al bajar a 1 usuario. Las operaciones más lentas fueron la exportación a Excel y las búsquedas (registradas como DEF-007 y DEF-008, abiertas). **Estas cifras no representan a AWS**: la prueba definitiva debe repetirse sobre la URL desplegada (PEN-01).
