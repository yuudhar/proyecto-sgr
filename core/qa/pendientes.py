"""Lo que todavía no está probado y por qué. No se declara aprobado nada de esta lista."""

COLUMNAS = ["Código", "Requisito", "Qué falta", "Por qué está pendiente", "Cómo se cierra", "Estado"]
ANCHOS = [10, 34, 56, 64, 64, 14]

PENDIENTES = [
    (
        "PEN-01",
        "A3 · Pruebas de estrés",
        "Ejecutar la concurrencia creciente en el entorno AWS y registrar los resultados definitivos.",
        "Necesitan la URL de AWS operativa con la versión entregada. En este entorno solo se pudo medir una línea base local, "
        "que sirve para ensayar el procedimiento pero no representa a AWS.",
        "Seguir docs/pruebas/estres/PLAN_ESTRES.md: python tools/estres/estres.py --url https://<tu-url> ... y cargar el resultado en la hoja «Estrés».",
        "Pendiente",
    ),
    (
        "PEN-02",
        "A2 · Normas gráficas oficiales",
        "Archivo oficial del escudo y código exacto del color de las normas gráficas de La Serena.",
        "El archivo y el código deben venir de la fuente oficial (laserena.cl); no se inventan ni se dibujan. Hoy el sistema usa Arial y #920000 y deja el lugar del escudo. La página de laserena.cl declara #920000 como color del tema en sus metadatos, lo que coincide con el sistema, pero no es el manual de normas gráficas (no se pudo obtener el escudo en alta resolución ni los códigos Pantone/CMYK).",
        "Copiar el escudo como core/static/core/img/escudo-la-serena.svg (o .png): aparece solo. Si el color oficial es otro, cambiar la variable de color en core/static/core/css/sgr.css.",
        "Pendiente",
    ),
    (
        "PEN-03",
        "A4 · Evidencias 1 a 8 en AWS",
        "Repetir las capturas y el recorrido de cada evidencia sobre la URL de AWS.",
        "Las capturas incluidas se tomaron en un servidor local con datos de demostración; la evidencia de entrega debe mostrar el despliegue en AWS.",
        "python tools/evidencias/capturar.py --url https://<tu-url> (ver docs/evidencias/README.md).",
        "Pendiente",
    ),
    (
        "PEN-04",
        "A3 · Correo real de la recuperación",
        "Probar el envío por SMTP real (EMAIL_HOST) y la recepción del código.",
        "Las pruebas automáticas usan la bandeja de prueba de Django; el envío real depende del servidor de correo que se configure en AWS.",
        "Completar EMAIL_HOST y credenciales en el .env de AWS y repetir el flujo de recuperación (evidencia 1).",
        "Pendiente",
    ),
    (
        "PEN-05",
        "A3 · Intentos de recuperación con varios procesos",
        "Comprobar el límite de 5 intentos con gunicorn de varios procesos y la caché compartida configurada.",
        "Las pruebas corren en un solo proceso con caché local. Con varios procesos hace falta una caché compartida (CACHE_BACKEND=redis).",
        "Configurar CACHE_BACKEND=redis y REDIS_URL en AWS (docs/aws/DESPLIEGUE_AWS.md) y repetir las pruebas de código incorrecto.",
        "Pendiente",
    ),
    (
        "PEN-06",
        "A3 · Base de datos MySQL/RDS",
        "Correr la suite con DB_ENGINE=mysql si el despliegue usa MySQL o RDS.",
        "Esta corrida usó SQLite (el valor por defecto del proyecto).",
        "Con la base MySQL creada: DB_ENGINE=mysql python manage.py test y volver a generar este registro.",
        "Pendiente",
    ),
    (
        "PEN-07",
        "A3 · Comportamiento de JavaScript",
        "Las pruebas de Django revisan el HTML y la respuesta del servidor, pero no ejecutan JavaScript.",
        "Los avisos SweetAlert2, el pegado del código en seis casillas y la lista dependiente se verifican en navegador en la hoja «Navegador»; lo que esa hoja no cubra queda como revisión manual.",
        "Ejecutar python tools/evidencias/capturar.py (o con --url de AWS) y revisar la hoja «Navegador».",
        "Parcial",
    ),
]


def filas():
    return [list(p) for p in PENDIENTES]
