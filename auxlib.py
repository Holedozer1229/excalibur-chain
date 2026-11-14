"""Shared helpers for the AuxPoW scratch tests and the live landing.

Child construction mirrors fork_child.py (coinbase v2 paying the fork
wallet PKH, tag "Excalibur", DAA bits from the trailing window) with one
correction: fork_child.py reverses the chain record's stored hash when
filling the header prev field, but chain records store hashes in
internal order already (verified empirically: sha256d(header).hex() ==
record["hash"], and record[n].prev == record[n-1].hash as stored), so
the prev field must be the stored bytes verbatim — as ChainState and
the miner use them.
"""
import hashlib
import http.client
import json
import os
import struct
import sys
import time
from multiprocessing import Process, Queue

# Portable: genesis_fork / txscript live next to this script.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import genesis_fork as gf
import txscript

gf.use_network("fork")

PAYOUT_SCRIPT = bytes.fromhex(
    "76a914130a603c7eba4023bcc0ac478257d2c80918521988ac")


_PUB = None
def _load_pub():
    """Fork wallet pubkey, loaded lazily: importing auxlib must not
    crash on a machine without the VM wallet file (e.g. Windows — the
    sniper only needs rpc/blk_json/parent_header from this module).
    Wallet path: wallet_fork.json next to this script, or
    EXCAL_WALLET_FILE."""
    global _PUB
    if _PUB is None:
        path = os.environ.get("EXCAL_WALLET_FILE") or os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "wallet_fork.json")
        _PUB = bytes.fromhex(json.load(open(path))["pub"])
    return _PUB


def rpc(port, method, params, timeout=120):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    c.request("POST", "/", json.dumps(
        {"method": method, "params": params, "id": 1}))
    r = json.loads(c.getresponse().read())
    c.close()
    return r


def load_records(chain_path):
    with open(chain_path) as f:
        return [json.loads(l) for l in f.read().strip().split("\n")]


def build_child(records, nonce=0, bits_override=None, prev_rec=None):
    """Child block for prev_rec.height+1 (default: tip+1), fork_child
    construction with the record's internal-order prev verbatim."""
    base = prev_rec if prev_rec is not None else records[-1]
    height = base["height"] + 1
    ctx = {r["height"]: {"time": r["time"], "bits": r["bits"]}
           for r in records[-70:]}
    t = max(base["time"] + 1, int(time.time()))
    bits = bits_override if bits_override is not None else \
        gf.required_bits(height, ctx, t)
    cb = txscript.make_coinbase_v2(height, bits, b"Excalibur", 0, _load_pub())
    merkle = gf.txid(cb)
    prev = bytes.fromhex(base["hash"])
    header = gf.ser_header(1, prev, merkle, t, bits, nonce)
    blk = {"version": 1, "prev": prev, "merkle": merkle, "time": t,
           "bits": bits, "nonce": nonce, "txs": [cb]}
    return blk, header, gf.sha256d(header)


def _push(d):
    return bytes([len(d)]) + d


def build_parent(child_hash, btc_tip_hash, btc_height, btc_bits, t):
    """Parent (Bitcoin) template in the campaign's format: coinbase pays
    the P2PKH payout, tag P9-FULLTARGET, mm blob = fabe 'mm' + child
    hash (internal) + size 1 (u32 LE) + nonce 0 (u32 LE). Returns
    (coinbase_raw, header_prefix76)."""
    blob = (b"\xfa\xbe" + b"mm" + child_hash
            + (1).to_bytes(4, "little") + (0).to_bytes(4, "little"))
    script = (_push((btc_height + 1).to_bytes(3, "little"))
              + _push(b"P9-FULLTARGET") + _push(blob))
    cb = txscript.ser_tx({
        "version": 1,
        "vin": [{"prev": b"\x00" * 32, "idx": 0xFFFFFFFF,
                 "script": script, "seq": 0xFFFFFFFF}],
        "vout": [{"value": 312500000, "script": PAYOUT_SCRIPT}],
        "locktime": 0})
    merkle = gf.txid(cb)
    prefix = (struct.pack("<I", 1) + bytes.fromhex(btc_tip_hash)[::-1]
              + merkle + struct.pack("<II", t, btc_bits))
    assert len(prefix) == 76
    return cb, prefix


def _scan(prefix76, target, lo, hi, q, stop):
    n = lo
    while n < hi:
        h = hashlib.sha256(hashlib.sha256(
            prefix76 + struct.pack("<I", n)).digest()).digest()
        if int.from_bytes(h, "big") <= target:
            q.put(n)
            stop.set()
            return
        n += 1
        if (n & 0xFFF) == 0 and stop.is_set():
            return
    q.put(None)


def grind(prefix76, target, procs=2):
    """First nonce with sha256d(prefix76+nonce) meeting target under the
    fork's integer convention (int.from_bytes(digest, 'big') <= target —
    the same expression as validate_block's own PoW check). Workers exit
    as soon as any of them finds a hit (shared stop event), so the call
    returns at find time rather than at the end of a scan wave."""
    from multiprocessing import Event
    q = Queue()
    stop = Event()
    chunk = 1 << 22
    base = 0
    while base < (1 << 32):
        ps = []
        for i in range(procs):
            lo = base + i * chunk
            hi = min(lo + chunk, 1 << 32)
            p = Process(target=_scan,
                        args=(prefix76, target, lo, hi, q, stop))
            p.start()
            ps.append(p)
        remaining = procs
        found = None
        while remaining:
            g = q.get()
            remaining -= 1
            if g is not None:
                found = g
                break
        stop.set()
        for p in ps:
            p.join()
        if found is not None:
            return found
        base += procs * chunk
    return None


def blk_json(blk, auxpow=None):
    d = {"version": blk["version"], "prev": blk["prev"].hex(),
         "merkle": blk["merkle"].hex(), "time": blk["time"],
         "bits": blk["bits"], "nonce": blk["nonce"],
         "txs": [t.hex() for t in blk["txs"]]}
    if auxpow is not None:
        phdr, pcb, branch, idx = auxpow
        d["auxpow"] = {"parent_header": phdr.hex(),
                       "parent_coinbase": pcb.hex(),
                       "coinbase_branch": [s.hex() for s in branch],
                       "coinbase_index": idx}
    return d


def parent_header(prefix76, nonce):
    return prefix76 + struct.pack("<I", nonce)
