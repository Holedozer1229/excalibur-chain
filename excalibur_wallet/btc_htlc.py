"""btc_htlc.py — Bitcoin-side HTLC (P2WSH, SegWit v0), standalone.

This is the BTC leg the wallet was missing: a real Bitcoin hash-time-
locked contract, built, signed and verified inside the wallet. It is
STANDALONE — no EXCAL leg, no atomic-swap state machine, no cross-
chain flow, no watcher, no counterparty coordination. It does not
touch the Strange swap template and does not know any offer lot.

Witness script (P2WSH, SegWit v0), roles named by what they do:
    OP_IF
        OP_SHA256 <secret_hash: 32 bytes> OP_EQUALVERIFY
        <claim_pubkey: 33 bytes> OP_CHECKSIG
    OP_ELSE
        <timeout: script number> OP_CHECKLOCKTIMEVERIFY OP_DROP
        <refund_pubkey: 33 bytes> OP_CHECKSIG
    OP_ENDIF

Claim path (IF branch): witness = [sig, secret_preimage, 0x01,
witness_script]. The claimer reveals the secret by claiming.
Refund path (ELSE branch): witness = [sig, <empty>, witness_script],
valid only in a tx whose locktime is >= timeout and whose spending
input sequence is not 0xffffffff (CLTV rule). The empty push is
OP_0 — the minimal encoding of false; a 1-byte 0x00 push is rejected
by the node as a non-minimal OP_IF argument.

Same script as the self-serve vendored BTC HTLC (self-serve/vendor/
btc_htlc.py) — the two are cross-checked against each other in the
test suite (same params must give the same address and the same
BIP143 sighash). This module is self-contained (stdlib + the repo's
secp256k1 + txscript.hash160 only); it does NOT import the vendored
module, so the wallet stays one package.

Full spend-and-sign protocol, always (Lux's standing order):
  1. build the full transaction (all inputs, all outputs, fee)
  2. sign EVERY input — via a real BIP174 PSBT (unsigned PSBT ->
     partial signatures -> finalize), never by hand-assembling a
     witness
  3. re-verify every signature independently (secp.verify over the
     BIP143 sighash) BEFORE the tx is returned
  4. claim: the secret is checked against the script's hash;
     refund: the CLTV preconditions (locktime, sequence, current
     height >= timeout) are checked before signing
  5. this module NEVER broadcasts. Submitting a signed tx is a
     separate, explicit step (`wallet broadcast --tx HEX --network
     bitcoin --yes`), which re-checks the tx (replay, unspent
     inputs, testmempoolaccept) before it touches a node.

Funding inputs are the wallet's own Bitcoin P2WPKH UTXOs: the same
secp256k1 key that gives the wallet's EXCAL PKH lock gives its
Bitcoin P2WPKH address (same hash160, different encoding). The
caller supplies the UTXO explicitly (txid, vout, value,
scriptPubKey) — the wallet does NOT scan Bitcoin for it, and it
refuses an input whose scriptPubKey is not a P2WPKH of a wallet
key. The Bitcoin node (gettxout) is the final unspent check, done
by broadcast.py before submit.

Fees: sats/vB, two-pass like txbuild.build_send (measure with a
max-size placeholder signature, set the fee from the exact vsize,
then build + sign for real). Dust is 546 sats (Bitcoin standard).
Networks: mainnet (bc), testnet (tb), regtest (bcrt), signet (tb).

No secrets are ever written to a file or a log by this module. The
secret is passed in by the caller for a claim and is never stored;
only its SHA256 is recorded (by the CLI's lock record).
"""
import base64
import hashlib
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import secp256k1 as secp
from txscript import hash160

# ---------------------------------------------------------------- errors
class BtcHtlcError(Exception):
    pass


# ---------------------------------------------------------------- constants
SIGHASH_ALL = 1
LOCKTIME_THRESHOLD = 500_000_000  # below this, locktime is a block height
DUST_SATS = 546
SEQ_FINAL = 0xFFFFFFFF
SEQ_CLTV = 0xFFFFFFFE  # non-final, so CLTV can apply
MAX_DER_SIG_LEN = 73  # 72-byte DER + 1 sighash byte (placeholder size)

OP_0 = 0x00
OP_IF = 0x63
OP_ELSE = 0x67
OP_ENDIF = 0x68
OP_DROP = 0x75
OP_EQUALVERIFY = 0x88
OP_SHA256 = 0xA8
OP_CHECKSIG = 0xAC
OP_CHECKLOCKTIMEVERIFY = 0xB1

NETWORKS = {
    "mainnet": "bc",
    "testnet": "tb",
    "regtest": "bcrt",
    "signet": "tb",
}

# BIP174 PSBT key types
PSBT_GLOBAL_UNSIGNED_TX = 0x00
PSBT_IN_WITNESS_UTXO = 0x01
PSBT_IN_PARTIAL_SIG = 0x02
PSBT_IN_SIGHASH_TYPE = 0x03
PSBT_IN_WITNESS_SCRIPT = 0x05
PSBT_IN_FINAL_SCRIPTWITNESS = 0x08


# ---------------------------------------------------------------- encoding
def push(data: bytes) -> bytes:
    """Bitcoin push encoding for a data item."""
    n = len(data)
    if n < 76:
        return bytes([n]) + data
    if n <= 255:
        return bytes([76, n]) + data
    if n <= 65535:
        return bytes([77]) + n.to_bytes(2, "little") + data
    return bytes([78]) + n.to_bytes(4, "little") + data


def encode_num(value: int) -> bytes:
    """Minimal script-number encoding (Bitcoin CScriptNum)."""
    if value == 0:
        return b""
    neg = value < 0
    a = abs(value)
    out = bytearray()
    while a:
        out.append(a & 0xFF)
        a >>= 8
    if out[-1] & 0x80:
        out.append(0x80 if neg else 0x00)
    elif neg:
        out[-1] |= 0x80
    return bytes(out)


def decode_num(data: bytes) -> int:
    if len(data) == 0:
        return 0
    value = int.from_bytes(data, "little")
    if data[-1] & 0x80:
        value &= ~(0x80 << (8 * (len(data) - 1)))
        value = -value
    return value


def varint(n: int) -> bytes:
    if n < 253:
        return bytes([n])
    if n <= 65535:
        return b"\xfd" + n.to_bytes(2, "little")
    if n <= 4294967295:
        return b"\xfe" + n.to_bytes(4, "little")
    return b"\xff" + n.to_bytes(8, "little")


def sha256d(data: bytes) -> bytes:
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()


# ---------------------------------------------------------------- bech32 (BIP173)
_BECH32 = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"


def _polymod(vals):
    gen = [0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3]
    chk = 1
    for v in vals:
        b = chk >> 25
        chk = ((chk & 0x1FFFFFF) << 5) ^ v
        for i in range(5):
            if (b >> i) & 1:
                chk ^= gen[i]
    return chk


def _hrp_expand(hrp):
    return [ord(c) >> 5 for c in hrp] + [0] + [ord(c) & 31 for c in hrp]


def _convertbits(data, frm, to, pad=True):
    acc = val = 0
    bits = 0
    out = []
    maxv = (1 << to) - 1
    for v in data:
        val = (val << frm) | v
        bits += frm
        while bits >= to:
            bits -= to
            out.append((val >> bits) & maxv)
    if pad:
        if bits:
            out.append((val << (to - bits)) & maxv)
    elif bits >= frm or ((val << (to - bits)) & maxv):
        return None
    return out


def bech32_encode(hrp: str, witver: int, prog: bytes) -> str:
    data = [witver] + _convertbits(prog, 8, 5)
    pm = _polymod(_hrp_expand(hrp) + data + [0] * 6) ^ 1
    chk = [(pm >> 5 * (5 - i)) & 31 for i in range(6)]
    return hrp + "1" + "".join(_BECH32[d] for d in data + chk)


def bech32_decode(addr: str):
    """(hrp, witver, program); raises BtcHtlcError on bad checksum/format."""
    if not isinstance(addr, str):
        raise BtcHtlcError("address must be a string")
    addr = addr.lower()
    pos = addr.rfind("1")
    if pos < 1 or pos + 7 > len(addr):
        raise BtcHtlcError("bad bech32 address")
    hrp, tail = addr[:pos], addr[pos + 1:]
    try:
        vals = [_BECH32.index(c) for c in tail]
    except ValueError:
        raise BtcHtlcError("bad bech32 character in address")
    if _polymod(_hrp_expand(hrp) + vals) != 1:
        raise BtcHtlcError("bad bech32 checksum")
    prog = _convertbits(vals[1:-6], 5, 8, False)
    if prog is None:
        raise BtcHtlcError("bad bech32 program bits")
    return hrp, vals[0], bytes(prog)


def script_pubkey_from_address(addr: str) -> bytes:
    """scriptPubKey for a SegWit v0 bech32 address (P2WPKH/P2WSH)."""
    hrp, witver, prog = bech32_decode(addr)
    if witver != 0 or len(prog) not in (20, 32):
        raise BtcHtlcError(
            f"address {addr!r} is not a SegWit v0 P2WPKH/P2WSH address")
    return bytes([OP_0]) + push(prog)


def hrp_for_network(network: str) -> str:
    try:
        return NETWORKS[network]
    except KeyError:
        raise BtcHtlcError(
            f"unknown Bitcoin network {network!r} (want one of "
            f"{sorted(NETWORKS)})")


# ---------------------------------------------------------------- pubkey validation
def validate_pubkey(pub: bytes, role: str) -> None:
    if len(pub) != 33 or pub[0] not in (0x02, 0x03):
        raise BtcHtlcError(
            f"{role} pubkey must be 33-byte compressed (got {len(pub)} bytes)")
    try:
        secp.decompress(pub)  # raises if not on curve
    except Exception as e:
        raise BtcHtlcError(f"{role} pubkey is not a valid secp256k1 point: {e}")


# ---------------------------------------------------------------- witness script
def build_witness_script(claim_pub: bytes, refund_pub: bytes,
                         secret_hash: bytes, timeout: int) -> bytes:
    """Build the HTLC witness script. Roles are NOT interchangeable:
    the IF branch is the claimer (secret + claim key), the ELSE branch
    is the refunder (timeout + refund key)."""
    validate_pubkey(claim_pub, "claim")
    validate_pubkey(refund_pub, "refund")
    if len(secret_hash) != 32:
        raise BtcHtlcError(
            f"secret_hash must be 32 bytes (got {len(secret_hash)})")
    if not (0 < timeout < LOCKTIME_THRESHOLD):
        raise BtcHtlcError(
            f"timeout must be a block height in (0, {LOCKTIME_THRESHOLD}) "
            f"(got {timeout})")
    if claim_pub == refund_pub:
        raise BtcHtlcError("claim and refund pubkeys must differ")
    return (
        bytes([OP_IF])
        + bytes([OP_SHA256]) + push(secret_hash) + bytes([OP_EQUALVERIFY])
        + push(claim_pub) + bytes([OP_CHECKSIG])
        + bytes([OP_ELSE])
        + push(encode_num(timeout)) + bytes([OP_CHECKLOCKTIMEVERIFY, OP_DROP])
        + push(refund_pub) + bytes([OP_CHECKSIG])
        + bytes([OP_ENDIF])
    )


def parse_witness_script(script: bytes):
    """Parse and strictly validate a witness script.

    Returns {claim_pubkey, refund_pubkey, secret_hash, timeout}.
    Raises BtcHtlcError on any structural deviation, including
    swapped pubkey roles (the IF branch must hold the claim key, the
    ELSE branch the refund key). This checks structure only, not
    signatures."""
    try:
        i = 0

        def expect_op(op):
            nonlocal i
            if i >= len(script) or script[i] != op:
                raise BtcHtlcError(f"expected opcode 0x{op:02x} at offset {i}")
            i += 1

        def expect_push():
            nonlocal i
            if i >= len(script):
                raise BtcHtlcError("truncated push")
            n = script[i]
            i += 1
            if n >= 76:
                raise BtcHtlcError("non-minimal push in HTLC script")
            data = script[i:i + n]
            if len(data) != n:
                raise BtcHtlcError("truncated push data")
            i += n
            return data

        expect_op(OP_IF)
        expect_op(OP_SHA256)
        secret_hash = expect_push()
        if len(secret_hash) != 32:
            raise BtcHtlcError("secret_hash push must be 32 bytes")
        expect_op(OP_EQUALVERIFY)
        claim_pub = expect_push()
        expect_op(OP_CHECKSIG)
        expect_op(OP_ELSE)
        timeout_bytes = expect_push()
        timeout = decode_num(timeout_bytes)
        expect_op(OP_CHECKLOCKTIMEVERIFY)
        expect_op(OP_DROP)
        refund_pub = expect_push()
        expect_op(OP_CHECKSIG)
        expect_op(OP_ENDIF)
        if i != len(script):
            raise BtcHtlcError("trailing bytes after ENDIF")
    except BtcHtlcError:
        raise
    except Exception as e:
        raise BtcHtlcError(f"malformed witness script: {e}")
    validate_pubkey(claim_pub, "claim (IF branch)")
    validate_pubkey(refund_pub, "refund (ELSE branch)")
    if not (0 < timeout < LOCKTIME_THRESHOLD):
        raise BtcHtlcError(f"timeout out of block-height range: {timeout}")
    return {
        "claim_pubkey": claim_pub,
        "refund_pubkey": refund_pub,
        "secret_hash": secret_hash,
        "timeout": timeout,
    }


def witness_script_hash(script: bytes) -> bytes:
    return hashlib.sha256(script).digest()


def p2wsh_script_pubkey(script: bytes) -> bytes:
    """OP_0 <SHA256(witness_script)>."""
    return bytes([OP_0]) + push(witness_script_hash(script))


def p2wsh_address(script: bytes, network: str = "mainnet") -> str:
    """Native SegWit v0 P2WSH address (bech32)."""
    return bech32_encode(hrp_for_network(network), 0,
                         witness_script_hash(script))


def p2wpkh_script_pubkey(pub: bytes) -> bytes:
    """OP_0 <hash160(pubkey)>."""
    validate_pubkey(pub, "P2WPKH")
    return bytes([OP_0]) + push(hash160(pub))


def p2wpkh_address(pub: bytes, network: str = "mainnet") -> str:
    """Native SegWit v0 P2WPKH address (bech32)."""
    validate_pubkey(pub, "P2WPKH")
    return bech32_encode(hrp_for_network(network), 0, hash160(pub))


def build_lock(claim_pub: bytes, refund_pub: bytes, secret_hash: bytes,
               timeout: int, network: str = "mainnet") -> dict:
    """Build everything needed to fund the lock. No signing, no keys."""
    script = build_witness_script(claim_pub, refund_pub, secret_hash,
                                  timeout)
    parsed = parse_witness_script(script)
    assert parsed["claim_pubkey"] == claim_pub
    assert parsed["refund_pubkey"] == refund_pub
    return {
        "witness_script_hex": script.hex(),
        "witness_script_hash": witness_script_hash(script).hex(),
        "script_pubkey_hex": p2wsh_script_pubkey(script).hex(),
        "address": p2wsh_address(script, network),
        "claim_pubkey": claim_pub.hex(),
        "refund_pubkey": refund_pub.hex(),
        "secret_hash": secret_hash.hex(),
        "timeout": timeout,
        "network": network,
    }


def secret_hash_of(secret: bytes) -> bytes:
    """SHA256 of a 32-byte secret preimage."""
    if len(secret) != 32:
        raise BtcHtlcError(f"secret must be 32 bytes (got {len(secret)})")
    return hashlib.sha256(secret).digest()


# ---------------------------------------------------------------- segwit tx
# Tx dict convention (same as the vendored BTC HTLC module, so the two
# can be cross-checked):
#   version: int
#   vin: [{prev_txid: 32 bytes in WIRE order, prev_vout: int,
#          sequence: int, script_sig: bytes (always b"" here),
#          witness: None | [bytes, ...]}]
#   vout: [{value: int sats, script_pubkey: bytes}]
#   locktime: int
#
# For a txid, the stripped (non-witness) serialization is hashed.
# For broadcast, the marker/flag serialization carries the witness.

def ser_stripped_tx(tx: dict) -> bytes:
    """Non-witness serialization — what the txid hashes."""
    return _ser_stripped(tx)


def _ser_stripped(tx: dict) -> bytes:
    out = bytearray()
    out += int(tx["version"]).to_bytes(4, "little", signed=True)
    out += varint(len(tx["vin"]))
    for v in tx["vin"]:
        out += bytes(v["prev_txid"])
        out += int(v["prev_vout"]).to_bytes(4, "little")
        out += varint(len(v.get("script_sig", b""))) + v.get("script_sig", b"")
        out += int(v["sequence"]).to_bytes(4, "little")
    out += varint(len(tx["vout"]))
    for o in tx["vout"]:
        out += int(o["value"]).to_bytes(8, "little")
        out += varint(len(o["script_pubkey"])) + o["script_pubkey"]
    out += int(tx["locktime"]).to_bytes(4, "little")
    return bytes(out)


def ser_segwit_tx(tx: dict) -> bytes:
    """Full serialization with marker/flag and witnesses."""
    has_witness = any(v.get("witness") for v in tx["vin"])
    out = bytearray()
    out += int(tx["version"]).to_bytes(4, "little", signed=True)
    if has_witness:
        out += b"\x00\x01"
    out += varint(len(tx["vin"]))
    for v in tx["vin"]:
        out += bytes(v["prev_txid"])
        out += int(v["prev_vout"]).to_bytes(4, "little")
        out += varint(len(v.get("script_sig", b""))) + v.get("script_sig", b"")
        out += int(v["sequence"]).to_bytes(4, "little")
    out += varint(len(tx["vout"]))
    for o in tx["vout"]:
        out += int(o["value"]).to_bytes(8, "little")
        out += varint(len(o["script_pubkey"])) + o["script_pubkey"]
    if has_witness:
        for v in tx["vin"]:
            wit = v.get("witness") or []
            out += varint(len(wit))
            for item in wit:
                out += varint(len(item)) + item
    out += int(tx["locktime"]).to_bytes(4, "little")
    return bytes(out)


def txid_display(tx: dict) -> str:
    """Display-order txid (stripped serialization, reversed)."""
    return sha256d(_ser_stripped(tx))[::-1].hex()


def wtxid_display(tx: dict) -> str:
    """Display-order witness txid (full serialization, reversed)."""
    return sha256d(ser_segwit_tx(tx))[::-1].hex()


def tx_vsize(tx: dict) -> int:
    """Virtual size: ceil((3 * stripped + total) / 4)."""
    stripped = len(_ser_stripped(tx))
    total = len(ser_segwit_tx(tx))
    return (3 * stripped + total + 3) // 4


def _read_varint(buf: bytes, p: int):
    b0 = buf[p]
    p += 1
    if b0 < 253:
        return b0, p
    if b0 == 253:
        return int.from_bytes(buf[p:p + 2], "little"), p + 2
    if b0 == 254:
        return int.from_bytes(buf[p:p + 4], "little"), p + 4
    return int.from_bytes(buf[p:p + 8], "little"), p + 8


def parse_segwit_tx(raw: bytes) -> dict:
    """Parse a serialized Bitcoin tx (segwit or legacy). Raises
    BtcHtlcError on malformed input. Witness items are returned per
    input (empty list when the tx carries no witness)."""
    try:
        if len(raw) < 10:
            raise BtcHtlcError("tx too short")
        p = 0
        version = int.from_bytes(raw[p:p + 4], "little", signed=True)
        p += 4
        segwit = False
        if raw[p] == 0x00 and raw[p + 1] == 0x01:
            segwit = True
            p += 2
        n_in, p = _read_varint(raw, p)
        if n_in == 0:
            raise BtcHtlcError("no inputs")
        vin = []
        for _ in range(n_in):
            if p + 36 > len(raw):
                raise BtcHtlcError("truncated vin")
            prev = raw[p:p + 32]
            p += 32
            idx = int.from_bytes(raw[p:p + 4], "little")
            p += 4
            sl, p = _read_varint(raw, p)
            if p + sl + 4 > len(raw):
                raise BtcHtlcError("truncated scriptSig")
            ss = raw[p:p + sl]
            p += sl
            seq = int.from_bytes(raw[p:p + 4], "little")
            p += 4
            vin.append({"prev_txid": prev, "prev_vout": idx,
                        "sequence": seq, "script_sig": ss, "witness": []})
        n_out, p = _read_varint(raw, p)
        if n_out == 0:
            raise BtcHtlcError("no outputs")
        vout = []
        for _ in range(n_out):
            if p + 8 > len(raw):
                raise BtcHtlcError("truncated vout")
            val = int.from_bytes(raw[p:p + 8], "little")
            p += 8
            sl, p = _read_varint(raw, p)
            if p + sl > len(raw):
                raise BtcHtlcError("truncated scriptPubKey")
            spk = raw[p:p + sl]
            p += sl
            vout.append({"value": val, "script_pubkey": spk})
        if segwit:
            for v in vin:
                n_wit, p = _read_varint(raw, p)
                items = []
                for _ in range(n_wit):
                    wl, p = _read_varint(raw, p)
                    if p + wl > len(raw):
                        raise BtcHtlcError("truncated witness item")
                    items.append(raw[p:p + wl])
                    p += wl
                v["witness"] = items
        if p + 4 > len(raw):
            raise BtcHtlcError("truncated locktime")
        locktime = int.from_bytes(raw[p:p + 4], "little")
        p += 4
        if p != len(raw):
            raise BtcHtlcError("trailing bytes")
    except BtcHtlcError:
        raise
    except Exception as e:
        raise BtcHtlcError(f"malformed tx: {e}")
    return {"version": version, "vin": vin, "vout": vout,
            "locktime": locktime, "segwit": segwit}


# ---------------------------------------------------------------- watcher signal
# The offer swap watcher (self-serve/deliver_seed.py) finds a taker's
# BTC funding tx by a payment to the signal address, then reads the
# OP_RETURN tag + delivery pubkey from the same tx and publishes the
# QHTLC claim seed encrypted to that pubkey. A wallet-built funding
# tx carries no signal unless the caller opts in — without it the
# watcher never sees the funding and no claim seed is delivered.
# Signal outputs, in order after the HTLC output:
#   OP_RETURN (0 sats): push(tag || delivery_pubkey) — tag is the lot
#     tag (e.g. b"EXCAL1K"); the payload must fit one push byte, so
#     len(tag) + 33 <= 75 (deliver_seed matches the tag exactly).
#   1,000 sats to the signal address (P2WPKH; above the dust limit).
DEFAULT_SIGNAL_ADDRESS = "bc1qj37xg5qmyedwfe70cz0f385cxmf6642kcznjdg"
WATCHER_SIGNAL_SATS = 1000


def build_watcher_signal(tag: bytes, delivery_pubkey: bytes,
                         signal_address: str = DEFAULT_SIGNAL_ADDRESS,
                         signal_sats: int = WATCHER_SIGNAL_SATS) -> list:
    """The two watcher-signal outputs for a BTC funding tx.

    Returns [{"value", "script_pubkey"}, ...] (OP_RETURN, then the
    signal payment). Raises BtcHtlcError on a bad tag, pubkey,
    address, or amount. The caller adds these after the HTLC output;
    the fee is measured over the whole tx by the builder."""
    if not isinstance(tag, (bytes, bytearray)) or not 1 <= len(tag) <= 42:
        raise BtcHtlcError(
            "signal tag must be 1..42 bytes — tag + delivery pubkey "
            "must fit one OP_RETURN push (<= 75 bytes)")
    validate_pubkey(bytes(delivery_pubkey), "delivery")
    if not isinstance(signal_sats, int) or signal_sats < DUST_SATS:
        raise BtcHtlcError(
            f"signal payment must be >= {DUST_SATS} sats "
            f"(got {signal_sats!r})")
    try:
        signal_spk = script_pubkey_from_address(signal_address)
    except BtcHtlcError as e:
        raise BtcHtlcError(f"bad signal address: {e}")
    if not (len(signal_spk) == 22 and signal_spk[0] == 0x00
            and signal_spk[1] == 0x14):
        raise BtcHtlcError(
            "signal address must be a P2WPKH address (the watcher "
            "polls a P2WPKH signal address)")
    payload = bytes(tag) + bytes(delivery_pubkey)
    op_return = b"\x6a" + push(payload)
    return [{"value": 0, "script_pubkey": op_return},
            {"value": signal_sats, "script_pubkey": signal_spk}]


def find_watcher_signal(tx: dict, tag: bytes,
                        signal_address: str = None,
                        signal_sats: int = None) -> dict | None:
    """Find the watcher signal in a parsed tx (parse_segwit_tx shape).

    Returns {"delivery_pubkey", "op_return_vout", "signal_vout"} or
    None when the tx carries no OP_RETURN output whose payload is
    exactly tag + a 33-byte pubkey. When signal_address/signal_sats
    are given, signal_vout is the output paying that many sats to
    that address (None otherwise); the OP_RETURN match alone is
    what the watcher keys on."""
    want_spk = None
    if signal_address is not None:
        try:
            want_spk = script_pubkey_from_address(signal_address)
        except BtcHtlcError:
            return None
    found = None
    for i, o in enumerate(tx.get("vout", [])):
        spk = o["script_pubkey"]
        if len(spk) < 2 or spk[0] != 0x6A:
            continue
        data = spk[1:]
        if not data or data[0] != len(data) - 1:
            continue
        payload = data[1:]
        if len(payload) == len(tag) + 33 and payload[:len(tag)] == tag:
            found = {"delivery_pubkey": payload[len(tag):],
                     "op_return_vout": i, "signal_vout": None}
            break
    if found is None:
        return None
    if want_spk is not None:
        for i, o in enumerate(tx.get("vout", [])):
            if o["script_pubkey"] == want_spk and (
                    signal_sats is None or o["value"] == signal_sats):
                found["signal_vout"] = i
                break
    return found
def bip143_sighash(tx: dict, input_index: int, script_code: bytes,
                   spent_value: int) -> bytes:
    """BIP143 sighash (SIGHASH_ALL only) for one segwit input.

    script_code: for a P2WPKH input, the 25-byte P2PKH script of the
    pubkey (OP_DUP OP_HASH160 <hash160> OP_EQUALVERIFY OP_CHECKSIG);
    for a P2WSH input, the witness script itself. spent_value is the
    value of the output being spent, in sats (committed by BIP143)."""
    if spent_value is None:
        raise BtcHtlcError("BIP143 sighash requires the spent value")
    vin = tx["vin"]
    if not (0 <= input_index < len(vin)):
        raise BtcHtlcError("input index out of range")
    prevouts = b"".join(bytes(v["prev_txid"])
                        + int(v["prev_vout"]).to_bytes(4, "little")
                        for v in vin)
    sequences = b"".join(int(v["sequence"]).to_bytes(4, "little")
                         for v in vin)
    outputs = b"".join(
        int(o["value"]).to_bytes(8, "little")
        + varint(len(o["script_pubkey"])) + o["script_pubkey"]
        for o in tx["vout"])
    inp = vin[input_index]
    preimage = (
        int(tx["version"]).to_bytes(4, "little", signed=True)
        + sha256d(prevouts)
        + sha256d(sequences)
        + bytes(inp["prev_txid"])
        + int(inp["prev_vout"]).to_bytes(4, "little")
        + varint(len(script_code)) + script_code
        + int(spent_value).to_bytes(8, "little")
        + int(inp["sequence"]).to_bytes(4, "little")
        + sha256d(outputs)
        + int(tx["locktime"]).to_bytes(4, "little")
        + SIGHASH_ALL.to_bytes(4, "little")
    )
    return sha256d(preimage)


def p2wpkh_script_code(pub: bytes) -> bytes:
    """BIP143 scriptCode for a P2WPKH input (the P2PKH script)."""
    validate_pubkey(pub, "P2WPKH")
    return b"\x76\xa9\x14" + hash160(pub) + b"\x88\xac"


# ---------------------------------------------------------------- signatures
def _der_sig_with_hashtype(priv: int, sighash: bytes) -> bytes:
    """DER signature + SIGHASH_ALL byte (the witness signature form)."""
    return secp.sign_der(priv, sighash) + bytes([SIGHASH_ALL])


def _verify_der_sig(pub: bytes, der_sig: bytes, sighash: bytes) -> bool:
    """Verify a DER (+optional hashtype byte) signature. Returns
    False on any malformation — never raises."""
    try:
        if der_sig and der_sig[-1] == SIGHASH_ALL and len(der_sig) > 1:
            der_sig = der_sig[:-1]
        r, s = secp.der_decode(der_sig)
        raw = r.to_bytes(32, "big") + s.to_bytes(32, "big")
        return secp.verify(pub, raw, sighash)
    except Exception:
        return False


# ---------------------------------------------------------------- PSBT (BIP174)
def _psbt_kv(key_type: int, key_data: bytes, value: bytes) -> bytes:
    return varint(1 + len(key_data)) + bytes([key_type]) + key_data \
        + varint(len(value)) + value


def build_psbt(unsigned_tx: dict, inputs_meta: list) -> str:
    """Build an UNSIGNED BIP174 PSBT (base64) for `unsigned_tx`.

    inputs_meta[i]: {"witness_utxo_value": int,
                     "witness_utxo_script": bytes,
                     "witness_script": bytes | None}
    The unsigned tx must carry empty scriptSigs and no witness (the
    PSBT global map holds the stripped serialization)."""
    psbt = bytearray(b"psbt\xff")
    psbt += _psbt_kv(PSBT_GLOBAL_UNSIGNED_TX, b"", _ser_stripped(unsigned_tx))
    psbt += b"\x00"
    for meta in inputs_meta:
        wu = (int(meta["witness_utxo_value"]).to_bytes(8, "little")
              + varint(len(meta["witness_utxo_script"]))
              + meta["witness_utxo_script"])
        psbt += _psbt_kv(PSBT_IN_WITNESS_UTXO, b"", wu)
        if meta.get("witness_script"):
            psbt += _psbt_kv(PSBT_IN_WITNESS_SCRIPT, b"",
                             meta["witness_script"])
        psbt += b"\x00"
    # No output maps: the PSBT ends with the last input map's
    # terminator (BIP174).
    return base64.b64encode(bytes(psbt)).decode()


def parse_psbt(psbt_b64: str) -> dict:
    """Parse a base64 PSBT. Returns {"tx": tx dict, "inputs": [{
    "witness_utxo": {"value", "script_pubkey"} | None,
    "witness_script": bytes | None,
    "partial_sigs": {pubkey_hex: sig_bytes}}]}. Raises BtcHtlcError
    on malformed input."""
    try:
        raw = base64.b64decode(psbt_b64, validate=True)
    except Exception as e:
        raise BtcHtlcError(f"PSBT is not valid base64: {e}")
    if raw[:5] != b"psbt\xff":
        raise BtcHtlcError("PSBT magic missing (want 'psbt' + 0xff)")
    p = 5

    def read_kv():
        nonlocal p
        if p >= len(raw):
            raise BtcHtlcError("truncated PSBT map")
        kl, p2 = _read_varint(raw, p)
        if kl == 0:
            return None, None, p2
        p = p2
        if p + kl > len(raw):
            raise BtcHtlcError("truncated PSBT key")
        key = raw[p:p + kl]
        p += kl
        vl, p = _read_varint(raw, p)
        if p + vl > len(raw):
            raise BtcHtlcError("truncated PSBT value")
        val = raw[p:p + vl]
        p += vl
        return key, val, p

    unsigned_tx = None
    while True:
        key, val, p = read_kv()
        if key is None:
            break
        if key == b"\x00":
            unsigned_tx = parse_segwit_tx(val)
        # unknown global keys are ignored (BIP174 extensibility)
    if unsigned_tx is None:
        raise BtcHtlcError("PSBT has no global unsigned tx")
    inputs = []
    for _ in range(len(unsigned_tx["vin"])):
        meta = {"witness_utxo": None, "witness_script": None,
                "partial_sigs": {}, "final_witness": None}
        while True:
            key, val, p = read_kv()
            if key is None:
                break
            t = key[0]
            if t == PSBT_IN_WITNESS_UTXO:
                if len(val) < 8:
                    raise BtcHtlcError("bad witness_utxo in PSBT")
                v = int.from_bytes(val[:8], "little")
                sl, q = _read_varint(val, 8)
                spk = val[q:q + sl]
                if len(spk) != sl:
                    raise BtcHtlcError("bad witness_utxo script in PSBT")
                meta["witness_utxo"] = {"value": v, "script_pubkey": spk}
            elif t == PSBT_IN_PARTIAL_SIG:
                meta["partial_sigs"][key[1:].hex()] = val
            elif t == PSBT_IN_WITNESS_SCRIPT:
                meta["witness_script"] = val
            elif t == PSBT_IN_FINAL_SCRIPTWITNESS:
                items = []
                q = 0
                n, q = _read_varint(val, q)
                for _ in range(n):
                    wl, q = _read_varint(val, q)
                    items.append(val[q:q + wl])
                    q += wl
                meta["final_witness"] = items
            # unknown input keys are ignored
        inputs.append(meta)
    if p != len(raw):
        raise BtcHtlcError("trailing bytes in PSBT")
    return {"tx": unsigned_tx, "inputs": inputs}


def sign_psbt(psbt_b64: str, pub_to_priv: dict) -> str:
    """Sign every PSBT input this wallet can sign (BIP143 SIGHASH_ALL).

    pub_to_priv: {compressed_pubkey_bytes: priv_int}. For a P2WPKH
    input the scriptCode is the P2PKH script of the pubkey; for a
    P2WSH input it is the input's witness script. Each added partial
    signature is verified locally (secp.verify over the sighash)
    BEFORE it is written — a bad signature never enters the PSBT.
    Inputs the wallet cannot sign are left unsigned. Returns the new
    base64 PSBT. Raises BtcHtlcError if an input claims a witness
    script that does not match its witness_utxo scriptPubKey."""
    doc = parse_psbt(psbt_b64)
    tx = doc["tx"]
    out_inputs = []
    for i, meta in enumerate(doc["inputs"]):
        wu = meta["witness_utxo"]
        if wu is None:
            raise BtcHtlcError(f"PSBT input {i}: no witness_utxo")
        spk = wu["script_pubkey"]
        sigs = dict(meta["partial_sigs"])
        if meta["witness_script"] is not None:
            # P2WSH input: the scriptPubKey must be OP_0 <sha256(script)>.
            script = meta["witness_script"]
            if spk != p2wsh_script_pubkey(script):
                raise BtcHtlcError(
                    f"PSBT input {i}: witness script does not match "
                    f"the witness_utxo scriptPubKey")
            parsed = parse_witness_script(script)
            for role_pub in (parsed["claim_pubkey"],
                             parsed["refund_pubkey"]):
                priv = pub_to_priv.get(role_pub)
                if priv is None:
                    continue
                h = bip143_sighash(tx, i, script, wu["value"])
                sig = _der_sig_with_hashtype(priv, h)
                if not _verify_der_sig(role_pub, sig, h):
                    raise BtcHtlcError(
                        f"PSBT input {i}: local verification of the "
                        f"fresh signature failed (refusing to write it)")
                sigs[role_pub.hex()] = sig
        elif len(spk) == 22 and spk[0] == 0x00 and spk[1] == 0x14:
            # P2WPKH input: find the wallet key whose hash160 matches.
            for pub, priv in pub_to_priv.items():
                if hash160(pub) == spk[2:]:
                    h = bip143_sighash(tx, i, p2wpkh_script_code(pub),
                                       wu["value"])
                    sig = _der_sig_with_hashtype(priv, h)
                    if not _verify_der_sig(pub, sig, h):
                        raise BtcHtlcError(
                            f"PSBT input {i}: local verification of the "
                            f"fresh signature failed (refusing to write it)")
                    sigs[pub.hex()] = sig
                    break
        else:
            raise BtcHtlcError(
                f"PSBT input {i}: unsupported witness_utxo scriptPubKey "
                f"(want P2WPKH or P2WSH)")
        out_inputs.append({**meta, "partial_sigs": sigs})
    return _encode_psbt(tx, out_inputs)


def _encode_psbt(tx: dict, inputs_meta: list) -> str:
    """Re-encode a parsed PSBT (unsigned tx + per-input maps)."""
    psbt = bytearray(b"psbt\xff")
    psbt += _psbt_kv(PSBT_GLOBAL_UNSIGNED_TX, b"", _ser_stripped(tx))
    psbt += b"\x00"
    for meta in inputs_meta:
        wu = meta["witness_utxo"]
        if wu is not None:
            w = (int(wu["value"]).to_bytes(8, "little")
                 + varint(len(wu["script_pubkey"])) + wu["script_pubkey"])
            psbt += _psbt_kv(PSBT_IN_WITNESS_UTXO, b"", w)
        for pub_hex, sig in meta.get("partial_sigs", {}).items():
            psbt += _psbt_kv(PSBT_IN_PARTIAL_SIG,
                             bytes.fromhex(pub_hex), sig)
        if meta.get("witness_script"):
            psbt += _psbt_kv(PSBT_IN_WITNESS_SCRIPT, b"",
                             meta["witness_script"])
        if meta.get("final_witness") is not None:
            fw = varint(len(meta["final_witness"]))
            for item in meta["final_witness"]:
                fw += varint(len(item)) + item
            psbt += _psbt_kv(PSBT_IN_FINAL_SCRIPTWITNESS, b"", fw)
        psbt += b"\x00"
    # No output maps: the PSBT ends with the last input map's
    # terminator (BIP174).
    return base64.b64encode(bytes(psbt)).decode()


def finalize_psbt(psbt_b64: str, htlc_spends: dict = None) -> dict:
    """Finalize a fully-signed PSBT into a network tx.

    htlc_spends: {input_index: {"branch": "claim"|"refund",
    "secret": bytes (claim only)}} — the witness stack for a P2WSH
    HTLC input. P2WPKH inputs finalize as [sig, pubkey].
    Every P2WSH signature is re-verified (secp.verify over the
    BIP143 sighash) before the witness is assembled; a missing or
    bad signature refuses the whole finalize. Returns {"raw_hex",
    "txid", "wtxid", "vsize", "tx"} — the tx dict carries the final
    witnesses."""
    htlc_spends = htlc_spends or {}
    doc = parse_psbt(psbt_b64)
    tx = doc["tx"]
    for i, meta in enumerate(doc["inputs"]):
        wu = meta["witness_utxo"]
        if wu is None:
            raise BtcHtlcError(f"PSBT input {i}: no witness_utxo")
        spk = wu["script_pubkey"]
        sigs = meta["partial_sigs"]
        if meta["witness_script"] is not None:
            script = meta["witness_script"]
            parsed = parse_witness_script(script)
            spend = htlc_spends.get(i)
            if spend is None:
                raise BtcHtlcError(
                    f"PSBT input {i}: P2WSH HTLC input needs a spend "
                    f"description (branch claim|refund)")
            branch = spend.get("branch")
            if branch == "claim":
                pub = parsed["claim_pubkey"]
                secret = spend.get("secret")
                if secret is None:
                    raise BtcHtlcError(
                        f"PSBT input {i}: claim branch needs the secret")
                if hashlib.sha256(secret).digest() != parsed["secret_hash"]:
                    raise BtcHtlcError(
                        f"PSBT input {i}: secret does not hash to the "
                        f"script's secret hash")
                branch_flag = b"\x01"
            elif branch == "refund":
                pub = parsed["refund_pubkey"]
                secret = None
                # Minimal false: the EMPTY push (OP_0). A 1-byte 0x00
                # push is a non-minimal OP_IF argument and the node
                # rejects it ("OP_IF/NOTIF argument must be minimal").
                branch_flag = b""
                if tx["locktime"] < parsed["timeout"]:
                    raise BtcHtlcError(
                        f"PSBT input {i}: refund locktime "
                        f"{tx['locktime']} is below the timeout "
                        f"{parsed['timeout']}")
                if tx["vin"][i]["sequence"] == SEQ_FINAL:
                    raise BtcHtlcError(
                        f"PSBT input {i}: refund input sequence is final "
                        f"(CLTV cannot apply)")
            else:
                raise BtcHtlcError(
                    f"PSBT input {i}: unknown branch {branch!r}")
            sig = sigs.get(pub.hex())
            if sig is None:
                raise BtcHtlcError(
                    f"PSBT input {i}: no partial signature for the "
                    f"{branch} pubkey")
            h = bip143_sighash(tx, i, script, wu["value"])
            if not _verify_der_sig(pub, sig, h):
                raise BtcHtlcError(
                    f"PSBT input {i}: {branch} signature does not verify")
            if branch == "claim":
                witness = [sig, secret, branch_flag, script]
            else:
                witness = [sig, branch_flag, script]
            tx["vin"][i]["witness"] = witness
        elif len(spk) == 22 and spk[0] == 0x00 and spk[1] == 0x14:
            pub = None
            sig = None
            for pub_hex, s in sigs.items():
                if hash160(bytes.fromhex(pub_hex)) == spk[2:]:
                    pub, sig = bytes.fromhex(pub_hex), s
                    break
            if sig is None:
                raise BtcHtlcError(f"PSBT input {i}: no P2WPKH signature")
            h = bip143_sighash(tx, i, p2wpkh_script_code(pub), wu["value"])
            if not _verify_der_sig(pub, sig, h):
                raise BtcHtlcError(
                    f"PSBT input {i}: P2WPKH signature does not verify")
            tx["vin"][i]["witness"] = [sig, pub]
        else:
            raise BtcHtlcError(
                f"PSBT input {i}: unsupported witness_utxo scriptPubKey")
    raw = ser_segwit_tx(tx)
    return {"raw_hex": raw.hex(), "txid": txid_display(tx),
            "wtxid": wtxid_display(tx), "vsize": tx_vsize(tx), "tx": tx}


# ---------------------------------------------------------------- builders
def _check_fee_rate(fee_rate: int):
    if not isinstance(fee_rate, int) or fee_rate < 1:
        raise BtcHtlcError(f"fee rate must be an integer >= 1 sat/vB (got {fee_rate!r})")


def _placeholder_witness_p2wpkh() -> list:
    return [b"\x00" * MAX_DER_SIG_LEN, b"\x00" * 33]


def _placeholder_witness_htlc(branch: str, script: bytes) -> list:
    if branch == "claim":
        return [b"\x00" * MAX_DER_SIG_LEN, b"\x00" * 32, b"\x01", script]
    # Refund flag is the empty push (OP_0) — see finalize_psbt.
    return [b"\x00" * MAX_DER_SIG_LEN, b"", script]


def _fee_for(tx: dict, fee_rate: int) -> int:
    return tx_vsize(tx) * fee_rate


def build_btc_htlc_lock(utxos, pub_to_priv, amount_sats: int,
                        claim_pub: bytes, refund_pub: bytes,
                        secret_hash: bytes, timeout: int,
                        change_pub: bytes, fee_rate: int = 5,
                        network: str = "mainnet",
                        signal: dict = None) -> dict:
    """Build + sign + verify a BTC HTLC funding tx (P2WPKH inputs ->
    P2WSH HTLC output + P2WPKH change).

    utxos: [{txid (display hex), vout, value (sats), script_pubkey
    (hex)}] — each must be a P2WPKH of a key in pub_to_priv.
    pub_to_priv: {compressed_pubkey_bytes: priv_int} for the wallet
    keys that may fund. amount_sats is the HTLC output value.
    change_pub: the wallet key taking the change (P2WPKH).
    signal (optional): {"tag", "delivery_pubkey",
    "signal_address", "signal_sats"} — adds the watcher-signal
    outputs (OP_RETURN tag + delivery pubkey, then the signal
    payment) after the HTLC output; the fee is measured over the
    whole tx, signal outputs included. Returns the txbuild-style
    result dict plus the lock, the PSBT (base64, signed +
    finalized), the witness script, and "signal" when given. Raises
    BtcHtlcError on any failure. NEVER broadcasts."""
    _check_fee_rate(fee_rate)
    if amount_sats < DUST_SATS:
        raise BtcHtlcError(
            f"HTLC amount {amount_sats} is dust (< {DUST_SATS} sats)")
    lock = build_lock(claim_pub, refund_pub, secret_hash, timeout,
                      network)
    htlc_spk = bytes.fromhex(lock["script_pubkey_hex"])
    change_spk = p2wpkh_script_pubkey(change_pub)
    signal_outputs = []
    signal_value = 0
    if signal is not None:
        try:
            signal_outputs = build_watcher_signal(
                signal["tag"], signal["delivery_pubkey"],
                signal.get("signal_address") or DEFAULT_SIGNAL_ADDRESS,
                signal.get("signal_sats") or WATCHER_SIGNAL_SATS)
        except KeyError as e:
            raise BtcHtlcError(
                f"watcher signal needs 'tag' and 'delivery_pubkey' "
                f"(missing {e})")
        signal_value = sum(o["value"] for o in signal_outputs)
    # Validate + select funding inputs (largest first, like txbuild).
    cands = []
    for u in utxos:
        spk = bytes.fromhex(u["script_pubkey"])
        if not (len(spk) == 22 and spk[0] == 0x00 and spk[1] == 0x14):
            raise BtcHtlcError(
                f"funding UTXO {u['txid']}:{u['vout']} is not a P2WPKH "
                f"output (only wallet P2WPKH inputs fund a BTC HTLC)")
        owner = None
        for pub in pub_to_priv:
            if hash160(pub) == spk[2:]:
                owner = pub
                break
        if owner is None:
            raise BtcHtlcError(
                f"funding UTXO {u['txid']}:{u['vout']} is not a wallet "
                f"P2WPKH output — the wallet cannot sign for it")
        cands.append({**u, "script_pubkey_bytes": spk, "pub": owner})
    cands.sort(key=lambda c: -c["value"])
    if not cands:
        raise BtcHtlcError("insufficient funds (no wallet P2WPKH UTXOs)")
    total_in = sum(c["value"] for c in cands)
    # Measure with placeholder witnesses (max-size sigs), then set the
    # fee from the exact vsize and rebuild once — the real signatures
    # are never larger than the placeholders, so the fee never falls
    # short of fee_rate * vsize.
    def build_tx(fee, with_change):
        vout = [{"value": amount_sats, "script_pubkey": htlc_spk}]
        vout.extend(signal_outputs)
        if with_change:
            change = total_in - amount_sats - signal_value - fee
            vout.append({"value": change, "script_pubkey": change_spk})
        return {"version": 2,
                "vin": [{"prev_txid": bytes.fromhex(c["txid"])[::-1],
                         "prev_vout": int(c["vout"]),
                         "sequence": SEQ_FINAL,
                         "script_sig": b"",
                         "witness": _placeholder_witness_p2wpkh()}
                        for c in cands],
                "vout": vout, "locktime": 0}

    t = build_tx(0, True)
    fee = _fee_for(t, fee_rate)
    change = total_in - amount_sats - signal_value - fee
    if change < 0:
        raise BtcHtlcError(
            f"insufficient funds: need {amount_sats + signal_value + fee} "
            f"sats (amount + signal + fee), have {total_in}")
    if change >= DUST_SATS:
        t = build_tx(fee, True)
    else:
        # Dust change folds into the fee (txbuild's rule).
        fee = total_in - amount_sats - signal_value
        t = build_tx(fee, False)
    fee = total_in - sum(o["value"] for o in t["vout"])
    # PSBT flow: unsigned PSBT -> sign EVERY input -> finalize.
    unsigned = {"version": t["version"],
                "vin": [{**v, "witness": None} for v in t["vin"]],
                "vout": t["vout"], "locktime": 0}
    meta = [{"witness_utxo_value": c["value"],
             "witness_utxo_script": c["script_pubkey_bytes"],
             "witness_script": None} for c in cands]
    psbt = build_psbt(unsigned, meta)
    signed = sign_psbt(psbt, pub_to_priv)
    fin = finalize_psbt(signed)
    real_fee = total_in - sum(o["value"] for o in fin["tx"]["vout"])
    if real_fee != fee:
        raise BtcHtlcError(
            f"fee mismatch: computed {fee}, finalized {real_fee}")
    if fin["vsize"] * fee_rate > real_fee:
        raise BtcHtlcError(
            f"fee {real_fee} is below {fee_rate} sats/vB * "
            f"vsize {fin['vsize']}")
    return {"raw_hex": fin["raw_hex"], "txid": fin["txid"],
            "wtxid": fin["wtxid"], "fee": real_fee,
            "vsize": fin["vsize"], "fee_rate": fee_rate,
            "inputs": [{"txid": c["txid"], "vout": c["vout"],
                        "value": c["value"]} for c in cands],
            "outputs": [{"value": o["value"],
                         "script_pubkey": o["script_pubkey"].hex()}
                        for o in fin["tx"]["vout"]],
            "validated": True, "broadcast": False,
            "network": network, "lock": lock,
            "witness_script_hex": lock["witness_script_hex"],
            "address": lock["address"],
            "psbt": signed,
            "signal": ({"tag": bytes(signal["tag"]).hex(),
                        "delivery_pubkey":
                            bytes(signal["delivery_pubkey"]).hex(),
                        "signal_address": signal.get(
                            "signal_address") or DEFAULT_SIGNAL_ADDRESS,
                        "signal_sats": signal.get(
                            "signal_sats") or WATCHER_SIGNAL_SATS}
                       if signal is not None else None)}


def _htlc_spend_tx(lock_txid: str, lock_vout: int, lock_value: int,
                   dest_spk: bytes, fee: int, script: bytes,
                   branch: str):
    """Unsigned spend tx for one HTLC input. Claim: version 2,
    locktime 0, sequence final. Refund: version 2, locktime =
    timeout, sequence non-final (CLTV)."""
    parsed = parse_witness_script(script)
    if branch == "claim":
        locktime, seq = 0, SEQ_FINAL
    elif branch == "refund":
        locktime, seq = parsed["timeout"], SEQ_CLTV
    else:
        raise BtcHtlcError(f"unknown HTLC branch {branch!r}")
    if lock_value - fee <= 0:
        raise BtcHtlcError("amount after fee must be positive")
    return {"version": 2,
            "vin": [{"prev_txid": bytes.fromhex(lock_txid)[::-1],
                     "prev_vout": int(lock_vout),
                     "sequence": seq, "script_sig": b"",
                     "witness": None}],
            "vout": [{"value": lock_value - fee,
                      "script_pubkey": dest_spk}],
            "locktime": locktime}


def build_btc_htlc_claim(lock_txid: str, lock_vout: int, lock_value: int,
                         dest_spk: bytes, secret: bytes,
                         script: bytes, claim_priv: int,
                         fee: int = None, fee_rate: int = 5) -> dict:
    """Build + sign + verify a BTC HTLC claim (secret + claim key).

    The fee is fee_rate * vsize (measured with a max-size placeholder
    witness first) unless an explicit fee is given. The secret is
    checked against the script's hash BEFORE signing, and the
    signature is re-verified before the tx is returned. NEVER
    broadcasts."""
    from .keys import priv_to_pub_compressed
    parsed = parse_witness_script(script)
    claim_pub = priv_to_pub_compressed(claim_priv)
    if claim_pub != parsed["claim_pubkey"]:
        raise BtcHtlcError(
            "claim key does not match the script's claim pubkey")
    if hashlib.sha256(secret).digest() != parsed["secret_hash"]:
        raise BtcHtlcError(
            "secret does not hash to the script's secret hash — "
            "claim refused before signing")
    t = _htlc_spend_tx(lock_txid, lock_vout, lock_value, dest_spk,
                       fee if fee is not None else 0, script, "claim")
    # Fee: measure with a max-size placeholder witness, then set it.
    t["vin"][0]["witness"] = _placeholder_witness_htlc("claim", script)
    _check_fee_rate(fee_rate)
    if fee is None:
        fee = _fee_for(t, fee_rate)
        t = _htlc_spend_tx(lock_txid, lock_vout, lock_value, dest_spk,
                           fee, script, "claim")
    elif fee < _fee_for(t, fee_rate):
        raise BtcHtlcError(
            f"fee {fee} is below {fee_rate} sats/vB * vsize "
            f"{tx_vsize(t)} ({_fee_for(t, fee_rate)} sats)")
    if fee <= 0:
        raise BtcHtlcError("fee must be positive")
    if lock_value - fee < DUST_SATS:
        raise BtcHtlcError(
            f"claim output {lock_value - fee} would be dust "
            f"(< {DUST_SATS} sats)")
    t["vin"][0]["witness"] = None
    meta = [{"witness_utxo_value": lock_value,
             "witness_utxo_script": p2wsh_script_pubkey(script),
             "witness_script": script}]
    psbt = build_psbt(t, meta)
    signed = sign_psbt(psbt, {claim_pub: claim_priv})
    fin = finalize_psbt(signed, {0: {"branch": "claim", "secret": secret}})
    return {"raw_hex": fin["raw_hex"], "txid": fin["txid"],
            "wtxid": fin["wtxid"], "fee": fee,
            "vsize": fin["vsize"], "fee_rate": fee_rate,
            "inputs": [{"txid": lock_txid, "vout": lock_vout,
                        "value": lock_value}],
            "outputs": [{"value": lock_value - fee,
                         "script_pubkey": dest_spk.hex()}],
            "validated": True, "broadcast": False, "branch": "claim",
            "psbt": signed}


def build_btc_htlc_refund(lock_txid: str, lock_vout: int, lock_value: int,
                          dest_spk: bytes, script: bytes,
                          refund_priv: int, current_height: int,
                          fee: int = None, fee_rate: int = 5) -> dict:
    """Build + sign + verify a BTC HTLC refund (refund key, after
    timeout).

    The fee is fee_rate * vsize unless an explicit fee is given.
    current_height is the CURRENT Bitcoin tip height (the caller
    supplies it — the CLI takes --btc-height). The refund is refused
    unless current_height >= timeout: the chain, not this builder,
    enforces CLTV, but building a refund that cannot confirm yet
    would only strand a signed tx. NEVER broadcasts."""
    from .keys import priv_to_pub_compressed
    parsed = parse_witness_script(script)
    refund_pub = priv_to_pub_compressed(refund_priv)
    if refund_pub != parsed["refund_pubkey"]:
        raise BtcHtlcError(
            "refund key does not match the script's refund pubkey")
    if current_height is None or current_height < parsed["timeout"]:
        raise BtcHtlcError(
            f"refund refused: current height {current_height} is below "
            f"the timeout {parsed['timeout']} — the refund cannot "
            f"confirm yet")
    t = _htlc_spend_tx(lock_txid, lock_vout, lock_value, dest_spk,
                       fee if fee is not None else 0, script, "refund")
    t["vin"][0]["witness"] = _placeholder_witness_htlc("refund", script)
    _check_fee_rate(fee_rate)
    if fee is None:
        fee = _fee_for(t, fee_rate)
        t = _htlc_spend_tx(lock_txid, lock_vout, lock_value, dest_spk,
                           fee, script, "refund")
    elif fee < _fee_for(t, fee_rate):
        raise BtcHtlcError(
            f"fee {fee} is below {fee_rate} sats/vB * vsize "
            f"{tx_vsize(t)} ({_fee_for(t, fee_rate)} sats)")
    if fee <= 0:
        raise BtcHtlcError("fee must be positive")
    if lock_value - fee < DUST_SATS:
        raise BtcHtlcError(
            f"refund output {lock_value - fee} would be dust "
            f"(< {DUST_SATS} sats)")
    t["vin"][0]["witness"] = None
    meta = [{"witness_utxo_value": lock_value,
             "witness_utxo_script": p2wsh_script_pubkey(script),
             "witness_script": script}]
    psbt = build_psbt(t, meta)
    signed = sign_psbt(psbt, {refund_pub: refund_priv})
    fin = finalize_psbt(signed, {0: {"branch": "refund"}})
    return {"raw_hex": fin["raw_hex"], "txid": fin["txid"],
            "wtxid": fin["wtxid"], "fee": fee,
            "vsize": fin["vsize"], "fee_rate": fee_rate,
            "inputs": [{"txid": lock_txid, "vout": lock_vout,
                        "value": lock_value}],
            "outputs": [{"value": lock_value - fee,
                         "script_pubkey": dest_spk.hex()}],
            "validated": True, "broadcast": False, "branch": "refund",
            "psbt": signed}


# ---------------------------------------------------------------- validation
def validate_claim(secret: bytes, script: bytes) -> bool:
    """True iff the preimage hashes to the script's secret hash."""
    try:
        parsed = parse_witness_script(script)
    except BtcHtlcError:
        return False
    return hashlib.sha256(secret).digest() == parsed["secret_hash"]


def validate_refund(locktime: int, sequence: int, script: bytes) -> bool:
    """True iff the refund's CLTV preconditions hold (locktime reached,
    sequence not final, same locktime type). Signature validity is
    checked separately; this rejects premature refunds before signing."""
    try:
        parsed = parse_witness_script(script)
    except BtcHtlcError:
        return False
    if sequence == SEQ_FINAL:
        return False
    if locktime < parsed["timeout"]:
        return False
    if (locktime < LOCKTIME_THRESHOLD) != \
            (parsed["timeout"] < LOCKTIME_THRESHOLD):
        return False
    return True
