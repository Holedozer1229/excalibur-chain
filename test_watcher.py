#!/usr/bin/env python3
"""Simulation harness for payment_watcher: synthetic mempool.space
txs exercise the full classify path. No network, no real BTC."""
import sys
sys.path.insert(0, "/home/hatch/workspace/stratum_shim")
import payment_watcher as pw

ADDR = pw.ADDRESS
H160 = "62e907b15cbf27d5425399ebf6f0fb50ebb88f18"  # any 20-byte value


def order_spk(height, tag=b"TEST LOT"):
    payload = pw.MAGIC + height.to_bytes(3, "big") + bytes.fromhex(H160) + tag
    return "6a" + f"{len(payload):02x}" + payload.hex()


def mk_tx(txid, paid, height=None, conf_block=900000, tag=b"TEST LOT"):
    vout = [{"value": paid, "scriptpubkey_address": ADDR,
             "scriptpubkey": "0014" + "00" * 20}]
    if height is not None:
        vout.append({"value": 0, "scriptpubkey": order_spk(height, tag),
                     "scriptpubkey_address": None})
    return {"txid": txid, "vout": vout,
            "status": {"confirmed": conf_block is not None,
                       "block_height": conf_block or 0}}


passed = failed = 0


def check(name, cond):
    global passed, failed
    if cond:
        passed += 1
        print(f"  PASS {name}")
    else:
        failed += 1
        print(f"  FAIL {name}")


TIP = 25770
BTC_TIP = 900050

# parse
o = pw.parse_order(mk_tx("a", 100000, 25800))
check("order parses", o and o["height"] == 25800 and o["hash160"] == H160
      and o["tag"] == "TEST LOT")
check("plain payment parses to no order",
      pw.parse_order(mk_tx("b", 5000)) is None)

# validate: happy path, 1 conf, exact price, unsold, future
reg = {}
ok, _ = pw.validate(o, pw.paid_to_address(mk_tx("a", 100000, 25800)),
                    pw.confirmations(mk_tx("a", 100000, 25800), BTC_TIP),
                    TIP, reg)
check("valid ordinary order accepted", ok)

# round height needs the round price
o2 = pw.parse_order(mk_tx("c", 100000, 26000))
ok, reason = pw.validate(o2, 100000, 5, TIP, reg)
check("round height at ordinary price rejected", not ok and "underpaid" in reason)
ok, _ = pw.validate(o2, 1000000, 5, TIP, reg)
check("round height at round price accepted", ok)

# premium lot
o3 = pw.parse_order(mk_tx("d", 5000000, 26400))
ok, _ = pw.validate(o3, 5000000, 5, TIP, reg)
check("premium lot at premium price accepted", ok)

# already sold
reg["25800"] = {"lock": H160, "tag": "x"}
ok, reason = pw.validate(o, 100000, 5, TIP, reg)
check("sold height rejected", not ok and "already sold" in reason)

# past height
o4 = pw.parse_order(mk_tx("e", 100000, 25700))
ok, reason = pw.validate(o4, 100000, 5, TIP, {})
check("past height rejected", not ok and "not in the future" in reason)

# unconfirmed stays pending (not ok, reason unconfirmed)
txu = mk_tx("f", 100000, 25900, conf_block=None)
ok, reason = pw.validate(pw.parse_order(txu), 100000,
                         pw.confirmations(txu, BTC_TIP), TIP, {})
check("unconfirmed held pending", not ok and reason == "unconfirmed")

# price table sanity
check("prices", pw.price_for(25800) == 21000
      and pw.price_for(26000) == 1000000
      and pw.price_for(26400) == 5000000)

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
