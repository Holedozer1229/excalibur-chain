#!/usr/bin/env python3
"""taker_claim.py — build + sign the EXCAL claim for the 1,000 EXCAL offer.

Run AFTER Lux has claimed your BTC HTLC (the secret is then public,
visible in his BTC claim transaction's witness). You need:
  * --secret: the 32-byte secret preimage (hex), read from Lux's BTC
    claim tx on mempool.space (its witness carries the preimage).
  * --claim-seed: the claim seed hex, decrypted with decrypt_seed.py
    from the ciphertext the swap watcher published for your funding tx.
  * --destination: YOUR Excalibur address — a LEGACY P2PKH address
    (starting with 1...). The Excalibur fork accepts only its own
    opcode-free locks as outputs; a SegWit bc1q address is NOT a valid
    fork output and validation will refuse it. Use the legacy address
    for your key (same hash160 as a Bitcoin legacy address).

The claim spends the confirmed QHTLC lock (funding tx 4873ebb3..., vout 0)
using the Trifold claim witness + the secret. The script verifies the
claim locally (Trifold signature + full fork validation) and refuses to
print the hex unless it validates. Nothing is broadcast by this script:
post the signed hex as a comment on GitHub issue #2 and the fork node
mines it into the next block. No message to Lux is needed.

Run from a checkout of the excalibur-chain repo (this script imports the
repo's txscript / trifold_lockbox modules). Plain python3, stdlib + repo.
"""
import argparse, hashlib, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Also allow running from the repo root (modules are repo siblings).
for _p in (os.getcwd(), os.path.expanduser("~/workspace")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Real lock parameters (public; confirmed on the fork in block 42899).
# Defaults come from lots/<lot>.json; --lock/--descriptor/--funding-txid/
# --locked-swords override them (test use). The 1k lot is the default.
LOCK_HEX = "045220338521d9905441244e566634f227b72bbb92"
DESC_HEX = ("d1baf924987ec0b2c4885f31b62abecf46919b113d2f0f3b9de83156c8564663"
            "91f33e7fe8f40b990da7f0911e9ae1ef8292273ce673d8965101ff1da1238d58"
            "9471855e1524e76ca41030b9137532bf5ca903c60e9744de33fa9b5488fbb791"
            "0000f5b2")
FUNDING_TXID = "4873ebb3a40b83f2401266587aba9f73bf837dd51349e07029b06819fcccfc95"
LOCKED_SWORDS = 100_000_000_000  # 1,000 EXCAL
SECRET_HASH_HEX = "d1baf924987ec0b2c4885f31b62abecf46919b113d2f0f3b9de83156c8564663"

def load_lot(name):
    """Public parameters for one lot (1k or 1excal)."""
    here = os.path.dirname(os.path.abspath(__file__))
    for cand in (os.path.join(here, "lots", name + ".json"),
                 os.path.join(here, name + ".json")):
        if os.path.exists(cand):
            with open(cand) as f:
                return json.load(f)
    sys.exit(f"unknown lot {name!r} (expected lots/{name}.json next to this script)")

# ---------------------------------------------------------------- address helpers
_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"

def b58check_decode(addr):
    n = 0
    for c in addr:
        n = n * 58 + _B58.index(c)
    raw = n.to_bytes(25, "big")
    payload, checksum = raw[:-4], raw[-4:]
    if hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4] != checksum:
        raise ValueError("bad base58check checksum")
    return payload[0], payload[1:]

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

def dest_script(address):
    """EXCAL PKH output script (0x00 + hash160) from a legacy P2PKH address.

    The fork accepts only its own opcode-free locks as outputs.
    A SegWit bc1q address is not a valid fork output — it is refused
    here with a clear error instead of producing an invalid claim.
    """
    if address.startswith("bc1"):
        sys.exit("destination must be a LEGACY P2PKH address (1...), not bc1q: "
                 "the Excalibur fork does not accept SegWit outputs. "
                 "Use the legacy address for your key (same hash160).")
    ver, payload = b58check_decode(address)
    if ver != 0x00 or len(payload) != 20:
        sys.exit("destination must be a legacy P2PKH address (1...)")
    return b"\x00" + payload

def main():
    ap = argparse.ArgumentParser(description="Build + sign the EXCAL claim for the 1,000 EXCAL offer.")
    ap.add_argument("--secret", required=True, help="32-byte secret preimage hex (from Lux's BTC claim tx)")
    ap.add_argument("--claim-seed", required=True, help="Claim seed hex (from decrypt_seed.py)")
    ap.add_argument("--destination", required=True, help="Your Excalibur LEGACY address (1...). bc1q is not valid on the fork.")
    ap.add_argument("--fee", type=int, default=10_000, help="Fee in swords (default 10000)")
    ap.add_argument("--fork-tip", type=int, default=42899, help="Fork tip height for local validation (default 42899)")
    ap.add_argument("--lot", default="1k", help="Which lot: 1k (1,000 EXCAL) or 1excal (1 EXCAL). Default 1k.")
    ap.add_argument("--lock", default=None, help="QHTLC lock hex (test override; default from the lot file)")
    ap.add_argument("--descriptor", default=None, help="QHTLC descriptor hex (test override; default from the lot file)")
    ap.add_argument("--funding-txid", default=None, help="Funding txid, display order (test override; default from the lot file)")
    ap.add_argument("--locked-swords", type=int, default=None, help="Locked amount in swords (test override; default from the lot file)")
    args = ap.parse_args()
    lot = load_lot(args.lot)
    lock_hex = args.lock or lot["lock"]
    desc_hex = args.descriptor or lot["descriptor"]
    funding_txid = args.funding_txid or lot["funding_txid"]
    locked_swords = args.locked_swords if args.locked_swords is not None else lot["locked_swords"]
    secret_hash_hex = lot["secret_hash"]
    print(f"Lot: {lot['label']} (--lot {lot['lot']}), {lot['locked_excal']} EXCAL locked")

    from txscript import (ser_tx, parse_tx, validate_tx, sighash_all,
                          sign_qhtlc_claim, parse_qhtlc_descriptor,
                          lock_qhtlc_for_descriptor)
    from trifold_lockbox import TrifoldKey
    from txpq import trifold_verify

    try:
        secret = bytes.fromhex(args.secret)
        if len(secret) != 32: raise ValueError
    except Exception:
        sys.exit("--secret must be 32 bytes hex")
    if hashlib.sha256(secret).digest().hex() != secret_hash_hex and args.descriptor is None:
        sys.exit("secret does not hash to the published secret hash — wrong secret")
    try:
        seed = bytes.fromhex(args.claim_seed)
    except Exception:
        sys.exit("--claim-seed must be hex")

    lock = bytes.fromhex(lock_hex)
    desc = bytes.fromhex(desc_hex)
    if lock_qhtlc_for_descriptor(desc) != lock:
        sys.exit("descriptor does not match the lock")
    d = parse_qhtlc_descriptor(desc)

    # Find the Trifold tree height whose root matches the descriptor's claim root.
    key = None
    for height in range(1, 11):
        k = TrifoldKey(seed, height=height)
        if k.root == d["claim_root"]:
            key = k
            print(f"claim tree height: {height} (root matches)")
            break
    if key is None:
        sys.exit("claim seed does not reproduce the claim root at any height 1..10")

    dest = dest_script(args.destination)
    prev_wire = bytes.fromhex(funding_txid)[::-1]
    claim_tx = {"version": 1,
                "vin": [{"prev": prev_wire, "idx": 0, "script": b"", "seq": 0xFFFFFFFF}],
                "vout": [{"value": locked_swords - args.fee, "script": dest}],
                "locktime": 0}
    claim_tx["vin"][0]["script"] = sign_qhtlc_claim(claim_tx, 0, lock, key, secret, desc)
    raw = ser_tx(claim_tx)
    txid_disp = hashlib.sha256(hashlib.sha256(raw).digest()).digest()[::-1].hex()

    # Local verification: witness parses, Trifold sig verifies, fork validation passes.
    from txscript import parse_qhtlc_witness
    mode, root, tsig, sec, _desc = parse_qhtlc_witness(claim_tx["vin"][0]["script"])
    assert mode == 1 and root == d["claim_root"] and sec == secret, "witness mismatch"
    h = sighash_all(claim_tx, 0, lock)
    assert trifold_verify(root, h, tsig), "Trifold signature does not verify"
    utxo = {(prev_wire, 0): [(locked_swords, lock, False, 0)]}
    ok, reason, vfee = validate_tx(raw, utxo, args.fork_tip)
    if not ok:
        sys.exit(f"LOCAL VALIDATION FAILED: {reason}")
    print(f"LOCAL VALIDATION PASSED (fee {vfee} swords)")
    print("signed claim tx hex:")
    print(raw.hex())
    print("claim txid:", txid_disp)
    issue = lot.get("issue")
    issue_txt = f"GitHub issue #{issue} (Holedozer1229/excalibur-chain)" if issue else \
        "the GitHub issue for this lot (Holedozer1229/excalibur-chain)"
    print()
    print("NEXT (no message needed): post the signed hex above as a comment on")
    print(issue_txt + ". The fork node picks")
    print(f"it up, broadcasts it, and mines it into the next block — the {lot['locked_excal']:,}")
    print("EXCAL then lands at your destination address.")

if __name__ == "__main__":
    main()
