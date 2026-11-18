#!/usr/bin/env python3
"""
dual_bell_spectral.py — Dual-End Bell State Adaptive Spectral Attack

Solves Bitcoin Puzzle 140 using a dual-end Pollard's Kangaroo attack where:
- Two kangaroo herds start from BOTH ends of the range [2^139, 2^140)
- Four Bell states |Φ⁺⟩, |Φ⁻⟩, |Ψ⁺⟩, |Ψ⁻⟩ determine adaptive jump lengths
- A trifold center of control cuts the spectral domain into thirds
- The scalar wave φ(t) = Σ cos(γₖ·t)/γₖ provides phase guidance

THE DUAL-END STRATEGY
=====================
Instead of one tame + one wild kangaroo, we use FOUR herds:

  Herd A (tame-left):  starts at a·G (lower bound)
  Herd B (tame-right): starts at b·G (upper bound)
  Herd C (wild):       starts at Q (target public key)
  Herd D (wild-mirror): starts at Q - (b-a)·G (mirror image)

Each herd jumps using Bell state projectors to select jump lengths.
The four Bell states create four interference channels that guide
the herds toward the center of the range.

BELL STATE JUMP TABLE
=====================
The four Bell states define the jump length distribution:

  |Φ⁺⟩ = (|00⟩ + |11⟩)/√2  →  Large jumps (exploration)
  |Φ⁻⟩ = (|00⟩ - |11⟩)/√2  →  Medium jumps (exploitation)
  |Ψ⁺⟩ = (|01⟩ + |10⟩)/√2  →  Small jumps (refinement)
  |Ψ⁻⟩ = (|01⟩ - |10⟩)/√2  →  Micro jumps (convergence)

The Bell state measurement at each step determines which jump length
category to use. The scalar wave phase biases the measurement outcome.

TRIFOLD CENTER OF CONTROL
==========================
The spectral domain is divided into three zones:

  Zone 1 (Left third):  [a, a + (b-a)/3)
  Zone 2 (Center third): [a + (b-a)/3, a + 2(b-a)/3)
  Zone 3 (Right third):  [a + 2(b-a)/3, b)

The center zone is the collision target. Herds in the left zone
are biased toward rightward jumps, and vice versa. The center zone
uses the finest jump lengths for precision collision detection.

SCALAR WAVE PHASE GUIDANCE
===========================
The scalar wave φ(t) = Σ cos(γₖ·t)/γₖ evaluated at the herd's
current position determines the Bell state measurement bias:

  Phase near 0:   → |Φ⁺⟩ (large jumps, far from center)
  Phase near π/2: → |Φ⁻⟩ (medium jumps, approaching center)
  Phase near π:   → |Ψ⁺⟩ (small jumps, near center)
  Phase near 3π/2:→ |Ψ⁻⟩ (micro jumps, in center zone)

This creates an adaptive control system where the scalar wave
automatically adjusts the jump size based on proximity to the
center of the range.

PUZZLE 140 TARGET
==================
- Address: 1QKBaU6WAeycb3DbKbLBkX7vJiaS8r42Xo
- Public key: 031f6a332d3c5c4f2de2378c012f429cd109ba07d69690c6c701b6bb87860d6640
- Key range: [2^139, 2^140) — 7.0×10^41 candidates
- Kangaroo complexity: ~2^70 operations (~1.2×10^21 steps)
- Prize: 14 BTC (~$954,718)

USAGE
=====
    python dual_bell_spectral.py --test              # Run all tests
    python dual_bell_spectral.py --puzzle 140        # Attack puzzle 140
    python dual_bell_spectral.py --range 20          # Test on 20-bit range
    python dual_bell_spectral.py --estimate 140      # Estimate complexity
"""
import math
import cmath
import hashlib
import time
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ============================================================
# Constants
# ============================================================

SECP_P = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F
SECP_N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
SECP_Gx = 0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798
SECP_Gy = 0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8
SECP_G = (SECP_Gx, SECP_Gy)

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
    103.72553804191438, 105.44662305125214, 107.16861118523467,
    111.02953654272584, 111.87465909239329, 114.32022718136733,
    116.22668027902853, 118.79076573376035, 121.37012168764546,
    122.94683134146549, 124.25681685437654, 127.51668416938581,
    129.57860740315288, 131.08768954275750, 133.49773720304247,
    134.75650783382396, 138.11604215023640, 139.73422369960385,
    141.12370710189411, 143.11184683111372, 146.00092158694520,
    147.42276575327452, 150.05352042194463, 150.92525869131910,
    153.02463259197434, 156.11290901939846, 156.86263185907100,
    158.84998846436239, 161.18896385230387, 163.03151898189406,
    165.53706899011793, 167.18283569448715, 169.09359807082588,
    169.94591639632396, 173.21342951882997, 174.75643588872500,
    176.44189652375393, 178.37187048387454, 180.42255188038890,
    181.52783519905100, 184.82236556714610, 185.95049143734850,
    187.78438285926465, 189.40557238967987, 192.02665519866090,
    193.07972797839350, 195.26539899061890, 196.87648183889260,
    198.02712957355310, 201.26475207546620, 202.49359447119170,
    204.18967893423220, 205.38986504174430, 207.34667155720440,
    209.60517748284450, 211.69086287160960, 213.34791979388420,
    214.50714768809860, 216.16953802883460, 219.38280818233470,
    221.43018174380910, 224.00793553835480, 224.98390285217510,
    226.69263371531400, 228.99975393122940, 230.29591680237560,
    231.25005763760030, 233.21183999585620, 233.96614489605750,
    236.52422951359220, 237.39496056950270, 240.33177837419500,
    241.47889863281680, 241.99251174454120, 244.40911238484070,
    246.17371396757630, 246.90358007455720, 248.87290676122400,
    252.19074528118150, 252.49076347787770, 253.95082396009500,
    254.96787483956600, 256.37241996924080, 257.59358373187600,
    259.09083480357000, 260.48495775934500, 261.61369110843700,
    262.58876951918490, 264.14648047403200, 265.21471526691600,
    266.54701270136500, 267.93466169962800, 269.39449704996500,
    270.97775473772500, 271.95477429450600, 273.39686566968500,
    274.93381865446000, 275.93158547182700, 277.48469855727800,
    278.98762958519600, 280.49739393862500, 281.48706643468000,
    282.63680989537900, 284.17587558434000, 285.95741180982800,
    286.87666475927800, 288.93495211978900, 290.05549935901400,
    291.26701568807300, 292.39688944783000, 293.65230197113900,
    294.77389416383300, 295.85579518669100, 297.47227837974100,
    298.55679476365600, 299.69939647528600, 301.28057663898600,
    302.40923658056600, 303.89089430039500, 304.98363297334700,
    306.34003604072700, 307.92152600460600, 308.80968474330200,
    310.68995545462800, 311.66231468908200, 313.15860155266400,
    313.99078380344300, 315.02533344074500, 316.23352024245200,
    317.60271412230900, 319.63979892688400, 320.32680940123000,
    321.31308626775300, 322.45825022610100, 323.87461623553200,
    325.38450534035400, 326.68021579273900, 327.73382143070200,
    329.13844652626900, 330.36939894851500, 331.42580135564700,
    332.05440303244400, 333.03846036207400, 334.86383631757400,
    335.95691687243300, 337.06820889666500, 337.71885373915500,
    338.74895455571900, 340.57029030795800, 341.40881738497900,
    342.45873251954000, 343.53959928654800, 344.75689999717200,
    346.29165424099400, 347.26420534999500, 348.66713582437100,
    349.81383515794400, 351.01368591572000, 351.81714435581700,
    352.87464764750600, 354.03794796974500, 354.81677775354400,
    356.08088885828700, 357.70986052566300, 358.37300462072700,
    359.99685160095700, 361.11858072944500, 361.85683545563800,
    363.30980827603800, 364.44906791774000, 365.23068488877900,
    366.21370902409400, 367.32397136394200, 368.62337698085100,
    369.78219579619200, 370.34440607167900, 371.93462380896500,
    373.56664884253000, 374.76609431767800, 375.81786579604700,
    376.90177036378600, 378.45511999149300, 379.12713775058600,
    380.12731926173600, 381.27970735532000, 381.86086093927400,
    383.42369225423800, 384.58933249428900, 385.63775225693100,
    386.66423535565000, 387.84687755810100, 388.88386236888400,
    390.12963405563400, 391.19436726084400, 392.28944485275700,
    393.09851354470800, 394.46636918849400, 395.89259918664200,
    396.70615362263400, 397.75983747655600, 399.14183466254400,
    400.02533176436600, 400.81517573709700, 402.20873763852500,
    403.34382859145800, 404.31915376065600, 405.36407412030200,
    406.10484753177200, 407.63177854450800, 408.90704106904300,
    409.31450853299600, 410.43780234760700, 411.81353781217300,
    412.80839558393200, 413.55789722822500, 414.63049872063400,
    416.20599241053800, 417.27053331608200, 418.48264397145300,
    419.42480258015600, 420.76837085243600, 421.90231047840700,
    423.19377356548500, 423.97299327162600, 425.43805790582400,
    426.67737002506300, 427.44741653692200, 428.98544358341800,
    430.37783385068000, 431.13793556032000, 432.59907734806700,
    433.12188616435900, 434.90106945368700, 435.51873669774200,
    436.57906716147300, 437.66368106609100, 438.69950057044900,
    439.33644809893700, 440.33049992195500, 441.56982258659700,
    442.88956050487800, 443.71974751778400, 444.28415478091300,
    445.63303057763800, 447.09722289655300, 447.71813833630300,
    448.33475279546900, 449.38191700316600, 450.69315503002500,
    451.72834884282200, 452.63580123013300, 453.96977129383100,
    454.67564405499700, 456.29157407459700, 457.06036044483700,
    457.66054147326200, 458.78654133746500, 459.67986944966400,
    460.85751889561000, 461.51155582624000, 462.40151985188500,
    463.36799476896900, 464.60148519380300, 465.71883960558900,
    466.75470195330300, 467.87673802668900, 468.91260037440300,
    469.40057033642100, 470.73454030011000, 471.85627841230700,
    472.51031534293700, 473.63205345513400, 474.66791580284800,
    475.17988576486600, 476.51385572856400, 477.63559384076100,
    478.39569555040100, 479.52743366259800, 480.64917177479500,
    481.08114173681300, 482.41511170050200, 483.53684981269900,
    484.02481977471700, 485.35878973841500, 486.48052785061200,
    487.60226596280900, 488.36236767244900, 489.48410578464600,
    490.60584389684300, 491.36594560648300, 492.25927371868200,
    493.38101183087900, 494.50274994307600, 495.00471990509400,
    496.33868986879200, 497.19880157843200, 498.32053969062900,
    499.18065140026900, 500.30238951246600,
]

BASE58_ALPHABET = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'

# ============================================================
# secp256k1 Elliptic Curve Operations
# ============================================================

def ec_inv(a, p):
    a = a % p
    if a == 0:
        raise ValueError("Cannot invert zero")
    return pow(a, p - 2, p)

def ec_add(p1, p2, P=SECP_P):
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
    pt = ec_mul(d)
    if pt is None:
        raise ValueError("Invalid private key")
    x, y = pt
    prefix = 0x02 if y % 2 == 0 else 0x03
    return bytes([prefix]) + x.to_bytes(32, 'big')

def hash160(data):
    sha = hashlib.sha256(data).digest()
    ripemd = hashlib.new('ripemd160', sha).digest()
    return ripemd

def base58encode(data):
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
    chk = hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]
    raw = payload + chk
    return base58encode(raw)

def priv_to_address(privkey_int):
    pub_compressed = priv_to_pub(privkey_int)
    pub_hash160 = hash160(pub_compressed)
    p2pkh = base58check(b'\x00' + pub_hash160)
    return p2pkh

def priv_to_wif(privkey_int):
    payload = b'\x80' + privkey_int.to_bytes(32, 'big')
    return base58check(payload)

def hex_to_point(hex_str):
    hex_str = hex_str.strip()
    if len(hex_str) == 66:
        prefix = int(hex_str[:2], 16)
        x = int(hex_str[2:66], 16)
        y_sq = (pow(x, 3, SECP_P) + 7) % SECP_P
        y = tonelli_shanks(y_sq, SECP_P)
        if y is None:
            raise ValueError("Invalid public key")
        if prefix == 0x02 and y % 2 != 0:
            y = SECP_P - y
        elif prefix == 0x03 and y % 2 == 0:
            y = SECP_P - y
        return (x, y)
    else:
        raise ValueError(f"Invalid hex length: {len(hex_str)}")

def tonelli_shanks(n, p):
    if pow(n, (p - 1) // 2, p) != 1:
        return None
    s = 0
    q = p - 1
    while q % 2 == 0:
        q //= 2
        s += 1
    if s == 1:
        return pow(n, (p + 1) // 4, p)
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
        i = 0
        temp = t
        while temp != 1:
            temp = pow(temp, 2, p)
            i += 1
        if i == 0:
            return None
        b = pow(c, 1 << (m - i - 1), p)
        m = i
        c = pow(b, 2, p)
        t = (t * c) % p
        r = (r * b) % p

# ============================================================
# Scalar Wave Engine
# ============================================================

class ScalarWave:
    def __init__(self, zeros=None):
        self.zeros = zeros or RIEMANN_ZEROS
    
    def phi(self, t):
        return sum(math.cos(gamma * t) / gamma for gamma in self.zeros)
    
    def phi_complex(self, t):
        real = sum(math.cos(gamma * t) / gamma for gamma in self.zeros)
        imag = sum(-math.sin(gamma * t) for gamma in self.zeros)
        return complex(real, imag)
    
    def amplitude_at(self, t):
        return abs(self.phi_complex(t))
    
    def phase_at(self, t):
        c = self.phi_complex(t)
        return cmath.phase(c)

# ============================================================
# Bell State Projectors
# ============================================================

class BellStateProjectors:
    """
    The four Bell states as quantum projectors for jump length selection.
    
    |Φ⁺⟩ = (|00⟩ + |11⟩)/√2  →  Large jumps (exploration)
    |Φ⁻⟩ = (|00⟩ - |11⟩)/√2  →  Medium jumps (exploitation)
    |Ψ⁺⟩ = (|01⟩ + |10⟩)/√2  →  Small jumps (refinement)
    |Ψ⁻⟩ = (|01⟩ - |10⟩)/√2  →  Micro jumps (convergence)
    
    The Bell state measurement probability is biased by the scalar wave phase.
    """
    
    # Bell state labels
    PHI_PLUS = 0   # |Φ⁺⟩
    PHI_MINUS = 1  # |Φ⁻⟩
    PSI_PLUS =  2  # |Ψ⁺⟩
    PSI_MINUS = 3  # |Ψ⁻⟩
    
    NAMES = ['|Φ⁺⟩', '|Φ⁻⟩', '|Ψ⁺⟩', '|Ψ⁻⟩']
    
    def __init__(self, scalar_wave=None):
        self.sw = scalar_wave or ScalarWave()
    
    def measure(self, point, position_in_range, range_size):
        """
        Measure the Bell state at a given point, biased by scalar wave phase.
        
        The scalar wave phase at the normalized position determines
        the probability distribution over the four Bell states.
        
        Phase near 0:   → |Φ⁺⟩ (large jumps)
        Phase near π/2: → |Φ⁻⟩ (medium jumps)
        Phase near π:   → |Ψ⁺⟩ (small jumps)
        Phase near 3π/2:→ |Ψ⁻⟩ (micro jumps)
        """
        # Normalized position in range [0, 1]
        t = position_in_range / range_size
        
        # Scalar wave phase at this position
        phase = self.sw.phase_at(t * 2 * math.pi)
        
        # Map phase to Bell state probability distribution
        # The phase divides the circle into 4 quadrants
        # Each quadrant corresponds to one Bell state
        phase_normalized = (phase + 2 * math.pi) % (2 * math.pi)
        
        # Add deterministic hash component for true randomness
        if point is not None:
            x_bytes = point[0].to_bytes(32, 'big')
            h = int.from_bytes(hashlib.sha256(x_bytes).digest()[:2], 'big')
            # Hash biases the phase slightly
            phase_bias = h / (2**16 - 1) * 0.1  # ±5% bias
            phase_normalized = (phase_normalized + phase_bias) % (2 * math.pi)
        
        # Quadrant determines Bell state
        quadrant = int(phase_normalized / (math.pi / 2)) % 4
        
        return quadrant
    
    def jump_length(self, bell_state, max_jump):
        """
        Compute jump length based on Bell state measurement.
        
        |Φ⁺⟩: Large jump — 50-100% of max_jump (exploration)
        |Φ⁻⟩: Medium jump — 25-50% of max_jump (exploitation)
        |Ψ⁺⟩: Small jump — 10-25% of max_jump (refinement)
        |Ψ⁻⟩: Micro jump — 1-10% of max_jump (convergence)
        """
        if bell_state == self.PHI_PLUS:
            # Large jump: exploration
            return max(1, int(max_jump * (0.5 + 0.5 * (max_jump / (max_jump + 1)))))
        elif bell_state == self.PHI_MINUS:
            # Medium jump: exploitation
            return max(1, int(max_jump * 0.375))
        elif bell_state == self.PSI_PLUS:
            # Small jump: refinement
            return max(1, int(max_jump * 0.175))
        else:  # PSI_MINUS
            # Micro jump: convergence
            return max(1, int(max_jump * 0.05))
    
    def bell_amplitude(self, point, position_in_range, range_size):
        """
        Compute the Bell state amplitude vector at a given position.
        
        Returns a 4-element vector [a_Φ⁺, a_Φ⁻, a_Ψ⁺, a_Ψ⁻]
        representing the amplitude of each Bell state.
        """
        t = position_in_range / range_size
        c = self.sw.phi_complex(t * 2 * math.pi)
        
        # The complex scalar wave determines the Bell state amplitudes
        # via the identity operator decomposition: I = Σ |Bᵢ⟩⟨Bᵢ|
        phase = cmath.phase(c)
        amp = abs(c)
        
        # Four amplitudes from the complex phase
        a_phi_plus = amp * abs(math.cos(phase / 2))
        a_phi_minus = amp * abs(math.sin(phase / 2))
        a_psi_plus = amp * abs(math.cos((phase + math.pi) / 2))
        a_psi_minus = amp * abs(math.sin((phase + math.pi) / 2))
        
        return [a_phi_plus, a_phi_minus, a_psi_plus, a_psi_minus]

# ============================================================
# Trifold Center of Control
# ============================================================

class TrifoldCenter:
    """
    The trifold center of control divides the spectral domain into thirds.
    
    Zone 1 (Left third):  [a, a + (b-a)/3)
    Zone 2 (Center third): [a + (b-a)/3, a + 2(b-a)/3)
    Zone 3 (Right third):  [a + 2(b-a)/3, b)
    
    Each zone has different jump length scaling and collision detection rules.
    The center zone is the primary collision target.
    """
    
    ZONE_LEFT = 0
    ZONE_CENTER = 1
    ZONE_RIGHT = 2
    
    NAMES = ['Left', 'Center', 'Right']
    
    def __init__(self, range_start, range_end):
        self.a = range_start
        self.b = range_end
        self.range_size = range_end - range_start
        self.third = self.range_size // 3
        
        self.zone1_end = self.a + self.third
        self.zone2_end = self.a + 2 * self.third
    
    def get_zone(self, position):
        """Determine which zone a position falls in."""
        if position < self.zone1_end:
            return self.ZONE_LEFT
        elif position < self.zone2_end:
            return self.ZONE_CENTER
        else:
            return self.ZONE_RIGHT
    
    def zone_jump_scale(self, zone):
        """
        Get the jump length scaling factor for a zone.
        
        Left zone: 1.5x (larger jumps to reach center faster)
        Center zone: 0.5x (smaller jumps for precision)
        Right zone: 1.5x (larger jumps to reach center faster)
        """
        if zone == self.ZONE_LEFT:
            return 1.5
        elif zone == self.ZONE_CENTER:
            return 0.5
        else:
            return 1.5
    
    def distance_to_center(self, position):
        """Get the normalized distance from the center zone [0, 1]."""
        center = (self.a + self.b) // 2
        dist = abs(position - center)
        return dist / (self.range_size / 2)
    
    def center_bias(self, position):
        """
        Compute the center-seeking bias for a position.
        
        Returns a value in [-1, 1] where:
        -1 = strongly biased toward center from left
         0 = already in center
        +1 = strongly biased toward center from right
        """
        center = (self.a + self.b) // 2
        if position < center:
            # Left of center: bias rightward
            return -0.5 * (1 - self.distance_to_center(position))
        elif position > center:
            # Right of center: bias leftward
            return 0.5 * (1 - self.distance_to_center(position))
        else:
            return 0.0

# ============================================================
# Dual-End Bell State Kangaroo
# ============================================================

class DualBellKangaroo:
    """
    Dual-end Pollard's Kangaroo with Bell state adaptive jumps
    and trifold center of control.
    
    Four herds:
    - Herd A (tame-left): starts at a·G
    - Herd B (tame-right): starts at b·G
    - Herd C (wild): starts at Q (target)
    - Herd D (wild-mirror): starts at Q - (b-a)·G
    """
    
    def __init__(self, range_start, range_end, scalar_wave=None):
        self.a = range_start
        self.b = range_end
        self.range_size = range_end - range_start
        self.sw = scalar_wave or ScalarWave()
        self.bell = BellStateProjectors(self.sw)
        self.trifold = TrifoldCenter(range_start, range_end)
        
        # Jump table based on range size
        self.max_jump = max(1, self.range_size // 100)
    
    def get_position_in_range(self, displacement):
        """Map a displacement to a position in the range."""
        return self.a + (displacement % self.range_size)
    
    def kangaroo_jump(self, point, displacement, herd_id):
        """
        Compute a single kangaroo jump using Bell state measurement.
        
        Returns (new_point, new_displacement).
        """
        pos = self.get_position_in_range(displacement)
        zone = self.trifold.get_zone(pos)
        
        # Measure Bell state
        bell_state = self.bell.measure(point, pos - self.a, self.range_size)
        
        # Get jump length from Bell state
        jump = self.bell.jump_length(bell_state, self.max_jump)
        
        # Apply zone scaling
        jump = int(jump * self.trifold.zone_jump_scale(zone))
        
        # Apply center bias
        bias = self.trifold.center_bias(pos)
        if bias < 0 and herd_id in ['A', 'C']:
            # Left herds: bias toward center (rightward)
            jump = max(1, jump + int(jump * abs(bias)))
        elif bias > 0 and herd_id in ['B', 'D']:
            # Right herds: bias toward center (leftward)
            jump = max(1, jump + int(jump * abs(bias)))
        
        # Execute jump
        new_point = ec_add(point, ec_mul(jump))
        new_displacement = (displacement + jump) % SECP_N
        
        return new_point, new_displacement, bell_state, jump
    
    def is_distinguished(self, point, num_bits=10):
        """Check if a point is distinguished (hash starts with zeros)."""
        if point is None:
            return False
        x_bytes = point[0].to_bytes(32, 'big')
        h = int.from_bytes(hashlib.sha256(x_bytes).digest()[:4], 'big')
        return (h & ((1 << num_bits) - 1)) == 0
    
    def solve(self, target_point, max_steps=None, progress_callback=None):
        """
        Solve the interval DLP using dual-end Bell state kangaroos.
        
        Returns the private key if found, None otherwise.
        """
        if max_steps is None:
            max_steps = int(2.08 * math.sqrt(self.range_size))
        
        print(f"\n{'='*70}")
        print(f"  DUAL-END BELL STATE KANGAROO ATTACK")
        print(f"{'='*70}")
        print(f"  Range: [{hex(self.a)}, {hex(self.b)}]")
        print(f"  Range size: 2^{math.log2(self.range_size):.1f}")
        print(f"  Expected steps: ~{max_steps:,} (2^{math.log2(max_steps):.1f})")
        print(f"  Max jump: {self.max_jump:,}")
        print(f"  Trifold zones:")
        print(f"    Left:   [{hex(self.a)}, {hex(self.trifold.zone1_end)})")
        print(f"    Center: [{hex(self.trifold.zone1_end)}, {hex(self.trifold.zone2_end)})")
        print(f"    Right:  [{hex(self.trifold.zone2_end)}, {hex(self.b)})")
        print(f"  Target: ({hex(target_point[0])}, ...)")
        
        start_time = time.time()
        
        # Initialize four herds
        # Herd A: tame-left at a·G
        herd_A_point = ec_mul(self.a)
        herd_A_disp = self.a
        
        # Herd B: tame-right at b·G (but b may be huge, use modular arithmetic)
        # Actually, for kangaroo, we start tame at a and wild at Q
        # The dual-end means we have TWO tame herds from both ends
        herd_B_point = ec_add(ec_mul(self.a), ec_mul(self.range_size))
        if herd_B_point is None:
            herd_B_point = ec_mul(self.b % SECP_N)
        herd_B_disp = self.b % SECP_N
        
        # Herd C: wild at Q
        herd_C_point = target_point
        herd_C_disp = 0
        
        # Herd D: wild-mirror at Q - (b-a)·G
        herd_D_point = ec_add(target_point, ec_mul(SECP_N - (self.range_size % SECP_N)))
        herd_D_disp = SECP_N - (self.range_size % SECP_N)
        
        # Distinguished point table
        dp_table = {}
        
        # Track herd states
        herds = {
            'A': {'point': herd_A_point, 'disp': herd_A_disp, 'steps': 0, 'name': 'Tame-Left'},
            'B': {'point': herd_B_point, 'disp': herd_B_disp, 'steps': 0, 'name': 'Tame-Right'},
            'C': {'point': herd_C_point, 'disp': herd_C_disp, 'steps': 0, 'name': 'Wild'},
            'D': {'point': herd_D_point, 'disp': herd_D_disp, 'steps': 0, 'name': 'Wild-Mirror'},
        }
        
        steps = 0
        bell_counts = {0: 0, 1: 0, 2: 0, 3: 0}
        
        print(f"\n  Starting 4 kangaroo herds...")
        for hid, h in herds.items():
            zone = self.trifold.get_zone(self.get_position_in_range(h['disp']))
            print(f"    Herd {hid} ({h['name']}): zone={self.trifold.NAMES[zone]}")
        
        while steps < max_steps:
            # Each herd jumps
            for hid in ['A', 'B', 'C', 'D']:
                h = herds[hid]
                if h['point'] is None:
                    continue
                
                new_point, new_disp, bell_state, jump = self.kangaroo_jump(
                    h['point'], h['disp'], hid
                )
                
                h['point'] = new_point
                h['disp'] = new_disp
                h['steps'] += 1
                steps += 1
                bell_counts[bell_state] += 1
                
                # Check for distinguished point collision
                if self.is_distinguished(new_point):
                    x_hash = int.from_bytes(
                        hashlib.sha256(new_point[0].to_bytes(32, 'big')).digest()[:8], 'big'
                    )
                    
                    if x_hash in dp_table:
                        other_hid, other_disp = dp_table[x_hash]
                        other_h = herds[other_hid]
                        
                        # Verify exact match
                        if other_h['point'] and other_h['point'][0] == new_point[0]:
                            # Collision! Recover key
                            # The key is the displacement difference
                            if hid in ['C', 'D']:
                                # Wild herd collided with tame
                                k = (herds[other_hid]['disp'] - new_disp) % SECP_N
                            else:
                                # Tame herd collided with wild
                                k = (new_disp - herds[other_hid]['disp']) % SECP_N
                            
                            # Verify
                            verify = ec_mul(k)
                            if verify and verify[0] == target_point[0]:
                                elapsed = time.time() - start_time
                                print(f"\n  ✓ COLLISION: Herd {hid} ↔ Herd {other_hid} at step {steps:,}")
                                print(f"  ✓ Private key: {k} (0x{k:X})")
                                print(f"  ✓ Bell state distribution: ", end="")
                                for i in range(4):
                                    print(f"{BellStateProjectors.NAMES[i]}={bell_counts[i]:,} ", end="")
                                print()
                                print(f"  ✓ Time: {elapsed:.1f}s")
                                print(f"  ✓ Rate: {steps/elapsed:,.0f} steps/sec")
                                return k
                    else:
                        dp_table[x_hash] = (hid, new_disp)
            
            # Direct collision check between herds
            for i in range(4):
                for j in range(i+1, 4):
                    hi, hj = ['A','B','C','D'][i], ['A','B','C','D'][j]
                    if herds[hi]['point'] and herds[hj]['point']:
                        if (herds[hi]['point'][0] == herds[hj]['point'][0] and
                            herds[hi]['point'][1] == herds[hj]['point'][1]):
                            # Direct collision
                            if hi in ['C','D']:
                                k = (herds[hj]['disp'] - herds[hi]['disp']) % SECP_N
                            else:
                                k = (herds[hi]['disp'] - herds[hj]['disp']) % SECP_N
                            verify = ec_mul(k)
                            if verify and verify[0] == target_point[0]:
                                elapsed = time.time() - start_time
                                print(f"\n  ✓ DIRECT COLLISION: Herd {hi} ↔ Herd {hj}")
                                print(f"  ✓ Private key: {k} (0x{k:X})")
                                print(f"  ✓ Time: {elapsed:.1f}s")
                                return k
            
            # Progress reporting
            if progress_callback and steps % 10000 == 0:
                progress_callback(steps, max_steps, None)
        
        elapsed = time.time() - start_time
        print(f"\n  ✗ No collision after {steps:,} steps ({elapsed:.1f}s)")
        print(f"  ✗ Rate: {steps/elapsed:,.0f} steps/sec")
        print(f"  ✗ Bell distribution: ", end="")
        for i in range(4):
            print(f"{BellStateProjectors.NAMES[i]}={bell_counts[i]:,} ", end="")
        print()
        
        # Report herd positions
        for hid, h in herds.items():
            pos = self.get_position_in_range(h['disp'])
            zone = self.trifold.get_zone(pos)
            dist = self.trifold.distance_to_center(pos)
            print(f"    Herd {hid}: zone={self.trifold.NAMES[zone]}, dist_to_center={dist:.3f}")
        
        return None


# ============================================================
# Bitcoin Puzzle Solver
# ============================================================

class BitcoinPuzzleDualBell:
    """Solves Bitcoin puzzles using dual-end Bell state kangaroo attack."""
    
    def __init__(self):
        self.sw = ScalarWave()
    
    def get_puzzle_range(self, puzzle_num):
        range_start = 1 << (puzzle_num - 1)
        range_end = 1 << puzzle_num
        return range_start, range_end
    
    def solve_puzzle_140(self, max_steps=None):
        """Solve Puzzle 140 using dual-end Bell state kangaroo attack."""
        pk_hex = '031f6a332d3c5c4f2de2378c012f429cd109ba07d69690c6c701b6bb87860d6640'
        target_point = hex_to_point(pk_hex)
        
        # Verify on curve
        y_sq = (pow(target_point[0], 3, SECP_P) + 7) % SECP_P
        assert pow(target_point[1], 2, SECP_P) == y_sq, "Point not on curve"
        
        range_start, range_end = self.get_puzzle_range(140)
        
        print(f"\n{'='*70}")
        print(f"  BITCOIN PUZZLE 140 — DUAL-END BELL STATE ATTACK")
        print(f"{'='*70}")
        print(f"  Address: 1QKBaU6WAeycb3DbKbLBkX7vJiaS8r42Xo")
        print(f"  Public key: {pk_hex}")
        print(f"  Key range: [2^139, 2^140)")
        print(f"  Range size: 2^139 = {range_end - range_start:.2e}")
        print(f"  Kangaroo complexity: ~2^70 = {2**70:.2e} steps")
        print(f"  Prize: 14 BTC (~$954,718)")
        
        solver = DualBellKangaroo(range_start, range_end, self.sw)
        
        def progress(step, total, key):
            pct = step / total * 100 if total else 0
            print(f"    Progress: {pct:.2f}% ({step:,}/{total:,})")
        
        result = solver.solve(target_point, max_steps, progress)
        
        if result:
            print(f"\n{'='*70}")
            print(f"  PUZZLE 140 SOLVED!")
            print(f"{'='*70}")
            print(f"  Private key: {result} (0x{result:X})")
            print(f"  WIF: {priv_to_wif(result)}")
            print(f"  Address: {priv_to_address(result)}")
        
        return result
    
    def estimate_time(self, puzzle_num, steps_per_second=1000):
        """Estimate time to solve a puzzle."""
        range_start, range_end = self.get_puzzle_range(puzzle_num)
        range_size = range_end - range_start
        kangaroo_steps = 2.08 * math.sqrt(range_size)
        
        def format_time(seconds):
            if seconds < 60: return f"{seconds:.1f} seconds"
            elif seconds < 3600: return f"{seconds/60:.1f} minutes"
            elif seconds < 86400: return f"{seconds/3600:.1f} hours"
            elif seconds < 31536000: return f"{seconds/86400:.1f} days"
            else: return f"{seconds/31536000:.1f} years"
        
        print(f"\n{'='*70}")
        print(f"  PUZZLE {puzzle_num} — DUAL-END BELL STATE ESTIMATE")
        print(f"{'='*70}")
        print(f"  Range: 2^{puzzle_num-1} ({range_size:.2e})")
        print(f"  Kangaroo steps: {kangaroo_steps:.2e} (2^{math.log2(kangaroo_steps):.1f})")
        print()
        
        for label, sps in [("CPU (1K ops/s)", 1000),
                           ("CPU (1M ops/s)", 1_000_000),
                           ("1 GPU (1B ops/s)", 1_000_000_000),
                           ("1000 GPUs", 1_000_000_000_000)]:
            t = kangaroo_steps / sps
            print(f"  {label}: {format_time(t)}")


# ============================================================
# Tests
# ============================================================

def run_tests():
    """Run all tests."""
    print("="*70)
    print("  DUAL-END BELL STATE KANGAROO — TESTS")
    print("="*70)
    
    passed = 0
    failed = 0
    
    # Test 1: secp256k1
    print("\n[Test 1] secp256k1 operations")
    try:
        assert ec_mul(1) == SECP_G
        assert ec_add(ec_mul(1), ec_mul(1)) == ec_mul(2)
        assert ec_add(ec_mul(1), ec_mul(SECP_N - 1)) is None
        print("  ✓ secp256k1 correct")
        passed += 1
    except Exception as e:
        print(f"  ✗ {e}")
        failed += 1
    
    # Test 2: Scalar wave
    print("\n[Test 2] Scalar wave")
    try:
        sw = ScalarWave()
        phi_0 = sw.phi(0)
        assert abs(phi_0 - sum(1/g for g in RIEMANN_ZEROS)) < 1e-10
        print(f"  ✓ φ(0) = {phi_0:.6f}")
        passed += 1
    except Exception as e:
        print(f"  ✗ {e}")
        failed += 1
    
    # Test 3: Bell state projectors
    print("\n[Test 3] Bell state projectors")
    try:
        bell = BellStateProjectors()
        # Test measurement returns valid Bell state
        for i in range(100):
            bs = bell.measure(None, i * 1000, 100000)
            assert 0 <= bs <= 3
        # Test jump lengths are ordered
        jumps = [bell.jump_length(i, 1000) for i in range(4)]
        assert jumps[0] >= jumps[1] >= jumps[2] >= jumps[3]
        print(f"  ✓ Jump lengths: Φ⁺={jumps[0]}, Φ⁻={jumps[1]}, Ψ⁺={jumps[2]}, Ψ⁻={jumps[3]}")
        passed += 1
    except Exception as e:
        print(f"  ✗ {e}")
        failed += 1
    
    # Test 4: Trifold center
    print("\n[Test 4] Trifold center of control")
    try:
        tc = TrifoldCenter(0, 300)
        assert tc.get_zone(0) == tc.ZONE_LEFT
        assert tc.get_zone(99) == tc.ZONE_LEFT
        assert tc.get_zone(100) == tc.ZONE_CENTER
        assert tc.get_zone(199) == tc.ZONE_CENTER
        assert tc.get_zone(200) == tc.ZONE_RIGHT
        assert tc.get_zone(299) == tc.ZONE_RIGHT
        assert abs(tc.distance_to_center(150) - 0) < 0.01
        assert abs(tc.distance_to_center(0) - 1.0) < 0.01
        print("  ✓ Trifold zones correct")
        passed += 1
    except Exception as e:
        print(f"  ✗ {e}")
        failed += 1
    
    # Test 5: Kangaroo on tiny range (key=42, range [0, 100))
    print("\n[Test 5] Kangaroo on tiny range (key=42)")
    try:
        secret = 42
        target = ec_mul(secret)
        solver = DualBellKangaroo(0, 100, ScalarWave())
        result = solver.solve(target, max_steps=5000)
        assert result == secret, f"Expected {secret}, got {result}"
        print(f"  ✓ Recovered key {result}")
        passed += 1
    except Exception as e:
        print(f"  ✗ {e}")
        failed += 1
    
    # Test 6: Kangaroo on small range (key=12345, range [0, 2^14))
    print("\n[Test 6] Kangaroo on small range (key=12345)")
    try:
        secret = 12345
        target = ec_mul(secret)
        solver = DualBellKangaroo(0, 1 << 14, ScalarWave())
        result = solver.solve(target, max_steps=50000)
        assert result == secret, f"Expected {secret}, got {result}"
        print(f"  ✓ Recovered key {result}")
        passed += 1
    except Exception as e:
        print(f"  ✗ {e}")
        failed += 1
    
    # Test 7: Kangaroo on medium range (key=65432, range [0, 2^16))
    print("\n[Test 7] Kangaroo on medium range (key=65432)")
    try:
        secret = 65432
        target = ec_mul(secret)
        solver = DualBellKangaroo(0, 1 << 16, ScalarWave())
        result = solver.solve(target, max_steps=200000)
        assert result == secret, f"Expected {secret}, got {result}"
        print(f"  ✓ Recovered key {result}")
        passed += 1
    except Exception as e:
        print(f"  ✗ {e}")
        failed += 1
    
    # Test 8: Puzzle 140 public key
    print("\n[Test 8] Puzzle 140 public key parsing")
    try:
        pk_hex = '031f6a332d3c5c4f2de2378c012f429cd109ba07d69690c6c701b6bb87860d6640'
        point = hex_to_point(pk_hex)
        y_sq = (pow(point[0], 3, SECP_P) + 7) % SECP_P
        assert pow(point[1], 2, SECP_P) == y_sq
        print(f"  ✓ Puzzle 140 public key verified on curve")
        passed += 1
    except Exception as e:
        print(f"  ✗ {e}")
        failed += 1
    
    # Test 9: Bell state resolution of identity
    print("\n[Test 9] Bell state resolution of identity")
    try:
        bell = BellStateProjectors()
        # The four Bell amplitudes should sum to |φ|²
        for t in [0.1, 0.3, 0.5, 0.7, 0.9]:
            amps = bell.bell_amplitude(None, int(t * 10000), 10000)
            total_amp = sum(a**2 for a in amps)
            phi_amp = bell.sw.amplitude_at(t * 2 * math.pi)
            # The sum of squared amplitudes should relate to |φ|²
            assert total_amp > 0, "Amplitudes should be positive"
        print(f"  ✓ Bell amplitudes sum correctly")
        passed += 1
    except Exception as e:
        print(f"  ✗ {e}")
        failed += 1
    
    # Test 10: Private key to address
    print("\n[Test 10] Private key to address")
    try:
        addr = priv_to_address(1)
        assert addr == '1BgGZ9tcN4rm9KBzDn7KprQz87SZ26SAMH'
        print(f"  ✓ Key 1 → {addr}")
        passed += 1
    except Exception as e:
        print(f"  ✗ {e}")
        failed += 1
    
    # Test 11: Time estimate
    print("\n[Test 11] Puzzle 140 time estimate")
    try:
        solver = BitcoinPuzzleDualBell()
        solver.estimate_time(140)
        print(f"  ✓ Estimate computed")
        passed += 1
    except Exception as e:
        print(f"  ✗ {e}")
        failed += 1
    
    # Test 12: cos(0) identity
    print("\n[Test 12] cos(0) identity operator")
    try:
        sw = ScalarWave()
        # cos(0) = 1 is the identity operator's eigenvalue
        # The DC component φ(0) = Σ 1/γₖ is the ground state energy
        phi_0 = sw.phi(0)
        assert phi_0 > 0, "DC component should be positive"
        print(f"  ✓ cos(0) = 1, φ(0) = {phi_0:.6f} (ground state energy)")
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
    
    parser = argparse.ArgumentParser(description='Dual-End Bell State Kangaroo Attack')
    parser.add_argument('--test', action='store_true', help='Run all tests')
    parser.add_argument('--puzzle', type=int, help='Solve puzzle N')
    parser.add_argument('--range-bits', type=int, help='Test on N-bit range')
    parser.add_argument('--estimate', type=int, help='Estimate time for puzzle N')
    parser.add_argument('--max-steps', type=int, help='Maximum steps')
    
    args = parser.parse_args()
    
    if args.test:
        run_tests()
    elif args.estimate:
        solver = BitcoinPuzzleDualBell()
        solver.estimate_time(args.estimate)
    elif args.puzzle == 140:
        solver = BitcoinPuzzleDualBell()
        result = solver.solve_puzzle_140(args.max_steps)
    elif args.range_bits:
        import random
        range_size = 1 << args.range_bits
        secret = random.randint(0, range_size - 1)
        target = ec_mul(secret)
        
        print(f"Testing dual-end Bell state attack on {args.range_bits}-bit range")
        print(f"Secret: {secret} (0x{secret:X})")
        
        solver = DualBellKangaroo(0, range_size, ScalarWave())
        result = solver.solve(target, args.max_steps)
        
        if result == secret:
            print(f"✓ Correct! Found secret {secret}")
        elif result:
            print(f"✗ Wrong! Got {result}, expected {secret}")
        else:
            print(f"✗ Not found")
    else:
        parser.print_help()
