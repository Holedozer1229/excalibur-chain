#!/usr/bin/env python3
"""deliver_seed.py — swap watcher: publish the claim seed, encrypted to the taker.

Runs on Lux's side (this VM). It NEVER signs, spends, or broadcasts
anything. Its only job: when a taker funds a Bitcoin HTLC for one of the
EXCAL lots, verify the funding and publish that lot's claim seed
ENCRYPTED to the taker's delivery pubkey — so only that taker can
decrypt it. No message to or from the taker is needed.

Why encryption matters: the EXCAL claim needs the claim seed + the
secret. The secret appears on-chain when Lux claims the BTC. If the
seed were published raw, anyone could race the taker for the EXCAL
after the secret appears. Encrypted to the taker's key, only the
taker can claim. The watcher therefore verifies the funding BEFORE
delivering, and delivers ONLY to the FIRST verified funding per lot
(one lot, one taker — a second funding is never claimed by Lux; its
BTC refunds to its taker after the timeout).

Verification needs the taker's witness script, which the taker posts as
a comment on the lot's GitHub issue (public, verifiable — not a message
to Lux). The funding transaction itself is found via the 1,000-sat
signal payment to Lux's miner address. The OP_RETURN tag identifies
the lot (EXCAL1K or EXCAL1); the tags are matched exactly, with a
length check, because EXCAL1 is a prefix of EXCAL1K.

Usage (run with the cirq venv python — it has `cryptography`):
  ~/workspace/venvs/cirq-env/bin/python deliver_seed.py --check
  ~/workspace/venvs/cirq-env/bin/python deliver_seed.py --watch
  ~/workspace/venvs/cirq-env/bin/python deliver_seed.py --funding-txid TXID --witness-script HEX [--lot 1k]

--check / --watch: one pass over the signal address + issue comments;
  delivers for the first verified funding per lot (if any) and exits.
  (--watch is the same pass, meant for cron, every 5 minutes.)
--funding-txid + --witness-script: one-shot delivery for one funding.

Outputs (public): self-serve/claim-seeds/<lot>-<funding_txid>.json
  {lot, funding_txid, delivery_pubkey, ephemeral_pubkey, nonce, ciphertext}
The claim seed itself is NEVER printed or written anywhere in the clear.
State: self-serve/watch_state.json (per lot: seen txids, delivered txid).
"""
import argparse, hashlib, json, os, re, subprocess, sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.expanduser("~/workspace"))
sys.path.insert(0, os.path.join(HERE, "vendor"))
OFFER_ROOT = os.path.expanduser("~/workspace")
OUT_DIR = os.path.join(HERE, "claim-seeds")
STATE_FILE = os.path.join(HERE, "watch_state.json")
MAKER_PUB_HEX = "02e8311342cb7accd4edef31462fcda1ef56bfbf7d4f03d3c8872dbec9a1bba1b3"
SIGNAL_ADDR = "bc1qj37xg5qmyedwfe70cz0f385cxmf6642kcznjdg"
REPO = "Holedozer1229/excalibur-chain"
# Production safeguard: require 6 BTC confirmations before delivering the
# claim seed (reduces reorg exposure; does not eliminate it).
MIN_BTC_CONFIRMATIONS = 6

def load_lot(name):
    with open(os.path.join(HERE, "lots", name + ".json")) as f:
        return json.load(f)

def all_lots():
    names = []
    lots_dir = os.path.join(HERE, "lots")
    if os.path.isdir(lots_dir):
        names = sorted(fn[:-5] for fn in os.listdir(lots_dir) if fn.endswith(".json"))
    return [load_lot(n) for n in names]

def curl(url, method="GET", data=None):
    cmd = ["curl", "-s", "-m", "30"]
    if method == "POST":
        cmd += ["-X", "POST", "--data-binary", data,
                "-H", "Content-Type: text/plain"]
    cmd.append(url)
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"curl {url} failed rc={r.returncode}: {r.stderr[:200]}")
    return r.stdout

def read_claim_seed_hex(lot):
    """Read ONLY the claim seed line of the lot's seed file. Never print it."""
    seed_file = os.path.join(OFFER_ROOT, lot["offer_dir"], "trifold_seeds.key")
    with open(seed_file) as f:
        for line in f:
            if line.startswith("claim_seed_hex:"):
                return line.split(":", 1)[1].strip()
    raise RuntimeError(f"claim_seed_hex line not found in {seed_file}")

def load_state():
    try:
        with open(STATE_FILE) as f:
            s = json.load(f)
    except Exception:
        return {"lots": {}}
    # Migrate the old single-lot format, if present.
    if "delivered_txid" in s or "seen" in s:
        s = {"lots": {"1k": {"seen": s.get("seen", []),
                             "delivered_txid": s.get("delivered_txid")}}}
    s.setdefault("lots", {})
    return s

def save_state(s):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(s, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, STATE_FILE)

def lot_state(state, lot_name):
    return state["lots"].setdefault(lot_name, {"seen": [], "delivered_txid": None})

def bc_tx_to_mempool_shape(bc_tx):
    """Translate one BlockCypher tx into the mempool.space shape the
    verifier expects, preserving confirmation metadata so both
    providers expose the same status fields."""
    confirmations = int(bc_tx.get("confirmations") or 0)
    block_height = bc_tx.get("block_height")
    return {
        "txid": bc_tx.get("hash"),
        "vout": [
            {
                "scriptpubkey": o.get("script", ""),
                "value": o.get("value", 0)
            }
            for o in bc_tx.get("outputs", [])
        ],
        "status": {
            "confirmed": confirmations > 0 and block_height is not None,
            "block_height": block_height,
            "block_hash": bc_tx.get("block_hash"),
            "confirmations": confirmations
        }
    }

def verify_confirmed_tx(tx, requested_txid, tip_height,
                        min_confirmations=MIN_BTC_CONFIRMATIONS):
    actual = str(tx.get("txid") or "").lower()
    requested = str(requested_txid).lower()
    if not re.fullmatch(r"[0-9a-f]{64}", requested):
        raise ValueError("requested funding txid is malformed")
    if actual != requested:
        raise ValueError("transaction provider returned a different txid")
    status = tx.get("status") or {}
    if status.get("confirmed") is not True:
        raise ValueError("funding transaction is not confirmed")
    block_height = status.get("block_height")
    if not isinstance(block_height, int) or block_height <= 0:
        raise ValueError("confirmed transaction has no valid block height")
    if not isinstance(tip_height, int) or tip_height < block_height:
        raise ValueError("invalid Bitcoin tip height")
    confirmations = tip_height - block_height + 1
    if confirmations < min_confirmations:
        raise ValueError(
            f"funding has {confirmations} confirmations; "
            f"{min_confirmations} required"
        )
    return confirmations

def fetch_btc_tip_height():
    raw = curl("https://mempool.space/api/blocks/tip/height").strip()
    if not raw.isdigit():
        raise RuntimeError("Bitcoin tip-height response is invalid")
    return int(raw)

def fetch_canonical_block_hash(height):
    """Fetch the active-chain block hash at height; fail closed if unavailable."""
    block_hash = curl(
        f"https://mempool.space/api/block-height/{int(height)}"
    ).strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", block_hash):
        raise RuntimeError(
            f"canonical block-hash response for height {height} is invalid"
        )
    return block_hash

def verify_canonical_block(tx, canonical_block_hash):
    """Reject a confirmation tied to a block no longer on the active chain."""
    status = tx.get("status") or {}
    observed = str(status.get("block_hash") or "").lower()
    expected = str(canonical_block_hash or "").lower()
    if not re.fullmatch(r"[0-9a-f]{64}", observed):
        raise ValueError("transaction provider omitted confirmed block hash")
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise ValueError("canonical block hash is unavailable or malformed")
    if observed != expected:
        raise ValueError("funding transaction block is not on the active chain")
    return True

def signal_txs_blockcypher():
    """Fallback signal-address poll via BlockCypher (unauthenticated).
    One addr request per check plus one tx fetch per tx seen; the signal
    address normally has ~0 txs, so volume stays far under the free limit.
    txrefs are most-recent-first, so new fundings are always on page 1."""
    addr = json.loads(curl(
        f"https://api.blockcypher.com/v1/btc/main/addrs/{SIGNAL_ADDR}?limit=50"))
    hashes = []
    for refs in (addr.get("txrefs") or [], addr.get("unconfirmed_txrefs") or []):
        for r in refs:
            h = r.get("tx_hash")
            if h and h not in hashes:
                hashes.append(h)
    txs = []
    for h in hashes:
        bc = json.loads(curl(f"https://api.blockcypher.com/v1/btc/main/txs/{h}"))
        txs.append(bc_tx_to_mempool_shape(bc))
    return txs

def fetch_tx(txid):
    """Fetch one BTC tx in mempool.space shape; mempool.space first,
    BlockCypher fallback."""
    try:
        return json.loads(curl(f"https://mempool.space/api/tx/{txid}"))
    except Exception as e:
        print(f"warning: mempool.space tx fetch failed ({str(e)[:120]}); trying BlockCypher")
        bc = json.loads(curl(f"https://api.blockcypher.com/v1/btc/main/txs/{txid}"))
        return bc_tx_to_mempool_shape(bc)

def signal_txs():
    try:
        return json.loads(curl(f"https://mempool.space/api/address/{SIGNAL_ADDR}/txs"))
    except Exception as e:
        print(f"warning: mempool.space unreachable ({str(e)[:120]}); falling back to BlockCypher")
        return signal_txs_blockcypher()

def find_delivery_key(tx, lots, witness_script=None):
    """
    Find (lot, delivery_pubkey, htlc_vout, htlc_value, script_pubkey).
    If witness_script is supplied, only an output whose P2WSH
    commitment matches that exact script can be selected.
    """
    expected_spk = None
    if witness_script is not None:
        expected_spk = b"\x00\x20" + hashlib.sha256(
            witness_script
        ).digest()
    htlc_outputs = []
    for i, o in enumerate(tx.get("vout", [])):
        try:
            spk = bytes.fromhex(o["scriptpubkey"])
        except (ValueError, KeyError, TypeError):
            continue
        if len(spk) == 34 and spk[:2] == b"\x00\x20":
            if expected_spk is None or spk == expected_spk:
                htlc_outputs.append((i, o["value"], spk))
    if not htlc_outputs:
        return None
    # Do not silently choose between multiple matching HTLC outputs.
    # Ambiguity is rejected only when a specific witness script is
    # supplied; during discovery (no script) keep the old behavior of
    # selecting the last P2WSH candidate.
    if expected_spk is not None and len(htlc_outputs) != 1:
        raise ValueError("funding transaction has ambiguous matching P2WSH outputs")
    htlc_vout, htlc_value, htlc_spk = htlc_outputs[-1]
    for o in tx.get("vout", []):
        try:
            spk = bytes.fromhex(o["scriptpubkey"])
        except (ValueError, KeyError, TypeError):
            continue
        if spk[:1] != b"\x6a" or len(spk) < 2:
            continue
        # spk = OP_RETURN <push> <payload>; payload = <tag> + 33-byte pubkey.
        data = spk[1:]
        if not data or data[0] != len(data) - 1:
            continue
        payload = data[1:]
        for lot in lots:
            tag = lot["tag"].encode()
            if len(payload) == len(tag) + 33 and payload[:len(tag)] == tag:
                return (
                    lot, payload[len(tag):], htlc_vout,
                    htlc_value, htlc_spk
                )
    return None

def issue_witness_scripts(issue_no):
    """Map funding_txid -> witness_script hex from an issue's comments."""
    out = {}
    if not issue_no:
        return out
    try:
        raw = curl(f"https://api.github.com/repos/{REPO}/issues/{issue_no}/comments?per_page=100")
        comments = json.loads(raw)
    except Exception as e:
        print("warning: could not fetch issue comments:", str(e)[:150])
        return out
    for c in comments:
        body = c.get("body", "")
        txm = re.search(r"([0-9a-f]{64})", body)
        for m in re.finditer(r"witness[_ ]script[:\s]*([0-9a-f]{100,300})", body, re.I):
            if txm:
                out.setdefault(txm.group(1).lower(), m.group(1).lower())
    return out

def verify_htlc(script_hex, htlc_value, lot):
    from btc_htlc import parse_witness_script
    script = bytes.fromhex(script_hex)
    p = parse_witness_script(script)
    assert p["maker_pubkey"].hex() == MAKER_PUB_HEX, "maker pubkey is not Lux's miner key"
    assert p["secret_hash"].hex() == lot["secret_hash"], "secret hash mismatch for this lot"
    assert p["timeout"] > 0, "bad timeout"
    assert htlc_value > 0, "HTLC value must be positive"
    ask = lot.get("ask_sats")
    assert ask is None or htlc_value == ask, \
        f"HTLC value {htlc_value} sats does not match the {lot['label']} lot's ask of {ask} sats"
    return p

def encrypt_seed(seed_hex, delivery_pub_hex):
    from cryptography.hazmat.primitives.asymmetric.ec import SECP256K1, EllipticCurvePublicKey
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    eph_priv = ec.generate_private_key(SECP256K1())
    eph_pub = eph_priv.public_key().public_bytes(Encoding.X962, PublicFormat.CompressedPoint)
    delivery_pub = EllipticCurvePublicKey.from_encoded_point(
        SECP256K1(), bytes.fromhex(delivery_pub_hex))
    shared = eph_priv.exchange(ec.ECDH(), delivery_pub)
    key = hashlib.sha256(shared).digest()
    nonce = os.urandom(12)
    ct = AESGCM(key).encrypt(nonce, bytes.fromhex(seed_hex), None)
    return {"ephemeral_pubkey": eph_pub.hex(), "nonce": nonce.hex(), "ciphertext": ct.hex()}

def deliver(funding_txid, witness_script_hex, lot):
    state = load_state()
    ls = lot_state(state, lot["lot"])
    if ls.get("delivered_txid"):
        print(
            f"[{lot['lot']}] already delivered for "
            f"{ls['delivered_txid']}; refusing a second delivery"
        )
        return False
    try:
        witness_script = bytes.fromhex(witness_script_hex)
    except (TypeError, ValueError):
        raise ValueError("witness script is not valid hexadecimal")
    tx = fetch_tx(funding_txid)
    tip_height = fetch_btc_tip_height()
    confirmations = verify_confirmed_tx(
        tx, funding_txid, tip_height
    )
    block_height = tx["status"]["block_height"]
    canonical_hash = fetch_canonical_block_hash(block_height)
    verify_canonical_block(tx, canonical_hash)
    found = find_delivery_key(
        tx, [lot], witness_script=witness_script
    )
    if not found:
        print(
            f"[{lot['lot']}] no P2WSH output commits to the "
            "posted witness script; refusing delivery"
        )
        return False
    _lot, delivery_pub, htlc_vout, htlc_value, htlc_spk = found
    expected_spk = b"\x00\x20" + hashlib.sha256(
        witness_script
    ).digest()
    if htlc_spk != expected_spk:
        raise ValueError("witness script does not match funded P2WSH output")
    p = verify_htlc(witness_script_hex, htlc_value, lot)
    print(
        f"[{lot['lot']}] verified HTLC: {htlc_value} sats, "
        f"{confirmations} BTC confirmations, "
        f"timeout {p['timeout']}"
    )
    seed_hex = read_claim_seed_hex(lot)
    enc = encrypt_seed(seed_hex, delivery_pub.hex())
    os.makedirs(OUT_DIR, exist_ok=True)
    out = {"lot": lot["lot"], "label": lot["label"],
           "funding_txid": funding_txid,
           "delivery_pubkey": delivery_pub.hex(),
           "htlc_vout": htlc_vout, "htlc_value_sats": htlc_value,
           "htlc_timeout": p["timeout"],
           "created_utc": datetime.now(timezone.utc).isoformat(),
           **enc}
    path = os.path.join(OUT_DIR, f"{lot['lot']}-{funding_txid}.json")
    with open(path, "w") as f:
        json.dump(out, f, indent=2)
    ls["delivered_txid"] = funding_txid
    save_state(state)
    print(f"[{lot['lot']}] encrypted claim seed published to", path)
    print("delivery pubkey:", delivery_pub.hex())
    print("NOTE: push claim-seeds/ to the repo so the taker can fetch it.")
    return True

def check_once():
    lots = all_lots()
    by_tag = {lot["tag"]: lot for lot in lots}
    state = load_state()
    scripts_by_issue = {}
    try:
        txs = signal_txs()
    except Exception as e:
        print(f"warning: signal address unreachable ({str(e)[:150]}); will retry next run")
        return
    for tx in txs:
        txid = tx["txid"]
        found = find_delivery_key(tx, lots)
        if not found:
            continue
        lot, _pub, _vout, _val, _spk = found
        ls = lot_state(state, lot["lot"])
        if ls.get("delivered_txid"):
            continue
        issue_no = lot.get("issue")
        if issue_no not in scripts_by_issue:
            scripts_by_issue[issue_no] = issue_witness_scripts(issue_no)
        scripts = scripts_by_issue[issue_no]
        if txid in scripts:
            print(f"[{lot['lot']}] candidate funding:", txid)
            if deliver(txid, scripts[txid], lot):
                return
        else:
            if issue_no:
                print(f"[{lot['lot']}] candidate funding {txid} has no witness script posted on issue #{issue_no} yet; waiting")
            else:
                print(f"[{lot['lot']}] candidate funding {txid} — no GitHub issue exists for this lot yet; cannot verify the witness script")
    print("check complete: no new verified funding")

def main():
    ap = argparse.ArgumentParser(description="Swap watcher: deliver the encrypted claim seed to the first verified taker (per lot).")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--watch", action="store_true")
    ap.add_argument("--funding-txid")
    ap.add_argument("--witness-script")
    ap.add_argument("--lot", default="1k", help="Lot for one-shot delivery (default 1k)")
    args = ap.parse_args()
    if args.funding_txid:
        if not args.witness_script:
            sys.exit("--witness-script is required with --funding-txid")
        deliver(args.funding_txid, args.witness_script, load_lot(args.lot))
    else:
        check_once()

if __name__ == "__main__":
    main()
