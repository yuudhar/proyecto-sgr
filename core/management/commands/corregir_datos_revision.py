"""v45 a v49: corrige los datos de revisión que ya están cargados para que tengan sentido entre sí.

Qué corrige (solo toca datos de revisión: se reconocen por sus textos, orígenes y cargos de demostración)
----------------------------------------------------------------------------------------------------------
* cargos: los funcionarios pasan a los cargos del descriptor 2026 (así su ficha muestra las funciones) y los ítems del
  cargo suman 100 %;
* identificadores: ``REV-N-001`` pasa al formato del sistema, ``F-1001``; si ese número ya es de otra persona recibe el
  siguiente libre de su delegación;
* clasificación: servicio, ítem y «requiere visita» de cada atención salen de lo que dice la solicitud;
* estados: una atención «Registrada» no tiene acciones ni gestiones, y una «Cerrada» sí tiene acción;
* compromisos: los del tubo y los de terreno nacen de su atención (mismo solicitante, fecha, funcionario), ninguno se
  solicita en el futuro y los que vencieron hace más de 30 días ya no quedan «Ingresados» o «Pendientes»;
* ausencias: la observación coincide con el tipo, tienen días hábiles y no caen sobre días con atenciones;
* cambios de trimestre: se piden antes de resolverse y se aprueban después de la fecha nueva; cada delegación usa sus
  propias cuentas (se crean ``editor_b`` y ``admin_b`` si se entrega una contraseña);
* autoría: las cartas, ausencias y ajustes de Sur quedan registrados por la cuenta de Sur (``admin_b``);
* restos (v47): lo que la auditoría marca en cualquier otro registro, aunque no sea de revisión (pruebas tempranas
  hechas a mano): atenciones «Registradas» con acciones, visitas y «tubo» sin su compromiso, gestiones de atenciones
  archivadas o con fechas de visita al revés, compromisos vencidos sin avanzar, evidencias con autor distinto al de la
  atención, sin archivo en disco o con un estado distinto al de su última validación, e identificadores de
  funcionario fuera del formato ``F-0000``;
* periodos (v49): cada período anual pasa a cuatro trimestres (se archiva el anual): las metas, las cartas y los ajustes
  se reparten en los trimestres y los indicadores se recalculan;
* metas: la meta de atenciones se acerca a lo que de verdad se puede cumplir y se recalculan los indicadores.

Cómo se usa
-----------
``python manage.py corregir_datos_revision``            muestra lo que cambiaría, sin guardar nada (simulación);
``python manage.py corregir_datos_revision --aplicar``  lo guarda.
Se puede repetir: lo que ya está corregido no se vuelve a tocar. Con ``--solo cargos compromisos`` se eligen pasos.
Después de corregir, no se debe volver a correr ``cargar_datos_revision`` (volvería a crear los cargos y los
identificadores de antes).
"""
import os
import statistics
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from io import StringIO

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts.models import UserProfile
from core import entry_rules
from core.audit import log_event
from core.management.commands import cargar_datos_revision as carga
from evidence.models import Evidence, Validation
from operations.models import Activity, Commitment, Followup, QuarterChangeRequest
from organization.models import Item, Officer, Position, PositionItem, Service, Territory
from planning import calculation
from planning import feedback as feedback_rules
from planning.models import Absence, Adjustment, Feedback, Goal, Indicator, Period
from planning.pace import weekdays_between

# cargo de demostración -> cargo del descriptor 2026
CARGOS = {
    "Jefe de Delegación": "Delegado",
    "Encargado Social": "Gestor Social",
    "Coordinador de Terreno": "Coordinador de Servicios Comunitarios",
    "Analista de Datos": "Gestión y Planificación",
}

# (inicio de la solicitud, servicio, ítem, requiere visita)
CLASIFICACION = [
    ("Solicita certificado de residencia", "Certificado de Residencia", "Atención Social", False),
    ("Consulta por ayuda social", "Ayuda Social", "Atención Social", False),
    ("Reclama por luminaria en mal estado", None, "Coordinación Territorial", False),
    ("Pide visita domiciliaria", None, "Visita Domiciliaria", True),
    ("Consulta por subsidio de agua potable", "Ayuda Social", "Atención Social", False),
    ("Solicita orientación sobre trámites municipales", None, "Atención Social", False),
    ("Pide ayuda para postular al subsidio de vivienda", "Postulación a Subsidio", "Atención Social", False),
    ("Consulta por entrega de cajas de alimentos", "Ayuda Social", "Entrega de Ayudas Sociales", False),
    ("Solicita retiro de escombros en la vereda", None, "Coordinación Territorial", True),
    ("Pregunta cómo actualizar el Registro Social de Hogares", None, "Atención Social", False),
    ("Pide una silla de ruedas en préstamo", "Ayuda Social", "Entrega de Ayudas Sociales", False),
    ("Reclama por un árbol que obstruye el cableado", None, "Coordinación Territorial", True),
    ("Consulta por beca de arriendo para adulto mayor", "Vivienda", "Atención Social", False),
    ("Solicita apoyo para una emergencia por lluvias", "Ayuda Social", "Entrega de Ayudas Sociales", False),
    ("Pide orientación para renovar la credencial de discapacidad", None, "Atención Social", False),
    ("Consulta por talleres comunitarios del barrio", None, "Coordinación Territorial", False),
]

NOTA_POR_TIPO = {
    "license": "Licencia médica",
    "vacation": "Vacaciones",
    "administrative": "Trámite personal",
    "emergency": "Emergencia familiar",
    "compensatory": "Día compensatorio",
}

PASOS = ("cargos", "identificadores", "clasificacion", "estados", "compromisos", "ausencias", "trimestres", "autoria", "restos", "periodos", "metas")


def fila_de(texto):
    for fila in CLASIFICACION:
        if (texto or "").startswith(fila[0]):
            return fila
    return None


class Command(BaseCommand):
    help = (
        "Corrige los datos de revisión ya cargados para que tengan sentido entre sí. Sin --aplicar solo muestra lo "
        "que cambiaría. Se puede repetir."
    )

    def add_arguments(self, parser):
        parser.add_argument("--aplicar", action="store_true", help="Guarda los cambios (sin esto es una simulación).")
        parser.add_argument("--solo", nargs="+", choices=PASOS, help="Corre solo estos pasos.")
        parser.add_argument(
            "--password",
            help="Contraseña de las cuentas editor_b y admin_b si hay que crearlas (o SGR_REVISION_PASSWORD).",
        )

    # ------------------------------------------------------------------------------------------------------------
    def handle(self, *args, **opciones):
        self.aplicar = opciones["aplicar"]
        self.password = opciones.get("password") or os.environ.get(carga.PASSWORD_ENV_COMUN, "")
        self.hoy = entry_rules.portal_today()
        self.ahora = timezone.now()
        self.cuenta = defaultdict(int)
        self.avisos = []
        self.alineados = set()  # compromisos que esta corrida dejó saliendo de su atención
        pasos = opciones["solo"] or PASOS
        with transaction.atomic():
            for paso in PASOS:
                if paso in pasos:
                    getattr(self, paso)()
            if self.aplicar:
                admin = get_user_model().objects.filter(username="admin_a").first()
                if admin is not None and sum(self.cuenta.values()):
                    resumen = ", ".join(f"{k}={v}" for k, v in sorted(self.cuenta.items()))
                    log_event(admin, "Corrección de datos de revisión", admin, new=resumen[:2000])
            else:
                transaction.set_rollback(True)
        self.informe()

    def hecho(self, clave, n=1):
        if n:
            self.cuenta[clave] += n

    def aviso(self, texto):
        self.avisos.append(texto)

    def informe(self):
        titulo = "CAMBIOS GUARDADOS" if self.aplicar else "SIMULACIÓN (no se guardó nada; usa --aplicar para guardar)"
        self.stdout.write(f"\n{titulo}\n")
        if not self.cuenta:
            self.stdout.write("  Nada que corregir: los datos ya tienen sentido.")
        for clave, n in sorted(self.cuenta.items()):
            self.stdout.write(f"  {clave:<58}{n:>6}")
        for texto in self.avisos:
            self.stdout.write(self.style.WARNING(f"  Aviso: {texto}"))
        if self.aplicar:
            self.stdout.write(self.style.SUCCESS("\nListo. Corre la auditoría de datos para confirmarlo."))

    # ------------------------------------------------------------------------------------------------------------
    # 1. Cargos
    # ------------------------------------------------------------------------------------------------------------
    def cargos(self):
        call_command("cargar_funciones_cargos", stdout=StringIO())  # deja los siete cargos del descriptor
        ahora = timezone.now()
        for nombre_viejo, nombre_nuevo in CARGOS.items():
            viejo = Position._base_manager.filter(name=nombre_viejo, deleted_at__isnull=True).first()
            nuevo = Position._base_manager.filter(name__iexact=nombre_nuevo, deleted_at__isnull=True).first()
            if viejo is None or nuevo is None:
                continue
            self.hecho(f"funcionarios que pasan a «{nombre_nuevo}»", Officer._base_manager.filter(position=viejo).update(position=nuevo))
            self.hecho("metas que pasan al cargo nuevo", Goal._base_manager.filter(position=viejo).update(position=nuevo))
            for item in PositionItem._base_manager.filter(position=viejo):
                ya = PositionItem._base_manager.filter(position=nuevo, item_id=item.item_id, kind=item.kind).exists()
                if not ya:
                    PositionItem._base_manager.filter(pk=item.pk).update(position=nuevo)
                    self.hecho("ítems de cargo que pasan al cargo nuevo")
            if not (
                Officer._base_manager.filter(position=viejo).exists()
                or Goal._base_manager.filter(position=viejo).exists()
                or PositionItem._base_manager.filter(position=viejo, deleted_at__isnull=True).exists()
            ):
                Position._base_manager.filter(pk=viejo.pk).update(deleted_at=ahora)
                self.hecho("cargos de demostración archivados")
        for nombre_nuevo in CARGOS.values():
            nuevo = Position._base_manager.filter(name__iexact=nombre_nuevo, deleted_at__isnull=True).first()
            if nuevo is None:
                continue
            normales = list(
                PositionItem._base_manager.filter(
                    position=nuevo, kind="NORMAL", deleted_at__isnull=True, valid_until__isnull=True
                )
            )
            if len(normales) == 1 and normales[0].weight != 100:
                PositionItem._base_manager.filter(pk=normales[0].pk).update(weight=100)
                self.hecho("cargos cuyo ítem normal ahora pesa 100 %")

    # ------------------------------------------------------------------------------------------------------------
    # 2. Identificadores de funcionario
    # ------------------------------------------------------------------------------------------------------------
    def identificadores(self):
        for letra, bloque in (("N", 1), ("S", 2)):
            for oficial in Officer._base_manager.filter(institutional_id__startswith=f"REV-{letra}-").order_by("institutional_id"):
                numero = int(oficial.institutional_id.rsplit("-", 1)[1])
                nuevo = f"F-{bloque}{numero:03d}"
                if Officer._base_manager.filter(institutional_id=nuevo).exclude(pk=oficial.pk).exists():
                    nuevo = oficial.next_institutional_id()  # ese número ya es de otra persona: el siguiente libre
                Officer._base_manager.filter(pk=oficial.pk).update(institutional_id=nuevo)
                self.hecho("identificadores de funcionario con el formato F-0000")

    # ------------------------------------------------------------------------------------------------------------
    # 3. Servicio, ítem y visita de cada atención según su solicitud
    # ------------------------------------------------------------------------------------------------------------
    def clasificacion(self):
        servicios = {s.name: s for s in Service._base_manager.filter(deleted_at__isnull=True)}
        items = {i.name: i for i in Item._base_manager.filter(deleted_at__isnull=True).select_related("parent_item")}
        for a in Activity._base_manager.select_related("item__parent_item", "beneficiary"):
            fila = fila_de(a.request_description)
            if fila is None:
                continue
            _texto, servicio, item, visita = fila
            nuevo_item = items.get(item)
            if nuevo_item is None:
                continue
            nuevo_servicio = servicios.get(servicio) if servicio else None
            if nuevo_servicio is None and servicio:
                continue
            cambios = {}
            if a.service_id != (nuevo_servicio.pk if nuevo_servicio else None):
                cambios["service"] = nuevo_servicio
            if a.item_id != nuevo_item.pk:
                cambios["item"] = nuevo_item
            if a.requires_visit != visita:
                cambios["requires_visit"] = visita
            if not cambios:
                continue
            a.item, a.service, a.requires_visit = nuevo_item, nuevo_servicio, visita
            a.refresh_scoring()
            Activity._base_manager.filter(pk=a.pk).update(
                item=nuevo_item,
                service=nuevo_servicio,
                requires_visit=visita,
                counts_for_score=a.counts_for_score,
                no_score_reason=a.no_score_reason,
            )
            self.hecho("atenciones con servicio, ítem y visita según su solicitud")

    # ------------------------------------------------------------------------------------------------------------
    # 4. Estado de las atenciones
    # ------------------------------------------------------------------------------------------------------------
    def estados(self):
        gestiones = defaultdict(int)
        for g in Followup._base_manager.filter(deleted_at__isnull=True):
            gestiones[g.activity_id] += 1
        acciones = carga.ACCIONES_TOMADAS
        for a in Activity._base_manager.all():
            if fila_de(a.request_description) is None:
                continue
            nuevo, accion = a.status, a.action_taken
            if a.status == "registered" and (a.date < self.hoy - timedelta(days=60)):
                nuevo = "closed"
                accion = accion or acciones[a.pk % len(acciones)]
            elif a.status == "registered" and (accion or gestiones[a.pk]):
                nuevo = "in_progress"
            elif a.status == "in_progress" and not accion and not gestiones[a.pk]:
                accion = acciones[a.pk % len(acciones)]
            elif a.status == "closed" and not accion:
                accion = acciones[a.pk % len(acciones)]
            if nuevo != a.status or accion != a.action_taken:
                Activity._base_manager.filter(pk=a.pk).update(status=nuevo, action_taken=accion)
                self.hecho("atenciones con estado y acción coherentes")

    # ------------------------------------------------------------------------------------------------------------
    # 5. Compromisos
    # ------------------------------------------------------------------------------------------------------------
    def alinear(self, c, a, fisico):
        """Deja el compromiso tal como lo habría creado la atención (operations/pipeline.py)."""
        creado = carga.momento(a.date, a.pk)
        campos = {
            "source": f"Atención ATN{a.pk:05d}"[:100],
            "request_date": a.date,
            "description": a.request_description or None,
            "requester": (a.contact_name or "Sin nombre")[:100],
            "responsible_officer_id": a.author_officer_id,
            "delegation_id": a.delegation_id,
            "physical": fisico,
            "due_date": c.due_date if c.due_date >= a.date else a.date + timedelta(days=14),
            "created_at": creado,
        }
        if c.deleted_at:
            campos["deleted_at"] = creado + timedelta(days=3)
        Commitment._base_manager.filter(pk=c.pk).update(**campos)
        self.alineados.add(c.pk)

    def huerfano_de(self, a):
        """Compromiso suelto que ya nació de esta atención (se reutiliza en vez de crear un duplicado)."""
        enlazados = Activity._base_manager.filter(commitment__isnull=False).values("commitment_id")
        return (
            Commitment._base_manager.filter(source=f"Atención ATN{a.pk:05d}"[:100], deleted_at__isnull=True)
            .exclude(pk__in=enlazados)
            .order_by("pk")
            .first()
        )

    def estado_por_fecha(self, pk, vence):
        if vence < self.hoy - timedelta(days=30):
            return "in_progress" if pk % 3 == 0 else "fulfilled"
        if vence < self.hoy:
            return "in_progress"
        return "pending"

    def compromisos(self):
        semillas = set(carga.ORIGENES_COMPROMISO) | set(carga.ORIGENES_TERRENO)
        terreno = set(carga.ORIGENES_TERRENO)
        compromisos = {c.pk: c for c in Commitment._base_manager.all()}
        atenciones = list(Activity._base_manager.select_related("author_officer"))
        enlazados = {a.commitment_id for a in atenciones if a.commitment_id}

        # a) Los compromisos que ya están enlazados a una atención salen de ella
        for a in atenciones:
            c = compromisos.get(a.commitment_id) if a.commitment_id else None
            if c is not None and c.source in semillas:
                self.alinear(c, a, a.requires_visit)
                self.hecho("compromisos enlazados que ahora salen de su atención")

        # b) Cada atención con visita tiene su compromiso de terreno (se reutilizan los de terreno sueltos)
        sueltos = defaultdict(list)
        for c in sorted(compromisos.values(), key=lambda x: x.pk):
            if c.physical and c.source in terreno and c.pk not in enlazados:
                sueltos[c.delegation_id].append(c)
        territorios = defaultdict(list)
        for t in Territory._base_manager.filter(deleted_at__isnull=True).order_by("pk"):
            territorios[t.delegation_id].append(t)
        for a in atenciones:
            if not (a.requires_visit and not a.commitment_id and a.deleted_at is None and fila_de(a.request_description)):
                continue
            propio = self.huerfano_de(a)
            if propio is not None:
                self.alinear(propio, a, True)
                Activity._base_manager.filter(pk=a.pk).update(commitment=propio, added_to_pipeline=True)
                self.hecho("atenciones que recuperan su propio compromiso suelto")
            elif sueltos[a.delegation_id]:
                c = sueltos[a.delegation_id].pop(0)
                self.alinear(c, a, True)
                Activity._base_manager.filter(pk=a.pk).update(commitment=c, added_to_pipeline=True)
                self.hecho("atenciones con visita enlazadas a un compromiso de terreno ya existente")
            elif territorios[a.delegation_id]:
                lista = territorios[a.delegation_id]
                vence = a.date + timedelta(days=10)
                c = Commitment.objects.create(
                    source=f"Atención ATN{a.pk:05d}"[:100],
                    request_date=a.date,
                    description=a.request_description or None,
                    requester=(a.contact_name or "Sin nombre")[:100],
                    requester_type="EXTERNAL",
                    territory=lista[a.pk % len(lista)],
                    due_date=vence,
                    status=self.estado_por_fecha(a.pk, vence),
                    physical=True,
                    responsible_officer_id=a.author_officer_id,
                    delegation_id=a.delegation_id,
                )
                Commitment._base_manager.filter(pk=c.pk).update(created_at=carga.momento(a.date, a.pk))
                Activity._base_manager.filter(pk=a.pk).update(commitment=c, added_to_pipeline=True)
                self.alineados.add(c.pk)
                self.hecho("compromisos de terreno nuevos para atenciones con visita")
        sobran = sum(len(v) for v in sueltos.values())
        if sobran:
            self.aviso(f"quedan {sobran} compromisos de terreno sin atención de origen (no había más atenciones con visita).")

        # c) Ninguno se solicita en el futuro y los vencidos ya no quedan sin avanzar
        for c in Commitment._base_manager.all():
            if not (c.source in semillas or c.pk in self.alineados):
                continue
            cambios = {}
            solicitud = c.request_date
            if solicitud and solicitud > self.hoy:
                solicitud = min(solicitud, c.due_date - timedelta(days=15), self.hoy - timedelta(days=7))
                cambios["request_date"] = solicitud
            if c.status == "fulfilled" and c.due_date > self.hoy:
                base = solicitud or c.request_date
                cambios["due_date"] = min(self.hoy, max(base + timedelta(days=1), self.hoy - timedelta(days=3)))
                self.hecho("compromisos realizados con fecha comprometida ya cumplida")
            if cambios or c.created_at > self.ahora:
                creado = carga.momento(solicitud or c.due_date, c.pk)
                cambios["created_at"] = creado
                if c.deleted_at:
                    cambios["deleted_at"] = creado + timedelta(days=3)
            if c.status in ("submitted", "pending") and c.due_date < self.hoy - timedelta(days=30):
                cambios["status"] = "in_progress" if c.pk % 3 == 0 else "fulfilled"
                self.hecho("compromisos vencidos que avanzan de estado")
            if cambios:
                Commitment._base_manager.filter(pk=c.pk).update(**cambios)
                if "request_date" in cambios or "created_at" in cambios:
                    self.hecho("compromisos con fecha de solicitud que no es futura")

    # ------------------------------------------------------------------------------------------------------------
    # 6. Ausencias
    # ------------------------------------------------------------------------------------------------------------
    def ausencias(self):
        con_atencion = defaultdict(set)
        for a in Activity._base_manager.filter(deleted_at__isnull=True):
            if a.date.weekday() < 5:
                con_atencion[a.author_officer_id].add(a.date)
        todas = list(Absence._base_manager.filter(deleted_at__isnull=True))
        for ausencia in todas:
            if ausencia.notes not in carga.NOTAS_AUSENCIA:
                continue
            inicio, fin = ausencia.start_date, ausencia.end_date
            largo = (fin - inicio).days
            if weekdays_between(inicio, fin) == 0:
                inicio += timedelta(days=(7 - inicio.weekday()) % 7)
                fin = inicio + timedelta(days=largo)

            def choca(desde, hasta):
                dias = {desde + timedelta(days=i) for i in range((hasta - desde).days + 1)}
                if dias & con_atencion[ausencia.officer_id]:
                    return True
                return any(
                    o.pk != ausencia.pk and o.officer_id == ausencia.officer_id and o.start_date <= hasta and o.end_date >= desde
                    for o in todas
                )

            intentos = 0
            while choca(inicio, fin) and intentos < 60:
                inicio, fin = inicio + timedelta(days=7), fin + timedelta(days=7)
                intentos += 1
            cambios = {}
            if (inicio, fin) != (ausencia.start_date, ausencia.end_date):
                cambios.update(start_date=inicio, end_date=fin)
                self.hecho("ausencias movidas a días hábiles sin atenciones")
            nota = NOTA_POR_TIPO.get(ausencia.kind)
            if nota and ausencia.notes != nota:
                cambios["notes"] = nota
                self.hecho("ausencias cuya observación coincide con el tipo")
            if cambios:
                Absence._base_manager.filter(pk=ausencia.pk).update(**cambios)
                ausencia.start_date, ausencia.end_date = inicio, fin

    # ------------------------------------------------------------------------------------------------------------
    # 7. Cambios de trimestre y cuentas de cada delegación
    # ------------------------------------------------------------------------------------------------------------
    def cuentas_sur(self):
        User = get_user_model()
        usuarios = {}
        sur = next(a for a in carga.AMBITOS if a["letra"] == "S")
        for username, grupos, posicion, permisos in (
            ("editor_b", ("Funcionario",), 2, "editor"),
            ("admin_b", ("Jefatura", "Funcionario"), 1, "administrador"),
        ):
            usuario = User.objects.filter(username=username).first()
            if usuario is None:
                # se busca por nombre y delegación: el identificador cambia en el paso «identificadores»
                oficial = Officer._base_manager.filter(
                    name=carga.FUNCIONARIOS_FIJOS["S"][posicion], delegation__name=sur["delegacion"]
                ).first()
                if oficial is None:
                    self.aviso(f"no se creó «{username}»: no se encontró el funcionario {posicion} de la Delegación Sur.")
                    continue
                if UserProfile.objects.filter(officer=oficial).exists():
                    self.aviso(f"no se creó «{username}»: {oficial.name} ya tiene otra cuenta.")
                    continue
                if not self.password:
                    self.aviso(
                        f"no se creó «{username}»: falta la contraseña (usa --password o SGR_REVISION_PASSWORD). "
                        "Las solicitudes de Sur siguen a nombre de las cuentas de Norte."
                    )
                    continue
                try:
                    validate_password(self.password)
                except ValidationError as error:
                    raise CommandError(f"La contraseña no es válida: {' '.join(error.messages)}")
                usuario = User.objects.create(
                    username=username, email=f"{username}@{carga.DOMINIO_CORREO}", is_staff=False, is_superuser=False, is_active=True
                )
                usuario.set_password(self.password)
                usuario.save()
                usuario.groups.add(*Group.objects.filter(name__in=grupos))
                usuario.user_permissions.add(*carga.Command().permisos(carga.PERMISOS_EXTRA[permisos]))
                UserProfile.objects.create(user=usuario, officer=oficial)
                self.hecho("cuentas creadas para la Delegación Sur")
            usuarios[username] = usuario
        return usuarios

    def trimestres(self):
        letra_de = {a["delegacion"]: a["letra"] for a in carga.AMBITOS}
        sur = self.cuentas_sur()
        solicitudes = QuarterChangeRequest._base_manager.select_related("delegation").filter(
            reason__in=carga.MOTIVOS_TRIMESTRE
        )
        for q in solicitudes:
            cambios = {}
            if q.resolved_at:
                resuelto, creado = q.resolved_at, q.created_at
                if q.status == "approved" and q.new_date and resuelto.date() <= q.new_date:
                    resuelto = carga.momento(q.new_date + timedelta(days=1), q.pk)
                if creado >= resuelto:
                    creado = resuelto - timedelta(days=2)
                if resuelto != q.resolved_at:
                    cambios["resolved_at"] = resuelto
                    self.hecho("cambios de trimestre aprobados después de la fecha nueva")
                if creado != q.created_at:
                    cambios["created_at"] = creado
                    self.hecho("cambios de trimestre pedidos antes de resolverse")
            if letra_de.get(q.delegation.name) == "S" and "editor_b" in sur and "admin_b" in sur:
                if q.requested_by_id != sur["editor_b"].pk:
                    cambios["requested_by"] = sur["editor_b"]
                    self.hecho("cambios de trimestre de Sur pedidos por una cuenta de Sur")
                if q.resolved_by_id and q.resolved_by_id != sur["admin_b"].pk:
                    cambios["resolved_by"] = sur["admin_b"]
                    self.hecho("cambios de trimestre de Sur resueltos por una cuenta de Sur")
            if cambios:
                QuarterChangeRequest._base_manager.filter(pk=q.pk).update(**cambios)

    def autoria(self):
        """Cartas, ausencias y ajustes de Sur registrados por una cuenta de Norte pasan a la cuenta de Sur."""
        sur = self.cuentas_sur().get("admin_b")
        if sur is None:
            return
        delegacion = next(a["delegacion"] for a in carga.AMBITOS if a["letra"] == "S")
        de_usuario = {
            p.user_id: p.officer.delegation_id
            for p in UserProfile.objects.select_related("officer").filter(officer__isnull=False)
        }
        for modelo, campo, nombre in (
            (Feedback, "registered_by", "cartas de Sur registradas por una cuenta de Sur"),
            (Absence, "registered_by", "ausencias de Sur registradas por una cuenta de Sur"),
            (Adjustment, "responsible_user", "ajustes de Sur a cargo de una cuenta de Sur"),
        ):
            filas = modelo._base_manager.select_related("officer").filter(officer__delegation__name=delegacion)
            for fila in filas:
                usuario_id = getattr(fila, f"{campo}_id")
                if usuario_id is None or de_usuario.get(usuario_id) == fila.officer.delegation_id:
                    continue
                modelo._base_manager.filter(pk=fila.pk).update(**{campo: sur})
                self.hecho(nombre)

    # ------------------------------------------------------------------------------------------------------------
    # 8. Restos: lo que la auditoría marca en registros que no son de revisión
    # ------------------------------------------------------------------------------------------------------------
    def restos(self):
        self.restos_atenciones()
        self.restos_gestiones()
        self.restos_compromisos()
        self.restos_evidencias()
        self.restos_funcionarios()

    def restos_atenciones(self):
        gestiones = defaultdict(int)
        for g in Followup._base_manager.filter(deleted_at__isnull=True):
            gestiones[g.activity_id] += 1
        territorios = defaultdict(list)
        for t in Territory._base_manager.filter(deleted_at__isnull=True).order_by("pk"):
            territorios[t.delegation_id].append(t)
        atenciones = (
            Activity._base_manager.filter(deleted_at__isnull=True)
            .select_related("commitment", "beneficiary", "organization_leader")
            .order_by("pk")
        )
        for a in atenciones:
            if not (a.contact_name or "").strip():
                persona = a.organization_leader if a.organization_leader_id else a.beneficiary
                nombre = (persona.name if persona is not None else "").strip()[:100]
                if nombre:
                    Activity._base_manager.filter(pk=a.pk).update(contact_name=nombre)
                    a.contact_name = nombre
                    if a.commitment_id:
                        Commitment._base_manager.filter(pk=a.commitment_id).update(requester=nombre)
                    self.hecho("atenciones sin nombre de contacto que reciben el de la persona atendida")
            if a.status == "registered" and (a.action_taken or gestiones[a.pk]):
                Activity._base_manager.filter(pk=a.pk).update(status="in_progress")
                self.hecho("atenciones «Registradas» con acciones que pasan a «En proceso»")
            if a.commitment_id is None:
                if not (a.requires_visit or a.added_to_pipeline):
                    continue
                propio = self.huerfano_de(a)
                if propio is not None:
                    self.alinear(propio, a, a.requires_visit)
                    Activity._base_manager.filter(pk=a.pk).update(commitment=propio, added_to_pipeline=True)
                    self.hecho("atenciones que recuperan su propio compromiso suelto")
                    continue
                lista = territorios[a.delegation_id]
                if not lista:
                    self.aviso(f"la atención {a.pk} necesita un compromiso pero su delegación no tiene territorios.")
                    continue
                vence = a.date + timedelta(days=10)
                c = Commitment.objects.create(
                    source=f"Atención ATN{a.pk:05d}"[:100],
                    request_date=a.date,
                    description=a.request_description or None,
                    requester=(a.contact_name or "Sin nombre")[:100],
                    requester_type="EXTERNAL",
                    territory=lista[a.pk % len(lista)],
                    due_date=vence,
                    status=self.estado_por_fecha(a.pk, vence),
                    physical=a.requires_visit,
                    responsible_officer_id=a.author_officer_id,
                    delegation_id=a.delegation_id,
                )
                Commitment._base_manager.filter(pk=c.pk).update(created_at=carga.momento(a.date, a.pk))
                Activity._base_manager.filter(pk=a.pk).update(commitment=c, added_to_pipeline=True)
                self.alineados.add(c.pk)
                self.hecho("atenciones sin su compromiso que reciben uno")
                continue
            if a.requires_visit and not a.commitment.physical:
                Commitment._base_manager.filter(pk=a.commitment_id).update(physical=True)
                self.hecho("compromisos enlazados a una visita que pasan a ser de terreno")
            if not a.added_to_pipeline:
                Activity._base_manager.filter(pk=a.pk).update(added_to_pipeline=True)
                self.hecho("atenciones con compromiso que quedan marcadas «ingresa al tubo»")

    def restos_gestiones(self):
        for f in Followup._base_manager.filter(deleted_at__isnull=True).select_related("activity").order_by("pk"):
            if f.activity.deleted_at:
                Followup._base_manager.filter(pk=f.pk).update(deleted_at=f.activity.deleted_at)
                self.hecho("gestiones de una atención archivada que se archivan con ella")
                continue
            programada, realizada = f.scheduled_visit_date, f.visit_date
            if programada and programada < f.date:
                programada = f.date
            if realizada and programada and realizada < programada:
                if realizada >= f.date:
                    programada = realizada
                else:
                    realizada = programada if programada <= self.hoy else None
            if (programada, realizada) != (f.scheduled_visit_date, f.visit_date):
                Followup._base_manager.filter(pk=f.pk).update(scheduled_visit_date=programada, visit_date=realizada)
                self.hecho("gestiones con las fechas de visita en orden")

    def restos_compromisos(self):
        for c in Commitment._base_manager.filter(deleted_at__isnull=True).order_by("pk"):
            cambios = {}
            estado = c.status
            if estado in ("submitted", "pending") and c.due_date < self.hoy - timedelta(days=30):
                estado = "in_progress" if c.pk % 3 == 0 else "fulfilled"
                cambios["status"] = estado
                self.hecho("compromisos vencidos que avanzan de estado")
            if estado == "fulfilled" and c.due_date > self.hoy:
                nueva = self.hoy - timedelta(days=3)
                if c.request_date and nueva < c.request_date:
                    nueva = min(self.hoy, c.request_date + timedelta(days=1))
                cambios["due_date"] = nueva
                self.hecho("compromisos realizados con fecha comprometida ya cumplida")
            if cambios:
                Commitment._base_manager.filter(pk=c.pk).update(**cambios)

    def restos_evidencias(self):
        from core.views import STATUS_AFTER_DECISION  # el mismo mapa que usa la pantalla de validar

        ultimas = {}
        for v in Validation._base_manager.filter(deleted_at__isnull=True).order_by("date", "pk"):
            ultimas[v.evidence_id] = v
        for e in Evidence._base_manager.filter(deleted_at__isnull=True).select_related("activity").order_by("pk"):
            cambios = {}
            v = ultimas.get(e.pk)
            autor = e.activity.author_officer_id
            if e.author_officer_id != autor:
                libre = True
                if v is not None and v.reviewer_officer_id == autor:
                    # quien la validó pasaría a validar lo que subió: la valida otra jefatura de la delegación
                    alterno = (
                        Officer._base_manager.filter(
                            delegation_id=e.activity.delegation_id,
                            status=Officer.Status.ACTIVE,
                            position__name__in=("Delegado", "Jefe de Delegación"),
                        )
                        .exclude(pk=autor)
                        .order_by("pk")
                        .first()
                    )
                    if alterno is None:
                        libre = False
                        self.aviso(f"la evidencia {e.pk} sigue con otro autor: no hay otra jefatura que la valide.")
                    else:
                        Validation._base_manager.filter(pk=v.pk).update(reviewer_officer=alterno)
                if libre:
                    cambios["author_officer_id"] = autor
                    self.hecho("evidencias con el autor de su atención")
            # «Observado» deja la evidencia pendiente (no existe un estado «observada»)
            esperado = STATUS_AFTER_DECISION[v.decision] if v is not None else Evidence.ReviewStatus.PENDING
            if e.review_status != esperado:
                cambios["review_status"] = esperado
                self.hecho("evidencias con el estado de su última validación")
            if not e.file_link or not e.file_link.storage.exists(e.file_link.name):
                self.hecho("evidencias con un archivo de prueba repuesto en disco")
                if self.aplicar:  # en la simulación no se escribe nada en disco
                    e.file_link.save(
                        f"{e.unique_code.lower()}.pdf",
                        ContentFile(carga.pdf_minimo(f"Evidencia de prueba {e.unique_code}")),
                        save=False,
                    )
                    cambios["file_link"] = e.file_link.name
            if cambios:
                Evidence._base_manager.filter(pk=e.pk).update(**cambios)

    def restos_funcionarios(self):
        for o in Officer._base_manager.all().order_by("pk"):
            if not Officer.ID_FORMAT.fullmatch(o.institutional_id):
                nuevo = o.next_institutional_id()
                Officer._base_manager.filter(pk=o.pk).update(institutional_id=nuevo)
                self.hecho("identificadores de funcionario con el formato F-0000")

    # ------------------------------------------------------------------------------------------------------------
    # 9. Períodos: de anuales a trimestres
    # ------------------------------------------------------------------------------------------------------------
    @staticmethod
    def trimestres_de(inicio, fin):
        """Los trimestres calendario (ene-mar, abr-jun, jul-sep, oct-dic) que cubren de `inicio` a `fin`."""
        salida = []
        dia = inicio
        while dia <= fin:
            mes0 = 3 * ((dia.month - 1) // 3)
            siguiente = date(dia.year + 1, 1, 1) if mes0 == 9 else date(dia.year, mes0 + 4, 1)
            termina = siguiente - timedelta(days=1)
            salida.append((dia, min(termina, fin)))
            dia = termina + timedelta(days=1)
        return salida

    def periodos(self):
        """Cada período de más de 100 días (anual) se reparte en trimestres y el anual queda archivado.

        Las metas se copian a cada trimestre (la meta de atenciones se acerca a lo que se logra en un trimestre), las
        cartas y los ajustes pasan al trimestre de su fecha y los indicadores se recalculan. Los trimestres de años
        anteriores quedan cerrados; los del año en curso quedan vigentes para poder seguir ingresando cartas y
        cambios de trimestre.
        """
        ahora = timezone.now()
        anuales = [
            p
            for p in Period._base_manager.filter(deleted_at__isnull=True).order_by("start_date")
            if (p.end_date - p.start_date).days > 100
        ]
        if not anuales:
            return
        trimestres_de = {}
        for anual in anuales:
            habiles_anual = weekdays_between(anual.start_date, anual.end_date) or 1
            lista = []
            for inicio, fin in self.trimestres_de(anual.start_date, anual.end_date):
                if fin < date(self.hoy.year, 1, 1):
                    estado = Period.Status.CLOSED
                elif inicio <= self.hoy:
                    estado = Period.Status.ACTIVE
                else:
                    estado = Period.Status.PLANNED
                trimestre = (
                    Period._base_manager.filter(start_date=inicio, deleted_at__isnull=True).exclude(pk=anual.pk).first()
                )
                if trimestre is None:
                    habiles = weekdays_between(inicio, fin)
                    computables = min((fin - inicio).days + 1, max(1, round(habiles * anual.computable_days / habiles_anual)))
                    trimestre = Period.objects.create(
                        start_date=inicio,
                        end_date=fin,
                        computable_days=computables,
                        status=estado,
                        collective_threshold=anual.collective_threshold,
                        amber_threshold=anual.amber_threshold,
                        weighted_cap=anual.weighted_cap,
                        parameters_version=anual.parameters_version,
                        compliment_value=anual.compliment_value,
                        complaint_value=anual.complaint_value,
                        compliment_limit=anual.compliment_limit,
                    )
                    self.hecho("trimestres creados a partir de los períodos anuales")
                lista.append(trimestre)
            trimestres_de[anual.pk] = lista

        def trimestre_del(anual, dia):
            lista = trimestres_de[anual.pk]
            for trimestre in lista:
                if trimestre.start_date <= dia <= trimestre.end_date:
                    return trimestre
            return lista[0] if dia < lista[0].start_date else lista[-1]

        # a) Metas: una copia por trimestre
        recalcular = []
        for anual in anuales:
            trimestres = trimestres_de[anual.pk]
            metas = list(
                Goal._base_manager.filter(period=anual, deleted_at__isnull=True).select_related("item", "officer")
            )
            if not metas:
                continue
            propias = [g for g in metas if g.officer_id and g.unit == "atenciones"]
            nuevas = []
            for trimestre in trimestres:
                conteos = [
                    calculation.valid_activities(Goal(item_id=g.item_id, period=trimestre), g.officer).count()
                    for g in propias
                ]
                objetivo = max(1, int(statistics.median(conteos)) + 1) if conteos else 1
                for g in metas:
                    if g.officer_id and g.unit == "atenciones":
                        valor = Decimal(objetivo)
                    else:
                        valor = max(Decimal(1), (g.target_value / 4).quantize(Decimal(1)))
                    nuevas.append(
                        Goal(
                            target_value=valor,
                            unit=g.unit,
                            weight=g.weight,
                            version=g.version,
                            item_id=g.item_id,
                            officer_id=g.officer_id,
                            position_id=g.position_id,
                            period=trimestre,
                        )
                    )
            Goal.objects.bulk_create(nuevas, batch_size=200)  # sin señales: el recálculo se hace al final
            self.hecho("metas copiadas a los trimestres", len(nuevas))
            ids = [g.pk for g in metas]
            Indicator._base_manager.filter(goal_id__in=ids).update(deleted_at=ahora)
            Goal._base_manager.filter(pk__in=ids).update(deleted_at=ahora)
            recalcular.extend(trimestres)

        # b) Cartas y ajustes pasan al trimestre de su fecha
        pares = set()
        for anual in anuales:
            for f in Feedback._base_manager.filter(period=anual):
                trimestre = trimestre_del(anual, f.date)
                Feedback._base_manager.filter(pk=f.pk).update(period=trimestre)
                if f.deleted_at is None:
                    pares.add((f.officer_id, trimestre.pk))
                self.hecho("cartas que pasan al trimestre de su fecha")
        for funcionario_id, periodo_id in sorted(pares):
            feedback_rules.sync(funcionario_id, periodo_id)
        for anual in anuales:
            for ajuste in Adjustment._base_manager.filter(period=anual):
                trimestre = trimestre_del(anual, ajuste.created_at.date())
                Adjustment._base_manager.filter(pk=ajuste.pk).update(period=trimestre)
                self.hecho("ajustes que pasan al trimestre de su fecha")

        # c) Los anuales se archivan y los indicadores se calculan para los trimestres
        Period._base_manager.filter(pk__in=[a.pk for a in anuales]).update(deleted_at=ahora)
        self.hecho("períodos anuales archivados", len(anuales))
        for trimestre in recalcular:
            self.hecho("indicadores nuevos recalculados", calculation.recalculate_period(trimestre, force=True))

    # ------------------------------------------------------------------------------------------------------------
    # 10. Metas
    # ------------------------------------------------------------------------------------------------------------
    def metas(self):
        metas = list(
            Goal._base_manager.filter(deleted_at__isnull=True, unit="atenciones", target_value=36).select_related(
                "period", "officer", "item"
            )
        )
        propias = [g for g in metas if g.officer_id]
        if not propias:
            return
        conteos = [calculation.valid_activities(g, g.officer).count() for g in propias]
        objetivo = max(3, int(statistics.median(conteos)) + 1)
        Goal._base_manager.filter(pk__in=[g.pk for g in propias]).update(target_value=objetivo)
        self.hecho(f"metas de atenciones con una meta alcanzable ({objetivo})", len(propias))
        for periodo in {g.period for g in propias}:
            self.hecho("indicadores nuevos recalculados", calculation.recalculate_period(periodo, force=True))
