import sys
import tkinter

from baby_browser.html import lexer
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
        self._layout(self.loaded_text)
        self.canvas.delete("all")
        self.draw()

    def _on_scroll(self, event: tkinter.Event):
        scroll_delta = 0

        if event.type == tkinter.EventType.MouseWheel:
            scroll_delta -= event.delta * SCROLL_STEP
        elif event.type == tkinter.EventType.KeyPress:
            if event.keysym == 'Down':
                scroll_delta -= SCROLL_STEP
            elif event.keysym == 'Up':
                scroll_delta += SCROLL_STEP

        if self.scroll + scroll_delta >= 0:
            self.scroll += scroll_delta
        else:
            return

        self.canvas.delete("all")
        self.draw()

    def _layout(self, text):
        self.display_list = []
        cursor_x, cursor_y = HSTEP, VSTEP

        for c in text:
            if c == "\n":
                cursor_y += VSTEP * 1.5
                cursor_x = HSTEP
                continue

            if cursor_x + 2 * HSTEP >= self.canvas.winfo_width():
                cursor_y += VSTEP
                cursor_x = HSTEP
            else:
                cursor_x += HSTEP

            self.display_list.append((cursor_x, cursor_y, c))

    def load_page(self, url: str):
        html = _load_page_content(url)

        self.loaded_text = lexer(html)

        self._layout(self.loaded_text)
        self.draw()

    def draw(self):
        for x, y, c in self.display_list:
            if (y > self.scroll + self.canvas.winfo_height()) or (y + VSTEP < self.scroll):
                continue

            self.canvas.create_text(x, y - self.scroll, text=c)
