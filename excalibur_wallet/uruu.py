"""uruu.py — read-only URUU view via the public zkSync Era RPC.

URUU (verified live 2026-11-12, zkSync Era chain 324):
  token 0x5B6C9d85465Cc6FFe84039183872239657D90208
  "Camelot Excalibur URUU", 18 decimals, total supply exactly 100,000,000.

This module only READS. No keys, no signing, no bridge execution, no
transactions. It calls the public RPC with eth_call (balanceOf,
decimals, totalSupply, symbol, name) and decodes the ABI outputs.

Transport: curl via subprocess. The sandbox egress proxy refuses
Python urllib for public HTTPS but curl works; Windows 10+ ships
curl.exe, so this stays Windows-compatible. If the RPC is unreachable
the functions raise UruuError and the CLI reports the lookup as
unavailable — it never invents a balance.
"""
import json
import subprocess

URUU_TOKEN = "0x5B6C9d85465Cc6FFe84039183872239657D90208"
URUU_CHAIN_ID = 324
URUU_RPC = "https://mainnet.era.zksync.io"
URUU_DECIMALS = 18
URUU_TOTAL_SUPPLY = 100_000_000

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
    payload = json.dumps({"jsonrpc": "2.0", "id": 1,
                          "method": method, "params": params})
    try:
        proc = subprocess.run(
            ["curl", "-s", "-m", str(timeout), "-X", "POST", URUU_RPC,
             "-H", "Content-Type: application/json",
             "-d", payload],
            capture_output=True, timeout=timeout + 5)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise UruuError(f"URUU RPC unreachable: {e}")
    if proc.returncode != 0:
        raise UruuError(f"curl failed (exit {proc.returncode}): "
                        f"{proc.stderr.decode(errors='replace')[:200]}")
    try:
        data = json.loads(proc.stdout.decode())
    except ValueError:
        raise UruuError("URUU RPC returned non-JSON")
    if data.get("error") is not None:
        raise UruuError(f"URUU RPC error: {data['error']}")
    return data.get("result")


def _eth_call(data_hex):
    return _rpc_call("eth_call",
                     [{"to": URUU_TOKEN, "data": data_hex}, "latest"])


def _decode_uint(result):
    if not result or not isinstance(result, str):
        raise UruuError("empty RPC result")
    return int(result, 16)


def _decode_string(result):
    """ABI-encoded string: offset(32) + length(32) + bytes."""
    raw = bytes.fromhex(result[2:] if result.startswith("0x") else result)
    if len(raw) < 64:
        raise UruuError("short string return")
    length = int.from_bytes(raw[32:64], "big")
    return raw[64:64 + length].decode(errors="replace")


def validate_eth_address(addr: str) -> str:
    a = str(addr).strip()
    if a.lower().startswith("0x"):
        a = a[2:]
    if len(a) != 40:
        raise UruuError("Ethereum address must be 0x + 40 hex chars")
    try:
        bytes.fromhex(a)
    except ValueError:
        raise UruuError("Ethereum address is not hex")
    return "0x" + a.lower()


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
     decimals, token}. No keys involved — a pure read."""
    addr = validate_eth_address(eth_address)
    padded = addr[2:].rjust(64, "0")
    raw = _eth_call("0x" + _SEL["balanceOf"] + padded)
    base = _decode_uint(raw)
    return {"address": addr, "balance_base_units": base,
            "balance_uruu": base / (10 ** URUU_DECIMALS),
            "decimals": URUU_DECIMALS, "token": URUU_TOKEN}
