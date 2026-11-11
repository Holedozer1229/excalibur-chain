#!/usr/bin/env python3
"""claim_btc.py — Lux's side: claim the taker's BTC HTLC (reveals the secret).

Run when the swap watcher reports a verified funding. This is a LIVE
Bitcoin spend, so it defaults to DRY RUN: it prints the claim tx and
its txid and does NOT sign or broadcast. Pass --sign-and-broadcast
only when Lux approves this exact claim (amount, funding txid, fee).

What it does: spends the taker's P2WSH HTLC with the secret preimage +
a signature from Lux's miner key, paying the BTC to Lux's miner P2WPKH
(bc1qj37xg5qmyedwfe70cz0f385cxmf6642kcznjdg). The secret appears in
the claim witness on-chain — that is what lets the taker claim the
1,000 EXCAL. Claim promptly: the taker can only claim the EXCAL after
this reveals the secret, and the EXCAL refund opens at fork height
62898.

Usage:
  python3 claim_btc.py --funding-txid TXID --witness-script HEX [--fee 1000]
  python3 claim_btc.py --funding-txid TXID --witness-script HEX --sign-and-broadcast

Needs the repo's btc_htlc / secp256k1 modules (run from ~/workspace).
Reads secret.key and wallet_fork.json (0600). NEVER prints either value.
"""
import argparse, hashlib, json, os, subprocess, sys

sys.path.insert(0, os.path.expanduser("~/workspace"))

SECRET_HASH_HEX = "d1baf924987ec0b2c4885f31b62abecf46919b113d2f0f3b9de83156c8564663"
MAKER_PUB_HEX = "02e8311342cb7accd4edef31462fcda1ef56bfbf7d4f03d3c8872dbec9a1bba1b3"
OFFER_DIR = os.path.expanduser("~/workspace/excal-1k-offer-2026-11-10")
SECRET_FILE = os.path.join(OFFER_DIR, "secret.key")
WALLET_FILE = os.path.expanduser("~/workspace/wallet_fork.json")

def load_lot(name):
    """Public parameters for one lot (1k or 1excal)."""
    here = os.path.join(os.path.expanduser("~/workspace"),
                        "excal-1k-offer-2026-11-10", "self-serve")
    with open(os.path.join(here, "lots", name + ".json")) as f:
        return json.load(f)

def curl(url, data=None):
    cmd = ["curl", "-s", "-m", "30"]
    if data is not None:
        cmd += ["-X", "POST", "--data-binary", data, "-H", "Content-Type: text/plain"]
    cmd.append(url)
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"curl {url} failed rc={r.returncode}: {r.stderr[:200]}")
    return r.stdout

def read_secret(secret_file, secret_hash_hex):
    with open(secret_file) as f:
        txt = f.read().strip()
    if ":" in txt:
        txt = txt.split(":", 1)[1].strip()
    secret = bytes.fromhex(txt)
    if len(secret) != 32 or hashlib.sha256(secret).digest().hex() != secret_hash_hex:
        sys.exit("secret.key does not match the published secret hash")
    return secret

def read_miner_priv():
    with open(WALLET_FILE) as f:
        d = json.load(f)
    priv = bytes.fromhex(d["priv"])
    from secp256k1 import priv_to_pub
    if priv_to_pub(priv).hex() != MAKER_PUB_HEX:
        sys.exit("wallet_fork.json pubkey does not match the maker pubkey")
    return priv

def varint(n):
    if n < 0xfd: return bytes([n])
    if n <= 0xffff: return b"\xfd" + n.to_bytes(2, "little")
    if n <= 0xffffffff: return b"\xfe" + n.to_bytes(4, "little")
    return b"\xff" + n.to_bytes(8, "little")

def ser_segwit_tx(tx, witnesses):
    out = bytearray()
    out += int(tx["version"]).to_bytes(4, "little", signed=True)
    out += b"\x00\x01"
    out += varint(len(tx["vin"]))
    for v in tx["vin"]:
        out += bytes(v["prev_txid"]) + int(v["prev_vout"]).to_bytes(4, "little")
        out += varint(0)
        out += int(v["sequence"]).to_bytes(4, "little")
    out += varint(len(tx["vout"]))
    for o in tx["vout"]:
        out += int(o["value"]).to_bytes(8, "little")
        out += varint(len(o["script_pubkey"])) + o["script_pubkey"]
    for w in witnesses:
        out += varint(len(w))
        for item in w:
            out += varint(len(item)) + item
    out += int(tx["locktime"]).to_bytes(4, "little")
    return bytes(out)

def main():
    ap = argparse.ArgumentParser(description="Claim the taker's BTC HTLC (Lux side). Dry run unless --sign-and-broadcast.")
    ap.add_argument("--funding-txid", required=True)
    ap.add_argument("--witness-script", required=True, help="Witness script hex (taker posted it on issue #2)")
    ap.add_argument("--fee", type=int, default=1000, help="Claim fee in sats (default 1000)")
    ap.add_argument("--lot", default="1k", help="Which lot: 1k (1,000 EXCAL) or 1excal (1 EXCAL). Default 1k.")
    ap.add_argument("--sign-and-broadcast", action="store_true",
                    help="Actually sign with the miner key and broadcast. Requires Lux's approval.")
    args = ap.parse_args()
    lot = load_lot(args.lot)
    secret_hash_hex = lot["secret_hash"]
    secret_file = os.path.join(os.path.expanduser("~/workspace"), lot["offer_dir"], "secret.key")
    print(f"Lot: {lot['label']} (--lot {lot['lot']})")

    import btc_htlc as H
    from txscript import hash160
    from secp256k1 import sign_der

    script = bytes.fromhex(args.witness_script)
    p = H.parse_witness_script(script)
    assert p["maker_pubkey"].hex() == MAKER_PUB_HEX, "witness script maker is not Lux's miner key"
    assert p["secret_hash"].hex() == secret_hash_hex, "witness script secret hash mismatch for this lot"

    ftx = json.loads(curl(f"https://mempool.space/api/tx/{args.funding_txid}"))
    spk = H.p2wsh_script_pubkey(script).hex()
    htlc_vout = None; htlc_value = None
    for i, o in enumerate(ftx["vout"]):
        if o["scriptpubkey"] == spk:
            htlc_vout, htlc_value = i, o["value"]
    if htlc_vout is None:
        sys.exit("no P2WSH output matching the witness script in the funding tx")
    print(f"HTLC output: vout {htlc_vout}, {htlc_value} sats, timeout BTC height {p['timeout']}")

    maker_pub = bytes.fromhex(MAKER_PUB_HEX)
    dest_spk = b"\x00\x14" + hash160(maker_pub)
    claim = H.claim_tx_template(bytes.fromhex(args.funding_txid)[::-1], htlc_vout,
                                dest_spk, htlc_value, args.fee)
    tx = {"version": claim["version"], "vin": claim["vin"], "vout": claim["vout"],
          "locktime": claim["locktime"]}
    sighash = H.bip143_sighash(tx, 0, script, htlc_value)
    print("claim pays", htlc_value - args.fee, "sats to the miner P2WPKH")
    print("BIP143 sighash:", sighash.hex())
    if not args.sign_and_broadcast:
        print("DRY RUN — not signed, not broadcast. Re-run with --sign-and-broadcast to execute.")
        return
    secret = read_secret(secret_file, secret_hash_hex)
    priv = read_miner_priv()
    sig = sign_der(priv, sighash) + b"\x01"
    witness = [sig, secret, b"\x01", script]
    raw = ser_segwit_tx(tx, [witness])
    txid = hashlib.sha256(hashlib.sha256(raw).digest()).digest()[::-1].hex()
    print("signed claim txid:", txid)
    resp = curl("https://mempool.space/api/tx", data=raw.hex())
    print("broadcast response:", resp[:200])
    print("SECRET REVEALED on-chain in this claim. The taker can now claim the 1,000 EXCAL.")

if __name__ == "__main__":
    main()
