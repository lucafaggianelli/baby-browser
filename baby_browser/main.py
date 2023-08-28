import pathlib
import sys
import tkinter

from baby_browser.browser import Browser


DEFAULT_HTML_URI = (
    pathlib.Path(__file__).parent / ".." / "browser.engineering.html"
).as_uri()


def main():
    url = sys.argv[1] if len(sys.argv) >= 2 else DEFAULT_HTML_URI

    browser = Browser()
    browser.load_page(url)
    tkinter.mainloop()


if __name__ == "__main__":
    main()
