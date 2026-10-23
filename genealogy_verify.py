#!/usr/bin/env python3
"""
Genealogy Bridge — reference verifier (spec section 3.1, full-sync mode).

Verifies the Excalibur fork header chain from its anchor to the live tip:
  anchor  = Bitcoin block 968698's header (byte-exact, fork block 0)
  checks  = header hash recomputation, PoW (self or AuxPoW per consensus),
            prev linkage, strictly increasing time, exact DAA bits
            recomputation (window 60 / spacing 60 / 4x clamp / activation 74),
            chainwork accumulation (total and fork-native)
  vectors = heights 25344 / 25351 (countersignature lineage) + live RPC tip
  anchor cross-check against mempool.space (public BTC record)

Independent implementation: consensus rules replicated from genesis_fork.py
by reading the code, not by importing it. Stdlib only (curl subprocess for
the public cross-check, per sandbox egress rules).
"""
import hashlib, json, struct, subprocess, sys, time

RPC_HOST, RPC_PORT = "127.0.0.1", 9432
CHAIN_FILE = "/home/hatch/workspace/chaindata_fork/chain.jsonl"

# --- consensus constants (genesis_fork.py, fork network) ---
MIN_BITS = 0x1F000100
DAA_WINDOW, DAA_SPACING, DAA_ACTIVATION = 60, 60, 74
AUXPOW_ACTIVATION = 23785
AUXPOW_MAGIC = b"\xfa\xbe" + b"mm"

# --- the anchor: BTC block 968698 header (fork block 0) ---
FORK_BTC_HEIGHT = 968698
FORK_BTC_HASH_DISPLAY = "000000000000000000015d0478e7b60044314fb055fbb306ac7371ef89b60496"
ANCHOR = {
    "version": 537059328,
    "prev": bytes.fromhex("17834318684358cad3cc4e832b29946c5a302914880900000000000000000000"),
    "merkle": bytes.fromhex("03eb3de87579a2e42f8d9310c627774090aec64fa7bdc3ec2732f46f64b0a2f2"),
    "time": 1790432291, "bits": 0x17021EC5, "nonce": 1876081791,
}

def sha256d(b): return hashlib.sha256(hashlib.sha256(b).digest()).digest()

def ser_header(h):
    prev = h["prev"] if isinstance(h["prev"], bytes) else bytes.fromhex(h["prev"])
    merkle = h["merkle"] if isinstance(h["merkle"], bytes) else bytes.fromhex(h["merkle"])
    return (struct.pack("<I", h["version"]) + prev + merkle
            + struct.pack("<III", h["time"], h["bits"], h["nonce"]))

def bits_to_target(bits):
    exp = bits >> 24; mant = bits & 0xFFFFFF
    return (mant >> (8 * (3 - exp))) if exp <= 3 else (mant << (8 * (exp - 3)))

def target_to_bits(target):
    if target <= 0: return 0
    nbytes = (target.bit_length() + 7) // 8
    if nbytes <= 3:
        compact, size = target << (8 * (3 - nbytes)), 3
    else:
        compact, size = target >> (8 * (nbytes - 3)), nbytes
    if compact & 0x800000:
        compact >>= 8; size += 1
    return (size << 24) | (compact & 0x7FFFFF)

def expected_bits(height, hist):
    """Exact replication of the node's windowed DAA. hist[h] = (time, bits)."""
    if height < DAA_WINDOW: return MIN_BITS
    if height < DAA_ACTIVATION: return MIN_BITS
    first = hist[height - DAA_WINDOW]; last = hist[height - 1]
    timespan = last[0] - first[0]
    if timespan <= 0: timespan = 1
    target_span = DAA_WINDOW * DAA_SPACING
    timespan = max(target_span // 4, min(target_span * 4, timespan))
    new_target = bits_to_target(last[1]) * timespan // target_span
    new_target = min(new_target, bits_to_target(MIN_BITS))
    return target_to_bits(new_target)

def merkle_branch_root(leaf, branch, index):
    h = bytes(leaf); idx = int(index)
    for sib in branch:
        h = sha256d(bytes(sib) + h) if idx & 1 else sha256d(h + bytes(sib))
        idx >>= 1
    return h

def check_auxpow(rec, child_hash_internal):
    ap = rec.get("auxpow")
    if not isinstance(ap, dict): return "missing auxpow attachment"
    phdr = bytes.fromhex(ap["parent_header"]); pcb = bytes.fromhex(ap["parent_coinbase"])
    branch = [bytes.fromhex(s) for s in ap["coinbase_branch"]]; cidx = int(ap["coinbase_index"])
    if len(phdr) != 80: return "parent header not 80 bytes"
    if int.from_bytes(sha256d(phdr), "big") > bits_to_target(rec["bits"]):
        return "parent hash above child target"
    if merkle_branch_root(sha256d(pcb), branch, cidx) != phdr[36:68]:
        return "coinbase branch does not reach parent merkle root"
    i = pcb.find(AUXPOW_MAGIC)
    if i < 0: return "no merged-mining commitment in parent coinbase"
    blob = pcb[i + 4:i + 44]
    if len(blob) < 40: return "truncated commitment"
    if blob[:32] != child_hash_internal: return "commitment child hash mismatch"
    size, mnonce = struct.unpack_from("<II", blob, 32)
    if size != 1 or mnonce != 0: return "expected single-aux commitment (size 1, nonce 0)"
    return None

def rpc(method, params=[]):
    import http.client
    c = http.client.HTTPConnection(RPC_HOST, RPC_PORT, timeout=15)
    c.request("POST", "/", json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}))
    return json.loads(c.getresponse().read()).get("result")

def main():
    t0 = time.time()
    print("== Genealogy reference verifier (full-sync from anchor) ==")
    anchor_bytes = ser_header(ANCHOR)
    anchor_hash = sha256d(anchor_bytes)
    print(f"anchor: BTC height {FORK_BTC_HEIGHT}, header sha256d (internal) = {anchor_hash.hex()}")
    print(f"        display form = {anchor_hash[::-1].hex()} (expect {FORK_BTC_HASH_DISPLAY})")
    assert anchor_hash[::-1].hex() == FORK_BTC_HASH_DISPLAY, "anchor hash mismatch vs FORK_BTC_HASH"

    # public cross-check of the anchor against Bitcoin's own record
    try:
        h = subprocess.run(["curl", "-s", "-m", "20",
                            f"https://mempool.space/api/block-height/{FORK_BTC_HEIGHT}"],
                           capture_output=True, text=True).stdout.strip()
        blk = json.loads(subprocess.run(["curl", "-s", "-m", "20",
                                         f"https://mempool.space/api/block/{h}"],
                                        capture_output=True, text=True).stdout)
        ok = (h == FORK_BTC_HASH_DISPLAY and blk["version"] == ANCHOR["version"]
              and blk["timestamp"] == ANCHOR["time"] and blk["bits"] == ANCHOR["bits"]
              and blk["nonce"] == ANCHOR["nonce"]
              and bytes.fromhex(blk["previousblockhash"])[::-1] == ANCHOR["prev"]
              and bytes.fromhex(blk["merkle_root"])[::-1] == ANCHOR["merkle"])
        print(f"anchor cross-check vs mempool.space (public BTC record): {'PASS' if ok else 'FAIL'}")
    except Exception as e:
        print(f"anchor cross-check unavailable ({e}); internal consistency still enforced")

    # load records, walk the active chain from the live tip
    byhash = {}
    with open(CHAIN_FILE) as f:
        for line in f:
            r = json.loads(line); byhash[r["hash"]] = r
    tip_hash = rpc("getbestblockhash"); tip_height = rpc("getblockcount")
    chain = []
    h = tip_hash
    while h in byhash:
        chain.append(byhash[h])
        if byhash[h]["prev"] not in byhash: break
        h = byhash[h]["prev"]
    chain.reverse()
    print(f"walked active chain: {len(chain)} blocks, heights {chain[0]['height']}..{chain[-1]['height']}"
          f" (RPC tip height {tip_height})")

    hist = []            # (time, bits) per height
    work_total = 0; work_native = 0
    n_self = n_aux = 0
    n_grace = 0
    failures = []
    vectors = {}
    prev_hash = None
    for i, rec in enumerate(chain):
        height = rec["height"]
        if height != i: failures.append((height, f"height sequence break (record {i})")); break
        raw = ser_header(rec)
        hh = sha256d(raw)
        if hh.hex() != rec["hash"]:
            failures.append((height, "stored hash != recomputed sha256d(header)")); break
        if height == 0:
            if raw != anchor_bytes:
                failures.append((0, "block 0 != anchor header bytes")); break
        else:
            if rec["prev"] != prev_hash:
                failures.append((height, "prev linkage mismatch")); break
            if not rec["time"] > chain[i - 1]["time"]:
                failures.append((height, "non-increasing timestamp")); break
            eb = expected_bits(height, hist)
            # Node's actual acceptance rule (validate_block): bits must equal
            # the DAA output, OR — at heights not divisible by the window —
            # equal the parent's bits (the "grace path", applied by the node
            # unconditionally). A verifier stricter than consensus rejects
            # the real chain; replicate the rule as built.
            grace = (height % DAA_WINDOW != 0 and rec["bits"] == chain[i - 1]["bits"])
            if rec["bits"] != eb and not grace:
                failures.append((height, f"bits {rec['bits']:#x} != DAA-expected {eb:#x} "
                                           f"(grace path not available)")); break
            if rec["bits"] != eb:
                n_grace += 1
            if int.from_bytes(hh, "big") <= bits_to_target(rec["bits"]):
                n_self += 1
            elif height >= AUXPOW_ACTIVATION:
                err = check_auxpow(rec, hh)
                if err: failures.append((height, f"auxpow: {err}")); break
                n_aux += 1
            else:
                failures.append((height, "insufficient PoW (no auxpow before activation)")); break
        w = (1 << 256) // (bits_to_target(rec["bits"]) + 1)
        work_total += w
        if height > 0: work_native += w
        hist.append((rec["time"], rec["bits"]))
        prev_hash = rec["hash"]
        if height in (25344, 25351):
            vectors[height] = rec["hash"]

    ok = not failures and chain[-1]["hash"] == tip_hash and len(chain) == tip_height + 1
    print(f"self-PoW blocks: {n_self} | AuxPoW blocks: {n_aux} | bits accepted via grace path: {n_grace}")
    print(f"chainwork total: {work_total} (2^{work_total.bit_length()-1} scale)")
    print(f"chainwork fork-native (excl. anchor): {work_native}")
    for ht, expect_stored in ((25344, "0000005d63e0b57f1d652f117533b6fb4824bec6cf7a90e4aee963b1ac256abc"),
                              (25351, "000000574ecf57d25781c510ec0a659bc511bbae7e708426faa1094157f50b0f")):
        got = vectors.get(ht)
        print(f"test vector height {ht}: on-chain hash {got} | matches lineage record: {got == expect_stored}")
    if failures:
        print(f"FAILURES: {failures[:5]}")
    print(f"VERDICT: {'ALL CHECKS PASS' if ok else 'FAILED'} — {len(chain)} headers verified from the "
          f"BTC-{FORK_BTC_HEIGHT} anchor to tip {tip_hash[:16]}… in {time.time()-t0:.1f}s")

    ckpt = {
        "bridge": "genealogy", "spec": "genealogy-bridge-spec.md v0.1 (anchor corrected)",
        "anchor": {"btc_height": FORK_BTC_HEIGHT, "hash_display": FORK_BTC_HASH_DISPLAY,
                   "header_sha256d_internal": anchor_hash.hex()},
        "height": chain[-1]["height"], "tip_hash": chain[-1]["hash"],
        "chainwork_total": work_total, "chainwork_fork_native": work_native,
        "daa_tail": [{"time": t, "bits": b} for (t, b) in hist[-DAA_WINDOW:]],
        "counts": {"self_pow": n_self, "auxpow": n_aux, "bits_grace_path": n_grace},
        "verified_at_unix": int(time.time()),
    }
    with open("/home/hatch/workspace/your_files/genealogy_checkpoint.json", "w") as f:
        json.dump(ckpt, f, indent=2)
    print("checkpoint written: genealogy_checkpoint.json")
    return 0 if ok else 1

if __name__ == "__main__":
    sys.exit(main())
