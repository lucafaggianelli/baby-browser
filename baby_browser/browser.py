import sys
from time import time_ns
import tkinter
from tkinter.font import Font
from typing import Literal, Optional

from baby_browser.html import Node, Element, Text, HTMLParser
from baby_browser.logger import get_logger
from baby_browser.networking import fetch, parse_url
from baby_browser.utils import format_bytes


logger = get_logger(__name__)

WINDOW_H_MARGIN = 13
WINDOW_V_MARGIN = 18

VSTEP = 18
SCROLL_STEP = 3 * VSTEP

FontWeight = Literal["normal", "bold"]
FontSlant = Literal["roman", "italic"]


def _load_page_content(url: str):
    parsed_url = parse_url(url)

    html = ""
    t0 = time_ns()

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

    logger.debug(
        f"Loaded page {format_bytes(len(html))} in {(time_ns() - t0) / 1_000_000} us"
    )

    return html


_fonts_cache = {}


def _get_font(size: int, weight: FontWeight, slant: FontSlant) -> Font:
    key = (size, weight, slant)

    if key not in _fonts_cache:
        font = Font(size=size, weight=weight, slant=slant)
        _fonts_cache[key] = font

    return _fonts_cache[key]


class BlockLayout:
    x: float
    y: float
    width: float
    height: float

    def __init__(
        self,
        html_tree_root: Node,
        parent: "DocumentLayout | BlockLayout",
        previous: Optional["BlockLayout"] = None,
    ):
        self.html_tree_root = html_tree_root

        self.parent = parent
        self.previous = previous
        self.children: list["BlockLayout"] = []

    def layout(self):
        self.display_list = []

        self.x = self.parent.x
        self.y = (
            self.previous.y + self.previous.height if self.previous else self.parent.y
        )
        self.width = self.parent.width

        mode = self.html_tree_root.get_layout_mode()

        if mode == "block":
            self._layout_intermediate()

            self.height = sum([child.height for child in self.children], 0.0)
        else:
            self._line = []
            self.cursor_x: float = 0
            self.cursor_y: float = 0

            self.weight: FontWeight = "normal"
            self.style: FontSlant = "roman"
            self.font_size = 16

            self._render_tree(self.html_tree_root)

            self._flush_line()

            self.height = self.cursor_y

    def _layout_intermediate(self):
        previous = None

        for child in self.html_tree_root.children:
            next = BlockLayout(child, self, previous)
            self.children.append(next)
            previous = next

        for child in self.children:
            child.layout()

        for child in self.children:
            self.display_list.extend(child.display_list)

    def _flush_line(self):
        if not self._line:
            return

        # Tallest word in the line
        max_ascent: float = max(
            [font.metrics("ascent") for x, word, font in self._line]
        )
        baseline = self.cursor_y + 1.25 * max_ascent

        # Biggest descent in the line
        max_descent: float = max(
            [font.metrics("descent") for x, word, font in self._line]
        )

        for relative_x, word, font in self._line:
            x = self.x + relative_x
            y = self.y + baseline - font.metrics("ascent")
            self.display_list.append((x, y, word, font))

        self.cursor_x = 0
        self.cursor_y = baseline + 1.25 * max_descent
        self._line = []

    def _open_tag(self, element: Element):
        if element.tag in ("i", "em"):
            self.style = "italic"
        elif element.tag in ("b", "strong"):
            self.weight = "bold"
        elif element.tag == "small":
            self.font_size -= 2
        elif element.tag == "big":
            self.font_size += 4
        elif element.tag == "br":
            self._flush_line()

    def _close_tag(self, element: Element):
        if element.tag in ("i", "em"):
            self.style = "roman"
        elif element.tag in ("b", "strong"):
            self.weight = "normal"
        elif element.tag == "small":
            self.font_size += 2
        elif element.tag == "big":
            self.font_size -= 4
        elif element.tag == "p":
            self._flush_line()
            self.cursor_y += VSTEP

    def _render_tree(self, node: Node):
        if isinstance(node, Text):
            for word in node.text.split():
                self._render_word(word)
        elif isinstance(node, Element):
            self._open_tag(node)

            for child in node.children:
                self._render_tree(child)

            self._close_tag(node)

    def _render_word(self, word: str):
        font = _get_font(
            size=self.font_size,
            weight=self.weight,
            slant=self.style,
        )

        word_width = font.measure(word)

        # Break line on word
        if self.cursor_x + word_width > self.width:
            self._flush_line()

        self._line.append((self.cursor_x, word, font))

        self.cursor_x += word_width + font.measure(" ")


class DocumentLayout:
    def __init__(self, node: Node) -> None:
        self.node = node
        self.parent = None
        self.children = []
        self.display_list = []

    def layout(self, width: float):
        self.width = width - 2 * WINDOW_H_MARGIN
        self.x = WINDOW_H_MARGIN
        self.y = WINDOW_V_MARGIN

        child = BlockLayout(self.node, self, None)
        self.children.append(child)
        child.layout()
        self.height = child.height + 2 * WINDOW_V_MARGIN

        self.display_list = child.display_list

    def get_full_page_height(self) -> float:
        return self.display_list[-1][1] if len(self.display_list) > 0 else 0


class Browser:
    def __init__(self):
        self.window = tkinter.Tk()
        self.window.wm_title("BabyBrowser")
        self.scroll = 0
        self.page_height = 0
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
        self.document.layout(self.canvas.winfo_width())
        self.page_height = self.document.get_full_page_height()

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
            self.scroll = min(
                [
                    self.scroll + scroll_delta,
                    self.page_height - self.canvas.winfo_height() + 2 * VSTEP,
                ]
            )
        else:
            self.scroll = 0

        self.canvas.delete("all")
        self.draw()

    def load_page(self, url: str):
        html = _load_page_content(url)

        self.parser = HTMLParser(html)
        self.parser.parse()

        if not self.parser.root:
            logger.error("The HTML tree is empty, did you call .parse()?")
            return

        self.document = DocumentLayout(self.parser.root)
        self.document.layout(self.canvas.winfo_width())
        self.page_height = self.document.get_full_page_height()

        self.draw()

    def draw(self):
        height = self.canvas.winfo_height()

        for x, y, c, font in self.document.display_list:
            is_before_viewport = y > self.scroll + height
            is_after_viewport = y + VSTEP < self.scroll

            # If the text is not visible skip the rendering
            if is_before_viewport or is_after_viewport:
                continue

            self.canvas.create_text(x, y - self.scroll, text=c, font=font, anchor="nw")
