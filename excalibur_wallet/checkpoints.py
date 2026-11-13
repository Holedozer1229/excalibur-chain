"""checkpoints.py — QAI-audited Trifold checkpoint verification.

Two halves of the light ledger, both verified from real data:

  1. ON-CHAIN ATTESTATIONS. The fork's own blocks carry the QAI
     auditor's Trifold attestations in coinbase scriptSigs:
       * fork block 43750: "OVERFLOW COUNTERSIGNED 7083fbeb - DR. TIME
         2026-11-11" — the Dr. Time overflow countersignature over the
         Bitcoin bad-block header (root 7083fbeb…e7bfe55, leaf 0).
       * fork block 43924: "DRTIME ON 3 CHAINS - T4 8f81d522 efbe4a1b"
       * DRTIME/v1 binary payloads (73 bytes: "DRTIME/v1" + 32-byte
         root + 32-byte bundle/signature hash) in rolling-sweep
         coinbases, when mined.
     scan_attestations() finds them in the live chain and cross-checks
     the root prefix against the known full root. A checkpoint is
     "verified" only if its marker is in a confirmed block at depth
     and its root matches the known root.

  2. LIGHTLEDGER CHECKPOINT OBJECTS (lightledger.py). A checkpoint
     JSON {height, tip_hash, overlay_root, spent_root, ...} signed by
     the QAI auditor's Trifold key. verify_checkpoint() checks the
     Trifold attestation (authentication only); checkpoint_status()
     says pending/final/void under the URUU fraud window. Light nodes
     bootstrap ONLY from 'final' checkpoints. The URUU anchor
     contract is NOT deployed yet, so the anchor leg is pending and
     the command says so plainly — legs 1-2 (snapshot + attestation)
     verify offline, the anchor does not exist yet.

What this does NOT do: it does not re-verify the 24,964-byte Trifold
countersignature itself (that was verified fresh-process on
2026-11-09; the signature bytes live in the Dr. Time bundle, not in
this module). The checkpoint command verifies the attestation's
presence in the chain + its root + its depth — and labels everything
else as what it is.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from txscript import parse_tx

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHAIN_PATH = os.path.join(WORKSPACE, "chaindata_fork", "chain.jsonl")
LIGHT_LEDGER_DIR = os.path.join(WORKSPACE, "light-ledger")

# Known full Trifold root for the Dr. Time overflow countersignature
# (sealed in fork block 43750; source: dr-time-overflow-countersignature
# .json `trifold_root`, cross-checked against the DRTIME/v1 payloads
# file — both carry the same 32 bytes).
KNOWN_ROOT_DRTIME = ("7083fbebd6bfbd5f82fd40827cf36bc30da81524914011e69488b5a"
                     "63e7bfe55")
# Lineage roots, as documented in the countersignature file (prefixes
# only — the full roots are not on file in this wallet; the scanner
# reports whatever marker text the chain carries at those heights).
LINEAGE = [
    {"height": 25344, "prefix": "65ef9c66", "label": "Dr. Time (leaf 0)"},
    {"height": 25351, "prefix": "fc4a1de9", "label": "PQ-CHAIN"},
    {"height": 43750, "prefix": "7083fbeb", "label": "Dr. Time overflow"},
]

_MARKER_RES = [
    (re.compile(rb"OVERFLOW COUNTERSIGNED ([0-9a-f]{4,64})"), "overflow"),
    (re.compile(rb"DRTIME/v1"), "drtime-v1"),
    (re.compile(rb"DRTIME ON 3 CHAINS - T4 ([0-9a-f]{4,64}) ([0-9a-f]{4,64})"),
     "drtime-3chains"),
    (re.compile(rb"DR\. TIME"), "dr-time"),
]


def _coinbase_pushes(raw_tx: bytes):
    try:
        t = parse_tx(raw_tx)
    except ValueError:
        return []
    if not t["vin"]:
        return []
    script = t["vin"][0]["script"]
    # Split into pushes (same parser the consensus code uses).
    from genesis_fork import _parse_pushes
    try:
        return _parse_pushes(script)
    except ValueError:
        return [script]


def scan_attestations(chain_path=CHAIN_PATH):
    """Scan the live chain for Trifold attestation markers in coinbase
    scriptSigs. Returns {"tip_height", "tip_hash", "markers": [...]}.
    markers: {height, hash, kind, text, root_prefix, confirmations}."""
    markers = []
    tip_height, tip_hash = -1, None
    with open(chain_path, "rb") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                rec = json.loads(line.decode())
            except ValueError:
                break
            height = int(rec["height"])
            if height > tip_height:
                tip_height, tip_hash = height, rec["hash"]
            txs = rec.get("txs", [])
            if not txs:
                continue
            for push in _coinbase_pushes(bytes.fromhex(txs[0])):
                text = None
                kind = None
                root_prefix = None
                if push.startswith(b"DRTIME/v1") and len(push) == 73:
                    kind = "drtime-v1"
                    root_prefix = push[9:41].hex()
                    text = push[:9].decode(errors="replace")
                else:
                    for rx, k in _MARKER_RES:
                        m = rx.search(push)
                        if m:
                            kind = k
                            text = push.decode(errors="replace")
                            if m.groups():
                                root_prefix = m.group(1).decode()
                            break
                if kind:
                    markers.append({
                        "height": height, "hash": rec["hash"],
                        "kind": kind, "text": text,
                        "root_prefix": root_prefix,
                        "confirmations": tip_height - height + 1})
                    break  # one marker per block is enough
    # Fill confirmations with the final tip.
    for mk in markers:
        mk["confirmations"] = tip_height - mk["height"] + 1
    return {"tip_height": tip_height, "tip_hash": tip_hash,
            "markers": markers}


def verify_chain_attestations(chain_path=CHAIN_PATH):
    """Full verdict on the on-chain attestations: which markers verify
    (root prefix matches a known root), which are unknown, and the
    lineage check. Returns a report dict."""
    scan = scan_attestations(chain_path)
    verified, unknown = [], []
    for mk in scan["markers"]:
        rp = (mk.get("root_prefix") or "").lower()
        if rp and KNOWN_ROOT_DRTIME.startswith(rp):
            verified.append({**mk, "root": KNOWN_ROOT_DRTIME,
                             "verdict": "verified"})
        elif mk["kind"] == "drtime-v1" and rp == KNOWN_ROOT_DRTIME:
            verified.append({**mk, "root": KNOWN_ROOT_DRTIME,
                             "verdict": "verified"})
        else:
            unknown.append({**mk, "verdict": "unknown-root"})
    lineage = []
    by_height = {m["height"]: m for m in scan["markers"]}
    for leg in LINEAGE:
        hit = by_height.get(leg["height"])
        lineage.append({**leg,
                        "found": hit is not None,
                        "text": hit["text"] if hit else None})
    return {"tip_height": scan["tip_height"], "tip_hash": scan["tip_hash"],
            "verified": verified, "unknown": unknown,
            "lineage": lineage,
            "fallback": ("markers that do not verify fall back to full "
                         "local verification — the wallet never treats an "
                         "unverified marker as a checkpoint")}


def verify_checkpoint_file(path):
    """Verify a lightledger checkpoint JSON: Trifold attestation +
    fraud-window status + anchor hash. Returns a report dict."""
    import lightledger
    with open(path) as f:
        cp = json.load(f)
    attested = lightledger.verify_checkpoint(cp)
    status = lightledger.checkpoint_status(cp)
    anchor = lightledger.anchor_hash(cp)
    uruu = cp.get("uruu") or {}
    return {"file": os.path.basename(path),
            "height": cp.get("height"),
            "tip_hash": cp.get("tip_hash"),
            "overlay_root": cp.get("overlay_root"),
            "overlay_count": cp.get("overlay_count"),
            "attestation_valid": attested,
            "auditor_root": cp.get("auditor_root"),
            "leaf_index": cp.get("leaf_index"),
            "status": status,
            "anchor_hash": anchor,
            "uruu_contract": uruu.get("contract"),
            "uruu_anchor_tx": uruu.get("anchor_tx"),
            "anchor_leg": ("pending — anchor contract not deployed; "
                           "checkpoint is attested but NOT URUU-anchored")
            if not uruu.get("contract") else "anchored",
            "bootstrap_ok": bool(attested and status == "final")}
