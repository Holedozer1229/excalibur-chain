#!/usr/bin/env python3
"""taker_htlc.py — self-serve BTC funding for the 1,000 EXCAL offer.

The taker runs this LOCALLY. No message to Lux is needed. It builds the
UNSIGNED funding PSBT for their Bitcoin HTLC at ANY amount they choose,
then they sign it in their own wallet (Sparrow / Electrum / Bitcoin Core)
and broadcast it themselves.

What the funding transaction does (4 outputs):
  0. P2WSH HTLC locking <amount> sats.
     Claim (Lux): secret preimage + signature from Lux's miner key
     (02e8311342cb7accd4edef31462fcda1ef56bfbf7d4f03d3c8872dbec9a1bba1b3).
     Refund (taker): after BTC height <funding height + 144>, signature
     from the taker's refund pubkey (supplied with --refund-pubkey).
     Secret hash is the published one: d1baf924... (same secret as the
     EXCAL lock, so one secret unlocks both legs).
  1. OP_RETURN carrying the tag EXCAL1K + the taker's fresh delivery
     pubkey (33 bytes). The claim seed for the EXCAL lock is encrypted
     to this key and published publicly — only the taker can decrypt it.
  2. 1,000 sats to Lux's miner address bc1qj37xg5qmyedwfe70cz0f385cxmf6642kcznjdg.
     This is the auto-detection signal: the swap watcher sees a payment
     to this address, finds this transaction, and publishes the encrypted
     claim seed. (1,000 sats is above the P2WPKH dust limit.)
  3. Change back to the taker's --change-address.

Stdlib only. No private keys are ever read, printed, or sent anywhere.
The delivery keypair is generated fresh here and saved to
delivery_key.txt (0600) in the current directory — KEEP THAT FILE.
It is the only way to decrypt the claim seed later.

Usage:
  python3 taker_htlc.py --utxo TXID:VOUT --amount SATS \\
      --refund-pubkey HEX --change-address bc1q... [--fee-rate 5] [--btc-height N]

--utxo details (value + scriptPubKey) are fetched from mempool.space
with curl; pass --utxo-value and --utxo-scriptpubkey to supply them
manually instead.
"""
import argparse, base64, hashlib, json, os, subprocess, sys

SECRET_HASH_HEX = "d1baf924987ec0b2c4885f31b62abecf46919b113d2f0f3b9de83156c8564663"
MAKER_PUB_HEX = "02e8311342cb7accd4edef31462fcda1ef56bfbf7d4f03d3c8872dbec9a1bba1b3"
SIGNAL_ADDR = "bc1qj37xg5qmyedwfe70cz0f385cxmf6642kcznjdg"
SIGNAL_SATS = 1000
TIMEOUT_BLOCKS = 144
OP_RETURN_TAG = b"EXCAL1K"

def load_lot(name):
    """Public parameters for one lot (1k or 1excal). The lot file is
    public data — it holds hashes and locks, never secrets."""
    here = os.path.dirname(os.path.abspath(__file__))
    for cand in (os.path.join(here, "lots", name + ".json"),
                 os.path.join(here, name + ".json")):
        if os.path.exists(cand):
            with open(cand) as f:
                return json.load(f)
    sys.exit(f"unknown lot {name!r} (expected lots/{name}.json next to this script)")

# ---------------------------------------------------------------- secp256k1 (keygen only, pure python)
P = 0xfffffffffffffffffffffffffffffffffffffffffffffffffffffffefffffc2f
N = 0xfffffffffffffffffffffffffffffffebaaedce6af48a03bbfd25e8cd0364141
Gx = 0x79be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798
Gy = 0x483ada7726a3c4655da4fbfc0e1108a8fd17b448a68554199c47d08ffb10d4b8

def _add(p, q):
    if p is None: return q
    if q is None: return p
    x1, y1 = p; x2, y2 = q
    if x1 == x2 and y1 != y2: return None
    if p == q:
        l = (3 * x1 * x1) * pow(2 * y1, P - 2, P) % P
    else:
        l = (y2 - y1) * pow(x2 - x1, P - 2, P) % P
    x3 = (l * l - x1 - x2) % P
    return (x3, (l * (x1 - x3) - y1) % P)

def _mul(k, point=(Gx, Gy)):
    r = None
    while k:
        if k & 1: r = _add(r, point)
        point = _add(point, point); k >>= 1
    return r

def compressed_pubkey(priv_bytes: bytes) -> bytes:
    d = int.from_bytes(priv_bytes, "big")
    x, y = _mul(d)
    return bytes([0x02 | (y & 1)]) + x.to_bytes(32, "big")

# ---------------------------------------------------------------- bech32 (BIP173)
CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"

def _polymod(vals):
    chk = 1
    for v in vals:
        b = chk >> 25; chk = ((chk & 0x1ffffff) << 5) ^ v
        for i in range(5):
            if (b >> i) & 1: chk ^= [0x3b6a57b2, 0x26508e6d, 0x1ea119fa, 0x3d4233dd, 0x2a1462b3][i]
    return chk

def _hrp_expand(hrp):
    return [ord(x) >> 5 for x in hrp] + [0] + [ord(x) & 31 for x in hrp]

def _convertbits(data, frm, to, pad=True):
    acc = 0; bits = 0; ret = []; maxv = (1 << to) - 1
    for v in data:
        acc = (acc << frm) | v; bits += frm
        while bits >= to:
            bits -= to; ret.append((acc >> bits) & maxv)
    if pad and bits: ret.append((acc << (to - bits)) & maxv)
    return ret

def bech32_decode(addr):
    if addr.lower() != addr and addr.upper() != addr: raise ValueError("mixed-case bech32")
    addr = addr.lower()
    pos = addr.rfind("1")
    hrp, data = addr[:pos], addr[pos + 1:]
    vals = [CHARSET.index(c) for c in data]
    if _polymod(_hrp_expand(hrp) + vals) != 1: raise ValueError("bad bech32 checksum")
    return hrp, vals[:-6]

def bech32_encode(hrp, witver, prog):
    data = [witver] + _convertbits(prog, 8, 5)
    vals = _hrp_expand(hrp) + data
    pm = _polymod(vals + [0] * 6) ^ 1
    cs = [(pm >> 5 * (5 - i)) & 31 for i in range(6)]
    return hrp + "1" + "".join(CHARSET[c] for c in data + cs)

def p2wpkh_scriptpubkey(addr):
    hrp, vals = bech32_decode(addr)
    if vals[0] != 0: raise ValueError("change address must be SegWit v0 (bc1q...)")
    prog = bytes(_convertbits(vals[1:], 5, 8, pad=False))
    if len(prog) != 20: raise ValueError("change address must be P2WPKH (20-byte program)")
    return b"\x00\x14" + prog

# ---------------------------------------------------------------- script helpers
def push(data: bytes) -> bytes:
    if len(data) < 76: return bytes([len(data)]) + data
    if len(data) < 256: return b"\x4c" + bytes([len(data)]) + data
    raise ValueError("push too large")

def encode_num(n: int) -> bytes:
    if n == 0: return b""
    neg = n < 0; a = abs(n); out = bytearray()
    while a: out.append(a & 0xff); a >>= 8
    if out[-1] & 0x80: out.append(0x80 if neg else 0x00)
    elif neg: out[-1] |= 0x80
    return bytes(out)

def htlc_witness_script(maker_pub, taker_pub, secret_hash, timeout):
    return (b"\x63" + b"\xa8" + push(secret_hash) + b"\x88"
            + push(maker_pub) + b"\xac" + b"\x67"
            + push(encode_num(timeout)) + b"\xb1\x75"
            + push(taker_pub) + b"\xac" + b"\x68")

def varint(n):
    if n < 0xfd: return bytes([n])
    if n <= 0xffff: return b"\xfd" + n.to_bytes(2, "little")
    if n <= 0xffffffff: return b"\xfe" + n.to_bytes(4, "little")
    return b"\xff" + n.to_bytes(8, "little")

def ser_tx(tx):
    out = bytearray()
    out += int(tx["version"]).to_bytes(4, "little", signed=True)
    out += varint(len(tx["vin"]))
    for v in tx["vin"]:
        out += bytes(v["prev"]) + int(v["idx"]).to_bytes(4, "little")
        out += varint(len(v["script"])) + v["script"]
        out += int(v["seq"]).to_bytes(4, "little")
    out += varint(len(tx["vout"]))
    for o in tx["vout"]:
        out += int(o["value"]).to_bytes(8, "little")
        out += varint(len(o["script"])) + o["script"]
    out += int(tx["locktime"]).to_bytes(4, "little")
    return bytes(out)

def txid_of(tx):
    return hashlib.sha256(hashlib.sha256(ser_tx(tx)).digest()).digest()[::-1].hex()

def curl_json(url):
    r = subprocess.run(["curl", "-s", "-m", "25", url], capture_output=True, text=True)
    if r.returncode != 0 or not r.stdout.strip():
        raise RuntimeError(f"curl failed for {url}: {r.stderr.strip()[:200]}")
    return json.loads(r.stdout)

# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="Build the unsigned BTC HTLC funding PSBT for the 1,000 EXCAL offer.")
    ap.add_argument("--utxo", required=True, help="Funding input TXID:VOUT (display-order txid)")
    ap.add_argument("--amount", type=int, required=True, help="BTC offered, in satoshis (any amount)")
    ap.add_argument("--refund-pubkey", required=True, help="Taker's compressed pubkey hex (33 bytes) for the HTLC refund path")
    ap.add_argument("--change-address", required=True, help="Taker's P2WPKH change address (bc1q...)")
    ap.add_argument("--fee-rate", type=int, default=5, help="Fee rate in sats/vB (default 5)")
    ap.add_argument("--btc-height", type=int, default=None, help="Current BTC tip height (auto-fetched from mempool.space if omitted)")
    ap.add_argument("--utxo-value", type=int, default=None, help="Funding UTXO value in sats (auto-fetched if omitted)")
    ap.add_argument("--utxo-scriptpubkey", default=None, help="Funding UTXO scriptPubKey hex (auto-fetched if omitted)")
    ap.add_argument("--force", action="store_true", help="Fund even if a swap is already in progress (NOT recommended)")
    ap.add_argument("--lot", default="1k", help="Which lot: 1k (1,000 EXCAL) or 1excal (1 EXCAL). Default 1k.")
    args = ap.parse_args()
    lot = load_lot(args.lot)
    tag = lot["tag"].encode()
    secret_hash_hex = lot["secret_hash"]
    if lot.get("funding_block") is None and not args.force:
        sys.exit(
            f"The {lot['label']} lot is NOT funded on-chain yet (funding built "
            "and verified, broadcast pending). Do NOT fund it — there is no "
            "confirmed EXCAL lock to claim. Wait until the funding confirms "
            "and the lot file shows a funding block. (Override with --force "
            "at your own risk.)")

    if args.amount <= 0: sys.exit("amount must be positive")
    try:
        txid_disp, vout_s = args.utxo.split(":")
        vout = int(vout_s)
        prev_wire = bytes.fromhex(txid_disp)[::-1]
    except Exception:
        sys.exit("--utxo must be TXID:VOUT")
    try:
        refund_pub = bytes.fromhex(args.refund_pubkey)
        if len(refund_pub) != 33 or refund_pub[0] not in (0x02, 0x03):
            raise ValueError
    except Exception:
        sys.exit("--refund-pubkey must be a 33-byte compressed pubkey hex")
    maker_pub = bytes.fromhex(MAKER_PUB_HEX)
    if refund_pub == maker_pub: sys.exit("refund pubkey must differ from the maker pubkey")

    # Pre-flight: is a swap already in progress? One lot, one taker.
    # Any earlier funding with an EXCAL1K OP_RETURN means the offer is
    # already taken; funding again would lock your BTC for 144 blocks
    # with no EXCAL to claim (Lux only claims the first funding).
    if not args.force:
        try:
            sig_txs = curl_json(f"https://mempool.space/api/address/{SIGNAL_ADDR}/txs")
            for t in sig_txs:
                for o in t.get("vout", []):
                    spk = bytes.fromhex(o["scriptpubkey"])
                    # Exact tag match: OP_RETURN data must be tag + 33-byte pubkey.
                    # (EXCAL1 is a prefix of EXCAL1K — the length check keeps lots apart.)
                    if spk[:1] == b"\x6a" and len(spk) >= 2 + len(tag) + 33:
                        data = spk[2:]
                        if data[1:1 + len(tag)] == tag and len(data) == 1 + len(tag) + 33:
                            sys.exit(
                                f"A swap is already in progress for the {lot['label']} lot: "
                                f"an {lot['tag']} funding exists on the signal address "
                                f"(tx {t['txid']}). Do NOT fund — that lot is taken. Wait for the "
                                "offer to reset or contact the maker through the GitHub issue. "
                                "(Override with --force at your own risk.)")
        except SystemExit:
            raise
        except Exception as e:
            print(f"warning: could not check the signal address ({e}); proceeding")
            print("Check the GitHub issue yourself before funding: an earlier funding")
            print("means the lot is taken and your BTC would sit locked for 144 blocks.")

    # Funding UTXO details
    if args.utxo_value is None or args.utxo_scriptpubkey is None:
        print("fetching UTXO details from mempool.space ...")
        tx = curl_json(f"https://mempool.space/api/tx/{txid_disp}")
        try:
            out = tx["vout"][vout]
        except Exception:
            sys.exit("UTXO not found on mempool.space for that txid:vout")
        utxo_value = out["value"]; utxo_script = bytes.fromhex(out["scriptpubkey"])
    else:
        utxo_value = args.utxo_value; utxo_script = bytes.fromhex(args.utxo_scriptpubkey)

    # BTC tip height + HTLC timeout
    if args.btc_height is None:
        print("fetching BTC tip height from mempool.space ...")
        tip = curl_json("https://mempool.space/api/blocks/tip/height")
        btc_height = int(tip)
    else:
        btc_height = args.btc_height
    timeout = btc_height + TIMEOUT_BLOCKS

    # Fresh delivery keypair (for the encrypted claim seed)
    delivery_priv = os.urandom(32)
    delivery_pub = compressed_pubkey(delivery_priv)
    with open("delivery_key.txt", "w") as f:
        f.write(delivery_priv.hex() + "\n")
    os.chmod("delivery_key.txt", 0o600)

    # HTLC lock
    secret_hash = bytes.fromhex(secret_hash_hex)
    script = htlc_witness_script(maker_pub, refund_pub, secret_hash, timeout)
    htlc_addr = bech32_encode("bc", 0, hashlib.sha256(script).digest())
    htlc_spk = b"\x00\x20" + hashlib.sha256(script).digest()

    # Fee + change (vsize estimate: 1 P2WPKH in ~68 vB, outputs ~158 vB, overhead ~10 vB)
    vsize_est = 236
    fee = args.fee_rate * vsize_est
    change = utxo_value - args.amount - SIGNAL_SATS - fee
    outputs = [
        {"value": args.amount, "script": htlc_spk},
        {"value": 0, "script": b"\x6a" + push(tag + delivery_pub)},
        {"value": SIGNAL_SATS, "script": p2wpkh_scriptpubkey(SIGNAL_ADDR)},
    ]
    if change >= 1000:
        outputs.append({"value": change, "script": p2wpkh_scriptpubkey(args.change_address)})
    elif change < 0:
        sys.exit(f"UTXO value {utxo_value} does not cover amount {args.amount} + signal {SIGNAL_SATS} + fee {fee}")
    else:
        fee += change  # dust change folds into the fee
        print(f"note: tiny change ({change} sats) folded into the fee")

    tx = {"version": 2,
          "vin": [{"prev": prev_wire, "idx": vout, "script": b"", "seq": 0xFFFFFFFF}],
          "vout": outputs, "locktime": 0}
    expected_txid = txid_of(tx)

    # Minimal BIP-174 PSBT: global unsigned tx + input witness_utxo
    psbt = bytearray(b"\x70\x73\x62\x74\xff")
    psbt += b"\x01\x00" + varint(len(ser_tx(tx))) + ser_tx(tx)
    psbt += b"\x00"
    wu = utxo_value.to_bytes(8, "little") + varint(len(utxo_script)) + utxo_script
    psbt += b"\x01\x01" + varint(len(wu)) + wu
    psbt += b"\x00"
    psbt += b"\x00"
    psbt_b64 = base64.b64encode(bytes(psbt)).decode()

    with open("funding.psbt", "w") as f:
        f.write(psbt_b64 + "\n")
    print()
    print(f"Lot: {lot['label']} (--lot {lot['lot']})")
    print("HTLC P2WSH address:", htlc_addr)
    print("HTLC timeout (BTC height):", timeout, f"(tip {btc_height} + {TIMEOUT_BLOCKS})")
    print("Maker (Lux) claim pubkey:", MAKER_PUB_HEX)
    print("Secret hash:", secret_hash_hex)
    print("Delivery pubkey (in OP_RETURN):", delivery_pub.hex())
    print("Delivery private key saved to delivery_key.txt (0600) — KEEP IT. It decrypts the claim seed.")
    print("Expected funding txid after broadcast:", expected_txid)
    print("Fee:", fee, "sats at", args.fee_rate, "sats/vB")
    print("Unsigned PSBT written to funding.psbt (base64). Sign it in your wallet and broadcast.")
    print()
    print("NEXT (no message needed): after broadcast, the swap watcher sees the")
    print("1,000-sat signal, verifies the HTLC, and publishes the claim seed")
    print("encrypted to your delivery pubkey. Lux claims the BTC (revealing the")
    print("secret on-chain); you then run taker_claim.py to claim the 1,000 EXCAL.")

if __name__ == "__main__":
    main()
