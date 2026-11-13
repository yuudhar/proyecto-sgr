"""Descriptor de funciones para los cargos de las Delegaciones Municipales (versión 2026).

Es el texto del documento de la Coordinación de Delegaciones que entregó el cliente, con ajustes menores de
ortografía y puntuación; las descripciones de los cargos son la introducción de cada uno, resumida. Cada cargo trae
su descripción y sus funciones; las funciones pueden ir agrupadas bajo un título (`group`) y se numeran en el orden
del documento. El comando `cargar_funciones_cargos` lo carga en la base.
"""

VALID_FROM = "2026-01-01"

DESCRIPTOR = [
    {
        "name": "Delegado",
        "description": (
            "Funcionario representante directo de la alcaldía en los distintos sectores de su territorio. Su rol "
            "principal es actuar como puente entre el municipio y los sectores más alejados o poblados de la comuna, "
            "acercando la atención social, asesorar a los dirigentes en el territorio y gestionar soluciones locales "
            "(seguridad, limpieza, áreas verdes)."
        ),
        "functions": [
            ("", "Informar a la autoridad comunal, sobre situaciones que pudieran ocurrir en su territorio, con el objeto de adoptar las medidas preventivas correspondientes."),
            ("", "Ser representante de la Máxima autoridad comunal en su territorio, empoderándose de su cargo para enfrentar y solucionar las necesidades permanentes de los usuarios."),
            ("", "Responsable del buen funcionamiento del territorio desde la parte interna administrativa al cumplimiento de las gestiones encomendadas a la Delegación."),
            ("", "Visitar periódicamente Juntas de vecinos y Organizaciones comunitarias con el objetivo de estar presente, generando acompañamiento y apoyo."),
            ("", "Proponer y dar soluciones a las necesidades y problemas de los usuarios del sector, con el objeto de potenciar y mejorar la gestión de los servicios municipales."),
            ("", "Poner en práctica y supervisar el cumplimiento de planes y políticas de Desarrollo, que beneficien a la comunidad, de acuerdo a lo dispuesto por la máxima autoridad comunal."),
            ("", "Mantener buena relación y comunicación con las distintas direcciones y/o departamentos del municipio, así como con las organizaciones públicas y sociales, con el objetivo de apoyar el buen funcionamiento de su equipo de trabajo en las soluciones de las tareas encomendadas."),
            ("", "Hacer difusión de los programas y actividades implementados por la Municipalidad."),
            ("", "Delegar trabajos solicitados por la comunidad a su equipo de trabajo orientando y guiando el buen desempeño de las acciones."),
            ("", "Generar mesas de trabajo con distintos estamentos públicos y privados siendo el puente para los usuarios que necesitan atención."),
            ("", "Ejecutar otras funciones que la ley señale, que le encomiende el alcalde o el Administrador Municipal en el ámbito de sus competencias."),
        ],
    },
    {
        "name": "Gestor Social",
        "description": (
            "Responsable de desarrollar acciones comunitarias y atención de casos para promover el bienestar y la "
            "calidad de vida de los ciudadanos, especialmente de aquellos en situación de vulnerabilidad."
        ),
        "functions": [
            ("Atención de casos", "Recepción y evaluación de casos."),
            ("Atención de casos", "Diagnóstico y planificación."),
            ("Atención de casos", "Intervención y seguimiento."),
            ("Atención de casos", "Derivación y articulación."),
            ("Atención de casos", "Visitas en terreno."),
            ("Acciones comunitarias", "Diagnóstico comunitario."),
            ("Acciones comunitarias", "Planificación y ejecución de programas."),
            ("Acciones comunitarias", "Organización y participación comunitaria."),
            ("Acciones comunitarias", "Articular con organizaciones de apoyo social."),
            ("Acciones de coordinación y gestión", "Coordinación con otros servicios: coordinar con otros servicios y programas municipales para asegurar la atención integral de los ciudadanos."),
            ("Acciones de coordinación y gestión", "Gestión de recursos: gestionar recursos para la atención de casos y la ejecución de programas comunitarios."),
            ("Acciones de coordinación y gestión", "Informes y estadísticas: elaborar informes y estadísticas sobre la atención de casos y las acciones comunitarias realizadas."),
            ("Acciones de auto-mejora de desempeño", "Participación en reuniones y comités."),
            ("Acciones de auto-mejora de desempeño", "Capacitación y actualización."),
            ("Acciones de auto-mejora de desempeño", "Apoyo a la gestión municipal."),
        ],
    },
    {
        "name": "Apoyo Administrativo",
        "description": (
            "Funcionario que brinda asistencia en tareas de gestión documental y atención ciudadana, que garantizan "
            "el funcionamiento eficiente entre las distintas direcciones y departamentos; gestiona la agenda y la "
            "logística de la delegación, la tramitación de expedientes y la administración de la base de datos."
        ),
        "functions": [
            ("", "Llevar la agenda del delegado para así poder coordinar los diferentes eventos y reuniones en los que él debe participar ordenando y centralizando la información."),
            ("", "Coordinador del transporte de la delegación."),
            ("", "Encargado (a) de los auxiliares, mantención y aseo."),
            ("", "Dar atención al público y derivar a las áreas correspondientes dentro de la delegación."),
            ("", "Generar un Registro de Atenciones (registro en planilla SGR), para posteriormente llamar preventivamente al usuario."),
            ("", "Generar inventario trimestral de la delegación."),
            ("", "Realizar la entrega de materiales a los funcionarios."),
            ("", "Retroalimentar para la gestión de delegado las solicitudes ingresadas por la comunidad (correos al alias, solicitudes por carta, en oficina y/o oficina de partes, etc.)."),
            ("", "Informes mensuales del personal administrativo (se excluye empleabilidad): permisos, solicitudes y armado de carpetas para pago, envío de documentos digitales para transparencia."),
            ("", "Encargada de envío de agenda a Comunicaciones."),
            ("", "Temas varios en procesos administrativos para cumplir los objetivos planteados por la Delegación."),
        ],
    },
    {
        "name": "Organizaciones Comunitarias",
        "description": (
            "Es el responsable del Registro de Organizaciones (OROC) y de facilitar la formación, legalización y "
            "asesoría de Juntas de Vecinos y agrupaciones funcionales bajo las leyes 19.418 y 20.500."
        ),
        "functions": [
            ("", "Potenciar integralmente el desarrollo de los territorios costeros en beneficio de la comunidad."),
            ("", "Creación de organizaciones nuevas, y mantener vigencia o cierre de organizaciones comunitarias inactivas."),
            ("", "Asesorar y capacitar en distintas temáticas y procedimientos de las organizaciones comunitarias en general."),
            ("", "Levantamiento de necesidades en cada territorio (visitas) en conjunto con los dirigentes de cada organización."),
            ("", "Encargado (a) de generar las convocatorias a las distintas actividades municipales que se realicen."),
            ("", "Articulador entre las organizaciones comunitarias y distintas áreas municipales para el cumplimiento de los requerimientos y necesidades de los usuarios."),
            ("", "Generar actividades y talleres a las organizaciones, manteniendo la motivación y aumentando la educación en temas municipales."),
            ("", "Temas varios en procesos administrativos para cumplir los objetivos planteados por la Delegación."),
        ],
    },
    {
        "name": "Gestor de Compras y Proyectos",
        "description": (
            "Responsable de tramitar los requerimientos de adquisiciones de bienes y/o servicios de las unidades "
            "municipales de su dirección ante las unidades intervinientes en el proceso (Unidad Revisora, Unidad "
            "Gestionadora y Unidad de Compra). En cada dirección hay al menos dos Gestores de Compras, uno titular y "
            "uno suplente, designados por decreto alcaldicio."
        ),
        "functions": [
            ("", "Recopilar y confeccionar la Planificación Operativa Anual de su Dirección, considerando los requerimientos de todas las unidades de ella."),
            ("", "Realizar control de gestión al cumplimiento del Plan Anual de Compras de su dirección, evaluando permanentemente las necesidades de éstas con el Director respectivo. Las necesidades deben estar en directa relación con los requerimientos para un correcto funcionamiento y operación de la Dirección a su cargo."),
            ("", "Revisar pliego de condiciones, marco de referencia y especificaciones técnicas, cuando corresponda, dando su visto bueno para posteriormente remitir a la Unidad Revisora junto con la solicitud y los documentos asociados."),
            ("", "Elaborar las solicitudes o el oficio interno ordinario de contrataciones de bienes y/o servicios de su dirección con la debida anticipación, de acuerdo a la planificación existente y a los requerimientos emanados de las distintas unidades."),
            ("", "Incorporar en las solicitudes o el oficio interno ordinario la propuesta de designación de la Comisión Evaluadora o Evaluador, del Inspector Técnico de Contrato titular y subrogante, según corresponda."),
        ],
    },
    {
        "name": "Gestión y Planificación",
        "description": (
            "Responsable de alinear los objetivos estratégicos de la organización con sus operaciones diarias. Diseña "
            "planes de acción, monitorea el rendimiento mediante indicadores clave y optimiza la toma de decisiones "
            "para garantizar el uso eficiente de los recursos."
        ),
        "functions": [
            ("", "Encargado de derivar y apoyar a cada área, en la realización y entrega de los informes solicitados por la Jefatura."),
            ("", "Apoya con registros al levantamiento y/o actualización del diagnóstico de las necesidades de la comunidad de su sector, así como listados de información estratégica para la toma de decisiones."),
            ("", "Encargado de mantener el buen funcionamiento de los procesos de la delegación, participando en acciones de coordinación interna del personal derivando tareas del día a día y apoyando el cumplimiento de estas."),
            ("", "Encargado de generar información al delegado referente al trabajo de la matriz SGR indicando las fortalezas y debilidades de cada colaborador y anticiparse a los resultados de la Delegación."),
            ("", "Informar oportunamente al delegado municipal sobre materias de interés del sector."),
            ("", "Coordinación con departamentos internos y/o equipo de coordinación de las Delegaciones municipales, cuando la jefatura requiera."),
            ("", "Encargado de tomar acciones rápidas de solución a problemas derivados desde Gabinete."),
            ("", "Participar como representante de la delegación cuando el delegado lo solicite."),
            ("", "Coordinación con los diferentes departamentos municipales para la consecución de los objetivos."),
            ("", "Responsable del buen funcionamiento del llenado de la matriz SGR."),
            ("", "Encargado de gestionar la reunión semanal."),
            ("", "Temas varios en procesos administrativos para cumplir los objetivos planteados por la Delegación."),
        ],
    },
    {
        "name": "Coordinador de Servicios Comunitarios",
        "description": (
            "Planifica, coordina y ejecuta iniciativas y programas destinados a fortalecer el desarrollo de acciones "
            "de aseo, ornato y medio ambiente en beneficio de la comunidad."
        ),
        "functions": [
            ("", "Servir de enlace permanente entre la Municipalidad y las Juntas de Vecinos, organizaciones funcionales, clubes deportivos y agrupaciones ambientales para la realización de operativos de limpieza y reparaciones de BNUP."),
            ("", "Atención del usuario presencial y en terreno cuando se requiera de un análisis técnico para desarrollar o ejecutar obras de mejoramiento (caminos, desmalezamiento, etc.)."),
            ("", "Coordinar la ejecución y seguimiento de operativos de limpieza y desmalezado, mejoramiento de barrios y recuperación de espacios."),
            ("", "Liderar y coordinar acciones de educación ambiental (talleres de reciclaje, compostaje, aseo y ornato), operativos de limpieza y programas de reciclaje."),
            ("", "Responsable del buen funcionamiento operativo y administrativo de las cuadrillas del programa de empleabilidad y cuadrilla de emergencia (polifuncionales)."),
            ("", "Coordinar acciones con distintas direcciones municipales (Aseo y Ornato, Operaciones, maquinarias) para garantizar servicios eficientes para la comunidad."),
            ("", "Recibir, canalizar y realizar el seguimiento de denuncias ciudadanas relacionadas con el uso indebido de los espacios públicos."),
            ("", "Elaborar informes de gestión periódicas del programa de empleabilidad y cuadrilla polifuncionales."),
            ("", "Temas varios en procesos administrativos para el buen desempeño de la delegación en el área de servicios a la comunidad."),
        ],
    },
]
