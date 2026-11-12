"""Carga reproducible de datos para la revisión de la Evaluación Sumativa III (TI3041).

Qué hace
--------
* Deja listos los roles (`seed_roles`) y el catálogo de tipos de gestión (`seed_management_types`).
* Carga más de 2.000 registros de negocio ficticios y variados, repartidos entre los modelos del proyecto, con al
  menos 50 en cada CRUD evaluado (y, en los que se filtran por delegación, al menos 50 en cada delegación).
* Reparte los datos entre dos ámbitos: **Delegación Norte = organización A** y **Delegación Sur = organización B**.
* Crea las seis cuentas de prueba (administrador A, editor A, lector A, lector B, cliente1 y cliente2).
* Al terminar imprime el total por modelo y comprueba los mínimos y los permisos de las cuentas.

Idempotencia
------------
El comando se puede ejecutar todas las veces que haga falta: cada registro tiene una clave natural (RUT, código de
funcionario, N.º de registro, código de evidencia, funcionario + fecha + persona, etc.) y solo se crea lo que falta.
Los valores salen de `random.Random(2026)` y de una fecha base fija (`FECHA_BASE`), no de la fecha de hoy, de modo
que dos ejecuciones generan exactamente los mismos registros. No toca lo que alguien haya editado o archivado después.

Contraseñas
-----------
Nunca están en el repositorio. Se leen, en este orden, de: `SGR_PASSWORD_<ALIAS>` (por cuenta, por ejemplo
`SGR_PASSWORD_ADMIN_A`), `--password`, la variable `SGR_REVISION_PASSWORD` o, si hay una terminal, se piden por
pantalla. Solo se asignan al crear la cuenta (o con `--reasignar-claves`).

`core/datos_prueba.py` (la demostración local) no se usa ni se debe cargar en el servidor.
"""
import getpass
import os
import random
import sys
from datetime import date, datetime, time, timedelta
from io import StringIO

from django.apps import apps
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from accounts.models import UserProfile
from core.audit import log_event
from core.management.commands.cargar_volumen_estres import digito_verificador
from evidence.models import Evidence, Validation
from operations.models import Activity, Commitment, Followup, ManagementType
from organization.models import (
    Beneficiary,
    CommunityOrganization,
    Delegation,
    Item,
    Officer,
    Position,
    PositionItem,
    Service,
    Territory,
)
from planning import calculation, feedback as feedback_rules
from planning.models import Absence, Feedback, Goal, Period

SEMILLA = 2026
FECHA_BASE = date(2026, 10, 30)  # fija: el comando debe generar siempre lo mismo, sin importar el día en que se ejecute
DIAS_ATRAS = 240

MINIMO_TOTAL = 2000
MINIMO_POR_CRUD = 50

# Los dos CRUD que el grupo presenta como evaluados. Se cambian aquí (y en el README) si el grupo elige otros.
CRUDS_EVALUADOS = ("actividades", "beneficiarios")

APLICACIONES_PROPIAS = ("core", "organization", "operations", "evidence", "planning", "accounts")

DOMINIO_CORREO = "revision.sgr.example"

PASSWORD_ENV_COMUN = "SGR_REVISION_PASSWORD"

# --- Cantidades (por delegación, salvo que se diga otra cosa) ---------------------------------------------------
FUNCIONARIOS = 55
TERRITORIOS = 55
ATENCIONES = 330
ATENCIONES_CLIENTE = 24  # por cada cliente final
COMPROMISOS = 60
COMPROMISOS_DE_TERRENO = 55  # por delegación: los que nacen de una atención con visita a terreno
EVIDENCIAS = 130  # máximo por delegación: se toma una de cada tres atenciones vigentes
FELICITACIONES_Y_RECLAMOS = 55
AUSENCIAS = 55
BENEFICIARIOS = 400  # compartidos entre delegaciones
ORGANIZACIONES = 80  # compartidas entre delegaciones
ATENCIONES_CON_COMPROMISO = 40

# --- Ámbitos -----------------------------------------------------------------------------------------------------
AMBITOS = (
    {
        "letra": "N",
        "delegacion": "Delegación Norte",
        "alcance": "Sector norte",
        "color": "#1D4E89",
        "responsable": "Diego Fuentes",
        "direccion": "Av. Cuatro Esquinas 1200",
        "comuna": "La Serena",
    },
    {
        "letra": "S",
        "delegacion": "Delegación Sur",
        "alcance": "Sector sur",
        "color": "#2E7D5B",
        "responsable": "Ignacio Vidal",
        "direccion": "Av. Juan Bohón 850",
        "comuna": "La Serena",
    },
)

# Posición 1 de cada delegación = jefatura; 2, 3 = encargado social y analista; el resto alterna cargos de terreno.
POSICION_JEFATURA, POSICION_ANALISTA = 1, 3

FUNCIONARIOS_FIJOS = {
    "N": {1: "Camila Fuentealba Reyes", 2: "Tomás Aravena Lagos", 3: "Daniela Maldonado Pino"},
    "S": {1: "Rodrigo Escobar Salas", 2: "Isidora Cárdenas Mella", 3: "Esteban Contreras Vera"},
}

# --- Cuentas de prueba (sin contraseñas: ver el encabezado) ---------------------------------------------------------
CUENTAS = (
    {
        "alias": "admin_a",
        "username": "admin_a",
        "rol": "Administrador A",
        "ambito": "N",
        "funcionario": 1,
        "grupos": ("Jefatura", "Funcionario"),
        "permisos": "administrador",
    },
    {
        "alias": "editor_a",
        "username": "editor_a",
        "rol": "Editor A",
        "ambito": "N",
        "funcionario": 2,
        "grupos": ("Funcionario",),
        "permisos": "editor",
    },
    {
        "alias": "lector_a",
        "username": "lector_a",
        "rol": "Lector A",
        "ambito": "N",
        "funcionario": 3,
        "grupos": ("Consulta",),
        "permisos": "lector",
    },
    {
        "alias": "lector_b",
        "username": "lector_b",
        "rol": "Lector B",
        "ambito": "S",
        "funcionario": 3,
        "grupos": ("Consulta",),
        "permisos": "lector",
    },
    {
        "alias": "cliente1",
        "username": "cliente1",
        "rol": "Cliente 1",
        "ambito": "N",
        "cliente": {"rut_base": 16_500_001, "nombre": "Marta Villarroel Cáceres", "telefono": "+56 9 6150 0001",
                    "direccion": "Pasaje Los Alerces 118, La Serena"},
        "grupos": ("Cliente",),
        "permisos": "cliente",
    },
    {
        "alias": "cliente2",
        "username": "cliente2",
        "rol": "Cliente 2",
        "ambito": "S",
        "cliente": {"rut_base": 16_500_002, "nombre": "Héctor Bravo Ibáñez", "telefono": "+56 9 6150 0002",
                    "direccion": "Calle Los Naranjos 2045, La Serena"},
        "grupos": ("Cliente",),
        "permisos": "cliente",
    },
)

ACCIONES = ("view", "add", "change", "delete")
MODULOS_OPERACION = (
    "operations.activity",
    "operations.followup",
    "operations.commitment",
    "evidence.evidence",
    "evidence.validation",
    "planning.feedback",
    "planning.absence",
    "organization.beneficiary",
    "organization.communityorganization",
    "organization.territory",
    "organization.officer",
)
# Permisos que se suman al rol (grupo) de cada cuenta: «eliminar y archivar» exige delete_<modelo> y ningún rol
# base lo tiene; la gestión de usuarios la define el rol de la cuenta, no un superusuario.
PERMISOS_EXTRA = {
    "administrador": [f"{modulo}:{accion}" for modulo in MODULOS_OPERACION for accion in ACCIONES]
    + ["auth.user:view", "auth.user:add", "auth.user:change"],
    "editor": [f"organization.beneficiary:{accion}" for accion in ("view", "add", "change")]
    + ["organization.communityorganization:view"],
    "lector": ["organization.beneficiary:view", "organization.communityorganization:view"],
    "cliente": [],
}

# --- Textos ficticios --------------------------------------------------------------------------------------------
NOMBRES = [
    "Rosa", "Juan", "María", "Pedro", "Ana", "Luis", "Carla", "Diego", "Sofía", "Mateo", "Elena", "Jorge", "Camila",
    "Felipe", "Valentina", "Cristián", "Paula", "Ricardo", "Javiera", "Andrés", "Constanza", "Gabriel", "Francisca",
    "Sebastián", "Macarena", "Nicolás", "Fernanda", "Claudio", "Antonia", "Hugo", "Beatriz", "Samuel", "Lorena",
    "Patricio", "Marcela", "Álvaro", "Gladys", "Raúl", "Ximena", "Óscar",
]
APELLIDOS = [
    "Núñez", "Pérez", "González", "Rojas", "Díaz", "Soto", "Araya", "Castillo", "Muñoz", "Tapia", "Rivera", "Vega",
    "Contreras", "Silva", "Martínez", "Sepúlveda", "Morales", "Rodríguez", "López", "Fuentes", "Hernández", "Torres",
    "Araneda", "Flores", "Espinoza", "Valdés", "Figueroa", "Carrasco", "Sandoval", "Reyes", "Gutiérrez", "Cortés",
    "Pizarro", "Godoy", "Orellana", "Campos", "Tobar", "Navarro", "Bustos", "Herrera",
]
CALLES = [
    "Los Aromos", "Las Rosas", "Arturo Prat", "Balmaceda", "Los Olivos", "El Sauce", "Cordovez", "Brasil", "Colo Colo",
    "Los Alerces", "Las Acacias", "Pedro Pablo Muñoz", "Larraín Alcalde", "Los Carrera", "Francisco de Aguirre",
    "Cisternas", "Almagro", "Regimiento Arica", "Amunátegui", "Benavente",
]
LUGARES = [
    "Villa Los Aromos", "Población El Milagro", "Las Compañías Alto", "Villa Alemana Norte", "Parcelas El Romeral",
    "Barrio Santa Lucía", "Población Estadio", "Villa San Joaquín", "Sector La Florida", "Población Gabriela Mistral",
    "Villa Los Olivos", "Barrio Pedro de Valdivia", "Población Las Rosas", "Villa Las Higueras", "Sector Cerro Grande",
    "Población Arcos de Pinamar", "Villa El Faro", "Barrio Antena", "Población Jardín del Este", "Villa Altovalsol",
    "Sector Tierras Blancas", "Población Los Pescadores", "Villa Santa Rosa", "Barrio San Juan", "Población Alessandri",
]
SOLICITUDES = [
    "Solicita certificado de residencia",
    "Consulta por ayuda social",
    "Reclama por luminaria en mal estado",
    "Pide visita domiciliaria",
    "Consulta por subsidio de agua potable",
    "Solicita orientación sobre trámites municipales",
    "Pide ayuda para postular al subsidio de vivienda",
    "Consulta por entrega de cajas de alimentos",
    "Solicita retiro de escombros en la vereda",
    "Pregunta cómo actualizar el Registro Social de Hogares",
    "Pide una silla de ruedas en préstamo",
    "Reclama por un árbol que obstruye el cableado",
    "Consulta por beca de arriendo para adulto mayor",
    "Solicita apoyo para una emergencia por lluvias",
    "Pide orientación para renovar la credencial de discapacidad",
    "Consulta por talleres comunitarios del barrio",
]
ACCIONES_TOMADAS = [
    "Se orientó a la persona y se entregó el formulario.",
    "Se derivó el caso a la oficina municipal correspondiente.",
    "Se coordinó una visita al domicilio para la próxima semana.",
    "Se ingresó la solicitud y se informó el plazo de respuesta.",
    "Se entregó el certificado en el momento.",
    "Se contactó a la dirigenta del sector para apoyar el trámite.",
    "Se registró el reclamo y se envió el aviso al departamento técnico.",
    "Se acompañó a la persona en la postulación en línea.",
]
RESULTADOS_GESTION = [
    "Se contactó a la persona y se acordó la fecha de visita.",
    "La persona entregó los documentos que faltaban.",
    "Se realizó la visita y se levantó el informe.",
    "Se entregó el beneficio y se dejó constancia firmada.",
    "No contestó el teléfono: se reintentará mañana.",
    "El trámite quedó ingresado y a la espera de respuesta.",
    "Se informó el resultado a la persona por llamada.",
]
ORIGENES_COMPROMISO = [
    "Reunión de coordinación mensual",
    "Cabildo abierto del barrio",
    "Solicitud de la junta de vecinos",
    "Visita a terreno del jefe de delegación",
    "Oficio municipal",
]
APOYOS_COMPROMISO = ["Municipalidad", "Dirección de obras", "Aseo y ornato", "Dirección de desarrollo comunitario", "Salud"]
ORIGENES_TERRENO = ["Atención con visita a terreno", "Atención con visita (derivada de la oficina)", "Visita pedida por la junta de vecinos"]
DESCRIPCIONES_TERRENO = [
    "Salida a terreno y catastro con dirigentes del sector.",
    "Revisión de luminarias en el pasaje y registro de las que no funcionan.",
    "Visita para evaluar la instalación de reductores de velocidad.",
    "Inspección de un sitio eriazo con acumulación de basura.",
    "Evaluación social en el domicilio y derivación de la familia.",
    "Poda de árboles en la plaza junto con la cuadrilla de áreas verdes.",
    "Visita a la sede social para revisar su estado y los arreglos pendientes.",
    "Verificación en terreno de una denuncia por ruidos molestos.",
    "Entrega de ayuda comprometida en el domicilio de la solicitante.",
    "Reunión en terreno con vecinos por el mejoramiento de la multicancha.",
]
DESCRIPCIONES_COMPROMISO = [
    "Reparar la luminaria de la plaza del sector.",
    "Entregar la ayuda social comprometida a las familias afectadas.",
    "Realizar un operativo de salud en la sede social.",
    "Limpiar el sitio eriazo junto a la escuela.",
    "Instalar señalética de tránsito frente al jardín infantil.",
    "Entregar los certificados pendientes de la junta de vecinos.",
    "Visitar a las familias inscritas en el catastro de emergencia.",
]
DESCRIPCIONES_FELICITACION = [
    "Agradece la rapidez y la amabilidad en la atención.",
    "Felicita la orientación recibida para su trámite.",
    "Destaca la paciencia al explicar los requisitos del beneficio.",
    "Reconoce el apoyo recibido durante una emergencia.",
]
DESCRIPCIONES_RECLAMO = [
    "Reclama porque la visita comprometida no se realizó en la fecha acordada.",
    "Reclama por demora en la entrega de un certificado.",
    "Reclama por falta de información sobre el estado de su solicitud.",
    "Reclama porque no le devolvieron el llamado que pidió.",
]
NOTAS_AUSENCIA = ["Licencia médica", "Vacaciones", "Trámite personal", "Emergencia familiar", "Día compensatorio"]
TIPOS_ORGANIZACION = ["Junta de Vecinos", "Club de Adulto Mayor", "Comité de Vivienda", "Centro de Madres", "Club Deportivo"]


# --- Utilidades --------------------------------------------------------------------------------------------------
def pdf_minimo(texto):
    """Un PDF válido de una página con el texto indicado (sirve como archivo de evidencia o de respaldo de prueba)."""
    seguro = texto.replace("\\", "").replace("(", "").replace(")", "")
    flujo = f"BT /F1 14 Tf 72 720 Td ({seguro}) Tj ET".encode("latin-1", "replace")
    objetos = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(flujo)).encode() + b" >>\nstream\n" + flujo + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    salida = b"%PDF-1.4\n"
    posiciones = []
    for numero, cuerpo in enumerate(objetos, start=1):
        posiciones.append(len(salida))
        salida += f"{numero} 0 obj\n".encode() + cuerpo + b"\nendobj\n"
    inicio = len(salida)
    salida += f"xref\n0 {len(objetos) + 1}\n".encode() + b"0000000000 65535 f \n"
    for posicion in posiciones:
        salida += f"{posicion:010d} 00000 n \n".encode()
    salida += f"trailer\n<< /Size {len(objetos) + 1} /Root 1 0 R >>\nstartxref\n{inicio}\n%%EOF\n".encode()
    return salida


def rut_de(numero):
    return f"{numero}-{digito_verificador(numero)}"


def momento(dia, indice=0):
    """Un instante dentro del día indicado (para que «reciente a antiguo» siga el orden de las fechas)."""
    return timezone.make_aware(datetime.combine(dia, time(8 + indice % 9, (indice * 7) % 60)))


def dia_habil(dia):
    while dia.weekday() >= 5:
        dia -= timedelta(days=1)
    return dia


def elegir_con_peso(azar, opciones):
    """opciones: [(valor, peso), …]"""
    total = sum(peso for _, peso in opciones)
    punto = azar.random() * total
    acumulado = 0
    for valor, peso in opciones:
        acumulado += peso
        if punto < acumulado:
            return valor
    return opciones[-1][0]


def telefono(azar):
    return f"+56 9 {azar.randint(1000, 9999)} {azar.randint(1000, 9999)}"


def nombre_persona(azar):
    return f"{azar.choice(NOMBRES)} {azar.choice(APELLIDOS)} {azar.choice(APELLIDOS)}"


def prefijo_evidencia(delegacion):
    nombre = delegacion.name
    if nombre.lower().startswith("delegación "):
        nombre = nombre[len("delegación "):]
    return f"EVD-{slugify(nombre).upper()}-R"


class Command(BaseCommand):
    help = (
        "Carga datos ficticios y reproducibles para la revisión (≥2.000 registros, ≥50 por CRUD evaluado, dos "
        "ámbitos) y crea las seis cuentas de prueba. Se puede ejecutar varias veces sin duplicar datos."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--password",
            help=(
                "Contraseña de las cuentas nuevas. Es preferible la variable de entorno "
                f"{PASSWORD_ENV_COMUN} (o SGR_PASSWORD_<ALIAS> para una cuenta), porque un argumento queda en el "
                "historial de la terminal."
            ),
        )
        parser.add_argument(
            "--reasignar-claves",
            action="store_true",
            help="Cambia también la contraseña de las cuentas que ya existen.",
        )

    # ------------------------------------------------------------------------------------------------------------
    def handle(self, *args, **opciones):
        claves = self.reunir_claves(opciones)
        self.azar = random.Random(SEMILLA)
        self.stdout.write("Cargando roles y catálogo de tipos de gestión...")
        call_command("seed_roles", stdout=StringIO())
        call_command("seed_management_types", stdout=StringIO())

        antes = self.total_negocio()
        # El recálculo automático queda en pausa: los indicadores se calculan una sola vez al final.
        with calculation.suspended(), transaction.atomic():
            self.catalogos()
            self.estructura()
            self.cuentas(claves, opciones["reasignar_claves"])
            self.beneficiarios_y_organizaciones()
            self.compromisos()
            self.atenciones()
            self.gestiones()
            self.evidencias_y_validaciones()
            self.felicitaciones_y_reclamos()
            self.ausencias()
            self.metas()
            self.compromisos_de_terreno()
        creados = calculation.recalculate_period(self.periodo)
        self.stdout.write(f"Indicadores nuevos calculados: {creados}.")

        total = self.informe()
        self.verificar(total)
        self.stdout.write(self.style.SUCCESS(f"Registros de negocio nuevos en esta ejecución: {total - antes}."))

    # ------------------------------------------------------------------------------------------------------------
    # Contraseñas
    # ------------------------------------------------------------------------------------------------------------
    def reunir_claves(self, opciones):
        User = get_user_model()
        reasignar = opciones["reasignar_claves"]
        faltan = [
            cuenta
            for cuenta in CUENTAS
            if reasignar or not User.objects.filter(username=cuenta["username"]).exists()
        ]
        claves = {}
        if not faltan:
            return claves
        comun = opciones.get("password") or os.environ.get(PASSWORD_ENV_COMUN, "")
        if not comun and not any(os.environ.get(f"SGR_PASSWORD_{c['alias'].upper()}") for c in faltan):
            if sys.stdin.isatty():
                comun = getpass.getpass("Contraseña para las cuentas de prueba: ")
                if comun != getpass.getpass("Repite la contraseña: "):
                    raise CommandError("Las contraseñas no coinciden.")
        for cuenta in faltan:
            clave = os.environ.get(f"SGR_PASSWORD_{cuenta['alias'].upper()}") or comun
            if not clave:
                raise CommandError(
                    f"Falta la contraseña de «{cuenta['username']}». Define {PASSWORD_ENV_COMUN} (o "
                    f"SGR_PASSWORD_{cuenta['alias'].upper()}), usa --password o ejecuta el comando en una terminal."
                )
            try:
                validate_password(clave)
            except ValidationError as error:
                raise CommandError(f"La contraseña de «{cuenta['username']}» no es válida: {' '.join(error.messages)}")
            claves[cuenta["username"]] = clave
        return claves

    # ------------------------------------------------------------------------------------------------------------
    # Catálogos y estructura
    # ------------------------------------------------------------------------------------------------------------
    def catalogos(self):
        desde = date(2025, 1, 1)
        self.cargo = {
            nombre: Position.objects.get_or_create(name=nombre, defaults={"valid_from": desde})[0]
            for nombre in ("Encargado Social", "Coordinador de Terreno", "Jefe de Delegación", "Analista de Datos")
        }
        social = Item.objects.get_or_create(
            name="Atención Social",
            defaults={
                "description": "Atención a vecinos y vecinas que piden apoyo social: orientación, visitas y seguimiento.",
                "calculation_type": Item.CalculationType.QUALITATIVE,
            },
        )[0]
        visita = Item.objects.get_or_create(
            name="Visita Domiciliaria",
            defaults={
                "description": "Visita al domicilio del vecino para conocer su situación.",
                "parent_item": social,
                "calculation_type": Item.CalculationType.QUALITATIVE,
            },
        )[0]
        telefonico = Item.objects.get_or_create(
            name="Seguimiento Telefónico",
            defaults={
                "description": "Llamado de seguimiento a un caso que ya fue atendido.",
                "parent_item": social,
                "calculation_type": Item.CalculationType.QUALITATIVE,
            },
        )[0]
        ayudas = Item.objects.get_or_create(
            name="Entrega de Ayudas Sociales",
            defaults={
                "description": "Entrega de ayudas sociales a quienes cumplen los requisitos.",
                "calculation_type": Item.CalculationType.QUANTITATIVE,
            },
        )[0]
        coordinacion = Item.objects.get_or_create(
            name="Coordinación Territorial",
            defaults={
                "description": "Coordinación con las organizaciones y dirigentes del territorio.",
                "calculation_type": Item.CalculationType.QUALITATIVE,
            },
        )[0]
        self.item_social, self.item_ayudas = social, ayudas
        self.items = [(social, 4), (visita, 5), (telefonico, 4), (ayudas, 3), (coordinacion, 2)]
        for cargo in ("Encargado Social", "Coordinador de Terreno", "Jefe de Delegación"):
            PositionItem.objects.get_or_create(
                position=self.cargo[cargo],
                item=social,
                defaults={"weight": 50, "valid_from": desde, "kind": PositionItem.Kind.NORMAL},
            )
        PositionItem.objects.get_or_create(
            position=self.cargo["Encargado Social"],
            item=ayudas,
            defaults={"weight": 10, "valid_from": desde, "kind": PositionItem.Kind.BONUS, "max_cap": 15},
        )
        self.servicios = [
            Service.objects.get_or_create(name=nombre, defaults={"status": Service.Status.ACTIVE})[0]
            for nombre in ("Ayuda Social", "Vivienda", "Certificado de Residencia", "Postulación a Subsidio")
        ]
        self.tipos_gestion = list(ManagementType.objects.order_by("pk"))

        self.periodo = Period.objects.get_or_create(
            start_date=date(2026, 1, 1),
            defaults={"end_date": date(2026, 12, 31), "computable_days": 240, "status": Period.Status.ACTIVE},
        )[0]
        Period.objects.get_or_create(
            start_date=date(2025, 1, 1),
            defaults={"end_date": date(2025, 12, 31), "computable_days": 235, "status": Period.Status.CLOSED},
        )

    def estructura(self):
        """Delegaciones, territorios y funcionarios de cada ámbito."""
        self.delegacion = {}
        self.territorios = {}
        self.funcionarios = {}  # letra -> {posición: Officer}
        for ambito in AMBITOS:
            letra = ambito["letra"]
            delegacion = Delegation.objects.get_or_create(
                name=ambito["delegacion"],
                defaults={
                    "status": Delegation.Status.ACTIVE,
                    "scope": ambito["alcance"],
                    "color": ambito["color"],
                    "managers": ambito["responsable"],
                    "address": ambito["direccion"],
                    "commune": ambito["comuna"],
                },
            )[0]
            self.delegacion[letra] = delegacion

            territorios = []
            for numero in range(TERRITORIOS):
                nombre = f"{LUGARES[numero % len(LUGARES)]} {numero // len(LUGARES) + 1}"
                territorios.append(Territory.objects.get_or_create(name=nombre, delegation=delegacion)[0])
            self.territorios[letra] = territorios

            oficiales = {}
            for posicion in range(1, FUNCIONARIOS + 1):
                nombre = FUNCIONARIOS_FIJOS[letra].get(posicion) or nombre_persona(self.azar)
                if posicion == POSICION_JEFATURA:
                    cargo = self.cargo["Jefe de Delegación"]
                elif posicion == POSICION_ANALISTA:
                    cargo = self.cargo["Analista de Datos"]
                else:
                    cargo = self.cargo["Encargado Social" if posicion % 2 == 0 else "Coordinador de Terreno"]
                oficiales[posicion] = Officer.objects.get_or_create(
                    institutional_id=f"REV-{letra}-{posicion:03d}",
                    defaults={
                        "name": nombre,
                        "status": Officer.Status.ACTIVE,
                        "delegation": delegacion,
                        "position": cargo,
                    },
                )[0]
            self.funcionarios[letra] = oficiales

    def de_terreno(self, letra):
        """Funcionarios que registran atenciones (todos menos la jefatura y el analista)."""
        return [o for p, o in self.funcionarios[letra].items() if p not in (POSICION_JEFATURA, POSICION_ANALISTA)]

    # ------------------------------------------------------------------------------------------------------------
    # Cuentas
    # ------------------------------------------------------------------------------------------------------------
    def permisos(self, claves):
        encontrados = []
        for clave in claves:
            modelo, accion = clave.split(":")
            app, nombre = modelo.split(".")
            encontrados.append(
                Permission.objects.get(content_type__app_label=app, codename=f"{accion}_{nombre}")
            )
        return encontrados

    def cuentas(self, claves, reasignar):
        User = get_user_model()
        self.usuario = {}
        self.cliente = {}
        for cuenta in CUENTAS:
            usuario, nuevo = User.objects.get_or_create(
                username=cuenta["username"],
                defaults={
                    "email": f"{cuenta['username']}@{DOMINIO_CORREO}",
                    "is_staff": False,
                    "is_superuser": False,
                    "is_active": True,
                },
            )
            if nuevo or (reasignar and cuenta["username"] in claves):
                usuario.set_password(claves[cuenta["username"]])
                usuario.save()
            usuario.groups.add(*Group.objects.filter(name__in=cuenta["grupos"]))
            extra = self.permisos(PERMISOS_EXTRA[cuenta["permisos"]])
            if extra:
                usuario.user_permissions.add(*extra)
            self.usuario[cuenta["username"]] = usuario

            perfil = UserProfile.objects.filter(user=usuario).first()
            if "cliente" in cuenta:
                if perfil is not None and perfil.beneficiary_id:
                    beneficiario = perfil.beneficiary
                else:
                    datos = cuenta["cliente"]
                    beneficiario = Beneficiary.objects.get_or_create(
                        rut=rut_de(datos["rut_base"]),
                        defaults={"name": datos["nombre"], "phone": datos["telefono"], "address": datos["direccion"]},
                    )[0]
                    if perfil is None:
                        UserProfile.objects.create(user=usuario, beneficiary=beneficiario)
                self.cliente[cuenta["username"]] = beneficiario
            elif perfil is None:
                funcionario = self.funcionarios[cuenta["ambito"]][cuenta["funcionario"]]
                UserProfile.objects.create(user=usuario, officer=funcionario)

            if nuevo:
                log_event(
                    self.usuario["admin_a"],
                    "Creación de cuenta de revisión",
                    usuario,
                    new=f"username={usuario.username}, rol={cuenta['rol']}, grupos={','.join(cuenta['grupos'])}",
                )

    # ------------------------------------------------------------------------------------------------------------
    # Beneficiarios y organizaciones
    # ------------------------------------------------------------------------------------------------------------
    def beneficiarios_y_organizaciones(self):
        azar = self.azar
        filas = []
        for i in range(BENEFICIARIOS):
            filas.append(
                Beneficiary(
                    rut=rut_de(14_000_000 + i * 17),
                    name=nombre_persona(azar),
                    phone=telefono(azar) if azar.random() > 0.05 else None,
                    address=f"{azar.choice(CALLES)} {azar.randint(1, 3500)}, La Serena",
                )
            )
        existentes = set(Beneficiary.objects.filter(rut__in=[f.rut for f in filas]).values_list("rut", flat=True))
        Beneficiary.objects.bulk_create([f for f in filas if f.rut not in existentes], batch_size=500)
        self.beneficiarios = list(Beneficiary.objects.filter(rut__in=[f.rut for f in filas]).order_by("rut"))

        filas = []
        for i in range(ORGANIZACIONES):
            letra = AMBITOS[i % 2]["letra"]
            territorio = self.territorios[letra][(i // 2) % len(self.territorios[letra])]
            tipo = TIPOS_ORGANIZACION[i % len(TIPOS_ORGANIZACION)]
            nombre = f"{tipo} {LUGARES[i % len(LUGARES)]} {i // len(LUGARES) + 1}".upper()
            filas.append(
                CommunityOrganization(
                    registry_number=7001 + i,
                    name=nombre,
                    legal_address=f"{azar.choice(CALLES)} {azar.randint(1, 3500)}, La Serena",
                    territory=territorio,
                    territory_text=territorio.name.upper()[:100],
                    active_members=azar.randint(15, 220),
                    constitution_date=date(2000, 1, 1) + timedelta(days=azar.randint(0, 9000)),
                    verified=azar.random() > 0.3,
                )
            )
        numeros = [f.registry_number for f in filas]
        existentes = set(CommunityOrganization.objects.filter(registry_number__in=numeros).values_list("registry_number", flat=True))
        CommunityOrganization.objects.bulk_create([f for f in filas if f.registry_number not in existentes], batch_size=500)
        self.organizaciones = {letra: [] for letra in self.delegacion}
        for organizacion in CommunityOrganization.objects.filter(registry_number__in=numeros).select_related("territory").order_by("registry_number"):
            letra = "N" if organizacion.territory.delegation_id == self.delegacion["N"].pk else "S"
            self.organizaciones[letra].append(organizacion)

    # ------------------------------------------------------------------------------------------------------------
    # Compromisos (agenda colectiva)
    # ------------------------------------------------------------------------------------------------------------
    def compromisos(self):
        azar = self.azar
        self.compromisos_por_ambito = {}
        for ambito in AMBITOS:
            letra = ambito["letra"]
            delegacion = self.delegacion[letra]
            usados, filas = set(), []
            for i in range(COMPROMISOS):
                while True:
                    solicitante = nombre_persona(azar) if i % 3 else f"{azar.choice(TIPOS_ORGANIZACION)} {azar.choice(LUGARES)}"
                    vence = FECHA_BASE + timedelta(days=azar.randint(-150, 90))
                    if (solicitante, vence) not in usados:
                        usados.add((solicitante, vence))
                        break
                estado = elegir_con_peso(
                    azar,
                    [
                        (Commitment.Status.SUBMITTED, 2),
                        (Commitment.Status.PENDING, 3),
                        (Commitment.Status.IN_PROGRESS, 3),
                        (Commitment.Status.FULFILLED, 4),
                    ],
                )
                fila = Commitment(
                    source=azar.choice(ORIGENES_COMPROMISO),
                    request_date=vence - timedelta(days=azar.randint(15, 80)),
                    description=azar.choice(DESCRIPCIONES_COMPROMISO),
                    requester=solicitante,
                    requester_type=(Commitment.RequesterType.INTERNAL if i % 5 == 0 else Commitment.RequesterType.EXTERNAL),
                    territory=azar.choice(self.territorios[letra]),
                    due_date=vence,
                    support=azar.choice(APOYOS_COMPROMISO),
                    status=estado,
                    notes="" if azar.random() < 0.5 else "Se coordinó con la dirigente del sector.",
                    responsible_officer=azar.choice(self.de_terreno(letra)),
                    delegation=delegacion,
                )
                fila._archivado = azar.random() < 0.08
                fila._sello = momento(fila.request_date, i)
                filas.append(fila)
            clave = lambda c: (c.delegation_id, c.requester, c.due_date)  # noqa: E731
            existentes = set(
                Commitment._base_manager.filter(delegation=delegacion).values_list("delegation_id", "requester", "due_date")
            )
            nuevas = [f for f in filas if clave(f) not in existentes]
            Commitment.objects.bulk_create(nuevas, batch_size=500)
            guardadas = {clave(c): c for c in Commitment._base_manager.filter(delegation=delegacion)}
            sellos = []
            for fila in nuevas:
                objeto = guardadas[clave(fila)]
                objeto.created_at = fila._sello
                if fila._archivado:
                    objeto.deleted_at = fila._sello + timedelta(days=3)
                sellos.append(objeto)
            Commitment.objects.bulk_update(sellos, ["created_at", "deleted_at"], batch_size=500)
            self.compromisos_por_ambito[letra] = [guardadas[clave(f)] for f in filas]

    # ------------------------------------------------------------------------------------------------------------
    # Compromisos de terreno (sección Compromisos)
    # ------------------------------------------------------------------------------------------------------------
    def compromisos_de_terreno(self):
        """Se carga al final para que el resto de los datos salga exactamente igual que antes de existir esta sección."""
        azar = self.azar
        for ambito in AMBITOS:
            letra = ambito["letra"]
            delegacion = self.delegacion[letra]
            usados, filas = set(), []
            for i in range(COMPROMISOS_DE_TERRENO):
                while True:
                    solicitante = nombre_persona(azar) if i % 4 else f"{azar.choice(TIPOS_ORGANIZACION)} {azar.choice(LUGARES)}"
                    vence = FECHA_BASE + timedelta(days=azar.randint(-120, 60))
                    if (solicitante, vence) not in usados:
                        usados.add((solicitante, vence))
                        break
                estado = elegir_con_peso(
                    azar,
                    [
                        (Commitment.Status.SUBMITTED, 3),
                        (Commitment.Status.PENDING, 2),
                        (Commitment.Status.IN_PROGRESS, 2),
                        (Commitment.Status.FULFILLED, 4),
                    ],
                )
                fila = Commitment(
                    source=azar.choice(ORIGENES_TERRENO),
                    request_date=vence - timedelta(days=azar.randint(5, 40)),
                    description=azar.choice(DESCRIPCIONES_TERRENO),
                    requester=solicitante,
                    requester_type=Commitment.RequesterType.EXTERNAL,
                    territory=azar.choice(self.territorios[letra]),
                    due_date=vence,
                    support=azar.choice(APOYOS_COMPROMISO),
                    status=estado,
                    notes="" if azar.random() < 0.6 else "Se coordinó la visita con la dirigente del sector.",
                    physical=True,
                    responsible_officer=azar.choice(self.de_terreno(letra)),
                    delegation=delegacion,
                )
                fila._archivado = azar.random() < 0.05
                fila._sello = momento(fila.request_date, i)
                filas.append(fila)
            clave = lambda c: (c.delegation_id, c.requester, c.due_date)  # noqa: E731
            existentes = set(
                Commitment._base_manager.filter(delegation=delegacion, physical=True).values_list(
                    "delegation_id", "requester", "due_date"
                )
            )
            nuevas = [f for f in filas if clave(f) not in existentes]
            Commitment.objects.bulk_create(nuevas, batch_size=500)
            guardadas = {clave(c): c for c in Commitment._base_manager.filter(delegation=delegacion, physical=True)}
            sellos = []
            for fila in nuevas:
                objeto = guardadas[clave(fila)]
                objeto.created_at = fila._sello
                if fila._archivado:
                    objeto.deleted_at = fila._sello + timedelta(days=3)
                sellos.append(objeto)
            Commitment.objects.bulk_update(sellos, ["created_at", "deleted_at"], batch_size=500)

    # ------------------------------------------------------------------------------------------------------------
    # Atenciones
    # ------------------------------------------------------------------------------------------------------------
    def atenciones(self):
        azar = self.azar
        carga = {}  # (funcionario, día) -> atenciones del mismo día (máximo diario por funcionario)
        usadas = set()
        especificaciones = []
        for ambito in AMBITOS:
            letra = ambito["letra"]
            terreno = self.de_terreno(letra)
            clientes = [
                self.cliente[cuenta["username"]]
                for cuenta in CUENTAS
                if "cliente" in cuenta and cuenta["ambito"] == letra
            ]
            total = ATENCIONES + ATENCIONES_CLIENTE * len(clientes)
            for i in range(total):
                funcionario = terreno[i % len(terreno)]
                cliente = clientes[(i - ATENCIONES) // ATENCIONES_CLIENTE] if i >= ATENCIONES else None
                organizacion = None
                if cliente is not None:
                    persona = cliente
                elif azar.random() < 0.10:
                    persona, organizacion = None, azar.choice(self.organizaciones[letra])
                else:
                    persona = azar.choice(self.beneficiarios)
                while True:
                    dia = dia_habil(FECHA_BASE - timedelta(days=azar.randint(0, DIAS_ATRAS)))
                    clave = (funcionario.pk, dia, persona.pk if persona else None, organizacion.pk if organizacion else None)
                    if clave not in usadas and carga.get((funcionario.pk, dia), 0) < 7:
                        usadas.add(clave)
                        carga[(funcionario.pk, dia)] = carga.get((funcionario.pk, dia), 0) + 1
                        break
                item = elegir_con_peso(azar, self.items)
                estado = elegir_con_peso(
                    azar,
                    [(Activity.Status.REGISTERED, 3), (Activity.Status.IN_PROGRESS, 4), (Activity.Status.CLOSED, 4)],
                )
                sin_contacto = cliente is None and azar.random() < 0.08
                solicitud = azar.choice(SOLICITUDES)
                if cliente is not None:
                    solicitud += f" ({cliente.name.split()[0]})"
                if persona is not None:
                    nombre_contacto, fono = persona.name, persona.phone or ""
                else:
                    nombre_contacto, fono = f"Directiva {organizacion.name.title()}"[:100], telefono(azar)
                if sin_contacto:
                    nombre_contacto, fono = "", ""
                fila = Activity(
                    date=dia,
                    request_description=solicitud + ".",
                    action_taken="" if estado == Activity.Status.REGISTERED else azar.choice(ACCIONES_TOMADAS),
                    contact_name=nombre_contacto,
                    phone=fono,
                    beneficiary=persona,
                    organization=organizacion,
                    status=estado,
                    requires_visit=azar.random() < 0.25,
                    requester_is_delegate=azar.random() < 0.04,
                    item=item,
                    service=azar.choice(self.servicios + [None]),
                    delegation=self.delegacion[letra],
                    author_officer=funcionario,
                )
                fila.refresh_scoring()
                fila._archivado = cliente is None and azar.random() < 0.06
                fila._sello = momento(dia, i)
                fila._ambito = letra
                especificaciones.append(fila)

        funcionarios = [f.author_officer for f in especificaciones]
        clave = lambda a: (a.author_officer_id, a.date, a.beneficiary_id, a.organization_id)  # noqa: E731
        existentes = set(
            Activity._base_manager.filter(author_officer__in=set(funcionarios)).values_list(
                "author_officer_id", "date", "beneficiary_id", "organization_id"
            )
        )
        nuevas = [f for f in especificaciones if clave(f) not in existentes]
        # Los primeros compromisos de cada ámbito quedan ligados a una atención (relación uno a uno).
        pendientes = {letra: iter(self.compromisos_por_ambito[letra][:ATENCIONES_CON_COMPROMISO]) for letra in self.delegacion}
        ligadas = set(Activity._base_manager.exclude(commitment__isnull=True).values_list("commitment_id", flat=True))
        de_clientes = {b.pk for b in self.cliente.values()}
        for fila in nuevas:
            if fila._archivado or fila.beneficiary_id in de_clientes:
                continue
            compromiso = next(pendientes[fila._ambito], None)
            if compromiso is not None and compromiso.pk not in ligadas:
                fila.commitment = compromiso
                fila.added_to_pipeline = True
        Activity.objects.bulk_create(nuevas, batch_size=500)

        guardadas = {
            clave(a): a for a in Activity._base_manager.filter(author_officer__in=set(funcionarios))
        }
        sellos = []
        for fila in nuevas:
            objeto = guardadas[clave(fila)]
            objeto.created_at = fila._sello
            objeto.deleted_at = fila._sello + timedelta(days=2) if fila._archivado else None
            sellos.append(objeto)
        Activity.objects.bulk_update(sellos, ["created_at", "deleted_at"], batch_size=500)
        for fila in especificaciones:
            fila.pk = guardadas[clave(fila)].pk
        self.especificaciones = especificaciones

    # ------------------------------------------------------------------------------------------------------------
    # Gestiones de seguimiento
    # ------------------------------------------------------------------------------------------------------------
    def gestiones(self):
        azar = self.azar
        filas = []
        for fila in self.especificaciones:
            if fila._archivado:
                continue
            cuantas = elegir_con_peso(azar, [(0, 4), (1, 3), (2, 2), (3, 1)])
            for secuencia in range(1, cuantas + 1):
                fecha = min(fila.date + timedelta(days=secuencia * azar.randint(2, 9)), FECHA_BASE)
                visita = azar.random() < 0.4
                gestion = Followup(
                    sequence_number=secuencia,
                    management_type=azar.choice(self.tipos_gestion) if self.tipos_gestion else None,
                    date=fecha,
                    result=azar.choice(RESULTADOS_GESTION),
                    scheduled_visit_date=fecha + timedelta(days=3) if visita else None,
                    visit_date=fecha + timedelta(days=3) if visita and fecha + timedelta(days=3) <= FECHA_BASE else None,
                    activity_id=fila.pk,
                )
                gestion._sello = momento(fecha, secuencia)
                filas.append(gestion)
        pks = [f.activity_id for f in filas]
        existentes = set(
            Followup._base_manager.filter(activity_id__in=pks).values_list("activity_id", "sequence_number")
        )
        clave = lambda g: (g.activity_id, g.sequence_number)  # noqa: E731
        nuevas = [f for f in filas if clave(f) not in existentes]
        Followup.objects.bulk_create(nuevas, batch_size=500)
        guardadas = {clave(g): g for g in Followup._base_manager.filter(activity_id__in=pks)}
        sellos = []
        for fila in nuevas:
            objeto = guardadas[clave(fila)]
            objeto.created_at = fila._sello
            sellos.append(objeto)
        Followup.objects.bulk_update(sellos, ["created_at"], batch_size=500)

    # ------------------------------------------------------------------------------------------------------------
    # Evidencias y validaciones
    # ------------------------------------------------------------------------------------------------------------
    def evidencias_y_validaciones(self):
        azar = self.azar
        for ambito in AMBITOS:
            letra = ambito["letra"]
            delegacion = self.delegacion[letra]
            prefijo = prefijo_evidencia(delegacion)
            elegibles = [
                f for f in self.especificaciones if f._ambito == letra and not f._archivado
            ]
            revisor = self.funcionarios[letra][POSICION_JEFATURA]
            for numero, fila in enumerate(elegibles[: EVIDENCIAS * 3 : 3][:EVIDENCIAS], start=1):
                estado = elegir_con_peso(
                    azar,
                    [
                        (Evidence.ReviewStatus.PENDING, 3),
                        (Evidence.ReviewStatus.APPROVED, 5),
                        (Evidence.ReviewStatus.REJECTED, 2),
                    ],
                )
                codigo = f"{prefijo}{numero:04d}"
                subida = momento(fila.date + timedelta(days=1), numero)
                if Evidence._base_manager.filter(unique_code=codigo).exists():
                    continue
                contenido = pdf_minimo(f"Evidencia de prueba {codigo}")
                evidencia = Evidence(
                    unique_code=codigo,
                    review_status=estado,
                    activity_id=fila.pk,
                    author_officer=fila.author_officer,
                    metadata="\n".join(
                        [f"Archivo original: {codigo.lower()}.pdf", "Tipo: PDF", f"Tamaño: {len(contenido) / 1024:.1f} KB"]
                    ),
                )
                evidencia.file_link.save(f"{codigo.lower()}.pdf", ContentFile(contenido), save=False)
                evidencia.save()
                Evidence.objects.filter(pk=evidencia.pk).update(created_at=subida, uploaded_at=subida)
                if estado != Evidence.ReviewStatus.PENDING:
                    aprobada = estado == Evidence.ReviewStatus.APPROVED
                    validacion = Validation.objects.create(
                        evidence=evidencia,
                        reviewer_officer=revisor,
                        decision=Validation.Decision.APPROVED if aprobada else Validation.Decision.REJECTED,
                        result="Evidencia conforme, se aprueba." if aprobada else "Archivo ilegible: se rechaza.",
                        notes="" if aprobada else "Se pide volver a subir el documento con mejor calidad.",
                    )
                    Validation.objects.filter(pk=validacion.pk).update(
                        created_at=subida + timedelta(days=1), date=subida + timedelta(days=1)
                    )

    # ------------------------------------------------------------------------------------------------------------
    # Felicitaciones y reclamos (con su ajuste automático)
    # ------------------------------------------------------------------------------------------------------------
    def felicitaciones_y_reclamos(self):
        azar = self.azar
        registra = self.usuario["admin_a"]
        pares = set()
        for ambito in AMBITOS:
            letra = ambito["letra"]
            oficiales = list(self.funcionarios[letra].values())
            usados = set(
                Feedback._base_manager.filter(officer__delegation=self.delegacion[letra]).values_list(
                    "officer_id", "date", "contact_name", "kind"
                )
            )
            for i in range(FELICITACIONES_Y_RECLAMOS):
                funcionario = oficiales[(i * 7) % len(oficiales)]
                tipo = Feedback.Kind.COMPLIMENT if azar.random() < 0.6 else Feedback.Kind.COMPLAINT
                dia = FECHA_BASE - timedelta(days=azar.randint(0, 200))
                contacto = nombre_persona(azar)
                canal = azar.choice([Feedback.Channel.EMAIL, Feedback.Channel.WHATSAPP, Feedback.Channel.LOGBOOK])
                texto = azar.choice(
                    DESCRIPCIONES_FELICITACION if tipo == Feedback.Kind.COMPLIMENT else DESCRIPCIONES_RECLAMO
                )
                telefono_contacto = telefono(azar)  # se sortea siempre: lo que sale no depende de lo que ya exista
                clave = (funcionario.pk, dia, contacto, tipo.value)
                if clave in usados:
                    continue
                usados.add(clave)
                registro = Feedback(
                    kind=tipo,
                    date=dia,
                    contact_name=contacto,
                    contact=(
                        f"{slugify(contacto).replace('-', '.')}@correo.example"
                        if canal == Feedback.Channel.EMAIL
                        else telefono_contacto
                    ),
                    channel=canal,
                    officer=funcionario,
                    description=texto,
                    period=self.periodo,
                    registered_by=registra,
                )
                registro.support.save(
                    f"respaldo-{i:03d}.pdf", ContentFile(pdf_minimo(f"Respaldo de prueba {contacto}")), save=False
                )
                registro.save()
                Feedback.objects.filter(pk=registro.pk).update(created_at=momento(dia, i))
                pares.add((funcionario.pk, self.periodo.pk))
        for funcionario_id, periodo_id in sorted(pares):
            feedback_rules.sync(funcionario_id, periodo_id)

    # ------------------------------------------------------------------------------------------------------------
    # Ausencias
    # ------------------------------------------------------------------------------------------------------------
    def ausencias(self):
        azar = self.azar
        registra = self.usuario["admin_a"]
        tipos = [Absence.Kind.LICENSE, Absence.Kind.VACATION, Absence.Kind.ADMINISTRATIVE, Absence.Kind.EMERGENCY, Absence.Kind.COMPENSATORY]
        for ambito in AMBITOS:
            letra = ambito["letra"]
            for i, funcionario in enumerate(list(self.funcionarios[letra].values())[:AUSENCIAS]):
                inicio = FECHA_BASE - timedelta(days=azar.randint(15, 200))
                duracion = azar.randint(1, 12)
                tipo = tipos[i % len(tipos)]
                notas = azar.choice(NOTAS_AUSENCIA)
                if Absence._base_manager.filter(officer=funcionario, kind=tipo, start_date=inicio).exists():
                    continue
                ausencia = Absence.objects.create(
                    officer=funcionario,
                    kind=tipo,
                    start_date=inicio,
                    end_date=inicio + timedelta(days=duracion),
                    notes=notas,
                    registered_by=registra,
                )
                Absence.objects.filter(pk=ausencia.pk).update(created_at=momento(inicio, i))

    # ------------------------------------------------------------------------------------------------------------
    # Metas (los indicadores salen del cálculo real, al final)
    # ------------------------------------------------------------------------------------------------------------
    def metas(self):
        for ambito in AMBITOS:
            for funcionario in self.de_terreno(ambito["letra"]):
                Goal.objects.get_or_create(
                    item=self.item_social,
                    officer=funcionario,
                    period=self.periodo,
                    defaults={"target_value": 36, "unit": "atenciones", "weight": 100},
                )
        Goal.objects.get_or_create(
            item=self.item_ayudas,
            position=self.cargo["Encargado Social"],
            period=self.periodo,
            defaults={"target_value": 50, "unit": "entregas", "weight": 80},
        )

    # ------------------------------------------------------------------------------------------------------------
    # Informe y verificación
    # ------------------------------------------------------------------------------------------------------------
    def modelos_de_negocio(self):
        for etiqueta in APLICACIONES_PROPIAS:
            yield from sorted(apps.get_app_config(etiqueta).get_models(), key=lambda m: m._meta.label)

    def total_negocio(self):
        return sum(modelo._base_manager.count() for modelo in self.modelos_de_negocio())

    def informe(self):
        self.stdout.write("\nTotal por modelo (sin sesiones, permisos ni tablas internas de Django):\n")
        self.stdout.write(f"{'Modelo':<40}{'Total':>8}{'Activos':>10}{'Archivados':>12}")
        total = 0
        for modelo in self.modelos_de_negocio():
            todos = modelo._base_manager.count()
            archivados = (
                modelo._base_manager.filter(deleted_at__isnull=False).count()
                if any(f.name == "deleted_at" for f in modelo._meta.fields)
                else 0
            )
            total += todos
            self.stdout.write(f"{modelo._meta.label:<40}{todos:>8}{todos - archivados:>10}{archivados:>12}")
        self.stdout.write(f"{'TOTAL':<40}{total:>8}\n")
        return total

    def verificar(self, total):
        import core.registry  # noqa: F401  (registra los CRUD)
        from core.crud import registry

        problemas = []
        if total < MINIMO_TOTAL:
            problemas.append(f"Hay {total} registros de negocio y se piden al menos {MINIMO_TOTAL}.")

        self.stdout.write(f"{'CRUD':<28}{'Norte':>8}{'Sur':>8}{'Total':>8}  Evaluado")
        for crud in registry.all():
            if crud.model._meta.app_label in ("auth", "core") or crud.model is Item:
                continue
            activos = crud.model._base_manager.filter(deleted_at__isnull=True) if hasattr(crud.model, "deleted_at") else crud.model._base_manager.all()
            if crud.queryset_filter:
                activos = activos.filter(**crud.queryset_filter)
            cifras = [None, None]
            if crud.delegation_lookup:
                cifras = [
                    activos.filter(**{crud.delegation_lookup: self.delegacion[ambito["letra"]]}).count()
                    for ambito in AMBITOS
                ]
            cuenta = activos.count()
            evaluado = crud.slug in CRUDS_EVALUADOS
            self.stdout.write(
                f"{crud.slug:<28}{'—' if cifras[0] is None else cifras[0]:>8}"
                f"{'—' if cifras[1] is None else cifras[1]:>8}{cuenta:>8}  {'sí' if evaluado else ''}"
            )
            if evaluado:
                minimos = [c for c in cifras if c is not None] or [cuenta]
                if cuenta < MINIMO_POR_CRUD or min(minimos) < MINIMO_POR_CRUD:
                    problemas.append(
                        f"El CRUD evaluado «{crud.slug}» tiene {cuenta} registros activos "
                        f"({', '.join(str(c) for c in cifras if c is not None) or 'sin ámbitos'}) y se piden {MINIMO_POR_CRUD}."
                    )

        problemas += self.verificar_permisos(registry)
        if problemas:
            raise CommandError("La verificación falló:\n- " + "\n- ".join(problemas))
        self.stdout.write(self.style.SUCCESS("\nVerificación correcta: totales, mínimos por CRUD evaluado y permisos de las cuentas."))

    def verificar_permisos(self, registry):
        User = get_user_model()
        problemas = []
        cruds = registry.all()
        evaluados = [registry.get(slug) for slug in CRUDS_EVALUADOS]
        admin = User.objects.get(username="admin_a")
        if admin.is_superuser:
            problemas.append("admin_a no debe ser superusuario.")
        for crud in evaluados:
            if not (crud.has_perm(admin, "delete") and crud.has_perm(admin, "add") and crud.has_perm(admin, "change")):
                problemas.append(f"admin_a debe poder crear, editar y eliminar/archivar en «{crud.slug}».")
        if not admin.has_perm("auth.add_user"):
            problemas.append("admin_a debe poder gestionar usuarios.")
        editor = User.objects.get(username="editor_a")
        for crud in cruds:
            if crud.has_perm(editor, "delete"):
                problemas.append(f"editor_a no debe poder eliminar ni archivar en «{crud.slug}».")
        for crud in evaluados:
            if not (crud.has_perm(editor, "add") and crud.has_perm(editor, "change")):
                problemas.append(f"editor_a debe poder crear y editar en «{crud.slug}».")
        for nombre in ("lector_a", "lector_b"):
            lector = User.objects.get(username=nombre)
            for crud in cruds:
                for accion in ("add", "change", "delete"):
                    if crud.has_perm(lector, accion):
                        problemas.append(f"{nombre} solo debe consultar y exportar, pero puede «{accion}» en «{crud.slug}».")
            for crud in evaluados:
                if not crud.has_perm(lector, "view"):
                    problemas.append(f"{nombre} debe poder ver «{crud.slug}».")
        return problemas
