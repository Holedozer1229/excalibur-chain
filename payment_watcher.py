#!/usr/bin/env python3
"""Payment watcher for Excalibur sponsored blocks.

Watches the BTC payout address on mempool.space. A payment carrying
an OP_RETURN order is self-describing:

    OP_RETURN  "EXCAL1" | height:3B big-endian | hash160:20B | tag:<=51B utf-8

On >= 1 confirmation, if the amount covers the lot price for that
height and the height is unsold and still in the future, the watcher
writes the sponsor registry the stratum shim reads — delivery at the
height is then automatic. Anything else (no order, underpaid, height
already sold) goes to a review file for a human, never to the
registry.

Usage: payment_watcher.py [--once]   (default: poll every 60 s)
"""
import json
import os
import subprocess
import sys
import time

ADDRESS = "12jgGaSXJ7jQvrroNZYru13CrjEaZrmDPj"
API = "https://mempool.space/api"
HERE = os.path.dirname(os.path.abspath(__file__))
REGISTRY = os.environ.get("SPONSORS_FILE", os.path.join(HERE, "sponsors.json"))
STATE_FILE = os.path.join(HERE, "watcher_state.json")
REVIEW_FILE = os.path.join(HERE, "watcher_review.jsonl")
MAGIC = b"EXCAL1"

# Lot prices in sats (mirror SPONSOR.md / FLOOD.md).
PRICE_ORDINARY = 100_000          # 0.001 BTC
PRICE_ROUND = 1_000_000           # 0.01 BTC  (height % 1000 == 0)
PRICE_PREMIUM = {26_400: 5_000_000, 30_000: 5_000_000}  # 0.05 BTC named premium lots


def price_for(height):
    if height in PRICE_PREMIUM:
        return PRICE_PREMIUM[height]
    if height % 1000 == 0:
        return PRICE_ROUND
    return PRICE_ORDINARY


def curl_json(url):
    out = subprocess.run(["curl", "-s", "-m", "30", url],
                         capture_output=True, text=True)
    return json.loads(out.stdout)


def fork_tip():
    import http.client
    c = http.client.HTTPConnection("127.0.0.1", 9432, timeout=10)
    c.request("POST", "/", json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": "getblockcount",
         "params": []}))
    r = json.loads(c.getresponse().read())
    return int(r["result"])


def parse_order(tx):
    """Extract an EXCAL1 order from a mempool.space tx dict.
    Returns dict(height, hash160_hex, tag) or None."""
    for vout in tx.get("vout", []):
        spk = vout.get("scriptpubkey", "")
        if not spk.startswith("6a"):
            continue
        try:
            raw = bytes.fromhex(spk)
        except ValueError:
            continue
        # OP_RETURN <push> payload
        if len(raw) < 3:
            continue
        ln = raw[1]
        payload = raw[2:2 + ln] if ln < 0x4c else raw[3:3 + raw[2]]
        if not payload.startswith(MAGIC):
            continue
        body = payload[len(MAGIC):]
        if len(body) < 23:
            continue
        height = int.from_bytes(body[0:3], "big")
        h160 = body[3:23].hex()
        tag = body[23:].decode("utf-8", "replace")
        return {"height": height, "hash160": h160, "tag": tag}
    return None


def paid_to_address(tx):
    return sum(v.get("value", 0) for v in tx.get("vout", [])
               if v.get("scriptpubkey_address") == ADDRESS)


def confirmations(tx, btc_tip):
    st = tx.get("status", {})
    if not st.get("confirmed"):
        return 0
    return btc_tip - int(st["block_height"]) + 1


def validate(order, paid, confs, tip, registry):
    """Pure validation. Returns (ok, reason)."""
    if confs < 1:
        return False, "unconfirmed"
    h = order["height"]
    if h <= tip + 1:
        return False, f"height {h} not in the future (tip {tip})"
    if str(h) in registry or h in registry:
        return False, f"height {h} already sold"
    price = price_for(h)
    if paid < price:
        return False, f"underpaid: {paid} < {price} sats for height {h}"
    return True, "ok"


def load_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def save_registry(reg):
    tmp = REGISTRY + ".tmp"
    with open(tmp, "w") as f:
        json.dump(reg, f, indent=1, sort_keys=True)
    os.replace(tmp, REGISTRY)


def review(entry):
    with open(REVIEW_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")
    print("REVIEW:", json.dumps(entry), flush=True)


def process_once():
    txs = curl_json(f"{API}/address/{ADDRESS}/txs")
    btc_tip = int(curl_json(f"{API}/blocks/tip/height"))
    tip = fork_tip()
    state = load_json(STATE_FILE, {"seen": {}})
    registry = load_json(REGISTRY, {})
    changed = False
    for tx in txs:
        txid = tx["txid"]
        if txid in state["seen"]:
            continue
        paid = paid_to_address(tx)
        if paid == 0:
            continue
        confs = confirmations(tx, btc_tip)
        order = parse_order(tx)
        rec = {"txid": txid, "paid_sats": paid, "confs": confs,
               "time": int(time.time())}
        if order is None:
            rec["reason"] = "payment without EXCAL1 order — manual review"
            review(rec)
            state["seen"][txid] = "review"
            changed = True
            continue
        ok, reason = validate(order, paid, confs, tip, registry)
        rec.update({"order": order, "reason": reason})
        if ok:
            registry[str(order["height"])] = {
                "lock": order["hash160"], "tag": order["tag"]}
            save_registry(registry)
            state["seen"][txid] = "registered"
            print(f"REGISTERED height {order['height']} from {txid} "
                  f"({paid} sats)", flush=True)
        else:
            # keep unconfirmed orders pending; file the rest
            if reason == "unconfirmed":
                continue
            rec["reason"] = reason
            review(rec)
            state["seen"][txid] = "review"
        changed = True
    if changed:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=1)
    return len(txs)


def main():
    once = "--once" in sys.argv
    while True:
        try:
            n = process_once()
            print(f"poll ok: {n} txs on address", flush=True)
        except Exception as e:
            print(f"poll error: {e}", flush=True)
        if once:
            return
        time.sleep(60)


if __name__ == "__main__":
    main()
