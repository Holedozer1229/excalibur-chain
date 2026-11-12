#!/usr/bin/env python3
"""FORK SNIPER — continuous merged-mining loop for the Excalibur fork.

Forever: build the fork's fresh child for tip+1 (via fork_child.py's own
construction — the script is executed and its JSON parsed, so the child
is byte-for-byte what the campaign's aux commitments use), build a
Bitcoin parent template on the LIVE BTC tip whose coinbase pays Lux's
payout 12jgGaSXJ7jQvrroNZYru13CrjEaZrmDPj with tag "P9-SNIPER" and
carries the fabe-'mm' commitment to the child, grind the parent with
btc_core6 at the CHILD's target, and on a hit submit the assembled
AuxPoW block through the fork node's submitblock RPC (127.0.0.1:9432).

The fork's own miner races at ~1 block/min: if the fork tip moves
mid-round the child is stale, so the round is abandoned and rebuilt.
The sniper never writes chaindata files and never submits non-auxpow
blocks. Unattended by design: every round is wrapped so no exception
kills the loop (30s backoff on errors, ~5s between rounds).
"""
import json
import os
import queue
import re
import struct
import subprocess
import sys
import time

# Portable: everything the sniper needs (genesis_fork, txscript, auxlib,
# fork_child.py) lives next to this script. No /home/hatch paths.
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import genesis_fork as gf
import txscript
from auxlib import rpc, blk_json, parent_header

gf.use_network("fork")

PORT = 9432
# btc_core6f = btc_core6 with the primary-target comparison flipped to
# the fork's PoW convention. The fork's consensus (genesis_fork.py
# validate_block/validate_auxpow) reads the raw sha256d digest as a
# big-endian integer: int.from_bytes(digest, "big") <= target. Stock
# btc_core6 implements Bitcoin's convention (the byte-reversed reading),
# so its hits essentially never satisfy the fork check; btc_core6f is
# the identical engine with the comparison flipped (d[j] vs TARGET_BE[j],
# top word from d[0..3]). The original btc_core6 is untouched — the
# campaign's Bitcoin hunt depends on its convention.
# btc_core6f.exe on Windows (MinGW build, see WINDOWS_MINER.md),
# btc_core6f on POSIX. Absent -> the pure-Python grind below runs.
CORE6 = os.path.join(HERE, "btc_core6f.exe" if os.name == "nt" else "btc_core6f")
FORK_CHILD = os.path.join(HERE, "fork_child.py")
WORKDIR = os.path.join(HERE, "sniper")
PAYOUT_SCRIPT = bytes.fromhex(
    "76a914130a603c7eba4023bcc0ac478257d2c80918521988ac")
ROUND_BUDGET = 3600         # seconds of grinding per round, max (tip-move poll aborts stale rounds; effectively uncapped)
POLL_S = 1                  # core6 poll interval
TIP_POLL_EVERY = 5          # polls between fork-tip re-checks


def log(msg):
    print(f"[sniper] {msg}", flush=True)


def _push(d):
    return bytes([len(d)]) + d


# Local bitcoind is optional: the VM path is the default, override with
# EXCAL_BITCOIN_CLI / EXCAL_BITCOIN_DATADIR, and on a machine without
# bitcoind (e.g. the Windows laptop) btc_tip() falls through to the
# mempool.space / BlockCypher sources below.
BTC_CLI = [os.environ.get("EXCAL_BITCOIN_CLI",
                          "/home/hatch/workspace/bitcoin/bitcoin-28.0/bin/bitcoin-cli"),
           "-datadir=" + os.environ.get("EXCAL_BITCOIN_DATADIR",
                                        "/home/hatch/workspace/bitcoin/data")]


def btc_tip_local():
    """Bitcoin tip from the local bitcoind's header chain: highest-height
    branch from getchaintips (headers-only tip while IBD runs), bits
    from getblockheader. Answers in milliseconds, no internet.
    Verified 2026-11-11: height 975489, hash and bits 386000300 all
    matched mempool.space exactly. Returns (tip_hash_display, height,
    bits_int) — same shapes as the mempool source."""
    if not os.path.exists(BTC_CLI[0]):
        raise FileNotFoundError(f"no local bitcoind at {BTC_CLI[0]}")
    tips = json.loads(subprocess.run(
        BTC_CLI + ["getchaintips"], capture_output=True, text=True,
        timeout=30).stdout)
    best = max(tips, key=lambda t: t["height"])
    hdr = json.loads(subprocess.run(
        BTC_CLI + ["getblockheader", best["hash"]], capture_output=True,
        text=True, timeout=30).stdout)
    return best["hash"], int(hdr["height"]), int(hdr["bits"], 16)


def btc_tip_mempool():
    """Previous source, kept as fallback when local bitcoind is down."""
    tip = subprocess.run(
        ["curl", "-s", "--max-time", "20",
         "https://mempool.space/api/blocks/tip/hash"],
        capture_output=True, text=True).stdout.strip()
    blk = json.loads(subprocess.run(
        ["curl", "-s", "--max-time", "20",
         f"https://mempool.space/api/block/{tip}"],
        capture_output=True, text=True).stdout)
    return tip, blk["height"], blk["bits"]


def btc_tip_blockcypher():
    """Third source, added 2026-11-12: BlockCypher, same
    (tip_hash_display, height, bits_int) shape. Chain endpoint gives
    latest height+hash; block endpoint gives bits (int). Used when
    local bitcoind is reindexing AND mempool.space returns empty."""
    chain = json.loads(subprocess.run(
        ["curl", "-s", "--max-time", "20",
         "https://api.blockcypher.com/v1/btc/main"],
        capture_output=True, text=True).stdout)
    tip = chain["hash"]
    blk = json.loads(subprocess.run(
        ["curl", "-s", "--max-time", "20",
         f"https://api.blockcypher.com/v1/btc/main/blocks/{tip}?limit=0"],
        capture_output=True, text=True).stdout)
    return tip, int(chain["height"]), int(blk["bits"])


def btc_tip():
    try:
        return btc_tip_local()
    except Exception as e:
        log(f"btc_tip: local bitcoind failed ({e!r}); falling back to mempool.space")
    try:
        return btc_tip_mempool()
    except Exception as e:
        log(f"btc_tip: mempool.space failed ({e!r}); falling back to BlockCypher")
        return btc_tip_blockcypher()


def fork_tip():
    count = rpc(PORT, "getblockcount", [])["result"]
    best = rpc(PORT, "getbestblockhash", [])["result"]
    return count, best


def build_child():
    """Run fork_child.py and turn its JSON into (blk, child_hash)."""
    out = subprocess.run([sys.executable, FORK_CHILD],
                         capture_output=True, text=True, timeout=120)
    d = json.loads(out.stdout)
    hdr = bytes.fromhex(d["child_header_hex"])
    assert len(hdr) == 80
    blk = {"version": struct.unpack("<I", hdr[0:4])[0],
           "prev": hdr[4:36],
           "merkle": hdr[36:68],
           "time": struct.unpack("<I", hdr[68:72])[0],
           "bits": struct.unpack("<I", hdr[72:76])[0],
           "nonce": struct.unpack("<I", hdr[76:80])[0],
           "txs": [bytes.fromhex(d["coinbase_hex"])]}
    assert blk["bits"] == d["bits"] and blk["nonce"] == 0
    chash = bytes.fromhex(d["child_hash_internal"])
    assert gf.sha256d(hdr) == chash
    return blk, chash, d


def build_parent(child_hash, btc_tip_hash, btc_height, btc_bits, t):
    """Bitcoin parent template, campaign format, tag P9-SNIPER:
    coinbase pays the P2PKH payout; mm blob = fabe 'mm' + child hash
    (internal) + size 1 (u32 LE) + nonce 0 (u32 LE). Single-tx merkle.
    Returns (coinbase_raw, header_prefix76)."""
    blob = (b"\xfa\xbe" + b"mm" + child_hash
            + (1).to_bytes(4, "little") + (0).to_bytes(4, "little"))
    script = (_push((btc_height + 1).to_bytes(3, "little"))
              + _push(b"P9-SNIPER") + _push(blob))
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


def btc_target_hit(phash, bbits):
    """True if parent header hash phash (raw sha256d bytes) is below the
    Bitcoin target for bits bbits. Bitcoin compares the DISPLAY hash
    (byte-reversed sha256d) as a big-endian integer against the target,
    which is the opposite byte order from the fork's own target check.
    A hit means the parent is a valid Bitcoin block (3.125 BTC)."""
    return int.from_bytes(phash[::-1], "big") <= gf.bits_to_target(bbits)


def save_and_submit_btc_block(phdr, cb, btc_height, rnd):
    """A parent hash below the Bitcoin target IS a valid Bitcoin block
    (single-tx coinbase pays Lux 3.125 BTC). Save it and try to submit
    it to the local bitcoind; the file survives even if submission fails
    (e.g. bitcoind still syncing) so it can be submitted later."""
    block_hex = phdr.hex() + "01" + cb.hex()
    path = os.path.join(WORKDIR, f"btc_block_hit_{btc_height}.hex")
    with open(path, "w") as fh:
        fh.write(block_hex)
    log(f"round {rnd}: *** BTC BLOCK HIT *** valid Bitcoin block "
        f"(height {btc_height}, 3.125 BTC to Lux); saved to {path}")
    if not os.path.exists(BTC_CLI[0]):
        log(f"round {rnd}: no local bitcoind; block file preserved at "
            f"{path} for later submission")
        return
    try:
        sb = subprocess.run(
            BTC_CLI + ["submitblock", block_hex],
            capture_output=True, text=True, timeout=120)
        log(f"round {rnd}: bitcoind submitblock rc={sb.returncode} "
            f"out={sb.stdout.strip()[:200]} err={sb.stderr.strip()[:200]}")
    except Exception as e:
        log(f"round {rnd}: bitcoind submit failed {e!r}; block file "
            f"preserved at {path}")


def _py_grind_range(prefix76, target, n_start, n_end, result_q, stop_ev):
    """Worker process: pure-Python grind of nonces in [n_start, n_end).

    Same header/nonce logic as excalibur._grind_range, but the job is a
    pre-built 76-byte parent header prefix + the fork target (fork PoW
    convention: int.from_bytes(digest, "big") <= target). Top-level
    with picklable args, so it runs under fork AND spawn (Windows).
    """
    import hashlib
    nonce = n_start
    hashes = 0
    while nonce < n_end:
        dh = hashlib.sha256(hashlib.sha256(
            prefix76 + struct.pack("<I", nonce)).digest()).digest()
        hashes += 1
        if int.from_bytes(dh, "big") <= target:
            result_q.put((nonce, hashes))
            return
        nonce += 1
        if (hashes & 0xFFF) == 0 and stop_ev.is_set():
            return
    result_q.put(None)  # range exhausted (practically never)


def _py_grind(prefix76, target, rnd, best, workers=2):
    """Pure-Python fallback grind when the btc_core6f binary is absent
    (Windows before the MinGW build, or a fresh checkout). Same return
    contract as the core6 path: (nonce, outcome, dt). Polls the fork
    tip every 5 polls and aborts stale rounds; ROUND_BUDGET caps the
    round. The fork target is only ~23 bits, so this genuinely finds
    blocks (~8M hashes expected) — it is the miner, not a placeholder.
    """
    import multiprocessing as mp
    ctx = mp.get_context()  # default: fork on POSIX, spawn on Windows
    result_q = ctx.Queue()
    stop_ev = ctx.Event()
    span = 0x100000000 // workers
    procs = []
    started = time.time()
    for i in range(workers):
        n_start = i * span
        n_end = (i + 1) * span if i + 1 < workers else 0x100000000
        p = ctx.Process(target=_py_grind_range,
                        args=(prefix76, target, n_start, n_end,
                              result_q, stop_ev))
        p.start()
        procs.append(p)
    nonce = None
    outcome = None
    polls = 0
    try:
        while True:
            if time.time() - started > ROUND_BUDGET:
                outcome = "budget-exhausted"
                break
            try:
                item = result_q.get(timeout=1)
            except queue.Empty:
                polls += 1
                if polls % TIP_POLL_EVERY == 0:
                    try:
                        _c, best_now = fork_tip()
                    except Exception:
                        best_now = best
                    if best_now != best:
                        outcome = "fork-tip-moved"
                        break
                if all(not p.is_alive() for p in procs):
                    outcome = "py-exhausted"
                    break
                continue
            if item is None:
                continue  # a worker exhausted its range; keep waiting
            nonce, _hashes = item
            outcome = "hit"
            break
    finally:
        stop_ev.set()
        for p in procs:
            p.join(timeout=3)
            if p.is_alive():
                p.terminate()
    return nonce, outcome, time.time() - started


def one_round(rnd):
    count, best = fork_tip()
    blk, chash, cj = build_child()
    height = count + 1
    if cj["height"] != height or blk["prev"].hex() != best:
        log(f"round {rnd}: child built on stale file tip "
            f"(child h={cj['height']} prev={blk['prev'].hex()[:16]}.. "
            f"vs RPC tip h={count} best={best[:16]}..); skipping")
        return
    target = gf.bits_to_target(blk["bits"])
    btip, bheight, bbits = btc_tip()
    t0 = int(time.time())
    cb, pfx = build_parent(chash, btip, bheight, bbits, t0)
    merkle_internal = gf.txid(cb)
    log(f"round {rnd}: child {height} {chash.hex()[:16]}.. "
        f"bits {blk['bits']:08x} (expect ~2^{256 - target.bit_length()} "
        f"hashes) on BTC tip {bheight} {btip[:16]}..; grinding 2 threads")
    if os.path.exists(CORE6):
        outp = os.path.join(WORKDIR, f"round_{rnd}.out")
        logp = os.path.join(WORKDIR, f"round_{rnd}.log")
        ckpt = os.path.join(WORKDIR, f"ckpt_{rnd}.txt")
        cmd = [CORE6, bytes.fromhex(btip)[::-1].hex(), merkle_internal.hex(),
               str(t0), "%08x" % bbits, "%064x" % target, "1", "2",
               "--rot", "2731", "--checkpoint", ckpt]
        out = open(outp, "w")
        err = open(logp, "w")
        proc = subprocess.Popen(cmd, stdout=out, stderr=err)
        started = time.time()
        nonce = None
        outcome = None
        polls = 0
        while True:
            rc = proc.poll()
            if rc is not None:
                out.flush()
                txt = open(outp).read()
                m = re.search(r"FOUND (\d+) (\d+) ([0-9a-f]{64})", txt)
                if m:
                    nonce = int(m.group(2))
                    outcome = "hit"
                else:
                    outcome = f"core-exit-{rc}"
                break
            if time.time() - started > ROUND_BUDGET:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except Exception:
                    proc.kill()
                outcome = "budget-exhausted"
                break
            polls += 1
            if polls % TIP_POLL_EVERY == 0:
                try:
                    _c, best_now = fork_tip()
                except Exception:
                    best_now = best
                if best_now != best:
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except Exception:
                        proc.kill()
                    outcome = "fork-tip-moved"
                    break
            time.sleep(POLL_S)
        out.close()
        err.close()
        dt = time.time() - started
    else:
        # No compiled grind core (Windows before the MinGW build):
        # pure-Python fallback, same (nonce, outcome, dt) contract.
        log(f"round {rnd}: btc_core6f binary absent; pure-Python grind")
        nonce, outcome, dt = _py_grind(pfx, target, rnd, best)
    if outcome != "hit":
        log(f"round {rnd}: {outcome} after {dt:.0f}s; no submission")
        return
    phdr = parent_header(pfx, nonce)
    phash = gf.sha256d(phdr)
    if int.from_bytes(phash, "big") > target:
        log(f"round {rnd}: core6 nonce {nonce} fails local target "
            f"re-check; NOT submitting")
        return
    btc_hit = btc_target_hit(phash, bbits)
    log(f"round {rnd}: HIT parent nonce {nonce} after {dt:.0f}s, "
        f"parent hash {phash.hex()[:24]}..; submitting child {height} "
        f"(BTC-target check: {'HIT' if btc_hit else 'miss'})")
    r = rpc(PORT, "submitblock", [blk_json(blk, (phdr, cb, [], 0))])
    res = r.get("result")
    if res:
        log(f"round {rnd}: VERDICT {json.dumps(res)} "
            f"(child {height} {chash.hex()})")
    else:
        log(f"round {rnd}: VERDICT rejected: {r.get('error')} "
            f"(child {height} {chash.hex()[:16]}..)")
    if btc_hit:
        save_and_submit_btc_block(phdr, cb, bheight + 1, rnd)


def main():
    os.makedirs(WORKDIR, exist_ok=True)
    log("FORK SNIPER live — continuous merged-mining loop "
        "(tag P9-SNIPER, 2 grind threads, budget "
        f"{ROUND_BUDGET}s/round, dual-target BTC check on)")
    rnd = 0
    while True:
        rnd += 1
        try:
            one_round(rnd)
        except Exception as e:
            log(f"round {rnd}: ERROR {e!r}; backing off 30s")
            time.sleep(30)
            continue
        time.sleep(1)


if __name__ == "__main__":
    main()
