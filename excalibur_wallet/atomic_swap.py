"""atomic_swap.py — cross-chain atomic swap: EXCAL HTLC/QHTLC + BTC P2WSH HTLC.

This fuses the two legs the wallet already knows how to build:

* EXCAL leg — fork HTLC lock 0x03 (locks.htlc_lock / txbuild.build_htlc_*)
  or fork QHTLC lock 0x04 (locks.qhtlc_lock / txbuild.build_qhtlc_*).
  HTLC descriptor: secret_hash (32) | claim_pubkey (33) |
  refund_pubkey (33) | timeout (4, big-endian). Claim = taker with the
  secret; refund = maker after the fork timeout (height-enforced, not
  locktime). QHTLC descriptor: secret_hash (32) | claim_root (32) |
  refund_root (32) | timeout (4, big-endian). Claim = taker with the
  secret + a Trifold witness under the claim root; refund = maker
  with a Trifold witness under the refund root after the timeout.
  Which leg kind a swap uses is recorded as `excal_leg_kind`
  ("htlc" or "qhtlc"); the BTC leg and the state machine are the
  same either way, and funding verification is lock-agnostic (it
  checks the funding tx pays the record's lock). QHTLC legs exist
  so the swap flow can take over the three funded QHTLC offer lots
  (1,000 / 1 / 0.001 EXCAL) — their claim roots come from Lux's
  claim seed, delivered encrypted to the taker by the watcher, and
  the taker supplies that seed per claim (the wallet never holds
  Lux's seed; `wallet qhtlc claim` likewise accepts an external
  --claim-seed instead of requiring the wallet's own Trifold key).
* BTC leg — P2WSH HTLC (btc_htlc.build_witness_script / build_btc_htlc_*).
  OP_IF OP_SHA256 <hash> OP_EQUALVERIFY <claim> OP_CHECKSIG OP_ELSE
  <timeout> OP_CHECKLOCKTIMEVERIFY OP_DROP <refund> OP_CHECKSIG OP_ENDIF.
  Claim = maker with the secret; refund = taker after the BTC timeout
  (refund tx locktime = timeout, input sequence non-final). The BTC
  funding tx may carry the watcher signal (opt-in): an OP_RETURN
  output (lot tag + taker delivery pubkey) plus a 1,000-sat payment
  to the signal address, so the watcher sees the funding and
  delivers the encrypted claim seed for a QHTLC lot. Without the
  signal the watcher never sees a wallet-built funding tx.
* BTC leg — P2WSH HTLC (btc_htlc.build_witness_script / build_btc_htlc_*).
  OP_IF OP_SHA256 <hash> OP_EQUALVERIFY <claim> OP_CHECKSIG OP_ELSE
  <timeout> OP_CHECKLOCKTIMEVERIFY OP_DROP <refund> OP_CHECKSIG OP_ENDIF.
  Claim = maker with the secret; refund = taker after the BTC timeout
  (refund tx locktime = timeout, input sequence non-final).

Roles (the Strange template's roles, ~/workspace/strange-atomic-swap-
2026-11-11/, used as REFERENCE ONLY — that directory is never read
here and never modified):
* MAKER locks EXCAL first, then claims the BTC leg with the secret —
  revealing it. The maker key is the BTC leg's CLAIM key and the EXCAL
  leg's REFUND key.
* TAKER locks BTC second, then claims the EXCAL leg with the revealed
  secret. The taker key is the EXCAL leg's CLAIM key and the BTC leg's
  REFUND key.

Both legs lock the SAME secret hash. The secret itself is NEVER stored:
the swap record keeps only the hash; whoever needs the secret supplies
it per command (maker generates it at create and shows it once).

Timeout ordering — the safety invariant, enforced by validate_timeouts:
the BTC leg must expire FIRST and the EXCAL leg strictly LATER, with
at least DEFAULT_SAFETY_MARGIN_SECONDS (24h) of wall-clock between
the two expiries. That gives the taker a full day to claim the EXCAL
leg after the maker reveals the secret by claiming BTC, and it means
the maker can only refund the EXCAL leg after the BTC leg has already
expired — so he cannot take both. Wall clock uses nominal block times
(BTC 600s, fork 60s); the fork is observed slower than nominal, which
only lengthens the taker's window.

State machine (recorded in the wallet's "swaps" list, same style as
the "locks" book and the ledger's pending_spend tracking — a swap
record is the single source of truth for where a swap stands):

    created -> excal-funded -> btc-funded -> btc-claimed -> complete
                  |                |              (taker claims EXCAL
                  |                |               with revealed secret)
                  |                +-> btc-refunded   (taker, after BTC
                  |                      timeout)
                  +-> excal-refunded   (maker, after fork timeout AND
                                        after the BTC timeout if the
                                        BTC leg was ever funded)

Terminal states: complete, excal-refunded, btc-refunded. Every
transition is checked by `transition()`; illegal moves (claim before
fund, refund after claim, wrong role, refund while the other leg is
still live) are refused. All builders are dry-run only: they build,
sign EVERY input, and verify every signature locally (the fork
builders run the full fork validator; the BTC builders re-verify each
signature over the BIP143 sighash). Nothing here broadcasts.

Cross-references: the Strange template's numbers (0.5 EXCAL <->
0.5 BTC, BTC tip+144, fork tip+2880) are the defaults for the timeout
helpers, not hard-coded amounts — any amounts may be swapped.
"""

import hashlib
import secrets

from txscript import (htlc_descriptor, lock_htlc_for_descriptor,
                      qhtlc_descriptor, lock_qhtlc_for_descriptor,
                      parse_qhtlc_descriptor, parse_tx, txid_display)

from . import btc_htlc
from .btc_htlc import BtcHtlcError
from .txbuild import (TxBuildError, build_send, build_htlc_claim,
                      build_htlc_refund, build_qhtlc_claim,
                      build_qhtlc_refund, DUST_SWORDS)

# Nominal block times (seconds). The fork is observed slower than
# nominal, which only lengthens the taker's claim window — using the
# nominal 60s is the conservative direction.
BTC_BLOCK_SECONDS = 600
FORK_BLOCK_SECONDS = 60
# Minimum wall-clock gap between the BTC leg expiring and the EXCAL
# leg expiring: the taker's window to claim EXCAL after the reveal.
DEFAULT_SAFETY_MARGIN_SECONDS = 86400
# Strange-template defaults: BTC tip+144 (~24h), fork tip+2880 (~48h
# nominal). Used by the CLI when a timeout is not given explicitly.
DEFAULT_BTC_TIMEOUT_BLOCKS = 144
DEFAULT_FORK_TIMEOUT_BLOCKS = 2880
BTC_DUST_SATS = 546

STATES = ("created", "excal-funded", "btc-funded", "btc-claimed",
          "complete", "excal-refunded", "btc-refunded")
TERMINAL_STATES = ("complete", "excal-refunded", "btc-refunded")

# from-state -> {to-state: (role allowed to move it, None = either)}
_ALLOWED = {
    "created": {"excal-funded": None},
    "excal-funded": {"btc-funded": None, "excal-refunded": "maker"},
    "btc-funded": {"btc-claimed": None, "excal-refunded": "maker",
                   "btc-refunded": "taker"},
    "btc-claimed": {"complete": None},
}


class SwapError(Exception):
    """A swap was refused: bad parameters, illegal transition, or a
    safety invariant (timeout ordering, refund-while-live) failed."""


# ---------------------------------------------------------------- secrets
def new_secret() -> bytes:
    """A fresh random 32-byte swap secret (CSPRNG)."""
    return secrets.token_bytes(32)


def secret_hash_of(secret: bytes) -> bytes:
    if len(secret) != 32:
        raise SwapError("swap secret must be 32 bytes")
    return hashlib.sha256(secret).digest()


def check_secret(record: dict, secret: bytes) -> bool:
    """True iff the secret hashes to the record's secret hash."""
    try:
        return secret_hash_of(secret) == bytes.fromhex(
            record["secret_hash"])
    except (ValueError, KeyError):
        return False


# ---------------------------------------------------------------- legs
def derive_legs(secret_hash: bytes, maker_pub: bytes, taker_pub: bytes,
                excal_timeout: int, btc_timeout: int,
                network: str = "mainnet") -> dict:
    """Both legs from one secret hash. EXCAL leg: claim=taker,
    refund=maker. BTC leg: claim=maker, refund=taker. Returns
    {"excal": {"lock", "descriptor"}, "btc": {"address",
    "witness_script", "script_pubkey"}} — all hex except the address.
    Raises SwapError on a bad pubkey/hash/timeout."""
    try:
        btc_htlc.validate_pubkey(maker_pub, "maker")
        btc_htlc.validate_pubkey(taker_pub, "taker")
        if maker_pub == taker_pub:
            raise BtcHtlcError("maker and taker pubkeys must differ")
        if len(secret_hash) != 32:
            raise BtcHtlcError("secret hash must be 32 bytes")
        desc = htlc_descriptor(secret_hash, taker_pub, maker_pub,
                               excal_timeout)
        excal_lock = lock_htlc_for_descriptor(desc)
        btc_lock = btc_htlc.build_lock(maker_pub, taker_pub, secret_hash,
                                       btc_timeout, network)
    except (BtcHtlcError, ValueError, AssertionError) as e:
        raise SwapError(f"cannot derive swap legs: {e}")
    return {
        "excal": {"lock": excal_lock.hex(), "descriptor": desc.hex()},
        "btc": {"address": btc_lock["address"],
                "witness_script": btc_lock["witness_script_hex"],
                "script_pubkey": btc_lock["script_pubkey_hex"]},
    }


def derive_qhtlc_legs(secret_hash: bytes, claim_root: bytes,
                      refund_root: bytes, maker_pub: bytes,
                      taker_pub: bytes, excal_timeout: int,
                      btc_timeout: int,
                      network: str = "mainnet") -> dict:
    """Both legs from one secret hash, EXCAL leg as QHTLC (0x04).

    Same BTC leg as derive_legs (claim=maker, refund=taker). EXCAL
    leg: claim = the Trifold claim root (with the secret), refund =
    the Trifold refund root after the fork timeout. The roots are
    key material the maker holds (for the funded offer lots they
    come from Lux's claim/refund seeds); the wallet never derives
    them from its own keys. Returns the derive_legs shape plus
    "excal_leg_kind": "qhtlc" and the roots on the EXCAL leg.
    Raises SwapError on a bad root/hash/timeout or equal roots."""
    try:
        btc_htlc.validate_pubkey(maker_pub, "maker")
        btc_htlc.validate_pubkey(taker_pub, "taker")
        if maker_pub == taker_pub:
            raise BtcHtlcError("maker and taker pubkeys must differ")
        if len(secret_hash) != 32:
            raise BtcHtlcError("secret hash must be 32 bytes")
        for name, root in (("claim_root", claim_root),
                           ("refund_root", refund_root)):
            if not isinstance(root, (bytes, bytearray)) or len(root) != 32:
                raise BtcHtlcError(f"{name} must be 32 bytes")
        if bytes(claim_root) == bytes(refund_root):
            raise BtcHtlcError(
                "QHTLC claim and refund roots must differ (a lock "
                "whose claimer and refunder are the same root is a "
                "self-lock, not a swap)")
        desc = qhtlc_descriptor(bytes(secret_hash), bytes(claim_root),
                                bytes(refund_root), excal_timeout)
        excal_lock = lock_qhtlc_for_descriptor(desc)
        btc_lock = btc_htlc.build_lock(maker_pub, taker_pub, secret_hash,
                                       btc_timeout, network)
    except (BtcHtlcError, ValueError, AssertionError) as e:
        raise SwapError(f"cannot derive QHTLC swap legs: {e}")
    return {
        "excal_leg_kind": "qhtlc",
        "excal": {"lock": excal_lock.hex(), "descriptor": desc.hex(),
                  "claim_root": bytes(claim_root).hex(),
                  "refund_root": bytes(refund_root).hex()},
        "btc": {"address": btc_lock["address"],
                "witness_script": btc_lock["witness_script_hex"],
                "script_pubkey": btc_lock["script_pubkey_hex"]},
    }


def trifold_key_for_root(seed: bytes, want_root: bytes,
                         state_dir: str = None, max_height: int = 10):
    """A TrifoldKey from an externally supplied 32-byte seed whose
    root must be `want_root`. Tries tree heights 1..max_height (the
    claim seed's height is not recorded anywhere) and returns the
    matching key; the state's next_index persists under state_dir
    when given (one state file per root, named by the root). Raises
    SwapError if no height reproduces the root — the seed does not
    belong to this lock. The seed itself is never stored; the caller
    keeps it only for the one claim/refund it signs."""
    if not isinstance(seed, (bytes, bytearray)) or len(seed) != 32:
        raise SwapError("Trifold seed must be 32 bytes")
    if not isinstance(want_root, (bytes, bytearray)) \
            or len(want_root) != 32:
        raise SwapError("wanted Trifold root must be 32 bytes")
    from trifold_lockbox import TrifoldKey
    want = bytes(want_root)
    for height in range(1, max_height + 1):
        try:
            key = TrifoldKey(bytes(seed), height=height,
                             state_dir=state_dir)
        except ValueError:
            continue
        if key.root == want:
            return key
    raise SwapError(
        "claim seed does not reproduce the lock's Trifold root at "
        "any height 1..10 — wrong seed for this lock")


def validate_timeouts(btc_timeout: int, btc_height: int,
                      excal_timeout: int, fork_height: int,
                      margin_seconds: int = DEFAULT_SAFETY_MARGIN_SECONDS):
    """Enforce the ordering invariant. Both timeouts must be in the
    future, and the EXCAL leg must expire at least margin_seconds of
    wall-clock AFTER the BTC leg. Raises SwapError otherwise."""
    if btc_timeout <= btc_height:
        raise SwapError(
            f"BTC timeout {btc_timeout} is not in the future "
            f"(BTC height {btc_height})")
    if excal_timeout <= fork_height:
        raise SwapError(
            f"EXCAL timeout {excal_timeout} is not in the future "
            f"(fork height {fork_height})")
    btc_remaining = (btc_timeout - btc_height) * BTC_BLOCK_SECONDS
    excal_remaining = (excal_timeout - fork_height) * FORK_BLOCK_SECONDS
    gap = excal_remaining - btc_remaining
    if gap < margin_seconds:
        raise SwapError(
            f"unsafe timeout ordering: EXCAL leg expires only {gap}s "
            f"after the BTC leg (need >= {margin_seconds}s) — the "
            f"taker would have no safe window to claim the EXCAL leg "
            f"after the secret is revealed")


# ---------------------------------------------------------------- record
def new_swap(role: str, maker_pub: bytes, taker_pub: bytes,
             excal_amount: int, btc_amount: int, excal_timeout: int,
             btc_timeout: int, fork_height: int, btc_height: int,
             secret: bytes = None, secret_hash: bytes = None,
             network: str = "mainnet", excal_leg_kind: str = "htlc",
             claim_root: bytes = None, refund_root: bytes = None) -> dict:
    """Build a swap record (state "created"). Maker: pass secret (or
    None to generate one — the caller must show it once, it is NOT
    stored). Taker: pass secret_hash (the secret is unknown to the
    taker until the maker reveals it). The record keeps hashes only —
    no secret, no key. Raises SwapError on bad parameters.

    excal_leg_kind: "htlc" (default, ECDSA claim/refund keys) or
    "qhtlc" (Trifold claim/refund roots — pass claim_root and
    refund_root, 32 bytes each; required for "qhtlc", refused for
    "htlc"). A QHTLC record is how the swap flow takes over a
    pre-funded QHTLC lot: the taker creates it from the lot's public
    parameters (secret hash, both roots, timeout, amounts) and the
    lot's funding tx then verifies against the record's lock."""
    if excal_leg_kind not in ("htlc", "qhtlc"):
        raise SwapError(
            f"excal_leg_kind must be 'htlc' or 'qhtlc' "
            f"(got {excal_leg_kind!r})")
    if excal_leg_kind == "qhtlc":
        for name, root in (("claim_root", claim_root),
                           ("refund_root", refund_root)):
            if root is None or len(root) != 32:
                raise SwapError(
                    f"QHTLC swap needs a 32-byte {name}")
        if bytes(claim_root) == bytes(refund_root):
            raise SwapError("QHTLC claim and refund roots must differ")
    elif claim_root is not None or refund_root is not None:
        raise SwapError("HTLC swap takes no claim/refund roots — "
                        "pass --excal-leg qhtlc for a QHTLC leg")
    if role not in ("maker", "taker"):
        raise SwapError(f"role must be 'maker' or 'taker' (got {role!r})")
    if excal_amount < DUST_SWORDS:
        raise SwapError(
            f"EXCAL amount {excal_amount} is dust "
            f"(< {DUST_SWORDS} swords)")
    if btc_amount < BTC_DUST_SATS:
        raise SwapError(
            f"BTC amount {btc_amount} is dust (< {BTC_DUST_SATS} sats)")
    if role == "maker":
        if secret_hash is not None:
            raise SwapError("maker creates the secret — do not pass "
                            "a secret hash")
        if secret is None:
            secret = new_secret()
        secret_hash = secret_hash_of(secret)
    else:
        if secret is not None:
            raise SwapError("taker does not know the secret yet — "
                            "pass --secret-hash, not --secret")
        if secret_hash is None or len(secret_hash) != 32:
            raise SwapError("taker needs the maker's 32-byte secret hash")
    validate_timeouts(btc_timeout, btc_height, excal_timeout, fork_height)
    if excal_leg_kind == "qhtlc":
        legs = derive_qhtlc_legs(secret_hash, claim_root, refund_root,
                                 maker_pub, taker_pub, excal_timeout,
                                 btc_timeout, network)
    else:
        legs = derive_legs(secret_hash, maker_pub, taker_pub,
                           excal_timeout, btc_timeout, network)
    from datetime import datetime, timezone
    # Normalize the EXCAL leg: HTLC legs carry no roots (None), QHTLC
    # legs carry both — so every record has the same keys.
    excal_leg = dict({"claim_root": None, "refund_root": None},
                     **legs["excal"], funding_txid=None, funding_vout=0,
                     claim_txid=None, refund_txid=None)
    return {
        "swap_id": secret_hash[:8].hex(),
        "role": role,
        "state": "created",
        "secret_hash": secret_hash.hex(),
        "network": network,
        "excal_leg_kind": excal_leg_kind,
        "excal_amount": excal_amount,
        "btc_amount": btc_amount,
        "maker_pubkey": maker_pub.hex(),
        "taker_pubkey": taker_pub.hex(),
        "excal_timeout": excal_timeout,
        "btc_timeout": btc_timeout,
        "fork_height_at_create": fork_height,
        "btc_height_at_create": btc_height,
        "excal": excal_leg,
        "btc": dict(legs["btc"], funding_txid=None, funding_vout=0,
                    claim_txid=None, refund_txid=None),
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def transition(record: dict, to_state: str, role: str = None,
               fork_height: int = None, btc_height: int = None) -> dict:
    """Move a swap record to a new state, enforcing the state machine
    AND the refund safety rules. Returns a NEW record dict (the input
    is not mutated). Raises SwapError on any refusal.

    Refund rules (the atomicity of the whole swap):
    * "btc-claimed" has no role guard: the move is recorded by the
      maker (claim-btc, which builds the claim) or by the taker
      (note-btc-claimed, which verifies the maker's claim tx — the
      claim tx itself is the proof the maker claimed). The CLI
      enforces who may perform each act; the state machine only
      enforces ordering + refund safety.
    * excal-refunded (maker): fork height must be >= the EXCAL
      timeout, AND — if the BTC leg was ever funded — the BTC height
      must be >= the BTC timeout, so the maker cannot refund EXCAL
      and then still claim the BTC leg.
    * btc-refunded (taker): BTC height must be >= the BTC timeout.
      The EXCAL leg then stays locked until its own timeout, when
      the maker refunds it; the taker cannot claim it without the
      secret, which was never revealed."""
    if to_state not in STATES:
        raise SwapError(f"unknown swap state {to_state!r}")
    cur = record["state"]
    if cur in TERMINAL_STATES:
        raise SwapError(f"swap is terminal ({cur}) — no further moves")
    allowed = _ALLOWED.get(cur, {})
    if to_state not in allowed:
        raise SwapError(
            f"illegal swap transition {cur} -> {to_state} "
            f"(allowed from {cur}: {sorted(allowed) or 'none'})")
    want_role = allowed[to_state]
    if want_role is not None and role is not None and role != want_role:
        raise SwapError(
            f"transition {cur} -> {to_state} is the {want_role}'s move, "
            f"not the {role}'s")
    if to_state == "excal-refunded":
        if fork_height is None:
            raise SwapError("excal refund needs the current fork height")
        if fork_height < record["excal_timeout"]:
            raise SwapError(
                f"EXCAL refund refused: fork height {fork_height} is "
                f"below the EXCAL timeout {record['excal_timeout']}")
        if record["btc"]["funding_txid"] is not None:
            if btc_height is None:
                raise SwapError(
                    "EXCAL refund needs the current BTC height — the "
                    "BTC leg was funded and must be expired first")
            if btc_height < record["btc_timeout"]:
                raise SwapError(
                    f"EXCAL refund refused: the BTC leg is still live "
                    f"(BTC height {btc_height} < timeout "
                    f"{record['btc_timeout']}) — refunding now would "
                    f"let the maker take both legs")
    if to_state == "btc-refunded":
        if btc_height is None:
            raise SwapError("BTC refund needs the current BTC height")
        if btc_height < record["btc_timeout"]:
            raise SwapError(
                f"BTC refund refused: BTC height {btc_height} is below "
                f"the BTC timeout {record['btc_timeout']}")
    out = dict(record)
    out["excal"] = dict(record["excal"])
    out["btc"] = dict(record["btc"])
    out["state"] = to_state
    return out


# ---------------------------------------------------------------- verification
def verify_btc_funding_raw(record: dict, raw_hex: str) -> dict:
    """Verify a counterparty's BTC funding tx (raw hex) against the
    record: it must pay exactly btc_amount to the leg's P2WSH
    scriptPubKey. Returns {"txid", "vout"}. Raises SwapError."""
    try:
        raw = bytes.fromhex(raw_hex)
    except ValueError:
        raise SwapError("BTC funding raw hex is not hex")
    try:
        tx = btc_htlc.parse_segwit_tx(raw)
    except BtcHtlcError as e:
        raise SwapError(f"cannot parse BTC funding tx: {e}")
    want_spk = bytes.fromhex(record["btc"]["script_pubkey"])
    for i, o in enumerate(tx["vout"]):
        if o["script_pubkey"] == want_spk and o["value"] == record["btc_amount"]:
            return {"txid": btc_htlc.txid_display(tx), "vout": i}
    raise SwapError(
        "BTC funding tx does not pay "
        f"{record['btc_amount']:,} sats to the swap's P2WSH address "
        f"{record['btc']['address']}")


def verify_btc_claim_raw(record: dict, raw_hex: str) -> dict:
    """Verify the maker's BTC claim tx (raw hex) against the record:
    it must spend the recorded BTC funding UTXO, its witness must be
    [sig, secret, 0x01, script] with the script matching the leg, and
    the secret must hash to the record's secret hash. Returns
    {"txid", "secret"} — the secret is public once this tx exists,
    so returning it is how the taker learns it. Raises SwapError."""
    try:
        raw = bytes.fromhex(raw_hex)
    except ValueError:
        raise SwapError("BTC claim raw hex is not hex")
    try:
        tx = btc_htlc.parse_segwit_tx(raw)
    except BtcHtlcError as e:
        raise SwapError(f"cannot parse BTC claim tx: {e}")
    leg = record["btc"]
    if not leg["funding_txid"]:
        raise SwapError("BTC leg is not funded yet")
    want_prev = bytes.fromhex(leg["funding_txid"])[::-1]
    for i, vin in enumerate(tx["vin"]):
        if vin["prev_txid"] != want_prev or vin["prev_vout"] != leg["funding_vout"]:
            continue
        wit = vin.get("witness") or []
        if len(wit) != 4:
            raise SwapError(
                "BTC claim witness is not [sig, secret, 0x01, script]")
        secret, flag, script = wit[1], wit[2], wit[3]
        if flag != b"\x01":
            raise SwapError("BTC claim witness does not take the IF "
                            "(claim) branch")
        if script != bytes.fromhex(leg["witness_script"]):
            raise SwapError("BTC claim witness script is not the swap's")
        if hashlib.sha256(secret).digest() != bytes.fromhex(
                record["secret_hash"]):
            raise SwapError("BTC claim secret does not hash to the "
                            "swap's secret hash")
        return {"txid": btc_htlc.txid_display(tx), "secret": secret}
    raise SwapError("BTC claim tx does not spend the swap's BTC funding "
                    "UTXO")


def verify_excal_funding_raw(record: dict, raw_hex: str) -> dict:
    """Verify a counterparty's EXCAL funding tx (raw hex) against the
    record: it must pay exactly excal_amount to the leg's lock. The
    check is lock-agnostic — it works for an HTLC leg and for a
    QHTLC leg alike, because it compares against the record's lock.
    Returns {"txid", "vout"}. Raises SwapError."""
    try:
        raw = bytes.fromhex(raw_hex)
    except ValueError:
        raise SwapError("EXCAL funding raw hex is not hex")
    try:
        tx = parse_tx(raw)
    except Exception as e:
        raise SwapError(f"cannot parse EXCAL funding tx: {e}")
    want_lock = bytes.fromhex(record["excal"]["lock"])
    for i, o in enumerate(tx["vout"]):
        if o["script"] == want_lock and o["value"] == record["excal_amount"]:
            return {"txid": txid_display(raw), "vout": i}
    raise SwapError(
        "EXCAL funding tx does not pay "
        f"{record['excal_amount']:,} swords to the swap's "
        f"{record.get('excal_leg_kind', 'htlc').upper()} lock "
        f"{record['excal']['lock']}")


# ---------------------------------------------------------------- builders
# Every builder below builds a full tx, signs EVERY input, and verifies
# every signature locally before returning (fork builders run the full
# fork validator; BTC builders re-verify each signature over the BIP143
# sighash). Nothing broadcasts. Funding/claim/refund txids are recorded
# by the caller via transition() + the wallet's update_swap().

def build_excal_funding(record: dict, utxos: list, lock_to_priv: dict,
                        change_lock: bytes, fee_rate: int,
                        height: int) -> dict:
    """Maker funds the EXCAL leg: a normal fork send to the HTLC lock.
    utxos/lock_to_priv/change_lock/height are the wallet-send inputs
    (live-node validated UTXO set, validation height = tip+1)."""
    try:
        return build_send(utxos, lock_to_priv,
                          bytes.fromhex(record["excal"]["lock"]),
                          record["excal_amount"], change_lock,
                          fee_rate=fee_rate, height=height)
    except (TxBuildError, ValueError) as e:
        raise SwapError(f"EXCAL funding refused: {e}")


def build_btc_funding(record: dict, utxo: dict, pub_to_priv: dict,
                      change_pub: bytes, fee_rate: int = 5,
                      network: str = None, signal: dict = None) -> dict:
    """Taker funds the BTC leg from one P2WPKH UTXO. utxo: {txid,
    vout, value, script_pubkey (hex)}. The taker's key must be in
    pub_to_priv (it signs the funding input). signal (optional) is
    the watcher-signal dict for btc_htlc.build_btc_htlc_lock —
    {"tag", "delivery_pubkey", "signal_address", "signal_sats"} —
    which adds the OP_RETURN tag + 1,000-sat signal outputs so the
    swap watcher sees the funding (needed for QHTLC lots, whose
    claim seed is delivered only to a verified, signalled funding)."""
    taker_pub = bytes.fromhex(record["taker_pubkey"])
    if taker_pub not in pub_to_priv:
        raise SwapError("BTC funding key (taker) is not a wallet key")
    try:
        return btc_htlc.build_btc_htlc_lock(
            [utxo], pub_to_priv, record["btc_amount"],
            bytes.fromhex(record["maker_pubkey"]), taker_pub,
            bytes.fromhex(record["secret_hash"]), record["btc_timeout"],
            change_pub, fee_rate=fee_rate,
            network=network or record["network"], signal=signal)
    except BtcHtlcError as e:
        raise SwapError(f"BTC funding refused: {e}")


def build_btc_claim(record: dict, secret: bytes, dest_spk: bytes,
                    pub_to_priv: dict, fee_rate: int = 5) -> dict:
    """Maker claims the BTC leg with the secret — revealing it on
    chain. The funding txid/vout come from the record (state must be
    btc-funded; the caller enforces that via transition())."""
    if not check_secret(record, secret):
        raise SwapError("secret does not hash to the swap's secret hash")
    leg = record["btc"]
    if not leg["funding_txid"]:
        raise SwapError("BTC leg is not funded yet")
    maker_pub = bytes.fromhex(record["maker_pubkey"])
    if maker_pub not in pub_to_priv:
        raise SwapError("BTC claim key (maker) is not a wallet key")
    try:
        return btc_htlc.build_btc_htlc_claim(
            leg["funding_txid"], leg["funding_vout"],
            record["btc_amount"], dest_spk, secret,
            bytes.fromhex(leg["witness_script"]),
            pub_to_priv[maker_pub], fee_rate=fee_rate)
    except BtcHtlcError as e:
        raise SwapError(f"BTC claim refused: {e}")


def build_excal_claim(record: dict, utxo_entry: dict, dest_lock: bytes,
                      fee: int, secret: bytes, claim_priv: int,
                      height: int, trifold_key=None,
                      registry=None) -> dict:
    """Taker claims the EXCAL leg with the revealed secret. utxo_entry
    is the funded UTXO ({txid, vout, value, lock, coinbase, cb_h,
    mature}); height is the fork validation height (tip+1).

    HTLC leg: claim_priv is the taker's ECDSA key. QHTLC leg:
    trifold_key is a TrifoldKey whose root is the leg's claim root
    (derived from the claim seed the watcher delivered, via
    trifold_key_for_root) — the wallet's own Trifold key is NOT
    used for an externally-rooted lot; claim_priv must be None.
    registry, when given, is the spent-leaf registry used for the
    QHTLC signing (tests pass a throwaway registry; production
    uses the chain-data registry)."""
    if not check_secret(record, secret):
        raise SwapError("secret does not hash to the swap's secret hash")
    kind = record.get("excal_leg_kind", "htlc")
    if kind == "qhtlc":
        if trifold_key is None:
            raise SwapError(
                "QHTLC claim needs the claim seed (--claim-seed): "
                "the claim root belongs to the maker's seed, not to "
                "this wallet — pass the decrypted claim seed")
        if claim_priv is not None:
            raise SwapError(
                "QHTLC claim takes a Trifold key, not an ECDSA key")
        desc = bytes.fromhex(record["excal"]["descriptor"])
        want_root = parse_qhtlc_descriptor(desc)["claim_root"]
        if getattr(trifold_key, "root", None) != want_root:
            raise SwapError(
                "claim seed's Trifold root is not the leg's claim "
                "root — wrong seed for this swap")
        try:
            return build_qhtlc_claim(
                utxo_entry, dest_lock, fee, secret, desc, trifold_key,
                height, registry=registry)
        except (TxBuildError, ValueError, RuntimeError) as e:
            raise SwapError(f"EXCAL claim refused: {e}")
    try:
        return build_htlc_claim(
            utxo_entry, dest_lock, fee, secret,
            bytes.fromhex(record["excal"]["descriptor"]), claim_priv,
            height)
    except (TxBuildError, ValueError) as e:
        raise SwapError(f"EXCAL claim refused: {e}")


def build_excal_refund(record: dict, utxo_entry: dict, dest_lock: bytes,
                       fee: int, refund_priv: int, height: int,
                       trifold_key=None, registry=None) -> dict:
    """Maker refunds the EXCAL leg after its timeout (height >= the
    EXCAL timeout — enforced by the fork validator). The caller must
    also have passed transition(..., "excal-refunded") so the BTC leg
    is expired first.

    HTLC leg: refund_priv is the maker's ECDSA key. QHTLC leg:
    trifold_key is a TrifoldKey whose root is the leg's refund root
    (derived from the maker's refund seed); refund_priv must be None.
    registry is the spent-leaf registry for the QHTLC signing (see
    build_excal_claim)."""
    kind = record.get("excal_leg_kind", "htlc")
    if kind == "qhtlc":
        if trifold_key is None:
            raise SwapError(
                "QHTLC refund needs the refund seed (--refund-seed): "
                "the refund root belongs to the maker's seed, not to "
                "this wallet")
        if refund_priv is not None:
            raise SwapError(
                "QHTLC refund takes a Trifold key, not an ECDSA key")
        desc = bytes.fromhex(record["excal"]["descriptor"])
        want_root = parse_qhtlc_descriptor(desc)["refund_root"]
        if getattr(trifold_key, "root", None) != want_root:
            raise SwapError(
                "refund seed's Trifold root is not the leg's refund "
                "root — wrong seed for this swap")
        try:
            return build_qhtlc_refund(
                utxo_entry, dest_lock, fee, desc, trifold_key, height,
                registry=registry)
        except (TxBuildError, ValueError, RuntimeError) as e:
            raise SwapError(f"EXCAL refund refused: {e}")
    try:
        return build_htlc_refund(
            utxo_entry, dest_lock, fee,
            bytes.fromhex(record["excal"]["descriptor"]), refund_priv,
            height)
    except (TxBuildError, ValueError) as e:
        raise SwapError(f"EXCAL refund refused: {e}")


def build_btc_refund(record: dict, dest_spk: bytes, pub_to_priv: dict,
                     fee_rate: int, current_height: int) -> dict:
    """Taker refunds the BTC leg after its timeout. current_height is
    the BTC height (must be >= the BTC timeout — enforced by
    btc_htlc and by transition())."""
    leg = record["btc"]
    if not leg["funding_txid"]:
        raise SwapError("BTC leg is not funded yet")
    taker_pub = bytes.fromhex(record["taker_pubkey"])
    if taker_pub not in pub_to_priv:
        raise SwapError("BTC refund key (taker) is not a wallet key")
    try:
        return btc_htlc.build_btc_htlc_refund(
            leg["funding_txid"], leg["funding_vout"],
            record["btc_amount"], dest_spk,
            bytes.fromhex(leg["witness_script"]),
            pub_to_priv[taker_pub], current_height=current_height,
            fee_rate=fee_rate)
    except BtcHtlcError as e:
        raise SwapError(f"BTC refund refused: {e}")
