import sys
from time import time_ns
import tkinter
from typing import Optional
from baby_browser.fonts import FontSlant, FontWeight, get_font

from baby_browser.html import HIDDEN_ELEMENTS, Node, Element, Text, HTMLParser
from baby_browser.layout.commands import DrawCommand, DrawRect, DrawText
from baby_browser.logger import get_logger
from baby_browser.networking import fetch, parse_url
from baby_browser.utils import format_bytes


logger = get_logger(__name__)

WINDOW_H_MARGIN = 13
WINDOW_V_MARGIN = 18

VSTEP = 18
SCROLL_STEP = 3 * VSTEP
SCROLLBAR_WIDTH = 15


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
        # fills the horizontal space
        self.width = self.parent.width

        mode = self.html_node.get_layout_mode()

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

            self._render_tree(self.html_node)

            self._flush_line()

            self.height = self.cursor_y

    def paint(self, display_list: list):
        if isinstance(self.html_node, Element) and self.html_node.tag == "pre":
            right = self.x + self.width
            bottom = self.y + self.height
            display_list.append(
                DrawRect(
                    top=self.y, left=self.x, bottom=bottom, right=right, color="grey"
                )
            )

        if self.html_node.get_layout_mode() == "block":
            for child in self.children:
                child.paint(display_list)
        else:
            display_list.extend(self.display_list)

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
            self.display_list.append(DrawText(top=y, left=x, text=word, font=font))

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
            if node.tag in HIDDEN_ELEMENTS:
                return

            self._open_tag(node)

            for child in node.children:
                self._render_tree(child)

            self._close_tag(node)

    def _render_word(self, word: str):
        font = get_font(
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
        )
        self.display_list: list[DrawCommand] = []

        self.canvas.pack(fill="both", expand=True)

        self.window.bind("<Configure>", self._on_resize)
        self.window.bind("<Down>", self._on_scroll)
        self.window.bind("<Up>", self._on_scroll)
        self.window.bind("<MouseWheel>", self._on_scroll)

    def _on_resize(self, event: tkinter.Event):
        window_width = self.canvas.winfo_width()

        if window_width <= 1:
            return

        self.document.layout(window_width)

        self.display_list = []
        self.document.paint(self.display_list)

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

    def load_page(self, url: str):
        html = _load_page_content(url)

        self.parser = HTMLParser(html)
        self.parser.parse()

        if not self.parser.root:
            logger.error("The HTML tree is empty, did you call .parse()?")
            return

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
