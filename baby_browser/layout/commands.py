from dataclasses import dataclass, field
from tkinter import Canvas
from tkinter.font import Font

from baby_browser.fonts import get_font


@dataclass
class DrawCommand:
    top: float
    left: float
    bottom: float = field(default=0)
    right: float = field(default=0)

    def execute(self, scroll: float, canvas: Canvas):
        pass


@dataclass
class DrawText(DrawCommand):
    bottom: float = field(init=False)
    text: str = field(default="")
    font: Font = field(default_factory=lambda: get_font(16, "normal", "roman"))

    def __post_init__(self):
        self.bottom = self.top + self.font.metrics("linespace")

    def execute(self, scroll: float, canvas: Canvas):
        canvas.create_text(
            self.left, self.top - scroll, text=self.text, font=self.font, anchor="nw"
        )


@dataclass
class DrawRect(DrawCommand):
    color: str = field(default="black")

    def execute(self, scroll: float, canvas: Canvas):
        canvas.create_rectangle(
            self.left,
            self.top - scroll,
            self.right,
            self.bottom - scroll,
            fill=self.color,
            width=0,
        )
