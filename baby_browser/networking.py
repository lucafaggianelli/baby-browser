from dataclasses import dataclass
import socket
from typing import List


HTTP_NEWLINE = "\r\n"


@dataclass
class URL:
    scheme: str
    host: str
    path: str
    port: int = 80


@dataclass
class HttpResponse:
    headers: dict
    body: str


def parse_url(url: str):
    assert url.startswith("http://"), 'Only http schema is supported'

    url_no_schema = url[len("http://"):]

    parts = url_no_schema.split("/", 1)
    path = "/" + (parts[1] if len(parts) == 2 else "")

    return URL("http", parts[0], path, 80)


def _encode_http_request(lines: List[str]):
    return HTTP_NEWLINE.join(lines + ["", ""]).encode("utf-8")


def fetch(url: str, method: str = None):
    sock = socket.socket(
        family=socket.AF_INET,
        type=socket.SOCK_STREAM,
        proto=socket.IPPROTO_TCP,
    )

    url_parsed = parse_url(url)

    sock.connect((url_parsed.host, url_parsed.port))

    payload = _encode_http_request([
        f"{method or 'GET'} {url_parsed.path} HTTP/1.0",
        f"HOST: {url_parsed.host}",
    ])

    sent_bytes = sock.send(payload)

    if sent_bytes != len(payload):
        print(f"Sent {sent_bytes}/{len(payload)} bytes")

    response = sock.makefile("r", encoding="utf-8", newline=HTTP_NEWLINE)

    status_line = response.readline()
    version, status_code, status = status_line.split(" ", 2)
    status_code = int(status_code)

    assert status_code == 200, f"The responded with {status_code}: {status}"

    headers = {}
    while True:
        line = response.readline()

        if line == HTTP_NEWLINE:
            break

        header, value = line.split(":", 1)
        headers[header.lower()] = value.strip()

    assert "transfer-encoding" not in headers
    assert "content-encoding" not in headers

    body = response.read()
    sock.close()

    return HttpResponse(headers, body)
