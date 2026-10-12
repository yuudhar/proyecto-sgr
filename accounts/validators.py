"""Política de contraseñas del SGR.

Se suma a los validadores de Django (parecido a los datos personales, largo mínimo, uso común, solo números) y se
configura en AUTH_PASSWORD_VALIDATORS (sgr_project/settings.py). La revisan todos los formularios que piden una
contraseña nueva: Control de usuarios, Mi perfil y la recuperación de contraseña. Las contraseñas que ya existen no
se revisan al ingresar: solo se exige al elegir una nueva.

La misma exigencia se avisa en el navegador con la regla «password» de core/rules.py, que repite validation.js.
Cada mensaje dice exactamente qué le falta a la contraseña escrita.
"""

import re

from django.core.exceptions import ValidationError

MAX_LENGTH = 128
LOWERCASE = "a-zñáéíóúü"
UPPERCASE = "A-ZÑÁÉÍÓÚÜ"
# Un símbolo es cualquier carácter que no sea letra, número ni espacio.
SYMBOL = r"[^A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9\s]"

# (expresión que debe encontrarse, código del error, mensaje)
REQUIREMENTS = (
    (f"[{LOWERCASE}]", "password_no_lower", "Le falta una letra minúscula."),
    (f"[{UPPERCASE}]", "password_no_upper", "Le falta una letra mayúscula."),
    (r"[0-9]", "password_no_digit", "Le falta un número."),
    (SYMBOL, "password_no_symbol", "Le falta un símbolo (por ejemplo ! # $ % & * - _ . ,)."),
)


class PasswordPolicyValidator:
    """Largo máximo y variedad de caracteres: minúscula, mayúscula, número y símbolo.

    El largo mínimo lo revisa MinimumLengthValidator, que sigue activo, para no repetir el mensaje.
    """

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
