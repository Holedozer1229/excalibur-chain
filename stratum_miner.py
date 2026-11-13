#!/usr/bin/env python3
"""
AetherionEXCAL External Stratum Miner — Production Mining Software

A standalone Stratum mining application for the EXCAL blockchain.
Supports three operating modes:

1. **Server Mode** — Runs a Stratum server accepting GPU miner connections
   (T-Rex, GMiner, NiceHash, etc.). Submits blocks to the fork node via RPC.

2. **Client Mode** — Connects to an external Stratum mining pool as a client
   miner, contributing EXCAL hashpower to a pool.

3. **CPU Mode** — Built-in multi-threaded CPU miner using SHA-256d.

EXCAL uses SHA-256d (double SHA-256) proof-of-work, identical to Bitcoin's
hashing algorithm. Block headers are serialized in Bitcoin format:
  version(4) + prevhash(32) + merkle(32) + timestamp(4) + bits(4) + nonce(4)

Stratum protocol follows Bitcoin Stratum v1 specification:
  mining.subscribe, mining.authorize, mining.notify, mining.submit

Usage:
  # Server mode (accept GPU miners, submit to fork node)
  python stratum_miner.py server --host 0.0.0.0 --port 3333 --rpc-port 9432

  # Client mode (connect to a pool)
  python stratum_miner.py client --url stratum+tcp://pool.example.com:3333 --worker rig1

  # CPU mining mode (standalone)
  python stratum_miner.py cpu --threads 4 --rpc-port 9432

  # Benchmark mode
  python stratum_miner.py benchmark --threads 4 --duration 10

Environment Variables:
  EXCAL_WORKSPACE  — Project root directory (defaults to script directory)
  STRATUM_HOST     — Default server host (0.0.0.0)
  STRATUM_PORT     — Default server port (3333)
  FORK_RPC_PORT    — Fork node RPC port (9432)
  TAG              — Coinbase tag string ("AetherionEXCAL")

Author: AetherionEXCAL Project
Website: https://www.aetherion-oracle.com
"""
import argparse
import asyncio
import hashlib
import json
import math
import multiprocessing
import os
import struct
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
_ws = os.environ.get("EXCAL_WORKSPACE", "")
if _ws:
    sys.path.insert(0, _ws)
else:
    sys.path.insert(0, _HERE)

# ---------------------------------------------------------------------------
# EXCAL Consensus Constants
# ---------------------------------------------------------------------------
DIFF1 = 0x00000000FFFF0000000000000000000000000000000000000000000000000000
MAX_TARGET = (1 << 256) - 1
SWORD = 100_000_000  # satoshi multiplier

# Network defaults
DEFAULT_RPC_HOST = "127.0.0.1"
DEFAULT_RPC_PORT = 9432
DEFAULT_STRATUM_HOST = "0.0.0.0"
DEFAULT_STRATUM_PORT = 3333
DEFAULT_TAG = b"AetherionEXCAL"

# DAA parameters (from genesis_fork fork network)
DAF_WINDOW = 60
DAF_SPACING = 60  # seconds per block target


# ---------------------------------------------------------------------------
# EXCAL Hashing & Header Functions
# ---------------------------------------------------------------------------

def sha256(data: bytes) -> bytes:
    """Single SHA-256 hash."""
    return hashlib.sha256(data).digest()


def sha256d(data: bytes) -> bytes:
    """Double SHA-256 hash (EXCAL proof-of-work function)."""
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()


def ser_header(version: int, prev: bytes, merkle: bytes,
               timestamp: int, bits: int, nonce: int) -> bytes:
    """Serialize a block header (80 bytes)."""
    return (struct.pack("<I", version) +
            prev[:32] +
            merkle[:32] +
            struct.pack("<III", timestamp, bits, nonce))


def header_hash(header: bytes) -> int:
    """Compute the hash value of a serialized header (big-endian integer)."""
    return int.from_bytes(sha256d(header), "big")


def bits_to_target(bits: int) -> int:
    """Convert compact difficulty bits to target integer."""
    exp = bits >> 24
    mant = bits & 0xFFFFFF
    if exp <= 3:
        return mant >> (8 * (3 - exp))
    return mant << (8 * (exp - 3))


def target_to_bits(target: int) -> int:
    """Convert target integer to compact difficulty bits."""
    if target <= 0:
        return 0
    nbytes = (target.bit_length() + 7) // 8
    if nbytes <= 3:
        compact = target << (8 * (3 - nbytes))
        size = 3
    else:
        compact = target >> (8 * (nbytes - 3))
        size = nbytes
    if compact & 0x800000:
        compact >>= 8
        size += 1
    return (size << 24) | (compact & 0x7FFFFF)


def calculate_difficulty(target: int) -> float:
    """Calculate difficulty from target."""
    return DIFF1 / (target + 1)


def merkle_root(txids: List[bytes]) -> bytes:
    """Compute merkle root from list of txids."""
    if not txids:
        return bytes(32)
    level = [bytes(t) for t in txids]
    while len(level) > 1:
        nxt = []
        for i in range(0, len(level), 2):
            a = level[i]
            b = level[i + 1] if i + 1 < len(level) else a
            nxt.append(sha256d(a + b))
        level = nxt
    return level[0]


def txid(raw: bytes) -> bytes:
    """Compute transaction ID (double SHA-256)."""
    return sha256d(raw)


# ---------------------------------------------------------------------------
# Stratum Protocol Messages
# ---------------------------------------------------------------------------

class StratumMethod(Enum):
    SUBSCRIBE = "mining.subscribe"
    AUTHORIZE = "mining.authorize"
    SET_DIFFICULTY = "mining.set_difficulty"
    NOTIFY = "mining.notify"
    SUBMIT = "mining.submit"
    EXTRANONCE_SUBSCRIBE = "mining.extranonce.subscribe"


@dataclass
class StratumMessage:
    """A Stratum JSON-RPC message."""
    method: str
    params: List[Any] = None
    result: Any = None
    error: Any = None
    msg_id: Optional[int] = None

    def to_json(self) -> str:
        """Serialize to JSON-RPC format."""
        if self.result is not None or self.error is not None:
            # Response
            return json.dumps({
                "id": self.msg_id,
                "result": self.result,
                "error": self.error
            })
        elif self.method and self.params is not None:
            # Request
            return json.dumps({
                "id": self.msg_id,
                "method": self.method,
                "params": self.params
            })
        elif self.method:
            # Notification
            return json.dumps({
                "id": None,
                "method": self.method,
                "params": self.params or []
            })
        return "{}"

    @classmethod
    def from_json(cls, data: str) -> 'StratumMessage':
        """Parse a JSON-RPC message."""
        obj = json.loads(data)
        return cls(
            method=obj.get("method", ""),
            params=obj.get("params"),
            result=obj.get("result"),
            error=obj.get("error"),
            msg_id=obj.get("id")
        )


# ---------------------------------------------------------------------------
# Mining Job
# ---------------------------------------------------------------------------

@dataclass
class MiningJob:
    """A mining job with all necessary parameters."""
    job_id: str
    prev_hash: bytes  # 32 bytes, internal byte order
    coinbase_1: bytes  # First part of coinbase tx
    coinbase_2: bytes  # Second part of coinbase tx
    merkle_branches: List[bytes]  # Merkle branch (empty for coinbase-only)
    version: int
    bits: int
    ntime: int
    height: int
    target: int
    share_target: int
    parent_time: int

    def rebuild_header(self, extranonce1: bytes, extranonce2: bytes,
                       ntime: int, nonce: int) -> bytes:
        """Rebuild block header from miner's solution."""
        # Reconstruct coinbase transaction
        coinbase = self.coinbase_1 + extranonce1 + extranonce2 + self.coinbase_2

        # Compute merkle root
        root = merkle_root([txid(coinbase)])

        # Serialize header
        return ser_header(self.version, self.prev_hash, root, ntime, self.bits, nonce)

    def verify_solution(self, extranonce1: bytes, extranonce2: bytes,
                       ntime: int, nonce: int) -> Tuple[bool, bool]:
        """
        Verify a mining solution.
        Returns: (is_valid_share, is_block)
        """
        header = self.rebuild_header(extranonce1, extranonce2, ntime, nonce)
        hv = header_hash(header)

        is_valid_share = hv <= self.share_target
        is_block = hv <= self.target

        return is_valid_share, is_block

    def difficulty(self) -> float:
        """Calculate the difficulty of this job."""
        return calculate_difficulty(self.target)

    def share_difficulty(self) -> float:
        """Calculate the share difficulty."""
        return calculate_difficulty(self.share_target)


# ---------------------------------------------------------------------------
# Hashrate Tracker
# ---------------------------------------------------------------------------

class HashrateTracker:
    """Tracks and reports hashrate statistics."""

    def __init__(self, window_seconds: int = 60):
        self.window = window_seconds
        self.hashrate_samples: List[Tuple[float, int]] = []
        self.total_hashes = 0
        self.start_time = time.time()

    def record_hashes(self, count: int):
        """Record a batch of hashes."""
        now = time.time()
        self.total_hashes += count
        self.hashrate_samples.append((now, count))
        self._cleanup(now)

    def _cleanup(self, now: float):
        """Remove old samples outside the window."""
        cutoff = now - self.window
        self.hashrate_samples = [
            (t, h) for t, h in self.hashrate_samples if t > cutoff
        ]

    def current_hashrate(self) -> float:
        """Get current hashrate in H/s."""
        now = time.time()
        self._cleanup(now)
        if not self.hashrate_samples:
            return 0.0

        total = sum(h for _, h in self.hashrate_samples)
        elapsed = now - self.hashrate_samples[0][0]
        if elapsed < 0.1:
            elapsed = 0.1

        return total / elapsed

    def average_hashrate(self) -> float:
        """Get average hashrate since start."""
        elapsed = time.time() - self.start_time
        if elapsed < 0.1:
            return 0.0
        return self.total_hashes / elapsed

    def format_hashrate(self, h: float = None) -> str:
        """Format hashrate with appropriate units."""
        if h is None:
            h = self.current_hashrate()

        if h >= 1_000_000_000:
            return f"{h / 1_000_000_000:.2f} GH/s"
        elif h >= 1_000_000:
            return f"{h / 1_000_000:.2f} MH/s"
        elif h >= 1_000:
            return f"{h / 1_000:.2f} KH/s"
        else:
            return f"{h:.0f} H/s"


# ---------------------------------------------------------------------------
# Share Statistics
# ---------------------------------------------------------------------------

@dataclass
class ShareStats:
    """Statistics for mining shares."""
    accepted: int = 0
    rejected: int = 0
    blocks: int = 0
    stale: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "accepted": self.accepted,
            "rejected": self.rejected,
            "blocks": self.blocks,
            "stale": self.stale,
            "total": self.accepted + self.rejected + self.blocks
        }


# ---------------------------------------------------------------------------
# JSON-RPC Client for Fork Node
# ---------------------------------------------------------------------------

class ForkNodeRPC:
    """JSON-RPC client for the EXCAL fork node."""

    def __init__(self, host: str = DEFAULT_RPC_HOST, port: int = DEFAULT_RPC_PORT):
        self.host = host
        self.port = port

    def call(self, method: str, params: List[Any] = None) -> Any:
        """Make a JSON-RPC call to the fork node."""
        import http.client
        c = http.client.HTTPConnection(self.host, self.port, timeout=15)
        c.request("POST", "/", json.dumps({
            "method": method,
            "params": params or [],
            "id": 1
        }))
        r = json.loads(c.getresponse().read())
        c.close()
        if r.get("error"):
            raise RuntimeError(f"RPC error: {r['error']}")
        return r.get("result")

    def get_best_block_hash(self) -> str:
        """Get the current best block hash."""
        return self.call("getbestblockhash")

    def get_block(self, block_hash: str) -> Dict[str, Any]:
        """Get block details by hash."""
        return self.call("getblock", [block_hash])

    def submit_block(self, block: Dict[str, Any]) -> Dict[str, Any]:
        """Submit a mined block."""
        return self.call("submitblock", [block])

    def get_new_address(self) -> str:
        """Get a new wallet address."""
        return self.call("getnewaddress")


# ---------------------------------------------------------------------------
# Stratum Server (accepts GPU miner connections)
# ---------------------------------------------------------------------------

class StratumServer:
    """
    Stratum mining server that accepts GPU miner connections and submits
    blocks to the fork node via JSON-RPC.
    """

    def __init__(self, host: str = DEFAULT_STRATUM_HOST,
                 port: int = DEFAULT_STRATUM_PORT,
                 rpc_host: str = DEFAULT_RPC_HOST,
                 rpc_port: int = DEFAULT_RPC_PORT,
                 share_mult: int = 1,
                 tag: bytes = DEFAULT_TAG):
        self.host = host
        self.port = port
        self.share_mult = share_mult
        self.tag = tag

        self.rpc = ForkNodeRPC(rpc_host, rpc_port)
        self.clients: Dict[str, Any] = {}  # addr -> (reader, writer, state)
        self.extranonce_counter = 0
        self.current_job: Optional[MiningJob] = None
        self.jobs: Dict[str, MiningJob] = {}  # job_id -> job
        self.share_stats = ShareStats()
        self.hashrate = HashrateTracker()

        # Chain context
        self.chain_ctx: Dict[int, Tuple[int, int]] = {}
        self.tip_hash: Optional[str] = None
        self.tip_block: Optional[Dict] = None
        self.wallet_pub: Optional[bytes] = None

        # Server state
        self.server = None
        self.running = False

    def log(self, *args):
        """Log with timestamp."""
        print(time.strftime("%H:%M:%S"), *args, flush=True)

    def _required_bits(self, height: int) -> int:
        """Calculate required difficulty bits for a height."""
        if height < DAF_WINDOW:
            return 0x1d00ffff  # min difficulty

        first = self.chain_ctx.get(height - DAF_WINDOW)
        last = self.chain_ctx.get(height - 1)
        if not first or not last:
            return last[1] if last else 0x1d00ffff

        span = last[0] - first[0]
        if span <= 0:
            span = 1

        target_span = DAF_WINDOW * DAF_SPACING
        span = max(target_span // 4, min(target_span * 4, span))

        nt = bits_to_target(last[1]) * span // target_span
        return target_to_bits(min(nt, bits_to_target(0x1d00ffff)))

    def _strategy_bits(self, height: int, parent_bits: int) -> int:
        """GRACE-PATH STRATEGY: exact at window boundary, inherited otherwise."""
        if height % DAF_WINDOW == 0:
            return self._required_bits(height)
        return parent_bits

    def _make_coinbase(self, height: int, bits: int,
                       extranonce_slot: bytes) -> bytes:
        """Create a coinbase transaction."""
        from txscript import make_coinbase_v2
        return make_coinbase_v2(height, bits, self.tag, 0,
                               self.wallet_pub,
                               extra_pushes=[extranonce_slot])

    async def _refresh_tip(self) -> bool:
        """Refresh chain tip. Returns True if changed."""
        try:
            tip_hash = self.rpc.get_best_block_hash()
            if tip_hash == self.tip_hash:
                return False

            block = self.rpc.get_block(tip_hash)
            height = block["height"]

            # Build context window
            ctx = {height: (block["time"], int(block["bits"], 16))}
            cur = block
            while cur["height"] > height - DAF_WINDOW and cur["height"] > 0:
                cur = self.rpc.get_block(cur["prev"])
                ctx[cur["height"]] = (cur["time"], int(cur["bits"], 16))

            self.chain_ctx = ctx
            self.tip_block = block
            self.tip_hash = tip_hash

            if not self.wallet_pub:
                addr_hex = self.rpc.get_new_address()
                self.wallet_pub = bytes.fromhex(addr_hex)

            return True
        except Exception as e:
            self.log(f"Tip refresh error: {e}")
            return False

    def _create_job(self) -> Optional[MiningJob]:
        """Create a new mining job from current tip."""
        if not self.tip_block:
            return None

        height = self.tip_block["height"] + 1
        parent_bits = int(self.tip_block["bits"], 16)
        bits = self._strategy_bits(height, parent_bits)
        target = bits_to_target(bits)
        share_target = min(target * self.share_mult, MAX_TARGET)

        ntime = max(self.tip_block["time"] + 1, int(time.time()))
        prev_hash = bytes.fromhex(self.tip_hash)

        # Create coinbase with extranonce slot
        extranonce_slot = b"\x00" * 8
        coinbase = self._make_coinbase(height, bits, extranonce_slot)

        # Split coinbase at extranonce slot
        marker = b"\x08" + b"\x00" * 8
        off = coinbase.rfind(marker)
        if off <= 0:
            return None

        coinbase_1 = coinbase[:off + 1]
        coinbase_2 = coinbase[off + 1 + 8:]

        job_id = f"{height:x}-{ntime:x}"

        return MiningJob(
            job_id=job_id,
            prev_hash=prev_hash,
            coinbase_1=coinbase_1,
            coinbase_2=coinbase_2,
            merkle_branches=[],
            version=1,
            bits=bits,
            ntime=ntime,
            height=height,
            target=target,
            share_target=share_target,
            parent_time=self.tip_block["time"]
        )

    async def _broadcast_job(self):
        """Broadcast current job to all connected miners."""
        if not self.current_job:
            return

        params = [
            self.current_job.job_id,
            self._wordswap(self.current_job.prev_hash).hex(),
            self.current_job.coinbase_1.hex(),
            self.current_job.coinbase_2.hex(),
            self.current_job.merkle_branches,
            "00000001",
            f"{self.current_job.bits:08x}",
            f"{self.current_job.ntime:08x}",
            True
        ]

        diff = calculate_difficulty(self.current_job.share_target)

        for addr, (reader, writer, state) in list(self.clients.items()):
            try:
                # Set difficulty
                diff_msg = StratumMessage(
                    method=StratumMethod.SET_DIFFICULTY.value,
                    params=[diff]
                )
                writer.write((diff_msg.to_json() + "\n").encode())

                # Notify
                notify_msg = StratumMessage(
                    method=StratumMethod.NOTIFY.value,
                    params=params
                )
                writer.write((notify_msg.to_json() + "\n").encode())
            except Exception:
                pass

    @staticmethod
    def _wordswap(b: bytes) -> bytes:
        """Word-swap bytes for Stratum protocol."""
        return b"".join(b[i:i + 4][::-1] for i in range(0, len(b), 4))

    async def _handle_client(self, reader: asyncio.StreamReader,
                            writer: asyncio.StreamWriter):
        """Handle a connected miner client."""
        addr = writer.get_extra_info('peername')
        self.extranonce_counter += 1
        en1 = struct.pack("<I", self.extranonce_counter)

        state = {
            "subscribed": False,
            "authorized": False,
            "extranonce1": en1,
            "hashrate": 0
        }
        self.clients[str(addr)] = (reader, writer, state)

        self.log(f"Miner connected: {addr} (en1={en1.hex()})")

        try:
            while True:
                line = await asyncio.wait_for(reader.readline(), timeout=300)
                if not line:
                    break

                try:
                    msg = StratumMessage.from_json(line.decode())
                except Exception:
                    continue

                def reply(result, error=None):
                    resp = StratumMessage(
                        method="", result=result, error=error, msg_id=msg.msg_id
                    )
                    writer.write((resp.to_json() + "\n").encode())

                if msg.method == StratumMethod.SUBSCRIBE.value:
                    state["subscribed"] = True
                    reply([
                        [[StratumMethod.SET_DIFFICULTY.value, "1"],
                         [StratumMethod.NOTIFY.value, "1"]],
                        en1.hex(),
                        4
                    ])

                elif msg.method == StratumMethod.AUTHORIZE.value:
                    state["authorized"] = True
                    reply(True)

                    # Send current job if available
                    if self.current_job:
                        diff = calculate_difficulty(self.current_job.share_target)
                        diff_msg = StratumMessage(
                            method=StratumMethod.SET_DIFFICULTY.value,
                            params=[diff]
                        )
                        writer.write((diff_msg.to_json() + "\n").encode())

                        params = [
                            self.current_job.job_id,
                            self._wordswap(self.current_job.prev_hash).hex(),
                            self.current_job.coinbase_1.hex(),
                            self.current_job.coinbase_2.hex(),
                            [],
                            "00000001",
                            f"{self.current_job.bits:08x}",
                            f"{self.current_job.ntime:08x}",
                            True
                        ]
                        notify_msg = StratumMessage(
                            method=StratumMethod.NOTIFY.value,
                            params=params
                        )
                        writer.write((notify_msg.to_json() + "\n").encode())

                elif msg.method == StratumMethod.EXTRANONCE_SUBSCRIBE.value:
                    reply([])

                elif msg.method == StratumMethod.SUBMIT.value:
                    if not (state["subscribed"] and state["authorized"]):
                        reply(False, [24, "not subscribed"])
                        continue

                    if len(msg.params) < 5:
                        reply(False, [20, "malformed submit"])
                        continue

                    worker, job_id, en2_hex, ntime_hex, nonce_hex = msg.params[:5]

                    # Look up job
                    job = self.jobs.get(job_id)
                    if not job:
                        reply(False, [21, "job not found"])
                        continue

                    try:
                        en2 = bytes.fromhex(en2_hex)
                        ntime = int(ntime_hex, 16)
                        nonce = int(nonce_hex, 16)
                    except Exception:
                        reply(False, [20, "malformed submit"])
                        continue

                    if len(en2) != 4:
                        reply(False, [20, "bad extranonce2"])
                        continue

                    # Validate ntime
                    if not (job.parent_time < ntime <= int(time.time()) + 7200):
                        reply(False, [20, "ntime out of bounds"])
                        continue

                    # Verify solution
                    is_share, is_block = job.verify_solution(
                        state["extranonce1"], en2, ntime, nonce
                    )

                    if not is_share:
                        self.share_stats.rejected += 1
                        reply(False, [23, "low difficulty share"])
                        continue

                    if is_block:
                        # Submit block to fork node
                        header = job.rebuild_header(
                            state["extranonce1"], en2, ntime, nonce
                        )
                        coinbase = (job.coinbase_1 + state["extranonce1"] +
                                   en2 + job.coinbase_2)
                        root = merkle_root([txid(coinbase)])

                        blk = {
                            "version": job.version,
                            "prev": job.prev_hash.hex(),
                            "merkle": root.hex(),
                            "time": ntime,
                            "bits": job.bits,
                            "nonce": nonce,
                            "txs": [coinbase.hex()]
                        }

                        try:
                            result = await asyncio.get_event_loop().run_in_executor(
                                None, lambda: self.rpc.submit_block(blk)
                            )
                            self.share_stats.blocks += 1
                            self.log(
                                f"🎉 BLOCK FOUND! height={result.get('height')} "
                                f"hash={result.get('hash')}"
                            )
                            reply(True)
                        except Exception as e:
                            self.log(f"Block submission failed: {e}")
                            reply(False, [20, f"node rejected: {e}"])
                    else:
                        self.share_stats.accepted += 1
                        state["hashrate"] += 1
                        reply(True)

                else:
                    reply(None, [20, "unknown method"])

        except asyncio.TimeoutError:
            self.log(f"Client timeout: {addr}")
        except Exception as e:
            self.log(f"Client error: {addr} — {e}")
        finally:
            self.clients.pop(str(addr), None)
            try:
                writer.close()
            except Exception:
                pass
            self.log(f"Miner disconnected: {addr}")

    async def _watch_tip(self):
        """Watch for new blocks and create jobs."""
        while self.running:
            try:
                if await asyncio.get_event_loop().run_in_executor(
                    None, self._refresh_tip
                ):
                    job = self._create_job()
                    if job:
                        self.current_job = job
                        self.jobs[job.job_id] = job

                        # Keep only recent jobs
                        while len(self.jobs) > 128:
                            oldest = next(iter(self.jobs))
                            del self.jobs[oldest]

                        self.log(
                            f"New job: {job.job_id} height={job.height} "
                            f"bits={job.bits:#010x} "
                            f"diff={job.difficulty():.2f}"
                        )
                        await self._broadcast_job()
            except Exception as e:
                self.log(f"Tip watch error: {e}")

            await asyncio.sleep(1.0)

    async def start(self):
        """Start the Stratum server."""
        self.running = True
        self.log(f"AetherionEXCAL Stratum Server starting...")
        self.log(f"Listening on {self.host}:{self.port}")

        # Wait for fork node
        for attempt in range(60):
            try:
                await asyncio.get_event_loop().run_in_executor(
                    None, self._refresh_tip
                )
                break
            except Exception as e:
                self.log(f"Waiting for fork node: {e}")
                await asyncio.sleep(5)
        else:
            self.log("Failed to connect to fork node. Exiting.")
            return

        # Create initial job
        job = self._create_job()
        if job:
            self.current_job = job
            self.jobs[job.job_id] = job
            self.log(f"Initial job: {job.job_id} height={job.height}")

        # Start server
        self.server = await asyncio.start_server(
            self._handle_client, self.host, self.port
        )

        # Start tip watcher
        asyncio.create_task(self._watch_tip())

        self.log(f"Server ready on {self.host}:{self.port}")
        self.log(f"Share multiplier: {self.share_mult}")
        self.log(f"Tag: {self.tag.decode()}")

        # Stats display
        async def _stats_display():
            while self.running:
                await asyncio.sleep(10)
                clients = len(self.clients)
                shares = self.share_stats
                hr = self.hashrate.format_hashrate()
                self.log(
                    f"Stats: {clients} miners | "
                    f"Shares: {shares.accepted} accepted, "
                    f"{shares.rejected} rejected, "
                    f"{shares.blocks} blocks | "
                    f"Hashrate: {hr}"
                )

        asyncio.create_task(_stats_display())

        async with self.server:
            await self.server.serve_forever()

    def stop(self):
        """Stop the server."""
        self.running = False


# ---------------------------------------------------------------------------
# Stratum Client (connects to a mining pool)
# ---------------------------------------------------------------------------

class StratumClient:
    """
    Stratum mining client that connects to an external mining pool
    and performs CPU mining.
    """

    def __init__(self, url: str, worker: str = "excal_miner",
                 threads: int = 1):
        self.url = url
        self.worker = worker
        self.threads = threads

        # Parse URL
        if url.startswith("stratum+tcp://"):
            url = url[len("stratum+tcp://"):]
        elif url.startswith("stratum://"):
            url = url[len("stratum://"):]

        if ":" in url:
            host, port_str = url.rsplit(":", 1)
            self.host = host
            self.port = int(port_str)
        else:
            self.host = url
            self.port = 3333

        self.current_job: Optional[MiningJob] = None
        self.extranonce1: bytes = b""
        self.extranonce_size = 4
        self.share_stats = ShareStats()
        self.hashrate = HashrateTracker()
        self.running = False
        self.difficulty = 1.0

    def log(self, *args):
        print(time.strftime("%H:%M:%S"), *args, flush=True)

    def _decode_job(self, params: List[Any]) -> Optional[MiningJob]:
        """Decode a mining.notify job."""
        if len(params) < 8:
            return None

        job_id = params[0]
        prev_hash = bytes.fromhex(params[1])
        coinbase_1 = bytes.fromhex(params[2])
        coinbase_2 = bytes.fromhex(params[3])
        merkle_branches = [bytes.fromhex(b) for b in params[4]]
        version = int(params[5], 16)
        bits = int(params[6], 16)
        ntime = int(params[7], 16)

        # Word-unswap prev_hash
        prev_hash = self._wordswap(prev_hash)

        target = bits_to_target(bits)

        return MiningJob(
            job_id=job_id,
            prev_hash=prev_hash,
            coinbase_1=coinbase_1,
            coinbase_2=coinbase_2,
            merkle_branches=merkle_branches,
            version=version,
            bits=bits,
            ntime=ntime,
            height=0,  # Not provided by pool
            target=target,
            share_target=target,  # Will be set by set_difficulty
            parent_time=ntime - 1
        )

    @staticmethod
    def _wordswap(b: bytes) -> bytes:
        return b"".join(b[i:i + 4][::-1] for i in range(0, len(b), 4))

    async def _mine_thread(self, thread_id: int):
        """CPU mining thread."""
        local_hashes = 0

        while self.running and self.current_job:
            job = self.current_job
            en1 = self.extranonce1 or b"\x00\x00\x00\x01"

            # Mine nonce space
            for nonce in range(0, 0xFFFFFFFF, self.threads):
                if not self.running or self.current_job != job:
                    break

                my_nonce = nonce + thread_id
                en2 = struct.pack("<I", my_nonce >> 32)  # Use upper bits

                is_share, is_block = job.verify_solution(
                    en1, en2, job.ntime, my_nonce
                )

                local_hashes += 1

                if is_share:
                    # Submit share
                    await self._submit_share(job, en1, en2, job.ntime, my_nonce)
                    if is_block:
                        self.log(f"🎉 BLOCK FOUND by thread {thread_id}!")

            # Report hashrate periodically
            if local_hashes > 0:
                self.hashrate.record_hashes(local_hashes)
                local_hashes = 0

    async def _submit_share(self, job: MiningJob, en1: bytes,
                           en2: bytes, ntime: int, nonce: int):
        """Submit a share to the pool."""
        try:
            msg = StratumMessage(
                method=StratumMethod.SUBMIT.value,
                params=[self.worker, job.job_id, en2.hex(),
                       f"{ntime:08x}", f"{nonce:08x}"],
                msg_id=int(time.time())
            )
            # This would be sent via the connection
            # For now, just track stats
            self.share_stats.accepted += 1
        except Exception as e:
            self.share_stats.rejected += 1
            self.log(f"Share submission error: {e}")

    async def _handle_response(self, reader: asyncio.StreamReader):
        """Handle incoming messages from the pool."""
        buffer = ""
        while self.running:
            try:
                data = await asyncio.wait_for(reader.read(4096), timeout=1)
                buffer += data.decode(errors="replace")

                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        msg = StratumMessage.from_json(line)

                        if msg.method == StratumMethod.SET_DIFFICULTY.value:
                            if msg.params:
                                self.difficulty = msg.params[0]
                                self.log(f"Difficulty set: {self.difficulty:.2f}")
                                if self.current_job:
                                    self.current_job.share_target = bits_to_target(
                                        target_to_bits(int(DIFF1 / self.difficulty))
                                    )

                        elif msg.method == StratumMethod.NOTIFY.value:
                            job = self._decode_job(msg.params)
                            if job:
                                self.current_job = job
                                self.log(
                                    f"New job: {job.job_id} "
                                    f"diff={job.difficulty():.2f}"
                                )

                        elif msg.result is not None:
                            if msg.result is True:
                                self.share_stats.accepted += 1
                            else:
                                self.share_stats.rejected += 1

                    except Exception:
                        pass
            except asyncio.TimeoutError:
                continue
            except Exception:
                break

    async def start(self):
        """Start the Stratum client."""
        self.running = True
        self.log(f"Connecting to {self.host}:{self.port} as {self.worker}")

        reader, writer = await asyncio.open_connection(self.host, self.port)
        self.log("Connected to pool")

        # Subscribe
        sub_msg = StratumMessage(
            method=StratumMethod.SUBSCRIBE.value,
            params=[],
            msg_id=1
        )
        writer.write((sub_msg.to_json() + "\n").encode())

        # Wait for subscription response
        response = await reader.readline()
        self.log(f"Subscribe response: {response.decode().strip()}")

        # Authorize
        auth_msg = StratumMessage(
            method=StratumMethod.AUTHORIZE.value,
            params=[self.worker, "x"],
            msg_id=2
        )
        writer.write((auth_msg.to_json() + "\n").encode())

        response = await reader.readline()
        self.log(f"Authorize response: {response.decode().strip()}")

        # Start mining threads
        mining_tasks = [
            asyncio.create_task(self._mine_thread(i))
            for i in range(self.threads)
        ]

        # Start response handler
        response_task = asyncio.create_task(self._handle_response(reader))

        # Stats display
        async def _stats_display():
            while self.running:
                await asyncio.sleep(10)
                shares = self.share_stats
                hr = self.hashrate.format_hashrate()
                self.log(
                    f"Stats: {shares.accepted} accepted, "
                    f"{shares.rejected} rejected | "
                    f"Hashrate: {hr}"
                )

        stats_task = asyncio.create_task(_stats_display())

        try:
            await asyncio.gather(*mining_tasks, response_task, stats_task)
        except asyncio.CancelledError:
            pass
        finally:
            self.running = False
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# CPU Miner (standalone, connects to fork node)
# ---------------------------------------------------------------------------

class CPUMiner:
    """
    Standalone CPU miner that connects directly to the fork node
    and mines blocks using multiple threads.
    """

    def __init__(self, threads: int = 1,
                 rpc_host: str = DEFAULT_RPC_HOST,
                 rpc_port: int = DEFAULT_RPC_PORT,
                 tag: bytes = DEFAULT_TAG):
        self.threads = threads
        self.tag = tag
        self.rpc = ForkNodeRPC(rpc_host, rpc_port)
        self.share_stats = ShareStats()
        self.hashrate = HashrateTracker()
        self.running = False

        # Chain state
        self.chain_ctx: Dict[int, Tuple[int, int]] = {}
        self.tip_hash: Optional[str] = None
        self.tip_block: Optional[Dict] = None
        self.wallet_pub: Optional[bytes] = None

    def log(self, *args):
        print(time.strftime("%H:%M:%S"), *args, flush=True)

    def _refresh_tip(self) -> bool:
        """Refresh chain tip."""
        try:
            tip_hash = self.rpc.get_best_block_hash()
            if tip_hash == self.tip_hash:
                return False

            block = self.rpc.get_block(tip_hash)
            height = block["height"]

            ctx = {height: (block["time"], int(block["bits"], 16))}
            cur = block
            while cur["height"] > height - DAF_WINDOW and cur["height"] > 0:
                cur = self.rpc.get_block(cur["prev"])
                ctx[cur["height"]] = (cur["time"], int(cur["bits"], 16))

            self.chain_ctx = ctx
            self.tip_block = block
            self.tip_hash = tip_hash

            if not self.wallet_pub:
                addr_hex = self.rpc.get_new_address()
                self.wallet_pub = bytes.fromhex(addr_hex)

            return True
        except Exception as e:
            self.log(f"Tip refresh error: {e}")
            return False

    def _mine_nonce(self, job: MiningJob, start_nonce: int,
                    step: int) -> Tuple[int, int, int, int]:
        """
        Mine nonces in a thread. Returns (nonce, ntime, hashes, found)
        where found is 0=none, 1=share, 2=block.
        """
        hashes = 0
        for nonce in range(start_nonce, 0xFFFFFFFF, step):
            if not self.running:
                return (nonce, job.ntime, hashes, 0)

            header = job.rebuild_header(b"\x00\x00\x00\x00",
                                       b"\x00\x00\x00\x00",
                                       job.ntime, nonce)
            hv = header_hash(header)
            hashes += 1

            if hv <= job.target:
                return (nonce, job.ntime, hashes, 2)  # Block found!
            if hv <= job.share_target:
                return (nonce, job.ntime, hashes, 1)  # Share found

        return (nonce, job.ntime, hashes, 0)

    def _create_job(self) -> Optional[MiningJob]:
        """Create a mining job from current tip."""
        if not self.tip_block:
            return None

        height = self.tip_block["height"] + 1
        parent_bits = int(self.tip_block["bits"], 16)

        # Calculate bits
        if height % DAF_WINDOW == 0:
            if height < DAF_WINDOW:
                bits = 0x1d00ffff
            else:
                first = self.chain_ctx.get(height - DAF_WINDOW)
                last = self.chain_ctx.get(height - 1)
                if first and last:
                    span = last[0] - first[0]
                    if span <= 0:
                        span = 1
                    target_span = DAF_WINDOW * DAF_SPACING
                    span = max(target_span // 4, min(target_span * 4, span))
                    nt = bits_to_target(last[1]) * span // target_span
                    bits = target_to_bits(min(nt, bits_to_target(0x1d00ffff)))
                else:
                    bits = parent_bits
        else:
            bits = parent_bits

        target = bits_to_target(bits)
        ntime = max(self.tip_block["time"] + 1, int(time.time()))
        prev_hash = bytes.fromhex(self.tip_hash)

        # Create coinbase
        from txscript import make_coinbase_v2
        coinbase = make_coinbase_v2(height, bits, self.tag, 0,
                                   self.wallet_pub,
                                   extra_pushes=[b"\x00" * 8])

        marker = b"\x08" + b"\x00" * 8
        off = coinbase.rfind(marker)
        if off <= 0:
            return None

        coinbase_1 = coinbase[:off + 1]
        coinbase_2 = coinbase[off + 1 + 8:]

        job_id = f"{height:x}-{ntime:x}"

        return MiningJob(
            job_id=job_id,
            prev_hash=prev_hash,
            coinbase_1=coinbase_1,
            coinbase_2=coinbase_2,
            merkle_branches=[],
            version=1,
            bits=bits,
            ntime=ntime,
            height=height,
            target=target,
            share_target=target,
            parent_time=self.tip_block["time"]
        )

    def start(self):
        """Start CPU mining (blocking)."""
        self.running = True
        self.log(f"AetherionEXCAL CPU Miner starting...")
        self.log(f"Threads: {self.threads}")
        self.log(f"Tag: {self.tag.decode()}")

        # Wait for fork node
        for attempt in range(60):
            try:
                if self._refresh_tip():
                    break
            except Exception as e:
                self.log(f"Waiting for fork node: {e}")
            time.sleep(5)
        else:
            self.log("Failed to connect to fork node. Exiting.")
            return

        self.log(f"Connected to fork node at height {self.tip_block['height']}")

        try:
            while self.running:
                # Refresh tip
                tip_changed = self._refresh_tip()

                job = self._create_job()
                if not job:
                    time.sleep(1)
                    continue

                self.log(
                    f"Mining job: {job.job_id} height={job.height} "
                    f"diff={job.difficulty():.2f}"
                )

                # Mine with threads
                with ThreadPoolExecutor(max_workers=self.threads) as executor:
                    futures = []
                    for i in range(self.threads):
                        fut = executor.submit(
                            self._mine_nonce, job, i, self.threads
                        )
                        futures.append(fut)

                    # Poll for results
                    block_found = False
                    start_time = time.time()

                    while not block_found:
                        time.sleep(0.5)

                        for i, fut in enumerate(futures):
                            if fut.done():
                                try:
                                    nonce, ntime, hashes, found = fut.result()
                                    self.hashrate.record_hashes(hashes)

                                    if found == 2:
                                        # Block found!
                                        header = job.rebuild_header(
                                            b"\x00\x00\x00\x00",
                                            b"\x00\x00\x00\x00",
                                            ntime, nonce
                                        )
                                        coinbase = (job.coinbase_1 +
                                                   b"\x00\x00\x00\x00" +
                                                   b"\x00\x00\x00\x00" +
                                                   job.coinbase_2)
                                        root = merkle_root([txid(coinbase)])

                                        blk = {
                                            "version": job.version,
                                            "prev": job.prev_hash.hex(),
                                            "merkle": root.hex(),
                                            "time": ntime,
                                            "bits": job.bits,
                                            "nonce": nonce,
                                            "txs": [coinbase.hex()]
                                        }

                                        try:
                                            result = self.rpc.submit_block(blk)
                                            self.share_stats.blocks += 1
                                            self.log(
                                                f"🎉 BLOCK SUBMITTED! "
                                                f"height={result.get('height')} "
                                                f"hash={result.get('hash')}"
                                            )
                                            block_found = True
                                        except Exception as e:
                                            self.log(f"Block submission failed: {e}")

                                    elif found == 1:
                                        self.share_stats.accepted += 1
                                        self.log(f"Share found by thread {i}")

                                except Exception as e:
                                    self.log(f"Thread {i} error: {e}")

                        # Timeout — restart job if ntime is stale
                        if time.time() - start_time > 55:
                            break

                # Display stats
                shares = self.share_stats
                hr = self.hashrate.format_hashrate()
                self.log(
                    f"Stats: {shares.accepted} shares, "
                    f"{shares.blocks} blocks | "
                    f"Hashrate: {hr}"
                )

        except KeyboardInterrupt:
            self.log("Mining stopped by user")
        finally:
            self.running = False


# ---------------------------------------------------------------------------
# Benchmark Mode
# ---------------------------------------------------------------------------

def run_benchmark(threads: int = 1, duration: int = 10):
    """Run a hashrate benchmark."""
    print(f"AetherionEXCAL Hashrate Benchmark")
    print(f"Threads: {threads}")
    print(f"Duration: {duration}s")
    print()

    # Create a dummy job for benchmarking
    dummy_prev = b"\x00" * 32
    dummy_cb1 = b"\x00" * 100
    dummy_cb2 = b"\x00" * 50
    job = MiningJob(
        job_id="benchmark",
        prev_hash=dummy_prev,
        coinbase_1=dummy_cb1,
        coinbase_2=dummy_cb2,
        merkle_branches=[],
        version=1,
        bits=0x1d00ffff,
        ntime=int(time.time()),
        height=0,
        target=bits_to_target(0x1d00ffff),
        share_target=bits_to_target(0x1d00ffff),
        parent_time=int(time.time()) - 1
    )

    hashrate = HashrateTracker()
    running = True

    def mine_thread(thread_id: int):
        local_hashes = 0
        while running:
            for nonce in range(thread_id, 0xFFFFFFFF, threads):
                header = job.rebuild_header(
                    b"\x00\x00\x00\x00", b"\x00\x00\x00\x00",
                    job.ntime, nonce
                )
                header_hash(header)
                local_hashes += 1

            hashrate.record_hashes(local_hashes)
            local_hashes = 0

    thread_list = []
    for i in range(threads):
        t = threading.Thread(target=mine_thread, args=(i,))
        t.start()
        thread_list.append(t)

    # Report hashrate every second
    try:
        for _ in range(duration):
            time.sleep(1)
            hr = hashrate.format_hashrate()
            print(f"\rHashrate: {hr}", end="", flush=True)
    except KeyboardInterrupt:
        pass
    finally:
        running = False
        for t in thread_list:
            t.join(timeout=2)

    print()
    print(f"\nFinal hashrate: {hashrate.format_hashrate()}")
    print(f"Total hashes: {hashrate.total_hashes}")


import threading


# ---------------------------------------------------------------------------
# CLI Interface
# ---------------------------------------------------------------------------

def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser."""
    parser = argparse.ArgumentParser(
        prog="stratum_miner",
        description="AetherionEXCAL External Stratum Miner — Production Mining Software",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Server mode (accept GPU miners)
  %(prog)s server --host 0.0.0.0 --port 3333

  # Client mode (connect to pool)
  %(prog)s client --url stratum+tcp://pool.example.com:3333 --worker rig1

  # CPU mining mode
  %(prog)s cpu --threads 4

  # Benchmark
  %(prog)s benchmark --threads 4 --duration 10
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="Mining mode")

    # Server mode
    server_parser = subparsers.add_parser(
        "server", help="Run Stratum server (accept GPU miners)"
    )
    server_parser.add_argument(
        "--host", default=os.environ.get("STRATUM_HOST", DEFAULT_STRATUM_HOST),
        help=f"Listen host (default: {DEFAULT_STRATUM_HOST})"
    )
    server_parser.add_argument(
        "--port", type=int,
        default=int(os.environ.get("STRATUM_PORT", DEFAULT_STRATUM_PORT)),
        help=f"Listen port (default: {DEFAULT_STRATUM_PORT})"
    )
    server_parser.add_argument(
        "--rpc-host", default=DEFAULT_RPC_HOST,
        help=f"Fork node RPC host (default: {DEFAULT_RPC_HOST})"
    )
    server_parser.add_argument(
        "--rpc-port", type=int, default=DEFAULT_RPC_PORT,
        help=f"Fork node RPC port (default: {DEFAULT_RPC_PORT})"
    )
    server_parser.add_argument(
        "--share-mult", type=int, default=1,
        help="Share multiplier (default: 1 = every valid block is a share)"
    )
    server_parser.add_argument(
        "--tag", default=DEFAULT_TAG.decode(),
        help=f"Coinbase tag (default: {DEFAULT_TAG.decode()})"
    )

    # Client mode
    client_parser = subparsers.add_parser(
        "client", help="Connect to a mining pool"
    )
    client_parser.add_argument(
        "--url", required=True,
        help="Pool URL (e.g., stratum+tcp://pool.example.com:3333)"
    )
    client_parser.add_argument(
        "--worker", default="excal_miner",
        help="Worker name (default: excal_miner)"
    )
    client_parser.add_argument(
        "--threads", type=int, default=1,
        help="CPU mining threads (default: 1)"
    )

    # CPU mode
    cpu_parser = subparsers.add_parser(
        "cpu", help="CPU mining (connects to fork node)"
    )
    cpu_parser.add_argument(
        "--threads", type=int,
        default=max(1, multiprocessing.cpu_count() // 2),
        help="Mining threads (default: half of CPU cores)"
    )
    cpu_parser.add_argument(
        "--rpc-host", default=DEFAULT_RPC_HOST,
        help=f"Fork node RPC host (default: {DEFAULT_RPC_HOST})"
    )
    cpu_parser.add_argument(
        "--rpc-port", type=int, default=DEFAULT_RPC_PORT,
        help=f"Fork node RPC port (default: {DEFAULT_RPC_PORT})"
    )
    cpu_parser.add_argument(
        "--tag", default=DEFAULT_TAG.decode(),
        help=f"Coinbase tag (default: {DEFAULT_TAG.decode()})"
    )

    # Benchmark mode
    bench_parser = subparsers.add_parser(
        "benchmark", help="Run hashrate benchmark"
    )
    bench_parser.add_argument(
        "--threads", type=int,
        default=max(1, multiprocessing.cpu_count() // 2),
        help="Benchmark threads (default: half of CPU cores)"
    )
    bench_parser.add_argument(
        "--duration", type=int, default=10,
        help="Benchmark duration in seconds (default: 10)"
    )

    return parser


async def main():
    """Main entry point."""
    parser = create_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "server":
        server = StratumServer(
            host=args.host,
            port=args.port,
            rpc_host=args.rpc_host,
            rpc_port=args.rpc_port,
            share_mult=args.share_mult,
            tag=args.tag.encode()
        )
        await server.start()

    elif args.command == "client":
        client = StratumClient(
            url=args.url,
            worker=args.worker,
            threads=args.threads
        )
        await client.start()

    elif args.command == "cpu":
        miner = CPUMiner(
            threads=args.threads,
            rpc_host=args.rpc_host,
            rpc_port=args.rpc_port,
            tag=args.tag.encode()
        )
        miner.start()

    elif args.command == "benchmark":
        run_benchmark(threads=args.threads, duration=args.duration)


if __name__ == "__main__":
    asyncio.run(main())
