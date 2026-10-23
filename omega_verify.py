#!/usr/bin/env python3
"""Phase Omega chain verifier.

Walks the canonical Excalibur fork chain from the node RPC tip and,
for each block, checks whether its coinbase carries an Omega blob —
a Trifold signature over the parent block's 80-byte header — and
verifies it against the epoch root in omega/epochs.json.

Usage: python3 omega_verify.py [n]   (check the top n blocks, default 10)
Anyone can run this: the chain file, this script, trifold_lockbox.py
and the published epoch roots are all public.
"""
import http.client
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import genesis_fork as gf
import omega_sign as om

gf.use_network("fork")
D = os.path.dirname(os.path.abspath(__file__))


def rpc(method, params=None):
    c = http.client.HTTPConnection("127.0.0.1", 9432, timeout=15)
    c.request("POST", "/", json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or []}))
    r = json.loads(c.getresponse().read())
    c.close()
    return r["result"]


def _hx(x):
    return bytes.fromhex(x) if isinstance(x, str) else bytes(x)


def _int(x):
    return int(x) if not isinstance(x, str) else int(x, 16)


def header_of(rec):
    return gf.ser_header(_int(rec["version"]), _hx(rec["prev"]),
                         _hx(rec["merkle"]), _int(rec["time"]),
                         _int(rec["bits"]), _int(rec["nonce"]))


def coinbase_pushes(raw_cb):
    off = 4 + 1 + 32 + 4
    slen, off = gf._read_varint(raw_cb, off)
    return gf._parse_pushes(raw_cb[off:off + slen])


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    records = {}
    with open(os.path.join(D, "chaindata_fork", "chain.jsonl")) as f:
        for line in f:
            line = line.strip()
            if line:
                r = json.loads(line)
                records[r["hash"]] = r
    tip_hash = rpc("getbestblockhash")
    chain = []
    h = tip_hash
    while len(chain) < n and h in records:
        chain.append(records[h])
        h = records[h]["prev"]
    signed = 0
    for rec in chain:
        cb = bytes.fromhex(rec["txs"][0])
        pushes = coinbase_pushes(cb)
        blob = next((p for p in pushes if p.startswith(om.MAGIC)), None)
        kind = "auxpow" if rec.get("auxpow") else "pow"
        if blob is None:
            print(f"h{rec['height']} [{kind}] no Omega push")
            continue
        epoch, sig = om.parse_blob(blob)
        root = om.root_for_epoch(epoch)
        parent = records.get(rec["prev"])
        ok = parent is not None and om.verify_blob(
            root, header_of(parent), blob)
        print(f"h{rec['height']} [{kind}] OMEGA epoch {epoch} "
              f"leaf {sig['index']} — signature "
              f"{'VERIFIES' if ok else 'FAILED'}")
        signed += bool(ok)
    print(f"{signed}/{len(chain)} canonical blocks Omega-verified")


if __name__ == "__main__":
    main()
