"""Colores de las delegaciones: valida el formato y elige un texto legible sobre el fondo."""

import re

HEX_COLOR = re.compile(r"#[0-9A-Fa-f]{6}")
DEFAULT_COLOR = "#920000"

# Con blanco o negro puros, cualquier color de fondo queda con un contraste de al menos 4,5.
LIGHT_TEXT = "#ffffff"
DARK_TEXT = "#000000"


def clean_color(value):
    """El color escrito como #RRGGBB en minúsculas; si el valor no sirve, el color por defecto.

    Los colores se usan dentro de estilos en las páginas, así que nunca se escribe en ellas
    un texto que no sea exactamente un color.
    """
    text = str(value or "").strip()
    return text.lower() if HEX_COLOR.fullmatch(text) else DEFAULT_COLOR


def luminance(color):
    """Luminancia relativa (de 0 a 1) de un color #RRGGBB, según la fórmula de WCAG 2."""
    channels = []
    for start in (1, 3, 5):
        value = int(color[start : start + 2], 16) / 255
        channels.append(value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4)
    red, green, blue = channels
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast(color_a, color_b):
    """Razón de contraste entre dos colores (de 1 a 21). Para texto normal se pide 4,5 o más."""
    lighter, darker = sorted((luminance(color_a), luminance(color_b)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def palette(value):
    """Fondo, texto y sombreado de un bloque que lleva el color de una delegación.

    El texto es blanco u oscuro, el que más contraste tenga con el fondo. El sombreado
    sirve para las etiquetas que van encima: oscurece los fondos con texto blanco y
    aclara los que llevan texto oscuro, de modo que el texto no pierde contraste.
    """
    color = clean_color(value)
    text = max((LIGHT_TEXT, DARK_TEXT), key=lambda option: contrast(color, option))
    shade = "rgba(0, 0, 0, 0.26)" if text == LIGHT_TEXT else "rgba(255, 255, 255, 0.45)"
    return {"bg": color, "fg": text, "shade": shade}
