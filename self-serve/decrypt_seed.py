#!/usr/bin/env python3
"""decrypt_seed.py — decrypt the published claim seed (taker side).

The swap watcher publishes the EXCAL claim seed encrypted to the taker's
delivery pubkey (see taker_htlc.py). Only the taker holds the delivery
private key, so only the taker can decrypt it. No message to Lux needed.

Requires: pip install cryptography
Usage:
  python3 decrypt_seed.py --ciphertext claim-seeds/<funding_txid>.json \\
      --delivery-key delivery_key.txt
Writes the claim seed hex to claim_seed.txt (0600) and prints it once.
"""
import argparse, json, os, sys

def main():
    ap = argparse.ArgumentParser(description="Decrypt the published claim seed with the delivery private key.")
    ap.add_argument("--ciphertext", required=True, help="Ciphertext JSON published by the swap watcher")
    ap.add_argument("--delivery-key", required=True, help="delivery_key.txt from taker_htlc.py (hex, 32 bytes)")
    args = ap.parse_args()
    try:
        from cryptography.hazmat.primitives.asymmetric.ec import SECP256K1, EllipticCurvePrivateKey, EllipticCurvePublicKey
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError:
        sys.exit("need the cryptography package: pip install cryptography")
    with open(args.ciphertext) as f:
        ct = json.load(f)
    with open(args.delivery_key) as f:
        priv_hex = f.read().strip()
    priv_int = int(priv_hex, 16)
    priv = ec.derive_private_key(priv_int, SECP256K1())
    eph_pub = EllipticCurvePublicKey.from_encoded_point(
        SECP256K1(), bytes.fromhex(ct["ephemeral_pubkey"]))
    shared = priv.exchange(ec.ECDH(), eph_pub)
    import hashlib
    key = hashlib.sha256(shared).digest()
    seed = AESGCM(key).decrypt(bytes.fromhex(ct["nonce"]), bytes.fromhex(ct["ciphertext"]), None)
    print("claim seed hex:", seed.hex())
    with open("claim_seed.txt", "w") as f:
        f.write(seed.hex() + "\n")
    os.chmod("claim_seed.txt", 0o600)
    print("saved to claim_seed.txt (0600). Keep it private until you have claimed.")

if __name__ == "__main__":
    main()
