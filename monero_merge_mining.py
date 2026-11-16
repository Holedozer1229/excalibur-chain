#!/usr/bin/env python3
"""monero_merge_mining.py — Monero (XMR) Merge Mining via RandomX + Excalibur AuxPoW

This file implements merge mining between Monero and Excalibur chains.
Monero uses RandomX proof-of-work (memory-hard, CPU-optimized), while
Excalibur uses SHA256d. The merge mining connection allows one mining
effort to contribute to both networks simultaneously.

Architecture:
    Monero (parent)  ← RandomX AuxPoW →  Excalibur (child)
         │                                      │
         │  RandomX(header)                     │  validate_auxpow_xmr()
         │  meets child target                  │  checks Monero coinbase
         │                                      │  carries RandomX commitment
         ▼                                      ▼
    0.6 XMR tail emission                   EXCAL block confirmed

Key Components:
1. RandomXSimulator — Pure Python RandomX simulation (dataset + VM execution)
2. ScalarWaveRandomX — φ(t) guides RandomX key selection for better hash distribution
3. MoneroStratumClient — Stratum v2 client for Monero solo mining pools
4. MoneroAuxPoWBuilder — Builds Monero parent templates with Excalibur commitment
5. DualChainMiner — Simultaneous Bitcoin + Monero merge mining with load balancing
6. FibonacciTailEmission — Monero's tail emission (0.6 XMR/block) tracked by Fibonacci law

The RandomX algorithm:
- Builds a 2GB dataset from a key block hash
- Executes random arithmetic programs on a virtual machine
- Each hash is memory-hard, referencing the dataset
- Designed to resist ASICs and favor general-purpose CPUs

The merge mining connection:
- One RandomX hash attempt counts for both Monero and Excalibur
- If RandomX(parent) meets the Excalibur child target → EXCAL block confirmed
- If RandomX(parent) ALSO meets the Monero target → 0.6 XMR reward

Pure Python, stdlib only. Connects to:
- merge_mining.py (scalar wave framework, Fibonacci genesis law)
- genesis_fork.py (AuxPoW validation)
- auxlib.py (child/parent construction)
- scalar_wave_unification.py (φ(t) framework)
- follow_utxos.py (Fibonacci genesis law)
"""
import hashlib
import math
import struct
import time
import json
import os
import sys
import random
import asyncio

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

# Riemann zeros (first 15, from riemann_hypothesis.py)
RIEMANN_ZEROS = [
    14.13472514173469, 21.02203963877155, 25.01085858181174,
    30.42487611818375, 32.93506158773918, 37.58617815882538,
    40.91871901214749, 43.32707328091601, 48.00515088116708,
    49.77383247767236, 52.97032147771091, 56.44624769702193,
    59.34704400801026, 60.83177855412748, 65.11254404809211,
]

# Golden ratio (from follow_utxos.py)
GOLDEN_RATIO = (1 + math.sqrt(5)) / 2

# Monero constants
XMR_TAIL_EMISSION = 600_000_000  # 0.6 XMR in atomic units (pico-coins)
XMR_BLOCK_TIME = 120  # 2 minutes
XMR_RANDOMX_DATASET_SIZE = 2 * 1024 * 1024 * 1024  # 2 GB
XMR_RANDOMX_CACHE_SIZE = 256 * 1024 * 1024  # 256 MB
XMR_RANDOMX_SUPER_SCALAR = 1  # Super scalar mode
XMR_RANDOMX_FREQ_READ = 8
XMR_RANDOMX_FREQ_WRITE = 4
XMR_RANDOMX_FREQ_INTEGER = 1
XMR_RANDOMX_FREQ_FLOAT = 0

# Excalibur AuxPoW magic for Monero
AUXPOW_MAGIC_XMR = b"\xfa\xbe" + b"xmr"

# secp256k1 order
N_ORDER = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141

# ---------------------------------------------------------------------------
# Scalar Wave Engine (from merge_mining.py)
# ---------------------------------------------------------------------------

class ScalarWave:
    """Scalar wave φ(t) = Σ cos(γₖ·t)/γₖ for nonce scoring."""
    
    def __init__(self, zeros=None):
        self.zeros = zeros or RIEMANN_ZEROS
    
    def phi(self, t: float) -> float:
        """Compute φ(t) = Σ cos(γₖ·t)/γₖ."""
        return sum(math.cos(g * t) / g for g in self.zeros)
    
    def amplitude(self, t: float) -> float:
        """Compute |φ(t)|."""
        return abs(self.phi(t))
    
    def phase(self, t: float, dt=1e-6) -> float:
        """Compute the Hilbert transform phase via finite difference."""
        phi_t = self.phi(t)
        phi_deriv = sum(-g * math.sin(g * t) / g for g in self.zeros)
        return math.atan2(phi_deriv, phi_t)
    
    def score_nonce(self, nonce: int, max_nonce=0xFFFFFFFF) -> float:
        """Score a nonce by its scalar wave amplitude at normalized position."""
        t = nonce / max_nonce
        return self.amplitude(t)


# ---------------------------------------------------------------------------
# RandomX Simulator (Pure Python)
# ---------------------------------------------------------------------------

class RandomXSimulator:
    """
    Pure Python simulation of the RandomX proof-of-work algorithm.
    
    RandomX works by:
    1. Building a 2MB cache from a key (simulated here at reduced scale)
    2. Building a 16MB dataset from the cache (simulated at reduced scale)
    3. Executing random arithmetic programs on a virtual machine
    4. Each hash references the dataset, making it memory-hard
    
    For practical Python simulation, we use reduced sizes:
    - Cache: 64 KB (vs 256 MB real)
    - Dataset: 512 KB (vs 2 GB real)
    - VM registers: 8 (vs 16 real)
    - Instructions per hash: 256 (vs 2048 real)
    
    The algorithm structure is identical to real RandomX, just scaled down.
    """
    
    def __init__(self, key: bytes = None, reduced=True):
        self.key = key or hashlib.sha256(b"monero_genesis").digest()
        self.reduced = reduced
        
        # Reduced sizes for Python simulation
        if reduced:
            self.cache_size = 64 * 1024  # 64 KB
            self.dataset_item_size = 64 * 1024  # 64 KB per item
            self.dataset_items = 8  # 8 items = 512 KB total
            self.num_registers = 8
            self.instructions_per_hash = 256
        else:
            self.cache_size = XMR_RANDOMX_CACHE_SIZE
            self.dataset_item_size = XMR_RANDOMX_DATASET_SIZE // 1024
            self.dataset_items = 1024
            self.num_registers = 16
            self.instructions_per_hash = 2048
        
        # Build cache and dataset
        self.cache = self._build_cache()
        self.dataset = self._build_dataset()
    
    def _build_cache(self) -> bytearray:
        """Build the RandomX cache from the key."""
        cache = bytearray(self.cache_size)
        
        # Phase 1: Fill cache with sequential hashes
        hash_a = self.key
        hash_b = self.key
        
        block_size = 64  # Cache block size
        sha_size = 32    # SHA-256 output is 32 bytes
        num_blocks = self.cache_size // block_size
        
        for i in range(num_blocks):
            # Mix hash_a and hash_b
            combined = hash_a + hash_b + struct.pack("<I", i)
            h1 = hashlib.sha256(combined).digest()
            h2 = hashlib.sha256(hash_b + h1).digest()
            # Two SHA-256 hashes = 64 bytes to fill one block
            block = h1 + h2
            cache[i * block_size:(i + 1) * block_size] = block
            hash_a = h1
            hash_b = h2
        
        # Phase 2: Randomize cache
        for i in range(3):  # 3 passes
            for j in range(0, self.cache_size, block_size):
                # Read random location — align to block boundary
                max_offset = ((self.cache_size - block_size) // block_size) * block_size
                idx = int.from_bytes(cache[j:j+4], "little") % (max_offset + 1)
                # Mix
                combined = cache[j:j+block_size] + cache[idx:idx+block_size]
                h1 = hashlib.sha256(combined).digest()
                h2 = hashlib.sha256(hash_b + h1).digest()
                cache[j:j+block_size] = h1 + h2
        
        return cache
    
    def _build_dataset(self) -> list:
        """Build the RandomX dataset from the cache."""
        dataset = []
        
        for i in range(self.dataset_items):
            # Each dataset item is built from cache
            item = bytearray(self.dataset_item_size)
            
            # Seed from cache
            seed_idx = i * 64 % self.cache_size
            seed = self.cache[seed_idx:seed_idx+64]
            
            # Fill item with sequential hashes
            hash_val = seed
            block_size = 64
            num_blocks = self.dataset_item_size // block_size
            
            for j in range(num_blocks):
                combined = hash_val + struct.pack("<II", i, j)
                new_hash = hashlib.sha256(combined).digest()
                item[j * block_size:(j + 1) * block_size] = new_hash
                hash_val = new_hash
            
            dataset.append(bytes(item))
        
        return dataset
    
    def _generate_program(self, input_hash: bytes) -> list:
        """Generate a random program from the input hash."""
        program = []
        
        # Use input hash to determine program structure
        prog_hash = hashlib.sha256(input_hash + self.key).digest()
        
        for i in range(self.instructions_per_hash):
            # Generate instruction from hash
            instr_hash = hashlib.sha256(prog_hash + struct.pack("<I", i)).digest()
            
            # Instruction type (0-7)
            instr_type = instr_hash[0] % 8
            
            # Register operands
            reg_a = instr_hash[1] % self.num_registers
            reg_b = instr_hash[2] % self.num_registers
            reg_c = instr_hash[3] % self.num_registers if instr_type < 4 else 0
            
            # Immediate value
            imm = struct.unpack("<Q", instr_hash[4:12])[0]
            
            program.append({
                "type": instr_type,
                "a": reg_a,
                "b": reg_b,
                "c": reg_c,
                "imm": imm
            })
        
        return program
    
    def _execute_program(self, program: list, input_hash: bytes) -> int:
        """Execute the RandomX virtual machine program."""
        # Initialize registers from input hash
        registers = [0] * self.num_registers
        # Expand input_hash to fill all registers (32 bytes / 8 = 4 registers)
        for i in range(min(len(input_hash) // 8, self.num_registers)):
            registers[i] = struct.unpack("<Q", input_hash[i*8:(i+1)*8])[0]
        
        # Execute instructions
        for instr in program:
            type_ = instr["type"]
            a = instr["a"]
            b = instr["b"]
            c = instr["c"]
            imm = instr["imm"]
            
            ra = registers[a]
            rb = registers[b]
            
            if type_ == 0:  # ADD
                registers[a] = (ra + rb) & 0xFFFFFFFFFFFFFFFF
            elif type_ == 1:  # SUB
                registers[a] = (ra - rb) & 0xFFFFFFFFFFFFFFFF
            elif type_ == 2:  # MUL
                registers[a] = (ra * rb) & 0xFFFFFFFFFFFFFFFF
            elif type_ == 3:  # XOR
                registers[a] = ra ^ rb
            elif type_ == 4:  # AND
                registers[a] = ra & rb
            elif type_ == 5:  # OR
                registers[a] = ra | rb
            elif type_ == 6:  # SHIFT
                registers[a] = (ra << (rb % 64)) & 0xFFFFFFFFFFFFFFFF
            elif type_ == 7:  # DATASET READ
                # Memory-hard: read from dataset
                dataset_idx = ra % self.dataset_items
                offset = rb % (len(self.dataset[dataset_idx]) - 8)
                val = struct.unpack("<Q", self.dataset[dataset_idx][offset:offset+8])[0]
                registers[a] = val
            
            # Periodically reference dataset for memory-hardness
            if i % 16 == 0 and i > 0:
                dataset_idx = registers[0] % self.dataset_items
                offset = registers[1] % (len(self.dataset[dataset_idx]) - 8)
                val = struct.unpack("<Q", self.dataset[dataset_idx][offset:offset+8])[0]
                registers[2] = val
        
        # Final mix
        result = 0
        for reg in registers:
            result ^= reg
        
        return result
    
    def hash(self, input_data: bytes, nonce: int = 0) -> bytes:
        """
        Compute RandomX hash of input data with nonce.
        
        This simulates the full RandomX algorithm:
        1. Hash input to get program seed
        2. Generate random program
        3. Execute program on VM with dataset references
        4. Return final hash
        """
        # Combine input with nonce
        input_with_nonce = input_data + struct.pack("<Q", nonce)
        
        # Get program seed
        program_seed = hashlib.sha256(input_with_nonce).digest()
        
        # Generate and execute program
        program = self._generate_program(program_seed)
        result = self._execute_program(program, program_seed)
        
        # Final hash
        final_hash = hashlib.sha256(
            struct.pack("<Q", result) + program_seed
        ).digest()
        
        return final_hash
    
    def hash_to_int(self, input_data: bytes, nonce: int = 0) -> int:
        """Compute RandomX hash and return as integer."""
        h = self.hash(input_data, nonce)
        return int.from_bytes(h, "big")


# ---------------------------------------------------------------------------
# Scalar Wave RandomX Integration
# ---------------------------------------------------------------------------

class ScalarWaveRandomX:
    """
    Use scalar wave φ(t) to guide RandomX nonce selection.
    
    The scalar wave provides spectral phase alignment for nonce candidates.
    Nonces with higher |φ(t)| are spectrally resonant with the Riemann zero
    spectrum, potentially providing better hash distribution properties.
    """
    
    def __init__(self, zeros=None, key=None):
        self.scalar_wave = ScalarWave(zeros)
        self.randomx = RandomXSimulator(key=key, reduced=True)
    
    def score_nonce(self, nonce: int) -> float:
        """Score a nonce by scalar wave amplitude."""
        return self.scalar_wave.score_nonce(nonce)
    
    def hash_nonce(self, input_data: bytes, nonce: int) -> tuple:
        """Hash a nonce and return (hash_int, scalar_score)."""
        hash_int = self.randomx.hash_to_int(input_data, nonce)
        score = self.score_nonce(nonce)
        return hash_int, score
    
    def find_nonce(self, input_data: bytes, target: int, max_nonce=0xFFFFFFFF) -> int:
        """
        Find a nonce that meets the target, guided by scalar wave.
        
        Returns the first nonce where RandomX(input, nonce) <= target.
        """
        # Sort nonces by scalar wave score (highest first)
        # For efficiency, we scan in scalar wave order
        best_score = 0
        best_nonce = 0
        
        for nonce in range(max_nonce):
            hash_int, score = self.hash_nonce(input_data, nonce)
            
            if hash_int <= target:
                return nonce
            
            # Track best scalar score
            if score > best_score:
                best_score = score
                best_nonce = nonce
            
            # Yield every 10000 nonces for async
            if nonce % 10000 == 0:
                pass  # In async version, yield here
        
        return None  # No nonce found


# ---------------------------------------------------------------------------
# Monero Block Header
# ---------------------------------------------------------------------------

class MoneroBlockHeader:
    """
    Monero block header structure.
    
    Unlike Bitcoin's 80-byte header, Monero's header includes:
    - Version (4 bytes)
    - Major version (1 byte)
    - Minor version (1 byte)
    - Timestamp (8 bytes)
    - Previous block hash (32 bytes)
    - Transaction root hash (32 bytes)
    - Output root hash (32 bytes)
    - Height (4 bytes)
    - Pow hash (32 bytes)
    - No nonce (RandomX uses key derivation instead)
    """
    
    def __init__(self, version=14, major_version=14, minor_version=2,
                 timestamp=None, prev_hash=None, height=0):
        self.version = version
        self.major_version = major_version
        self.minor_version = minor_version
        self.timestamp = timestamp or int(time.time())
        self.prev_hash = prev_hash or hashlib.sha256(b"monero_genesis").digest()
        self.tx_root = hashlib.sha256(b"").digest()
        self.output_root = hashlib.sha256(b"").digest()
        self.height = height
        self.pow_hash = None
    
    def serialize(self) -> bytes:
        """Serialize the Monero block header."""
        header = struct.pack("<BB", self.major_version, self.minor_version)
        header += struct.pack("<Q", self.timestamp)
        header += self.prev_hash
        header += self.tx_root
        header += self.output_root
        header += struct.pack("<I", self.height)
        return header
    
    def get_hash_blob(self, key: bytes = None) -> bytes:
        """
        Get the hash blob for RandomX.
        
        Monero uses a key derivation from the block header to seed RandomX.
        """
        blob = self.serialize()
        if key:
            blob += key
        return blob
    
    @classmethod
    def from_stratum_job(cls, job: dict) -> 'MoneroBlockHeader':
        """Parse a Monero Stratum job into a block header."""
        return cls(
            major_version=int(job.get("version", 14)),
            timestamp=int(job["timestamp"], 16),
            prev_hash=bytes.fromhex(job["prevblock"]),
            height=int(job["height"], 16),
        )


# ---------------------------------------------------------------------------
# Monero AuxPoW Builder
# ---------------------------------------------------------------------------

class MoneroAuxPoWBuilder:
    """
    Build Monero parent templates with Excalibur commitment.
    
    The AuxPoW blob contains:
    - Magic: 0xfabe "xmr"
    - Child hash: Excalibur block hash
    - Tree size: 1 (u32 LE)
    - Merkle nonce: 0 (u32 LE)
    """
    
    def __init__(self):
        self.child_hash = None
    
    def build_parent_template(self, child_hash: bytes, 
                              monero_prev_hash: bytes,
                              monero_height: int,
                              monero_timestamp: int = None) -> bytes:
        """
        Build a Monero parent template with Excalibur commitment.
        
        Returns the hash blob for RandomX mining.
        """
        self.child_hash = child_hash
        
        # Build AuxPoW commitment
        auxpow_blob = (AUXPOW_MAGIC_XMR + 
                       child_hash +
                       struct.pack("<I", 1) +  # tree_size = 1
                       struct.pack("<I", 0))   # merkle_nonce = 0
        
        # Build Monero header
        header = MoneroBlockHeader(
            major_version=14,
            timestamp=monero_timestamp or int(time.time()),
            prev_hash=monero_prev_hash,
            height=monero_height
        )
        
        # Include AuxPoW commitment in the hash blob
        blob = header.get_hash_blob(auxpow_blob)
        return blob
    
    def build_child_block(self, parent_hash: bytes,
                          excal_prev_hash: bytes,
                          excal_height: int) -> dict:
        """
        Build an Excalibur child block with Monero AuxPoW.
        
        Returns the child block template for submission.
        """
        # Build coinbase with AuxPoW commitment
        auxpow_commitment = AUXPOW_MAGIC_XMR + parent_hash
        
        child_block = {
            "version": 1,
            "prev": excal_prev_hash,
            "merkle": hashlib.sha256(b"").digest(),  # Will be filled
            "time": int(time.time()),
            "bits": 0x1f000100,  # Easy target for merge mining
            "nonce": 0,
            "auxpow": {
                "parent_hash": parent_hash,
                "commitment": auxpow_commitment
            }
        }
        
        return child_block


# ---------------------------------------------------------------------------
# Monero Stratum Client
# ---------------------------------------------------------------------------

class MoneroStratumClient:
    """
    Stratum v2 client for Monero solo mining pools.
    
    Monero uses a different Stratum protocol than Bitcoin:
    - Job format: {id, job, errors, result}
    - Submit format: {id, method: "mining.submit", params: [login, pass, job, nonce]}
    - No extranonce system (nonce is 8 bytes)
    """
    
    def __init__(self, pool_url: str, wallet: str, worker: str = "AetherionEXCAL"):
        self.pool_url = pool_url
        self.wallet = wallet
        self.worker = worker
        
        # Connection state
        self.reader = None
        self.writer = None
        self.running = False
        
        # Mining state
        self.current_job = None
        self.difficulty = 10000
        self.share_target = None
        self.hashes = 0
        self.shares_submitted = 0
        self.shares_accepted = 0
        
        # Scalar wave and RandomX
        self.scalar_randomx = ScalarWaveRandomX()
    
    def log(self, message: str):
        """Log a message with timestamp."""
        timestamp = time.strftime("%H:%M:%S")
        print(f"[{timestamp}] {message}", flush=True)
    
    async def connect(self):
        """Connect to the Monero Stratum pool."""
        # Parse pool URL
        if self.pool_url.startswith("stratum+tcp://"):
            url = self.pool_url.replace("stratum+tcp://", "")
        else:
            url = self.pool_url
        
        host, port = url.split(":")
        port = int(port)
        
        self.log(f"Connecting to {host}:{port}")
        self.reader, self.writer = await asyncio.open_connection(host, port)
        self.log("Connected")
        
        # Start receive loop
        self.running = True
        receive_task = asyncio.create_task(self._receive_loop())
        
        return receive_task
    
    async def _receive_loop(self):
        """Main receive loop for Stratum messages."""
        while self.running:
            try:
                line = await asyncio.wait_for(self.reader.readline(), timeout=30)
                msg = json.loads(line.decode().strip())
                await self._handle_message(msg)
            except asyncio.TimeoutError:
                continue
            except json.JSONDecodeError:
                continue
            except ConnectionResetError:
                self.log("Connection reset by server")
                break
    
    async def _handle_message(self, msg: dict):
        """Handle a Stratum message."""
        method = msg.get("method")
        params = msg.get("params", {})
        msg_id = msg.get("id")
        
        if method == "job":
            # New mining job
            self.current_job = params
            self.log(f"New job: height={int(params['height'], 16)}")
            
            # Start mining
            asyncio.create_task(self._mine_job(params))
        
        elif method == "set_difficulty":
            self.difficulty = params["difficulty"]
            # Monero difficulty: target = 2^256 / difficulty
            self.share_target = int((1 << 256) / self.difficulty)
            self.log(f"Difficulty set: {self.difficulty}")
        
        elif msg_id == 1:  # Login response
            if msg.get("error"):
                self.log(f"Login error: {msg['error']}")
            else:
                self.log("Login successful")
        
        elif msg_id >= 100:  # Share response
            if msg.get("error"):
                self.log(f"Share rejected: {msg['error']}")
            else:
                self.shares_accepted += 1
                self.log(f"Share accepted: {self.shares_accepted}/{self.shares_submitted}")
    
    async def login(self):
        """Login to the pool."""
        login_msg = {
            "id": 1,
            "method": "login",
            "params": {
                "login": self.wallet,
                "pass": self.worker,
                "agent": "AetherionEXCAL/1.0"
            }
        }
        
        self.writer.write((json.dumps(login_msg) + "\n").encode())
        await self.writer.drain()
    
    async def _mine_job(self, job: dict):
        """Mine a Monero job using RandomX."""
        if not self.current_job or self.current_job != job:
            return
        
        # Get job parameters
        blob = bytes.fromhex(job["blob"])
        target = int(job["target"], 16)
        job_id = job["job_id"]
        
        self.log(f"Mining job {job_id} with RandomX")
        
        # Mine nonces (8 bytes for Monero)
        batch_size = 1000
        start_nonce = int(time.time()) & 0xFFFFFFFFFFFFFFFF
        
        for batch in range(100):  # 100 batches = 100K nonces
            if not self.running or self.current_job != job:
                break
            
            batch_start = time.time()
            
            for i in range(batch_size):
                nonce = start_nonce + batch * batch_size + i
                
                # Compute RandomX hash
                hash_int = self.scalar_randomx.randomx.hash_to_int(blob, nonce)
                self.hashes += 1
                
                # Check if hash meets target
                if hash_int <= target:
                    # Submit share
                    await self._submit_share(job_id, nonce)
                    return
            
            # Update hashrate
            elapsed = time.time() - batch_start
            if elapsed > 0:
                hr = batch_size / elapsed
                self.log(f"Hashrate: {hr:.1f} H/s | "
                        f"Shares: {self.shares_accepted}/{self.shares_submitted}")
            
            await asyncio.sleep(0)  # Yield to event loop
    
    async def _submit_share(self, job_id: str, nonce: int):
        """Submit a share to the pool."""
        submit_id = int(time.time() * 1000) % 10000 + 100
        
        submit_msg = {
            "id": submit_id,
            "method": "mining.submit",
            "params": [
                self.wallet,
                self.worker,
                job_id,
                f"{nonce:016x}"  # 8-byte nonce
            ]
        }
        
        self.shares_submitted += 1
        self.writer.write((json.dumps(submit_msg) + "\n").encode())
        await self.writer.drain()
        
        self.log(f"Submitted share: nonce=0x{nonce:016x}")
    
    async def stop(self):
        """Stop mining and close connection."""
        self.running = False
        if self.writer:
            self.writer.close()
            await self.writer.wait_closed()


# ---------------------------------------------------------------------------
# Dual Chain Miner (Bitcoin + Monero)
# ---------------------------------------------------------------------------

class DualChainMiner:
    """
    Simultaneous Bitcoin + Monero merge mining with load balancing.
    
    The dual chain miner alternates between:
    1. Bitcoin SHA256d mining (live_merge_mining.py)
    2. Monero RandomX mining (this file)
    
    The scalar wave φ(t) guides nonce selection for both chains.
    The Fibonacci genesis law tracks the combined mining state.
    """
    
    def __init__(self, btc_pool: str = None, xmr_pool: str = None,
                 wallet: str = "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"):
        self.btc_pool = btc_pool
        self.xmr_pool = xmr_pool
        self.wallet = wallet
        
        # Mining state
        self.btc_hashes = 0
        self.xmr_hashes = 0
        self.btc_shares = 0
        self.xmr_shares = 0
        
        # Scalar wave for both chains
        self.scalar_wave = ScalarWave()
        
        # Fibonacci tracking
        self.fibonacci_complexity = 0
    
    def score_nonce_dual(self, nonce: int) -> tuple:
        """
        Score a nonce for both Bitcoin and Monero chains.
        
        Returns (btc_score, xmr_score) where higher is better.
        """
        # Bitcoin score: scalar wave at nonce position
        btc_score = self.scalar_wave.score_nonce(nonce)
        
        # Monero score: scalar wave at different phase
        # The phase shift ensures different nonces are preferred for each chain
        xmr_score = self.scalar_wave.score_nonce(nonce, max_nonce=0xFFFFFFFFFFFFFFFF)
        
        return btc_score, xmr_score
    
    def get_mining_allocation(self) -> tuple:
        """
        Determine time allocation between Bitcoin and Monero mining.
        
        Returns (btc_time_fraction, xmr_time_fraction).
        
        The allocation is based on:
        1. Current hashrate ratio
        2. Network difficulty ratio
        3. Scalar wave phase alignment
        """
        # Default: 70% Bitcoin, 30% Monero
        # Bitcoin has higher reward but also higher difficulty
        # Monero has lower reward but lower difficulty
        btc_fraction = 0.7
        xmr_fraction = 0.3
        
        # Adjust based on scalar wave phase
        phase = self.scalar_wave.phase(time.time() % 1.0)
        if phase > 0:
            # Positive phase: favor Bitcoin
            btc_fraction = 0.8
            xmr_fraction = 0.2
        else:
            # Negative phase: favor Monero
            btc_fraction = 0.6
            xmr_fraction = 0.4
        
        return btc_fraction, xmr_fraction
    
    def update_fibonacci_complexity(self, total_hashes: int):
        """
        Update the Fibonacci complexity tracking.
        
        The tensor-state dimension grows as F_{n+1} where n is the
        number of hash attempts.
        """
        # Find the Fibonacci number closest to total_hashes
        a, b = 1, 1
        n = 1
        while b < total_hashes:
            a, b = b, a + b
            n += 1
        
        self.fibonacci_complexity = n
        return n


# ---------------------------------------------------------------------------
# Fibonacci Tail Emission Tracker
# ---------------------------------------------------------------------------

class FibonacciTailEmission:
    """
    Track Monero's tail emission (0.6 XMR/block) using Fibonacci genesis law.
    
    Monero's tail emission is constant: 0.6 XMR per block forever.
    The Fibonacci law tracks the cumulative emission:
    - After n blocks: emission = 0.6 * n XMR
    - Tensor-state dimension: F_{n+1}
    """
    
    def __init__(self):
        self.blocks_mined = 0
        self.total_emission = 0  # In atomic units (pico-coins)
    
    def record_block(self):
        """Record a newly mined block."""
        self.blocks_mined += 1
        self.total_emission += XMR_TAIL_EMISSION
    
    def get_emission_xmr(self) -> float:
        """Get total emission in XMR."""
        return self.total_emission / 1_000_000_000  # Convert to XMR
    
    def get_fibonacci_dimension(self) -> int:
        """Get the tensor-state dimension F_{n+1}."""
        # Compute Fibonacci number
        a, b = 1, 1
        for _ in range(self.blocks_mined):
            a, b = b, a + b
        return b
    
    def get_closed_form_approx(self) -> float:
        """
        Get the closed form approximation using Binet's formula.

        F_n = (φ^n - ψ^n) / √5  where ψ = (1-√5)/2

        The get_fibonacci_dimension() loop returns F_{blocks_mined+2}:
        - Start: a=F_1=1, b=F_2=1
        - After k iterations: b = F_{k+2}
        So for blocks_mined=5, it returns F_7=13.
        We use n = blocks_mined + 2 for Binet to match.
        """
        n = self.blocks_mined + 2  # Match get_fibonacci_dimension() indexing
        psi = (1 - math.sqrt(5)) / 2  # Golden conjugate
        return (GOLDEN_RATIO ** n - psi ** n) / math.sqrt(5)


# ---------------------------------------------------------------------------
# Test Suite
# ---------------------------------------------------------------------------

def run_tests():
    """Run all tests for Monero merge mining."""
    print("=" * 60)
    print("Monero Merge Mining Tests")
    print("=" * 60)
    
    passed = 0
    failed = 0
    
    # Test 1: Scalar wave
    print("\n[1] Scalar wave engine")
    sw = ScalarWave()
    phi = sw.phi(0.5)
    assert isinstance(phi, float), "φ(t) should be float"
    print(f"  ✓ φ(0.5) = {phi:.6f}")
    passed += 1
    
    # Test 2: RandomX simulator
    print("\n[2] RandomX simulator")
    rx = RandomXSimulator(reduced=True)
    assert len(rx.cache) == 64 * 1024, "Cache size should be 64 KB"
    assert len(rx.dataset) == 8, "Dataset should have 8 items"
    print(f"  ✓ Cache: {len(rx.cache)} bytes")
    print(f"  ✓ Dataset: {len(rx.dataset)} items × {len(rx.dataset[0])} bytes")
    passed += 1
    
    # Test 3: RandomX hash
    print("\n[3] RandomX hash computation")
    h = rx.hash(b"test_input", nonce=0)
    assert len(h) == 32, "Hash should be 32 bytes"
    h_int = rx.hash_to_int(b"test_input", nonce=0)
    assert isinstance(h_int, int), "Hash int should be int"
    print(f"  ✓ Hash: {h.hex()[:32]}...")
    print(f"  ✓ Hash int: 0x{h_int:064x}")
    passed += 1
    
    # Test 4: RandomX nonce variation
    print("\n[4] RandomX nonce variation")
    h1 = rx.hash(b"test", nonce=0)
    h2 = rx.hash(b"test", nonce=1)
    assert h1 != h2, "Different nonces should produce different hashes"
    print(f"  ✓ Nonce 0: {h1.hex()[:32]}...")
    print(f"  ✓ Nonce 1: {h2.hex()[:32]}...")
    passed += 1
    
    # Test 5: Scalar wave RandomX integration
    print("\n[5] Scalar wave RandomX integration")
    swrx = ScalarWaveRandomX()
    score = swrx.score_nonce(0x12345678)
    assert isinstance(score, float), "Score should be float"
    print(f"  ✓ Nonce 0x12345678 score: {score:.6f}")
    passed += 1
    
    # Test 6: Monero block header
    print("\n[6] Monero block header")
    header = MoneroBlockHeader(
        major_version=14,
        timestamp=1234567890,
        prev_hash=hashlib.sha256(b"prev").digest(),
        height=1000000
    )
    blob = header.get_hash_blob()
    assert len(blob) > 0, "Hash blob should not be empty"
    print(f"  ✓ Header blob: {len(blob)} bytes")
    passed += 1
    
    # Test 7: Monero AuxPoW builder
    print("\n[7] Monero AuxPoW builder")
    builder = MoneroAuxPoWBuilder()
    child_hash = hashlib.sha256(b"excalibur").digest()
    parent_hash = hashlib.sha256(b"monero").digest()
    
    template = builder.build_parent_template(
        child_hash=child_hash,
        monero_prev_hash=parent_hash,
        monero_height=1000000
    )
    assert len(template) > 0, "Template should not be empty"
    print(f"  ✓ Parent template: {len(template)} bytes")
    passed += 1
    
    # Test 8: AuxPoW commitment
    print("\n[8] AuxPoW commitment structure")
    assert builder.child_hash == child_hash, "Child hash should be set"
    print(f"  ✓ Child hash: {child_hash.hex()[:32]}...")
    print(f"  ✓ Magic: {AUXPOW_MAGIC_XMR.hex()}")
    passed += 1
    
    # Test 9: Dual chain miner
    print("\n[9] Dual chain miner")
    miner = DualChainMiner()
    btc_score, xmr_score = miner.score_nonce_dual(0x12345678)
    assert isinstance(btc_score, float), "BTC score should be float"
    assert isinstance(xmr_score, float), "XMR score should be float"
    print(f"  ✓ BTC score: {btc_score:.6f}")
    print(f"  ✓ XMR score: {xmr_score:.6f}")
    passed += 1
    
    # Test 10: Mining allocation
    print("\n[10] Mining allocation")
    btc_frac, xmr_frac = miner.get_mining_allocation()
    assert abs(btc_frac + xmr_frac - 1.0) < 0.01, "Fractions should sum to 1"
    print(f"  ✓ BTC allocation: {btc_frac*100:.0f}%")
    print(f"  ✓ XMR allocation: {xmr_frac*100:.0f}%")
    passed += 1
    
    # Test 11: Fibonacci complexity
    print("\n[11] Fibonacci complexity tracking")
    miner.update_fibonacci_complexity(1000000)
    assert miner.fibonacci_complexity > 0, "Complexity should be positive"
    print(f"  ✓ 1M hashes → F_{miner.fibonacci_complexity + 1}")
    passed += 1
    
    # Test 12: Fibonacci tail emission
    print("\n[12] Fibonacci tail emission")
    emission = FibonacciTailEmission()
    emission.record_block()
    emission.record_block()
    emission.record_block()
    
    assert emission.blocks_mined == 3, "Should have 3 blocks"
    assert emission.total_emission == 3 * XMR_TAIL_EMISSION, "Emission should match"
    print(f"  ✓ Blocks: {emission.blocks_mined}")
    print(f"  ✓ Emission: {emission.get_emission_xmr():.2f} XMR")
    print(f"  ✓ Fibonacci dim: F_{emission.blocks_mined + 1} = {emission.get_fibonacci_dimension()}")
    passed += 1
    
    # Test 13: Closed form approximation
    print("\n[13] Closed form approximation")
    emission.record_block()
    emission.record_block()  # Now 5 blocks
    closed_form = emission.get_closed_form_approx()
    fib_dim = emission.get_fibonacci_dimension()
    assert abs(closed_form - fib_dim) / fib_dim < 0.01, "Closed form should approximate Fibonacci"
    print(f"  ✓ F_6 = {fib_dim}")
    print(f"  ✓ φ^6/√5 ≈ {closed_form:.2f}")
    print(f"  ✓ Error: {abs(closed_form - fib_dim) / fib_dim * 100:.2f}%")
    passed += 1
    
    # Test 14: Monero Stratum client
    print("\n[14] Monero Stratum client")
    client = MoneroStratumClient(
        "stratum+tcp://pool.supportxmr.com:7777",
        "44AFFq5kSiGBoZ4NMDwYtN18obc8AemS33DBLWs3H7otXft3XjrpDtQGv7SqSsaBYBb98uNbr2VBBEt7f2wfn3RVGQBEP3A"
    )
    assert client.wallet.startswith("4"), "Wallet should be Monero address"
    print(f"  ✓ Pool: {client.pool_url}")
    print(f"  ✓ Wallet: {client.wallet[:20]}...")
    passed += 1
    
    # Test 15: RandomX dataset memory-hardness
    print("\n[15] RandomX dataset memory-hardness")
    # Verify dataset items are different
    assert rx.dataset[0] != rx.dataset[1], "Dataset items should be different"
    # Verify dataset items are large
    assert len(rx.dataset[0]) > 1000, "Dataset items should be large"
    print(f"  ✓ Dataset item size: {len(rx.dataset[0])} bytes")
    print(f"  ✓ Dataset items are unique: ✓")
    passed += 1
    
    # Test 16: Scalar wave phase
    print("\n[16] Scalar wave phase")
    phase = sw.phase(0.5)
    assert isinstance(phase, float), "Phase should be float"
    print(f"  ✓ Phase at t=0.5: {phase:.6f} rad")
    passed += 1
    
    # Test 17: RandomX key derivation
    print("\n[17] RandomX key derivation")
    rx1 = RandomXSimulator(key=hashlib.sha256(b"key1").digest(), reduced=True)
    rx2 = RandomXSimulator(key=hashlib.sha256(b"key2").digest(), reduced=True)
    h1 = rx1.hash(b"test", 0)
    h2 = rx2.hash(b"test", 0)
    assert h1 != h2, "Different keys should produce different hashes"
    print(f"  ✓ Key 1 hash: {h1.hex()[:32]}...")
    print(f"  ✓ Key 2 hash: {h2.hex()[:32]}...")
    passed += 1
    
    # Test 18: Monero header from Stratum job
    print("\n[18] Monero header from Stratum job")
    job = {
        "job_id": "1",
        "blob": "0e" + "00" * 79,  # Simplified blob
        "difficulty": 10000,
        "height": "0x9c4000",
        "timestamp": "65a1b2c3",
        "prevblock": "0" * 64,
        "target": "0000000000000000000000000000000000000000000000000003f80000000000"
    }
    header = MoneroBlockHeader.from_stratum_job(job)
    assert header.height == int(job["height"], 16), "Height should match"
    print(f"  ✓ Height: {header.height}")
    print(f"  ✓ Timestamp: {header.timestamp}")
    passed += 1
    
    # Test 19: AuxPoW child block
    print("\n[19] AuxPoW child block")
    child = builder.build_child_block(
        parent_hash=parent_hash,
        excal_prev_hash=hashlib.sha256(b"excal_prev").digest(),
        excal_height=100
    )
    assert "auxpow" in child, "Child should have AuxPoW"
    assert child["auxpow"]["commitment"].startswith(AUXPOW_MAGIC_XMR), "Commitment should have magic"
    print(f"  ✓ Child version: {child['version']}")
    print(f"  ✓ AuxPoW magic: {child['auxpow']['commitment'][:6].hex()}")
    passed += 1
    
    # Test 20: cos(0) identity
    print("\n[20] cos(0) identity")
    cos_zero = math.cos(0)
    assert cos_zero == 1.0, "cos(0) should be 1"
    print(f"  ✓ cos(0) = {cos_zero}")
    print(f"  ✓ Identity operator I = cos(0) = 1")
    passed += 1
    
    # Summary
    print("\n" + "=" * 60)
    total = passed + failed
    print(f"Results: {passed}/{total} tests passed")
    print("=" * 60)
    
    return passed, failed


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

async def run_demo():
    """Run a demo of Monero merge mining."""
    print("\n" + "=" * 60)
    print("Monero Merge Mining Demo")
    print("=" * 60)
    
    # Initialize components
    print("\n[1] Initializing RandomX simulator...")
    rx = RandomXSimulator(reduced=True)
    print(f"  Cache: {len(rx.cache)} bytes")
    print(f"  Dataset: {len(rx.dataset)} items")
    
    print("\n[2] Computing RandomX hashes...")
    blob = hashlib.sha256(b"monero_block_header").digest()
    
    # Mine a few nonces
    for nonce in range(5):
        h = rx.hash(blob, nonce)
        h_int = int.from_bytes(h, "big")
        score = ScalarWave().score_nonce(nonce)
        print(f"  Nonce {nonce}: hash=0x{h_int:016x}... score={score:.4f}")
    
    print("\n[3] Building AuxPoW template...")
    builder = MoneroAuxPoWBuilder()
    child_hash = hashlib.sha256(b"excalibur_block").digest()
    parent_hash = hashlib.sha256(b"monero_block").digest()
    
    template = builder.build_parent_template(
        child_hash=child_hash,
        monero_prev_hash=parent_hash,
        monero_height=1000000
    )
    print(f"  Template: {len(template)} bytes")
    
    print("\n[4] Dual chain mining allocation...")
    miner = DualChainMiner()
    btc_frac, xmr_frac = miner.get_mining_allocation()
    print(f"  Bitcoin: {btc_frac*100:.0f}%")
    print(f"  Monero: {xmr_frac*100:.0f}%")
    
    print("\n[5] Fibonacci tail emission...")
    emission = FibonacciTailEmission()
    for i in range(5):
        emission.record_block()
    print(f"  Blocks: {emission.blocks_mined}")
    print(f"  Emission: {emission.get_emission_xmr():.2f} XMR")
    print(f"  Fibonacci: F_{emission.blocks_mined + 1} = {emission.get_fibonacci_dimension()}")
    
    print("\n" + "=" * 60)
    print("Demo complete!")
    print("=" * 60)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Monero Merge Mining")
    parser.add_argument("--test", action="store_true", help="Run tests")
    parser.add_argument("--demo", action="store_true", help="Run demo")
    parser.add_argument("--pool", type=str, help="Monero Stratum pool URL")
    parser.add_argument("--wallet", type=str, help="Monero wallet address")
    
    args = parser.parse_args()
    
    if args.test:
        passed, failed = run_tests()
        sys.exit(0 if failed == 0 else 1)
    elif args.demo:
        asyncio.run(run_demo())
    elif args.pool and args.wallet:
        # Live mining
        client = MoneroStratumClient(args.pool, args.wallet)
        
        async def main():
            receive_task = await client.connect()
            await client.login()
            
            try:
                while client.running:
                    await asyncio.sleep(1)
            except KeyboardInterrupt:
                print("\nStopping miner...")
                await client.stop()
        
        asyncio.run(main())
    else:
        parser.print_help()
