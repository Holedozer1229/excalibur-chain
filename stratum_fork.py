#!/usr/bin/env python3
"""
Stratum shim for the Excalibur fork — lets any standard SHA-256d stratum
miner (the GPU rig) mine the fork node, which itself speaks only RPC.

  miner --stratum--> this shim --JSON-RPC--> fork node (127.0.0.1:9432)

Templates are coinbase-only (the fork mempool has no raw-tx RPC; it is
empty in practice) and pay the node wallet's PKH lock via
make_coinbase_v2 — the same payout path as the built-in CPU miners.

Difficulty follows the GRACE-PATH STRATEGY (genealogy-verified against
all 25,556 historical blocks):
  * window boundary (height % 60 == 0): bits = required_bits, exact;
  * any other height: inherit the parent's bits verbatim (consensus-
    valid via the grace path; freezes cost inside the window).
Timestamps: t = max(parent_time + 1, now), the wall-clock anchor rule.

Stratum conventions follow the canonical Bitcoin stratum protocol:
prevhash is sent word-swapped (each 4-byte group byte-reversed) from
the node's stored hash bytes; coinbase split at an 8-byte extranonce
slot (extranonce1 = 4 B per connection, extranonce2 = 4 B miner-side),
carried as a consensus-safe extra push after the coinbase height push.
If a miner family disagrees on the prevhash swap, flip
STRATUM_PREVHASH_WORDSWAP=0 and reconnect — the shim's reconstruction
(and the node's acceptance) is the arbiter.

Config (env): STRATUM_HOST (default 127.0.0.1 — set to the Tailscale/LAN
address when the rig connects from another machine), STRATUM_PORT
(9434), STRATUM_SHARE_MULT (share target = block target * M, default 1
= every valid share is a block; raise for the GPU rig, e.g. M such that
share_work ~ rig_hashrate * 2s), FORK_RPC_PORT (9432), TAG (coinbase
tag, default "Excalibur").
"""
import asyncio, http.client, json, os, struct, sys, time

sys.path.insert(0, "/home/hatch/workspace")
import genesis_fork as gf
from genesis_fork import (sha256d, ser_header, bits_to_target,
                          target_to_bits, merkle_root, txid, subsidy)
from txscript import make_coinbase_v2

gf.use_network("fork")
P = gf.network()
MIN_BITS = P["min_bits"]; WINDOW = P.get("daa_window", 60)
SPACING = P.get("daa_spacing", 60); DAA_ACT = P.get("daa_activation", 0)

RPC_PORT = int(os.environ.get("FORK_RPC_PORT", "9432"))
HOST = os.environ.get("STRATUM_HOST", "127.0.0.1")
PORT = int(os.environ.get("STRATUM_PORT", "9434"))
SHARE_MULT = int(os.environ.get("STRATUM_SHARE_MULT", "1"))
TAG = os.environ.get("TAG", "Excalibur").encode()
WORDSWAP = os.environ.get("STRATUM_PREVHASH_WORDSWAP", "1") == "1"
DIFF1 = 0x00000000FFFF0000000000000000000000000000000000000000000000000000


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def rpc(method, params=None):
    c = http.client.HTTPConnection("127.0.0.1", RPC_PORT, timeout=15)
    c.request("POST", "/", json.dumps(
        {"method": method, "params": params or [], "id": 1}))
    r = json.loads(c.getresponse().read()); c.close()
    if r.get("error"):
        raise RuntimeError(r["error"])
    return r["result"]


def required_bits(height, ctx):
    """ctx: {height: (time, bits)} — mirrors genesis_fork.required_bits
    for the fork's DAA parameters (verified over the full chain)."""
    if height < WINDOW or height < DAA_ACT:
        return MIN_BITS
    first = ctx.get(height - WINDOW); last = ctx.get(height - 1)
    if first is None or last is None:
        return last[1] if last else MIN_BITS
    span = last[0] - first[0]
    if span <= 0: span = 1
    target_span = WINDOW * SPACING
    span = max(target_span // 4, min(target_span * 4, span))
    nt = bits_to_target(last[1]) * span // target_span
    return target_to_bits(min(nt, bits_to_target(MIN_BITS)))


def strategy_bits(height, ctx, parent_bits):
    if height % WINDOW == 0:
        return required_bits(height, ctx)
    return parent_bits


def wordswap(b):
    if not WORDSWAP: return b
    return b"".join(b[i:i + 4][::-1] for i in range(0, len(b), 4))


class Chain:
    """Incrementally tracked tip context from the node RPC."""

    def __init__(self):
        self.tip_hash = None; self.ctx = {}; self.tip = None
        self.wallet_pub = None

    def refresh(self):
        """Returns True if the tip changed."""
        h = rpc("getbestblockhash")
        if h == self.tip_hash:
            return False
        blk = rpc("getblock", [h])
        # walk back to fill the context window (heights tip-60 .. tip)
        ctx = {blk["height"]: (blk["time"], int(blk["bits"], 16))}
        cur = blk
        while cur["height"] > blk["height"] - WINDOW and cur["height"] > 0:
            cur = rpc("getblock", [cur["prev"]])
            ctx[cur["height"]] = (cur["time"], int(cur["bits"], 16))
        self.ctx = ctx; self.tip = blk; self.tip_hash = h
        if self.wallet_pub is None:
            self.wallet_pub = bytes.fromhex(rpc("getnewaddress"))
        return True


class Job:
    def __init__(self, chain):
        tip = chain.tip; height = tip["height"] + 1
        self.height = height
        self.parent_time = tip["time"]
        self.prev_hex = chain.tip_hash
        self.prev = bytes.fromhex(self.prev_hex)
        self.bits = strategy_bits(height, chain.ctx,
                                  int(tip["bits"], 16))
        self.time = max(tip["time"] + 1, int(time.time()))
        self.target = bits_to_target(self.bits)
        self.share_target = min(self.target * SHARE_MULT,
                                (1 << 256) - 1)
        cb = make_coinbase_v2(height, self.bits, TAG, 0,
                              chain.wallet_pub,
                              extra_pushes=[b"\x00" * 8])
        marker = b"\x08" + b"\x00" * 8
        off = cb.rfind(marker)
        assert off > 0
        self.coinb1 = cb[:off + 1]
        self.coinb2 = cb[off + 1 + 8:]
        assert self.coinb1 + b"\x00" * 8 + self.coinb2 == cb
        self.job_id = f"{height:x}-{self.time:x}"

    def notify_params(self):
        return [self.job_id, wordswap(self.prev).hex(),
                self.coinb1.hex(), self.coinb2.hex(), [],
                "00000001", f"{self.bits:08x}", f"{self.time:08x}", True]

    def rebuild(self, en1, en2, ntime, nonce):
        cb = self.coinb1 + en1 + en2 + self.coinb2
        root = merkle_root([txid(cb)])
        hdr = ser_header(1, self.prev, root, ntime, self.bits, nonce)
        return cb, root, hdr


class Shim:
    def __init__(self):
        self.chain = Chain(); self.job = None
        self.jobs = {}   # job_id -> Job, recent window for late submits
        self.clients = set(); self.en_counter = 0

    def register_job(self, job):
        self.jobs[job.job_id] = job
        while len(self.jobs) > 128:
            self.jobs.pop(next(iter(self.jobs)))

    async def broadcast_job(self):
        if self.job is None: return
        note = {"id": None, "method": "mining.notify",
                "params": self.job.notify_params()}
        diff = {"id": None, "method": "mining.set_difficulty",
                "params": [DIFF1 / self.job.share_target]}
        for w in list(self.clients):
            try:
                w.write((json.dumps(diff) + "\n").encode())
                w.write((json.dumps(note) + "\n").encode())
            except Exception:
                pass

    async def watch_tip(self):
        while True:
            try:
                if await asyncio.get_event_loop().run_in_executor(
                        None, self.chain.refresh):
                    self.job = Job(self.chain)
                    self.register_job(self.job)
                    log(f"new job {self.job.job_id} height "
                        f"{self.job.height} bits {self.job.bits:#010x} "
                        f"work/block {(1 << 256) // (self.job.target + 1)}")
                    await self.broadcast_job()
            except Exception as e:
                log("tip watch error:", e)
            await asyncio.sleep(1.0)

    async def handle(self, reader, writer):
        self.en_counter += 1
        en1 = struct.pack("<I", self.en_counter)
        self.clients.add(writer)
        subscribed = authorized = False
        log("miner connected, extranonce1", en1.hex())
        try:
            while True:
                line = await reader.readline()
                if not line: break
                try: msg = json.loads(line)
                except Exception: continue
                mid, method = msg.get("id"), msg.get("method")
                params = msg.get("params") or []

                def reply(result, error=None):
                    writer.write((json.dumps(
                        {"id": mid, "result": result,
                         "error": error}) + "\n").encode())

                if method == "mining.subscribe":
                    subscribed = True
                    reply([[["mining.set_difficulty", "1"],
                            ["mining.notify", "1"]], en1.hex(), 4])
                elif method == "mining.authorize":
                    authorized = True
                    reply(True)
                    if self.job is not None:
                        writer.write((json.dumps(
                            {"id": None, "method": "mining.set_difficulty",
                             "params": [DIFF1 / self.job.share_target]}
                        ) + "\n").encode())
                        writer.write((json.dumps(
                            {"id": None, "method": "mining.notify",
                             "params": self.job.notify_params()}
                        ) + "\n").encode())
                elif method == "mining.extranonce.subscribe":
                    reply([])
                elif method == "mining.submit":
                    if not (subscribed and authorized) or self.job is None:
                        reply(False, [24, "not subscribed"]); continue
                    job = self.jobs.get(params[1]) if len(params) >= 2 \
                        else None
                    if len(params) < 5 or job is None:
                        reply(False, [21, "job not found"]); continue
                    try:
                        en2 = bytes.fromhex(params[2])
                        ntime = int(params[3], 16)
                        nonce = int(params[4], 16)
                    except Exception:
                        reply(False, [20, "malformed submit"]); continue
                    if len(en2) != 4:
                        reply(False, [20, "bad extranonce2"]); continue
                    if not (job.parent_time < ntime
                            <= int(time.time()) + 7200):
                        reply(False, [20, "ntime out of bounds"]); continue
                    cb, root, hdr = job.rebuild(en1, en2, ntime, nonce)
                    hv = int.from_bytes(sha256d(hdr), "big")
                    if hv > job.share_target:
                        reply(False, [23, "low difficulty share"]); continue
                    if hv > job.target:
                        reply(True)  # valid share, not a block
                        continue
                    blk = {"version": 1, "prev": job.prev_hex,
                           "merkle": root.hex(), "time": ntime,
                           "bits": job.bits, "nonce": nonce,
                           "txs": [cb.hex()]}
                    try:
                        res = await asyncio.get_event_loop(
                        ).run_in_executor(None,
                                          lambda: rpc("submitblock", [blk]))
                        log(f"BLOCK ACCEPTED height {res['height']} "
                            f"{res['status']} hash {res['hash']}")
                        reply(True)
                    except Exception as e:
                        log("submitblock rejected:", e)
                        reply(False, [20, f"node rejected: {e}"])
                else:
                    reply(None, [20, "unknown method"])
        except Exception as e:
            log("client error:", e)
        finally:
            self.clients.discard(writer)
            try: writer.close()
            except Exception: pass
            log("miner disconnected")


async def main():
    shim = Shim()
    await asyncio.get_event_loop().run_in_executor(None, shim.chain.refresh)
    shim.job = Job(shim.chain)
    shim.register_job(shim.job)
    log(f"tip {shim.chain.tip['height']} bits "
        f"{shim.chain.tip['bits']}; first job {shim.job.job_id} "
        f"bits {shim.job.bits:#010x}")
    srv = await asyncio.start_server(shim.handle, HOST, PORT)
    log(f"stratum shim listening on {HOST}:{PORT} "
        f"(share_mult {SHARE_MULT}, wordswap {WORDSWAP})")
    asyncio.create_task(shim.watch_tip())
    async with srv:
        await srv.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
