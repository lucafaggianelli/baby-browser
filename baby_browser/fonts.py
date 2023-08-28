from tkinter.font import Font
from typing import Literal


FontWeight = Literal["normal", "bold"]
FontSlant = Literal["roman", "italic"]

_fonts_cache = {}


def get_font(family: str, size: int, weight: FontWeight, slant: FontSlant) -> Font:
    key = (family, size, weight, slant)

    if key not in _fonts_cache:
        font = Font(family=family, size=size, weight=weight, slant=slant)
        _fonts_cache[key] = font

    return _fonts_cache[key]
