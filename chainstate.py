"""chainstate.py — Excalibur fork chain state with UTXO overlay.

Loads chain.jsonl from a chaindata directory, replays all blocks to build
the live UTXO set, and exposes the interface the light ledger needs:
  cs = ChainState(chaindata_path, net='fork')
  cs.load()
  tip = cs.tips[0]          # {height, hash, work, ...}
  overlay = cs.utxo          # {(txid_bytes, vout): [(value, spk, is_cb, cb_h)]}

The overlay covers fork-created UTXOs only. Bitcoin-snapshot base outputs
(spent tombstones) are phase 2 — when available, cs.utxo becomes a UtxoSet
with .overlay and .spent attributes.

Supports bootstrapping from a light-ledger snapshot via load_from_snapshot(),
skipping full replay when a trusted checkpoint is available.
"""

import json
import os
import struct

import genesis_fork as gf
from genesis_fork import sha256d, ser_header, bits_to_target, subsidy
from txscript import parse_tx, txid_internal

_HERE = os.path.dirname(os.path.abspath(__file__))


class UtxoSet:
    """UTXO set with separate overlay and spent-tombstone views.

    Used when the Bitcoin snapshot base is available. When only fork blocks
    are loaded, ChainState exposes a plain dict as .utxo instead."""

    def __init__(self):
        self.overlay = {}  # {(txid_bytes, vout): [(value, spk, is_cb, cb_h)]}
        self.spent = set()  # {(txid_bytes, vout)} tombstones


class ChainState:
    """In-memory chain state loaded from chaindata_fork/chain.jsonl."""

    def __init__(self, chaindata_path, net="fork"):
        self.chaindata_path = chaindata_path
        self.net = net
        gf.use_network(net)
        self.chain_file = os.path.join(chaindata_path, "chain.jsonl")
        self.records = {}       # {hash_str: record}
        self.by_height = {}     # {height: record}
        self.tips = []          # [tip_record, ...]
        self.utxo = None        # dict or UtxoSet after load()
        self._loaded = False

    def load(self):
        """Load chain.jsonl and replay all blocks to build the UTXO overlay."""
        print(f"Loading chain from {self.chain_file} ...", flush=True)
        records = {}
        by_height = {}
        with open(self.chain_file, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                h = rec["hash"]
                records[h] = rec
                by_height[rec["height"]] = rec

        # Find tip(s) — highest height record(s)
        if not by_height:
            self.tips = []
            self.utxo = {}
            self._loaded = True
            print("Empty chain, nothing to load.", flush=True)
            return

        max_h = max(by_height.keys())
        self.tips = [by_height[max_h]]
        self.records = records
        self.by_height = by_height

        # Replay all blocks in height order to build UTXO overlay
        overlay = {}  # {(txid_bytes, vout): [(value, spk, is_cb, cb_h)]}
        spent_outpoints = set()  # track which outputs have been spent

        for height in sorted(by_height.keys()):
            rec = by_height[height]
            txs_hex = rec.get("txs", [])
            for ti, tx_hex in enumerate(txs_hex):
                if isinstance(tx_hex, str):
                    tx_bytes = bytes.fromhex(tx_hex)
                else:
                    tx_bytes = tx_hex

                txid = txid_internal(tx_bytes)
                tx = parse_tx(tx_bytes)
                is_coinbase = ti == 0 and len(tx["vin"]) == 1 and \
                              tx["vin"][0]["prev"] == b"\x00" * 32

                # Process inputs — mark referenced outputs as spent
                for vin in tx["vin"]:
                    prev_txid = vin["prev"]
                    prev_vout = vin["idx"]
                    key = (prev_txid, prev_vout)
                    if key in overlay:
                        del overlay[key]
                    spent_outpoints.add(key)

                # Process outputs — add to overlay
                for j, vout in enumerate(tx["vout"]):
                    key = (txid, j)
                    entry = (vout["value"], vout["script"],
                             is_coinbase, height if is_coinbase else 0)
                    overlay[key] = [entry]

        # Check for Bitcoin snapshot base files (phase 2)
        snapshot_dir = os.path.join(self.chaindata_path, "snapshot_968698.json")
        if os.path.exists(snapshot_dir):
            # Full UtxoSet with spent tombstones
            utxo_set = UtxoSet()
            utxo_set.overlay = overlay
            # Load spent tombstones from snapshot base when available
            self.utxo = utxo_set
        else:
            # Plain dict — fork-only overlay
            self.utxo = overlay

        tip = self.tips[0]
        tip_work = self._compute_chainwork(tip["height"])
        tip["work"] = tip_work
        self._loaded = True
        print(f"Loaded {len(records)} blocks, tip height {tip['height']} "
              f"({tip['hash'][:16]}...), {len(overlay)} UTXOs, "
              f"chainwork {tip_work}", flush=True)

    def _compute_chainwork(self, height):
        """Compute cumulative chainwork up to `height`."""
        total = 0
        for h in range(min(height + 1, len(self.by_height))):
            rec = self.by_height.get(h)
            if rec is None:
                continue
            bits = rec["bits"]
            target = bits_to_target(bits)
            if target > 0:
                total += (1 << 256) // target
        return total

    def load_from_snapshot(self, snapshot_path, manifest, checkpoint=None):
        """Bootstrap from a light-ledger snapshot instead of full replay.

        This is the hook the P2P wallet sync will use: download a trusted
        snapshot + checkpoint, verify the attestation and anchor status,
        then start the node from the snapshot state.

        snapshot_path: path to the .jsonl.gz snapshot file
        manifest: snapshot manifest dict (from export_overlay)
        checkpoint: optional attested checkpoint dict for verification

        Returns (overlay, spent) on success.
        """
        import lightledger as ll

        # Verify checkpoint attestation if provided
        if checkpoint:
            if not ll.verify_checkpoint(checkpoint):
                raise ValueError("checkpoint attestation failed — "
                                 "refusing untrusted snapshot")
            status = ll.checkpoint_status(checkpoint)
            if status != "final":
                raise ValueError(f"checkpoint status is '{status}', "
                                 "not 'final' — refusing non-final snapshot")

        # Import and verify the snapshot
        overlay, spent = ll.import_overlay(snapshot_path, manifest)

        # Set up chain state from snapshot metadata
        self.tips = [{
            "height": manifest["height"],
            "hash": manifest["tip_hash"],
            "work": manifest["chainwork"],
        }]
        self.utxo = overlay if not spent else UtxoSet.__new__(UtxoSet)
        if spent:
            self.utxo.overlay = overlay
            self.utxo.spent = spent
        self._loaded = True

        print(f"Loaded from snapshot at height {manifest['height']}, "
              f"{len(overlay)} UTXOs, {len(spent)} spent tombstones",
              flush=True)
        return overlay, spent
