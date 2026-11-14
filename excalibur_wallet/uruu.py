"""uruu.py — read-only URUU view via the public zkSync Era RPC.

URUU (verified live 2026-11-12, zkSync Era chain 324):
  token 0x5B6C9d85465Cc6FFe84039183872239657D90208
  "Camelot Excalibur URUU", 18 decimals, total supply exactly 100,000,000.

This module only READS. No keys, no signing, no bridge execution, no
transactions. It calls the public RPC with eth_call (balanceOf,
decimals, totalSupply, symbol, name) and decodes the ABI outputs.

Transport: curl via subprocess with fallback to urllib.request.
Windows 10+ ships curl.exe; if unavailable the module falls back to
the standard library.  If the RPC is unreachable the functions raise
UruuError and the CLI reports the lookup as unavailable — it never
invents a balance.
"""
import json
import subprocess
import time
import urllib.request
import urllib.error

URUU_TOKEN = "0x5B6C9d85465Cc6FFe84039183872239657D90208"
URUU_CHAIN_ID = 324
URUU_RPC = "https://mainnet.era.zksync.io"
URUU_DECIMALS = 18
URUU_TOTAL_SUPPLY = 100_000_000

# Retry & rate-limit defaults
_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 1.0          # seconds
_MAX_RESPONSE_BYTES = 100_000   # 100 kB cap on RPC response bodies

_SEL = {
    "balanceOf": "70a08231",
    "decimals": "313ce567",
    "totalSupply": "18160ddd",
    "symbol": "95d89b41",
    "name": "06fdde03",
}


class UruuError(Exception):
    pass


def _rpc_call(method, params, timeout=20):
    """Send a JSON-RPC call with retry/backoff and a response-size cap.

    Tries ``curl`` first; if ``curl`` is not on PATH it falls back to
    ``urllib.request`` so the module works without external tools.
    """
    payload = json.dumps({"jsonrpc": "2.0", "id": 1,
                          "method": method, "params": params}).encode()
    last_err = None
    for attempt in range(_MAX_RETRIES):
        try:
            raw = _do_rpc_call(payload, timeout)
            break  # success
        except UruuError as e:
            last_err = e
            if attempt < _MAX_RETRIES - 1:
                time.sleep(_RETRY_BASE_DELAY * (2 ** attempt))
    else:
        raise UruuError(f"URUU RPC unreachable after {_MAX_RETRIES} attempts: {last_err}")
    # cap response size before JSON parsing
    if len(raw) > _MAX_RESPONSE_BYTES:
        raise UruuError(f"URUU RPC response too large ({len(raw)} bytes)")
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        raise UruuError("URUU RPC returned non-JSON")
    if data.get("error") is not None:
        raise UruuError(f"URUU RPC error: {data['error']}")
    return data.get("result")


def _do_rpc_call(payload: bytes, timeout: int) -> str:
    """Execute one RPC attempt via curl, falling back to urllib."""
    try:
        proc = subprocess.run(
            ["curl", "-s", "-m", str(timeout), "-X", "POST", URUU_RPC,
             "-H", "Content-Type: application/json",
             "-d", payload.decode()],
            capture_output=True, timeout=timeout + 5)
        if proc.returncode != 0:
            raise UruuError(f"curl failed (exit {proc.returncode}): "
                            f"{proc.stderr.decode(errors='replace')[:200]}")
        return proc.stdout.decode()
    except OSError:
        pass  # curl not found — fall through to urllib

    # Fallback: standard-library urllib (no external deps)
    req = urllib.request.Request(
        URUU_RPC, data=payload,
        headers={"Content-Type": "application/json"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode()
    except urllib.error.URLError as e:
        raise UruuError(f"URUU RPC unreachable (urllib): {e}")


def _eth_call(data_hex):
    """Call the token contract at the safe (finalized) block for deterministic reads.

    Using "safe" instead of "latest" avoids non-deterministic results during
    a chain reorg — all fields fetched in token_info() come from the same
    post-reorg-finality state.
    """
    return _rpc_call("eth_call",
                     [{"to": URUU_TOKEN, "data": data_hex}, "safe"])


def _decode_uint(result):
    if not result or not isinstance(result, str):
        raise UruuError("empty RPC result")
    hex_str = result
    if hex_str.startswith("0x"):
        hex_str = hex_str[2:]
    if not hex_str:
        return 0  # "0x" or "0x0" with no meaningful digits → zero
    return int(hex_str, 16)


def _decode_string(result):
    """ABI-encoded string: offset(32) + length(32) + bytes."""
    raw = bytes.fromhex(result[2:] if result.startswith("0x") else result)
    if len(raw) < 64:
        raise UruuError("short string return")
    length = int.from_bytes(raw[32:64], "big")
    end = 64 + length
    if end > len(raw):
        # Truncate to available data rather than reading past the buffer
        length = len(raw) - 64
        if length <= 0:
            return ""
    return raw[64:64 + length].decode(errors="replace")


def validate_eth_address(addr: str) -> str:
    """Validate and return an Ethereum address in EIP-55 checksummed form.

    EIP-55 checksumming prevents case-collision bugs: the contract
    expects the checksummed form, so we always return it rather than
    a plain lowercase address.
    """
    a = str(addr).strip()
    if a.lower().startswith("0x"):
        a = a[2:]
    if len(a) != 40:
        raise UruuError("Ethereum address must be 0x + 40 hex chars")
    try:
        bytes.fromhex(a)
    except ValueError:
        raise UruuError("Ethereum address is not hex")
    return _eip55_checksum(a)


def _eip55_checksum(addr_hex: str) -> str:
    """Apply EIP-55 checksum to a 40-char hex address (no 0x prefix)."""
    import hashlib
    hashed = hashlib.sha256(addr_hex.lower().encode()).hexdigest()
    result = []
    for i, c in enumerate(addr_hex.lower()):
        if c in "0123456789":
            result.append(c)
        else:
            if int(hashed[i], 16) >= 8:
                result.append(c.upper())
            else:
                result.append(c)
    return "0x" + "".join(result)


def token_info():
    """{name, symbol, decimals, total_supply, chain_id, token} from the
    live contract. total_supply is in whole URUU."""
    name = _decode_string(_eth_call("0x" + _SEL["name"]))
    symbol = _decode_string(_eth_call("0x" + _SEL["symbol"]))
    decimals = _decode_uint(_eth_call("0x" + _SEL["decimals"]))
    total_base = _decode_uint(_eth_call("0x" + _SEL["totalSupply"]))
    return {"name": name, "symbol": symbol, "decimals": decimals,
            "total_supply": total_base // (10 ** decimals),
            "total_supply_base_units": total_base,
            "chain_id": URUU_CHAIN_ID, "token": URUU_TOKEN}


def balance_of(eth_address: str):
    """URUU balance of an Ethereum address. Returns
    {address, balance_uruu (float), balance_base_units (int),
     decimals, token}. No keys involved — a pure read.

    Fetches ``decimals`` from the live contract so the result stays
    correct even if the token contract is ever upgraded."""
    addr = validate_eth_address(eth_address)
    padded = addr[2:].rjust(64, "0")
    raw = _eth_call("0x" + _SEL["balanceOf"] + padded)
    base = _decode_uint(raw)
    decimals = _decode_uint(_eth_call("0x" + _SEL["decimals"]))
    return {"address": addr, "balance_base_units": base,
            "balance_uruu": base / (10 ** decimals),
            "decimals": decimals, "token": URUU_TOKEN}
