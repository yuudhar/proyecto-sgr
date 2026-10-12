"""Formularios de la recuperación de contraseña (uno por pantalla)."""

from django import forms
from django.contrib.auth.forms import SetPasswordForm

from accounts.recovery import CODE_LENGTH
from core.forms import BootstrapFormMixin, password_help
from core.rules import get_rule


class RecoveryEmailForm(BootstrapFormMixin, forms.Form):
    """Paso 1: el correo de la cuenta."""

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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.style_fields()

    def clean_email(self):
        # Mismo formato que exigen los formularios de usuarios; en minúsculas porque el correo no distingue.
        value, error = get_rule("email").apply(self.cleaned_data["email"])
        if error:
            raise forms.ValidationError(error)
        return value.lower()


class RecoveryCodeForm(BootstrapFormMixin, forms.Form):
    """Paso 2: el código de 6 dígitos que llegó por correo."""

    code = forms.CharField(
        label="Código de 6 dígitos",
        max_length=12,  # deja espacio para un código escrito con espacios; la regla lo arregla
        widget=forms.TextInput(
            attrs={
                "autofocus": True,
                "autocomplete": "one-time-code",
                "inputmode": "numeric",
                "placeholder": "000000",
                "class": "code-input",
                # Con JavaScript el campo se cambia por seis casillas (core/static/core/js/code-boxes.js).
                "data-code-boxes": str(CODE_LENGTH),
                **get_rule("recovery_code").attrs(),
            }
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.style_fields()

    def clean_code(self):
        value, error = get_rule("recovery_code").apply(self.cleaned_data["code"])
        if error:
            raise forms.ValidationError(error)
        return value


class RecoveryPasswordForm(BootstrapFormMixin, SetPasswordForm):
    """Paso 3: la contraseña nueva, con las mismas exigencias de siempre (AUTH_PASSWORD_VALIDATORS)."""

    error_messages = {
        **SetPasswordForm.error_messages,
        "password_mismatch": "Las dos contraseñas nuevas no son iguales.",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["new_password1"].label = "Contraseña nueva"
        self.fields["new_password1"].help_text = password_help()
        self.fields["new_password1"].widget.attrs["autofocus"] = True
        self.fields["new_password2"].label = "Repite la contraseña nueva"
        self.fields["new_password2"].help_text = ""
        self.fields["new_password2"].widget.attrs["data-match"] = "id_new_password1"
        self.style_fields()

    def validate_password_for_user(self, user, password_field_name="new_password2"):
        # El aviso de una contraseña débil va en el campo de la contraseña nueva, no en el de repetirla.
        super().validate_password_for_user(user, "new_password1")
