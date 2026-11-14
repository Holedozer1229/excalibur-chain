"""Spent-leaf registry for quantum-safe (Trifold / PQH) spends.

The hole this closes: a one-time leaf is safe only if it is used once.
A wallet counter alone does not close it — restoring an old wallet
backup resets the counter, and a second wallet holding the same seed
never saw the first spend at all. The chain itself is therefore the
authority: a (root, index) pair that appears in a confirmed block is
spent, everywhere, forever, no matter which wallet copy signs next.

Design, in one paragraph:
- The registry is a set of (root, index) pairs, keyed by root hex +
  index, with a first-spend reference (txid, height) for every entry.
- It lives in the chain data directory, NOT in any wallet file, so
  restoring a wallet backup never resets it. ChainState rebuilds it
  from the confirmed chain on load and updates it on every new best
  block, so the file on disk is a cache of the chain, not a second
  source of truth that can drift from it.
- The wallet checks it BEFORE producing a signature and records the
  pair BEFORE the signature is returned, so a crash between signing
  and recording cannot reuse a leaf. A refused pair is never silently
  skipped for the next leaf — refusal is explicit, with the first-spend
  reference, and the caller must decide what to do.
- Validation checks it too: a transaction whose witness reuses a pair
  already spent on the chain, in the mempool, or earlier in the same
  block is rejected, even if it spends a different UTXO — the pair, not
  the UTXO, is the one-time unit.

Pure stdlib. No network. No keys are stored here — roots are public
commitments already revealed by their first spend.
"""
import json
import os

from txpq import decode_witness


def pair_key(root: bytes, index: int) -> str:
    return f"{root.hex()}:{int(index)}"


def extract_pairs(raw_tx: bytes):
    """All (root, index) pairs revealed by a transaction's witnesses.

    Only PQH witnesses decode; PKH (98 bytes), P2PK (66 bytes), OPEN
    (empty) and coinbase scriptSigs do not, and are skipped. A malformed
    witness is skipped here — validation elsewhere rejects it on its
    own grounds; this function never turns a malformed spend into a
    spent pair.
    """
    from txscript import parse_tx
    try:
        t = parse_tx(raw_tx)
    except Exception:
        return []
    pairs = []
    for vin in t["vin"]:
        script = vin["script"]
        if len(script) < 100:  # PQH witnesses are ~25 KB; nothing else is
            continue
        try:
            root, sig = decode_witness(script)
        except Exception:
            # QHTLC witnesses carry a mode byte before the Trifold
            # witness; a leaf spent there is one-time too, and must
            # be recorded by chain rebuilds exactly like a PQH leaf.
            try:
                from txscript import parse_qhtlc_witness
                _mode, root, sig, _secret, _desc = \
                    parse_qhtlc_witness(script)
            except Exception:
                continue
        pairs.append((root, int(sig["index"])))
    return pairs


def extract_pairs_from_txs(txs):
    out = []
    for raw in txs:
        out.extend(extract_pairs(raw))
    return out


class SpentLeafRegistry:
    """Persistent (root, index) -> first-spend reference map."""

    def __init__(self, path):
        self.path = path
        self.entries = {}  # pair_key -> {"txid": hex, "height": int|None}
        self.load()

    def load(self):
        try:
            with open(self.path) as f:
                data = json.load(f)
        except (OSError, ValueError):
            self.entries = {}
            return
        if isinstance(data, dict):
            self.entries = {str(k): v for k, v in data.items()
                            if isinstance(v, dict)}
        else:
            self.entries = {}

    def save(self):
        tmp = self.path + ".tmp"
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(tmp, "w") as f:
            json.dump(self.entries, f, sort_keys=True)
        os.replace(tmp, self.path)

    def is_spent(self, root: bytes, index: int) -> bool:
        return pair_key(root, index) in self.entries

    def first_spend(self, root: bytes, index: int):
        return self.entries.get(pair_key(root, index))

    def record(self, root: bytes, index: int, txid=None, height=None):
        """Record a pair. Raises RuntimeError if already spent, with the
        first-spend reference — never overwrites, never silently proceeds."""
        key = pair_key(root, index)
        if key in self.entries:
            first = self.entries[key]
            raise RuntimeError(
                f"spent leaf refused: root={root.hex()} index={index} "
                f"already spent in tx {first.get('txid')} "
                f"at height {first.get('height')}")
        self.entries[key] = {"txid": txid, "height": height}
        self.save()
        return True

    def record_many(self, pairs, txid=None, height=None):
        """Record several pairs atomically as a set: if any is spent,
        none are recorded. Returns the list of recorded pair keys."""
        for root, index in pairs:
            if self.is_spent(root, index):
                first = self.first_spend(root, index)
                raise RuntimeError(
                    f"spent leaf refused: root={root.hex()} index={index} "
                    f"already spent in tx {first.get('txid')} "
                    f"at height {first.get('height')}")
        for root, index in pairs:
            self.entries[pair_key(root, index)] = {"txid": txid,
                                                   "height": height}
        self.save()
        return [pair_key(r, i) for r, i in pairs]

    def replace_with(self, pairs_with_refs):
        """Replace the whole set (chain rebuild / reorg). pairs_with_refs
        is a dict pair_key -> reference. Persists immediately."""
        self.entries = dict(pairs_with_refs)
        self.save()

    def as_set(self):
        """Set of (root_bytes, index) for validation."""
        out = set()
        for key in self.entries:
            try:
                root_hex, idx = key.rsplit(":", 1)
                out.add((bytes.fromhex(root_hex), int(idx)))
            except (ValueError, TypeError):
                continue
        return out

    def __len__(self):
        return len(self.entries)

    def __contains__(self, pair):
        root, index = pair
        return self.is_spent(root, index)


def default_registry_path():
    """Chain-data location for the live fork, independent of any wallet
    file. An explicit path always wins over this default."""
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(here, "chaindata_fork",
                        "spent_pqh_registry.json")


def load_registry(path=None):
    return SpentLeafRegistry(path or default_registry_path())
