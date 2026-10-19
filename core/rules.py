import re
from dataclasses import dataclass

LETTERS = "A-Za-zÁÉÍÓÚÜÑáéíóúüñ"


def collapse_spaces(text):
    return re.sub(r"\s+", " ", text).strip()


def normalize_lines(text):
    return re.sub(r"\r\n?", "\n", text).strip()


def rut_check_digit(body):
    total, factor = 0, 2
    for digit in reversed(body):
        total += int(digit) * factor
        factor = 2 if factor == 7 else factor + 1
    rest = 11 - total % 11
    if rest == 11:
        return "0"
    return "K" if rest == 10 else str(rest)


def normalize_rut(text):
    clean = re.sub(r"[.\s-]", "", text).upper()
    return f"{clean[:-1]}-{clean[-1]}" if len(clean) > 1 else clean


def is_valid_rut(text):
    body, _, digit = text.partition("-")
    return body.isdecimal() and rut_check_digit(body) == digit


NORMALIZERS = {
    "spaces": collapse_spaces,
    "trim": lambda text: text.strip(),
    "nospaces": lambda text: re.sub(r"\s+", "", text),
    "upper": lambda text: text.strip().upper(),
    "rut": lambda text: normalize_rut(collapse_spaces(text)),
    "lines": normalize_lines,
    "none": lambda text: text,
}

CHECKS = {"rut": is_valid_rut}


@dataclass(frozen=True)
class Rule:
    name: str
    pattern: str
    message: str
    normalizer: str = "spaces"
    check: str = ""
    server: bool = True

    def normalize(self, text):
        return NORMALIZERS[self.normalizer](text)

    def apply(self, text):
        value = self.normalize(text)
        if re.fullmatch(self.pattern, value) is None:
            return value, self.message
        if self.check and not CHECKS[self.check](value):
            return value, self.message
        return value, None

    def attrs(self):
        data = {
            "data-rule": self.name,
            "data-pattern": self.pattern,
            "data-message": self.message,
            "data-normalize": self.normalizer,
        }
        if self.check:
            data["data-check"] = self.check
        return data


RULES = {
    rule.name: rule
    for rule in (
        Rule(
            "rut",
            r"[0-9]{1,2}\.?[0-9]{3}\.?[0-9]{3}-?[0-9kK]",
            "Escribe un RUT válido, por ejemplo 12.345.678-5.",
            normalizer="rut",
            check="rut",
        ),
        Rule(
            "phone",
            r"\+?[0-9](?: ?[0-9]){7,13}",
            "El teléfono debe tener entre 8 y 14 números. Puede partir con + y llevar espacios, "
            "por ejemplo +56 9 1234 5678.",
        ),
        Rule(
            "email",
            r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}",
            "Escribe un correo válido, por ejemplo nombre@dominio.cl.",
            normalizer="trim",
        ),
        Rule(
            "person_name",
            f"[{LETTERS}][{LETTERS}' .\\-]*",
            "El nombre solo puede llevar letras, espacios, apóstrofes, puntos y guiones.",
        ),
        Rule(
            "commune",
            f"[{LETTERS}][{LETTERS}' .\\-]*",
            "La comuna solo puede llevar letras, espacios, apóstrofes, puntos y guiones.",
        ),
        Rule(
            "label",
            r"[^<>\x00-\x1f]+",
            "El texto no puede llevar los símbolos < ni >.",
        ),
        Rule(
            "text",
            r"[^<>\x00-\x08\x0b\x0c\x0e-\x1f]+",
            "El texto no puede llevar los símbolos < ni >.",
            normalizer="lines",
        ),
        Rule(
            "code",
            r"[A-Za-z0-9][A-Za-z0-9._\-]{1,49}",
            "Usa solo letras, números, puntos y guiones, sin espacios (entre 2 y 50 caracteres).",
            normalizer="trim",
        ),
        Rule(
            "username",
            r"[A-Za-z0-9][A-Za-z0-9._@+\-]{2,149}",
            "El usuario debe tener al menos 3 caracteres: letras, números y . _ @ + -, sin espacios.",
            normalizer="trim",
        ),
        Rule(
            "recovery_code",
            r"[0-9]{6}",
            "El código tiene 6 dígitos, solo números.",
            normalizer="nospaces",
        ),
        Rule(
            "hex_color",
            r"#[0-9A-Fa-f]{6}",
            "Escribe el color como #RRGGBB, por ejemplo #920000.",
            normalizer="upper",
        ),
        Rule(
            "password",
            "(?=.*[a-zñáéíóúü])(?=.*[A-ZÑÁÉÍÓÚÜ])(?=.*[0-9])(?=.*[^A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9\\s]).{8,128}",
            "La contraseña debe tener entre 8 y 128 caracteres, con al menos una minúscula, una mayúscula, "
            "un número y un símbolo (por ejemplo ! # $ %).",
            normalizer="none",
            server=False,
        ),
        Rule(
            "version",
            r"[0-9A-Za-z][0-9A-Za-z.\-]{0,19}",
            "Usa letras, números, puntos o guiones (hasta 20 caracteres), por ejemplo 1 o 2.1.",
            normalizer="trim",
        ),
    )
}


def get_rule(name):
    return RULES[name]


def rut_with_wrong_digit(text):
    clean = collapse_spaces(text)
    if re.fullmatch(r"[0-9]{1,2}\.?[0-9]{3}\.?[0-9]{3}-[0-9kK]", clean) is None:
        return False
    return not is_valid_rut(normalize_rut(clean))
