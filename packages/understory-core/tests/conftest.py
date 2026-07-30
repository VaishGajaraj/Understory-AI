"""Offline HTTP server fixture for the ingest tests.

Every test in this package runs without network: the fixture binds a real HTTP
server to loopback on an ephemeral port and drives it with a per-request script,
so the resilient download path is exercised against genuine sockets, status
codes, and Range headers rather than a mock of what we imagine requests does.

The server is scripted: ``server.script`` is a list of behaviours consumed one
per request (falling back to ``"ok"`` when exhausted), and ``server.requests``
records the method, path, and headers of each request for assertions like "did
the client actually send a Range on the retry?".
"""

from __future__ import annotations

import socketserver
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest


class _LoopbackServer(ThreadingHTTPServer):
    """Loopback HTTP server that does not touch DNS.

    ``HTTPServer.server_bind`` calls ``socket.getfqdn()``, which blocks on a
    reverse-DNS lookup for tens of seconds in a network-isolated sandbox. We
    only ever bind to 127.0.0.1, so skip the lookup entirely.
    """

    def server_bind(self) -> None:
        socketserver.TCPServer.server_bind(self)
        self.server_name = "127.0.0.1"
        self.server_port = self.server_address[1]


@dataclass
class ServerControl:
    """Handle to the running test server: its URL, script, and request log."""

    host: str
    port: int
    body: bytes = b""
    script: list[str] = field(default_factory=list)
    requests: list[dict] = field(default_factory=list)
    honor_range: bool = True
    retry_after: str = "0"

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}/granule"

    def next_behavior(self) -> str:
        return self.script.pop(0) if self.script else "ok"


def _make_handler(control: ServerControl) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # silence the default stderr spam
            pass

        def _record(self) -> None:
            control.requests.append(
                {"method": self.command, "path": self.path, "headers": dict(self.headers)}
            )

        def do_GET(self) -> None:  # noqa: N802 (http.server API)
            self._record()
            behavior = control.next_behavior()
            body = control.body

            if behavior == "500":
                self.send_response(500)
                self.end_headers()
                return
            if behavior == "503-retry-after":
                self.send_response(503)
                self.send_header("Retry-After", control.retry_after)
                self.end_headers()
                return
            if behavior == "403":
                self.send_response(403)
                self.end_headers()
                return
            if behavior == "truncate":
                # Declare the full length but send only part of it, then hang up.
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Accept-Ranges", "bytes")
                self.end_headers()
                self.wfile.write(body[: len(body) // 2])
                return
            if behavior == "ignore-range":
                # A server that ignores Range answers 200 with the whole body.
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Accept-Ranges", "bytes")
                self.end_headers()
                self.wfile.write(body)
                return
            if behavior == "lying-206":
                # Claims to honour the range but resumes from the wrong offset:
                # a 206 whose Content-Range start is not what was requested.
                start = len(body) // 4
                chunk = body[start:]
                self.send_response(206)
                self.send_header("Content-Range", f"bytes {start}-{len(body) - 1}/{len(body)}")
                self.send_header("Content-Length", str(len(chunk)))
                self.send_header("Accept-Ranges", "bytes")
                self.end_headers()
                self.wfile.write(chunk)
                return
            if behavior == "garbled-206":
                # A 206 whose Content-Range cannot be parsed at all.
                self.send_response(206)
                self.send_header("Content-Range", "pears ?-?/?")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Accept-Ranges", "bytes")
                self.end_headers()
                self.wfile.write(body)
                return

            # "ok": honour Range when asked and allowed to.
            range_header = self.headers.get("Range")
            if range_header and control.honor_range:
                start = int(range_header.split("=")[1].split("-")[0])
                chunk = body[start:]
                self.send_response(206)
                self.send_header("Content-Range", f"bytes {start}-{len(body) - 1}/{len(body)}")
                self.send_header("Content-Length", str(len(chunk)))
                self.send_header("Accept-Ranges", "bytes")
                self.end_headers()
                self.wfile.write(chunk)
                return

            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()
            self.wfile.write(body)

    return Handler


@pytest.fixture
def http_server():
    """Yield a ``ServerControl`` for a loopback server running in a thread."""
    control = ServerControl(host="127.0.0.1", port=0)
    server = _LoopbackServer((control.host, 0), _make_handler(control))
    control.port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield control
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
