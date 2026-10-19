import re

from django.core.exceptions import ValidationError

MAX_LENGTH = 128
LOWERCASE = "a-zñáéíóúü"
UPPERCASE = "A-ZÑÁÉÍÓÚÜ"
SYMBOL = r"[^A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9\s]"

REQUIREMENTS = (
    (f"[{LOWERCASE}]", "password_no_lower", "Le falta una letra minúscula."),
    (f"[{UPPERCASE}]", "password_no_upper", "Le falta una letra mayúscula."),
    (r"[0-9]", "password_no_digit", "Le falta un número."),
    (SYMBOL, "password_no_symbol", "Le falta un símbolo (por ejemplo ! # $ % & * - _ . ,)."),
)


class PasswordPolicyValidator:

    def __init__(self, max_length=MAX_LENGTH):
        self.max_length = max_length

    def validate(self, password, user=None):
        errors = []
        if len(password) > self.max_length:
            errors.append(
                ValidationError(
                    f"Es demasiado larga: tiene {len(password)} caracteres y el máximo es {self.max_length}.",
                    code="password_too_long",
                )
            )
        for pattern, code, message in REQUIREMENTS:
            if re.search(pattern, password) is None:
                errors.append(ValidationError(message, code=code))
        if errors:
            raise ValidationError(errors)

    def get_help_text(self):
        return (
            f"Debe tener como máximo {self.max_length} caracteres y llevar al menos una minúscula, "
            "una mayúscula, un número y un símbolo."
        )
