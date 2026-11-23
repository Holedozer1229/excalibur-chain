"""Read-only EXCAL node observer.

This observer is intentionally loopback-only. It samples the active tip and
its corresponding block record, then emits a hash-addressed observation.
It does not validate consensus, sign attestations, inspect wallets, or submit
transactions. A matching RPC response is an observation, not independent
proof that the node is honest.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import urllib.error
import urllib.request
from typing import Any
from .core import canonical_json

_ALLOWED = {"getblockcount", "getbestblockhash", "getblockbyheight"}


class ObserverError(RuntimeError):
    pass


def _loopback_url(url: str) -> str:
    from urllib.parse import urlsplit
    parsed = urlsplit(url)
    if parsed.scheme != "http" or not parsed.hostname or parsed.port is None:
        raise ObserverError("observer requires an explicit loopback HTTP URL")
    try:
        addr = ipaddress.ip_address(parsed.hostname)
    except ValueError:
        if parsed.hostname != "localhost":
            raise ObserverError("RPC hostname must be localhost or a loopback IP")
    else:
        if not addr.is_loopback:
            raise ObserverError("RPC endpoint must be loopback-only")
    if parsed.username or parsed.password:
        raise ObserverError("credentials in RPC URL are forbidden")
    return url.rstrip("/")


def rpc_call(url: str, method: str, params: list[Any] | None = None, timeout: float = 5.0) -> Any:
    if method not in _ALLOWED:
        raise ObserverError(f"RPC method is not allowed: {method}")
    endpoint = _loopback_url(url)
    body = canonical_json({"jsonrpc": "2.0", "id": "aetherion-observer-v1",
                           "method": method, "params": params or []})
    request = urllib.request.Request(
        endpoint + "/", data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            if response.status != 200:
                raise ObserverError(f"RPC returned HTTP {response.status}")
            payload = json.loads(response.read(2_000_001))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise ObserverError(f"RPC request failed: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("id") != "aetherion-observer-v1":
        raise ObserverError("malformed or mismatched RPC response")
    if payload.get("error") is not None:
        raise ObserverError(f"node RPC error: {payload['error']}")
    if "result" not in payload:
        raise ObserverError("RPC response has no result")
    return payload["result"]


def observe_tip(url: str) -> dict[str, Any]:
    """Cross-check height, best hash, and block-at-height through read-only RPC."""
    height = rpc_call(url, "getblockcount")
    best_hash = rpc_call(url, "getbestblockhash")
    if type(height) is not int or height < 0:
        raise ObserverError("getblockcount returned an invalid height")
    if not isinstance(best_hash, str) or len(best_hash) != 64:
        raise ObserverError("getbestblockhash returned an invalid hash")
    try:
        int(best_hash, 16)
    except ValueError as exc:
        raise ObserverError("best block hash is not hexadecimal") from exc
    block = rpc_call(url, "getblockbyheight", [height])
    if not isinstance(block, dict):
        raise ObserverError("getblockbyheight returned a non-object")
    block_hash = block.get("hash")
    block_height = block.get("height")
    consistent = block_height == height and block_hash == best_hash
    observation = {
        "schema": "aetherion.excal.observation.v1",
        "observer": "aetherion-verifier",
        "checks": {
            "height_is_nonnegative_integer": True,
            "best_hash_is_64_hex": True,
            "tip_block_matches_height_and_hash": consistent,
        },
        "tip": {"height": height, "hash": best_hash},
        "block_record": {
            "height": block_height,
            "hash": block_hash,
            "previous_hash": block.get("prev"),
            "time": block.get("time"),
            "bits": block.get("bits"),
            "transaction_count": len(block.get("tx", [])) if isinstance(block.get("tx"), list) else None,
        },
        "result": "consistent" if consistent else "inconsistent",
        "scope": "single-node RPC consistency check; not a consensus or chain-history proof",
    }
    observation["observation_sha256"] = hashlib.sha256(canonical_json(observation)).hexdigest()
    if not consistent:
        raise ObserverError("node tip RPCs disagree; observation: " + json.dumps(observation, sort_keys=True))
    return observation
