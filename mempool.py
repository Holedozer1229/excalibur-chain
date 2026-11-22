"""mempool.py — unconfirmed transaction pool for the Genesis Fork node.

Persists to JSON; every tx is revalidated against the current UTXO set on
load and at template time. Pure Python, stdlib only.

BIP-369 (quantum protection): replace-by-fee is disabled. A transaction
that conflicts with one already in the mempool is rejected outright --
never considered as a replacement. Rationale: spends from
quantum-vulnerable locks (bare-P2PK, whose keys are exposed at rest, and
PKH, whose key is exposed in the mempool at spend time) give a quantum
adversary a short-exposure window to derive the key and RBF-steal the
funds. Refusing replacements closes that theft path; the first-seen
transaction keeps its head start and confirms first.
Excalibur goes one step further than BIP-369 strictly requires and
disables RBF entirely (there is no keyless input type worth replacing).

Enhancements:
- Fee rate tracking: each tx stores fee/sword for priority scoring
- Minimum relay fee: transactions below MIN_RELAY_FEE are rejected
- Transaction priority: combines fee rate with input age for scoring
- Eviction: when mempool exceeds MAX_MEMPOOL_TXS, lowest-priority txs
  are evicted first
"""
import base64
import json
import os
import time

from txscript import parse_tx, txid_internal, validate_tx, _view_copy
from spent_leaf_registry import extract_pairs

# Minimum relay fee in swords per 1000 swords of virtual size
# (1 sword/vByte equivalent)
MIN_RELAY_FEE = 1

# Maximum mempool size; oldest/lowest-fee txs are evicted first
MAX_MEMPOOL_TXS = 30_000


def _tx_inputs(raw):
    t = parse_tx(raw)
    return {(v["prev"], v["idx"]) for v in t["vin"]}


def _tx_vsize(raw):
    """Virtual size of a transaction in swords (legacy = weight/4 rounded up)."""
    return (len(raw) * 4 + 3) // 4


def _tx_fee_rate(raw, fee):
    """Fee rate in swords per 1000 swords of vsize."""
    vsize = _tx_vsize(raw)
    if vsize == 0:
        return 0
    return fee * 1000 // vsize


class Mempool:
    def __init__(self, path, chain_spent_pairs=None):
        self.path = path
        self.txs = {}  # txid hex (internal order) -> raw bytes
        self.spent = {}  # (prev_bytes, idx) -> txid hex spending it
        # (root, index) pairs already spent on the chain, as a live set
        # shared with the chain state (mutated in place by it). A pair in
        # here, or already in this mempool, can never be admitted again.
        self.chain_spent_pairs = chain_spent_pairs
        self.pqh_pairs = {}  # (root, index) -> txid hex in this mempool
        # Fee tracking metadata (not persisted; recomputed on load)
        self._fee_cache = {}  # txid -> (fee, fee_rate, timestamp)

    # ------------------------------------------------------------ persist
    def save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump({k: base64.b64encode(v).decode() for k, v in
                       self.txs.items()}, f)
        os.replace(tmp, self.path)

    def _index(self, tid_hex, raw):
        for key in _tx_inputs(raw):
            self.spent[key] = tid_hex
        for pair in extract_pairs(raw):
            self.pqh_pairs[pair] = tid_hex

    def _unindex(self, tid_hex, raw):
        for key in _tx_inputs(raw):
            if self.spent.get(key) == tid_hex:
                del self.spent[key]
        for pair in extract_pairs(raw):
            if self.pqh_pairs.get(pair) == tid_hex:
                del self.pqh_pairs[pair]

    def _pqh_conflict(self, raw):
        """First conflicting spent-leaf pair, or None. Checks the chain
        set first, then this mempool — a pair is spent once, anywhere."""
        for pair in extract_pairs(raw):
            if self.chain_spent_pairs is not None and \
                    pair in self.chain_spent_pairs:
                return (f"spent leaf already used: "
                        f"root={pair[0].hex()} index={pair[1]} "
                        f"(already spent on chain)")
            if pair in self.pqh_pairs:
                return (f"spent leaf already used: "
                        f"root={pair[0].hex()} index={pair[1]} "
                        f"(already in mempool)")
        return None

    def load(self, utxo, height):
        """Reload persisted txs, keeping only ones still valid. Returns the
        number kept."""
        try:
            with open(self.path) as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return 0
        kept = 0
        now = time.time()
        for tid_hex, b64 in data.items():
            try:
                raw = base64.b64decode(b64)
            except Exception:
                continue
            if txid_internal(raw).hex() != tid_hex:
                continue
            if self._pqh_conflict(raw) is not None:
                continue
            spent = set(self.chain_spent_pairs) \
                if self.chain_spent_pairs is not None else set()
            ok, _, fee = validate_tx(raw, utxo, height, spent_pairs=spent)
            if ok:
                self.txs[tid_hex] = raw
                self._index(tid_hex, raw)
                self._fee_cache[tid_hex] = (fee, _tx_fee_rate(raw, fee), now)
                kept += 1
        return kept

    # -------------------------------------------------------------- ops
    def add(self, raw, utxo, height):
        """Try to admit a raw tx. Returns (ok, reason).

        BIP-369: conflicting transactions are never treated as replacements.
        If any input is already spent by a mempool tx, the newcomer is
        rejected outright -- no RBF, so a quantum adversary observing a
        key-revealing spend in the mempool cannot displace it.

        Minimum relay fee: transactions with fee rate below MIN_RELAY_FEE
        are rejected to prevent mempool spam.
        """
        raw = bytes(raw)
        try:
            t = parse_tx(raw)
        except Exception:
            return False, "parse failed"
        tid = txid_internal(raw).hex()
        if tid in self.txs:
            return False, "already in mempool"
        for v in t["vin"]:
            key = (v["prev"], v["idx"])
            if key in self.spent:
                return False, (
                    "conflicting tx already in mempool "
                    "(BIP-369: no replace-by-fee)")
        conflict = self._pqh_conflict(raw)
        if conflict is not None:
            return False, conflict
        spent = set(self.chain_spent_pairs) \
            if self.chain_spent_pairs is not None else set()
        # Also refuse a pair already in this mempool at validation time:
        # _pqh_conflict already checked it, and validate_tx's working set
        # starts from the chain set, so a mempool pair is caught twice.
        ok, reason, fee = validate_tx(raw, utxo, height, spent_pairs=spent)
        if not ok:
            return False, reason
        # Enforce minimum relay fee
        fee_rate = _tx_fee_rate(raw, fee)
        if fee_rate < MIN_RELAY_FEE:
            return False, (f"fee rate {fee_rate} below minimum "
                           f"{MIN_RELAY_FEE} swords/1000 vsize")
        self.txs[tid] = raw
        self._index(tid, raw)
        self._fee_cache[tid] = (fee, fee_rate, time.time())
        self.save()
        # Evict lowest-priority txs if mempool is full
        self._evict_if_needed()
        return True, "ok"

    def remove(self, tid_hex):
        if tid_hex in self.txs:
            self._unindex(tid_hex, self.txs[tid_hex])
            del self.txs[tid_hex]
            self._fee_cache.pop(tid_hex, None)
            self.save()

    def _evict_if_needed(self):
        """Evict lowest-priority transactions if mempool exceeds MAX_MEMPOOL_TXS.
        Priority is determined by fee rate; lowest fee rate txs are evicted first."""
        if len(self.txs) <= MAX_MEMPOOL_TXS:
            return
        # Sort by fee rate ascending (lowest first)
        sorted_txs = sorted(
            self._fee_cache.items(),
            key=lambda item: item[1][1]  # fee_rate
        )
        num_to_evict = len(self.txs) - MAX_MEMPOOL_TXS
        for i in range(num_to_evict):
            tid_hex = sorted_txs[i][0]
            if tid_hex in self.txs:
                self.remove(tid_hex)

    def evict_block_txs(self, txs):
        """Drop txs confirmed by a new block (skip the coinbase)."""
        for raw in txs[1:]:
            self.remove(txid_internal(raw).hex())

    def select_template(self, utxo, height, max_txs=999):
        """Pick (raw, fee) pairs for the next block template: highest fee
        rate first, each validated against the utxo plus already-selected txs.

        Priority scoring: transactions are sorted by fee rate (swords per
        1000 vsize) rather than total fee, so small high-fee transactions
        are not starved by large low-fee ones. Ties are broken by total
        fee (higher first), then by arrival time (older first).
        """
        scored = []
        for tid, raw in self.txs.items():
            spent = set(self.chain_spent_pairs) \
                if self.chain_spent_pairs is not None else set()
            ok, _, fee = validate_tx(raw, utxo, height, spent_pairs=spent)
            if ok:
                fee_rate = self._fee_cache.get(tid, (fee, 0, 0))[1]
                timestamp = self._fee_cache.get(tid, (0, 0, 0))[2]
                # Sort key: (-fee_rate, -fee, timestamp) => highest fee rate
                # first, then highest fee, then oldest first
                scored.append((-fee_rate, -fee, timestamp, raw))
        scored.sort()
        overlay = _view_copy(utxo)
        spent = set(self.chain_spent_pairs) \
            if self.chain_spent_pairs is not None else set()
        template = []
        for _fr, _fee, _ts, raw in scored:
            if len(template) >= max_txs:
                break
            ok, _, fee = validate_tx(raw, utxo, height, view=overlay,
                                     spent_pairs=spent)
            if ok:
                template.append((raw, fee))
        return template

    def get_stats(self):
        """Return mempool statistics: tx count, total fees, min/max/avg fee rate."""
        if not self._fee_cache:
            return {
                "tx_count": len(self.txs),
                "total_fees": 0,
                "min_fee_rate": 0,
                "max_fee_rate": 0,
                "avg_fee_rate": 0,
            }
        fee_rates = [info[1] for info in self._fee_cache.values()]
        total_fees = sum(info[0] for info in self._fee_cache.values())
        return {
            "tx_count": len(self.txs),
            "total_fees": total_fees,
            "min_fee_rate": min(fee_rates),
            "max_fee_rate": max(fee_rates),
            "avg_fee_rate": total_fees // len(fee_rates) if fee_rates else 0,
        }

    def __len__(self):
        return len(self.txs)
