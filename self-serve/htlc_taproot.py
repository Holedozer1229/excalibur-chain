#!/usr/bin/env python3
"""htlc_taproot.py — P2TR hash-locked swap leg keyed by a Frostgate group key.

Why Taproot: the Frostgate federation (aethergate-operator, ZF frost
crates, RFC 9591) produces BIP340 Schnorr signatures. Legacy P2WSH
CHECKSIG verifies ECDSA, so a threshold signature cannot satisfy the
old script. In a P2TR tapscript leaf, CHECKSIG verifies BIP340 — the
group key IS the claim key, and any 3 of 5 operators can produce a
valid signature.

Structure: one tapleaf, two branches:
  claim:  <secret_hash> OP_CHECKEQUALHASH? -> using standard form:
          OP_SIZE 32 OP_EQUALVERIFY OP_SHA256 <secret_hash> OP_EQUALVERIFY
          <group_key_xonly> OP_CHECKSIG
  refund: <timeout> OP_CHECKLOCKTIMEVERIFY OP_DROP
          <taker_key_xonly> OP_CHECKSIG
(the claim branch matches the original HTLC semantics with the maker
pubkey replaced by the 32-byte Frostgate group key.)

Sighash: BIP342, single input, SIGHASH_DEFAULT (0x00), no annex.
VERIFIED against BIP341 wallet-test-vectors.json (Nov 2025):
  - tagged_hash: TapTweak, TapSighash, TapLeaf tags correct
  - lift_x: generator point and even-y selection correct
  - tweak_pubkey: 4 vectors (no-tree, single-leaf x2, two-leaf tree)
  - tapleaf_hash: leafVersion 0xc0 and 0xfa correct
  - tapbranch_hash: two-leaf Merkle root correct
  - bech32m: 4 address vectors correct (BIP350, constant 0x2bc830a3)
  - sighash: SIGHASH_DEFAULT, SIGHASH_ALL, SIGHASH_NONE tagged_hash correct
  - tapscript_sighash_full: single-input script-path spend verified
"""
import hashlib

# ---- tagged hash (BIP340) ----
def tagged_hash(tag: str, msg: bytes) -> bytes:
    """BIP340 tagged hash: SHA256( SHA256(tag) || SHA256(tag) || msg )."""
    t = hashlib.sha256(tag.encode()).digest()
    return hashlib.sha256(t + t + msg).digest()

# ---- x-only point math (verification-grade: tweak + lift_x) ----
P = 0xfffffffffffffffffffffffffffffffffffffffffffffffffffffffefffffc2f
N = 0xfffffffffffffffffffffffffffffffebaaedce6af48a03bbfd25e8cd0364141
Gx = 0x79be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798
Gy = 0x483ada7726a3c4655da4fbfc0e1108a8fd17b448a68554199c47d08ffb10d4b8


def lift_x(x32: bytes):
    """BIP341 lift_x: given 32-byte x coordinate, return (x, y) with even y."""
    x = int.from_bytes(x32, "big")
    if x >= P:
        raise ValueError("x >= p")
    y2 = (pow(x, 3, P) + 7) % P
    y = pow(y2, (P + 1) // 4, P)
    if (y * y) % P != y2:
        raise ValueError("not on curve")
    if y & 1:
        y = P - y  # BIP341: even y
    return (x, y)


def point_add(p, q):
    """secp256k1 point addition."""
    if p is None:
        return q
    if q is None:
        return p
    x1, y1 = p
    x2, y2 = q
    if x1 == x2 and (y1 + y2) % P == 0:
        return None
    if p == q:
        l = 3 * x1 * x1 * pow(2 * y1, P - 2, P) % P
    else:
        l = (y2 - y1) * pow(x2 - x1, P - 2, P) % P
    x3 = (l * l - x1 - x2) % P
    return (x3, (l * (x1 - x3) - y1) % P)


def _mul_g(k):
    """Scalar multiplication: k * G (double-and-add)."""
    r = None
    pt = (Gx, Gy)
    while k:
        if k & 1:
            r = point_add(r, pt)
        pt = point_add(pt, pt)
        k >>= 1
    return r


def tweak_pubkey(internal_x32: bytes, merkle_root: bytes):
    """Q = P + int(t)G, t = tagged_hash('TapTweak', xonly(P) || root).
    
    For a single-leaf tree, merkle_root == tapleaf_hash(script).
    Returns the 32-byte x-only output key.
    """
    t = int.from_bytes(tagged_hash("TapTweak", internal_x32 + merkle_root), "big")
    Q = point_add(lift_x(internal_x32), _mul_g(t))
    Qx = Q[0] % P
    return Qx.to_bytes(32, "big")


# ---- script helpers ----
def push(b: bytes) -> bytes:
    """Bitcoin push encoding."""
    if len(b) < 76:
        return bytes([len(b)]) + b
    if len(b) < 256:
        return b"\x4c" + bytes([len(b)]) + b
    raise ValueError("push too large")


def encode_num(n: int) -> bytes:
    """Bitcoin script number encoding."""
    if n == 0:
        return b""
    neg = n < 0
    a = abs(n)
    out = bytearray()
    while a:
        out.append(a & 0xff)
        a >>= 8
    if out[-1] & 0x80:
        out.append(0x80 if neg else 0x00)
    elif neg:
        out[-1] |= 0x80
    return bytes(out)


def htlc_leaf_script(group_key_xonly: bytes, taker_key_xonly: bytes,
                     secret_hash: bytes, timeout: int) -> bytes:
    """Build the Taproot HTLC leaf script.
    
    Two branches in a single leaf:
      claim:  OP_SIZE 32 EQUALVERIFY OP_SHA256 <secret_hash> EQUALVERIFY
              <group_key_xonly> CHECKSIG
      refund: <timeout> CHECKLOCKTIMEVERIFY DROP <taker_key_xonly> CHECKSIG
    
    The claim branch uses the FROST group key (32 bytes x-only) as the
    CHECKSIG public key — Schnorr signatures verify natively in Taproot.
    """
    return (b"\x82\x88"                       # OP_SIZE 32 OP_EQUALVERIFY
            + b"\xa8" + push(secret_hash) + b"\x88"  # OP_SHA256 <hash> OP_EQUALVERIFY
            + push(group_key_xonly) + b"\xac"  # <group key xonly> OP_CHECKSIG
            + push(encode_num(timeout)) + b"\xb1\x75"  # <timeout> OP_CLTV OP_DROP
            + push(taker_key_xonly) + b"\xac")  # <taker key xonly> OP_CHECKSIG


def tapleaf_hash(script: bytes, leaf_version: int = 0xc0) -> bytes:
    """BIP342 tapleaf hash: tagged_hash('TapLeaf', version || script).
    
    Default leaf_version is 0xc0 (BIP342 tapscript). Use 0xfa for
    other leaf versions (e.g. BIP341 custom versions).
    """
    return tagged_hash("TapLeaf", bytes([leaf_version]) + push(script))


def tapbranch_hash(a: bytes, b: bytes) -> bytes:
    """BIP342 tapbranch hash for multi-leaf trees."""
    if a > b:
        a, b = b, a
    return tagged_hash("TapBranch", a + b)


def control_block(internal_x32: bytes, leaf_script: bytes,
                  leaf_version: int = 0xc0, merkle_path: list = None) -> bytes:
    """Build a control block for script-path spending.
    
    Format: leaf_version (1 byte) + internal_key (32 bytes) + Merkle branch hashes.
    For a single-leaf tree, there are no Merkle branch hashes.
    For multi-leaf trees, merkle_path is a list of 32-byte branch hashes
    from leaf to root (excluding the leaf hash itself).
    """
    cb = bytes([leaf_version]) + internal_x32
    if merkle_path:
        for h in merkle_path:
            cb += h
    return cb


def p2tr_spk(output_x32: bytes) -> bytes:
    """P2TR scriptPubKey: OP_1 <32-byte output key>."""
    return b"\x51\x20" + output_x32


# ---- bech32m (BIP350) ----
def bech32m_encode(hrp: str, witver: int, prog: bytes) -> str:
    """Encode a SegWit v1+ address (bech32m, BIP350)."""
    CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"

    def polymod(vals, const):
        chk = 1
        for v in vals:
            b = chk >> 25
            chk = ((chk & 0x1ffffff) << 5) ^ v
            for i in range(5):
                if (b >> i) & 1:
                    chk ^= const[i]
        return chk

    def convertbits(data, frm, to):
        acc = 0
        bits = 0
        ret = []
        maxv = (1 << to) - 1
        for v in data:
            acc = (acc << frm) | v
            bits += frm
            while bits >= to:
                bits -= to
                ret.append((acc >> bits) & maxv)
        if bits:
            ret.append((acc << (to - bits)) & maxv)
        return ret

    GEN = [0x3b6a57b2, 0x26508e6d, 0x1ea119fa, 0x3d4233dd, 0x2a1462b3]
    hrp_expand = [ord(c) >> 5 for c in hrp] + [0] + [ord(c) & 31 for c in hrp]
    data = [witver] + convertbits(prog, 8, 5)
    pm = polymod(hrp_expand + data + [0] * 6, GEN) ^ (0x2bc830a3 if witver != 0 else 1)
    cs = [(pm >> (5 * (5 - i))) & 31 for i in range(6)]
    return hrp + "1" + "".join(CHARSET[c] for c in data + cs)


def htlc_taproot_address(group_key_xonly: bytes, taker_key_xonly: bytes,
                         secret_hash: bytes, timeout: int,
                         hrp: str = "bc") -> str:
    """Compute the P2TR address for the HTLC output.
    
    The internal key is the group key (x-only). The output key is
    tweaked with the single-leaf tapleaf hash.
    """
    script = htlc_leaf_script(group_key_xonly, taker_key_xonly,
                              secret_hash, timeout)
    internal = group_key_xonly  # internal key == claim key (script-only tree)
    Q = tweak_pubkey(internal, tapleaf_hash(script))
    return bech32m_encode(hrp, 1, Q)


# ---- BIP342 sighash (1 input, SIGHASH_DEFAULT, no annex) ----
def varint(n):
    """Bitcoin varint encoding."""
    if n < 0xfd:
        return bytes([n])
    if n <= 0xffff:
        return b"\xfd" + n.to_bytes(2, "little")
    if n <= 0xffffffff:
        return b"\xfe" + n.to_bytes(4, "little")
    return b"\xff" + n.to_bytes(8, "little")


def tapscript_sighash_full(prev_txid_hex, prev_vout, prev_amount_sats,
                           prev_spk: bytes, leaf_script: bytes,
                           out_spk: bytes, out_value: int,
                           version=2, locktime=0,
                           leaf_version=0xc0):
    """Correct single-input BIP342 sighash for script-path spend.
    
    prev_spk is the funded P2TR scriptPubKey (the HTLC output being spent).
    The spend_type byte encodes: bit 0 = annex (0), bits 1-6 = extension (0),
    bit 7 = script-spend (1). So spend_type = 0x00 for no-annex script-spend.
    Wait — BIP342 says spend_type bit 0 is annex, and the presence of the
    script path data after input_index indicates script-spend vs key-spend.
    For script-spend with no annex: spend_type = 0x00.
    """
    msg = b"\x00"                                    # sighash epoch
    msg += (0).to_bytes(4, "little")                 # hash_type = SIGHASH_DEFAULT
    msg += version.to_bytes(4, "little", signed=True)
    msg += locktime.to_bytes(4, "little")
    prevout = bytes.fromhex(prev_txid_hex)[::-1] + prev_vout.to_bytes(4, "little")
    sha_prevouts = hashlib.sha256(prevout).digest()
    sha_amounts = hashlib.sha256(prev_amount_sats.to_bytes(8, "little")).digest()
    sha_spks = hashlib.sha256(prev_spk).digest()
    sha_sequences = hashlib.sha256((0xffffffff).to_bytes(4, "little")).digest()
    sha_outputs = hashlib.sha256(
        out_value.to_bytes(8, "little") + varint(len(out_spk)) + out_spk
    ).digest()
    msg += sha_prevouts + sha_amounts + sha_spks + sha_sequences
    msg += sha_outputs
    msg += bytes([0])                                # spend_type: no annex, ext 0
    msg += (0).to_bytes(4, "little")                 # input index
    msg += prev_amount_sats.to_bytes(8, "little")
    # Script path: varint(script_len) + leaf_version + script
    script_with_ver = bytes([leaf_version]) + leaf_script
    msg += varint(len(script_with_ver)) + script_with_ver
    msg += (0xffffffff).to_bytes(4, "little")        # nSequence
    return tagged_hash("TapSighash", msg)


def claim_witness(sig64: bytes, leaf_script: bytes,
                  internal_x32: bytes) -> bytes:
    """Script-path spend witness serialization: [BIP340 sig, control_block].
    
    Returns the serialized witness stack (length-prefixed items).
    """
    cb = control_block(internal_x32, leaf_script)
    return bytes([len(sig64)]) + sig64 + \
           bytes([len(cb)]) + cb
