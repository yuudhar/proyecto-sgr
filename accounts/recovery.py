"""Recuperación de contraseña con un código temporal que llega por correo.

Son tres pantallas (accounts/views.py) y este módulo hace el trabajo de cada una:

  1. La persona escribe su correo   -> send_codes() crea un código de 6 dígitos y lo envía.
  2. Escribe el código que le llegó -> check() revisa que calce, que esté vigente y que no se haya usado.
  3. Elige su contraseña nueva      -> el código ya quedó usado, así que no sirve una segunda vez.

Reglas del código: 6 dígitos, vale RECOVERY_CODE_SECONDS (120), se usa una sola vez, falla tras
RECOVERY_MAX_ATTEMPTS intentos equivocados y pedir uno nuevo deja sin efecto los anteriores de la misma cuenta,
se hayan pedido desde este navegador o desde otro. Reenviar el código se puede cada RECOVERY_RESEND_SECONDS (45)
y hasta RECOVERY_MAX_REQUESTS (5) veces por hora. Los números están en settings.py.

Dónde queda cada cosa (no se agrega ninguna tabla al modelo de datos):

  - En request.session va lo que hay que recordar entre una pantalla y otra: el correo escrito, la hora en
    que vence el código, la hora del último envío y la huella del código. La sesión vive en el servidor (la
    tabla django_session que ya trae Django) y el navegador solo lleva una cookie con su clave, así que la
    persona no puede cambiar esos valores.
  - El código no se guarda: se guarda su huella (un HMAC con la SECRET_KEY). Para comparar se calcula la
    huella del código que escribió la persona.
  - Los intentos de cada código se cuentan en la caché de Django. Cada intento se anota antes de revisar el
    código y la suma es atómica, así que mandar muchos intentos a la vez no sirve para saltarse el límite.
  - Cada código enviado y cada código aceptado dejan un evento en la auditoría (Audit_Log). Ahí se cuentan los
    códigos enviados a una cuenta en la última hora y ahí se sabe cuál es el código vigente: el último evento
    de la cuenta, si es un envío. Un código nuevo (pedido desde donde sea) deja de ser el último y los
    anteriores dejan de servir; un código aceptado queda como último evento y tampoco sirve de nuevo.
"""

import logging
import secrets
from dataclasses import dataclass
from datetime import timedelta
from math import ceil
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac

from core.audit import log_event
from core.models import AuditLog

logger = logging.getLogger(__name__)

CODE_LENGTH = 6
SENT_EVENT = "Código de recuperación enviado"
VALIDATED_EVENT = "Código de recuperación validado"

# Claves de request.session mientras dura la recuperación.
EMAIL_KEY = "recovery_email"  # correo que escribió la persona (paso 1)
CODES_KEY = "recovery_codes"  # [[id de la cuenta, huella de su código, id del envío en la auditoría], ...] (paso 1)
NONCE_KEY = "recovery_nonce"  # identifica este envío: separa un código de otro
DEADLINE_KEY = "recovery_deadline"  # hora (en segundos) en que vence el código
SENT_AT_KEY = "recovery_sent_at"  # hora (en segundos) del último envío: de ahí se cuenta la espera para reenviar
USER_KEY = "recovery_user"  # cuenta cuyo código ya se validó (paso 2)
VERIFIED_UNTIL_KEY = "recovery_verified_until"  # hasta cuándo puede elegir la contraseña nueva
ALL_KEYS = (EMAIL_KEY, CODES_KEY, NONCE_KEY, DEADLINE_KEY, SENT_AT_KEY, USER_KEY, VERIFIED_UNTIL_KEY)

# Por qué se rechazó un código.
EXPIRED = "expired"  # pasaron los 120 segundos
LOCKED = "locked"  # ya se equivocó demasiadas veces con este código
SUPERSEDED = "superseded"  # el código era el correcto, pero se pidió uno más nuevo (o este ya se usó)
WRONG = "wrong"  # no calza con el código enviado


@dataclass
class Result:
    """Lo que devuelve check(): la cuenta si el código era válido, o el motivo del rechazo."""

    user: object = None
    problem: str = ""
    left: int = 0  # intentos que quedan después de equivocarse


def new_code():
    """Seis dígitos al azar. Se usa secrets (pensado para claves); random se puede adivinar."""
    return f"{secrets.randbelow(10**CODE_LENGTH):0{CODE_LENGTH}d}"


def fingerprint(user_pk, code, nonce):
    """Huella de un código. Incluye la cuenta y el envío: el mismo número en otra cuenta o en otro envío da otra huella."""
    return salted_hmac("sgr.recovery-code", f"{nonce}:{user_pk}:{code}", algorithm="sha256").hexdigest()


def users_for(email):
    """Cuentas activas con ese correo, sin distinguir mayúsculas. Un correo vacío no calza con nadie."""
    email = (email or "").strip()
    users = get_user_model().objects.filter(is_active=True)
    return users.filter(email__iexact=email) if email else users.none()


def mask_email(email):
    """Esconde casi todo el correo (ma***@dominio.cl): alcanza para que la persona reconozca el suyo."""
    name, _, domain = email.partition("@")
    return f"{name[:2]}***@{domain}"


def clear(session):
    """Borra de la sesión todo lo de la recuperación."""
    for key in ALL_KEYS:
        session.pop(key, None)


def pending(session):
    """True si la persona ya escribió su correo (paso 1) y le corresponde escribir el código."""
    return bool(session.get(EMAIL_KEY) and session.get(NONCE_KEY))


def seconds_left(session):
    """Segundos que le quedan al código; 0 cuando venció."""
    return max(0, ceil(session.get(DEADLINE_KEY, 0) - timezone.now().timestamp()))


def cooldown_left(session):
    """Segundos que faltan para poder pedir otro código desde esta sesión; 0 cuando ya se puede.

    La espera corre desde el último envío y vale igual exista o no una cuenta con ese correo, así que
    tampoco delata qué correos están registrados.
    """
    ready_at = session.get(SENT_AT_KEY, 0) + settings.RECOVERY_RESEND_SECONDS
    return max(0, ceil(ready_at - timezone.now().timestamp()))


def _count(key, timeout):
    """Suma 1 a un contador de la caché y devuelve el valor nuevo. La suma es atómica."""
    cache.add(key, 0, timeout)  # lo crea en 0 si no existía; si ya existe, no lo toca
    try:
        return cache.incr(key)
    except ValueError:  # el contador venció justo entre una línea y la otra
        cache.set(key, 1, timeout)
        return 1


def _attempts_key(session):
    return f"sgr:recovery:attempts:{session.get(NONCE_KEY)}"


def failures(session):
    """Intentos que lleva el código actual (los equivocados y, si lo hubo, el que lo aceptó)."""
    return cache.get(_attempts_key(session), 0)


def sent_last_hour(user):
    """Cuántos códigos se le enviaron a la cuenta en la última hora, según la auditoría."""
    since = timezone.now() - timedelta(hours=1)
    return AuditLog.objects.filter(user=user, event=SENT_EVENT, date__gte=since).count()


def live_code_id(user):
    """Id, en la auditoría, del envío cuyo código sigue vigente para la cuenta; None si no hay ninguno.

    Manda el último evento de recuperación de la cuenta (código enviado o código aceptado):
      - si es un envío, ese es el único código vigente. Los anteriores quedaron sin efecto, aunque se
        hayan pedido desde otro navegador u otro computador;
      - si es una validación, el código ya se usó y no queda ninguno vigente.
    """
    last = (
        AuditLog.objects.filter(user=user, event__in=(SENT_EVENT, VALIDATED_EVENT))
        .order_by("-pk")
        .values_list("pk", "event")
        .first()
    )
    return last[0] if last is not None and last[1] == SENT_EVENT else None


def describe_duration(seconds):
    """Cuánto dura el código dicho como lo diría una persona: 120 -> «2 minutos», 60 -> «1 minuto», 45 -> «45 segundos»."""
    if seconds % 60 == 0:
        minutes = seconds // 60
        return f"{minutes} minuto" if minutes == 1 else f"{minutes} minutos"
    return f"{seconds} segundos"


def send_code(user, code, expires_at):
    """Envía el correo con el código. Con el correo de consola (sin EMAIL_HOST) sale en la terminal.

    Va en dos versiones dentro del mismo mensaje: el texto simple (lo que muestra un lector que no sabe de HTML y lo
    que se ve en la consola) y la versión con los colores del portal, con el código grande al centro. El lector de
    correo elige la que sepa mostrar.
    """
    context = {
        "name": user.get_full_name() or user.get_username(),
        "code": code,
        "seconds": settings.RECOVERY_CODE_SECONDS,
        "duration": describe_duration(settings.RECOVERY_CODE_SECONDS),
        # La hora de vencimiento va siempre en hora de Chile, esté o no activada la zona horaria del portal.
        "expires_at": timezone.localtime(expires_at, ZoneInfo(settings.PORTAL_TIME_ZONE)),
    }
    send_mail(
        "Tu código para recuperar la contraseña del SGR",
        render_to_string("registration/recovery_email.txt", context),
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
        html_message=render_to_string("registration/recovery_email.html", context),
    )


def send_codes(session, email):
    """Paso 1 (y reenvío): envía un código a cada cuenta activa con ese correo y deja la sesión lista para el paso 2.

    La sesión queda igual exista o no una cuenta con ese correo, haya pedido demasiados códigos o haya
    fallado el envío: así la respuesta no deja averiguar qué correos están registrados. Cada envío queda
    anotado en la auditoría, y eso es lo que deja sin efecto los códigos anteriores de la cuenta.
    """
    now = timezone.now()
    expires_at = now + timedelta(seconds=settings.RECOVERY_CODE_SECONDS)
    nonce = secrets.token_hex(8)
    codes = []
    for user in users_for(email):
        if sent_last_hour(user) >= settings.RECOVERY_MAX_REQUESTS:
            continue  # ya pidió demasiados en la última hora: no se envía otro
        code = new_code()
        try:
            send_code(user, code, expires_at)
        except Exception:
            # Un envío que falla no cuenta para el límite por hora (no queda en la auditoría) y no se avisa
            # a la persona, porque el aviso delataría que el correo está registrado.
            logger.exception("No se pudo enviar el código de recuperación a la cuenta %s", user.pk)
            continue
        sent = log_event(user, SENT_EVENT, user)
        codes.append([user.pk, fingerprint(user.pk, code, nonce), sent.pk])

    clear(session)
    session[EMAIL_KEY] = email
    session[CODES_KEY] = codes
    session[NONCE_KEY] = nonce
    session[DEADLINE_KEY] = expires_at.timestamp()
    session[SENT_AT_KEY] = now.timestamp()


def check(session, code):
    """Paso 2: revisa el código que escribió la persona y devuelve un Result.

    Es válido si calza con el que se envió, no venció, es el último que se pidió para la cuenta y no tiene
    demasiados intentos. Al aceptarlo se borra de la sesión y queda anotado en la auditoría, así que sirve una
    sola vez, y queda anotado hasta cuándo puede elegir su contraseña nueva. El vencimiento se revisa contra la
    hora del servidor, no contra la cuenta regresiva de la pantalla.
    """
    if seconds_left(session) == 0:
        return Result(problem=EXPIRED)

    tries = _count(_attempts_key(session), settings.RECOVERY_CODE_SECONDS * 2)
    if tries > settings.RECOVERY_MAX_ATTEMPTS:
        return Result(problem=LOCKED)

    nonce = session.get(NONCE_KEY)
    for user_pk, stored, sent_id in session.get(CODES_KEY, []):
        if not constant_time_compare(stored, fingerprint(user_pk, code, nonce)):
            continue
        user = get_user_model().objects.filter(pk=user_pk, is_active=True).first()
        if user is None:
            continue
        # El código es el correcto, pero puede que después se haya pedido otro (desde este u otro navegador).
        # Esto solo se dice cuando la persona escribió el código bien, así que no revela nada a quien adivina.
        if live_code_id(user) != sent_id:
            return Result(problem=SUPERSEDED)
        log_event(user, VALIDATED_EVENT, user)  # desde aquí el código queda usado, también para otras sesiones
        clear(session)
        session[USER_KEY] = user.pk
        session[VERIFIED_UNTIL_KEY] = (
            timezone.now() + timedelta(seconds=settings.RECOVERY_PASSWORD_SECONDS)
        ).timestamp()
        return Result(user=user)
    return Result(problem=WRONG, left=settings.RECOVERY_MAX_ATTEMPTS - tries)


def verification_expired(session):
    """True si la persona ya validó su código pero se le acabó el tiempo para elegir la contraseña."""
    until = session.get(VERIFIED_UNTIL_KEY)
    return until is not None and timezone.now().timestamp() > until


def verified_user(session):
    """Cuenta cuyo código se validó hace poco, o None si no corresponde estar en el paso 3."""
    user_pk = session.get(USER_KEY)
    if user_pk is None or verification_expired(session):
        return None
    return get_user_model().objects.filter(pk=user_pk, is_active=True).first()
