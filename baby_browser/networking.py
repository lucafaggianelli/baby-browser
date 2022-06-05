from typing import List, Union

from dataclasses import dataclass
import gzip
import io
import socket
import ssl
from time import time_ns

from baby_browser.utils import format_bytes
from baby_browser.logger import get_logger


HTTP_NEWLINE = "\r\n"


logger = get_logger(__name__)


@dataclass
class URL:
    scheme: str
    host: str = None
    path: str = ""
    port: int = 80


@dataclass
class HttpResponse:
    headers: dict
    body: str
    status: str
    status_code: int


def _get_available_content_encoding():
    return "gzip"
    # return "*"


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

    return URL(scheme, host, path, port)


def _encode_http_request(lines: List[str]):
    return HTTP_NEWLINE.join(lines + ["", ""]).encode("utf-8")


def fetch(url: Union[str, URL], method: str = None, headers: dict = None):
    sock = socket.socket(
        family=socket.AF_INET,
        type=socket.SOCK_STREAM,
        proto=socket.IPPROTO_TCP,
    )

    url_parsed = parse_url(url) if type(url) == str else url

    sock.connect((url_parsed.host, url_parsed.port))

    if url_parsed.scheme == "https":
        ctx = ssl.create_default_context()
        sock = ctx.wrap_socket(sock, server_hostname=url_parsed.host)

    content_encoding = _get_available_content_encoding()

    request_headers = {
        "Accept-Encoding": content_encoding,
        "Connection": "close",
        "User-Agent": "BabyBrowser/0.1.0",
        **(headers or {}),
        "Host": url_parsed.host,
    }

    payload = [
        f"{method or 'GET'} {url_parsed.path} HTTP/1.1",
    ]

    payload.extend(
        [f"{header}: {value.strip()}" for header, value in request_headers.items()]
    )

    encoded_payload = _encode_http_request(payload)
    logger.debug("Sending HTTP request: \n" + encoded_payload.decode("utf-8"))

    sent_bytes = sock.send(encoded_payload)

    if sent_bytes != len(encoded_payload):
        logger.warn(f"Sent only {sent_bytes}/{len(encoded_payload)} bytes")

    t0 = time_ns()
    response = sock.makefile("rb")

    status_line = response.readline().decode("utf-8")
    version, status_code, status = status_line.split(" ", 2)
    status_code = int(status_code)

    response_headers = {}
    while True:
        line = response.readline().decode("utf-8")

        if line == HTTP_NEWLINE:
            break

        header, value = line.split(":", 1)
        response_headers[header.lower()] = value.strip()

    if response_headers.get("content-encoding") == "gzip":
        if response_headers["transfer-encoding"] == "chunked":
            data = _read_chunked_response(response)
        else:
            logger.error(
                f"Unsupported Transfer-Encoding {response_headers['transfer-encoding']}"
            )

        body = gzip.decompress(data).decode("utf-8")
    else:
        body = response.read()

    logger.debug(f"Read {format_bytes(len(body))} in {(time_ns() - t0) / 1000} ms")

    sock.close()

    return HttpResponse(response_headers, body, status, status_code)
