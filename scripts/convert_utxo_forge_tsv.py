#!/usr/bin/env python3
"""Convert a UTXO Forge TSV export into EXCAL snapshot-v2.

This is a format adapter, not a proof that the source export is complete or
correct. Always retain and independently verify the publisher manifest.
"""
import argparse
import csv
import hashlib
import json
import os
import struct
import sys
import tempfile

HEIGHT = 968698
MAGIC = 0x45425346
MAX_MONEY = 21_000_000 * 100_000_000
FIELDS = ["txid", "vout", "value_sats", "height", "coinbase",
          "script_type", "address", "script_pub_key"]


def varint(n):
    if n < 0xfd:
        return bytes([n])
    if n <= 0xffff:
        return b"\xfd" + struct.pack("<H", n)
    if n <= 0xffffffff:
        return b"\xfe" + struct.pack("<I", n)
    return b"\xff" + struct.pack("<Q", n)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input", help="decompressed TSV path, or '-' for stdin")
    ap.add_argument("output", help="destination snapshot-v2 file")
    ap.add_argument("--height", type=int, required=True,
                    help="source snapshot height; must be 968698")
    ap.add_argument("--block-hash", required=True,
                    help="source block hash from the publisher manifest")
    ap.add_argument("--manifest", required=True,
                    help="saved publisher JSON manifest; must identify this height/hash")
    args = ap.parse_args()

    if args.height != HEIGHT:
        ap.error(f"EXCAL anchor is {HEIGHT}; refusing height {args.height}")
    block_hash = args.block_hash.lower()
    if len(block_hash) != 64 or any(c not in "0123456789abcdef" for c in block_hash):
        ap.error("--block-hash must be 32-byte hex")

    with open(args.manifest, encoding="utf-8") as mf:
        manifest = json.load(mf)
    # Accept common manifest key spellings, but require both binding values.
    mh = manifest.get("height", manifest.get("block_height"))
    mb = manifest.get("block_hash", manifest.get("bestblock"))
    if int(mh) != HEIGHT or str(mb).lower() != block_hash:
        ap.error("manifest height/block_hash does not match the requested anchor")
    expected_rows = manifest.get("row_count", manifest.get("utxo_count"))
    expected_sha = manifest.get("sha256", manifest.get("file_sha256"))
    if expected_rows is None or expected_sha is None:
        ap.error("manifest must include row_count/utxo_count and sha256/file_sha256")
    if args.input == "-":
        ap.error("input must be a saved decompressed TSV file so its bytes can be hashed")

    source_sha = sha256_file(args.input)
    if source_sha.lower() != str(expected_sha).lower():
        ap.error(f"source SHA-256 mismatch: got {source_sha}, manifest says {expected_sha}")

    tmp = args.output + ".partial"
    count = 0
    seen = set()
    total = 0
    try:
        with open(args.input, newline="", encoding="utf-8") as src, open(tmp, "wb") as dst:
            reader = csv.DictReader(src, delimiter="\t")
            if reader.fieldnames != FIELDS:
                raise ValueError(f"unexpected TSV header: {reader.fieldnames!r}")
            dst.write(struct.pack("<IIIQ", MAGIC, 2, HEIGHT, int(expected_rows)))
            for line, row in enumerate(reader, start=2):
                txid = row["txid"].strip().lower()
                if len(txid) != 64 or any(c not in "0123456789abcdef" for c in txid):
                    raise ValueError(f"line {line}: invalid txid")
                # TSV txids use display byte order; snapshot stores internal byte order.
                txid_raw = bytes.fromhex(txid)[::-1]
                vout = int(row["vout"])
                value = int(row["value_sats"])
                created = int(row["height"])
                coinbase = int(row["coinbase"])
                script_hex = row["script_pub_key"].strip()
                if len(script_hex) % 2 or any(c not in "0123456789abcdefABCDEF" for c in script_hex):
                    raise ValueError(f"line {line}: invalid script_pub_key hex")
                script = bytes.fromhex(script_hex)
                if not (0 <= vout <= 0xffffffff):
                    raise ValueError(f"line {line}: vout out of range")
                if not (0 <= value <= MAX_MONEY):
                    raise ValueError(f"line {line}: value out of range")
                if not (0 <= created <= HEIGHT):
                    raise ValueError(f"line {line}: creation height outside snapshot")
                if coinbase not in (0, 1):
                    raise ValueError(f"line {line}: coinbase must be 0 or 1")
                if not coinbase and created == 0:
                    # Height zero is valid for ordinary outputs; this check is intentionally absent.
                    pass
                if coinbase and created > HEIGHT:
                    raise ValueError(f"line {line}: coinbase created after snapshot")
                key = (txid_raw, vout)
                if key in seen:
                    raise ValueError(f"line {line}: duplicate outpoint")
                seen.add(key)
                # Core UTXO snapshots contain only outputs retained as unspent;
                # this adapter marks them present. Script spendability is not
                # inferred from an address or script_type field.
                dst.write(txid_raw)
                dst.write(struct.pack("<IQ", vout, value))
                dst.write(varint(len(script)))
                dst.write(script)
                dst.write(bytes([1, coinbase]))
                dst.write(struct.pack("<I", created if coinbase else 0))
                count += 1
                total += value
            if count != int(expected_rows):
                raise ValueError(f"row count mismatch: parsed={count}, manifest={expected_rows}")
            dst.flush()
            os.fsync(dst.fileno())
        os.replace(tmp, args.output)
    except Exception:
        try:
            os.remove(tmp)
        except FileNotFoundError:
            pass
        raise

    print(json.dumps({
        "format": "fork-snapshot-v2",
        "height": HEIGHT,
        "block_hash": block_hash,
        "source_sha256": source_sha,
        "record_count": count,
        "total_sats": total,
        "snapshot_sha256d": hashlib.sha256(
            hashlib.sha256(open(args.output, "rb").read()).digest()).hexdigest(),
        "warning": "Conversion and file hashes do not prove UTXO completeness or MuHash equality."
    }, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(2)
