"""txbuild.py — build + sign + verify. NEVER broadcast.

Full spend-and-sign protocol, always (Lux's standing order):
  1. build the full transaction (all inputs, all outputs, fee)
  2. sign EVERY input with the right key/witness for its lock type
  3. re-verify every signature independently (secp.verify over the
     sighash), before any consensus call
  4. run the fork's own validate_tx over the raw tx at height tip+1
  5. return the raw hex + txid for the user to review

There is deliberately NO broadcast path in this module. A signed tx
leaves the wallet only as hex printed to the user (or saved to a file
they name). Submitting it is a separate, explicit user action through
the node's sendrawtransaction — never this wallet's job.

Fee: 1 sword/vbyte default (the node's floor). vsize estimate is the
node's (10 + 139/in + 30/out); the exact fee is recomputed from the
real serialized size, then the tx is rebuilt + re-signed once.
Dust is 1000 swords: change below dust is folded into the fee.
"""
import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import secp256k1 as secp
from genesis_fork import SWORD, knot_activation
from txscript import (ser_tx, parse_tx, validate_tx, sighash_all,
                      SIGHASH_ALL, lock_type, hash160,
                      sign_pkh_input, sign_bridge_input,
                      sign_htlc_claim, sign_htlc_refund,
                      sign_qhtlc_claim, sign_qhtlc_refund,
                      lock_pkh_for_pubkey)
from .locks import knot_lock_refuse

DUST_SWORDS = 1000
DEFAULT_FEE_RATE = 1  # swords per vbyte
SEQ_FINAL = 0xFFFFFFFF  # no-RBF, like the fork mempool


class TxBuildError(Exception):
    pass


def parse_amount(s):
    """Amount string -> swords. Plain integers are swords; a decimal or
    an 'EXCAL' suffix is EXCAL (1 EXCAL = 100,000,000 swords)."""
    t = str(s).strip().upper().replace("EXCAL", "").strip()
    if "." in t:
        whole, _, frac = t.partition(".")
        if len(frac) > 8 and int(frac[8:]) != 0:
            raise TxBuildError(
                f"amount {s!r} has sub-sword precision "
                f"(more than 8 decimal places)")
        frac = (frac + "00000000")[:8]
        return int(whole or 0) * SWORD + int(frac)
    return int(t)


def _est_fee(n_in, n_out, rate):
    return (10 + 139 * n_in + 30 * n_out) * rate


def _verify_pkh_signatures(t, utxo_locks):
    """Independent re-verification of every PKH/bridge signature in a
    built tx (same check knot_wallet.py performs). Raises on failure."""
    parsed = parse_tx(ser_tx(t))
    for i, vin in enumerate(parsed["vin"]):
        lock = utxo_locks[i]
        lt = lock_type(lock)
        if lt not in ("pkh", "bridge"):
            continue
        ss = vin["script"]
        if len(ss) not in (98, 130):
            raise TxBuildError(f"input {i}: bad {lt} scriptSig length")
        pk = ss[:33] if len(ss) == 98 else ss[:65]
        sig = ss[33:97] if len(ss) == 98 else ss[65:129]
        if lt == "pkh":
            if hash160(pk) != lock[1:]:
                raise TxBuildError(f"input {i}: pubkey != lock")
        else:
            if pk[1:33] != lock[1:]:
                raise TxBuildError(f"input {i}: pubkey x != bridge lock")
        if len(pk) == 65:
            pk_v = bytes([0x02 | (pk[64] & 1)]) + pk[1:33]
        else:
            pk_v = pk
        h = sighash_all(t, i, lock)
        if not secp.verify(pk_v, sig, h):
            raise TxBuildError(f"input {i}: signature does not verify")


def _validate(raw, utxo_view, height, spent_pairs=None):
    ok, reason, fee = validate_tx(raw, utxo_view, height,
                                  spent_pairs=spent_pairs)
    if not ok:
        raise TxBuildError(f"local validation failed: {reason}")
    return fee


def _view_from_utxos(selected):
    """{(txid_bytes, vout): [(value, lock, is_cb, cb_h)]} for validate_tx."""
    view = {}
    for u in selected:
        key = (bytes.fromhex(u["txid"]), u["vout"])
        view.setdefault(key, []).append(
            (u["value"], bytes.fromhex(u["lock"]),
             bool(u.get("coinbase", False)), int(u.get("cb_h", 0))))
    return view


def select_utxos(candidates, amount, fee_rate):
    """Largest-first selection of mature UTXOs covering amount + fee.
    Returns (selected, fee_estimate). Raises on insufficient funds."""
    cands = sorted([c for c in candidates if c.get("mature", True)],
                   key=lambda c: -c["value"])
    if not cands:
        raise TxBuildError("insufficient funds (no mature UTXOs)")
    selected, total = [], 0
    i = 0
    while True:
        fee = _est_fee(max(1, len(selected)), 2, fee_rate)
        if selected and total >= amount + fee:
            return selected, fee
        if i >= len(cands):
            raise TxBuildError(
                f"insufficient funds: need {amount + fee}, "
                f"have {total} swords mature")
        selected.append(cands[i])
        total += cands[i]["value"]
        i += 1


def build_send(utxos, lock_to_priv, dest_lock, amount,
               change_lock, fee_rate=DEFAULT_FEE_RATE, height=None):
    """Build + sign + verify a PKH/BRIDGE spend.

    utxos: [{txid, vout, value, lock (hex), coinbase, cb_h, mature}]
    lock_to_priv: {lock_hex: priv_int} for every spendable wallet lock
    dest_lock: 21-byte lock bytes for the payment output
    change_lock: 21-byte lock bytes for change
    height: validation height (tip+1); required.
    Returns {"raw_hex", "txid", "fee", "inputs", "outputs", "validated"}.
    Raises TxBuildError on any failure. No broadcast, ever."""
    if height is None:
        raise TxBuildError("validation height required (tip+1)")
    if amount <= 0:
        raise TxBuildError("amount must be positive")
    if amount < DUST_SWORDS:
        raise TxBuildError(f"dust: amount {amount} < {DUST_SWORDS} swords")
    if lock_type(dest_lock) is None:
        raise TxBuildError("destination is not a recognized lock")
    if lock_type(dest_lock) == "knot":
        knot_lock_refuse(height - 1)
    # Only PKH and BRIDGE inputs are spendable by this builder (both
    # use the same witness shape). PQH/HTLC/QHTLC have their own
    # builders below — a mixed send would hide which key authorized it.
    spendable = []
    for u in utxos:
        lt = lock_type(bytes.fromhex(u["lock"]))
        if lt in ("pkh", "bridge") and u["lock"] in lock_to_priv:
            spendable.append(u)
    selected, _fee = select_utxos(spendable, amount, fee_rate)
    total_in = sum(u["value"] for u in selected)

    def build(change_value, with_change):
        vout = [{"value": amount, "script": dest_lock}]
        if with_change:
            vout.append({"value": change_value, "script": change_lock})
        t = {"version": 1,
             "vin": [{"prev": bytes.fromhex(u["txid"]), "idx": u["vout"],
                      "script": b"", "seq": SEQ_FINAL} for u in selected],
             "vout": vout, "locktime": 0}
        for j, u in enumerate(selected):
            lock = bytes.fromhex(u["lock"])
            priv = lock_to_priv[u["lock"]]
            lt = lock_type(lock)
            try:
                if lt == "pkh":
                    t["vin"][j]["script"] = sign_pkh_input(t, j, lock, priv)
                elif lt == "bridge":
                    t["vin"][j]["script"] = sign_bridge_input(t, j, lock,
                                                               priv)
                else:
                    raise TxBuildError(
                        f"input {j}: unsupported lock {lt}")
            except AssertionError as e:
                raise TxBuildError(f"input {j}: signing failed: {e}")
        return t

    # Measure with a placeholder change output, then finalize.
    t = build(0, True)
    fee = len(ser_tx(t)) * fee_rate
    change = total_in - amount - fee
    if change >= DUST_SWORDS:
        t = build(change, True)
    else:
        t = build(0, False)
        fee = total_in - amount
    raw = ser_tx(t)
    fee = total_in - sum(v["value"] for v in t["vout"])
    _verify_pkh_signatures(t, [bytes.fromhex(u["lock"]) for u in selected])
    view = _view_from_utxos(selected)
    vfee = _validate(raw, view, height)
    if vfee != fee:
        raise TxBuildError(f"fee mismatch: computed {fee}, validated {vfee}")
    from txscript import txid_display
    return {"raw_hex": raw.hex(), "txid": txid_display(raw), "fee": fee,
            "inputs": [{"txid": u["txid"], "vout": u["vout"],
                        "value": u["value"]} for u in selected],
            "outputs": [{"value": v["value"], "lock": v["script"].hex()}
                        for v in t["vout"]],
            "validated": True, "validated_at_height": height,
            "broadcast": False}


# ------------------------------------------------------- single-lock spends
def _one_input_tx(prev_txid, prev_idx, dest_lock, amount, fee):
    if amount - fee <= 0:
        raise TxBuildError("amount after fee must be positive")
    return {"version": 1,
            "vin": [{"prev": bytes.fromhex(prev_txid), "idx": prev_idx,
                     "script": b"", "seq": SEQ_FINAL}],
            "vout": [{"value": amount - fee, "script": dest_lock}],
            "locktime": 0}


def _finish_single(t, utxo_entry, height, spent_pairs=None):
    raw = ser_tx(t)
    view = {(bytes.fromhex(utxo_entry["txid"]), utxo_entry["vout"]): [
        (utxo_entry["value"], bytes.fromhex(utxo_entry["lock"]),
         bool(utxo_entry.get("coinbase", False)),
         int(utxo_entry.get("cb_h", 0)))]}
    vfee = _validate(raw, view, height, spent_pairs=spent_pairs)
    from txscript import txid_display
    return {"raw_hex": raw.hex(), "txid": txid_display(raw), "fee": vfee,
            "validated": True, "validated_at_height": height,
            "broadcast": False}


def build_htlc_claim(utxo_entry, dest_lock, fee, secret, descriptor,
                     claim_priv, height, registry=None):
    """Spend an HTLC UTXO via the claim path (secret + claim key)."""
    from txscript import lock_htlc_for_descriptor
    lock = bytes.fromhex(utxo_entry["lock"])
    t = _one_input_tx(utxo_entry["txid"], utxo_entry["vout"],
                      dest_lock, utxo_entry["value"], fee)
    try:
        t["vin"][0]["script"] = sign_htlc_claim(t, 0, lock, claim_priv,
                                                secret, descriptor)
    except AssertionError as e:
        raise TxBuildError(f"HTLC claim signing failed: {e}")
    return _finish_single(t, utxo_entry, height)


def build_htlc_refund(utxo_entry, dest_lock, fee, descriptor,
                      refund_priv, height):
    """Spend an HTLC UTXO via the refund path (refund key, height >=
    timeout — enforced by validate_tx, not by this builder)."""
    lock = bytes.fromhex(utxo_entry["lock"])
    t = _one_input_tx(utxo_entry["txid"], utxo_entry["vout"],
                      dest_lock, utxo_entry["value"], fee)
    try:
        t["vin"][0]["script"] = sign_htlc_refund(t, 0, lock, refund_priv,
                                                 descriptor)
    except AssertionError as e:
        raise TxBuildError(f"HTLC refund signing failed: {e}")
    return _finish_single(t, utxo_entry, height)


def build_qhtlc_claim(utxo_entry, dest_lock, fee, secret, descriptor,
                      trifold_key, height, registry=None):
    """Spend a QHTLC UTXO via the claim path (secret + Trifold claim
    root). The Trifold leaf is recorded in the registry BEFORE signing
    (sign_qhtlc_claim's own guard) — a failed validation after this
    point burns the leaf; that is the documented safe direction."""
    lock = bytes.fromhex(utxo_entry["lock"])
    t = _one_input_tx(utxo_entry["txid"], utxo_entry["vout"],
                      dest_lock, utxo_entry["value"], fee)
    spent = _registry_set(registry)  # BEFORE signing: signing records
    try:                             # this leaf; validation must see
        t["vin"][0]["script"] = sign_qhtlc_claim(  # the pre-sign set
            t, 0, lock, trifold_key, secret, descriptor, registry=registry)
    except AssertionError as e:
        raise TxBuildError(f"QHTLC claim signing failed: {e}")
    return _finish_single(t, utxo_entry, height, spent_pairs=spent)


def build_qhtlc_refund(utxo_entry, dest_lock, fee, descriptor,
                       trifold_key, height, registry=None):
    """Spend a QHTLC UTXO via the refund path (Trifold refund root,
    height >= timeout enforced by validate_tx)."""
    lock = bytes.fromhex(utxo_entry["lock"])
    t = _one_input_tx(utxo_entry["txid"], utxo_entry["vout"],
                      dest_lock, utxo_entry["value"], fee)
    spent = _registry_set(registry)  # BEFORE signing (see claim)
    try:
        t["vin"][0]["script"] = sign_qhtlc_refund(
            t, 0, lock, trifold_key, descriptor, registry=registry)
    except AssertionError as e:
        raise TxBuildError(f"QHTLC refund signing failed: {e}")
    return _finish_single(t, utxo_entry, height, spent_pairs=spent)


def build_pqh_spend(utxo_entry, dest_lock, fee, trifold_key, height,
                    registry=None):
    """Spend a PQH UTXO with the wallet's Trifold key.

    WARNING (shown by the CLI before calling): sign_pqh_input records
    the (root, index) pair in the spent-leaf registry BEFORE signing,
    so if local validation fails after this call, that leaf is burned
    (never reusable). That is the safe direction — a crash cannot
    reuse a leaf — but the caller must know the leaf is spent the
    moment this runs."""
    from txpq import sign_pqh_input
    lock = bytes.fromhex(utxo_entry["lock"])
    t = _one_input_tx(utxo_entry["txid"], utxo_entry["vout"],
                      dest_lock, utxo_entry["value"], fee)
    h = sighash_all(t, 0, lock)
    spent = _registry_set(registry)  # BEFORE signing: sign_pqh_input
    try:                             # records this leaf first; the
        t["vin"][0]["script"] = sign_pqh_input(trifold_key, h,
                                               registry=registry)
    except AssertionError as e:
        raise TxBuildError(f"PQH signing failed: {e}")
    return _finish_single(t, utxo_entry, height, spent_pairs=spent)


def _registry_set(registry):
    """(root, index) set for validate_tx, or None (validate_tx then
    enforces only the intra-tx one-time rule)."""
    if registry is None:
        from spent_leaf_registry import load_registry
        try:
            return load_registry().as_set()
        except Exception:
            return None
    if hasattr(registry, "as_set"):
        return registry.as_set()
    return None


# ------------------------------------------------------- KNOT (test-chain)
def build_knot_lock_test(funding_utxos, funding_priv, amount,
                         p, q, n_terms, eps_u32, t_star, fee):
    """Test-chain-only KNOT funding tx (knot_wallet). Validated at
    height KNOT_ACTIVATION — the only height at which it is valid
    while activation is staged. NOT broadcastable on the live fork.
    Returns knot_wallet's result dict (includes t_star — the caller
    must store it in a 0600 file, never print it)."""
    from knot_wallet import build_knot_lock_tx
    return build_knot_lock_tx(funding_utxos, funding_priv, amount,
                              p, q, n_terms, eps_u32, t_star, fee)


def build_knot_spend_test(lock_prev, lock_idx, lock_value, lock,
                          descriptor, t_star, dest_lock, fee):
    """Test-chain-only KNOT spend tx (knot_wallet). Validated at
    height KNOT_ACTIVATION. NOT broadcastable on the live fork."""
    from knot_wallet import build_knot_spend_tx
    return build_knot_spend_tx(lock_prev, lock_idx, lock_value, lock,
                               descriptor, t_star, dest_lock, fee)
