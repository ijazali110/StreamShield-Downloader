from __future__ import annotations

import json
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

from PySide6.QtCore import QObject, Signal


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
MAX_BODY_BYTES = 1024 * 1024


class BrowserBridgeSignals(QObject):
    media_received = Signal(object)
    status = Signal(str)


class BrowserBridge:
    """Localhost bridge used by the Shield Stream browser companion.

    V2 adds a random per-process session token. Normal websites are rejected by
    Origin checks, and companion writes must also present the token returned by
    /health. The token changes every time Shield Stream starts and is never saved.
    """

    def __init__(
        self,
        signals: BrowserBridgeSignals,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
    ) -> None:
        self.signals = signals
        self.host = host
        self.port = int(port)
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self.session_token = secrets.token_urlsafe(32)
        self._commands: list[dict] = []
        self._commands_lock = threading.Lock()

    @staticmethod
    def _valid_http_url(value: Any) -> bool:
        if not isinstance(value, str):
            return False
        try:
            parsed = urlparse(value.strip())
            return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
        except Exception:
            return False

    def request_refresh(self, item) -> bool:
        """Ask the companion to re-capture a browser stream when possible."""
        try:
            tab_id = int(getattr(item, "tab_id", 0) or 0)
        except Exception:
            tab_id = 0
        if tab_id <= 0:
            return False
        command = {
            "type": "refresh_stream",
            "tab_id": tab_id,
            "group_id": str(getattr(item, "group_id", "") or ""),
            "page_url": str(getattr(item, "page_url", "") or ""),
            "title": str(getattr(item, "title", "") or ""),
        }
        with self._commands_lock:
            # Keep only the latest equivalent request.
            self._commands = [c for c in self._commands if not (c.get("type") == command["type"] and c.get("tab_id") == tab_id and c.get("group_id") == command["group_id"])]
            self._commands.append(command)
            self._commands = self._commands[-20:]
        return True

    def _take_commands(self) -> list[dict]:
        with self._commands_lock:
            commands = list(self._commands)
            self._commands.clear()
        return commands

    def start(self) -> bool:
        if self._server is not None:
            return True

        owner = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "Shield StreamBridge/2.0"

            def log_message(self, _format: str, *_args) -> None:
                return

            def _origin_allowed(self) -> bool:
                origin = str(self.headers.get("Origin") or "").strip()
                return not origin or origin.startswith("chrome-extension://")

            def _token_allowed(self) -> bool:
                supplied = str(self.headers.get("X-StreamForge-Token") or "").strip()
                return bool(supplied) and secrets.compare_digest(supplied, owner.session_token)

            def _cors(self) -> None:
                origin = str(self.headers.get("Origin") or "").strip()
                allow_origin = origin if origin.startswith("chrome-extension://") else "*"
                self.send_header("Access-Control-Allow-Origin", allow_origin)
                self.send_header("Vary", "Origin")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type, X-StreamForge-Token")
                self.send_header("Cache-Control", "no-store")

            def _json(self, status: int, payload: dict) -> None:
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self._cors()
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_OPTIONS(self) -> None:
                if not self._origin_allowed():
                    self._json(403, {"ok": False, "error": "Origin not allowed"})
                    return
                self.send_response(204)
                self._cors()
                self.end_headers()

            def do_GET(self) -> None:
                if not self._origin_allowed():
                    self._json(403, {"ok": False, "error": "Origin not allowed"})
                    return
                path = self.path.split("?", 1)[0].rstrip("/")
                if path == "/health":
                    # Only a chrome-extension Origin can obtain the write token.
                    origin = str(self.headers.get("Origin") or "").strip()
                    payload = {"ok": True, "app": "Shield Stream", "bridge": "2.0"}
                    if not origin or origin.startswith("chrome-extension://"):
                        payload["token"] = owner.session_token
                    self._json(200, payload)
                    return
                if path == "/commands":
                    if not self._token_allowed():
                        self._json(401, {"ok": False, "error": "Token required"})
                        return
                    self._json(200, {"ok": True, "commands": owner._take_commands()})
                    return
                self._json(404, {"ok": False, "error": "Not found"})

            def do_POST(self) -> None:
                if not self._origin_allowed():
                    self._json(403, {"ok": False, "error": "Origin not allowed"})
                    return
                if not self._token_allowed():
                    self._json(401, {"ok": False, "error": "Companion token missing or expired. Reconnect the extension."})
                    return
                if self.path.split("?", 1)[0].rstrip("/") != "/add-media":
                    self._json(404, {"ok": False, "error": "Not found"})
                    return

                try:
                    length = int(self.headers.get("Content-Length", "0") or 0)
                except ValueError:
                    length = 0
                if length <= 0 or length > MAX_BODY_BYTES:
                    self._json(400, {"ok": False, "error": "Invalid request size"})
                    return

                try:
                    raw = self.rfile.read(length)
                    data = json.loads(raw.decode("utf-8"))
                except Exception:
                    self._json(400, {"ok": False, "error": "Invalid JSON"})
                    return

                payloads = data if isinstance(data, list) else [data]
                accepted = 0
                for payload in payloads[:100]:
                    if not isinstance(payload, dict):
                        continue
                    url = str(payload.get("url") or "").strip()
                    if not owner._valid_http_url(url):
                        continue
                    clean = {
                        "url": url,
                        "page_url": str(payload.get("page_url") or "").strip(),
                        "frame_url": str(payload.get("frame_url") or "").strip(),
                        "title": str(payload.get("title") or "").strip(),
                        "thumbnail": str(payload.get("thumbnail") or "").strip(),
                        "kind": str(payload.get("kind") or "").strip().lower(),
                        "source": str(payload.get("source") or "chrome-extension").strip(),
                        "user_agent": str(payload.get("user_agent") or "").strip(),
                        "referer": str(
                            payload.get("referer")
                            or payload.get("frame_url")
                            or payload.get("page_url")
                            or ""
                        ).strip(),
                        "origin": str(payload.get("origin") or "").strip(),
                        "content_type": str(payload.get("content_type") or "").strip(),
                        "detector": str(payload.get("detector") or "").strip(),
                        "verified": bool(payload.get("verified")),
                        "status_code": int(payload.get("status_code") or 0) if str(payload.get("status_code") or "0").isdigit() else 0,
                        "content_length": int(payload.get("content_length") or 0) if str(payload.get("content_length") or "0").isdigit() else 0,
                        "tab_id": int(payload.get("tab_id") or 0) if str(payload.get("tab_id") or "0").isdigit() else 0,
                        "group_id": str(payload.get("group_id") or "").strip(),
                        "quality_hint": str(payload.get("quality_hint") or "").strip(),
                        "preferred_quality": str(payload.get("preferred_quality") or payload.get("quality_hint") or "").strip(),
                        "detected_at": float(payload.get("detected_at") or 0) if str(payload.get("detected_at") or "").replace(".", "", 1).isdigit() else 0.0,
                    }
                    owner.signals.media_received.emit(clean)
                    accepted += 1

                self._json(200, {"ok": True, "accepted": accepted})

        try:
            self._server = ThreadingHTTPServer((self.host, self.port), Handler)
            self._server.daemon_threads = True
        except OSError as exc:
            self._server = None
            self.signals.status.emit(f"Browser companion bridge unavailable: {exc}")
            return False

        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="Shield StreamBrowserBridge",
            daemon=True,
        )
        self._thread.start()
        self.signals.status.emit(f"Browser companion ready on {self.host}:{self.port}")
        return True

    def stop(self) -> None:
        server = self._server
        self._server = None
        if server is None:
            return
        try:
            server.shutdown()
            server.server_close()
        except Exception:
            pass
        self._thread = None
