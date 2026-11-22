"""node_client.py — JSON-RPC client for the Excalibur node.

Calls the running node via HTTP JSON-RPC (same protocol as excaliburRpc.ts)
so the adapter never imports consensus code directly.
"""
from __future__ import annotations

import json
import socket
import time
from typing import Any


class NodeClientError(Exception):
    """Raised when the node RPC call fails."""


class NodeClient:
    """Lightweight JSON-RPC client for the Excalibur node.

    Usage:
        client = NodeClient("http://127.0.0.1:9432")
        height = client.call("getblockcount")
        peers = client.call("getpeerinfo")
    """

    def __init__(self, url: str = "http://127.0.0.1:9432", timeout: int = 30) -> None:
        self.url = url.rstrip("/")
        self.timeout = timeout
        self._id = 0

    def call(self, method: str, params: list[Any] | None = None) -> Any:
        """Make a JSON-RPC call and return the result."""
        self._id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self._id,
            "method": method,
            "params": params or [],
        }
        try:
            import urllib.request

            req = urllib.request.Request(
                self.url,
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode())
        except socket.timeout as e:
            raise NodeClientError(f"RPC {method} timed out after {self.timeout}s") from e
        except urllib.error.URLError as e:
            raise NodeClientError(f"RPC {method} failed: {e.reason}") from e
        except json.JSONDecodeError as e:
            raise NodeClientError(f"RPC {method} returned invalid JSON") from e

        if "error" in data and data["error"] is not None:
            err = data["error"]
            msg = err if isinstance(err, str) else err.get("message", "unknown error")
            raise NodeClientError(f"RPC {method}: {msg}")
        return data.get("result")

    # Convenience methods
    def get_block_count(self) -> int:
        """Return the current chain height."""
        return self.call("getblockcount")

    def get_best_block_hash(self) -> str:
        """Return the hash of the current tip."""
        return self.call("getbestblockhash")

    def get_peer_info(self) -> list[dict]:
        """Return connected peer information."""
        return self.call("getpeerinfo")

    def get_mempool_info(self) -> dict:
        """Return mempool statistics."""
        return self.call("getmempoolinfo")

    def get_balance(self) -> dict:
        """Return wallet balance."""
        return self.call("getbalance")

    def estimate_smart_fee(self, target: int = 2) -> dict:
        """Estimate fee rate for confirmation within target blocks."""
        return self.call("estimatesmartfee", [target])
