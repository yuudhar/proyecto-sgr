import re
import unicodedata

MAX_WORD_LENGTH = 60

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
SEPARATOR = "[. \\-]?"


def plain_letter(char):
    base = unicodedata.normalize("NFD", char.lower())[0]
    return base


def letter_pattern(char):
    base = plain_letter(char)
    if base in VARIANTS:
        return f"[{VARIANTS[base]}]"
    return "\\" + char if char in SPECIAL else char


def number_like(word):
    clean = re.sub(r"[.\-]", "", word)
    if len(clean) >= 3 and re.fullmatch(r"[0-9]+[kK]?", clean):
        return clean
    return ""


def word_pattern(word):
    word = word[:MAX_WORD_LENGTH]
    digits = number_like(word)
    if digits:
        return SEPARATOR.join(letter_pattern(char) for char in digits)
    return "".join(letter_pattern(char) for char in word)
