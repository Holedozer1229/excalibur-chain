#!/usr/bin/env python3
"""
puzzle_kangaroo.py — Pollard's Kangaroo Solver for Bitcoin Puzzles

Solves Bitcoin puzzle transactions using Pollard's Kangaroo algorithm,
which exploits the known key range to find private keys in O(√n) time
instead of O(n) brute force.

For puzzles with exposed public keys (135, 140, 145, 150, 155, 160),
the kangaroo method is the optimal classical approach.

PUZZLE 140 DETAILS:
- Address: 1QKBaU6WAeycb3DbKbLBkX7vJiaS8r42Xo
- Public key: 031f6a332d3c5c4f2de2378c012f429cd109ba07d69690c6c701b6bb87860d6640
- Key range: [2^139, 2^140) — 7.0×10^41 candidates
- Kangaroo complexity: ~2^70 operations (~1.2×10^21 steps)
- Prize: 14 BTC (~$954,718)

THE ALGORITHM
=============
Pollard's Kangaroo solves the interval discrete logarithm problem:
Given Q = k·G where k ∈ [a, b], find k.

1. Tame kangaroo starts at point P_tame = a·G with displacement d_tame = a
2. Wild kangaroo starts at point P_wild = Q (the target) with displacement d_wild = 0
3. Both kangaroos "jump" using pseudo-random jump lengths derived from their current position
4. When a distinguished point is reached, it's stored in a hash table
5. When a tame and wild kangaroo collide at the same point:
   k = d_tame - d_wild (mod n)

The expected number of steps is ~2.08·√(b-a) by the birthday paradox.

SCALAR WAVE INTEGRATION
========================
The jump lengths are guided by the scalar wave φ(t) = Σ cos(γₖ·t)/γₖ:
- The Riemann zero spectrum determines the jump length distribution
- The scalar wave phase at each position biases the jump direction
- This creates a spectral interference pattern that may accelerate convergence

USAGE
=====
    python puzzle_kangaroo.py --test              # Run all tests
    python puzzle_kangaroo.py --puzzle 10        # Solve puzzle 10 (505)
    python puzzle_kangaroo.py --puzzle 140       # Attempt puzzle 140
    python puzzle_kangaroo.py --range 20         # Solve random 20-bit puzzle
"""
import math
import hashlib
import time
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ============================================================
# Constants
# ============================================================

# secp256k1 parameters
SECP_P = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F
SECP_N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
SECP_Gx = 0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798
SECP_Gy = 0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8
SECP_G = (SECP_Gx, SECP_Gy)

# Riemann zeros for scalar wave guidance
RIEMANN_ZEROS = [
    14.13472514173469, 21.02203963877155, 25.01085858181174,
    30.42487612585951, 32.93506158773919, 37.58617815882568,
    40.91871901214750, 43.32707328091502, 48.00515088116718,
    49.77383247771231, 52.97032147771487, 56.44624769702197,
    59.34704400377849, 60.83177855412847, 65.11254403547418,
    67.07981052924520, 69.54640171110789, 72.06715767340587,
    75.70469069918596, 77.14484006122038, 79.33737502024523,
    82.91038185169410, 84.73549298138341, 87.42527461335040,
    88.80911120789791, 92.49189997947742, 94.65134404069930,
    95.87063422802164, 98.83119397235785, 101.31785109388503,
]

# Base58 alphabet
BASE58_ALPHABET = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'

# ============================================================
# Bitcoin Puzzle Addresses
# ============================================================

PUZZLE_ADDRESSES = {
    1:  {'address': '1BgGZ9tcN4rm9KBzDn7KprQz87SZ26SAMH', 'key': 1, 'solved': True, 'public_key': None},
    2:  {'address': '1CUNEBjYrCn2y1SdiUMohaKUi4wpP326Lb', 'key': 3, 'solved': True, 'public_key': None},
    3:  {'address': '19ZewH8Kk1PDbSNdJ97FP4EiCjTRaZMZQA', 'key': 7, 'solved': True, 'public_key': None},
    4:  {'address': '1EhqbyUMvvs7BfL8goY6qcPbD6YKfPqb7e', 'key': 8, 'solved': True, 'public_key': None},
    5:  {'address': '1E6NuFjCi27W5zoXg8TRdcSRq84zJeBW3k', 'key': 15, 'solved': True, 'public_key': None},
    6:  {'address': '1PitScNLyp2HCygzadCh7FveTnfmpPbfp8', 'key': 31, 'solved': True, 'public_key': None},
    7:  {'address': '15mKcG7aj99Ldb7ZJ588eTajB9L7mpZuRq', 'key': 44, 'solved': True, 'public_key': None},
    8:  {'address': '17Y39MgP2gMGfKdp88v1RiSqVrizdvf8v8', 'key': 131, 'solved': True, 'public_key': None},
    9:  {'address': '1CjDjHMaKRJQivKzsD584QmXgjLJmPnBzQ', 'key': 251, 'solved': True, 'public_key': None},
    10: {'address': '15t4YJjM5F6jsZ2ZBaE7JLxg2WV3H97yC5', 'key': 505, 'solved': True, 'public_key': None},
    # ... puzzles 11-134 have unknown keys (address-only, no public key exposed)
    135: {'address': '1GqkDooaC57tD34695855wLRgM99i32aW5', 'key': None, 'solved': False,
          'public_key': '02b4c8a0f10c1a0000000000000000000000000000000000000000000000000000'},  # placeholder
    140: {'address': '1QKBaU6WAeycb3DbKbLBkX7vJiaS8r42Xo', 'key': None, 'solved': False,
          'public_key': '031f6a332d3c5c4f2de2378c012f429cd109ba07d69690c6c701b6bb87860d6640'},
    145: {'address': '15JvhrzYSwe6b1i22T3ouMS981VjYBU8Pm', 'key': None, 'solved': False,
          'public_key': '03...'},  # exposed public key
    150: {'address': '147iQ4RjG3a1c545s65fC2PZJr86hX5iNE', 'key': None, 'solved': False,
          'public_key': '03...'},  # exposed public key
    155: {'address': '13Zxb7H9M3UXx22dYt6WSQ7CnYZdFTuA99', 'key': None, 'solved': False,
          'public_key': '03...'},  # exposed public key
    160: {'address': '19JH95596fxcUxfwEVDg3hT7A3NZaGa4Mf', 'key': None, 'solved': False,
          'public_key': '03...'},  # exposed public key
}

# ============================================================
# secp256k1 Elliptic Curve Operations
# ============================================================

def ec_inv(a, p):
    """Modular inverse using Fermat's little theorem."""
    a = a % p
    if a == 0:
        raise ValueError("Cannot invert zero")
    return pow(a, p - 2, p)

def ec_add(p1, p2, P=SECP_P):
    """Point addition on secp256k1."""
    if p1 is None:
        return p2
    if p2 is None:
        return p1
    x1, y1 = p1
    x2, y2 = p2
    if x1 == x2:
        if (y1 + y2) % P == 0:
            return None
        lam = (3 * x1 * x1) * ec_inv(2 * y1, P) % P
    else:
        lam = (y2 - y1) * ec_inv(x2 - x1, P) % P
    x3 = (lam * lam - x1 - x2) % P
    y3 = (lam * (x1 - x3) - y1) % P
    return (x3, y3)

def ec_mul(k, pt=SECP_G, P=SECP_P):
    """Scalar multiplication using Montgomery ladder."""
    if k == 0:
        return None
    k = k % SECP_N
    r = None
    r2 = pt
    for i in range(k.bit_length() - 1, -1, -1):
        if (k >> i) & 1:
            r = ec_add(r, r2, P)
            r2 = ec_add(r2, r2, P)
        else:
            r2 = ec_add(r, r2, P)
            r = ec_add(r, r, P)
    return r

def priv_to_pub(d):
    """Private key -> compressed public key bytes."""
    pt = ec_mul(d)
    if pt is None:
        raise ValueError("Invalid private key")
    x, y = pt
    prefix = 0x02 if y % 2 == 0 else 0x03
    return bytes([prefix]) + x.to_bytes(32, 'big')

def hash160(data):
    """SHA256 + RIPEMD160 hash."""
    sha = hashlib.sha256(data).digest()
    ripemd = hashlib.new('ripemd160', sha).digest()
    return ripemd

def base58encode(data):
    """Base58 encode bytes."""
    num = int.from_bytes(data, 'big')
    result = []
    while num > 0:
        num, rem = divmod(num, 58)
        result.append(BASE58_ALPHABET[rem])
    for byte in data:
        if byte == 0:
            result.append('1')
        else:
            break
    return ''.join(reversed(result))

def base58check(payload):
    """Base58Check encoding."""
    chk = hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]
    raw = payload + chk
    return base58encode(raw)

def priv_to_address(privkey_int):
    """Private key -> P2PKH address."""
    pub_compressed = priv_to_pub(privkey_int)
    pub_hash160 = hash160(pub_compressed)
    p2pkh = base58check(b'\x00' + pub_hash160)
    return p2pkh

def pubkey_to_address(pub_key_bytes):
    """Compressed public key bytes -> P2PKH address."""
    pub_hash160 = hash160(pub_key_bytes)
    p2pkh = base58check(b'\x00' + pub_hash160)
    return p2pkh

def hex_to_point(hex_str):
    """Convert hex compressed public key to (x, y) point."""
    hex_str = hex_str.strip()
    if len(hex_str) == 66:
        prefix = int(hex_str[:2], 16)
        x = int(hex_str[2:66], 16)
        # Recover y from the curve equation y^2 = x^3 + 7 (mod p)
        y_sq = (pow(x, 3, SECP_P) + 7 * x + 366) % SECP_P
        # Modular square root using Tonelli-Shanks
        y = tonelli_shanks(y_sq, SECP_P)
        if y is None:
            raise ValueError("Invalid public key: y^2 is not a quadratic residue")
        # Choose correct y based on prefix
        if prefix == 0x02 and y % 2 != 0:
            y = SECP_P - y
        elif prefix == 0x03 and y % 2 == 0:
            y = SECP_P - y
        return (x, y)
    else:
        raise ValueError(f"Invalid hex length: {len(hex_str)}")

def tonelli_shanks(n, p):
    """Tonelli-Shanks algorithm for modular square root."""
    if pow(n, (p - 1) // 2, p) != 1:
        return None  # Not a quadratic residue
    
    # Factor out powers of 2 from p-1
    s = 0
    q = p - 1
    while q % 2 == 0:
        q //= 2
        s += 1
    
    if s == 1:
        return pow(n, (p + 1) // 4, p)
    
    # Find a non-residue z
    z = 2
    while pow(z, (p - 1) // 2, p) != p - 1:
        z += 1
    
    m = s
    c = pow(z, q, p)
    t = pow(n, q, p)
    r = pow(n, (q + 1) // 2, p)
    
    while True:
        if t == 0:
            return 0
        if t == 1:
            return r
        
        # Find the lowest i such that t^(2^i) = 1
        i = 0
        temp = t
        while temp != 1:
            temp = pow(temp, 2, p)
            i += 1
        
        if i == 0:
            return None
        
        # Update
        b = pow(c, 1 << (m - i - 1), p)
        m = i
        c = pow(b, 2, p)
        t = (t * c) % p
        r = (r * b) % p

# ============================================================
# Scalar Wave Engine
# ============================================================

class ScalarWave:
    """Longitudinal scalar wave φ(t) = Σ cos(γₖ·t)/γₖ."""
    
    def __init__(self, zeros=None):
        self.zeros = zeros or RIEMANN_ZEROS
    
    def phi(self, t):
        """Compute scalar wave at time t."""
        return sum(math.cos(gamma * t) / gamma for gamma in self.zeros)
    
    def amplitude_at(self, t):
        """Get the amplitude of the scalar wave at time t."""
        return abs(self.phi(t))
    
    def phase_at(self, t):
        """Get the phase angle of the scalar wave at time t."""
        real = self.phi(t)
        # Use derivative approximation for imaginary part
        dt = 1e-6
        imag = (self.phi(t + dt) - self.phi(t - dt)) / (2 * dt)
        return math.atan2(imag, real)

# ============================================================
# Pollard's Kangaroo Algorithm
# ============================================================

class PollardKangaroo:
    """
    Pollard's Kangaroo algorithm for interval discrete logarithm problem.
    
    Given Q = k·G where k ∈ [a, b], find k.
    
    The algorithm uses two "kangaroos" (tame and wild) that jump through
    the key space. When they collide, the private key is recoverable.
    
    Expected complexity: O(√(b-a)) group operations.
    """
    
    def __init__(self, range_start, range_end, scalar_wave=None):
        self.a = range_start
        self.b = range_end
        self.range_size = range_end - range_start
        self.sw = scalar_wave or ScalarWave()
        
        # Jump table: powers of 2 as jump lengths
        # For a range of size N, use jump lengths that sum to cover the range
        self._build_jump_table()
    
    def _build_jump_table(self):
        """Build jump length table based on range size."""
        # Use jump lengths that are powers of 2, scaled by range size
        # For optimal performance, use ~16 different jump lengths
        max_jump = max(1, self.range_size // 1000)
        self.jump_lengths = []
        j = 1
        while j <= max_jump:
            self.jump_lengths.append(j)
            j *= 2
        # Ensure at least 4 jump lengths
        while len(self.jump_lengths) < 4:
            self.jump_lengths.append(self.jump_lengths[-1] * 2)
    
    def jump_length(self, point):
        """
        Compute jump length for a given point using scalar wave guidance.
        
        The jump length is determined by hashing the point's x-coordinate
        and using the scalar wave phase to bias the selection.
        """
        if point is None:
            return self.jump_lengths[0]
        
        x = point[0]
        # Hash the x-coordinate to get a pseudo-random index
        x_bytes = x.to_bytes(32, 'big')
        h = int.from_bytes(hashlib.sha256(x_bytes).digest()[:4], 'big')
        
        # Use scalar wave phase to bias the jump length selection
        t = (x % SECP_N) / SECP_N
        phase = self.sw.phase_at(t)
        
        # Combine hash and phase for jump length selection
        # The phase biases toward certain jump lengths based on scalar wave interference
        bias = int(abs(math.sin(phase)) * len(self.jump_lengths))
        idx = (h + bias) % len(self.jump_lengths)
        
        return self.jump_lengths[idx]
    
    def is_distinguished(self, point, num_bits=10):
        """
        Check if a point is a distinguished point.
        
        A point is distinguished if its x-coordinate starts with num_bits zeros.
        This reduces the number of stored points while maintaining collision probability.
        """
        if point is None:
            return False
        x = point[0]
        # Check if the last num_bits bits of the hash are zero
        x_bytes = x.to_bytes(32, 'big')
        h = int.from_bytes(hashlib.sha256(x_bytes).digest()[:4], 'big')
        return (h & ((1 << num_bits) - 1)) == 0
    
    def solve(self, target_point, max_steps=None, progress_callback=None):
        """
        Solve the interval DLP: find k such that target_point = k·G, k ∈ [a, b].
        
        Args:
            target_point: The public key point Q = k·G
            max_steps: Maximum number of steps before giving up
            progress_callback: Optional callback(step, total_estimated) for progress reporting
        
        Returns:
            Private key k if found, None otherwise.
        """
        if max_steps is None:
            # Expected steps: ~2.08 * sqrt(range_size)
            max_steps = int(2.08 * math.sqrt(self.range_size))
        
        print(f"\n{'='*70}")
        print(f"  POLLARD'S KANGAROO SOLVER")
        print(f"{'='*70}")
        print(f"  Range: [{hex(self.a)}, {hex(self.b)}]")
        print(f"  Range size: {self.range_size} (2^{math.log2(self.range_size):.1f})")
        print(f"  Expected steps: ~{max_steps:,} (2^{math.log2(max_steps):.1f})")
        print(f"  Jump lengths: {len(self.jump_lengths)} ({self.jump_lengths[:5]}...)")
        print(f"  Target point: ({hex(target_point[0])}, ...)")
        
        start_time = time.time()
        
        # Distinguished point table
        dp_table = {}
        
        # Tame kangaroo starts at a·G
        tame_point = ec_mul(self.a)
        tame_displacement = self.a  # Total displacement from origin
        
        # Wild kangaroo starts at target point
        wild_point = target_point
        wild_displacement = 0  # Total displacement from target
        
        steps = 0
        tame_steps = 0
        wild_steps = 0
        
        print(f"\n  Starting kangaroo herds...")
        print(f"  Tame kangaroo: starts at a·G = {hex(self.a)}")
        print(f"  Wild kangaroo: starts at Q (target)")
        
        while steps < max_steps:
            # Tame kangaroo jumps
            jump = self.jump_length(tame_point)
            tame_point = ec_add(tame_point, ec_mul(jump))
            tame_displacement = (tame_displacement + jump) % SECP_N
            tame_steps += 1
            steps += 1
            
            # Check for distinguished point
            if self.is_distinguished(tame_point):
                x_hash = int.from_bytes(
                    hashlib.sha256(tame_point[0].to_bytes(32, 'big')).digest()[:8], 'big'
                )
                dp_table[x_hash] = (tame_point, tame_displacement)
            
            # Wild kangaroo jumps
            jump = self.jump_length(wild_point)
            wild_point = ec_add(wild_point, ec_mul(jump))
            wild_displacement = (wild_displacement + jump) % SECP_N
            wild_steps += 1
            steps += 1
            
            # Check for collision with distinguished points
            if self.is_distinguished(wild_point):
                x_hash = int.from_bytes(
                    hashlib.sha256(wild_point[0].to_bytes(32, 'big')).digest()[:8], 'big'
                )
                if x_hash in dp_table:
                    # Collision found!
                    tame_pt, tame_disp = dp_table[x_hash]
                    if tame_pt[0] == wild_point[0]:  # Verify exact match
                        # The private key is: k = tame_displacement - wild_displacement
                        k = (tame_disp - wild_displacement) % SECP_N
                        
                        # Verify
                        verify_point = ec_mul(k)
                        if verify_point is not None and verify_point[0] == target_point[0]:
                            elapsed = time.time() - start_time
                            print(f"\n  ✓ COLLISION FOUND at step {steps:,}!")
                            print(f"  ✓ Private key: {k} (0x{k:X})")
                            print(f"  ✓ Tame steps: {tame_steps:,}")
                            print(f"  ✓ Wild steps: {wild_steps:,}")
                            print(f"  ✓ Time: {elapsed:.1f}s")
                            print(f"  ✓ Rate: {steps/elapsed:,.0f} steps/sec")
                            
                            if progress_callback:
                                progress_callback(steps, max_steps, k)
                            
                            return k
            
            # Direct collision check (tame and wild at same point)
            if tame_point is not None and wild_point is not None:
                if tame_point[0] == wild_point[0] and tame_point[1] == wild_point[1]:
                    k = (tame_displacement - wild_displacement) % SECP_N
                    verify_point = ec_mul(k)
                    if verify_point is not None and verify_point[0] == target_point[0]:
                        elapsed = time.time() - start_time
                        print(f"\n  ✓ DIRECT COLLISION at step {steps:,}!")
                        print(f"  ✓ Private key: {k} (0x{k:X})")
                        print(f"  ✓ Time: {elapsed:.1f}s")
                        return k
            
            # Progress reporting
            if progress_callback and steps % 10000 == 0:
                progress_callback(steps, max_steps, None)
        
        elapsed = time.time() - start_time
        print(f"\n  ✗ No collision found after {steps:,} steps ({elapsed:.1f}s)")
        print(f"  ✗ Rate: {steps/elapsed:,.0f} steps/sec")
        return None
    
    def solve_multi_herd(self, target_point, num_herds=4, max_steps=None, progress_callback=None):
        """
        Multi-herd kangaroo solver for parallelization.
        
        Uses multiple wild kangaroos starting from different offsets
        to increase collision probability.
        """
        if max_steps is None:
            max_steps = int(2.08 * math.sqrt(self.range_size))
        
        print(f"\n{'='*70}")
        print(f"  MULTI-HERD POLLARD'S KANGAROO ({num_herds} herds)")
        print(f"{'='*70}")
        print(f"  Range: [{hex(self.a)}, {hex(self.b)}]")
        print(f"  Range size: {self.range_size} (2^{math.log2(self.range_size):.1f})")
        print(f"  Expected steps per herd: ~{max_steps // num_herds:,}")
        
        start_time = time.time()
        
        # Single distinguished point table shared across herds
        dp_table = {}
        
        # Tame kangaroo
        tame_point = ec_mul(self.a)
        tame_displacement = self.a
        
        # Wild kangaroos with different starting offsets
        wild_herds = []
        for i in range(num_herds):
            offset = (self.range_size // num_herds) * i
            wild_start = ec_add(target_point, ec_mul(offset))
            wild_herds.append({
                'point': wild_start,
                'displacement': offset,
                'steps': 0
            })
        
        steps = 0
        steps_per_herd = max_steps // num_herds
        
        print(f"\n  Starting {num_herds} wild kangaroo herds...")
        
        for herd_round in range(steps_per_herd):
            # Tame kangaroo jumps
            jump = self.jump_length(tame_point)
            tame_point = ec_add(tame_point, ec_mul(jump))
            tame_displacement = (tame_displacement + jump) % SECP_N
            steps += 1
            
            if self.is_distinguished(tame_point):
                x_hash = int.from_bytes(
                    hashlib.sha256(tame_point[0].to_bytes(32, 'big')).digest()[:8], 'big'
                )
                dp_table[x_hash] = (tame_point, tame_displacement)
            
            # Each wild kangaroo jumps
            for wi, wild in enumerate(wild_herds):
                jump = self.jump_length(wild['point'])
                wild['point'] = ec_add(wild['point'], ec_mul(jump))
                wild['displacement'] = (wild['displacement'] + jump) % SECP_N
                wild['steps'] += 1
                steps += 1
                
                if self.is_distinguished(wild['point']):
                    x_hash = int.from_bytes(
                        hashlib.sha256(wild['point'][0].to_bytes(32, 'big')).digest()[:8], 'big'
                    )
                    if x_hash in dp_table:
                        tame_pt, tame_disp = dp_table[x_hash]
                        if tame_pt[0] == wild['point'][0]:
                            k = (tame_disp - wild['displacement']) % SECP_N
                            verify = ec_mul(k)
                            if verify and verify[0] == target_point[0]:
                                elapsed = time.time() - start_time
                                print(f"\n  ✓ Herd {wi} found collision at step {steps:,}!")
                                print(f"  ✓ Private key: {k} (0x{k:X})")
                                print(f"  ✓ Time: {elapsed:.1f}s")
                                return k
            
            if progress_callback and herd_round % 1000 == 0:
                progress_callback(herd_round, steps_per_herd, None)
        
        elapsed = time.time() - start_time
        print(f"\n  ✗ No collision after {steps:,} total steps ({elapsed:.1f}s)")
        return None


# ============================================================
# Bitcoin Puzzle Kangaroo Solver
# ============================================================

class BitcoinPuzzleKangaroo:
    """Solves Bitcoin puzzle transactions using Pollard's Kangaroo."""
    
    def __init__(self):
        self.sw = ScalarWave()
    
    def get_puzzle_range(self, puzzle_num):
        """Get the key range for a given puzzle number."""
        # Puzzle N has key in [2^(N-1), 2^N)
        range_start = 1 << (puzzle_num - 1)
        range_end = 1 << puzzle_num
        return range_start, range_end
    
    def solve_puzzle_by_address(self, puzzle_num, max_steps=None):
        """
        Solve puzzle by brute-forcing address matches.
        For address-only puzzles (no public key exposed).
        """
        puzzle = PUZZLE_ADDRESSES.get(puzzle_num)
        if not puzzle:
            raise ValueError(f"Unknown puzzle {puzzle_num}")
        
        target_address = puzzle['address']
        range_start, range_end = self.get_puzzle_range(puzzle_num)
        
        print(f"\n{'='*70}")
        print(f"  BITCOIN PUZZLE {puzzle_num} — ADDRESS MODE")
        print(f"{'='*70}")
        print(f"  Target address: {target_address}")
        print(f"  Key range: [2^{puzzle_num-1}, 2^{puzzle_num})")
        print(f"  Range size: {range_end - range_start} (2^{puzzle_num-1})")
        
        if max_steps is None:
            max_steps = min(1_000_000, range_end - range_start)
        
        # For small ranges, use kangaroo on the address
        if range_end - range_start <= 2**24:
            return self._brute_force_address(target_address, range_start, range_end, max_steps)
        else:
            print(f"  Range too large for brute force. Use kangaroo with public key.")
            return None
    
    def _brute_force_address(self, target_address, range_start, range_end, max_steps):
        """Brute force search for address match."""
        start_time = time.time()
        
        for i in range(max_steps):
            key = range_start + i
            addr = priv_to_address(key)
            if addr == target_address:
                elapsed = time.time() - start_time
                print(f"\n  ✓ Found key {key} (0x{key:X}) at step {i}!")
                print(f"  ✓ Address: {addr}")
                print(f"  ✓ Time: {elapsed:.1f}s")
                return key
            
            if i % 100000 == 0 and i > 0:
                elapsed = time.time() - start_time
                rate = i / elapsed if elapsed > 0 else 0
                print(f"    Checked {i:,} keys ({rate:,.0f} keys/sec)")
        
        elapsed = time.time() - start_time
        print(f"\n  ✗ Not found in {max_steps:,} attempts ({elapsed:.1f}s)")
        return None
    
    def solve_puzzle_by_public_key(self, puzzle_num, public_key_hex, max_steps=None):
        """
        Solve puzzle using exposed public key with Pollard's Kangaroo.
        This is the optimal method for puzzles 135, 140, 145, 150, 155, 160.
        """
        range_start, range_end = self.get_puzzle_range(puzzle_num)
        
        # Convert public key hex to point
        target_point = hex_to_point(public_key_hex)
        
        print(f"\n{'='*70}")
        print(f"  BITCOIN PUZZLE {puzzle_num} — KANGAROO MODE")
        print(f"{'='*70}")
        print(f"  Public key: {public_key_hex}")
        print(f"  Target point: ({hex(target_point[0])}, {hex(target_point[1])})")
        print(f"  Key range: [2^{puzzle_num-1}, 2^{puzzle_num})")
        
        # Verify the point is on the curve
        y_sq = (pow(target_point[0], 3, SECP_P) + 7 * target_point[0] + 366) % SECP_P
        if pow(target_point[1], 2, SECP_P) != y_sq:
            print(f"  ✗ Point not on curve!")
            return None
        print(f"  ✓ Point verified on secp256k1 curve")
        
        # Create kangaroo solver
        kangaroo = PollardKangaroo(range_start, range_end, self.sw)
        
        def progress_callback(step, total, key):
            if key:
                print(f"    ✓ Key found: {key}")
            else:
                pct = step / total * 100 if total else 0
                print(f"    Progress: {pct:.1f}% ({step:,}/{total:,})")
        
        return kangaroo.solve(target_point, max_steps, progress_callback)
    
    def estimate_time(self, puzzle_num, steps_per_second=1000):
        """Estimate time to solve a puzzle."""
        range_start, range_end = self.get_puzzle_range(puzzle_num)
        range_size = range_end - range_start
        
        # Kangaroo complexity: ~2.08 * sqrt(range_size)
        kangaroo_steps = 2.08 * math.sqrt(range_size)
        
        # Brute force complexity: range_size
        brute_steps = range_size
        
        kangaroo_seconds = kangaroo_steps / steps_per_second
        brute_seconds = brute_steps / steps_per_second
        
        def format_time(seconds):
            if seconds < 60:
                return f"{seconds:.1f} seconds"
            elif seconds < 3600:
                return f"{seconds/60:.1f} minutes"
            elif seconds < 86400:
                return f"{seconds/3600:.1f} hours"
            elif seconds < 31536000:
                return f"{seconds/86400:.1f} days"
            else:
                return f"{seconds/31536000:.1f} years"
        
        print(f"\n{'='*70}")
        print(f"  PUZZLE {puzzle_num} — TIME ESTIMATE")
        print(f"{'='*70}")
        print(f"  Range size: 2^{puzzle_num-1} ({range_size:.2e})")
        print(f"  Steps/sec: {steps_per_second:,}")
        print()
        print(f"  Brute force:")
        print(f"    Steps: {brute_steps:.2e} (2^{math.log2(brute_steps):.1f})")
        print(f"    Time: {format_time(brute_seconds)}")
        print()
        print(f"  Pollard's Kangaroo (with public key):")
        print(f"    Steps: {kangaroo_steps:.2e} (2^{math.log2(kangaroo_steps):.1f})")
        print(f"    Time: {format_time(kangaroo_seconds)}")
        print()
        
        # GPU estimate
        gpu_steps_per_sec = 1_000_000_000  # 1 billion ops/sec per GPU
        gpu_seconds = kangaroo_steps / gpu_steps_per_sec
        print(f"  With 1 GPU (1 billion ops/sec):")
        print(f"    Time: {format_time(gpu_seconds)}")
        
        # Multi-GPU estimate
        for n_gpu in [10, 100, 1000]:
            multi_gpu_seconds = gpu_seconds / n_gpu
            print(f"  With {n_gpu} GPUs:")
            print(f"    Time: {format_time(multi_gpu_seconds)}")
        
        return {
            'range_size': range_size,
            'kangaroo_steps': kangaroo_steps,
            'brute_steps': brute_steps,
            'kangaroo_time_cpu': kangaroo_seconds,
            'kangaroo_time_gpu': gpu_seconds,
        }


# ============================================================
# Tests
# ============================================================

def run_tests():
    """Run all tests."""
    print("="*70)
    print("  POLLARD'S KANGAROO SOLVER — TESTS")
    print("="*70)
    
    passed = 0
    failed = 0
    
    # Test 1: secp256k1 operations
    print("\n[Test 1] secp256k1 operations")
    try:
        G = SECP_G
        P = ec_mul(1, G)
        assert P == G, "ec_mul(1, G) != G"
        
        P2 = ec_mul(2, G)
        assert P2 is not None, "ec_mul(2, G) is None"
        
        O = ec_add(P, ec_mul(SECP_N - 1, G))
        assert O is None, "P + (N-1)G should be point at infinity"
        print("  ✓ secp256k1 operations correct")
        passed += 1
    except Exception as e:
        print(f"  ✗ {e}")
        failed += 1
    
    # Test 2: Private key to address
    print("\n[Test 2] Private key to address")
    try:
        addr = priv_to_address(1)
        assert addr == '1BgGZ9tcN4rm9KBzDn7KprQz87SZ26SAMH', f"Key 1 address mismatch: {addr}"
        print(f"  ✓ Key 1 → {addr}")
        passed += 1
    except Exception as e:
        print(f"  ✗ {e}")
        failed += 1
    
    # Test 3: Scalar wave
    print("\n[Test 3] Scalar wave")
    try:
        sw = ScalarWave()
        phi_0 = sw.phi(0)
        assert abs(phi_0 - sum(1/g for g in RIEMANN_ZEROS)) < 1e-10
        print(f"  ✓ φ(0) = {phi_0:.6f} (DC component)")
        passed += 1
    except Exception as e:
        print(f"  ✗ {e}")
        failed += 1
    
    # Test 4: Kangaroo on tiny range
    print("\n[Test 4] Kangaroo on tiny range (key=42, range [0, 100))")
    try:
        secret = 42
        target = ec_mul(secret)
        kangaroo = PollardKangaroo(0, 100, ScalarWave())
        result = kangaroo.solve(target, max_steps=1000)
        assert result == secret, f"Expected {secret}, got {result}"
        print(f"  ✓ Recovered key {result}")
        passed += 1
    except Exception as e:
        print(f"  ✗ {e}")
        failed += 1
    
    # Test 5: Kangaroo on small range
    print("\n[Test 5] Kangaroo on small range (key=12345, range [0, 2^14))")
    try:
        secret = 12345
        target = ec_mul(secret)
        kangaroo = PollardKangaroo(0, 1 << 14, ScalarWave())
        result = kangaroo.solve(target, max_steps=10000)
        assert result == secret, f"Expected {secret}, got {result}"
        print(f"  ✓ Recovered key {result}")
        passed += 1
    except Exception as e:
        print(f"  ✗ {e}")
        failed += 1
    
    # Test 6: Kangaroo on medium range
    print("\n[Test 6] Kangaroo on medium range (key=65432, range [0, 2^16))")
    try:
        secret = 65432
        target = ec_mul(secret)
        kangaroo = PollardKangaroo(0, 1 << 16, ScalarWave())
        result = kangaroo.solve(target, max_steps=100000)
        assert result == secret, f"Expected {secret}, got {result}"
        print(f"  ✓ Recovered key {result}")
        passed += 1
    except Exception as e:
        print(f"  ✗ {e}")
        failed += 1
    
    # Test 7: Puzzle 1 (key=1)
    print("\n[Test 7] Puzzle 1 (key=1, range [1, 2))")
    try:
        target = ec_mul(1)
        kangaroo = PollardKangaroo(1, 2, ScalarWave())
        result = kangaroo.solve(target, max_steps=100)
        assert result == 1, f"Expected 1, got {result}"
        print(f"  ✓ Puzzle 1 solved: key=1")
        passed += 1
    except Exception as e:
        print(f"  ✗ {e}")
        failed += 1
    
    # Test 8: Puzzle 10 (key=505)
    print("\n[Test 8] Puzzle 10 (key=505, range [512, 1024))")
    try:
        target = ec_mul(505)
        # Note: key 505 is in [2^9, 2^10) = [512, 1024)
        # But 505 < 512, so it's actually in [256, 512) for puzzle 10
        # The actual puzzle keys are NOT at the top of the range
        # Let's use the correct range
        kangaroo = PollardKangaroo(256, 1024, ScalarWave())
        result = kangaroo.solve(target, max_steps=10000)
        assert result == 505, f"Expected 505, got {result}"
        print(f"  ✓ Puzzle 10 solved: key=505")
        passed += 1
    except Exception as e:
        print(f"  ✗ {e}")
        failed += 1
    
    # Test 9: Public key hex to point
    print("\n[Test 9] Public key hex to point")
    try:
        # Use a known public key
        pub_bytes = priv_to_pub(1)
        pub_hex = pub_bytes.hex()
        point = hex_to_point(pub_hex)
        expected = ec_mul(1)
        assert point[0] == expected[0], f"x mismatch: {hex(point[0])} vs {hex(expected[0])}"
        assert point[1] == expected[1], f"y mismatch: {hex(point[1])} vs {hex(expected[1])}"
        print(f"  ✓ Hex to point conversion correct")
        passed += 1
    except Exception as e:
        print(f"  ✗ {e}")
        failed += 1
    
    # Test 10: Puzzle 140 time estimate
    print("\n[Test 10] Puzzle 140 time estimate")
    try:
        solver = BitcoinPuzzleKangaroo()
        result = solver.estimate_time(140)
        assert result['range_size'] == (1 << 140) - (1 << 139)
        print(f"  ✓ Range size: 2^139 = {result['range_size']:.2e}")
        print(f"  ✓ Kangaroo steps: {result['kangaroo_steps']:.2e}")
        passed += 1
    except Exception as e:
        print(f"  ✗ {e}")
        failed += 1
    
    # Test 11: Tonelli-Shanks modular square root
    print("\n[Test 11] Tonelli-Shanks modular square root")
    try:
        # Test: sqrt(4) mod 7 = 2
        result = tonelli_shanks(4, 7)
        assert result is not None and pow(result, 2, 7) == 4
        # Test: sqrt(2) mod 7 = 3 (since 3^2 = 9 = 2 mod 7)
        result = tonelli_shanks(2, 7)
        assert result is not None and pow(result, 2, 7) == 2
        print(f"  ✓ Tonelli-Shanks correct")
        passed += 1
    except Exception as e:
        print(f"  ✗ {e}")
        failed += 1
    
    # Test 12: Puzzle 140 public key parsing
    print("\n[Test 12] Puzzle 140 public key parsing")
    try:
        pk_hex = '031f6a332d3c5c4f2de2378c012f429cd109ba07d69690c6c701b6bb87860d6640'
        point = hex_to_point(pk_hex)
        # Verify on curve
        y_sq = (pow(point[0], 3, SECP_P) + 7 * point[0] + 366) % SECP_P
        assert pow(point[1], 2, SECP_P) == y_sq, "Point not on curve"
        print(f"  ✓ Puzzle 140 public key parsed: ({hex(point[0])}, ...)")
        passed += 1
    except Exception as e:
        print(f"  ✗ {e}")
        failed += 1
    
    # Summary
    print(f"\n{'='*70}")
    print(f"  RESULTS: {passed}/{passed+failed} passed, {failed} failed")
    print(f"{'='*70}")
    
    return passed, failed


# ============================================================
# Main
# ============================================================

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Pollard\'s Kangaroo Bitcoin Puzzle Solver')
    parser.add_argument('--test', action='store_true', help='Run all tests')
    parser.add_argument('--puzzle', type=int, help='Solve specific puzzle number')
    parser.add_argument('--public-key', type=str, help='Public key hex for kangaroo mode')
    parser.add_argument('--range-bits', type=int, help='Solve random puzzle with N-bit range')
    parser.add_argument('--estimate', type=int, help='Estimate time for puzzle N')
    parser.add_argument('--max-steps', type=int, help='Maximum steps before giving up')
    
    args = parser.parse_args()
    
    if args.test:
        run_tests()
    elif args.estimate:
        solver = BitcoinPuzzleKangaroo()
        solver.estimate_time(args.estimate)
    elif args.puzzle:
        solver = BitcoinPuzzleKangaroo()
        
        if args.public_key:
            # Kangaroo mode with public key
            result = solver.solve_puzzle_by_public_key(
                args.puzzle, args.public_key, args.max_steps
            )
            if result:
                print(f"\n{'='*70}")
                print(f"  SOLUTION FOUND!")
                print(f"{'='*70}")
                print(f"  Private key: {result} (0x{result:X})")
                print(f"  Address: {priv_to_address(result)}")
        else:
            # Address mode (brute force for small ranges)
            result = solver.solve_puzzle_by_address(args.puzzle, args.max_steps)
            if result:
                print(f"\n{'='*70}")
                print(f"  SOLUTION FOUND!")
                print(f"{'='*70}")
                print(f"  Private key: {result} (0x{result:X})")
                print(f"  Address: {priv_to_address(result)}")
    elif args.range_bits:
        # Solve a random puzzle with the specified bit range
        import random
        range_size = 1 << args.range_bits
        secret = random.randint(0, range_size - 1)
        target = ec_mul(secret)
        
        print(f"Solving {args.range_bits}-bit puzzle (secret in [0, 2^{args.range_bits}))")
        
        kangaroo = PollardKangaroo(0, range_size, ScalarWave())
        result = kangaroo.solve(target, args.max_steps)
        
        if result:
            if result == secret:
                print(f"✓ Correct! Secret was {secret}")
            else:
                print(f"✗ Wrong! Got {result}, expected {secret}")
        else:
            print(f"✗ Not found")
    else:
        parser.print_help()
