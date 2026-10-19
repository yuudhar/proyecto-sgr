from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.debug import sensitive_post_parameters

from accounts import recovery
from accounts.forms import RecoveryCodeForm, RecoveryEmailForm, RecoveryPasswordForm
from core.audit import log_event


def sent_text(new=False):
    what = "un código nuevo de 6 dígitos. El anterior ya no sirve" if new else "un código de 6 dígitos"
    return f"Si ese correo está registrado, te enviamos {what}. Vale {settings.RECOVERY_CODE_SECONDS} segundos."


def wait_text(seconds):
    return f"Espera {seconds} {'segundo' if seconds == 1 else 'segundos'} para pedir otro código."


def request_code(request):
    if request.user.is_authenticated:
        return redirect("core:profile")

    session = request.session
    form = RecoveryEmailForm(request.POST or None, initial={"email": session.get(recovery.EMAIL_KEY, "")})
    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"]
        wait = recovery.cooldown_left(session) if email == session.get(recovery.EMAIL_KEY) else 0
        if wait:
            messages.warning(request, wait_text(wait))
            return redirect("accounts:recover_code")
        recovery.send_codes(session, email)
        messages.info(request, sent_text())
        return redirect("accounts:recover_code")

    return render(request, "registration/recover_request.html", {"form": form})


@sensitive_post_parameters("code")
def enter_code(request):
    if request.user.is_authenticated:
        return redirect("core:profile")

    session = request.session
    if not recovery.pending(session):
        messages.warning(request, "Primero escribe tu correo para que te enviemos un código.")
        return redirect("accounts:recover")

    superseded = False
    form = RecoveryCodeForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        result = recovery.check(session, form.cleaned_data["code"])
        if result.user is not None:
            return redirect("accounts:recover_password")
        superseded = result.problem == recovery.SUPERSEDED
        form.add_error("code", rejection_text(result))

    max_attempts = settings.RECOVERY_MAX_ATTEMPTS
    left = recovery.seconds_left(session)
    locked = recovery.failures(session) >= max_attempts
    context = {
        "form": form,
        "masked_email": recovery.mask_email(session[recovery.EMAIL_KEY]),
        "seconds_left": left,
        "seconds_total": settings.RECOVERY_CODE_SECONDS,
        "locked": locked,
        "needs_new_code": left == 0 or locked or superseded,
        "resend_seconds": recovery.cooldown_left(session),
    }
    return render(request, "registration/recover_code.html", context)


def resend_code(request):
    if request.user.is_authenticated:
        return redirect("core:profile")
    if request.method != "POST":
        return redirect("accounts:recover_code")

    session = request.session
    if not recovery.pending(session):
        messages.warning(request, "Primero escribe tu correo para que te enviemos un código.")
        return redirect("accounts:recover")

    wait = recovery.cooldown_left(session)
    if wait:
        messages.warning(request, wait_text(wait))
        return redirect("accounts:recover_code")

    recovery.send_codes(session, session[recovery.EMAIL_KEY])
    messages.info(request, sent_text(new=True))
    return redirect("accounts:recover_code")


def rejection_text(result):
    if result.problem == recovery.EXPIRED:
        return f"El código venció: duraba {settings.RECOVERY_CODE_SECONDS} segundos. Pide uno nuevo."
    if result.problem == recovery.LOCKED:
        return "Fallaste demasiadas veces con este código. Pide uno nuevo."
    if result.problem == recovery.SUPERSEDED:
        return "Ese código ya no sirve: se pidió uno más nuevo para esta cuenta. Usa el último que recibiste o pide otro."
    if result.left == 0:
        return "El código no es correcto. Ya no quedan intentos: pide uno nuevo."
    return (
        f"El código no es correcto. Te {'queda' if result.left == 1 else 'quedan'} "
        f"{result.left} {'intento' if result.left == 1 else 'intentos'}."
    )


@sensitive_post_parameters("new_password1", "new_password2")
def new_password(request):
    if request.user.is_authenticated:
        return redirect("core:profile")

    session = request.session
    user = recovery.verified_user(session)
    if user is None:
        if recovery.verification_expired(session):
            text = (
                f"Pasaron más de {settings.RECOVERY_PASSWORD_SECONDS // 60} minutos desde que validaste el código. "
                "Pide uno nuevo para continuar."
            )
        else:
            text = "Para elegir una contraseña nueva primero hay que validar el código que te enviamos."
        recovery.clear(session)
        messages.warning(request, text)
        return redirect("accounts:recover")

    form = RecoveryPasswordForm(user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        log_event(user, "Contraseña restablecida con código", user)
        recovery.clear(session)
        messages.success(request, "Cambiaste tu contraseña. Ya puedes ingresar con la nueva.")
        return redirect("core:login")

    return render(request, "registration/recover_password.html", {"form": form})
