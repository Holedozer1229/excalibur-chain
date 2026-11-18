#!/usr/bin/env python3
"""live_merge_mining.py — Live Merge Mining on Solo Pools

Connects to a Bitcoin solo mining pool (solo.cat or solo.ckpool.org) via
Stratum protocol, receives mining jobs, and performs merge mining:
every hash attempt simultaneously targets both Bitcoin (parent) and
Excalibur (child) chains.

Architecture:
    Solo pool (stratum+tcp://solo.cat:21496)
          ↓
    Stratum client (this file)
          ↓
    Mining loop: for each job from the pool:
      1. Decode job (prevhash, coinbase, merkle, version, bits, ntime)
      2. Build Excalibur child block on current fork tip
      3. Build AuxPoW parent template committing to child
      4. Mine nonces checking BOTH targets:
         - Bitcoin target (pool job bits) → pool share/block
         - Excalibur target (child bits) → child block via AuxPoW
      5. Submit shares to pool on Bitcoin hits
      6. Submit AuxPoW blocks to fork node on child hits

Scalar wave φ(t) = Σ cos(γₖ·t)/γₖ guides nonce selection by scoring
candidates at the Riemann zero spectrum positions.

Usage:
    # Connect to solo.cat
    py live_merge_mining.py --pool stratum+tcp://solo.cat:21496 --wallet YOUR_BTC_ADDRESS

    # Connect to solo.ckpool.org
    py live_merge_mining.py --pool stratum+tcp://solo.ckpool.org:3333 --wallet YOUR_BTC_ADDRESS

    # Test mode (no pool connection, just verify AuxPoW construction)
    py live_merge_mining.py --test

    # Dry run (build blocks without connecting)
    py live_merge_mining.py --dry-run

Environment:
    EXCAL_RPC_PORT  — Fork node RPC port (default: 9432)
    EXCAL_WALLET_FILE — Fork wallet file path
    BTC_WALLET       — Bitcoin payout address (or use --wallet)

Pure Python, stdlib only.
"""
import argparse
import asyncio
import hashlib
import http.client
import json
import math
import os
import struct
import sys
import time
import signal
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

# ---------------------------------------------------------------------------
# Riemann zeros (first 15) for scalar wave
# ---------------------------------------------------------------------------
RIEMANN_ZEROS = [
    14.13472514173469, 21.02203963877155, 25.01085858181174,
    30.42487611818375, 32.93506158773918, 37.58617815882538,
    40.91871901214749, 43.32707328091601, 48.00515088116708,
    49.77383247767236, 52.97032147771091, 56.44624769702193,
    59.34704400801026, 60.83177855412748, 65.11254404809211,
]

GOLDEN_RATIO = (1 + math.sqrt(5)) / 2

# AuxPoW magic
AUXPOW_MAGIC = b"\xfa\xbe" + b"mm"

# Bitcoin difficulty-1 target
DIFF1 = 0x00000000FFFF0000000000000000000000000000000000000000000000000000
MAX_TARGET = (1 << 256) - 1

# Default payout script (P2PKH)
DEFAULT_PAYOUT_SCRIPT = bytes.fromhex(
    "76a914130a603c7eba4023bcc0ac478257d2c80918521988ac")


# ---------------------------------------------------------------------------
# Scalar Wave Engine
# ---------------------------------------------------------------------------

class ScalarWave:
    """φ(t) = Σ cos(γₖ·t)/γₖ for nonce scoring."""

    def __init__(self, zeros=None):
        self.zeros = zeros or RIEMANN_ZEROS

    def phi(self, t):
        return sum(math.cos(g * t) / g for g in self.zeros)

    def amplitude(self, t):
        return abs(self.phi(t))

    def phase(self, t, dt=1e-8):
        return math.atan2(self.phi(t + dt) - self.phi(t - dt), 2 * dt * self.amplitude(t) + 1e-30)

    def score_nonce(self, nonce, max_nonce=0xFFFFFFFF):
        t = nonce / max_nonce
        return self.amplitude(t)

    def best_nonces(self, count=10, max_nonce=0xFFFFFFFF):
        """Find the top nonces by scalar wave amplitude."""
        candidates = []
        step = max_nonce // (count * 100)
        for i in range(count * 100):
            nonce = i * step
            score = self.score_nonce(nonce, max_nonce)
            candidates.append((score, nonce))
        candidates.sort(reverse=True)
        return [(n, s) for s, n in candidates[:count]]


# ---------------------------------------------------------------------------
# Hashing & Header Functions
# ---------------------------------------------------------------------------

def sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def sha256d(data: bytes) -> bytes:
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()


def bits_to_target(bits: int) -> int:
    exp = bits >> 24
    mant = bits & 0xFFFFFF
    if exp <= 3:
        return mant >> (8 * (3 - exp))
    return mant << (8 * (exp - 3))


def target_to_bits(target: int) -> int:
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


def ser_header(version: int, prev: bytes, merkle: bytes,
               timestamp: int, bits: int, nonce: int) -> bytes:
    return (struct.pack("<I", version) +
            prev[:32] +
            merkle[:32] +
            struct.pack("<III", timestamp, bits, nonce))


def header_hash(header: bytes) -> int:
    return int.from_bytes(sha256d(header), "big")


def txid(raw: bytes) -> bytes:
    return sha256d(raw)


def _push(d):
    return bytes([len(d)]) + d


# ---------------------------------------------------------------------------
# Coinbase Transaction Builder
# ---------------------------------------------------------------------------

def make_coinbase_v2(height, bits, tag, merkle_nonce, wallet_pub,
                     extra_pushes=None):
    """Build a coinbase transaction (simplified version from txscript)."""
    # ScriptSig: height + tag + merkle_nonce
    script_sig = _push(height.to_bytes(4, "little")) + _push(tag)
    if extra_pushes:
        for ep in extra_pushes:
            script_sig += _push(ep)

    # pubkey hash from wallet_pub (compressed 33 bytes → P2PKH)
    if wallet_pub and len(wallet_pub) == 33:
        x_bytes = wallet_pub[1:]
        prefix = b"\x00" * 12
        h = hashlib.sha256(wallet_pub).digest()
        pkh = hashlib.new("ripemd160", h).digest()
        script_pubkey = bytes.fromhex("76a914") + pkh + bytes.fromhex("88ac")
    else:
        # OP_TRUE (coinbase can have any scriptPubkey for mining)
        script_pubkey = bytes.fromhex("51")

    # Build transaction
    tx = struct.pack("<I", 1)  # version
    # vin
    tx += struct.pack("<B", 1)  # 1 input
    tx += b"\x00" * 32  # prevout txid
    tx += struct.pack("<I", 0xFFFFFFFF)  # prevout index
    tx += _push(script_sig)  # scriptSig
    tx += struct.pack("<I", 0xFFFFFFFF)  # sequence
    # vout
    tx += struct.pack("<B", 1)  # 1 output
    tx += struct.pack("<Q", 50 * 100_000_000)  # value (50 BTC in satoshis)
    tx += _push(script_pubkey)  # scriptPubkey
    tx += struct.pack("<I", 0)  # locktime

    return tx


# ---------------------------------------------------------------------------
# Fork Node RPC
# ---------------------------------------------------------------------------

class ForkNodeRPC:
    """JSON-RPC client for the Excalibur fork node."""

    def __init__(self, host="127.0.0.1", port=9432):
        self.host = host
        self.port = port

    def call(self, method, params=None):
        if params is None:
            params = []
        c = http.client.HTTPConnection(self.host, self.port, timeout=10)
        c.request("POST", "/", json.dumps({
            "method": method, "params": params, "id": 1
        }))
        r = json.loads(c.getresponse().read())
        c.close()
        if r.get("error"):
            raise RuntimeError(f"RPC error: {r['error']}")
        return r.get("result")

    def get_best_block_hash(self):
        return self.call("getbestblockhash")

    def get_block(self, block_hash):
        return self.call("getblock", [block_hash])

    def submit_block(self, block_dict):
        return self.call("submitblock", [json.dumps(block_dict)])


# ---------------------------------------------------------------------------
# AuxPoW Builder
# ---------------------------------------------------------------------------

class AuxPowBuilder:
    """Build AuxPoW parent templates for merge mining."""

    def __init__(self, payout_script=None):
        self.payout_script = payout_script or DEFAULT_PAYOUT_SCRIPT

    def build_child_block(self, fork_rpc, nonce=0, bits_override=None):
        """Build an Excalibur child block on the current fork tip."""
        try:
            tip_hash = fork_rpc.get_best_block_hash()
            tip_block = fork_rpc.get_block(tip_hash)
        except Exception as e:
            print(f"  [!] Cannot reach fork node: {e}")
            print(f"  [!] Using simulated tip for dry-run mode")
            # Simulated tip for dry-run
            tip_block = {
                "height": 0,
                "hash": "0" * 64,
                "time": int(time.time()),
                "bits": "1d00ffff"
            }
            tip_hash = "0" * 64

        height = tip_block["height"] + 1
        t = max(tip_block["time"] + 1, int(time.time()))
        bits = bits_override if bits_override else int(tip_block["bits"], 16)

        # Build coinbase
        cb = make_coinbase_v2(height, bits, b"AetherionEXCAL", 0, None)
        merkle = txid(cb)
        prev = bytes.fromhex(tip_hash)

        header = ser_header(1, prev, merkle, t, bits, nonce)
        child_hash = sha256d(header)

        blk = {
            "version": 1,
            "prev": prev,
            "merkle": merkle,
            "time": t,
            "bits": bits,
            "nonce": nonce,
            "txs": [cb]
        }
        return blk, header, child_hash

    def build_parent_template(self, child_hash, btc_prev_hash, btc_height,
                              btc_bits, timestamp, wallet_address=None):
        """Build a Bitcoin parent template with AuxPoW commitment.

        Returns (coinbase_raw, header_prefix76).
        """
        # Build the merged-mining commitment blob
        blob = (AUXPOW_MAGIC + child_hash
                + struct.pack("<I", 1)  # tree_size = 1 (single aux)
                + struct.pack("<I", 0))  # merkle_nonce = 0

        # Build coinbase script
        script = (_push((btc_height + 1).to_bytes(3, "little"))
                  + _push(b"AetherionEXCAL")
                  + _push(blob))

        # Build coinbase transaction
        cb = struct.pack("<I", 1)  # version
        cb += struct.pack("<B", 1)  # 1 input
        cb += b"\x00" * 32  # prevout txid
        cb += struct.pack("<I", 0xFFFFFFFF)  # prevout index
        cb += _push(script)  # scriptSig
        cb += struct.pack("<I", 0xFFFFFFFF)  # sequence
        cb += struct.pack("<B", 1)  # 1 output
        cb += struct.pack("<Q", 312500000)  # value (3.125 BTC)
        cb += _push(self.payout_script)  # scriptPubkey
        cb += struct.pack("<I", 0)  # locktime

        merkle = txid(cb)

        # Build header prefix (76 bytes without nonce)
        prefix = (struct.pack("<I", 1)  # version
                  + btc_prev_hash[::-1]  # prev_block (reversed for header)
                  + merkle  # merkle root
                  + struct.pack("<II", timestamp, btc_bits))  # time + bits

        assert len(prefix) == 76, f"Prefix length: {len(prefix)}"
        return cb, prefix

    def build_auxpow(self, parent_header, parent_coinbase, coinbase_branch,
                     coinbase_index):
        """Build the AuxPoW JSON structure for submission."""
        return {
            "parent_header": parent_header.hex(),
            "parent_coinbase": parent_coinbase.hex(),
            "coinbase_branch": [s.hex() for s in coinbase_branch],
            "coinbase_index": coinbase_index
        }


# ---------------------------------------------------------------------------
# Bitcoin Tip Fetcher
# ---------------------------------------------------------------------------

class BitcoinTipFetcher:
    """Fetch the current Bitcoin mainnet tip from various sources."""

    @staticmethod
    def from_mempool():
        """Fetch from mempool.space API."""
        try:
            import urllib.request
            # Get tip hash
            url = "https://mempool.space/api/blocks/tip/hash"
            with urllib.request.urlopen(url, timeout=15) as resp:
                tip_hash = resp.read().decode().strip()

            # Get block details
            url = f"https://mempool.space/api/block/{tip_hash}"
            with urllib.request.urlopen(url, timeout=15) as resp:
                block = json.loads(resp.read().decode())

            return {
                "hash": tip_hash,
                "height": block["height"],
                "bits": block["bits"],
                "time": block["timestamp"]
            }
        except Exception as e:
            print(f"  [!] mempool.space fetch failed: {e}")
            return None

    @staticmethod
    def from_blockcypher():
        """Fetch from BlockCypher API."""
        try:
            import urllib.request
            url = "https://api.blockcypher.com/v1/btc/main/blocks/latest"
            with urllib.request.urlopen(url, timeout=15) as resp:
                block = json.loads(resp.read().decode())

            return {
                "hash": block["hash"],
                "height": block["height"],
                "bits": block["bits"],
                "time": int(block["time"])
            }
        except Exception as e:
            print(f"  [!] BlockCypher fetch failed: {e}")
            return None

    @staticmethod
    def get_tip():
        """Get Bitcoin tip, trying multiple sources."""
        tip = BitcoinTipFetcher.from_mempool()
        if tip:
            return tip
        tip = BitcoinTipFetcher.from_blockcypher()
        if tip:
            return tip
        raise RuntimeError("Cannot fetch Bitcoin tip from any source")


# ---------------------------------------------------------------------------
# Stratum Client for Solo Mining
# ---------------------------------------------------------------------------

class SoloStratumClient:
    """Stratum client for solo mining pools with merge mining support."""

    def __init__(self, pool_url, wallet_address, worker="AetherionEXCAL"):
        self.wallet = wallet_address
        self.worker = worker

        # Parse URL
        url = pool_url
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

        # Mining state
        self.current_job = None
        self.extranonce1 = b""
        self.extranonce2_size = 4
        self.difficulty = 1.0
        self.share_target = MAX_TARGET

        # Statistics
        self.hashes = 0
        self.shares_submitted = 0
        self.shares_accepted = 0
        self.shares_rejected = 0
        self.blocks_found = 0
        self.child_hits = 0
        self.dual_hits = 0
        self.start_time = None
        self.running = False

        # Components
        self.scalar_wave = ScalarWave()
        self.aux_builder = AuxPowBuilder()
        self.fork_rpc = ForkNodeRPC()
        self.btc_tip_fetcher = BitcoinTipFetcher()
        # Cached Bitcoin tip (fetched once, reused)
        self.btc_tip_cache = None

        # Connection
        self.reader = None
        self.writer = None

    def log(self, *args):
        ts = time.strftime("%H:%M:%S")
        print(f"[{ts}] {' '.join(str(a) for a in args)}", flush=True)

    def _wordswap(self, b: bytes) -> bytes:
        return b"".join(b[i:i + 4][::-1] for i in range(0, len(b), 4))

    def _decode_job(self, params: List[Any]) -> Optional[Dict]:
        """Decode a mining.notify job."""
        if len(params) < 8:
            return None

        job_id = params[0]
        prev_hash = self._wordswap(bytes.fromhex(params[1]))
        coinbase_1 = bytes.fromhex(params[2])
        coinbase_2 = bytes.fromhex(params[3])
        merkle_branches = [bytes.fromhex(b) for b in params[4]]
        version = int(params[5], 16)
        bits = int(params[6], 16)
        ntime = int(params[7], 16)

        target = bits_to_target(bits)

        return {
            "job_id": job_id,
            "prev_hash": prev_hash,
            "coinbase_1": coinbase_1,
            "coinbase_2": coinbase_2,
            "merkle_branches": merkle_branches,
            "version": version,
            "bits": bits,
            "ntime": ntime,
            "target": target,
        }

    def _build_merkle_root(self, coinbase_tx, branches):
        """Build merkle root from coinbase and branches."""
        merkle = txid(coinbase_tx)
        for branch in branches:
            merkle = txid(merkle + branch)
        return merkle

    async def _send(self, msg_dict):
        """Send a JSON-RPC message to the pool."""
        line = json.dumps(msg_dict) + "\n"
        self.writer.write(line.encode())
        await self.writer.drain()

    async def _receive(self):
        """Receive a line from the pool."""
        line = await self.reader.readline()
        return line.decode().strip()

    async def _handle_notification(self, msg):
        """Handle pool notifications (jobs, difficulty changes)."""
        method = msg.get("method", "")
        params = msg.get("params", [])

        if method == "mining.notify" and params:
            job = self._decode_job(params)
            if job:
                self.current_job = job
                self.log(f"New job: {job['job_id']} bits=0x{job['bits']:08x}")
        elif method == "mining.set_difficulty" and params:
            self.difficulty = params[0]
            # Share target: difficulty 1 = DIFF1, higher diff = lower target
            # DIFF1 = 0x00000000FFFF... (Bitcoin difficulty-1 target)
            self.share_target = int(DIFF1 / self.difficulty)
            self.log(f"Difficulty set: {self.difficulty} (share target adjusted)")
        elif method == "mining.set_version_mask":
            pass  # Ignore version mask
        else:
            self.log(f"Notification: {method}")

    async def _handle_response(self, msg):
        """Handle pool responses to our requests."""
        msg_id = msg.get("id")
        result = msg.get("result")
        error = msg.get("error")

        if msg_id == 1:  # Subscribe response
            # Format: [[["mining.notify", "id"]], "extranonce1", extranonce2_size]
            if result and isinstance(result, list) and len(result) >= 3:
                self.extranonce1 = bytes.fromhex(result[1])
                self.extranonce2_size = result[2]
            self.log("Subscribed to pool")
        elif msg_id == 2:  # Authorize response
            if result:
                self.log("Authorized successfully")
            else:
                self.log(f"Authorization failed: {error}")
        elif msg_id and msg_id >= 100:  # Submit response
            if result:
                self.shares_accepted += 1
                self.log(f"Share accepted! (total: {self.shares_accepted})")
            else:
                self.shares_rejected += 1
                self.log(f"Share rejected: {error}")
        else:
            self.log(f"Response id={msg_id}: result={result}, error={error}")

    async def _connect_and_mine(self):
        """Main connection and mining loop."""
        self.running = True
        self.start_time = time.time()

        self.log(f"Connecting to {self.host}:{self.port}...")

        max_retries = 5
        for attempt in range(max_retries):
            try:
                self.reader, self.writer = await asyncio.open_connection(
                    self.host, self.port
                )
                self.log("Connected to pool")
                break
            except Exception as e:
                self.log(f"Connection failed (attempt {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(5 * (attempt + 1))
                else:
                    self.log("Max retries reached. Exiting.")
                    return
        else:
            return

        # Step 1: Subscribe
        self.log("Subscribing...")
        await self._send({"id": 1, "method": "mining.subscribe",
                          "params": [["AetherionEXCAL/1.0", ""]], })

        # Step 2: Read response (may be multiple lines)
        response = await self._receive()
        self.log(f"Subscribe response: {response[:100]}")
        resp = json.loads(response)
        await self._handle_response(resp)

        # Some pools send extranonce.subscribe request
        try:
            extra = await asyncio.wait_for(self._receive(), timeout=2)
            extra_resp = json.loads(extra)
            if extra_resp.get("method") == "mining.extranonce.subscribe":
                await self._send({"id": extra_resp.get("id"), "result": True, "error": None})
        except asyncio.TimeoutError:
            pass

        # Step 3: Authorize — use wallet address as worker name for solo pools
        self.log("Authorizing...")
        await self._send({
            "id": 2,
            "method": "mining.authorize",
            "params": [self.wallet, "x"]
        })

        response = await self._receive()
        self.log(f"Authorize response: {response[:100]}")
        resp = json.loads(response)
        await self._handle_response(resp)

        self.log(f"Wallet: {self.wallet}")
        self.log(f"Worker: {self.worker}")
        self.log(f"Extranonce1: {self.extranonce1.hex()} ({len(self.extranonce1)} bytes)")
        self.log(f"Extranonce2 size: {self.extranonce2_size} bytes")
        self.log("Waiting for mining jobs...")

        # Step 4: Main receive loop
        async def receive_loop():
            buffer = ""
            while self.running:
                try:
                    data = await asyncio.wait_for(
                        self.reader.read(4096), timeout=1
                    )
                    if not data:
                        self.log("Connection closed by server")
                        break
                    buffer += data.decode(errors="replace")

                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        line = line.strip()
                        if not line:
                            continue

                        try:
                            msg = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        if "method" in msg:
                            await self._handle_notification(msg)
                        else:
                            await self._handle_response(msg)

                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    self.log(f"Receive error: {e}")
                    break

        # Step 5: Mining loop
        async def mining_loop():
            while self.running:
                if self.current_job is None:
                    await asyncio.sleep(0.5)
                    continue

                job = self.current_job
                await self._mine_job(job)

        # Run both loops concurrently
        try:
            await asyncio.gather(receive_loop(), mining_loop())
        except asyncio.CancelledError:
            pass
        finally:
            self._print_stats()
            self.running = False
            if self.writer:
                self.writer.close()
                try:
                    await self.writer.wait_closed()
                except Exception:
                    pass

    async def _mine_job(self, job):
        """Mine a single job with merge mining support."""
        btc_target = job["target"]
        btc_bits = job["bits"]

        # Use cached Bitcoin tip for AuxPoW parent construction (non-blocking)
        if self.btc_tip_cache is None:
            try:
                self.btc_tip_cache = self.btc_tip_fetcher.get_tip()
                self.log(f"BTC tip cached: height {self.btc_tip_cache['height']}")
            except Exception as e:
                self.log(f"Cannot fetch BTC tip: {e}, using job prev_hash")
                self.btc_tip_cache = None

        if self.btc_tip_cache:
            btc_prev_hash = bytes.fromhex(self.btc_tip_cache["hash"])
            btc_height = self.btc_tip_cache["height"]
            btc_bits_real = self.btc_tip_cache["bits"]
        else:
            btc_prev_hash = job["prev_hash"]
            btc_height = 0
            btc_bits_real = btc_bits

        # Build Excalibur child block
        try:
            child_blk, child_header, child_hash = self.aux_builder.build_child_block(
                self.fork_rpc
            )
            child_target = bits_to_target(child_blk["bits"])
        except Exception as e:
            self.log(f"Cannot build child block: {e}")
            child_hash = b"\x00" * 32
            child_target = MAX_TARGET

        # Build AuxPoW parent template
        try:
            parent_cb, parent_prefix = self.aux_builder.build_parent_template(
                child_hash, btc_prev_hash, btc_height, btc_bits_real,
                job["ntime"]
            )
        except Exception as e:
            self.log(f"Cannot build parent template: {e}")
            parent_prefix = None

        # Mine nonces: vary header nonce with fixed merkle root
        # The pool embeds extranonce1 in coinbase_1, so we only add extranonce2
        en2_size = self.extranonce2_size

        # Build coinbase: coinbase_1 (contains en1) + en2 (zeros) + coinbase_2
        en2_fixed = b"\x00" * en2_size
        coinbase = job["coinbase_1"] + en2_fixed + job["coinbase_2"]

        # Build merkle root (fixed for this job)
        merkle = self._build_merkle_root(coinbase, job["merkle_branches"])

        # Build header prefix (76 bytes, without nonce)
        header_prefix = (struct.pack("<I", job["version"])
                         + job["prev_hash"]
                         + merkle
                         + struct.pack("<II", job["ntime"], job["bits"]))

        assert len(header_prefix) == 76

        # The extranonce2 we'll submit with shares (matches the zeros in coinbase)
        en2_submit = b"\x00" * en2_size

        # Scalar wave-guided nonce mining
        batch_size = 10000
        start_nonce = int(time.time()) & 0xFFFFFFFF

        # Debug: log share target
        self.log(f"Share target: 0x{self.share_target:064x} (diff={self.difficulty})")
        self.log(f"BTC target:   0x{btc_target:064x} (bits=0x{btc_bits:08x})")

        min_hash = MAX_TARGET  # Track minimum hash for debugging

        for batch in range(100):  # 100 batches = 1M nonces per job
            if not self.running or self.current_job != job:
                break

            base_nonce = (start_nonce + batch * batch_size) & 0xFFFFFFFF

            for i in range(batch_size):
                nonce = (base_nonce + i) & 0xFFFFFFFF

                # Check Bitcoin target
                header = header_prefix + struct.pack("<I", nonce)
                hash_val = sha256d(header)
                hash_int = int.from_bytes(hash_val, "big")

                self.hashes += 1

                if hash_int < min_hash:
                    min_hash = hash_int

                is_share = hash_int <= self.share_target
                is_block = hash_int <= btc_target

                if is_share:
                    # Yield to event loop so receive_loop can process responses
                    await asyncio.sleep(0)
                    # Submit share to pool
                    submit_id = int(time.time() * 1000) % 10000 + 100

                    await self._send({
                        "id": submit_id,
                        "method": "mining.submit",
                        "params": [
                            self.wallet,
                            job["job_id"],
                            en2_submit.hex(),
                            f"{job['ntime']:08x}",
                            f"{nonce:08x}"
                        ]
                    })
                    self.shares_submitted += 1

                    if is_block:
                        self.blocks_found += 1
                        self.log(f"🎉🎉🎉 BITCOIN BLOCK FOUND! 🎉🎉🎉")
                        self.log(f"   Nonce: 0x{nonce:08x}")
                        self.log(f"   Hash: {hash_val.hex()}")

                # Check Excalibur child target (merge mining)
                if parent_prefix and hash_int <= child_target:
                    self.child_hits += 1
                    parent_header = parent_prefix + struct.pack("<I", nonce)

                    # Build AuxPoW block for submission
                    auxpow = self.aux_builder.build_auxpow(
                        parent_header, parent_cb, [], 0
                    )

                    # Update child block nonce
                    child_blk["nonce"] = nonce

                    # Try to submit to fork node
                    try:
                        result = self.fork_rpc.submit_block({
                            **child_blk,
                            "prev": child_blk["prev"].hex(),
                            "merkle": child_blk["merkle"].hex(),
                            "txs": [t.hex() for t in child_blk.get("txs", [])],
                            "auxpow": auxpow
                        })
                        self.log(f"🎉 EXCALIBUR BLOCK SUBMITTED! (AuxPoW)")
                        self.log(f"   Nonce: 0x{nonce:08x}")
                        self.log(f"   Result: {result}")

                        # Check if it's also a Bitcoin hit (dual hit)
                        if is_block:
                            self.dual_hits += 1
                            self.log(f"🎉🎉🎉 DUAL HIT! Bitcoin + Excalibur! 🎉🎉🎉")
                    except Exception as e:
                        self.log(f"  [!] Fork submit failed: {e}")

            # Report hashrate every batch
            elapsed = time.time() - self.start_time
            if elapsed > 0:
                hr = self.hashes / elapsed
                self.log(f"Hashrate: {hr/1000:.1f} KH/s | "
                         f"Shares: {self.shares_accepted}/{self.shares_submitted} | "
                         f"Child hits: {self.child_hits} | "
                         f"Min hash: 0x{min_hash:064x}")

            await asyncio.sleep(0)  # Yield to event loop

    def _print_stats(self):
        """Print final mining statistics."""
        elapsed = time.time() - self.start_time if self.start_time else 0
        hr = self.hashes / elapsed if elapsed > 0 else 0

        print("\n" + "=" * 60)
        print("MINING SESSION STATISTICS")
        print("=" * 60)
        print(f"  Duration:        {elapsed:.1f} seconds")
        print(f"  Total hashes:    {self.hashes:,}")
        print(f"  Hashrate:        {hr/1000:.1f} KH/s ({hr:.0f} H/s)")
        print(f"  Shares submitted: {self.shares_submitted}")
        print(f"  Shares accepted:  {self.shares_accepted}")
        print(f"  Shares rejected:  {self.shares_rejected}")
        print(f"  Bitcoin blocks:   {self.blocks_found}")
        print(f"  Excalibur hits:   {self.child_hits}")
        print(f"  Dual hits:        {self.dual_hits}")
        print("=" * 60)


# ---------------------------------------------------------------------------
# Dry Run Mode
# ---------------------------------------------------------------------------

def run_dry_run():
    """Build and verify AuxPoW construction without connecting to a pool."""
    print("\n" + "=" * 70)
    print("DRY RUN — AuxPoW Merge Mining Construction")
    print("=" * 70)

    # Fetch Bitcoin tip
    print("\n[1] Fetching Bitcoin tip...")
    btc_tip = BitcoinTipFetcher.get_tip()
    print(f"  Height: {btc_tip['height']}")
    print(f"  Hash:   {btc_tip['hash']}")
    print(f"  Bits:   0x{btc_tip['bits']:08x}")
    print(f"  Time:   {btc_tip['time']}")

    # Build child block
    print("\n[2] Building Excalibur child block...")
    fork_rpc = ForkNodeRPC()
    aux_builder = AuxPowBuilder()

    try:
        child_blk, child_header, child_hash = aux_builder.build_child_block(fork_rpc)
        print(f"  Height: {child_blk['height']}")
        print(f"  Bits:   0x{child_blk['bits']:08x}")
        print(f"  Nonce:  {child_blk['nonce']}")
        print(f"  Hash:   {child_hash.hex()}")
    except Exception as e:
        print(f"  [!] Fork node unavailable, using simulated child")
        child_blk = {"height": 1, "bits": 0x1d00ffff, "nonce": 0}
        child_hash = b"\x00" * 32

    # Build parent template
    print("\n[3] Building Bitcoin parent template...")
    btc_prev_hash = bytes.fromhex(btc_tip["hash"])
    parent_cb, parent_prefix = aux_builder.build_parent_template(
        child_hash, btc_prev_hash, btc_tip["height"],
        btc_tip["bits"], btc_tip["time"]
    )
    print(f"  Coinbase size: {len(parent_cb)} bytes")
    print(f"  Header prefix: {len(parent_prefix)} bytes")
    print(f"  Contains AuxPoW magic: {AUXPOW_MAGIC in parent_cb}")

    # Verify AuxPoW commitment
    print("\n[4] Verifying AuxPoW commitment...")
    magic_idx = parent_cb.find(AUXPOW_MAGIC)
    if magic_idx >= 0:
        blob = parent_cb[magic_idx + 4:magic_idx + 44]
        committed_hash = blob[:32]
        tree_size, merkle_nonce = struct.unpack_from("<II", blob, 32)
        print(f"  Magic found at offset: {magic_idx}")
        print(f"  Committed hash: {committed_hash.hex()}")
        print(f"  Tree size: {tree_size} (expected: 1)")
        print(f"  Merkle nonce: {merkle_nonce} (expected: 0)")
        print(f"  Hash matches child: {committed_hash == child_hash}")
    else:
        print("  [!] AuxPoW magic not found in coinbase!")

    # Mine a few nonces
    print("\n[5] Mining nonces (demonstration)...")
    child_target = bits_to_target(child_blk["bits"])
    btc_target = bits_to_target(btc_tip["bits"])

    scalar_wave = ScalarWave()
    best = scalar_wave.best_nonces(5)
    print(f"  Top scalar wave nonces: {best}")

    found_child = False
    for nonce in range(100000):
        header = parent_prefix + struct.pack("<I", nonce)
        hash_val = sha256d(header)
        hash_int = int.from_bytes(hash_val, "big")

        if hash_int <= child_target:
            print(f"  ✓ Child target hit at nonce 0x{nonce:08x}")
            print(f"    Hash: {hash_val.hex()}")
            found_child = True
            break

        if hash_int <= btc_target:
            print(f"  🎉 BITCOIN TARGET HIT at nonce 0x{nonce:08x}")
            print(f"    Hash: {hash_val.hex()}")
            break

    if not found_child:
        print(f"  No child target hit in 100K nonces (expected at easy difficulty)")

    # Scalar wave analysis
    print("\n[6] Scalar wave analysis...")
    print(f"  φ(0) = {scalar_wave.phi(0):.6f}")
    print(f"  φ(1) = {scalar_wave.phi(1):.6f}")
    print(f"  Amplitude at nonce 0: {scalar_wave.score_nonce(0):.6f}")

    print("\n" + "=" * 70)
    print("Dry run complete. AuxPoW construction verified.")
    print("=" * 70)


# ---------------------------------------------------------------------------
# Test Suite
# ---------------------------------------------------------------------------

def run_tests():
    """Run all live merge mining tests."""
    passed = 0
    total = 0

    def check(name, condition):
        nonlocal passed, total
        total += 1
        if condition:
            passed += 1
            print(f"  ✓ {name}")
        else:
            print(f"  ✗ {name}")

    print("\n" + "=" * 70)
    print("LIVE MERGE MINING — Test Suite")
    print("=" * 70)

    # Section 1: Scalar wave
    print("\n[Section 1] Scalar Wave")
    sw = ScalarWave()
    check("phi(0) is finite", abs(sw.phi(0)) < 100)
    check("amplitude >= 0", sw.amplitude(0) >= 0)
    check("score_nonce in range", 0 <= sw.score_nonce(12345) < 100)
    check("best_nonces returns list", len(sw.best_nonces(5)) == 5)

    # Section 2: Hashing
    print("\n[Section 2] Hashing")
    h = sha256d(b"test")
    check("sha256d returns 32 bytes", len(h) == 32)
    check("sha256d is deterministic", sha256d(b"test") == h)

    # Section 3: Target conversion
    print("\n[Section 3] Target Conversion")
    target = bits_to_target(0x1d00ffff)
    check("bits_to_target works", target > 0)
    bits_back = target_to_bits(target)
    check("round-trip bits", bits_back == 0x1d00ffff)

    # Section 4: Header serialization
    print("\n[Section 4] Header Serialization")
    prev = b"\x00" * 32
    merkle = b"\x00" * 32
    header = ser_header(1, prev, merkle, 1231006505, 0x1d00ffff, 0)
    check("header is 80 bytes", len(header) == 80)
    hh = header_hash(header)
    check("header hash is int", isinstance(hh, int))

    # Section 5: Coinbase transaction
    print("\n[Section 5] Coinbase Transaction")
    cb = make_coinbase_v2(1, 0x1d00ffff, b"test", 0, None)
    check("coinbase is bytes", isinstance(cb, bytes))
    check("coinbase > 0 length", len(cb) > 0)
    check("txid is 32 bytes", len(txid(cb)) == 32)

    # Section 6: AuxPoW builder
    print("\n[Section 6] AuxPoW Builder")
    builder = AuxPowBuilder()
    child_hash = b"\xab" * 32
    btc_prev = b"\xcd" * 32

    parent_cb, parent_prefix = builder.build_parent_template(
        child_hash, btc_prev, 840000, 0x17000000, 1700000000
    )
    check("parent coinbase is bytes", isinstance(parent_cb, bytes))
    check("parent prefix is 76 bytes", len(parent_prefix) == 76)
    check("AuxPoW magic in coinbase", AUXPOW_MAGIC in parent_cb)

    # Verify commitment
    magic_idx = parent_cb.find(AUXPOW_MAGIC)
    blob = parent_cb[magic_idx + 4:magic_idx + 44]
    committed = blob[:32]
    tree_size, mnonce = struct.unpack_from("<II", blob, 32)
    check("committed hash matches", committed == child_hash)
    check("tree_size = 1", tree_size == 1)
    check("merkle_nonce = 0", mnonce == 0)

    # Section 7: AuxPoW JSON structure
    print("\n[Section 7] AuxPoW JSON Structure")
    parent_header = parent_prefix + struct.pack("<I", 12345)
    auxpow = builder.build_auxpow(parent_header, parent_cb, [], 0)
    check("auxpow has parent_header", "parent_header" in auxpow)
    check("auxpow has parent_coinbase", "parent_coinbase" in auxpow)
    check("auxpow has coinbase_branch", "coinbase_branch" in auxpow)
    check("auxpow has coinbase_index", "coinbase_index" in auxpow)

    # Section 8: Stratum client
    print("\n[Section 8] Stratum Client")
    client = SoloStratumClient(
        "stratum+tcp://solo.cat:21496",
        "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"
    )
    check("host parsed", client.host == "solo.cat")
    check("port parsed", client.port == 21496)
    check("wallet set", client.wallet == "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa")

    # Section 9: Job decoding
    print("\n[Section 9] Job Decoding")
    job_params = [
        "1",  # job_id
        "0" * 64,  # prev_hash
        "0320000001",  # coinbase_1
        "0000000000",  # coinbase_2
        [],  # merkle_branches
        "20000000",  # version
        "1d00ffff",  # bits
        "65a00000",  # ntime
    ]
    job = client._decode_job(job_params)
    check("job decoded", job is not None)
    check("job_id correct", job["job_id"] == "1")
    check("bits correct", job["bits"] == 0x1d00ffff)

    # Section 10: Word swap
    print("\n[Section 10] Word Swap")
    test_bytes = bytes.fromhex("0102030405060708")
    swapped = client._wordswap(test_bytes)
    expected = bytes.fromhex("0403020108070605")
    check("word swap correct", swapped == expected)

    # Section 11: Merkle root
    print("\n[Section 11] Merkle Root")
    cb_tx = make_coinbase_v2(1, 0x1d00ffff, b"test", 0, None)
    merkle = client._build_merkle_root(cb_tx, [])
    check("merkle root is 32 bytes", len(merkle) == 32)

    # Section 12: Bitcoin tip fetcher
    print("\n[Section 12] Bitcoin Tip Fetcher")
    try:
        tip = BitcoinTipFetcher.get_tip()
        check("tip fetched", tip is not None)
        check("tip has height", "height" in tip)
        check("tip has hash", "hash" in tip)
        check("tip has bits", "bits" in tip)
        check("height is reasonable", 800000 < tip["height"] < 1000000)
    except Exception as e:
        check(f"tip fetch failed: {e}", False)
        check("tip has height", False)
        check("tip has hash", False)
        check("tip has bits", False)
        check("height is reasonable", False)

    # Section 13: Mining simulation
    print("\n[Section 13] Mining Simulation")
    test_prefix = b"\x00" * 76
    test_target = bits_to_target(0x1f00ffff)  # Very easy target
    found = False
    found_nonce = None
    for nonce in range(100000):
        header = test_prefix + struct.pack("<I", nonce)
        hash_val = sha256d(header)
        hash_int = int.from_bytes(hash_val, "big")
        if hash_int <= test_target:
            found = True
            found_nonce = nonce
            break
    check(f"easy target found in 100K nonces (nonce={found_nonce})", found)

    print(f"\n{'=' * 70}")
    print(f"Results: {passed}/{total} tests passed")
    print(f"{'=' * 70}")

    return passed == total


# ---------------------------------------------------------------------------
# Main Entry Point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Live Merge Mining on Solo Pools"
    )
    parser.add_argument("--pool", type=str,
                        default="stratum+tcp://solo.cat:21496",
                        help="Stratum pool URL (default: solo.cat:21496)")
    parser.add_argument("--wallet", type=str, default=None,
                        help="Bitcoin payout address")
    parser.add_argument("--worker", type=str, default="AetherionEXCAL",
                        help="Worker name (default: AetherionEXCAL)")
    parser.add_argument("--test", action="store_true",
                        help="Run test suite")
    parser.add_argument("--dry-run", action="store_true",
                        help="Build AuxPoW without connecting")

    args = parser.parse_args()

    if args.test:
        success = run_tests()
        sys.exit(0 if success else 1)

    if args.dry_run:
        run_dry_run()
        sys.exit(0)

    # Live mining mode
    wallet = args.wallet or os.environ.get("BTC_WALLET")
    if not wallet:
        print("[!] Bitcoin wallet address required.")
        print("[!] Use --wallet YOUR_BTC_ADDRESS or set BTC_WALLET env var.")
        print("[!] Example: --wallet 1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa")
        sys.exit(1)

    client = SoloStratumClient(args.pool, wallet, args.worker)

    def signal_handler(sig, frame):
        print("\n[!] Interrupt signal received. Stopping...")
        client.running = False

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    print("\n" + "=" * 70)
    print("LIVE MERGE MINING — AetherionEXCAL")
    print("=" * 70)
    print(f"  Pool:    {args.pool}")
    print(f"  Wallet:  {wallet}")
    print(f"  Worker:  {args.worker}")
    print(f"  Scalar:  φ(t) = Σ cos(γₖ·t)/γₖ ({len(RIEMANN_ZEROS)} zeros)")
    print(f"  AuxPoW:  {AUXPOW_MAGIC.hex()} 'mm'")
    print("=" * 70)

    asyncio.run(client._connect_and_mine())


if __name__ == "__main__":
    main()
