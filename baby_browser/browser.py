import sys
import tkinter
from tkinter.font import Font
from typing import Literal

from baby_browser.html import Text, lexer
from baby_browser.logger import get_logger
from baby_browser.networking import fetch, parse_url


logger = get_logger(__name__)

HSTEP, VSTEP = 13, 18
SCROLL_STEP = 3 * VSTEP


def _load_page_content(url: str):
    parsed_url = parse_url(url)

    html = ""

    if parsed_url.scheme in ("http", "https"):
        response = fetch(parsed_url)

        if response.status_code != 200:
            logger.error(
                f"The server responded with {response.status_code}: {response.status}"
            )
            logger.error(response.body)
            sys.exit(1)

        html = response.body
    elif parsed_url.scheme == "file":
        with open(parsed_url.path, "r") as f:
            html = f.read()
    elif parsed_url.scheme == "data":
        mime_type, content = parsed_url.path.split(",", 1)
        html = content
    else:
        raise ValueError(f"URL scheme not supported: {url}")

    return html


class Layout:
    def __init__(self, tokens, width: float):
        self.tokens = tokens
        self.width = width

        self.render()

    def render(self):
        self.display_list = []
        self.cursor_x: float = HSTEP
        self.cursor_y: float = VSTEP

        self.weight: Literal["normal", "bold"] = "normal"
        self.style: Literal["roman", "italic"] = "roman"
        self.font_size = 16

        for token in self.tokens:
            self._render_token(token)

    def _render_token(self, token):
        if isinstance(token, Text):
            for word in token.text.split():
                self._render_word(word)
        elif token.tag in ("i", "em"):
            self.style = "italic"
        elif token.tag in ("/i", "/em"):
            self.style = "roman"
        elif token.tag in ("b", "strong"):
            self.weight = "bold"
        elif token.tag in ("/b", "/strong"):
            self.weight = "normal"

    def _render_word(self, word: str):
        font = Font(
            family="Times New Roman",
            size=self.font_size,
            weight=self.weight,
            slant=self.style,
        )

        word_width = font.measure(word)

        if self.cursor_x + word_width > self.width - HSTEP:
            # Break line on word
            self.cursor_y += font.metrics("linespace") * 1.25
            self.cursor_x = HSTEP

        self.display_list.append((self.cursor_x, self.cursor_y, word, font))

        self.cursor_x += word_width + font.measure(" ")


class Browser:
    def __init__(self):
        self.window = tkinter.Tk()
        self.scroll = 0
        self.canvas = tkinter.Canvas(
            self.window,
            width=800,
            height=600,
        )

        self.canvas.pack(fill="both", expand=True)

        self.window.bind("<Configure>", self._on_resize)
        self.window.bind("<Down>", self._on_scroll)
        self.window.bind("<Up>", self._on_scroll)
        self.window.bind("<MouseWheel>", self._on_scroll)

    def _on_resize(self, event: tkinter.Event):
        self.layout.width = self.canvas.winfo_width()
        self.layout.render()

        self.canvas.delete("all")
        self.draw()

    def _on_scroll(self, event: tkinter.Event):
        scroll_delta = 0

        if event.type == tkinter.EventType.MouseWheel:
            scroll_delta -= event.delta * SCROLL_STEP
        elif event.type == tkinter.EventType.KeyPress:
            if event.keysym == "Down":
                scroll_delta -= SCROLL_STEP
            elif event.keysym == "Up":
                scroll_delta += SCROLL_STEP

        if self.scroll + scroll_delta >= 0:
            self.scroll += scroll_delta
        else:
            return

        self.canvas.delete("all")
        self.draw()

    def load_page(self, url: str):
        html = _load_page_content(url)

        self.tokens = lexer(html)

        self.layout = Layout(self.tokens, self.canvas.winfo_width())

        self.draw()

    def draw(self):
        height = self.canvas.winfo_height()

        for x, y, c, font in self.layout.display_list:
            is_before_viewport = y > self.scroll + height
            is_after_viewport = y + VSTEP < self.scroll

            # If the text is not visible skip the rendering
            if is_before_viewport or is_after_viewport:
                continue

            self.canvas.create_text(x, y - self.scroll, text=c, font=font, anchor="nw")
