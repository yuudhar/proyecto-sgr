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

EMAIL_KEY = "recovery_email"
CODES_KEY = "recovery_codes"
NONCE_KEY = "recovery_nonce"
DEADLINE_KEY = "recovery_deadline"
SENT_AT_KEY = "recovery_sent_at"
USER_KEY = "recovery_user"
VERIFIED_UNTIL_KEY = "recovery_verified_until"
ALL_KEYS = (EMAIL_KEY, CODES_KEY, NONCE_KEY, DEADLINE_KEY, SENT_AT_KEY, USER_KEY, VERIFIED_UNTIL_KEY)

EXPIRED = "expired"
LOCKED = "locked"
SUPERSEDED = "superseded"
WRONG = "wrong"


@dataclass
class Result:

    user: object = None
    problem: str = ""
    left: int = 0


def new_code():
    return f"{secrets.randbelow(10**CODE_LENGTH):0{CODE_LENGTH}d}"


def fingerprint(user_pk, code, nonce):
    return salted_hmac("sgr.recovery-code", f"{nonce}:{user_pk}:{code}", algorithm="sha256").hexdigest()


def users_for(email):
    email = (email or "").strip()
    users = get_user_model().objects.filter(is_active=True)
    return users.filter(email__iexact=email) if email else users.none()


def mask_email(email):
    name, _, domain = email.partition("@")
    return f"{name[:2]}***@{domain}"


def clear(session):
    for key in ALL_KEYS:
        session.pop(key, None)


def pending(session):
    return bool(session.get(EMAIL_KEY) and session.get(NONCE_KEY))


def seconds_left(session):
    return max(0, ceil(session.get(DEADLINE_KEY, 0) - timezone.now().timestamp()))


def cooldown_left(session):
    ready_at = session.get(SENT_AT_KEY, 0) + settings.RECOVERY_RESEND_SECONDS
    return max(0, ceil(ready_at - timezone.now().timestamp()))


def _count(key, timeout):
    cache.add(key, 0, timeout)
    try:
        return cache.incr(key)
    except ValueError:
        cache.set(key, 1, timeout)
        return 1


def _attempts_key(session):
    return f"sgr:recovery:attempts:{session.get(NONCE_KEY)}"


def failures(session):
    return cache.get(_attempts_key(session), 0)


def sent_last_hour(user):
    since = timezone.now() - timedelta(hours=1)
    return AuditLog.objects.filter(user=user, event=SENT_EVENT, date__gte=since).count()


def live_code_id(user):
    last = (
        AuditLog.objects.filter(user=user, event__in=(SENT_EVENT, VALIDATED_EVENT))
        .order_by("-pk")
        .values_list("pk", "event")
        .first()
    )
    return last[0] if last is not None and last[1] == SENT_EVENT else None


def describe_duration(seconds):
    if seconds % 60 == 0:
        minutes = seconds // 60
        return f"{minutes} minuto" if minutes == 1 else f"{minutes} minutos"
    return f"{seconds} segundos"


def send_code(user, code, expires_at):
    context = {
        "name": user.get_full_name() or user.get_username(),
        "code": code,
        "seconds": settings.RECOVERY_CODE_SECONDS,
        "duration": describe_duration(settings.RECOVERY_CODE_SECONDS),
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
    now = timezone.now()
    expires_at = now + timedelta(seconds=settings.RECOVERY_CODE_SECONDS)
    nonce = secrets.token_hex(8)
    codes = []
    for user in users_for(email):
        if sent_last_hour(user) >= settings.RECOVERY_MAX_REQUESTS:
            continue
        code = new_code()
        try:
            send_code(user, code, expires_at)
        except Exception:
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
        if live_code_id(user) != sent_id:
            return Result(problem=SUPERSEDED)
        log_event(user, VALIDATED_EVENT, user)
        clear(session)
        session[USER_KEY] = user.pk
        session[VERIFIED_UNTIL_KEY] = (
            timezone.now() + timedelta(seconds=settings.RECOVERY_PASSWORD_SECONDS)
        ).timestamp()
        return Result(user=user)
    return Result(problem=WRONG, left=settings.RECOVERY_MAX_ATTEMPTS - tries)


def verification_expired(session):
    until = session.get(VERIFIED_UNTIL_KEY)
    return until is not None and timezone.now().timestamp() > until


def verified_user(session):
    user_pk = session.get(USER_KEY)
    if user_pk is None or verification_expired(session):
        return None
    return get_user_model().objects.filter(pk=user_pk, is_active=True).first()
