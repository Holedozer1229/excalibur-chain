#!/usr/bin/env python3
"""Generate HEIGHTS.md — the live sponsored-height inventory board.

Reads the fork tip (peer RPC 9532, checkpoint file as fallback) and the
sponsor registry, then lists the next 120 heights with the exact
prices the payment watcher enforces. The board header names the tip
source (live RPC or checkpoint fallback) so a stale fallback is
visible instead of silent. Prices here mirror
payment_watcher.py (PRICE_ORDINARY / PRICE_ROUND / PRICE_PREMIUM) —
if they ever disagree, the watcher is the law and this board is wrong.
"""
import http.client
import json
import os
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REGISTRY = os.environ.get("SPONSORS_FILE", os.path.join(HERE, "sponsors.json"))
PRICE_ORDINARY = 21_000
PRICE_ROUND = 1_000_000
PRICE_PREMIUM = {26_400: 5_000_000, 30_000: 5_000_000}
WINDOW = 120


def price_for(h):
    if h in PRICE_PREMIUM:
        return PRICE_PREMIUM[h]
    if h % 1000 == 0:
        return PRICE_ROUND
    return PRICE_ORDINARY


def tip():
    """Return (height, source). Source is 'live' (peer RPC 9532) or
    'checkpoint' (fallback when the RPC is unreachable after a retry)."""
    for attempt in range(2):
        try:
            c = http.client.HTTPConnection("127.0.0.1", 9532, timeout=8)
            c.request("POST", "/", json.dumps(
                {"jsonrpc": "2.0", "id": 1, "method": "getblockcount",
                 "params": []}))
            return int(json.loads(c.getresponse().read())["result"]), "live"
        except Exception:
            if attempt == 0:
                time.sleep(2)
    ck = json.load(open(os.path.join(HERE,
                                     "genealogy_checkpoint.json")))
    return int(ck.get("height") or ck.get("tip_height") or 0), "checkpoint"


def main():
    t, src = tip()
    try:
        sold = json.load(open(REGISTRY))
    except Exception:
        sold = {}
    now = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
    src_note = "live RPC" if src == "live" else "checkpoint fallback"
    lines = [
        "# Sponsored Heights — Live Inventory",
        "",
        f"Fork tip **{t}** · via {src_note} · board generated {now} · refreshed hourly.",
        "",
        "Every height below is for sale at the price shown — the same",
        "price the payment watcher enforces (see [SPONSOR.md](SPONSOR.md)",
        "for the exact OP_RETURN order format). Pay, wait one",
        "confirmation, and the height is registered to your lock and",
        "tag. Delivery is automatic: the chain's own merge-mining",
        "producer builds your coinbase at your height (first canonical",
        "sponsored block: height 25,889, delivered 2026-10-23).",
        "",
        "| Height | Price (sats) | Price (BTC) | Status |",
        "|-------:|-------------:|------------:|:-------|",
    ]
    for h in range(t + 2, t + 2 + WINDOW):
        p = price_for(h)
        status = "REGISTERED" if str(h) in sold else "OPEN"
        mark = ""
        if h in PRICE_PREMIUM:
            mark = " — premium lot"
        elif h % 1000 == 0:
            mark = " — round height"
        lines.append(f"| {h} | {p:,} | {p / 1e8:.5f} | {status}{mark} |")
    next_round = ((t // 1000) + 1) * 1000
    future_premium = sorted(h for h in PRICE_PREMIUM if h > t)
    if future_premium:
        premium_note = ("Premium lots ahead: " +
                        ", ".join(f"**{h:,}**" for h in future_premium) +
                        " (0.05 BTC).")
    else:
        premium_note = ("The named premium lots (" +
                        ", ".join(f"{h:,}" for h in sorted(PRICE_PREMIUM)) +
                        ", 0.05 BTC) are behind the tip.")
    lines += [
        "",
        f"Next round height: **{next_round:,}** (0.01 BTC). "
        f"{premium_note}",
        "Round heights (every 1,000th) are 0.01 BTC; all others",
        "0.00021 BTC.",
        "",
        "EXCAL has no market and no return is promised — a sponsored",
        "height buys a permanent, self-verifiable place in this",
        "chain's history: your lock paid by the coinbase, your tag",
        "sealed in it, checkable by anyone with",
        "[genealogy_verify.py](genealogy_verify.py).",
    ]
    out = os.path.join(HERE, "HEIGHTS.md")
    open(out, "w").write("\n".join(lines) + "\n")
    print(f"board written: tip {t}, heights {t + 2}..{t + 1 + WINDOW}, "
          f"{len(sold)} registered")


if __name__ == "__main__":
    main()
