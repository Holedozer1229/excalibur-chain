"""utxo_index.py — persistent per-height UTXO index for the EXCAL fork.

The index is a per-block delta log: for every canonical block height it
records exactly which UTXO rows the block spent and which it created.
Applying the deltas forward from the empty set (or undoing them backward
from the tip) reproduces the UTXO set at ANY height without replaying the
chain's transactions from genesis.

Format (all integers little-endian, deterministic, stdlib only):

  deltas.bin:
    magic      8 bytes  b"EXUTXO01"
    version    u32      1
    count      u64      number of block records (== tip height + 1)
    per block record:
      height     u32
      n_spent    u32
      n_created  u32
      n_spent spent entries, then n_created created entries; each entry:
        txid     32 bytes (internal byte order)
        vout     u32
        value    u64 (swords)
        spk_len  u16
        spk      spk_len bytes
        is_cb    u8 (0/1)
        cb_h     u32
  manifest.json: {"format": 1, "tip_height": int, "tip_hash": hex,
                  "blocks": int, "sha256": hex-of-deltas.bin,
                  "spent_total": int, "created_total": int}

The on-disk file is a CACHE, never the authority: ChainState always
derives the in-memory deltas from the replayed chain and verifies the
disk copy against them (manifest tip hash + sha256 + full equality).
A missing, corrupt, or stale file is rebuilt from the replay; deleting
the utxo_index/ directory forces a rebuild. Never edit the files by hand.
"""
import hashlib
import json
import os
import struct

MAGIC = b"EXUTXO01"
VERSION = 1
HEADER = struct.Struct("<8sIQ")
BLOCK_HDR = struct.Struct("<III")
ENTRY_HDR = struct.Struct("<32sIQH")
ENTRY_TAIL = struct.Struct("<BI")

# A delta entry: ((txid_bytes, vout), (value, spk_bytes, is_cb, cb_h)).
# A block delta: (height, spent_tuple, created_tuple) with spent/created
# tuples of delta entries in application order.


def _pack_entry(entry):
    (txid_b, vout), (value, spk, is_cb, cb_h) = entry
    return (ENTRY_HDR.pack(bytes(txid_b), int(vout), int(value), len(spk))
            + bytes(spk) + ENTRY_TAIL.pack(1 if is_cb else 0, int(cb_h)))


def _read_entry(buf, pos):
    if pos + ENTRY_HDR.size > len(buf):
        raise ValueError("truncated UTXO index entry header")
    (txid_b, vout, value, spk_len), = [ENTRY_HDR.unpack_from(buf, pos)]
    pos += ENTRY_HDR.size
    if pos + spk_len + ENTRY_TAIL.size > len(buf):
        raise ValueError("truncated UTXO index entry")
    spk = bytes(buf[pos:pos + spk_len])
    pos += spk_len
    is_cb, cb_h = ENTRY_TAIL.unpack_from(buf, pos)
    pos += ENTRY_TAIL.size
    return ((bytes(txid_b), int(vout)),
            (int(value), spk, bool(is_cb), int(cb_h))), pos


def serialize_deltas(deltas):
    """deltas: sequence of (height, spent, created) -> bytes."""
    out = bytearray()
    out += HEADER.pack(MAGIC, VERSION, len(deltas))
    for height, spent, created in deltas:
        out += BLOCK_HDR.pack(int(height), len(spent), len(created))
        for e in spent:
            out += _pack_entry(e)
        for e in created:
            out += _pack_entry(e)
    return bytes(out)


def parse_deltas(raw):
    """bytes -> [(height, spent_tuple, created_tuple)]. Raises ValueError
    on any structural problem (bad magic/version, truncation, trailing
    bytes, non-sequential heights)."""
    if len(raw) < HEADER.size:
        raise ValueError("UTXO index too short")
    magic, version, count = HEADER.unpack_from(raw, 0)
    if magic != MAGIC:
        raise ValueError("UTXO index bad magic")
    if version != VERSION:
        raise ValueError(f"UTXO index unsupported version {version}")
    pos = HEADER.size
    out = []
    for _ in range(count):
        if pos + BLOCK_HDR.size > len(raw):
            raise ValueError("UTXO index truncated block header")
        height, n_spent, n_created = BLOCK_HDR.unpack_from(raw, pos)
        pos += BLOCK_HDR.size
        if out and height != out[-1][0] + 1:
            raise ValueError("UTXO index heights not sequential")
        if not out and height != 0:
            raise ValueError("UTXO index must start at height 0")
        spent = []
        for _ in range(n_spent):
            entry, pos = _read_entry(raw, pos)
            spent.append(entry)
        created = []
        for _ in range(n_created):
            entry, pos = _read_entry(raw, pos)
            created.append(entry)
        out.append((height, tuple(spent), tuple(created)))
    if pos != len(raw):
        raise ValueError("UTXO index has trailing bytes")
    return out


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def index_paths(data_dir):
    d = os.path.join(data_dir, "utxo_index")
    return {"dir": d,
            "deltas": os.path.join(d, "deltas.bin"),
            "manifest": os.path.join(d, "manifest.json")}


def write_index(data_dir, deltas, tip_height, tip_hash):
    """Atomically write deltas.bin + manifest.json for `deltas`.
    Returns the manifest dict. Raises OSError on I/O failure (callers
    treat the on-disk index as a best-effort cache)."""
    paths = index_paths(data_dir)
    os.makedirs(paths["dir"], exist_ok=True)
    raw = serialize_deltas(deltas)
    tmp = paths["deltas"] + ".tmp"
    with open(tmp, "wb") as f:
        f.write(raw)
    os.replace(tmp, paths["deltas"])
    manifest = {
        "format": VERSION,
        "tip_height": int(tip_height),
        "tip_hash": bytes(tip_hash).hex(),
        "blocks": len(deltas),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "spent_total": sum(len(s) for _h, s, _c in deltas),
        "created_total": sum(len(c) for _h, _s, c in deltas),
    }
    tmp_m = paths["manifest"] + ".tmp"
    with open(tmp_m, "w", encoding="utf-8") as f:
        f.write(json.dumps(manifest, sort_keys=True) + "\n")
    os.replace(tmp_m, paths["manifest"])
    return manifest


def read_index(data_dir, tip_height, tip_hash):
    """Load and fully verify the persisted delta log for the given tip.
    Returns [(height, spent, created)] or None when absent/stale/corrupt
    (callers fall back to deriving deltas from the chain replay)."""
    paths = index_paths(data_dir)
    try:
        with open(paths["manifest"], encoding="utf-8") as f:
            manifest = json.load(f)
    except (OSError, ValueError):
        return None
    if manifest.get("format") != VERSION:
        return None
    if manifest.get("tip_height") != int(tip_height):
        return None
    if manifest.get("tip_hash") != bytes(tip_hash).hex():
        return None
    if manifest.get("blocks") != int(tip_height) + 1:
        return None
    try:
        digest = _sha256_file(paths["deltas"])
    except OSError:
        return None
    if digest != manifest.get("sha256"):
        return None
    try:
        with open(paths["deltas"], "rb") as f:
            raw = f.read()
        deltas = parse_deltas(raw)
    except (OSError, ValueError):
        return None
    if len(deltas) != int(tip_height) + 1:
        return None
    return deltas
