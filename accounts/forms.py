import logging

from django import forms
from django.conf import settings
from django.contrib.auth.forms import PasswordResetForm, SetPasswordForm
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from accounts import recovery
from core.audit import log_event
from core.forms import BootstrapFormMixin, password_help
from core.rules import get_rule

logger = logging.getLogger(__name__)


class RecoveryRequestForm(BootstrapFormMixin, PasswordResetForm):
    """Pide el correo de la cuenta y manda el enlace para elegir una contraseña nueva.

    Usa las reglas de Django para saber a quién escribir (cuentas activas, con contraseña y con ese correo) y le
    suma el tope de envíos por hora. Quien llama no se entera de si hubo o no destinatarios: la respuesta es
    siempre la misma.
    """

    email = forms.EmailField(
        label="Correo de tu cuenta",
        max_length=254,
        widget=forms.EmailInput(
            attrs={
                "autofocus": True,
                "autocomplete": "email",
                "placeholder": "nombre@dominio.cl",
                **get_rule("email").attrs(),
            }
        ),
    )

    subject_template_name = "registration/recovery_subject.txt"
    email_template_name = "registration/recovery_email.txt"
    html_email_template_name = "registration/recovery_email.html"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.style_fields()

    def clean_email(self):
        value, error = get_rule("email").apply(self.cleaned_data["email"])
        if error:
            raise forms.ValidationError(error)
        return value.lower()

    def get_users(self, email):
        """Nunca busca con un correo en blanco: Django casaría con las cuentas que no tienen correo."""
        if not (email or "").strip():
            return iter(())
        return super().get_users(email)

    def build_link(self, request, user):
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        path = reverse("accounts:recover_confirm", kwargs={"uidb64": uid, "token": token})
        return request.build_absolute_uri(path)

    def send_mail(self, to_email, context):
        """Manda el correo (texto y HTML). Si el envío falla, deja pasar el error para que ``save`` lo registre."""
        subject = "".join(render_to_string(self.subject_template_name, context).splitlines())
        message = EmailMultiAlternatives(
            subject,
            render_to_string(self.email_template_name, context),
            settings.DEFAULT_FROM_EMAIL,
            [to_email],
        )
        message.attach_alternative(render_to_string(self.html_email_template_name, context), "text/html")
        message.send()

    def save(self, request):
        """Manda un enlace a cada cuenta que corresponda y devuelve cuántos salieron (solo para pruebas y registros)."""
        sent = 0
        for user in self.get_users(self.cleaned_data["email"]):
            if recovery.over_the_limit(user):
                continue
            context = {
                "name": user.get_full_name() or user.get_username(),
                "link": self.build_link(request, user),
                "duration": recovery.link_duration(),
            }
            try:
                self.send_mail(user.email, context)
            except Exception:
                logger.exception("No se pudo enviar el enlace de recuperación a la cuenta %s", user.pk)
                continue
            log_event(user, recovery.SENT_EVENT, user)
            sent += 1
        return sent


class RecoveryPasswordForm(BootstrapFormMixin, SetPasswordForm):

    error_messages = {
        **SetPasswordForm.error_messages,
        "password_mismatch": "Las dos contraseñas nuevas no son iguales.",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["new_password1"].label = "Contraseña nueva"
        self.fields["new_password1"].help_text = password_help()
        self.fields["new_password1"].widget.attrs.update(get_rule("password").attrs())
        self.fields["new_password1"].widget.attrs["autofocus"] = True
        self.fields["new_password2"].label = "Repite la contraseña nueva"
        self.fields["new_password2"].help_text = ""
        self.fields["new_password2"].widget.attrs["data-match"] = "id_new_password1"
        self.style_fields()

    def validate_password_for_user(self, user, password_field_name="new_password2"):
        super().validate_password_for_user(user, "new_password1")
