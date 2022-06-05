import sys

from baby_browser.networking import fetch
from baby_browser.html import render_html


def main():
    response = fetch(sys.argv[1])

    render_html(response.body)


if __name__ == '__main__':
    main()
