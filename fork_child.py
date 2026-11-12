#!/usr/bin/env python3
"""Build the Excalibur fork's pending child block for merged mining.

Reads the fork tip from chaindata_fork/chain.jsonl, constructs the next
block exactly as the fork miner would (coinbase v2 paying the fork
wallet PKH, tag "Excalibur", nonce 0 — PoW to be supplied by a parent),
and prints JSON: {height, bits, target, child_hash_internal,
child_header_hex, coinbase_hex}. Used by the BTC full-target campaign
to embed the fabe-mm aux commitment in its parent candidates.
"""
import json, os, struct, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import genesis_fork as gf
from txscript import make_coinbase_v2
from node_rpc import load_wallet_key

gf.use_network("fork")
D = os.path.dirname(os.path.abspath(__file__))

def _read_tail(path, n=70):
    """Return the last n+1 parseable JSONL records of the chain file
    WITHOUT loading the whole file. The file is ~1.1GB; a full read
    costs ~60s per child build and is the sniper's bottleneck (rounds
    were ~60s build + ~10s grind). Each record is ~23KB, so an 8MB
    trailing window holds ~350 records — far more than needed. A torn
    tail line (node appending mid-read) is skipped, same as the old
    code's stale-tip check would have caught."""
    with open(path, "rb") as f:
        f.seek(0, os.SEEK_END)
        size = f.tell()
        window = 8 * 1024 * 1024
        start = max(0, size - window)
        f.seek(start)
        data = f.read().decode("utf-8", "replace")
    raw = data.strip().split("\n")
    if start > 0 and raw:
        raw = raw[1:]  # first line may be a fragment cut by the window
    recs = []
    for ln in reversed(raw):
        try:
            r = json.loads(ln)
        except Exception:
            continue
        if isinstance(r, dict) and "height" in r:
            recs.append(r)
        if len(recs) >= n + 1:
            break
    recs.reverse()
    return recs

_tail = _read_tail(os.path.join(D, "chaindata_fork", "chain.jsonl"), 70)
tip = _tail[-1]
height = tip["height"] + 1
ctx = {}
for r in _tail[-70:]:
    ctx[r["height"]] = {"time": r["time"], "bits": r["bits"]}
t = max(tip["time"] + 1, int(time.time()))
bits = gf.required_bits(height, ctx, t)
_priv, pub = load_wallet_key(os.path.join(D, "wallet_fork.json"))
# Phase Omega (2026-10-23): countersign the parent (tip) header with a
# Trifold signature; the blob rides as the coinbase's last push. Any
# failure leaves the child unsigned — production never depends on it.
# EXCAL_NO_OMEGA=1 skips signing entirely: a second machine sharing
# the epoch key would burn the same one-time leaf twice (the VM sniper
# owns the live leaves; a laptop child is valid unsigned).
_omega = None
try:
    import omega_sign as _om
    def _hx(x): return bytes.fromhex(x) if isinstance(x, str) else bytes(x)
    def _int(x): return int(x) if not isinstance(x, str) else int(x, 16)
    _phdr = gf.ser_header(_int(tip["version"]), _hx(tip["prev"]),
                           _hx(tip["merkle"]), _int(tip["time"]),
                           _int(tip["bits"]), _int(tip["nonce"]))
    if gf.sha256d(_phdr).hex() == tip["hash"] and not os.environ.get("EXCAL_NO_OMEGA"):
        _omega = _om.omega_blob(_phdr)
except Exception:
    _omega = None
cb = None
try:
    # Sponsor delivery (2026-10-23): if the land registry has an entry
    # for THIS height, the child pays the buyer's lock and seals their
    # tag instead of the wallet coinbase. The sniper is the chain's
    # pace-setter (~45-53 of every 60 blocks), so a sponsored child
    # built here rides the fastest producer we have instead of racing
    # it. Shape mirrors the shim's sponsor_coinbase exactly (consensus
    # lineage pins pushes[0] = LE32(bits)). Any error -> normal path.
    _reg = json.load(open(os.path.join(D, "stratum_shim", "sponsors.json")))
    _ent = _reg.get(str(height))
    if _ent:
        from txscript import lock_pkh as _lock_pkh
        _raw = _ent["lock"].strip().lower()
        if _raw.startswith("0x"):
            _raw = _raw[2:]
        _lock = (bytes.fromhex(_raw) if len(_raw) == 42
                 else _lock_pkh(bytes.fromhex(_raw)))
        _stag = _ent["tag"].encode()
        _script = (gf.push(struct.pack("<I", bits)) + gf.push(b"Excalibur")
                   + gf.push(struct.pack("<I", height)) + gf.push(_stag)
                   + gf.push(b"\x00" * 8))
        if _omega:
            _script += gf.push(_omega)
        _tx = struct.pack("<I", 1) + b"\x01"
        _tx += bytes(32) + struct.pack("<I", 0xFFFFFFFF)
        _tx += gf.ser_varint(len(_script)) + _script
        _tx += struct.pack("<I", 0xFFFFFFFF) + b"\x01"
        _tx += struct.pack("<Q", gf.subsidy(height))
        _tx += gf.ser_varint(len(_lock)) + _lock
        _tx += struct.pack("<I", 0)
        cb = _tx
except Exception:
    cb = None
if cb is None:
    cb = make_coinbase_v2(height, bits, b"Excalibur", 0, pub,
                          extra_pushes=[_omega] if _omega else None)
merkle = gf.txid(cb)
prev_internal = bytes.fromhex(tip["hash"])  # chain records store hashes in internal order already (verified: sha256d(header).hex() == record hash, and the 2026-10-21 live AuxPoW landing was accepted with prev verbatim); reversing here corrupts prev — fixed 2026-10-21
header = gf.ser_header(1, prev_internal, merkle, t, bits, 0)
child_hash = gf.sha256d(header)
print(json.dumps({
    "height": height, "bits": bits,
    "target": "%064x" % gf.bits_to_target(bits),
    "child_hash_internal": child_hash.hex(),
    "child_hash_display": child_hash[::-1].hex(),
    "child_header_hex": header.hex(),
    "coinbase_hex": cb.hex(),
}))
