"""lightledger.py — URUU-anchored trustless light ledger for Excalibur.

The problem: a new node today must replay the whole fork chain (44k+
blocks, 1.1 GB) before it can trust anything. The light ledger removes
that download without removing the trust.

How it works (three legs, all verifiable):

  1. SNAPSHOT. The QAI auditor (a full node) exports the fork's live
     UTXO overlay at height H — fork-created outputs plus tombstones of
     spent Bitcoin-snapshot outputs — and commits to it with two Merkle
     roots (overlay_root, spent_root). The snapshot is content-addressed:
     its SHA-256 is in the checkpoint, so a tampered download is caught
     by hashing alone.

  2. CHECKPOINT + ATTESTATION. The checkpoint {height, tip_hash,
     chainwork, overlay_root, spent_root, ...} is signed with the QAI
     auditor's Trifold key (hash-only Lamport-style signatures — no
     curve, nothing for a quantum adversary to break). The signature
     proves WHO published the checkpoint. It does not by itself prove
     the checkpoint is TRUE — that is leg 3.

  3. URUU ANCHOR. The checkpoint hash is anchored on zkSync Era in the
     URUU anchor contract, with a URUU bond posted by the auditor and a
     fraud window (default 24h). Anyone may challenge a checkpoint
     inside the window with a fraud proof (an omitted UTXO, a bad tip);
     a proven challenge voids the checkpoint and slashes the bond to the
     challenger. After the window passes unchallenged, the checkpoint is
     FINAL. A light node bootstraps ONLY from final checkpoints.

What "trustless" means here, precisely: no trust in the auditor's key.
What remains is (a) zkSync Era consensus + the anchor contract's code,
(b) at least one honest watcher inside the fraud window, and (c) the
fraud-proof verifier (this module + the contract). That is the standard
optimistic model — trust-minimized, not trust-free — and it is stated
here so nobody mistakes it for full replay validation.

URUU (verified live 2026-11-12, zkSync Era chain 324):
  token 0x5B6C9d85465Cc6FFe84039183872239657D90208 ("Camelot Excalibur
  URUU"), 18 decimals, total supply exactly 100,000,000.

The anchor contract itself (anchor_contract.sol) is NOT deployed yet:
deployment needs Lux's deployer key + ETH for gas. Until then the
checkpoint carries uruu.contract = null and the anchor leg is pending;
legs 1-2 (snapshot + Trifold attestation) already verify offline.
"""

import base64
import gzip
import hashlib
import json
import os
import secrets
import struct
import time

from genesis_fork import ser_header, sha256d
from trifold_lockbox import TrifoldKey, verify as trifold_verify
from txscript import parse_tx, txid_internal

# ------------------------------------------------------------------ URUU
URUU_CHAIN_ID = 324  # zkSync Era mainnet
URUU_TOKEN = "0x5B6C9d85465Cc6FFe84039183872239657D90208"
URUU_DECIMALS = 18
URUU_TOTAL_SUPPLY = 100_000_000
# Bond the auditor posts per checkpoint, in URUU (whole units; the
# contract holds 10**18 base units per URUU). Changeable by Lux.
BOND_URUU = 1_000
# Fraud window: a checkpoint is PENDING until this many seconds pass
# with no successful challenge; only FINAL checkpoints bootstrap nodes.
FRAUD_WINDOW_SECONDS = 86_400

CHECKPOINT_VERSION = 1
SNAPSHOT_FORMAT = "excal-overlay-snapshot-v1"


def sha256(b: bytes) -> bytes:
    return hashlib.sha256(b).digest()


# ----------------------------------------------------------------- Merkle
def _merkle_level(hashes):
    out = []
    for i in range(0, len(hashes), 2):
        left = hashes[i]
        right = hashes[i + 1] if i + 1 < len(hashes) else left
        out.append(sha256d(left + right))
    return out


def merkle_root(leaves):
    """Binary Merkle root over leaf hashes (odd last node duplicated).
    Empty set -> sha256d(b'EXCAL-LIGHT-EMPTY')."""
    if not leaves:
        return sha256d(b"EXCAL-LIGHT-EMPTY")
    level = list(leaves)
    while len(level) > 1:
        level = _merkle_level(level)
    return level[0]


def merkle_proof(leaves, index):
    """Inclusion proof: [(sibling_hash, sibling_is_left)] from leaf to root."""
    proof = []
    level = list(leaves)
    idx = index
    while len(level) > 1:
        sib = idx ^ 1
        if sib < len(level):
            proof.append((level[sib], sib < idx))
        else:  # odd last node duplicated: sibling is self
            proof.append((level[idx], False))
        level = _merkle_level(level)
        idx //= 2
    return proof


def verify_inclusion(root, leaf, proof, index, total):
    """Recompute the root from a leaf + inclusion proof."""
    if total <= 0 or index < 0 or index >= total:
        return False
    node = leaf
    idx = index
    for sib, is_left in proof:
        node = sha256d(sib + node) if is_left else sha256d(node + sib)
        idx //= 2
    return node == root


def prove_absence(sorted_keys, sorted_leaves, key):
    """Sorted-Merkle absence proof: the two leaves bracketing `key`.

    Returns {"left": (idx, leaf, proof) | None,
             "right": (idx, leaf, proof) | None}.
    A key smaller than every leaf has left=None; larger than every leaf
    has right=None. An empty set proves absence trivially."""
    import bisect
    pos = bisect.bisect_left(sorted_keys, key)
    out = {"left": None, "right": None}
    if pos > 0:
        i = pos - 1
        out["left"] = (i, sorted_leaves[i],
                       merkle_proof(sorted_leaves, i))
    if pos < len(sorted_keys):
        i = pos
        out["right"] = (i, sorted_leaves[i],
                        merkle_proof(sorted_leaves, i))
    return out


def verify_absence(root, total, key_b, proof):
    """Check a sorted-Merkle absence proof against a root. `key_b` is
    the 36-byte encoding of the UTXO key; `proof` is the JSON form
    produced by attach_absence: {"left": (idx, leaf_hex, [(sib_hex,
    is_left), ...]) | None, "right": ..., "left_key": hex | None,
    "right_key": hex | None}."""
    left, right = proof.get("left"), proof.get("right")
    if total == 0:
        return left is None and right is None
    if left is None and right is None:
        return False
    for side in (left, right):
        if side is None:
            continue
        idx, leaf_hex, pf = side
        pf = [(bytes.fromhex(x), l) for x, l in pf]
        if not verify_inclusion(root, bytes.fromhex(leaf_hex), pf,
                                idx, total):
            return False
    lk = bytes.fromhex(proof["left_key"]) \
        if proof.get("left_key") else None
    rk = bytes.fromhex(proof["right_key"]) \
        if proof.get("right_key") else None
    if left is not None and not (lk < key_b):
        return False
    if right is not None and not (key_b < rk):
        return False
    # Adjacency: the two bracketing leaves must be NEIGHBOURS in the
    # sorted set, or the prover could straddle the key with two far
    # apart leaves and hide a present UTXO between them.
    if left is not None and right is not None:
        if right[0] != left[0] + 1:
            return False
    elif left is None:
        if right[0] != 0:
            return False
    else:  # right is None
        if left[0] != total - 1:
            return False
    return True


# ------------------------------------------------------------ leaf codecs
def leaf_overlay(key, entry):
    """key=(txid_bytes, vout); entry=(value, spk, is_cb, cb_h)."""
    txid_b, vout = key
    value, spk, is_cb, cb_h = entry
    return sha256d(b"EXCAL-UTXO-v1" + txid_b
                   + struct.pack("<IQ", vout, value)
                   + struct.pack("<I", len(spk)) + spk
                   + bytes([1 if is_cb else 0])
                   + struct.pack("<I", cb_h))


def leaf_spent(key):
    txid_b, vout = key
    return sha256d(b"EXCAL-SPENT-v1" + txid_b
                   + struct.pack("<I", vout))


def key_bytes(key):
    """Canonical 36-byte encoding of a UTXO key for ordering."""
    txid_b, vout = key
    return txid_b + struct.pack("<I", vout)


def overlay_entries_sorted(overlay):
    """[(key, entry)] sorted by (txid, vout) — the canonical order."""
    return sorted(overlay.items(), key=lambda kv: (kv[0][0], kv[0][1]))


def overlay_root(overlay):
    items = overlay_entries_sorted(overlay)
    return merkle_root([leaf_overlay(k, entries[0])
                        for k, entries in items])


def spent_root(spent):
    keys = sorted(spent, key=lambda k: (k[0], k[1]))
    return merkle_root([leaf_spent(k) for k in keys])


# ------------------------------------------------------------- snapshots
def export_overlay(overlay, spent, height, tip_hash, chainwork, out_path):
    """Write the fork overlay snapshot (gzip JSONL) + return its manifest.

    overlay: {(txid_bytes, vout): [(value, spk, is_cb, cb_h)]}
    spent:   {(txid_bytes, vout)} tombstones of spent snapshot outputs.
    Only the FIRST entry per key is exported (fork outputs are unique)."""
    items = overlay_entries_sorted(overlay)
    oroot = overlay_root(overlay)
    sroot = spent_root(spent)
    total = 0
    with gzip.open(out_path, "wt", encoding="utf-8") as f:
        for key, entries in items:
            e = entries[0]
            total += e[0]
            f.write(json.dumps({
                "txid": key[0].hex(), "vout": key[1], "value": e[0],
                "spk": e[1].hex(), "is_cb": 1 if e[2] else 0,
                "cb_h": e[3]}) + "\n")
        for key in sorted(spent, key=lambda k: (k[0], k[1])):
            f.write(json.dumps({"spent": True, "txid": key[0].hex(),
                                "vout": key[1]}) + "\n")
    digest = sha256(open(out_path, "rb").read()).hex()
    return {
        "format": SNAPSHOT_FORMAT, "network": "fork",
        "height": height, "tip_hash": tip_hash,
        "chainwork": chainwork,
        "overlay_root": oroot.hex(), "overlay_count": len(items),
        "overlay_total_swords": total,
        "spent_root": sroot.hex(), "spent_count": len(spent),
        "file": os.path.basename(out_path), "sha256": digest,
    }


def import_overlay(path, manifest):
    """Load a snapshot, verifying its SHA-256 and both Merkle roots.
    Returns (overlay, spent). Raises ValueError on any mismatch."""
    digest = sha256(open(path, "rb").read()).hex()
    if digest != manifest["sha256"]:
        raise ValueError(f"snapshot sha256 mismatch: file {digest} "
                         f"!= manifest {manifest['sha256']}")
    overlay, spent = {}, set()
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            if d.get("spent"):
                spent.add((bytes.fromhex(d["txid"]), d["vout"]))
            else:
                key = (bytes.fromhex(d["txid"]), d["vout"])
                overlay[key] = [(d["value"], bytes.fromhex(d["spk"]),
                                 bool(d["is_cb"]), d["cb_h"])]
    if overlay_root(overlay).hex() != manifest["overlay_root"]:
        raise ValueError("overlay Merkle root mismatch — snapshot tampered")
    if spent_root(spent).hex() != manifest["spent_root"]:
        raise ValueError("spent Merkle root mismatch — snapshot tampered")
    if len(overlay) != manifest["overlay_count"]:
        raise ValueError("overlay count mismatch")
    if len(spent) != manifest["spent_count"]:
        raise ValueError("spent count mismatch")
    return overlay, spent


# ------------------------------------------------------------- checkpoints
def canonical_checkpoint_bytes(fields):
    """Canonical bytes a checkpoint is signed over: sorted-key JSON of
    every field EXCEPT signature / anchor-tx (those are added after)."""
    core = {k: v for k, v in fields.items()
            if k not in ("signature", "auditor_root", "leaf_index",
                         "anchor_tx", "anchor_status")}
    return json.dumps(core, sort_keys=True,
                      separators=(",", ":")).encode()


def _sig_to_json(sig):
    return {
        "index": sig["index"],
        "ots_sig": [s.hex() for s in sig["ots_sig"]],
        "ots_pub": [[a.hex(), b.hex()] for a, b in sig["ots_pub"]],
        "path": [[s.hex() for s in lvl] for lvl in sig["path"]],
    }


def _sig_from_json(d):
    return {
        "index": d["index"],
        "ots_sig": [bytes.fromhex(s) for s in d["ots_sig"]],
        "ots_pub": [(bytes.fromhex(a), bytes.fromhex(b))
                    for a, b in d["ots_pub"]],
        "path": [[bytes.fromhex(s) for s in lvl] for lvl in d["path"]],
    }


def attest_checkpoint(key, fields):
    """Trifold-sign a checkpoint's canonical bytes. `key` is a
    TrifoldKey (leaf state persisted — a leaf is never reused).
    Returns the full checkpoint dict, JSON-serializable."""
    msg = canonical_checkpoint_bytes(fields)
    sig = key.sign(msg)
    cp = dict(fields)
    cp["auditor_root"] = key.root.hex()
    cp["leaf_index"] = sig["index"]
    cp["signature"] = _sig_to_json(sig)
    return cp


def verify_checkpoint(cp):
    """Verify the Trifold attestation on a checkpoint. Returns True/False.
    (Authentication only — truth comes from the URUU anchor + fraud
    window; see checkpoint_status.)"""
    try:
        root = bytes.fromhex(cp["auditor_root"])
        sig = _sig_from_json(cp["signature"])
        msg = canonical_checkpoint_bytes(cp)
        return trifold_verify(root, msg, sig)
    except (KeyError, ValueError, TypeError):
        return False


def anchor_hash(cp):
    """The checkpoint hash anchored in URUU: sha256d of canonical bytes."""
    return sha256d(canonical_checkpoint_bytes(cp)).hex()


def checkpoint_status(cp, now=None, challenged=False):
    """'pending' (inside the fraud window), 'final' (window passed,
    unchallenged), or 'void' (successfully challenged). Light nodes
    bootstrap ONLY from 'final' checkpoints."""
    if challenged:
        return "void"
    end = cp.get("fraud_window_end_unix")
    if end is None:
        return "pending"
    now = int(time.time()) if now is None else now
    return "final" if now >= end else "pending"


def make_checkpoint_fields(manifest, prev_checkpoint_hash=None,
                           fraud_window_seconds=FRAUD_WINDOW_SECONDS,
                           bond_uruu=BOND_URUU, now=None):
    """Checkpoint fields from a snapshot manifest (before attestation)."""
    now = int(time.time()) if now is None else now
    return {
        "version": CHECKPOINT_VERSION, "network": "fork",
        "height": manifest["height"], "tip_hash": manifest["tip_hash"],
        "chainwork": manifest["chainwork"],
        "overlay_root": manifest["overlay_root"],
        "overlay_count": manifest["overlay_count"],
        "overlay_total_swords": manifest["overlay_total_swords"],
        "spent_root": manifest["spent_root"],
        "spent_count": manifest["spent_count"],
        "snapshot_file": manifest["file"],
        "snapshot_sha256": manifest["sha256"],
        "snapshot_base_hash": None,  # Bitcoin snapshot base (phase 2)
        "prev_checkpoint": prev_checkpoint_hash,
        "issued_unix": now,
        "fraud_window_end_unix": now + fraud_window_seconds,
        "uruu": {
            "chain_id": URUU_CHAIN_ID, "token": URUU_TOKEN,
            "contract": None,  # set at deployment
            "anchor_tx": None,
            "bond_uruu": bond_uruu,
        },
    }


# ------------------------------------------------------------ auditor key
def make_auditor_key(path, state_path=None, height=6):
    """Generate the QAI auditor's Trifold key. The seed is written 0600
    and NEVER printed; the root is the auditor's public identity.
    Returns (key, root_hex)."""
    seed = secrets.token_bytes(32)
    key = TrifoldKey(seed, height=height, state_path=state_path)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w") as f:
        json.dump({"seed": seed.hex(), "root": key.root.hex(),
                   "height": height, "created_unix": int(time.time())}, f)
    os.chmod(path, 0o600)
    return key, key.root.hex()


def load_auditor_key(path, state_path=None):
    """Load the auditor key (seed never leaves this function)."""
    with open(path) as f:
        d = json.load(f)
    return TrifoldKey(bytes.fromhex(d["seed"]), height=d.get("height", 6),
                      state_path=state_path)


# ------------------------------------------------------------ fraud proofs
def tx_merkle_root(txids):
    """Bitcoin-style Merkle root over txids (internal byte order)."""
    if not txids:
        return sha256d(b"")
    level = list(txids)
    while len(level) > 1:
        level = _merkle_level(level)
    return level[0]


def header_hash(rec):
    """Header hash of a chain record (same as consensus)."""
    return sha256d(ser_header(rec["version"], bytes(rec["prev"]),
                              bytes(rec["merkle"]), rec["time"],
                              rec["bits"], rec["nonce"]))


def build_omission_proof(records_by_hash, checkpoint, utxo_key):
    """Fraud proof: a confirmed block creates UTXO `utxo_key`, but the
    checkpoint's overlay_root omits it.

    records_by_hash: {header_hash_bytes: record} for the audited chain.
    Returns None when the UTXO is NOT created by any confirmed block
    (no fraud to prove) — the caller must have the creating block.
    Proof: {type, height, block_hash, tx_index, tx_hex, tx_proof,
    output, absence_proof, absence_left_key, absence_right_key}."""
    manifest = checkpoint
    items = None  # the attested overlay is NOT needed to build the proof
    for h, rec in records_by_hash.items():
        for ti, raw in enumerate(rec["txs"]):
            t = parse_tx(raw)
            tid = txid_internal(raw)
            for j, vout in enumerate(t["vout"]):
                if (tid, j) == utxo_key:
                    txids = [txid_internal(r) for r in rec["txs"]]
                    if tx_merkle_root(txids) != bytes(rec["merkle"]):
                        raise ValueError("block merkle mismatch — "
                                         "records are not a valid chain")
                    return {
                        "type": "overlay_omission",
                        "height": rec["height"],
                        "block_hash": h.hex(),
                        "tx_index": ti,
                        "tx_hex": raw.hex(),
                        "utxo_txid": tid.hex(),
                        "utxo_vout": j,
                        "tx_proof": [(s.hex(), l) for s, l in
                                     merkle_proof(txids, ti)],
                        "output": {"value": vout["value"],
                                   "spk": vout["script"].hex()},
                    }
    return None


def verify_omission_proof(checkpoint, proof, records_by_hash):
    """Verify an omission fraud proof. Returns (True, reason) or
    (False, reason). Checks, in order: the block is in the audited
    chain at the claimed height and at/below the checkpoint height;
    the tx is in the block (Merkle proof vs the block's merkle root);
    the tx output is exactly the claimed UTXO; the UTXO is ABSENT
    from the checkpoint's overlay root (sorted-Merkle absence proof)."""
    if proof.get("type") != "overlay_omission":
        return False, "wrong proof type"
    if proof["height"] > checkpoint["height"]:
        return False, "block is above the checkpoint height"
    rec = records_by_hash.get(bytes.fromhex(proof["block_hash"]))
    if rec is None or rec["height"] != proof["height"]:
        return False, "block not in the audited chain"
    raw = bytes.fromhex(proof["tx_hex"])
    tid = txid_internal(raw)
    txids = [txid_internal(r) for r in rec["txs"]]
    if proof["tx_index"] >= len(txids) or txids[proof["tx_index"]] != tid:
        return False, "tx not at the claimed index"
    if tx_merkle_root(txids) != bytes(rec["merkle"]):
        return False, "block merkle mismatch"
    t = parse_tx(raw)
    key = None
    for j, vout in enumerate(t["vout"]):
        if (tid, j) == (bytes.fromhex(proof.get("utxo_txid", "")),
                        proof.get("utxo_vout", -1)):
            key = (tid, j)
            if (vout["value"] != proof["output"]["value"]
                    or vout["script"].hex() != proof["output"]["spk"]):
                return False, "output does not match the proof"
    if key is None:
        return False, "tx does not create the claimed UTXO"
    # Absence: the proof carries the bracketing leaves + keys (JSON form).
    root = bytes.fromhex(checkpoint["overlay_root"])
    total = checkpoint["overlay_count"]
    if not verify_absence(root, total, key_bytes(key),
                          proof["absence"]):
        return False, "absence proof fails — UTXO is in the set"
    return True, "fraud proven: confirmed UTXO omitted from checkpoint"


def attach_absence(checkpoint, proof, overlay):
    """Fill a built omission proof's absence leg from the attested
    overlay (what the auditor claims). Used by challengers and tests."""
    items = overlay_entries_sorted(overlay)
    keys_b = [key_bytes(k) for k, _ in items]
    leaves = [leaf_overlay(k, entries[0]) for k, entries in items]
    key = (bytes.fromhex(proof["utxo_txid"]), proof["utxo_vout"])
    ap = prove_absence(keys_b, leaves, key_bytes(key))
    out = {}
    for side in ("left", "right"):
        v = ap[side]
        out[side] = None if v is None else (
            v[0], v[1].hex(), [(x.hex(), l) for x, l in v[2]])
    out["left_key"] = keys_b[ap["left"][0]].hex() \
        if ap["left"] is not None else None
    out["right_key"] = keys_b[ap["right"][0]].hex() \
        if ap["right"] is not None else None
    proof["absence"] = out
    return proof
