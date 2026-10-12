"""Búsqueda por palabras: no distingue mayúsculas ni tildes y entiende RUT y teléfonos.

Cada palabra se convierte en una expresión regular que se compara con los campos de
búsqueda de la pantalla (iregex). Así "nunez" encuentra a "Núñez", y "11111111" o
"11.111.111-1" encuentran el mismo RUT, escrito con o sin puntos y guion. La expresión
solo usa clases de caracteres y signos de interrogación, que entienden igual SQLite,
MySQL y PostgreSQL.
"""

import re
import unicodedata

MAX_WORD_LENGTH = 60  # una palabra más larga se corta; nadie busca con textos así

# Letra sin tilde -> todas las formas con que puede estar escrita en la base.
VARIANTS = {
    "a": "aáàäâ",
    "e": "eéèëê",
    "i": "iíìïî",
    "o": "oóòöô",
    "u": "uúùüû",
    "n": "nñ",
    "c": "cç",
}

SPECIAL = set("\\.^$*+?{}[]|()")
SEPARATOR = "[. \\-]?"  # separadores que se aceptan entre los números de un RUT o un teléfono


def plain_letter(char):
    """La letra sin tilde y en minúscula ("É" -> "e", "ñ" -> "n")."""
    base = unicodedata.normalize("NFD", char.lower())[0]
    return base


def letter_pattern(char):
    """Cómo se busca una letra: con todas sus variantes si las tiene, y si no, tal cual."""
    base = plain_letter(char)
    if base in VARIANTS:
        return f"[{VARIANTS[base]}]"
    return "\\" + char if char in SPECIAL else char


def number_like(word):
    """Los números del texto si la palabra es un RUT o un teléfono (solo dígitos, puntos y guion)."""
    clean = re.sub(r"[.\-]", "", word)
    if len(clean) >= 3 and re.fullmatch(r"[0-9]+[kK]?", clean):
        return clean
    return ""


def word_pattern(word):
    """Expresión regular de una palabra de búsqueda."""
    word = word[:MAX_WORD_LENGTH]
    digits = number_like(word)
    if digits:
        return SEPARATOR.join(letter_pattern(char) for char in digits)
    return "".join(letter_pattern(char) for char in word)
