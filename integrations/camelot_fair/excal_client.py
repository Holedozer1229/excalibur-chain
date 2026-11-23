"""Read-only EXCAL RPC adapter for the Camelot Fair game backend.

The game must never receive node RPC credentials or wallet secrets. This
adapter deliberately exposes only chain status and public-lock UTXO reads.
It does not prove address ownership, payment finality, or reward eligibility.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

SWORDS_PER_EXCAL = 100_000_000
_ALLOWED_METHODS = frozenset({
    "getblockcount", "getbestblockhash", "getutxos", "getblockbyheight",
})
_LOCK_RE = re.compile(r"^00[0-9a-fA-F]{40}$")


class ExcalRpcError(RuntimeError):
    """Raised when the EXCAL node RPC cannot safely answer a request."""


@dataclass(frozen=True)
class ChainStatus:
    height: int
    best_block_hash: str


class ExcalClient:
    """Minimal read-only client for a locally reachable EXCAL node.

    HTTP is accepted only for loopback addresses. For remote deployments,
    place this client beside the node and expose a separately authenticated,
    TLS-protected game API; do not point this client at a public RPC endpoint.
    """

    def __init__(self, rpc_url: str = "http://127.0.0.1:9432", timeout: float = 5.0):
        parsed = urlsplit(rpc_url)
        if (parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
                or parsed.username is not None or parsed.password is not None):
            raise ValueError("EXCAL RPC must be local HTTP loopback only, without URL credentials")
        if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
            raise ValueError("RPC URL must not contain path, query, or fragment")
        if timeout <= 0 or timeout > 30:
            raise ValueError("timeout must be in (0, 30] seconds")
        self.rpc_url = rpc_url.rstrip("/")
        self.timeout = timeout

    def _call(self, method: str, params: list[Any] | None = None) -> Any:
        if method not in _ALLOWED_METHODS:
            raise ValueError(f"RPC method is not allowed: {method}")
        body = json.dumps({
            "jsonrpc": "2.0", "method": method, "params": params or [],
            "id": "camelot-fair",
        }).encode("utf-8")
        request = urllib.request.Request(
            self.rpc_url + "/", data=body,
            headers={"Content-Type": "application/json"}, method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                if response.status != 200:
                    raise ExcalRpcError(f"EXCAL RPC returned HTTP {response.status}")
                payload = json.loads(response.read(2_000_001))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise ExcalRpcError(f"EXCAL RPC unavailable or invalid: {exc}") from exc
        if not isinstance(payload, dict) or payload.get("id") != "camelot-fair":
            raise ExcalRpcError("Malformed EXCAL RPC response")
        if payload.get("error") is not None:
            raise ExcalRpcError(str(payload["error"]))
        if "result" not in payload:
            raise ExcalRpcError("EXCAL RPC response has no result")
        return payload["result"]

    def chain_status(self) -> ChainStatus:
        height = self._call("getblockcount")
        block_hash = self._call("getbestblockhash")
        if not isinstance(height, int) or height < 0:
            raise ExcalRpcError("Invalid EXCAL chain height")
        if not isinstance(block_hash, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", block_hash):
            raise ExcalRpcError("Invalid EXCAL best-block hash")
        return ChainStatus(height=height, best_block_hash=block_hash.lower())

    def get_utxos(self, pkh_lock_hex: str) -> list[dict[str, Any]]:
        """Return node-indexed UTXOs for a public 21-byte PKH lock.

        The returned mature field means coinbase maturity only. It is not a
        payment-confirmation or reorg-finality indicator.
        """
        if not isinstance(pkh_lock_hex, str) or not _LOCK_RE.fullmatch(pkh_lock_hex):
            raise ValueError("Expected EXCAL PKH lock: 00 followed by 40 hex characters")
        result = self._call("getutxos", [pkh_lock_hex.lower()])
        if not isinstance(result, list):
            raise ExcalRpcError("Invalid getutxos response")
        checked: list[dict[str, Any]] = []
        for item in result:
            if not isinstance(item, dict):
                raise ExcalRpcError("Invalid UTXO entry")
            txid, vout, value = item.get("txid"), item.get("vout"), item.get("value")
            if not isinstance(txid, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", txid):
                raise ExcalRpcError("Invalid UTXO txid")
            if not isinstance(vout, int) or vout < 0:
                raise ExcalRpcError("Invalid UTXO vout")
            if not isinstance(value, int) or value < 0:
                raise ExcalRpcError("Invalid UTXO sword value")
            if not isinstance(item.get("mature"), bool):
                raise ExcalRpcError("Invalid UTXO maturity flag")
            checked.append({
                "txid": txid.lower(), "vout": vout, "value_swords": value,
                "coinbase_mature": item["mature"],
                "coinbase": bool(item.get("coinbase", False)),
            })
        return checked

    def utxo_total_swords(self, pkh_lock_hex: str) -> int:
        """Total UTXO value in swords; not a payment-finality claim."""
        return sum(item["value_swords"] for item in self.get_utxos(pkh_lock_hex))
