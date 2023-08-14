from typing import List, Optional

from dataclasses import dataclass
import gzip
import io
import socket
import ssl
from time import time_ns

from baby_browser.utils import format_bytes
from baby_browser.logger import get_logger


CONTENT_TYPE_DEFAULT_CHARSET = "utf-8"
HTTP_DEFAULT_CHARSET = "ISO-8859-1"
HTTP_NEWLINE = "\r\n"


logger = get_logger(__name__)


@dataclass
class URL:
    scheme: str
    host: Optional[str] = None
    path: str = ""
    port: int = 80


@dataclass
class HttpResponse:
    headers: dict
    body: str
    status: str
    status_code: int

    @property
    def is_redirect(self):
        return self.status_code >= 300 and self.status_code < 400


def _get_available_content_encoding():
    return "gzip"


def _get_scheme_default_port(scheme: str):
    return 80 if scheme == "http" else 443


def _read_chunked_response(reader: io.BufferedReader):
    data = bytes()

    while True:
        chunk_length = int(reader.readline().strip(), base=16)

        if chunk_length == 0:
            break

        data += reader.read(chunk_length)

        # Each chunk is followed by a newline
        reader.readline()

    return data


def _parse_header_with_attributes(header_line: str):
    parts = header_line.split(";")

    attributes = {}

    for attribute in parts[1:]:
        key, value = attribute.split("=")
        attributes[key.strip().lower()] = value.strip()

    return parts[0], attributes


def parse_url(url: str):
    scheme, url_no_scheme = url.split(":", 1)
    url_no_scheme = url_no_scheme.removeprefix("//")

    if scheme == "data":
        return URL(scheme, path=url_no_scheme)

    parts = url_no_scheme.split("/", 1)
    host_parts = parts[0].split(":", 1)

    host = host_parts[0]
    port = host_parts[1] if len(host_parts) == 2 else _get_scheme_default_port(scheme)
    path = "/" + (parts[1] if len(parts) == 2 else "")

    return URL(scheme, host, path, int(port))


def _encode_http_request(lines: List[str]):
    return HTTP_NEWLINE.join(lines + ["", ""]).encode(HTTP_DEFAULT_CHARSET)


def _fetch_inner(
    url: URL,
    method: str,
    headers: Optional[dict] = None,
    max_redirects: int = 5,
    redirects_count: int = 0,
):
    t0 = time_ns()

    sock = socket.socket(
        family=socket.AF_INET,
        type=socket.SOCK_STREAM,
        proto=socket.IPPROTO_TCP,
    )

    sock.connect((url.host, url.port))

    if url.scheme == "https":
        ctx = ssl.create_default_context()
        sock = ctx.wrap_socket(sock, server_hostname=url.host)

    request_headers = {
        "Accept-Encoding": _get_available_content_encoding(),
        "Connection": "close",
        "User-Agent": "BabyBrowser/0.1.0",
        **(headers or {}),
        "Host": url.host,
    }

    payload = [
        f"{method or 'GET'} {url.path} HTTP/1.1",
    ]

    payload.extend(
        [f"{header}: {value.strip()}" for header, value in request_headers.items()]
    )

    encoded_payload = _encode_http_request(payload)

    sent_bytes = sock.send(encoded_payload)

    if sent_bytes != len(encoded_payload):
        logger.warn(f"Sent only {sent_bytes}/{len(encoded_payload)} bytes")

    response = sock.makefile("rb")

    status_line = response.readline().decode(HTTP_DEFAULT_CHARSET)
    version, status_code, status = status_line.split(" ", 2)
    status_code = int(status_code)

    response_headers = {}
    while True:
        line = response.readline().decode(HTTP_DEFAULT_CHARSET)

        if line == HTTP_NEWLINE:
            break

        header, value = line.split(":", 1)
        response_headers[header.lower()] = value.strip()

    logger.debug(f"Received headers: {response_headers}")

    content_encoding = response_headers.get("content-encoding")
    transfer_encoding = response_headers.get("transfer-encoding")

    content_type, content_type_attributes = _parse_header_with_attributes(
        response_headers.get("content-type", "text/html")
    )

    if not transfer_encoding:
        data = response.read()
    elif transfer_encoding == "chunked":
        data = _read_chunked_response(response)
    else:
        raise ValueError(f"Unsupported Transfer-Encoding: {transfer_encoding}")

    if not content_encoding:
        body = data
    elif content_encoding == "gzip":
        body = gzip.decompress(data)
    else:
        raise ValueError(f"Unsupported Content-Encoding: {content_encoding}")

    body = body.decode(
        content_type_attributes.get("charset", CONTENT_TYPE_DEFAULT_CHARSET)
    )

    logger.debug(
        f"Read {format_bytes(len(data))} ({content_encoding=}) in {(time_ns() - t0) / 1_000_000} us"
    )

    sock.close()

    response = HttpResponse(response_headers, body, status, status_code)

    if response.is_redirect and max_redirects > 0 and redirects_count < max_redirects:
        location = response.headers.get("location")

        if location:
            location_url = parse_url(location)
            logger.debug(f"Following redirect to {location}")

            response = _fetch_inner(
                location_url, method, headers, max_redirects, redirects_count + 1
            )
        else:
            logger.error("Found a redirect without the Location header")

    return response


def fetch(
    url: str | URL,
    method: Optional[str] = None,
    headers: Optional[dict] = None,
    max_redirects: int = 5,
):
    _url = parse_url(url) if isinstance(url, str) else url
    _method = method or "GET"

    return _fetch_inner(_url, _method, headers, max_redirects, 0)
