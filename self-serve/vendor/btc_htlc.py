#!/usr/bin/env python3
"""btc_htlc.py — Maker HTLC for REAL Bitcoin (mainnet, SegWit v0 P2WSH).

NOT the EXCAL fork, NOT Azusa. This module builds a real Bitcoin
hash-time-locked contract that a taker funds on Bitcoin mainnet, and
that the maker claims with the revealed secret.

Offer terms on record (NOT changed by this module):
  * Maker: Lux. Maker BTC pubkey (compressed):
        02e8311342cb7accd4edef31462fcda1ef56bfbf7d4f03d3c8872dbec9a1bba1b3
    Maker BTC P2WPKH (reference, used only to cross-check bech32):
        bc1qj37xg5qmyedwfe70cz0f385cxmf6642kcznjdg
  * 1 EXCAL = 1 BTC, up to 47.75 per swap.
  * BTC-first ordering: the TAKER locks BTC first; the MAKER then locks
    EXCAL on the fork (fork HTLC, activated at fork height 36010, lock
    0x03 — a separate, fork-only leg, not built here).
  * Secret hash on record (SHA256 of the counterparty secret; the secret
    itself is NEVER read, printed, or loaded by this module):
        e988bc353174c52feab75d13b24f141ff5a90eca98c26f04e44ae242608a77fd
  * Timeouts on record: BTC 144 blocks, EXCAL 288 blocks. See
    wall_time_analysis() — the block counts are NOT changed here.

Witness script (P2WSH, SegWit v0):
    OP_IF
        OP_SHA256 <secret_hash: 32 bytes> OP_EQUALVERIFY
        <maker_pubkey: 33 bytes> OP_CHECKSIG
    OP_ELSE
        <timeout: script number> OP_CHECKLOCKTIMEVERIFY OP_DROP
        <taker_pubkey: 33 bytes> OP_CHECKSIG
    OP_ENDIF

Claim path (IF branch): witness = [maker_sig, secret_preimage, 0x01,
witness_script]. The maker reveals the secret by claiming.
Refund path (ELSE branch): witness = [taker_sig, 0x00, witness_script],
valid only in a transaction whose locktime is >= timeout and whose
spending input sequence is not 0xffffffff (CLTV rule).

CORRECTION TO THE TASK SHORTHAND, stated plainly: the shorthand listed
"OP_IF <secret_hash> OP_EQUALVERIFY ..." with no hash opcode. Taken
literally, that script compares the secret preimage itself to the hash
and can never verify for a real preimage (preimage != its SHA256, except
for a fixed point). The real script MUST include OP_SHA256 between
OP_IF and the hash push, as above. Nothing else about the offer changes:
same hash, same pubkeys, same timeout. The tests in test_btc_htlc.py
prove the point: the literal no-SHA256 script fails a correct claim,
the corrected script passes it.

What this module does NOT do:
  * It does NOT load any private key, does NOT sign with any real key,
    does NOT broadcast, does NOT post, and does NOT know the secret.
    Claim/refund transactions are built UNSIGNED; signing is a separate,
    separately approved step, using the BIP143 sighash computed here.
  * It does NOT invent a taker. The taker pubkey is TBD in the live
    offer. Functions take taker_pubkey as an argument; tests use a
    clearly-marked TEST pubkey only, never presented as the taker.
  * It does NOT fetch over Python urllib (the sandbox egress proxy
    refuses urllib). The only network call, fetch_btc_tip_height(),
    shells out to curl, as the sniffer does.

P2WSH address: witness program = SHA256(witness_script); scriptPubKey =
OP_0 <32-byte program>; address = bech32 ("bc", version 0, program),
BIP173. Cross-checked in tests against two independent bech32
implementations already in the workspace (bip322.py, payout.py) and
against the known maker P2WPKH address above.
"""

import hashlib
import json
import subprocess
import sys

# ---------------------------------------------------------------- constants
MAKER_PUBKEY_HEX = "02e8311342cb7accd4edef31462fcda1ef56bfbf7d4f03d3c8872dbec9a1bba1b3"
MAKER_PUBKEY = bytes.fromhex(MAKER_PUBKEY_HEX)
MAKER_P2WPKH = "bc1qj37xg5qmyedwfe70cz0f385cxmf6642kcznjdg"
SECRET_HASH_HEX = "e988bc353174c52feab75d13b24f141ff5a90eca98c26f04e44ae242608a77fd"
SECRET_HASH = bytes.fromhex(SECRET_HASH_HEX)

BTC_TIMEOUT_BLOCKS = 144
EXCAL_TIMEOUT_BLOCKS = 288
SIGHASH_ALL = 1
LOCKTIME_THRESHOLD = 500_000_000  # below this, locktime is a block height

OP_0 = 0x00
OP_IF = 0x63
OP_ELSE = 0x67
OP_ENDIF = 0x68
OP_DROP = 0x75
OP_EQUALVERIFY = 0x88
OP_SHA256 = 0xA8
OP_CHECKSIG = 0xAC
OP_CHECKLOCKTIMEVERIFY = 0xB1

# ---------------------------------------------------------------- helpers: push / script numbers / varint
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


try:
    # Reuse the exact script-number encoding the workspace interpreter uses.
    sys.path.insert(0, __file__.rsplit("/", 1)[0])
    from bitcoin_script import encode_num as _ws_encode_num  # type: ignore

    def encode_num(value: int) -> bytes:
        return _ws_encode_num(value)
except Exception:  # pragma: no cover - fallback, identical semantics
    def encode_num(value: int) -> bytes:
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


# ---------------------------------------------------------------- bech32 (BIP173, self-contained)
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
    """Return (hrp, witver, program); raises on bad checksum/format."""
    addr = addr.lower()
    pos = addr.rfind("1")
    if pos < 1 or pos + 7 > len(addr):
        raise ValueError("bad bech32 address")
    hrp, tail = addr[:pos], addr[pos + 1:]
    vals = [_BECH32.index(c) for c in tail]
    if _polymod(_hrp_expand(hrp) + vals) != 1:
        raise ValueError("bad bech32 checksum")
    prog = _convertbits(vals[1:-6], 5, 8, False)
    if prog is None:
        raise ValueError("bad bech32 program bits")
    return hrp, vals[0], bytes(prog)


def hash160(data: bytes) -> bytes:
    try:
        return hashlib.new("ripemd160", hashlib.sha256(data).digest()).digest()
    except Exception:
        from ripemd160_pure import ripemd160_pure

        return ripemd160_pure(hashlib.sha256(data).digest())


# ---------------------------------------------------------------- pubkey validation
def validate_pubkey(pub: bytes, role: str) -> None:
    if len(pub) != 33 or pub[0] not in (0x02, 0x03):
        raise ValueError(f"{role} pubkey must be 33-byte compressed (got {len(pub)} bytes)")
    try:
        sys.path.insert(0, __file__.rsplit("/", 1)[0])
        import secp256k1 as secp

        secp.decompress(pub)  # raises if not on curve
    except Exception as e:
        raise ValueError(f"{role} pubkey is not a valid secp256k1 point: {e}")


# ---------------------------------------------------------------- witness script
def build_witness_script(maker_pubkey: bytes, taker_pubkey: bytes,
                         secret_hash: bytes, timeout: int) -> bytes:
    """Build the HTLC witness script. Roles are NOT interchangeable."""
    validate_pubkey(maker_pubkey, "maker")
    validate_pubkey(taker_pubkey, "taker")
    if len(secret_hash) != 32:
        raise ValueError(f"secret_hash must be 32 bytes (got {len(secret_hash)})")
    if not (0 < timeout < LOCKTIME_THRESHOLD):
        raise ValueError(f"timeout must be a block height in (0, {LOCKTIME_THRESHOLD}) (got {timeout})")
    if maker_pubkey == taker_pubkey:
        raise ValueError("maker and taker pubkeys must differ")
    return (
        bytes([OP_IF])
        + bytes([OP_SHA256]) + push(secret_hash) + bytes([OP_EQUALVERIFY])
        + push(maker_pubkey) + bytes([OP_CHECKSIG])
        + bytes([OP_ELSE])
        + push(encode_num(timeout)) + bytes([OP_CHECKLOCKTIMEVERIFY, OP_DROP])
        + push(taker_pubkey) + bytes([OP_CHECKSIG])
        + bytes([OP_ENDIF])
    )


def parse_witness_script(script: bytes):
    """Parse and strictly validate a witness script.

    Returns a dict {maker_pubkey, taker_pubkey, secret_hash, timeout}.
    Raises ValueError on any structural deviation, including swapped
    pubkey roles (the IF branch must hold the maker, the ELSE branch
    the taker). This is the structural check the offer sheet refers to;
    it does not check signatures.
    """
    # Expected layout, parsed by hand (no interpreter needed for structure):
    # IF SHA256 push32 EQUALVERIFY push33 CHECKSIG ELSE push(timeout)
    # CLTV DROP push33 CHECKSIG ENDIF
    try:
        i = 0

        def expect_op(op):
            nonlocal i
            if i >= len(script) or script[i] != op:
                raise ValueError(f"expected opcode 0x{op:02x} at offset {i}")
            i += 1

        def expect_push():
            nonlocal i
            if i >= len(script):
                raise ValueError("truncated push")
            n = script[i]
            i += 1
            if n >= 76:
                raise ValueError("non-minimal push in HTLC script")
            data = script[i:i + n]
            if len(data) != n:
                raise ValueError("truncated push data")
            i += n
            return data

        expect_op(OP_IF)
        expect_op(OP_SHA256)
        secret_hash = expect_push()
        if len(secret_hash) != 32:
            raise ValueError("secret_hash push must be 32 bytes")
        expect_op(OP_EQUALVERIFY)
        maker_pubkey = expect_push()
        expect_op(OP_CHECKSIG)
        expect_op(OP_ELSE)
        timeout_bytes = expect_push()
        timeout = decode_num(timeout_bytes)
        expect_op(OP_CHECKLOCKTIMEVERIFY)
        expect_op(OP_DROP)
        taker_pubkey = expect_push()
        expect_op(OP_CHECKSIG)
        expect_op(OP_ENDIF)
        if i != len(script):
            raise ValueError("trailing bytes after ENDIF")
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"malformed witness script: {e}")
    validate_pubkey(maker_pubkey, "maker (IF branch)")
    validate_pubkey(taker_pubkey, "taker (ELSE branch)")
    if not (0 < timeout < LOCKTIME_THRESHOLD):
        raise ValueError(f"timeout out of block-height range: {timeout}")
    return {
        "maker_pubkey": maker_pubkey,
        "taker_pubkey": taker_pubkey,
        "secret_hash": secret_hash,
        "timeout": timeout,
    }


def script_hash(script: bytes) -> bytes:
    return hashlib.sha256(script).digest()


def p2wsh_script_pubkey(script: bytes) -> bytes:
    """OP_0 <SHA256(witness_script)>."""
    return bytes([OP_0]) + push(script_hash(script))


def p2wsh_address(script: bytes, hrp: str = "bc") -> str:
    """Native SegWit v0 P2WSH address (bech32, mainnet hrp 'bc')."""
    return bech32_encode(hrp, 0, script_hash(script))


def build_lock(maker_pubkey: bytes, taker_pubkey: bytes,
               secret_hash: bytes, timeout: int) -> dict:
    """Build everything a taker needs to fund the lock. No signing."""
    script = build_witness_script(maker_pubkey, taker_pubkey, secret_hash, timeout)
    parsed = parse_witness_script(script)
    assert parsed["maker_pubkey"] == maker_pubkey
    assert parsed["taker_pubkey"] == taker_pubkey
    return {
        "witness_script_hex": script.hex(),
        "witness_script_hash": script_hash(script).hex(),
        "script_pubkey_hex": p2wsh_script_pubkey(script).hex(),
        "address": p2wsh_address(script),
        "maker_pubkey": maker_pubkey.hex(),
        "taker_pubkey": taker_pubkey.hex(),
        "secret_hash": secret_hash.hex(),
        "timeout": timeout,
    }


# ---------------------------------------------------------------- BIP143 sighash (SIGHASH_ALL only)
def bip143_sighash(tx: dict, input_index: int, script_code: bytes, spent_value: int) -> bytes:
    """BIP143 sighash for one P2WSH input.

    tx dict format (same convention as azusa_segwit.bip143_sighash, so
    the two can be cross-checked):
      version: int
      vin: [{prev_txid: 32 bytes in WIRE order (as serialised),
             prev_vout: int, sequence: int}]
      vout: [{value: int sats, script_pubkey: bytes}]
      locktime: int
    script_code is the witness script. spent_value is the value of the
    HTLC output being spent, in sats (committed by BIP143).
    """
    if spent_value is None:
        raise ValueError("BIP143 sighash requires the spent value")
    vin = tx["vin"]
    prevouts = b"".join(bytes(v["prev_txid"]) + int(v["prev_vout"]).to_bytes(4, "little") for v in vin)
    sequences = b"".join(int(v["sequence"]).to_bytes(4, "little") for v in vin)
    outputs = b"".join(
        int(o["value"]).to_bytes(8, "little") + varint(len(o["script_pubkey"])) + o["script_pubkey"]
        for o in tx["vout"])
    inp = vin[input_index]
    preimage = (
        int(tx["version"]).to_bytes(4, "little", signed=True)
        + sha256d(prevouts)
        + sha256d(sequences)
        + bytes(inp["prev_txid"]) + int(inp["prev_vout"]).to_bytes(4, "little")
        + varint(len(script_code)) + script_code
        + int(spent_value).to_bytes(8, "little")
        + int(inp["sequence"]).to_bytes(4, "little")
        + sha256d(outputs)
        + int(tx["locktime"]).to_bytes(4, "little")
        + SIGHASH_ALL.to_bytes(4, "little")
    )
    return sha256d(preimage)


# ---------------------------------------------------------------- unsigned tx templates
def claim_tx_template(lock_txid_wire: bytes, lock_vout: int,
                      dest_script_pubkey: bytes, amount_sats: int,
                      fee_sats: int = 0) -> dict:
    """UNSIGNED maker-claim transaction template.

    lock_txid_wire: 32 bytes, wire order. amount_sats is the HTLC output
    value; the destination receives amount - fee. Witness is an empty
    placeholder: [maker_sig, secret_preimage, 0x01, witness_script],
    filled only after a separately approved signing step. locktime 0:
    the claim path has no CLTV, but the claim must be broadcast (and
    confirmed) before the taker spends the refund path — first valid
    spend wins.
    """
    if amount_sats - fee_sats <= 0:
        raise ValueError("claim output must be positive after fee")
    return {
        "version": 2,
        "vin": [{
            "prev_txid": bytes(lock_txid_wire),
            "prev_vout": int(lock_vout),
            "sequence": 0xFFFFFFFF,
            "script_sig": b"",
            "witness": None,  # UNSIGNED placeholder
        }],
        "vout": [{"value": int(amount_sats - fee_sats), "script_pubkey": bytes(dest_script_pubkey)}],
        "locktime": 0,
        "unsigned": True,
        "path": "claim (maker, secret)",
    }


def refund_tx_template(lock_txid_wire: bytes, lock_vout: int,
                       dest_script_pubkey: bytes, amount_sats: int,
                       timeout: int, fee_sats: int = 0) -> dict:
    """UNSIGNED taker-refund transaction template.

    locktime MUST be >= timeout, and sequence MUST NOT be 0xffffffff,
    or CLTV fails. Witness placeholder: [taker_sig, 0x00,
    witness_script], filled only after a separately approved signing
    step. A refund template with locktime < timeout is rejected here,
    before any signing is attempted.
    """
    if timeout <= 0 or timeout >= LOCKTIME_THRESHOLD:
        raise ValueError("refund timeout must be a block height")
    if amount_sats - fee_sats <= 0:
        raise ValueError("refund output must be positive after fee")
    return {
        "version": 2,
        "vin": [{
            "prev_txid": bytes(lock_txid_wire),
            "prev_vout": int(lock_vout),
            "sequence": 0xFFFFFFFE,
            "script_sig": b"",
            "witness": None,  # UNSIGNED placeholder
        }],
        "vout": [{"value": int(amount_sats - fee_sats), "script_pubkey": bytes(dest_script_pubkey)}],
        "locktime": int(timeout),
        "unsigned": True,
        "path": "refund (taker, after timeout)",
    }


# ---------------------------------------------------------------- pure validation (no interpreter, no keys)
def validate_claim(secret_preimage: bytes, script: bytes) -> bool:
    """True iff the preimage hashes to the script's secret hash."""
    try:
        parsed = parse_witness_script(script)
    except ValueError:
        return False
    return hashlib.sha256(secret_preimage).digest() == parsed["secret_hash"]


def validate_refund(tx_locktime: int, input_sequence: int, script: bytes) -> bool:
    """True iff the refund's CLTV preconditions hold (locktime reached,
    sequence not final). Signature validity is checked separately by
    script execution; this rejects premature refunds before signing."""
    try:
        parsed = parse_witness_script(script)
    except ValueError:
        return False
    if input_sequence == 0xFFFFFFFF:
        return False
    if tx_locktime < parsed["timeout"]:
        return False
    if (tx_locktime < LOCKTIME_THRESHOLD) != (parsed["timeout"] < LOCKTIME_THRESHOLD):
        return False
    return True


# ---------------------------------------------------------------- interpreter execution (tests / verification only)
def execute_witness(witness: list, script: bytes, sighash: bytes,
                    tx_locktime: int = 0, sequence: int = 0xFFFFFFFF):
    """Execute witness items + witness script in bitcoin_script.py.

    witness: list of byte pushes in witness order, EXCLUDING the final
    witness script itself (it is appended here). sighash is the BIP143
    sighash the CHECKSIG calls must verify against. Returns
    (ok, reason) from the interpreter. This is how tests prove a claim
    or refund path executes — it is not a signing step.
    """
    try:
        sys.path.insert(0, __file__.rsplit("/", 1)[0])
        import bitcoin_script

        def sighash_fn(sighash_type):
            return sighash

        combined = b"".join(push(item) for item in witness) + script
        return bitcoin_script.eval_script(
            combined, sighash_fn,
            context={"tx_locktime": tx_locktime, "sequence": sequence, "version": 2})
    except Exception as e:
        return False, f"interpreter unavailable: {e}"


# ---------------------------------------------------------------- tip / timeout helpers (curl only, never urllib)
def fetch_btc_tip_height(timeout_s: int = 25) -> int:
    """Current Bitcoin mainnet tip height via mempool.space (curl)."""
    out = subprocess.run(
        ["curl", "-s", "-m", str(timeout_s), "https://mempool.space/api/blocks/tip/height"],
        capture_output=True, text=True, check=False)
    text = (out.stdout or "").strip()
    if out.returncode != 0 or not text.isdigit():
        raise RuntimeError(f"could not fetch BTC tip height via curl (rc={out.returncode}, out={text!r}, err={out.stderr[:200]!r})")
    return int(text)


def timeout_height(current_tip: int, blocks: int = BTC_TIMEOUT_BLOCKS) -> int:
    if current_tip <= 0:
        raise ValueError("current_tip must be positive")
    height = current_tip + blocks
    if height >= LOCKTIME_THRESHOLD:
        raise ValueError("timeout height would exceed block-height range")
    return height


def wall_time_analysis(btc_blocks: int = BTC_TIMEOUT_BLOCKS,
                       excal_blocks: int = EXCAL_TIMEOUT_BLOCKS,
                       btc_block_seconds: float = 600.0,
                       fork_block_seconds_nominal: float = 60.0,
                       fork_block_seconds_observed: float = 68.0) -> dict:
    """Wall-time comparison of the two legs. Block counts are NOT time.

    BTC leg: btc_blocks * 600s. EXCAL leg: excal_blocks * fork pace.
    The atomic-swap safety condition is: the taker must be FORCED to
    reveal the secret (by claiming EXCAL) well BEFORE the BTC refund
    deadline, so the maker still has time to claim BTC with the revealed
    secret. That requires EXCAL window < BTC window, with margin for
    confirmations. If the EXCAL window were longer than the BTC window,
    the taker could refund BTC and still claim EXCAL afterwards — the
    maker would lose both sides.
    """
    btc_seconds = btc_blocks * btc_block_seconds
    excal_nominal = excal_blocks * fork_block_seconds_nominal
    excal_observed = excal_blocks * fork_block_seconds_observed
    return {
        "btc_blocks": btc_blocks,
        "btc_seconds": btc_seconds,
        "btc_hours": btc_seconds / 3600.0,
        "excal_blocks": excal_blocks,
        "excal_seconds_nominal_60s": excal_nominal,
        "excal_hours_nominal_60s": excal_nominal / 3600.0,
        "excal_seconds_observed_68s": excal_observed,
        "excal_hours_observed_68s": excal_observed / 3600.0,
        "margin_hours_nominal": (btc_seconds - excal_nominal) / 3600.0,
        "margin_hours_observed": (btc_seconds - excal_observed) / 3600.0,
        "safe_at_nominal_fork_pace": excal_nominal < btc_seconds,
        "safe_at_observed_fork_pace": excal_observed < btc_seconds,
        # Counterfactual, for the offer sheet: if the fork really ran at
        # 600s/block (the excalibur.py mainnet SPACING constant, NOT the
        # fork's daa_spacing=60 pace), 288 blocks would be 48h > 24h and
        # the timeouts would be UNSAFE as written.
        "excal_hours_if_fork_were_600s": (excal_blocks * 600.0) / 3600.0,
        "safe_if_fork_were_600s": (excal_blocks * 600.0) < btc_seconds,
    }


if __name__ == "__main__":
    # Demo of structure only, with the taker explicitly marked TBD:
    # this block does not build a live lock (no taker pubkey on record).
    print("maker pubkey:", MAKER_PUBKEY_HEX)
    print("secret hash: ", SECRET_HASH_HEX)
    print("BTC timeout blocks:", BTC_TIMEOUT_BLOCKS, "| EXCAL timeout blocks:", EXCAL_TIMEOUT_BLOCKS)
    print("wall time:", json.dumps(wall_time_analysis(), indent=2))
    print("NOTE: no live lock is built here — taker pubkey is TBD.")
