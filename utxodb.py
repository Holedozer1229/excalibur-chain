"""Two-tier UTXO storage for EXCAL's inherited Bitcoin snapshot.

Snapshot format v2 is deliberately fail-closed. Each record contains:
  txid[32] || vout[u32le] || value[u64le] || script[varbytes]
  || flags[u8] || coinbase_height[u32le]

flags bit 0 = spendable; bit 1 = created by a coinbase transaction.
All other flag bits are reserved and rejected. Non-coinbase records must
carry coinbase_height=0. A v1 snapshot cannot safely be imported because it
does not encode coinbase provenance.
"""
import os
import sqlite3
import tempfile

MAGIC = 0x45425346
SNAPSHOT_VERSION = 2
MAX_MONEY = 21_000_000 * 100_000_000
SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS utxo(
    txid BLOB NOT NULL,
    vout INTEGER NOT NULL,
    value INTEGER NOT NULL,
    spk BLOB NOT NULL,
    is_cb INTEGER NOT NULL,
    cb_h INTEGER NOT NULL,
    spendable INTEGER NOT NULL,
    PRIMARY KEY (txid, vout)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS idx_spk ON utxo(spk);
"""


class SnapshotDB:
    """Read-only handle on the imported Bitcoin UTXO snapshot."""

    def __init__(self, path):
        if not os.path.exists(path):
            raise FileNotFoundError(f"snapshot DB missing: {path}")
        self.path = path
        self._db = sqlite3.connect(
            f"file:{path}?mode=ro", uri=True, check_same_thread=False)
        self._db.execute("PRAGMA query_only=ON")

    def close(self):
        self._db.close()

    def get_any(self, key):
        """Return a record regardless of spendability (for collision checks)."""
        txid_b, vout = key
        row = self._db.execute(
            "SELECT value, spk, is_cb, cb_h, spendable FROM utxo "
            "WHERE txid=? AND vout=?", (txid_b, vout)).fetchone()
        if row is None:
            return None
        return (row[0], bytes(row[1]), row[2], row[3], row[4])

    def get(self, key):
        """Spendable entry in legacy four-tuple form, or None."""
        row = self.get_any(key)
        if row is None or not row[4]:
            return None
        return [(row[0], row[1], row[2], row[3])]

    def contains_any(self, key):
        txid_b, vout = key
        return self._db.execute(
            "SELECT 1 FROM utxo WHERE txid=? AND vout=?",
            (txid_b, vout)).fetchone() is not None

    def get_meta(self, k):
        row = self._db.execute("SELECT v FROM meta WHERE k=?", (k,)).fetchone()
        return row[0] if row else None

    def stats(self):
        """Count/value of spendable snapshot outputs."""
        return self.count_spendable()

    def stats_all(self):
        """Count/value of all imported outputs, including non-spendable ones."""
        return self._db.execute(
            "SELECT COUNT(*), COALESCE(SUM(value),0) FROM utxo").fetchone()

    def count_spendable(self):
        return self._db.execute(
            "SELECT COUNT(*), COALESCE(SUM(value),0) FROM utxo "
            "WHERE spendable=1").fetchone()

    def find_by_spk(self, spk):
        """Spendable snapshot outputs paying to lock script spk."""
        out = []
        for txid_b, vout, value, is_cb, cb_h in self._db.execute(
                "SELECT txid, vout, value, is_cb, cb_h FROM utxo "
                "WHERE spk=? AND spendable=1", (bytes(spk),)):
            out.append(((bytes(txid_b), vout),
                        (value, bytes(spk), is_cb, cb_h)))
        return out


def build_snapshot_db(dat_path, db_path, snapshot_hash_hex, height,
                      log=print):
    """Build a v2 SQLite snapshot, atomically replacing db_path on success."""
    digest = _sha256d_file(dat_path)
    if digest.lower() != snapshot_hash_hex.lower():
        raise ValueError(
            f"snapshot hash mismatch: file={digest} expected={snapshot_hash_hex}")

    target_dir = os.path.dirname(os.path.abspath(db_path))
    os.makedirs(target_dir, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=".utxo-snapshot-", suffix=".db",
                                    dir=target_dir)
    os.close(fd)
    db = None
    try:
        db = sqlite3.connect(tmp_path)
        db.executescript("PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF;")
        db.executescript(SCHEMA)
        n = _load_dat_into_db(db, dat_path, expected_height=int(height),
                              log=log)
        db.execute("INSERT INTO meta(k,v) VALUES "
                   "('snapshot_hash',?),('height',?),('format',?)",
                   (digest, str(height), "fork-snapshot-v2"))
        db.commit()
        db.execute("PRAGMA journal_mode=DELETE")
        db.execute("PRAGMA synchronous=FULL")
        db.commit()
        cnt, total = db.execute(
            "SELECT COUNT(*), COALESCE(SUM(value),0) FROM utxo").fetchone()
        assert cnt == n, (cnt, n)
        db.close()
        db = None
        os.replace(tmp_path, db_path)
        log(f"snapshot DB built: {cnt} outputs, {total/1e8:.2f} EXCAL -> {db_path}")
        return cnt, total
    except Exception:
        if db is not None:
            db.close()
        try:
            os.unlink(tmp_path)
        except FileNotFoundError:
            pass
        raise


def _sha256d_file(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return hashlib.sha256(h.digest()).hexdigest()


def _read_exact(f, size, field):
    data = f.read(size)
    if len(data) != size:
        raise ValueError(f"truncated snapshot while reading {field}")
    return data


def _read_varint(f):
    first = _read_exact(f, 1, "script length")[0]
    if first < 0xfd:
        return first
    if first == 0xfd:
        n = int.from_bytes(_read_exact(f, 2, "varint16"), "little")
        if n < 0xfd:
            raise ValueError("non-canonical varint16")
        return n
    if first == 0xfe:
        n = int.from_bytes(_read_exact(f, 4, "varint32"), "little")
        if n <= 0xffff:
            raise ValueError("non-canonical varint32")
        return n
    n = int.from_bytes(_read_exact(f, 8, "varint64"), "little")
    if n <= 0xffffffff:
        raise ValueError("non-canonical varint64")
    return n


def _load_dat_into_db(db, dat_path, expected_height, log):
    """Import only canonical v2 records with complete coinbase provenance."""
    import struct
    n = 0
    batch = []
    with open(dat_path, "rb") as f:
        magic = struct.unpack("<I", _read_exact(f, 4, "magic"))[0]
        if magic != MAGIC:
            raise ValueError(f"bad snapshot magic {magic:#x}")
        version = struct.unpack("<I", _read_exact(f, 4, "version"))[0]
        if version != SNAPSHOT_VERSION:
            raise ValueError(
                f"unsupported snapshot version {version}; v2 required "
                "(v1 omits coinbase provenance)")
        file_height = struct.unpack(
            "<I", _read_exact(f, 4, "height"))[0]
        if file_height != expected_height:
            raise ValueError(
                f"snapshot height mismatch: file={file_height} "
                f"metadata={expected_height}")
        count = struct.unpack("<Q", _read_exact(f, 8, "count"))[0]
        log(f"snapshot v{version} height={file_height} count={count}")

        for _ in range(count):
            txid_b = _read_exact(f, 32, "txid")
            vout = struct.unpack("<I", _read_exact(f, 4, "vout"))[0]
            value = struct.unpack("<Q", _read_exact(f, 8, "value"))[0]
            if value > MAX_MONEY:
                raise ValueError(f"output value exceeds Bitcoin MAX_MONEY: {value}")
            script_len = _read_varint(f)
            script = _read_exact(f, script_len, "scriptPubKey")
            flags = _read_exact(f, 1, "flags")[0]
            if flags & ~0x03:
                raise ValueError(f"reserved snapshot flags set: {flags:#x}")
            spendable = flags & 0x01
            is_coinbase = (flags >> 1) & 0x01
            cb_height = struct.unpack(
                "<I", _read_exact(f, 4, "coinbase height"))[0]
            if not is_coinbase and cb_height != 0:
                raise ValueError("non-coinbase record has nonzero coinbase height")
            if is_coinbase and cb_height > file_height:
                raise ValueError("coinbase height is above snapshot height")
            batch.append((txid_b, vout, value, script, is_coinbase,
                          cb_height, spendable))
            n += 1
            if len(batch) >= 50_000:
                db.executemany(
                    "INSERT INTO utxo(txid,vout,value,spk,is_cb,cb_h,spendable) "
                    "VALUES (?,?,?,?,?,?,?)", batch)
                batch = []
                if n % 1_000_000 == 0:
                    log(f"  ... {n//1_000_000}M / {count//1_000_000}M")
        if batch:
            db.executemany(
                "INSERT INTO utxo(txid,vout,value,spk,is_cb,cb_h,spendable) "
                "VALUES (?,?,?,?,?,?,?)", batch)
        if f.read(1):
            raise ValueError("trailing bytes after declared snapshot records")
    if n != count:
        raise ValueError(f"snapshot record count mismatch: parsed={n} header={count}")
    return n


class UtxoSet:
    """Dict-compatible overlay plus tombstones over an immutable SnapshotDB."""

    def __init__(self, snapshot=None, overlay=None, spent=None):
        self.snapshot = snapshot
        self.overlay = overlay if overlay is not None else {}
        self.spent = spent if spent is not None else set()

    def _snapshot_contains_any(self, key):
        return (self.snapshot is not None
                and self.snapshot.contains_any(key))

    def get(self, key, default=None):
        if key in self.spent:
            return default
        if key in self.overlay:
            return self.overlay[key]
        if self.snapshot is not None:
            r = self.snapshot.get(key)
            if r is not None:
                return r
        return default

    def __getitem__(self, key):
        r = self.get(key)
        if r is None:
            raise KeyError(key)
        return r

    def __setitem__(self, key, entries):
        if self._snapshot_contains_any(key):
            raise AssertionError("re-creating an existing snapshot outpoint")
        if key in self.overlay:
            raise AssertionError("overwriting an existing overlay outpoint")
        self.overlay[key] = list(entries)
        self.spent.discard(key)

    def __delitem__(self, key):
        if key in self.overlay:
            del self.overlay[key]
            return
        if key in self.spent:
            raise KeyError(key)
        if self.snapshot is not None and self.snapshot.get(key) is not None:
            self.spent.add(key)
            return
        raise KeyError(key)

    def setdefault(self, key, default):
        if key in self.spent:
            raise AssertionError("re-creating a spent snapshot output")
        if key in self.overlay or self._snapshot_contains_any(key):
            raise AssertionError("duplicate output creation")
        self.overlay[key] = default
        return default

    def __contains__(self, key):
        return self.get(key) is not None

    def copy(self):
        return UtxoSet(self.snapshot,
                       {k: list(v) for k, v in self.overlay.items()},
                       set(self.spent))

    def stats(self):
        n = total = 0
        if self.snapshot is not None:
            n, total = self.snapshot.stats()
            for key in self.spent:
                e = self.snapshot.get(key)
                if e:
                    n -= 1
                    total -= e[0][0]
        for entries in self.overlay.values():
            for value, _s, _c, _h in entries:
                n += 1
                total += value
        return n, total

    def find_by_spk(self, spk):
        out = []
        if self.snapshot is not None:
            for key, entry in self.snapshot.find_by_spk(bytes(spk)):
                if key not in self.spent:
                    out.append((key, entry))
        for key, entries in self.overlay.items():
            for entry in entries:
                if entry[1] == bytes(spk):
                    out.append((key, entry))
        return out

    def items(self):
        if self.snapshot is not None:
            db = self.snapshot._db
            for txid_b, vout, value, spk, is_cb, cb_h in db.execute(
                    "SELECT txid, vout, value, spk, is_cb, cb_h "
                    "FROM utxo WHERE spendable=1"):
                key = (bytes(txid_b), vout)
                if key not in self.spent and key not in self.overlay:
                    yield key, [(value, bytes(spk), is_cb, cb_h)]
        for key, entries in self.overlay.items():
            yield key, entries

    def values(self):
        for _key, entries in self.items():
            yield entries
