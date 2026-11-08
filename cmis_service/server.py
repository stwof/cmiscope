"""Standard-library HTTP server: routing, static hosting and error handling.

Depends only on http.server / sqlite3 / json. ThreadingHTTPServer handles
concurrent read requests. Static paths are resolved against static_dir and
checked for traversal before any file is opened.
"""

from __future__ import annotations

import json
import logging
import mimetypes
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from .api import dispatch
from .config import Settings

log = logging.getLogger("cmis.http")

MIME = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".woff2": "font/woff2",
    ".woff": "font/woff",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".map": "application/json; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
    ".md": "text/markdown; charset=utf-8",
}


class Handler(BaseHTTPRequestHandler):
    server_version = "CMIScope/1.0"
    sys_version = ""
    protocol_version = "HTTP/1.1"

    settings: Settings
    conn: sqlite3.Connection

    # ------------------------------------------------------------------ responses
    def _send_bytes(self, status: int, content: bytes, content_type: str,
                    cache: str = "no-store", extra: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", cache)
        self.send_header("X-Content-Type-Options", "nosniff")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(content)

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self._send_bytes(status, body, "application/json; charset=utf-8")

    def _error(self, status: int, code: str, message: str, details=None) -> None:
        err = {"code": code, "message": message}
        if details is not None:
            err["details"] = details
        self._send_json(status, {"ok": False, "error": err})

    def log_message(self, fmt: str, *args) -> None:
        log.debug("%s - %s", self.address_string(), fmt % args)

    # ------------------------------------------------------------------ static files
    def _static(self, path: str) -> None:
        root = self.settings.static_dir.resolve()
        rel = "index.html" if path in ("/", "") else path.lstrip("/")
        target = (root / rel).resolve()
        try:
            target.relative_to(root)
        except ValueError:
            self._error(403, "FORBIDDEN", "Access outside the static directory is forbidden")
            return
        if not target.is_file():
            # Single-page fallback for extension-less navigation paths
            if "." not in Path(rel).name:
                target = root / "index.html"
            if not target.is_file():
                self._error(404, "NOT_FOUND", f"Static resource not found: /{rel}")
                return
        ctype = MIME.get(target.suffix.lower(),
                         mimetypes.guess_type(str(target))[0] or "application/octet-stream")
        cache = "public, max-age=3600" if "vendor" in target.parts else "no-cache"
        try:
            content = target.read_bytes()
        except OSError as exc:
            self._error(500, "IO_ERROR", "Failed to read static resource", str(exc))
            return
        self._send_bytes(200, content, ctype, cache)

    # ------------------------------------------------------------------ dispatch
    def _handle(self, method: str) -> None:
        try:
            split = urlsplit(self.path)
            path = unquote(split.path).rstrip("/") or "/"
            query = parse_qs(split.query, keep_blank_values=True)

            if not path.startswith("/api/"):
                if method not in ("GET", "HEAD"):
                    self._error(405, "METHOD_NOT_ALLOWED", "Static resources only support GET/HEAD")
                    return
                self._static(path)
                return

            body: object = None
            if method in ("POST", "PUT", "PATCH"):
                raw_len = self.headers.get("Content-Length", "0")
                try:
                    length = int(raw_len)
                except ValueError:
                    self._error(400, "BAD_REQUEST", "Invalid Content-Length")
                    return
                if length <= 0:
                    self._error(400, "BAD_REQUEST", "Request body must not be empty")
                    return
                if length > self.settings.max_body_bytes:
                    self._error(413, "PAYLOAD_TOO_LARGE",
                                f"Request body exceeds {self.settings.max_body_bytes} bytes")
                    return
                raw = self.rfile.read(length)
                try:
                    body = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    self._error(400, "INVALID_JSON", "Request body is not valid JSON", str(exc))
                    return

            status, payload = dispatch(self.conn, self.settings, method, path, query, body)
            self._send_json(status, payload)
            log.info("%s %s -> %s", method, self.path, status)
        except (ConnectionResetError, BrokenPipeError):
            pass
        except Exception as exc:  # Last-resort guard
            log.exception("HTTP handler failed")
            try:
                self._error(500, "INTERNAL_ERROR", "Internal service error", str(exc))
            except Exception:
                pass

    def do_GET(self): self._handle("GET")
    def do_HEAD(self): self._handle("HEAD")
    def do_POST(self): self._handle("POST")
    def do_PUT(self): self._handle("PUT")
    def do_PATCH(self): self._handle("PATCH")
    def do_DELETE(self): self._handle("DELETE")


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, addr, settings: Settings, conn: sqlite3.Connection):
        self.settings = settings
        self.conn = conn
        super().__init__(addr, Handler)


def serve(settings: Settings, conn: sqlite3.Connection) -> None:
    Handler.settings = settings
    Handler.conn = conn
    httpd = Server((settings.host, settings.port), settings, conn)
    url = f"http://{settings.host}:{httpd.server_address[1]}/"
    log.info("CMIScope started -> %s", url)
    log.info("read_only=%s | access_mode=%s | default_language=%s",
             settings.read_only, settings.access_mode, settings.default_language)
    print(f"\n  CMIScope ready: {url}\n  Press Ctrl+C to stop.\n", flush=True)
    try:
        httpd.serve_forever(poll_interval=0.3)
    finally:
        httpd.server_close()
        log.info("HTTP server stopped")
