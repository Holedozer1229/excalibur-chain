"""status_api.py — HTTP status endpoint for the public node.

Provides a lightweight GET /api/status endpoint that returns chain status
without exposing the full JSON-RPC interface. Used by excalNodeStatus.ts.
"""
from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any


class StatusAPI:
    """HTTP status endpoint for public node monitoring.

    Exposes GET /api/status returning:
    {
        "network": "excalibur",
        "online": true,
        "height": 12345,
        "tip_hash": "abc...",
        "peer_count": 5,
        "sync_status": "synced",
        "updated_at": "2024-01-01T00:00:00Z"
    }

    Usage:
        status = StatusAPI(node_client, port=9434)
        status.start()
        # ... later
        status.stop()
    """

    def __init__(
        self,
        node_client: Any,
        port: int = 9434,
        host: str = "127.0.0.1",
    ) -> None:
        self.node_client = node_client
        self.port = port
        self.host = host
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None

    def _build_status(self) -> dict[str, Any]:
        """Build the status response from the node client."""
        try:
            height = self.node_client.get_block_count()
            tip_hash = self.node_client.get_best_block_hash()
            peers = self.node_client.get_peer_info()
            return {
                "network": "excalibur",
                "online": True,
                "height": height,
                "tip_hash": tip_hash,
                "peer_count": len(peers),
                "sync_status": "synced",
                "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
        except Exception:
            return {
                "network": "excalibur",
                "online": False,
                "height": 0,
                "tip_hash": "",
                "peer_count": 0,
                "sync_status": "disconnected",
                "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }

    def start(self) -> None:
        """Start the status API in a background thread."""
        status_api = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):  # type: ignore[no-untyped-def]
                pass

            def do_GET(self):  # type: ignore[no-untyped-def]
                if self.path == "/api/status" or self.path == "/status":
                    body = json.dumps(status_api._build_status()).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                else:
                    self.send_response(404)
                    self.end_headers()

        self._server = HTTPServer((self.host, self.port), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the status API."""
        if self._server:
            self._server.shutdown()
            self._server = None
            self._thread = None
