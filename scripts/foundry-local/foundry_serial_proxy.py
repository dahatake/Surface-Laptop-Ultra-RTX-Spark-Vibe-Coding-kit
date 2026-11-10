"""Loopback serializing proxy for Foundry Local CLI 0.13.0.

On this PC, concurrent chat requests to Foundry Local 0.13.0 GPU models fail
("CUDA error in CopyCompletedLocked" / "GenerateNext") and can leave the daemon
in a broken state. GitHub Copilot can issue parallel requests, so this proxy
forwards them to Foundry Local one at a time and retries a failed request once.
"""

import os
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

UPSTREAM = "http://127.0.0.1:5273"
LISTEN = ("127.0.0.1", 5274)
RETRY_MARKERS = (b"CopyCompletedLocked", b"GenerateNext", b"CUDA error")
LOG = Path(
    os.environ.get("FOUNDRY_PROXY_LOG")
    or Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Programs" / "FoundryLocal" / "proxy.log"
)
GPU_LOCK = threading.Lock()


def log(message: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(f"{datetime.now(timezone.utc).isoformat()} {message}\n")


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def log_message(self, format, *args):
        pass

    def _send(self, status, headers, body_iter):
        self.send_response(status)
        for key in ("Content-Type", "Cache-Control"):
            if headers.get(key):
                self.send_header(key, headers[key])
        self.send_header("Connection", "close")
        self.end_headers()
        for chunk in body_iter:
            self.wfile.write(chunk)
            self.wfile.flush()

    def _open(self, method, body=None):
        request = urllib.request.Request(
            UPSTREAM + self.path,
            data=body,
            method=method,
            headers={"Content-Type": "application/json"} if body else {},
        )
        return urllib.request.urlopen(request, timeout=900)

    @staticmethod
    def _stream(response):
        while True:
            chunk = response.read1(65536)
            if not chunk:
                break
            yield chunk

    def _relay(self, method, body=None):
        try:
            with self._open(method, body) as response:
                self._send(response.status, response.headers, self._stream(response))
            return None
        except urllib.error.HTTPError as error:
            return error.code, error.headers, error.read()
        except (BrokenPipeError, ConnectionResetError):
            return None
        except OSError as error:
            return 502, {"Content-Type": "text/plain"}, str(error).encode()

    def do_GET(self):
        failure = self._relay("GET")
        if failure:
            self._send(failure[0], failure[1], [failure[2]])

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        queued = time.monotonic()
        with GPU_LOCK:
            waited = time.monotonic() - queued
            if waited > 1:
                log(f"serialized path={self.path} waited_s={waited:.1f}")
            failure = self._relay("POST", body)
            if failure and any(m in failure[2] for m in RETRY_MARKERS):
                log(f"retry path={self.path} status={failure[0]} detail={failure[2][:200]!r}")
                time.sleep(1)
                failure = self._relay("POST", body)
                if failure:
                    log(f"retry failed status={failure[0]} detail={failure[2][:200]!r}")
        if failure:
            self._send(failure[0], failure[1], [failure[2]])


if __name__ == "__main__":
    server = ThreadingHTTPServer(LISTEN, Handler)
    log(f"proxy listening on http://{LISTEN[0]}:{LISTEN[1]} -> {UPSTREAM}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        sys.exit(0)
