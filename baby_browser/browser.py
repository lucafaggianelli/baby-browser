from pathlib import Path
import sys
from time import time_ns
import tkinter
from typing import Optional
from baby_browser.css import CSSParser, CSSSelector
from baby_browser.fonts import get_font

from baby_browser.html import HIDDEN_ELEMENTS, Node, Element, Text, HTMLParser
from baby_browser.layout.commands import DrawCommand, DrawRect, DrawText
from baby_browser.logger import get_logger
from baby_browser.networking import URL, fetch
from baby_browser.utils import format_bytes, is_windows, tree_to_list


logger = get_logger(__name__)

WINDOW_H_MARGIN = 13
WINDOW_V_MARGIN = 18

VSTEP = 18
SCROLL_STEP = 3 * VSTEP
SCROLLBAR_WIDTH = 15

DEFAULT_CSS = Path(__file__).parent / "default.css"


def _load_page_content(url: URL):
    html = ""
    t0 = time_ns()

    if url.scheme in ("http", "https"):
        response = fetch(url)

        if response.status_code != 200:
            logger.error(
                f"The server responded with {response.status_code}: {response.status}"
            )
            logger.error(response.body)
            sys.exit(1)

        html = response.body
    elif url.scheme == "file":
        filepath = url.path

        if is_windows():
            filepath = filepath.lstrip("/")

        with open(filepath, "r") as f:
            html = f.read()
    elif url.scheme == "data":
        mime_type, content = url.path.split(",", 1)
        html = content
    else:
        raise ValueError(f"URL scheme not supported: {url}")

    logger.debug(
        f"Loaded page {format_bytes(len(html))} in {(time_ns() - t0) / 1_000_000} us"
    )

    return html


INHERITED_PROPERTIES = {
    "font-family": "Times",
    "font-size": "16px",
    "font-style": "normal",
    "font-weight": "normal",
    "color": "black",
}


def style(node: Node, rules: list[tuple[CSSSelector, dict]]):
    node.style = {}

    for property, default_value in INHERITED_PROPERTIES.items():
        if node.parent:
            node.style[property] = node.parent.style[property]
        else:
            node.style[property] = default_value

    for selector, body in rules:
        if not selector.matches(node):
            continue

        for property, value in body.items():
            node.style[property] = value

    if isinstance(node, Element) and "style" in node.attributes:
        pairs = CSSParser(node.attributes.get("style") or "").parse_rule_body()
        node.style.update(pairs)

    if node.style["font-size"].endswith("%"):
        if node.parent:
            parent_font_size = node.parent.style["font-size"]
        else:
            parent_font_size = INHERITED_PROPERTIES["font-size"]

        node_percentage = float(node.style["font-size"][:-1]) / 100
        parent_font_size = float(parent_font_size[:-2])

        node.style["font-size"] = f"{parent_font_size * node_percentage}px"

    for child in node.children:
        style(child, rules)


class BlockLayout:
    x: float
    y: float
    width: float
    height: float
    display_list: list[DrawCommand]

    def __init__(
        self,
        html_node: Node,
        parent: "DocumentLayout | BlockLayout",
        previous: Optional["BlockLayout"] = None,
    ):
        self.html_node = html_node

        self.parent = parent
        self.previous = previous
        self.children: list["BlockLayout"] = []

    def layout(self):
        self.display_list = []

        # x pos starts at its parent x
        self.x = self.parent.x
        # if there's a sibling, it starts below it, otherwise it starts
        # at its parent top edge
        self.y = (
            self.previous.y + self.previous.height if self.previous else self.parent.y
        )

        if (width := self.html_node.style.get("width", "auto")) != "auto":
            # width: explicit
            self.width = float(width)
            logger.debug("Explicit width %f", self.width)
        else:
            # width: auto, fills the horizontal space
            self.width = self.parent.width

        if (height := self.html_node.style.get("height", "auto")) != "auto":
            self.height = float(height)
            logger.debug("Explicit height %f", self.height)
        else:
            self.height = 0

        mode = self.html_node.get_layout_mode()

        if mode == "block":
            self._layout_intermediate()

            self.height = sum([child.height for child in self.children], 0.0)
        elif mode == "inline":
            self._line = []
            self.cursor_x: float = 0
            self.cursor_y: float = 0

            self._render_tree(self.html_node)

            self._flush_line()

            if not self.height:
                self.height = self.cursor_y
        else:
            logger.warning("Unsupported display mode %s", mode)

    def paint(self, display_list: list):
        bgcolor = self.html_node.style.get("background-color", "transparent")

        if bgcolor != "transparent":
            right = self.x + self.width
            bottom = self.y + self.height
            display_list.append(
                DrawRect(
                    top=self.y, left=self.x, bottom=bottom, right=right, color=bgcolor
                )
            )

        mode = self.html_node.get_layout_mode()

        if mode == "block":
            pass
        elif mode == "inline":
            display_list.extend(self.display_list)
        else:
            logger.warning("Unsupported display mode %s", mode)

        for child in self.children:
            child.paint(display_list)

    def _layout_intermediate(self):
        previous = None

        for child in self.html_node.children:
            next = BlockLayout(child, self, previous)

            if (
                isinstance(self.html_node, Element)
                and self.html_node.tag in HIDDEN_ELEMENTS
            ):
                print("Skipped head")
                continue

            self.children.append(next)
            previous = next

        for child in self.children:
            child.layout()

    def _flush_line(self):
        if not self._line:
            return

        # Tallest word in the line
        max_ascent: float = max(
            [font.metrics("ascent") for x, word, font, color in self._line]
        )
        baseline = self.cursor_y + 1.25 * max_ascent

        # Biggest descent in the line
        max_descent: float = max(
            [font.metrics("descent") for x, word, font, color in self._line]
        )

        for relative_x, word, font, color in self._line:
            x = self.x + relative_x
            y = self.y + baseline - font.metrics("ascent")
            self.display_list.append(
                DrawText(top=y, left=x, text=word, font=font, color=color)
            )

        self.cursor_x = 0
        self.cursor_y = baseline + 1.25 * max_descent
        self._line = []

    def _render_tree(self, node: Node):
        if isinstance(node, Text):
            for word in node.text.split():
                self._render_word(node, word)
        elif isinstance(node, Element):
            if node.tag in HIDDEN_ELEMENTS:
                return

            if node.tag == "br":
                self._flush_line()

            for child in node.children:
                self._render_tree(child)

    def _render_word(self, node: Node, word: str):
        font = self.get_font(node)

        word_width = font.measure(word)

        # Break line on word
        if self.cursor_x + word_width > self.width:
            self._flush_line()

        self._line.append((self.cursor_x, word, font, node.style["color"]))

        self.cursor_x += word_width + font.measure(" ")

    def get_font(self, node: Node):
        family = node.style["font-family"]
        weight = node.style["font-weight"]
        style = node.style["font-style"]

        if style == "normal":
            style = "roman"

        size = int(float(node.style["font-size"][:-2]) * 0.75)
        return get_font(family, size, weight, style)


class DocumentLayout:
    def __init__(self, node: Node) -> None:
        self.node = node
        self.parent = None
        self.children: list[BlockLayout] = []

    def layout(self, width: float):
        self.width = width - 2 * WINDOW_H_MARGIN - SCROLLBAR_WIDTH
        self.height = 0
        self.x = WINDOW_H_MARGIN
        self.y = WINDOW_V_MARGIN

        child = BlockLayout(self.node, self, None)

        # Children should be reset at each layout
        # as it's called at every windows resize
        # and the DocumentLayout must always have 1 child
        self.children = [child]
        child.layout()
        self.height = child.height + 2 * WINDOW_V_MARGIN

    def paint(self, display_list):
        self.children[0].paint(display_list)


class Browser:
    def __init__(self):
        self.window = tkinter.Tk()
        self.window.wm_title("BabyBrowser")
        self.scroll = 0
        self.canvas = tkinter.Canvas(
            self.window,
            width=800,
            height=600,
            bg="white",
        )
        self.display_list: list[DrawCommand] = []

        self.canvas.pack(fill="both", expand=True)

        self.window.bind("<Configure>", self._on_resize)
        self.window.bind("<Down>", self._on_scroll)
        self.window.bind("<Up>", self._on_scroll)
        self.window.bind("<MouseWheel>", self._on_scroll)

        with DEFAULT_CSS.open("r", encoding="utf-8") as f:
            self.default_style_sheet = CSSParser(f.read()).parse_css()

        self._previous_window_width = -1

    def _on_resize(self, event: tkinter.Event):
        window_width = self.canvas.winfo_width()

        if window_width <= 1 or window_width == self._previous_window_width:
            return

        self.document.layout(window_width)

        self.display_list = []
        self.document.paint(self.display_list)

        self.canvas.delete("all")
        self.draw()

        self._previous_window_width = window_width

    def _on_scroll(self, event: tkinter.Event):
        scroll_delta = 0

        if event.type == tkinter.EventType.MouseWheel:
            scroll_delta -= event.delta * SCROLL_STEP

            if is_windows():
                scroll_delta /= 120

        elif event.type == tkinter.EventType.KeyPress:
            if event.keysym == "Down":
                scroll_delta -= SCROLL_STEP
            elif event.keysym == "Up":
                scroll_delta += SCROLL_STEP

        if self.scroll + scroll_delta >= 0:
            max_scroll = self.document.height - self.canvas.winfo_height()
            self.scroll = min(self.scroll + scroll_delta, max_scroll)
        else:
            self.scroll = 0

        self.canvas.delete("all")
        self.draw()

    def _render_scrollbar(self):
        window_height = self.canvas.winfo_height()
        window_width = self.canvas.winfo_width()

        padding_x = 2
        # Handler Width = full width - padding - border width
        handler_width = SCROLLBAR_WIDTH - 2 * padding_x - 1
        handler_height = window_height * (window_height / self.document.height)

        handler_y = (
            (window_height - handler_height)
            * self.scroll
            / (self.document.height - window_height)
        )

        # Border
        self.canvas.create_line(
            window_width - SCROLLBAR_WIDTH,
            0,
            window_width - SCROLLBAR_WIDTH,
            window_height,
            fill="#3e3e3e",
        )

        # Background
        self.canvas.create_rectangle(
            window_width - handler_width - 2 * padding_x,
            0,
            window_width,
            window_height,
            fill="#2c2c2c",
            width=0,
        )

        # Handler
        self.canvas.create_rectangle(
            window_width - handler_width - padding_x + 1,
            handler_y,
            window_width - padding_x,
            handler_y + handler_height,
            fill="#6b6b6b",
            width=0,
        )

    def load_page(self, url_raw: str):
        url = URL.parse(url_raw)

        html = _load_page_content(url)

        self.parser = HTMLParser(html)
        self.parser.parse()

        if not self.parser.root:
            logger.error("The HTML tree is empty, did you call .parse()?")
            return

        links = [
            node.attributes.get("href") or ""
            for node in tree_to_list(self.parser.root, [])
            if isinstance(node, Element)
            and node.tag == "link"
            and node.attributes.get("rel") == "stylesheet"
            and "href" in node.attributes
        ]

        rules = self.default_style_sheet.copy()

        # Download external stylesheets
        for link in links:
            try:
                response = fetch(url.resolve(link))
            except Exception as err:
                logger.error("Couldn't retrieve file %s", link)
                print(err)
                continue

            rules.extend(CSSParser(response.body).parse_css())

        def cascade_priority(rule: tuple[CSSSelector, dict]):
            selector, _ = rule
            return selector.priority

        style(self.parser.root, sorted(rules, key=cascade_priority))

        self.document = DocumentLayout(self.parser.root)
        self.document.layout(self.canvas.winfo_width())

        self.display_list = []
        self.document.paint(self.display_list)

        self.draw()

    def draw(self):
        height = self.canvas.winfo_height()

        for command in self.display_list:
            is_before_viewport = command.bottom < self.scroll
            is_after_viewport = command.top > self.scroll + height

            # If the text is not visible skip the rendering
            if is_before_viewport or is_after_viewport:
                continue

            command.execute(self.scroll, self.canvas)

        self._render_scrollbar()
