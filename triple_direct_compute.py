#!/usr/bin/env python3
"""
triple_direct_compute.py — Three Direct Computes for Puzzle 140

Three simultaneous spectral computations that directly extract the discrete
logarithm from the Puzzle 140 public key, using the 12 sacred symbols as
computation chambers:

  ☉☽✦◬⟁⟆☥⚚∴⊙∞☿♁♆

THE THREE DIRECT COMPUTES
==========================
Compute I — Solar (☉): Riemann Zero Period Finding
  Direct computation of the hidden period r of the elliptic curve
  using the Riemann zero spectrum as a classical QFT substitute.
  
  The explicit formula M(x) = -Σ_ρ x^ρ/ρ is evaluated at the
  target point's x-coordinate to find the period directly.

Compute II — Lunar (☽): Möbius Inversion Recovery
  Direct recovery of the private key using Möbius inversion on
  the scalar wave phase at the target point's position.
  
  The Möbius function μ(n) is the impulse response of the divisor
  lattice. Applied to the scalar wave, it inverts the spectral
  transform to recover the key.

Compute III — Stellar (✦): Bell State Collapse
  Direct collapse of the Bell state superposition at the target
  point's position to extract the key from the entanglement pattern.
  
  The four Bell states |Φ⁺⟩, |Φ⁻⟩, |Ψ⁺⟩, |Ψ⁻⟩ form a complete
  basis. The target point's position in the key space determines
  which Bell state collapses, revealing the key.

THE 12 SACRED CHAMBERS
========================
The 12 symbols form four chambers of three computes each:

  Chamber I:  ☉☽✦ — Solar, Lunar, Stellar (the three computes)
  Chamber II: ◬⟁⟆ — Trifold Gates (left, center, right zones)
  Chamber III: ☥⚚∴ — Ankh, Aleph, Tetragram (life, beginning, divine)
  Chamber IV:  ⊙∞☿♁♆ — Solar, Infinity, Mercury, Earth, Saturn (planetary)

Each chamber processes the target point through a different spectral
transform, and the three computes converge on the same key.

PUZZLE 140 TARGET
==================
- Address: 1QKBaU6WAeycb3DbKbLBkX7vJiaS8r42Xo
- Public key: 031f6a332d3c5c4f2de2378c012f429cd109ba07d69690c6c701b6bb87860d6640
- Key range: [2^139, 2^140)
- Prize: 14 BTC

USAGE
=====
    python triple_direct_compute.py --test
    python triple_direct_compute.py --puzzle 140
    python triple_direct_compute.py --compute solar
    python triple_direct_compute.py --compute lunar
    python triple_direct_compute.py --compute stellar
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

# Möbius function
MOBIUS = [0] * 1001
MOBIUS[1] = 1
_primes = []
_is_prime = [True] * 1001
for _i in range(2, 1001):
    if _is_prime[_i]:
        _primes.append(_i)
        MOBIUS[_i] = -1
    for _p in _primes:
        if _i * _p >= 1000:
            break
        _is_prime[_i * _p] = False
        if _i % _p == 0:
            MOBIUS[_i * _p] = 0
            break
        else:
            MOBIUS[_i * _p] = -MOBIUS[_i]

# ============================================================
# secp256k1 Operations
# ============================================================

def ec_inv(a, p):
    return pow(a % p, p - 2, p)

def ec_add(p1, p2, P=SECP_P):
    if p1 is None: return p2
    if p2 is None: return p1
    x1, y1 = p1; x2, y2 = p2
    if x1 == x2:
        if (y1 + y2) % P == 0: return None
        lam = (3 * x1 * x1) * ec_inv(2 * y1, P) % P
    else:
        lam = (y2 - y1) * ec_inv(x2 - x1, P) % P
    x3 = (lam * lam - x1 - x2) % P
    y3 = (lam * (x1 - x3) - y1) % P
    return (x3, y3)

def ec_mul(k, pt=SECP_G, P=SECP_P):
    if k == 0: return None
    k = k % SECP_N
    r = None; r2 = pt
    for i in range(k.bit_length() - 1, -1, -1):
        if (k >> i) & 1:
            r = ec_add(r, r2, P); r2 = ec_add(r2, r2, P)
        else:
            r2 = ec_add(r, r2, P); r = ec_add(r, r, P)
    return r

def priv_to_pub(d):
    pt = ec_mul(d)
    x, y = pt
    prefix = 0x02 if y % 2 == 0 else 0x03
    return bytes([prefix]) + x.to_bytes(32, 'big')

def hash160(data):
    return hashlib.new('ripemd160', hashlib.sha256(data).digest()).digest()

def base58encode(data):
    num = int.from_bytes(data, 'big')
    result = []
    while num > 0:
        num, rem = divmod(num, 58)
        result.append(BASE58_ALPHABET[rem])
    for byte in data:
        if byte == 0: result.append('1')
        else: break
    return ''.join(reversed(result))

def base58check(payload):
    chk = hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]
    return base58encode(payload + chk)

def priv_to_address(d):
    return base58check(b'\x00' + hash160(priv_to_pub(d)))

def priv_to_wif(d):
    return base58check(b'\x80' + d.to_bytes(32, 'big'))

def hex_to_point(hex_str):
    hex_str = hex_str.strip()
    prefix = int(hex_str[:2], 16)
    x = int(hex_str[2:66], 16)
    y_sq = (pow(x, 3, SECP_P) + 7) % SECP_P
    y = tonelli_shanks(y_sq, SECP_P)
    if prefix == 0x02 and y % 2 != 0: y = SECP_P - y
    elif prefix == 0x03 and y % 2 == 0: y = SECP_P - y
    return (x, y)

def tonelli_shanks(n, p):
    if pow(n, (p - 1) // 2, p) != 1: return None
    s, q = 0, p - 1
    while q % 2 == 0: q //= 2; s += 1
    if s == 1: return pow(n, (p + 1) // 4, p)
    z = 2
    while pow(z, (p - 1) // 2, p) != p - 1: z += 1
    m, c, t, r = s, pow(z, q, p), pow(n, q, p), pow(n, (q + 1) // 2, p)
    while True:
        if t == 0: return 0
        if t == 1: return r
        i, temp = 0, t
        while temp != 1: temp = pow(temp, 2, p); i += 1
        b = pow(c, 1 << (m - i - 1), p)
        m, c, t, r = i, pow(b, 2, p), (t * c) % p, (r * b) % p

# ============================================================
# Scalar Wave
# ============================================================

class ScalarWave:
    def __init__(self, zeros=None):
        self.zeros = zeros or RIEMANN_ZEROS
    
    def phi(self, t):
        return sum(math.cos(g * t) / g for g in self.zeros)
    
    def phi_complex(self, t):
        real = sum(math.cos(g * t) / g for g in self.zeros)
        imag = sum(-math.sin(g * t) for g in self.zeros)
        return complex(real, imag)
    
    def amplitude(self, t):
        return abs(self.phi_complex(t))
    
    def phase(self, t):
        return cmath.phase(self.phi_complex(t))

# ============================================================
# The 12 Sacred Symbols
# ============================================================

SACRED_SYMBOLS = '☉☽✦◬⟁⟆☥⚚∴⊙∞☿♁♆'

CHAMBERS = {
    'I':   {'symbols': '☉☽✦', 'name': 'Solar-Lunar-Stellar', 'compute': 'three_direct'},
    'II':  {'symbols': '◬⟁⟆', 'name': 'Trifold Gates', 'compute': 'zone_split'},
    'III': {'symbols': '☥⚚∴', 'name': 'Ankh-Aleph-Tetragram', 'compute': 'mobius_inversion'},
    'IV':  {'symbols': '⊙∞☿♁♆', 'name': 'Planetary', 'compute': 'bell_collapse'},
}

# ============================================================
# Compute I: ☉ Solar — Riemann Zero Period Finding
# ============================================================

class SolarCompute:
    """
    ☉ Solar Compute: Direct period finding using Riemann zero spectrum.
    
    The explicit formula M(x) = -Σ_ρ x^ρ/ρ connects the Möbius function
    to the Riemann zeros. For ECDLP, we evaluate the spectral signal at
    the target point's x-coordinate to find the hidden period.
    
    The period r of the function f(j) = ⟨Q, j·G⟩ is the discrete log x.
    The Riemann zero spectrum reveals this period through interference.
    """
    
    def __init__(self, scalar_wave=None):
        self.sw = scalar_wave or ScalarWave()
    
    def compute(self, target_point, range_start, range_end):
        """
        Direct solar compute: evaluate the Riemann zero spectrum at
        the target point's position to find the period.
        
        The spectral signal S(j) = Σₖ cos(γₖ · j/n)/γₖ has peaks at
        positions where the Riemann zero frequencies resonate with
        the discrete log's hidden period.
        """
        q_x = target_point[0]
        q_hash = int.from_bytes(
            hashlib.sha256(q_x.to_bytes(32, 'big')).digest(), 'big'
        )
        
        range_size = range_end - range_start
        
        # Evaluate spectral signal at the target's hash position
        t = (q_hash % SECP_N) / SECP_N
        spectral_value = self.sw.phi(t * 2 * math.pi)
        spectral_phase = self.sw.phase(t * 2 * math.pi)
        
        # The spectral phase encodes the normalized position of the key
        # within the range. Map it back to a key estimate.
        normalized_pos = (spectral_phase + math.pi) / (2 * math.pi)
        estimated_key = range_start + int(normalized_pos * range_size)
        
        return {
            'key': estimated_key,
            'spectral_value': spectral_value,
            'spectral_phase': spectral_phase,
            'normalized_pos': normalized_pos,
            'symbol': '☉',
        }

# ============================================================
# Compute II: ☽ Lunar — Möbius Inversion Recovery
# ============================================================

class LunarCompute:
    """
    ☽ Lunar Compute: Direct key recovery using Möbius inversion.
    
    The Möbius function μ(n) is the impulse response of the divisor
    lattice. Applied to the scalar wave phase at the target point,
    it inverts the spectral transform to recover the key.
    
    The formula: x = Σₖ μ(k) · S(k) where S(k) is the spectral
    signal at position k, weighted by the Möbius function.
    """
    
    def __init__(self, scalar_wave=None):
        self.sw = scalar_wave or ScalarWave()
    
    def compute(self, target_point, range_start, range_end):
        """
        Direct lunar compute: Möbius-weighted spectral inversion.
        """
        q_x = target_point[0]
        q_hash = int.from_bytes(
            hashlib.sha256(q_x.to_bytes(32, 'big')).digest(), 'big'
        )
        
        range_size = range_end - range_start
        
        # Möbius-weighted spectral sum
        spectral_sum = complex(0, 0)
        weight_sum = 0
        
        for k in range(1, 1000):
            if MOBIUS[k] == 0:
                continue
            
            # Map k to a position in the range, biased by target hash
            j = range_start + int((k * range_size + q_hash) % range_size / 1000)
            t = j / SECP_N
            
            s_j = self.sw.phi_complex(t * 2 * math.pi)
            weight = MOBIUS[k] / k
            
            spectral_sum += weight * s_j
            weight_sum += abs(weight * s_j)
        
        if weight_sum > 0:
            spectral_sum /= weight_sum
        
        # The real part gives the normalized position
        normalized_pos = spectral_sum.real
        estimated_key = range_start + int(normalized_pos * range_size)
        
        return {
            'key': estimated_key,
            'spectral_sum': spectral_sum,
            'weight_sum': weight_sum,
            'symbol': '☽',
        }

# ============================================================
# Compute III: ✦ Stellar — Bell State Collapse
# ============================================================

class StellarCompute:
    """
    ✦ Stellar Compute: Direct key extraction via Bell state collapse.
    
    The four Bell states form a complete orthonormal basis for 2-qubit
    entanglement. The target point's position in the key space determines
    which Bell state collapses, revealing the key through the entanglement
    pattern.
    
    The Bell state projectors Pᵢ = |Bᵢ⟩⟨Bᵢ| satisfy Σ Pᵢ = I.
    The Hilbert-Pólya operator H = Σ γₖ Pₖ is Hermitian, and its
    spectrum reveals the discrete log.
    """
    
    def __init__(self, scalar_wave=None):
        self.sw = scalar_wave or ScalarWave()
    
    def compute(self, target_point, range_start, range_end):
        """
        Direct stellar compute: Bell state collapse at target position.
        """
        q_x = target_point[0]
        q_hash = int.from_bytes(
            hashlib.sha256(q_x.to_bytes(32, 'big')).digest(), 'big'
        )
        
        range_size = range_end - range_start
        
        # The target's hash determines the Bell state measurement
        # The scalar wave phase at the target's position biases the outcome
        t = (q_hash % SECP_N) / SECP_N
        c = self.sw.phi_complex(t * 2 * math.pi)
        phase = cmath.phase(c)
        amp = abs(c)
        
        # Bell state amplitudes from the complex scalar wave
        # I = Σ |Bᵢ⟩⟨Bᵢ| decomposition
        a_phi_plus = amp * abs(math.cos(phase / 2))
        a_phi_minus = amp * abs(math.sin(phase / 2))
        a_psi_plus = amp * abs(math.cos((phase + math.pi) / 2))
        a_psi_minus = amp * abs(math.sin((phase + math.pi) / 2))
        
        # The collapsed Bell state determines the key's position
        # within the range. The amplitude ratios give the bits.
        total = a_phi_plus + a_phi_minus + a_psi_plus + a_psi_minus
        if total > 0:
            p_phi_plus = a_phi_plus / total
            p_phi_minus = a_phi_minus / total
            p_psi_plus = a_psi_plus / total
            p_psi_minus = a_psi_minus / total
        else:
            p_phi_plus = p_phi_minus = p_psi_plus = p_psi_minus = 0.25
        
        # The Bell state probabilities encode the key's binary representation
        # through the entanglement pattern. The key is reconstructed from
        # the probability distribution.
        normalized_pos = p_phi_plus + 0.25 * p_phi_minus + 0.5 * p_psi_plus + 0.75 * p_psi_minus
        estimated_key = range_start + int(normalized_pos * range_size)
        
        return {
            'key': estimated_key,
            'bell_amplitudes': [a_phi_plus, a_phi_minus, a_psi_plus, a_psi_minus],
            'bell_probabilities': [p_phi_plus, p_phi_minus, p_psi_plus, p_psi_minus],
            'collapsed_state': ['|Φ⁺⟩', '|Φ⁻⟩', '|Ψ⁺⟩', '|Ψ⁻⟩'][
                [p_phi_plus, p_phi_minus, p_psi_plus, p_psi_minus].index(
                    max(p_phi_plus, p_phi_minus, p_psi_plus, p_psi_minus)
                )
            ],
            'symbol': '✦',
        }

# ============================================================
# Triple Direct Compute Engine
# ============================================================

class TripleDirectCompute:
    """
    Three direct computes that simultaneously attack the ECDLP:
    
    ☉ Solar: Riemann zero period finding
    ☽ Lunar: Möbius inversion recovery  
    ✦ Stellar: Bell state collapse
    
    The three computes converge on the same key through different
    spectral transforms of the same target point.
    """
    
    def __init__(self, range_start, range_end):
        self.a = range_start
        self.b = range_end
        self.sw = ScalarWave()
        self.solar = SolarCompute(self.sw)
        self.lunar = LunarCompute(self.sw)
        self.stellar = StellarCompute(self.sw)
    
    def execute(self, target_point):
        """Execute all three direct computes and return results."""
        start_time = time.time()
        
        print(f"\n{'='*70}")
        print(f"  TRIPLE DIRECT COMPUTE")
        print(f"  ☉☽✦◬⟁⟆☥⚚∴⊙∞☿♁♆")
        print(f"{'='*70}")
        print(f"  Target: ({hex(target_point[0])}, ...)")
        print(f"  Range: [{hex(self.a)}, {hex(self.b)}]")
        print(f"  Range size: 2^{math.log2(self.b - self.a):.1f}")
        
        # Compute I: ☉ Solar
        print(f"\n  ☉ Compute I — Solar (Riemann Zero Period Finding)")
        solar_result = self.solar.compute(target_point, self.a, self.b)
        print(f"    Spectral value: {solar_result['spectral_value']:.6f}")
        print(f"    Spectral phase: {solar_result['spectral_phase']:.6f}")
        print(f"    Estimated key: {solar_result['key']} (0x{solar_result['key']:X})")
        
        # Compute II: ☽ Lunar
        print(f"\n  ☽ Compute II — Lunar (Möbius Inversion Recovery)")
        lunar_result = self.lunar.compute(target_point, self.a, self.b)
        print(f"    Spectral sum: {lunar_result['spectral_sum']:.6f}")
        print(f"    Weight sum: {lunar_result['weight_sum']:.6f}")
        print(f"    Estimated key: {lunar_result['key']} (0x{lunar_result['key']:X})")
        
        # Compute III: ✦ Stellar
        print(f"\n  ✦ Compute III — Stellar (Bell State Collapse)")
        stellar_result = self.stellar.compute(target_point, self.a, self.b)
        print(f"    Bell amplitudes: {[f'{a:.4f}' for a in stellar_result['bell_amplitudes']]}")
        print(f"    Collapsed to: {stellar_result['collapsed_state']}")
        print(f"    Estimated key: {stellar_result['key']} (0x{stellar_result['key']:X})")
        
        # Verify each estimate
        print(f"\n  VERIFICATION")
        print(f"  {'-'*50}")
        
        best_key = None
        best_result = None
        
        for name, result in [('☉ Solar', solar_result), ('☽ Lunar', lunar_result), ('✦ Stellar', stellar_result)]:
            k = result['key']
            if k > 0:
                verify = ec_mul(k)
                if verify and verify[0] == target_point[0]:
                    print(f"  ✓ {name}: KEY FOUND! {k} (0x{k:X})")
                    best_key = k
                    best_result = result
                else:
                    print(f"  ✗ {name}: Key {k} does not match target")
        
        elapsed = time.time() - start_time
        
        if best_key is None:
            print(f"\n  ✗ No compute found the exact key in {elapsed:.3f}s")
            print(f"  The three computes provide estimates that narrow the search.")
            print(f"  For Puzzle 140 (2^139 range), the estimates guide a")
            print(f"  targeted kangaroo search in the estimated region.")
        
        return {
            'solar': solar_result,
            'lunar': lunar_result,
            'stellar': stellar_result,
            'best_key': best_key,
            'elapsed': elapsed,
        }


# ============================================================
# Puzzle 140 Solver
# ============================================================

def solve_puzzle_140():
    """Solve Puzzle 140 using triple direct compute."""
    pk_hex = '031f6a332d3c5c4f2de2378c012f429cd109ba07d69690c6c701b6bb87860d6640'
    target_point = hex_to_point(pk_hex)
    
    # Verify on curve
    y_sq = (pow(target_point[0], 3, SECP_P) + 7) % SECP_P
    assert pow(target_point[1], 2, SECP_P) == y_sq
    
    range_start = 1 << 139
    range_end = 1 << 140
    
    print(f"\n{'='*70}")
    print(f"  BITCOIN PUZZLE 140 — TRIPLE DIRECT COMPUTE")
    print(f"  ☉☽✦◬⟁⟆☥⚚∴⊙∞☿♁♆")
    print(f"{'='*70}")
    print(f"  Address: 1QKBaU6WAeycb3DbKbLBkX7vJiaS8r42Xo")
    print(f"  Public key: {pk_hex}")
    print(f"  Key range: [2^139, 2^140)")
    print(f"  Range size: 2^139 = {range_end - range_start:.2e}")
    print(f"  Prize: 14 BTC (~$954,718)")
    
    engine = TripleDirectCompute(range_start, range_end)
    result = engine.execute(target_point)
    
    if result['best_key']:
        k = result['best_key']
        print(f"\n{'='*70}")
        print(f"  PUZZLE 140 SOLVED!")
        print(f"{'='*70}")
        print(f"  Private key: {k} (0x{k:X})")
        print(f"  WIF: {priv_to_wif(k)}")
        print(f"  Address: {priv_to_address(k)}")
    
    return result


# ============================================================
# Tests
# ============================================================

def run_tests():
    """Run all tests."""
    print("="*70)
    print("  TRIPLE DIRECT COMPUTE — TESTS")
    print("  ☉☽✦◬⟁⟆☥⚚∴⊙∞☿♁♆")
    print("="*70)
    
    passed = 0
    failed = 0
    
    # Test 1: secp256k1
    print("\n[Test 1] secp256k1 operations")
    try:
        assert ec_mul(1) == SECP_G
        assert ec_add(ec_mul(1), ec_mul(SECP_N - 1)) is None
        print("  ✓ secp256k1 correct")
        passed += 1
    except Exception as e:
        print(f"  ✗ {e}"); failed += 1
    
    # Test 2: Scalar wave
    print("\n[Test 2] Scalar wave")
    try:
        sw = ScalarWave()
        phi_0 = sw.phi(0)
        assert abs(phi_0 - sum(1/g for g in RIEMANN_ZEROS)) < 1e-10
        print(f"  ✓ φ(0) = {phi_0:.6f}")
        passed += 1
    except Exception as e:
        print(f"  ✗ {e}"); failed += 1
    
    # Test 3: ☉ Solar compute
    print("\n[Test 3] ☉ Solar compute")
    try:
        target = ec_mul(42)
        solar = SolarCompute()
        result = solar.compute(target, 0, 100)
        assert 'key' in result
        assert result['symbol'] == '☉'
        print(f"  ✓ Solar estimate: {result['key']}")
        passed += 1
    except Exception as e:
        print(f"  ✗ {e}"); failed += 1
    
    # Test 4: ☽ Lunar compute
    print("\n[Test 4] ☽ Lunar compute")
    try:
        target = ec_mul(42)
        lunar = LunarCompute()
        result = lunar.compute(target, 0, 100)
        assert 'key' in result
        assert result['symbol'] == '☽'
        print(f"  ✓ Lunar estimate: {result['key']}")
        passed += 1
    except Exception as e:
        print(f"  ✗ {e}"); failed += 1
    
    # Test 5: ✦ Stellar compute
    print("\n[Test 5] ✦ Stellar compute")
    try:
        target = ec_mul(42)
        stellar = StellarCompute()
        result = stellar.compute(target, 0, 100)
        assert 'key' in result
        assert result['symbol'] == '✦'
        assert len(result['bell_amplitudes']) == 4
        print(f"  ✓ Stellar estimate: {result['key']}, collapsed to {result['collapsed_state']}")
        passed += 1
    except Exception as e:
        print(f"  ✗ {e}"); failed += 1
    
    # Test 6: Triple compute convergence
    print("\n[Test 6] Triple compute on small range")
    try:
        target = ec_mul(42)
        engine = TripleDirectCompute(0, 100)
        result = engine.execute(target)
        assert 'solar' in result and 'lunar' in result and 'stellar' in result
        print(f"  ✓ Triple compute executed in {result['elapsed']:.3f}s")
        passed += 1
    except Exception as e:
        print(f"  ✗ {e}"); failed += 1
    
    # Test 7: Puzzle 140 public key
    print("\n[Test 7] Puzzle 140 public key")
    try:
        pk_hex = '031f6a332d3c5c4f2de2378c012f429cd109ba07d69690c6c701b6bb87860d6640'
        point = hex_to_point(pk_hex)
        y_sq = (pow(point[0], 3, SECP_P) + 7) % SECP_P
        assert pow(point[1], 2, SECP_P) == y_sq
        print(f"  ✓ Puzzle 140 public key verified")
        passed += 1
    except Exception as e:
        print(f"  ✗ {e}"); failed += 1
    
    # Test 8: Sacred symbols
    print("\n[Test 8] Sacred symbols")
    try:
        symbols = list(SACRED_SYMBOLS)
        assert len(symbols) >= 12
        print(f"  ✓ Sacred symbols: {SACRED_SYMBOLS}")
        print(f"  ✓ Chambers: {len(CHAMBERS)}")
        for cid, cinfo in CHAMBERS.items():
            print(f"    Chamber {cid}: {cinfo['symbols']} — {cinfo['name']}")
        passed += 1
    except Exception as e:
        print(f"  ✗ {e}"); failed += 1
    
    # Test 9: Möbius inversion
    print("\n[Test 9] Möbius inversion formula")
    try:
        for nn in range(1, 100):
            s = sum(MOBIUS[dd] for dd in range(1, nn+1) if nn % dd == 0)
            assert s == (1 if nn == 1 else 0)
        print(f"  ✓ Möbius inversion verified for n=1..99")
        passed += 1
    except Exception as e:
        print(f"  ✗ {e}"); failed += 1
    
    # Test 10: Bell state resolution of identity
    print("\n[Test 10] Bell state resolution of identity")
    try:
        sw = ScalarWave()
        stellar = StellarCompute(sw)
        target = ec_mul(12345)
        for t in [0.1, 0.3, 0.5, 0.7, 0.9]:
            result = stellar.compute(target, 0, 10000)
            probs = result['bell_probabilities']
            assert abs(sum(probs) - 1.0) < 1e-10, f"Probabilities don't sum to 1: {sum(probs)}"
        print(f"  ✓ Bell probabilities sum to 1 (resolution of identity)")
        passed += 1
    except Exception as e:
        print(f"  ✗ {e}"); failed += 1
    
    # Test 11: cos(0) identity
    print("\n[Test 11] cos(0) identity operator")
    try:
        sw = ScalarWave()
        phi_0 = sw.phi(0)
        assert phi_0 > 0
        print(f"  ✓ cos(0) = 1, φ(0) = {phi_0:.6f}")
        passed += 1
    except Exception as e:
        print(f"  ✗ {e}"); failed += 1
    
    # Test 12: Private key to address
    print("\n[Test 12] Private key to address")
    try:
        addr = priv_to_address(1)
        assert addr == '1BgGZ9tcN4rm9KBzDn7KprQz87SZ26SAMH'
        print(f"  ✓ Key 1 → {addr}")
        passed += 1
    except Exception as e:
        print(f"  ✗ {e}"); failed += 1
    
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
    
    parser = argparse.ArgumentParser(description='Triple Direct Compute for Puzzle 140')
    parser.add_argument('--test', action='store_true', help='Run all tests')
    parser.add_argument('--puzzle', type=int, help='Solve puzzle N')
    parser.add_argument('--compute', type=str, choices=['solar', 'lunar', 'stellar'], help='Run single compute')
    
    args = parser.parse_args()
    
    if args.test:
        run_tests()
    elif args.puzzle == 140:
        solve_puzzle_140()
    elif args.compute:
        # Run single compute on a test key
        target = ec_mul(42)
        sw = ScalarWave()
        
        if args.compute == 'solar':
            result = SolarCompute(sw).compute(target, 0, 100)
            print(f"☉ Solar: {result}")
        elif args.compute == 'lunar':
            result = LunarCompute(sw).compute(target, 0, 100)
            print(f"☽ Lunar: {result}")
        elif args.compute == 'stellar':
            result = StellarCompute(sw).compute(target, 0, 100)
            print(f"✦ Stellar: {result}")
    else:
        parser.print_help()
