import re

HEX_COLOR = re.compile(r"#[0-9A-Fa-f]{6}")
DEFAULT_COLOR = "#920000"

LIGHT_TEXT = "#ffffff"
DARK_TEXT = "#000000"


def clean_color(value):
    text = str(value or "").strip()
    return text.lower() if HEX_COLOR.fullmatch(text) else DEFAULT_COLOR


def luminance(color):
    channels = []
    for start in (1, 3, 5):
        value = int(color[start : start + 2], 16) / 255
        channels.append(value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4)
    red, green, blue = channels
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast(color_a, color_b):
    lighter, darker = sorted((luminance(color_a), luminance(color_b)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def palette(value):
    color = clean_color(value)
    text = max((LIGHT_TEXT, DARK_TEXT), key=lambda option: contrast(color, option))
    shade = "rgba(0, 0, 0, 0.26)" if text == LIGHT_TEXT else "rgba(255, 255, 255, 0.45)"
    return {"bg": color, "fg": text, "shade": shade}
