"""Localhost control API for XML-driven demos (opt-in).

# Demo HTTP API

Enable with env ``BTFVIEWER_DEMO_API=1`` (optional ``BTFVIEWER_DEMO_API_PORT``).
The demo runner posts JSON ``{"op": "...", ...}`` to ``POST /demo``.

Ops include ``highlight``, ``cursors``, ``clear_cursors``, ``clear_bookmarks``,
``clear_annotations``, ``zoom_range``, ``fit``, ``zoom_1to1``, ``limit``, ``stats_section``,
``jump_wcet``, ``move_view``, ``show_message``, ``panel``, ``target``, ``view_mode``, ``cpu_load``, ``analysis``, ``tick_dist``,
``find``, ``settings``, and ``ui`` (alias: ``command``).
"""
from __future__ import annotations

import json
import os
import signal
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Dict, Optional

from PySide6.QtCore import QObject, Qt, Signal, Slot


def demo_api_enabled() -> bool:
    raw = (os.environ.get("BTFVIEWER_DEMO_API") or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def demo_api_port() -> int:
    try:
        return int(os.environ.get("BTFVIEWER_DEMO_API_PORT") or "8765")
    except ValueError:
        return 8765


def ignore_sigint_for_demo() -> None:
    """Keep Ctrl-C on the demo runner; do not interrupt Qt event handlers."""
    if not demo_api_enabled():
        return
    try:
        signal.signal(signal.SIGINT, signal.SIG_IGN)
    except Exception:
        pass


class DemoApiBridge(QObject):
    """Marshal demo requests onto the Qt GUI thread."""

    _run = Signal(object, object)  # callable, result box

    def __init__(self, parent=None):
        super().__init__(parent)
        self._run.connect(self._on_run, Qt.ConnectionType.BlockingQueuedConnection)

    @Slot(object, object)
    def _on_run(self, fn: object, box: object) -> None:
        out = box if isinstance(box, dict) else {}
        try:
            out["value"] = fn() if callable(fn) else None
        except Exception as exc:
            out["error"] = str(exc)

    def call(self, fn: Callable[[], Any]) -> Any:
        box: Dict[str, Any] = {}
        if threading.current_thread() is threading.main_thread():
            self._on_run(fn, box)
        else:
            self._run.emit(fn, box)
        if "error" in box:
            raise RuntimeError(box["error"])
        return box.get("value")


def start_demo_api(
    handler: Callable[[Dict[str, Any]], Any],
    *,
    host: str = "127.0.0.1",
    port: Optional[int] = None,
    parent: Optional[QObject] = None,
) -> ThreadingHTTPServer:
    """Start a daemon HTTP server; returns the server instance.

    If the preferred port cannot be bound, nearby ports are tried, then an
    ephemeral port (``0``). Callers should read ``server.server_address[1]``
    for the actual listen port.
    """
    ignore_sigint_for_demo()
    bridge = DemoApiBridge(parent=parent)
    preferred = demo_api_port() if port is None else int(port)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args) -> None:  # noqa: A003
            return

        def _send(self, code: int, body: dict) -> None:
            data = json.dumps(body).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:  # noqa: N802
            if self.path.rstrip("/") in ("", "/demo", "/health"):
                self._send(200, {"ok": True, "service": "btfviewer-demo-api"})
                return
            self._send(404, {"ok": False, "error": "not found"})

        def do_POST(self) -> None:  # noqa: N802
            if self.path.rstrip("/") not in ("/demo", "/"):
                self._send(404, {"ok": False, "error": "not found"})
                return
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            try:
                payload = json.loads(raw.decode("utf-8") or "{}")
            except json.JSONDecodeError as exc:
                self._send(400, {"ok": False, "error": f"invalid JSON: {exc}"})
                return
            if not isinstance(payload, dict):
                self._send(400, {"ok": False, "error": "JSON object required"})
                return
            try:
                result = bridge.call(lambda: handler(payload))
                self._send(200, {"ok": True, "result": result})
            except Exception as exc:
                self._send(500, {"ok": False, "error": str(exc)})

    last_exc: Optional[OSError] = None
    candidates: list[int] = [preferred]
    if preferred > 0:
        for delta in range(1, 32):
            candidates.append(preferred + delta)
        candidates.append(0)  # ephemeral
    for listen_port in candidates:
        try:
            server = ThreadingHTTPServer((host, listen_port), Handler)
            break
        except OSError as exc:
            last_exc = exc
            server = None  # type: ignore[assignment]
    else:
        assert last_exc is not None
        raise last_exc

    thread = threading.Thread(
        target=server.serve_forever, name="btf-demo-api", daemon=True,
    )
    thread.start()
    return server
