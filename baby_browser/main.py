import pathlib
import sys

from baby_browser.html import render_html
from baby_browser.logger import get_logger
from baby_browser.networking import fetch, parse_url


logger = get_logger(__name__)


DEFAULT_HTML_URI = "file://" + str(pathlib.Path(__file__).parent / '..' / 'browser.engineering.html')


def load_page(url: str):
    parsed_url = parse_url(url)

    html = ""

    if parsed_url.scheme in ('http', 'https'):
        response = fetch(parsed_url)

        if response.status_code != 200:
            logger.error(f"The server responded with {response.status_code}: {response.status}")
            logger.error(response.body)
            sys.exit(1)

        html = response.body
    elif parsed_url.scheme == 'file':
        with open(parsed_url.path, 'r') as f:
            html = f.read()
    else:
        raise ValueError(f"URL scheme not supported: {url}")

    render_html(html)


def main():
    url = sys.argv[1] if len(sys.argv) >= 2 else DEFAULT_HTML_URI

    load_page(url)


if __name__ == '__main__':
    main()
