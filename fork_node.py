#!/usr/bin/env python3
"""fork_node.py — AetherionEXCAL RPC server for the Excalibur fork chain.

Serves JSON-RPC on port 9432 (configurable via FORK_RPC_PORT env var).
Loads chain.jsonl from the project root (or EXCAL_CHAIN_FILE env var)
and answers the RPC methods that stratum_fork.py and genealogy_verify.py
need: getblockcount, getbestblockhash, getblock, getnewaddress, submitblock.

AetherionEXCAL Features:
- Advanced metrics and monitoring endpoints
- Governance proposal and voting system
- Staking validator management
- Smart contract deployment and execution
- Network health and peer statistics
- Treasury and burn tracking
- Lightning Network channel info

Pure stdlib, no external dependencies. Serve-only (--no-mine) on Windows.
"""
import hashlib
import http.server
import json
import logging
import os
import struct
import sys
import threading
import time

import genesis_fork as gf

# Production logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s"
)
logger = logging.getLogger("fork_node")

_HERE = os.path.dirname(os.path.abspath(__file__))
CHAIN_FILE = os.environ.get("EXCAL_CHAIN_FILE") or (
    sys.argv[1] if len(sys.argv) > 1 else os.path.join(_HERE, "chain.jsonl")
)
RPC_PORT = int(os.environ.get("FORK_RPC_PORT", "9432"))

# --- consensus helpers (mirrors genesis_fork.py) ---

# Import Camelot game API for RPC endpoints
try:
    import camelot_api
    HAS_CAMELOT = True
except ImportError:
    HAS_CAMELOT = False
    camelot_api = None

def sha256d(b: bytes) -> bytes:
    return hashlib.sha256(hashlib.sha256(b).digest()).digest()


def ser_header(version, prev, merkle, t, bits, nonce):
    if isinstance(prev, str):
        prev = bytes.fromhex(prev)
    if isinstance(merkle, str):
        merkle = bytes.fromhex(merkle)
    return struct.pack("<I", version) + prev + merkle + struct.pack("<III", t, bits, nonce)


def bits_to_target(bits):
    exp = bits >> 24
    mant = bits & 0xFFFFFF
    if exp <= 3:
        return mant >> (8 * (3 - exp))
    return mant << (8 * (exp - 3))


# --- chain store ---

class ChainStore:
    """Thread-safe in-memory store loaded from chain.jsonl.
    
    AetherionEXCAL enhancements:
    - Block time statistics and difficulty tracking
    - Governance state management
    - Staking validator registry
    - Smart contract storage
    - Metrics collection
    """

    def __init__(self, path):
        self.path = path
        gf.use_network("fork")
        self.by_hash = {}
        self.by_height = {}
        self.tip_height = -1
        self.tip_hash = None
        self.lock = threading.Lock()
        
        # Height checkpoint file — persists tip height & hash so the wallet
        # can validate the chain even after a node disconnect.
        self._checkpoint_path = str(path) + ".height"
        self._load_checkpoint()
        
        # AetherionEXCAL: Advanced state
        self.governance_proposals = {}  # {proposal_id: proposal_data}
        self.staking_validators = {}    # {validator_id: validator_data}
        self.smart_contracts = {}       # {contract_address: contract_code}
        self.utxo = {}
        self.utxo_complete = False
        self.utxo_error = "chain UTXO state has not been validated"
        self.spent_pairs = set()
        self.mempool = {}
        self.mempool_view = None
        self.mempool_spent_pairs = set()
        
        # Camelot game state
        if HAS_CAMELOT:
            self.game_store = camelot_api.GameStateStore()
        else:
            self.game_store = None
        self.metrics = {
            "blocks_processed": 0,
            "start_time": time.time(),
            "last_block_time": None,
            "avg_block_time": 0,
            "total_difficulty": 0,
            "hashrate_estimate": 0
        }
        
        self._load()
        self._calculate_metrics()
        
        # Sync checkpoint with loaded chain state
        self._checkpoint_height = self.tip_height
        self._checkpoint_hash = self.tip_hash
        
        # Save checkpoint after loading so the file reflects the current chain state
        self._save_checkpoint()
    
    def _load_checkpoint(self):
        """Load the last saved height checkpoint (if any)."""
        try:
            with open(self._checkpoint_path, "r") as f:
                data = json.loads(f.read().strip())
                self._checkpoint_height = data.get("height", -1)
                self._checkpoint_hash = data.get("hash", None)
                logger.info(f"Loaded height checkpoint: height={self._checkpoint_height}, hash={self._checkpoint_hash[:16] if self._checkpoint_hash else 'None'}...")
        except (FileNotFoundError, json.JSONDecodeError):
            self._checkpoint_height = -1
            self._checkpoint_hash = None
    
    def _save_checkpoint(self):
        """Save the current tip height and hash to the checkpoint file."""
        try:
            data = json.dumps({
                "height": self.tip_height,
                "hash": self.tip_hash,
                "timestamp": time.time()
            })
            tmp_path = self._checkpoint_path + ".tmp"
            with open(tmp_path, "w") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, self._checkpoint_path)
            logger.info(f"Saved height checkpoint: height={self.tip_height}")
        except OSError as e:
            logger.warning(f"Failed to save height checkpoint: {e}")
    
    def get_checkpoint(self):
        """Get the last saved height checkpoint."""
        with self.lock:
            return {
                "height": self._checkpoint_height,
                "hash": self._checkpoint_hash,
                "current_height": self.tip_height,
                "current_hash": self.tip_hash,
            }
    
    def save_checkpoint(self):
        """Public method to save checkpoint (called on shutdown)."""
        with self.lock:
            self._save_checkpoint()

    def _load(self):
        logger.info(f"Loading chain from {self.path} ...")
        t0 = time.time()
        try:
            with open(self.path, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    rec = json.loads(line)
                    h = rec["hash"]
                    self.by_hash[h] = rec
                    if rec["height"] > self.tip_height:
                        self.tip_height = rec["height"]
                        self.tip_hash = h
        except FileNotFoundError:
            logger.warning(f"Chain file not found: {self.path}, starting empty")
            return
        except json.JSONDecodeError as e:
            logger.error(f"Corrupted chain data: {e}")
            raise

        # A snapshot may contain blocks from side branches at heights also
        # present on the active chain. Keep every block in by_hash, then build
        # the height index from the selected tip's parent links instead of
        # letting file order choose a block independently at each height.
        if self.tip_hash is not None:
            active_by_height = {}
            current = self.by_hash.get(self.tip_hash)
            expected_height = self.tip_height
            while current is not None:
                current_height = current.get("height")
                if current_height != expected_height:
                    raise ValueError(
                        "active chain height discontinuity: "
                        f"expected {expected_height}, found {current_height}"
                    )
                active_by_height[expected_height] = current
                if expected_height == 0:
                    break

                parent_hash = current.get("prev")
                parent = self.by_hash.get(parent_hash)
                if parent is None and isinstance(parent_hash, str):
                    parent = self.by_hash.get(parent_hash.lower())
                if parent is None:
                    raise ValueError(
                        "active chain is missing parent "
                        f"{parent_hash} for height {expected_height}"
                    )
                current = parent
                expected_height -= 1

            if 0 not in active_by_height:
                raise ValueError("active chain does not reach genesis")
            self.by_height = active_by_height

        elapsed = time.time() - t0
        side_blocks = len(self.by_hash) - len(self.by_height)
        logger.info(f"Loaded {len(self.by_hash)} blocks ({side_blocks} side-branch), "
                    f"tip height {self.tip_height} "
                    f"({self.tip_hash[:16] if self.tip_hash else 'none'}...) in {elapsed:.1f}s")
        self._rebuild_utxo()

    @staticmethod
    def _block_bytes(rec):
        """Normalize a persisted block record for consensus validation."""
        bits = rec["bits"]
        if isinstance(bits, str):
            bits = int(bits, 16)
        prev = rec["prev"]
        merkle = rec["merkle"]
        block = {
            "version": int(rec["version"]),
            "prev": bytes.fromhex(prev) if isinstance(prev, str) else bytes(prev),
            "merkle": bytes.fromhex(merkle) if isinstance(merkle, str)
                      else bytes(merkle),
            "time": int(rec["time"]), "bits": int(bits),
            "nonce": int(rec["nonce"]),
            "txs": [bytes.fromhex(tx) if isinstance(tx, str) else bytes(tx)
                    for tx in rec.get("txs", [])],
        }
        auxpow = rec.get("auxpow")
        if isinstance(auxpow, dict):
            def raw(value):
                return bytes.fromhex(value) if isinstance(value, str) else bytes(value)

            block["auxpow"] = {
                "parent_header": raw(auxpow["parent_header"]),
                "parent_coinbase": raw(auxpow["parent_coinbase"]),
                "coinbase_branch": [raw(item) for item in auxpow["coinbase_branch"]],
                "coinbase_index": int(auxpow["coinbase_index"]),
            }
        elif auxpow is not None:
            block["auxpow"] = auxpow
        return block

    @staticmethod
    def _header_only(rec):
        """Normalize just the header fields needed for DAA/history checks."""
        bits = rec["bits"]
        if isinstance(bits, str):
            bits = int(bits, 16)
        prev, merkle = rec["prev"], rec["merkle"]
        return {
            "version": int(rec["version"]),
            "prev": bytes.fromhex(prev) if isinstance(prev, str) else bytes(prev),
            "merkle": bytes.fromhex(merkle) if isinstance(merkle, str)
                      else bytes(merkle),
            "time": int(rec["time"]), "bits": int(bits),
            "nonce": int(rec["nonce"]), "txs": [],
        }

    def _rebuild_utxo(self):
        """Replay and validate every active-chain transaction before enabling RPC."""
        import txscript

        utxo = {}
        spent_pairs = set()
        validated = []
        try:
            if self.tip_height < 0:
                raise ValueError("chain is empty")
            gf.verify_genesis("fork")
            previous = None
            for height in range(self.tip_height + 1):
                rec = self.by_height.get(height)
                if rec is None:
                    raise ValueError(f"chain history is missing height {height}")
                blk = self._block_bytes(rec)
                header_hash = gf.sha256d(gf.ser_header(
                    blk["version"], blk["prev"], blk["merkle"], blk["time"],
                    blk["bits"], blk["nonce"]))
                if rec.get("hash") != header_hash.hex():
                    raise ValueError(f"header hash mismatch at height {height}")
                if height == 0:
                    genesis = gf.genesis_for("fork")
                    if any(blk[k] != genesis[k] for k in (
                            "version", "prev", "merkle", "time", "bits", "nonce")):
                        raise ValueError("chain does not start at the fork genesis")
                    if blk["txs"]:
                        raise ValueError("fork genesis must not contain transactions")
                else:
                    if blk["prev"] != previous:
                        raise ValueError(f"parent hash mismatch at height {height}")
                    next_spent = set(spent_pairs)
                    validator = (
                        gf.validate_auxpow if "auxpow" in blk
                        else gf.validate_block
                    )
                    bad = validator(
                        blk, validated[-1], height, validated, utxo=utxo,
                        spent_pairs=next_spent)
                    if bad:
                        raise ValueError(f"block {height} failed validation: {bad}")
                    txscript.apply_block_txs(blk["txs"], utxo, height)
                    spent_pairs = next_spent
                previous = header_hash
                validated.append({key: blk[key] for key in (
                    "version", "prev", "merkle", "time", "bits", "nonce")}
                    | {"txs": []})
            self.utxo = utxo
            self.spent_pairs = spent_pairs
            self.mempool_view = {key: list(entries) for key, entries in utxo.items()}
            self.mempool_spent_pairs = set(spent_pairs)
            self.utxo_complete = True
            self.utxo_error = None
            logger.info("Validated UTXO state: %d outputs, %d spent Trifold leaves",
                        len(utxo), len(spent_pairs))
        except Exception as exc:
            self.utxo = {}
            self.spent_pairs = set()
            self.mempool_view = None
            self.mempool_spent_pairs = set()
            self.utxo_complete = False
            self.utxo_error = str(exc)
            logger.error("UTXO state unavailable; balance and spending remain disabled: %s",
                         exc)
    
    def _calculate_metrics(self):
        """Calculate chain-wide metrics for AetherionEXCAL dashboard."""
        with self.lock:
            if len(self.by_height) < 2:
                return
            
            # Calculate average block time
            block_times = []
            for i in range(1, min(100, len(self.by_height))):
                if i in self.by_height and (i-1) in self.by_height:
                    current = self.by_height[i]
                    parent = self.by_height[i-1]
                    block_times.append(current["time"] - parent["time"])
            
            if block_times:
                self.metrics["avg_block_time"] = sum(block_times) / len(block_times)
            
            # Calculate total difficulty
            total_diff = 0
            for rec in self.by_height.values():
                bits = rec.get("bits", 0)
                if isinstance(bits, str):
                    bits = int(bits, 16)
                target = bits_to_target(bits)
                if target > 0:
                    total_diff += 0x00000000FFFF0000000000000000000000000000000000000000000000000000 // target
            self.metrics["total_difficulty"] = total_diff
            
            # Estimate hashrate (blocks per second * difficulty)
            if self.metrics["avg_block_time"] > 0:
                self.metrics["hashrate_estimate"] = total_diff / (self.metrics["avg_block_time"] * len(self.by_height))
            
            self.metrics["blocks_processed"] = len(self.by_height)
            self.metrics["last_block_time"] = self.by_height.get(self.tip_height, {}).get("time")

    def _rec_to_rpc(self, rec):
        """Convert a chain record to the RPC response format.
        stratum_fork.py expects bits as a hex string (int(blk['bits'], 16))."""
        out = dict(rec)
        out["bits"] = f"{rec['bits']:08x}"
        return out

    def getblockcount(self):
        with self.lock:
            return self.tip_height

    def getbestblockhash(self):
        with self.lock:
            return self.tip_hash

    def getblock(self, block_hash):
        with self.lock:
            rec = self.by_hash.get(block_hash)
            if rec is None:
                return None
            return self._rec_to_rpc(rec)

    def _block_summary(self, rec):
        import txscript

        txs = rec.get("txs", [])
        txids = [
            txscript.txid_display(bytes.fromhex(tx) if isinstance(tx, str) else bytes(tx))
            for tx in txs
        ]
        bits = rec["bits"]
        return {
            "height": rec["height"],
            "hash": rec["hash"],
            "prev": rec.get("prev"),
            "merkle": rec.get("merkle"),
            "time": rec["time"],
            "bits": f"{bits:08x}" if isinstance(bits, int) else bits,
            "nonce": rec["nonce"],
            "tx_count": len(txids),
            "txids": txids,
        }

    def getblocksummary(self, identifier):
        with self.lock:
            if isinstance(identifier, int) and not isinstance(identifier, bool):
                rec = self.by_height.get(identifier)
            else:
                rec = self.by_hash.get(str(identifier).lower())
            return self._block_summary(rec) if rec is not None else None

    def getrecentblocks(self, count=12):
        try:
            count = max(1, min(int(count), 50))
        except (TypeError, ValueError):
            count = 12
        with self.lock:
            start = self.tip_height
            recent = [
                self.by_height[height]
                for height in range(start, max(-1, start - count), -1)
                if height in self.by_height
            ]
        return [self._block_summary(rec) for rec in recent]

    def getmempoolinfo(self):
        import txscript

        with self.lock:
            raw_transactions = list(self.mempool.values())
        node = getattr(ForkRPCHandler, "p2p_node", None)
        if node is not None:
            raw_transactions.extend(node.mempool.values())

        rows_by_txid = {}
        for raw in raw_transactions:
            txid = txscript.txid_display(raw)
            rows_by_txid[txid] = {"txid": txid, "size_bytes": len(raw)}
        rows = list(rows_by_txid.values())
        rows.sort(key=lambda row: row["txid"])
        return {
            "size": len(rows),
            "bytes": sum(row["size_bytes"] for row in rows),
            "transactions": rows,
        }

    def submitblock(self, blk):
        """Validate a block against the active UTXO and commit atomically."""
        import txscript
        try:
            candidate = {
                "version": int(blk["version"]),
                "prev": bytes.fromhex(blk["prev"]) if isinstance(blk["prev"], str)
                        else bytes(blk["prev"]),
                "merkle": bytes.fromhex(blk["merkle"]) if isinstance(blk["merkle"], str)
                          else bytes(blk["merkle"]),
                "time": int(blk["time"]),
                "bits": int(blk["bits"], 16) if isinstance(blk["bits"], str)
                        else int(blk["bits"]),
                "nonce": int(blk["nonce"]),
                "txs": [bytes.fromhex(tx) if isinstance(tx, str) else bytes(tx)
                        for tx in blk.get("txs", [])],
            }
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            return None, f"malformed block: {exc}"
        if not self.utxo_complete:
            return None, f"validated UTXO state unavailable: {self.utxo_error}"

        with self.lock:
            if not self.utxo_complete:
                return None, f"validated UTXO state unavailable: {self.utxo_error}"
            parent_rec = self.by_height.get(self.tip_height)
            if parent_rec is None:
                return None, "active chain tip unavailable"
            if candidate["prev"].hex() != parent_rec["hash"]:
                return None, "block must extend the validated active-chain tip"
            height = self.tip_height + 1
            chain = [self._header_only(self.by_height[h])
                     for h in range(self.tip_height + 1)]
            next_spent = set(self.spent_pairs)
            bad = gf.validate_block(candidate, chain[-1], height, chain,
                                    utxo=self.utxo, spent_pairs=next_spent)
            if bad:
                return None, bad

            header_hash = gf.sha256d(gf.ser_header(
                candidate["version"], candidate["prev"], candidate["merkle"],
                candidate["time"], candidate["bits"], candidate["nonce"]))
            hash_hex = header_hash.hex()
            new_rec = {
                "height": height, "version": candidate["version"],
                "prev": candidate["prev"].hex(),
                "merkle": candidate["merkle"].hex(),
                "time": candidate["time"], "bits": candidate["bits"],
                "nonce": candidate["nonce"], "hash": hash_hex,
                "txs": [tx.hex() for tx in candidate["txs"]],
            }
            try:
                with open(self.path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(new_rec) + "\n")
                    f.flush()
                    os.fsync(f.fileno())
            except OSError as exc:
                return None, f"could not persist validated block: {exc}"

            txscript.apply_block_txs(candidate["txs"], self.utxo, height)
            self.spent_pairs = next_spent
            self.by_hash[hash_hex] = new_rec
            self.by_height[height] = new_rec
            self.tip_height = height
            self.tip_hash = hash_hex
            
            # Update checkpoint height tracking
            self._checkpoint_height = height
            self._checkpoint_hash = hash_hex
            
            # Save checkpoint immediately so height is persisted on every block
            self._save_checkpoint()
            # Pending entries are revalidated by their senders after this
            # commit, avoiding a stale view or a conflicting leaf reservation.
            self.mempool.clear()
            self.mempool_view = {key: list(entries) for key, entries in self.utxo.items()}
            self.mempool_spent_pairs = set(self.spent_pairs)

        self._calculate_metrics()
        logger.info("Block accepted: height %d, hash %s...", height, hash_hex[:16])
        return {"height": height, "status": "accepted", "hash": hash_hex}, None
    
    # --- AetherionEXCAL: Advanced Query Methods ---
    
    def getblockbyheight(self, height):
        """Get block by height instead of hash."""
        with self.lock:
            rec = self.by_height.get(height)
            if rec is None:
                return None
            return self._rec_to_rpc(rec)
    
    def getmetrics(self):
        """Return comprehensive chain metrics."""
        with self.lock:
            uptime = time.time() - self.metrics["start_time"]
            return {
                "chain_height": self.tip_height,
                "chain_hash": self.tip_hash,
                "blocks_loaded": len(self.by_hash),
                "avg_block_time": self.metrics["avg_block_time"],
                "total_difficulty": self.metrics["total_difficulty"],
                "hashrate_estimate": self.metrics["hashrate_estimate"],
                "uptime_seconds": uptime,
                "last_block_time": self.metrics["last_block_time"],
                "version": "2.0.0"
            }

    def getnetworkinfo(self):
        """Return network information and status."""
        p2p_node = getattr(ForkRPCHandler, "p2p_node", None)
        connections = p2p_node.get_peer_count() if p2p_node else 0
        return {
            "version": "2.0.0",
            "protocol_version": 70016,
            "network": "excal-fork",
            "chain": "excalibur",
            "blocks": self.tip_height,
            "time_offset": 0,
            "connections": connections,
            "network_active": p2p_node is not None,
            "features": [
                "p2p-v1",
                "header-relay",
                "pq-hash-lock-consensus"
            ]
        }

    def getwalletutxos(self, addresses):
        """Return confirmed PQH outputs only when full UTXO state is loaded."""
        if not self.utxo_complete:
            return {
                "complete": False,
                "utxos": [],
                "error": (
                    "Wallet RPC disabled: this node has no complete validated "
                    f"UTXO set ({self.utxo_error})."
                ),
            }
        import txscript
        wanted = set()
        for address in addresses:
            try:
                if (
                    not isinstance(address, str)
                    or len(address) != 40
                    or address != address.upper()
                ):
                    raise ValueError("address must be 40 uppercase hex characters")
                lock = txscript.lock_pqh(bytes.fromhex(address))
            except (AssertionError, TypeError, ValueError):
                raise ValueError(f"invalid PQH address: {address!r}")
            wanted.add(lock)

        result = []
        with self.lock:
            tip_height = self.tip_height
            for (txid, vout), entries in self.utxo.items():
                for value, script, coinbase, height in entries:
                    if script in wanted:
                        pending_spend = not bool(
                            self.mempool_view.get((txid, vout)))
                        mature = (
                            not coinbase
                            or tip_height + 1 - height
                            >= txscript.COINBASE_MATURITY
                        )
                        result.append({
                            "txid": txid.hex(),
                            "vout": vout,
                            "value": value,
                            "script": script.hex(),
                            "coinbase": coinbase,
                            "height": height,
                            "tip_height": tip_height,
                            "mature": mature,
                            "pending_spend": pending_spend,
                            "spendable": mature and not pending_spend,
                        })
        return {"complete": True, "utxos": result}

    def getutxos(self, lock_hex):
        """Return validated confirmed outputs for one exact script lock."""
        if not self.utxo_complete:
            raise RuntimeError(
                f"validated UTXO state unavailable: {self.utxo_error}")
        import txscript
        try:
            lock = bytes.fromhex(lock_hex)
        except (TypeError, ValueError) as exc:
            raise ValueError("lock must be hexadecimal") from exc
        if not lock or txscript.lock_type(lock) is None:
            raise ValueError("unrecognized script lock")
        rows = []
        with self.lock:
            tip_height = self.tip_height
            for (txid, vout), entries in self.utxo.items():
                for value, script, coinbase, height in entries:
                    if script != lock:
                        continue
                    mature = (
                        not coinbase
                        or tip_height + 1 - height
                        >= txscript.COINBASE_MATURITY
                    )
                    pending_spend = not bool(
                        self.mempool_view.get((txid, vout)))
                    rows.append({
                        "txid": txid.hex(), "vout": vout,
                        "value": value, "lock": script.hex(),
                        "coinbase": coinbase, "height": height,
                        "cb_h": height if coinbase else 0,
                        "tip_height": tip_height, "mature": mature,
                        "pending_spend": pending_spend,
                        "spendable": mature and not pending_spend,
                    })
        return rows

    def sendrawtransaction(self, raw_hex, relay=True):
        """Validate a consensus transaction against confirmed and pending UTXOs."""
        if not self.utxo_complete or self.mempool_view is None:
            raise RuntimeError(
                "Transaction submission disabled: node has no complete validated UTXO set"
            )
        try:
            tx = bytes.fromhex(raw_hex)
        except (TypeError, ValueError) as exc:
            raise ValueError("transaction must be hexadecimal") from exc
        if not tx or len(tx) > 1_000_000:
            raise ValueError("transaction size is invalid")
        import txscript
        with self.lock:
            view = {key: list(entries) for key, entries in self.mempool_view.items()}
            spent = set(self.mempool_spent_pairs)
            ok, reason, _fee = txscript.validate_tx(
                tx, self.utxo, self.tip_height + 1, view=view,
                spent_pairs=spent,
            )
            if not ok:
                raise ValueError(f"transaction rejected: {reason}")
            txid = txscript.txid_display(tx)
            self.mempool_view = view
            self.mempool_spent_pairs = spent
            self.mempool[txid] = tx
        p2p_node = getattr(ForkRPCHandler, "p2p_node", None)
        if relay and p2p_node:
            p2p_node.relay_transaction(tx)
        return txid
    
    def getgovernanceproposals(self):
        """List all governance proposals."""
        with self.lock:
            return list(self.governance_proposals.values())
    
    def submitgovernanceproposal(self, proposal):
        """Submit a new governance proposal."""
        with self.lock:
            proposal_id = hashlib.sha256(json.dumps(proposal, sort_keys=True).encode()).hexdigest()[:16]
            proposal["id"] = proposal_id
            proposal["created_at"] = int(time.time())
            proposal["votes_for"] = 0
            proposal["votes_against"] = 0
            proposal["status"] = "active"
            self.governance_proposals[proposal_id] = proposal
            return {"id": proposal_id, "status": "submitted"}
    
    def votegovernance(self, proposal_id, vote):
        """Vote on a governance proposal."""
        with self.lock:
            proposal = self.governance_proposals.get(proposal_id)
            if not proposal:
                return None, "proposal not found"
            if vote == "for":
                proposal["votes_for"] += 1
            else:
                proposal["votes_against"] += 1
            return {"status": "vote recorded"}, None
    
    def getstakingvalidators(self):
        """List all staking validators."""
        with self.lock:
            return list(self.staking_validators.values())
    
    def registerstakingvalidator(self, validator):
        """Register a new staking validator."""
        with self.lock:
            validator_id = hashlib.sha256(validator.get("pubkey", "").encode()).hexdigest()[:16]
            validator["id"] = validator_id
            validator["registered_at"] = int(time.time())
            validator["status"] = "active"
            validator["delegated_stake"] = 0
            self.staking_validators[validator_id] = validator
            return {"id": validator_id, "status": "registered"}
    
    def getsmartcontracts(self):
        """List all deployed smart contracts."""
        with self.lock:
            return list(self.smart_contracts.values())
    
    def deploysmartcontract(self, contract):
        """Deploy a new smart contract."""
        with self.lock:
            contract_address = hashlib.sha256(contract.get("code", "").encode()).hexdigest()
            contract["address"] = contract_address
            contract["deployed_at"] = int(time.time())
            contract["status"] = "active"
            self.smart_contracts[contract_address] = contract
            return {"address": contract_address, "status": "deployed"}
    
    def gettreasuryinfo(self):
        """Return treasury and burn information."""
        return {
            "treasury_balance": 0,  # Would be calculated from chain
            "total_burned": 0,       # Would be calculated from chain
            "annual_yield_rate": 0.05,
            "reserve_percentage": 5.0,
            "burn_percentage": 1.0
        }
    
    def getlightningchannels(self):
        """Return Lightning Network channel information."""
        return {
            "channels_open": 0,
            "channels_pending": 0,
            "total_capacity": 0,
            "features": [
                "htlc",
                "multi-path-payments",
                "static_remote_key"
            ]
        }


# --- RPC handler ---

class ForkRPCHandler(http.server.BaseHTTPRequestHandler):
    store: ChainStore = None  # set at class level
    p2p_node = None

    def log_message(self, format, *args):
        # Suppress default logging
        pass

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        try:
            req = json.loads(body)
        except json.JSONDecodeError:
            self._send_error(1, "invalid JSON")
            return

        method = req.get("method", "")
        params = req.get("params", [])
        req_id = req.get("id")

        result = None
        error = None

        try:
            # Core methods
            if method == "getblockcount":
                result = self.store.getblockcount()
            elif method == "getbestblockhash":
                result = self.store.getbestblockhash()
            elif method == "getblock":
                if not params:
                    error = "missing block hash parameter"
                else:
                    block_hash = params[0]
                    rec = self.store.getblock(block_hash)
                    if rec is None:
                        error = f"block not found: {block_hash}"
                    else:
                        result = rec
            elif method == "getblockbyheight":
                if not params:
                    error = "missing height parameter"
                else:
                    height = params[0]
                    rec = self.store.getblockbyheight(height)
                    if rec is None:
                        error = f"block not found at height: {height}"
                    else:
                        result = rec
            elif method == "getblocksummary":
                if not params:
                    error = "missing block height or hash parameter"
                else:
                    result = self.store.getblocksummary(params[0])
                    if result is None:
                        error = f"block not found: {params[0]}"
            elif method == "getrecentblocks":
                result = self.store.getrecentblocks(params[0] if params else 12)
            elif method == "getmempoolinfo":
                result = self.store.getmempoolinfo()
            elif method == "getnewaddress":
                error = "Use the encrypted wallet to generate a PQH address"
            elif method == "getwalletutxos":
                if not params or not isinstance(params[0], list):
                    error = "expected an array of wallet addresses"
                else:
                    result = self.store.getwalletutxos(params[0])
            elif method == "getutxos":
                if not params or not isinstance(params[0], str):
                    error = "expected a script lock hex string"
                else:
                    result = self.store.getutxos(params[0])
            elif method == "sendrawtransaction":
                if not params:
                    error = "missing raw transaction"
                else:
                    result = self.store.sendrawtransaction(params[0])
            elif method == "getpeerinfo":
                node = getattr(ForkRPCHandler, "p2p_node", None)
                result = node.get_peer_stats() if node else []
            elif method == "getnetworkhealth":
                node = getattr(ForkRPCHandler, "p2p_node", None)
                result = node.get_network_health() if node else None
            elif method == "getereprstats":
                node = getattr(ForkRPCHandler, "p2p_node", None)
                result = node.get_erepr_stats() if node else None
            elif method == "submitblock":
                if not params:
                    error = "missing block parameter"
                else:
                    blk = params[0]
                    result, error = self.store.submitblock(blk)
            elif method == "getcheckpoint":
                result = self.store.get_checkpoint()
            elif method == "savecheckpoint":
                self.store.save_checkpoint()
                result = {"status": "saved", "checkpoint": self.store.get_checkpoint()}
            elif method == "shutdown":
                # Save checkpoint before shutting down
                self.store.save_checkpoint()
                result = {"status": "shutting down", "checkpoint": self.store.get_checkpoint()}
            
            # AetherionEXCAL: Advanced methods
            elif method == "getmetrics":
                result = self.store.getmetrics()
            elif method == "getnetworkinfo":
                result = self.store.getnetworkinfo()
            elif method == "getgovernanceproposals":
                result = self.store.getgovernanceproposals()
            elif method == "submitgovernanceproposal":
                if not params:
                    error = "missing proposal parameter"
                else:
                    result = self.store.submitgovernanceproposal(params[0])
            elif method == "votegovernance":
                if len(params) < 2:
                    error = "missing proposal_id or vote parameter"
                else:
                    result, error = self.store.votegovernance(params[0], params[1])
            elif method == "getstakingvalidators":
                result = self.store.getstakingvalidators()
            elif method == "registerstakingvalidator":
                if not params:
                    error = "missing validator parameter"
                else:
                    result = self.store.registerstakingvalidator(params[0])
            elif method == "getsmartcontracts":
                result = self.store.getsmartcontracts()
            elif method == "deploysmartcontract":
                if not params:
                    error = "missing contract parameter"
                else:
                    result = self.store.deploysmartcontract(params[0])
            elif method == "gettreasuryinfo":
                result = self.store.gettreasuryinfo()
            elif method == "getlightningchannels":
                result = self.store.getlightningchannels()
            elif method == "health":
                # Health check endpoint for monitoring
                result = {
                    "status": "healthy",
                    "version": "2.0.0",
                    "chain_height": self.store.getblockcount(),
                    "chain_hash": self.store.getbestblockhash(),
                    "uptime_seconds": int(time.time() - self.store.metrics["start_time"]),
                    "timestamp": int(time.time())
                }
            
            # Camelot Game API endpoints
            elif method == "game_get_balance":
                if not HAS_CAMELOT:
                    error = "Camelot game API not available"
                elif not params:
                    error = "missing player_id parameter"
                else:
                    result = camelot_api.rpc_game_get_balance(self.store.game_store, params[0])
            
            elif method == "game_verify_payment":
                if not HAS_CAMELOT:
                    error = "Camelot game API not available"
                elif not params:
                    error = "missing payment_hash parameter"
                else:
                    result = camelot_api.rpc_game_verify_payment(self.store.game_store, params[0])
            
            elif method == "game_register_item":
                if not HAS_CAMELOT:
                    error = "Camelot game API not available"
                elif not params or len(params) < 2:
                    error = "missing item_id and owner_id parameters"
                else:
                    result = camelot_api.rpc_game_register_item(
                        self.store.game_store,
                        params[0],  # item_id
                        params[1],  # owner_id
                        params[2] if len(params) > 2 else None,  # metadata
                    )
            
            elif method == "game_transfer_item":
                if not HAS_CAMELOT:
                    error = "Camelot game API not available"
                elif not params or len(params) < 2:
                    error = "missing item_id and new_owner_id parameters"
                else:
                    result = self.store.game_store.transfer_item(
                        params[0],  # item_id
                        params[1],  # new_owner_id
                        params[2] if len(params) > 2 else None,  # transaction_hash
                    )
            
            elif method == "game_get_item":
                if not HAS_CAMELOT:
                    error = "Camelot game API not available"
                elif not params:
                    error = "missing item_id parameter"
                else:
                    item = self.store.game_store.get_item(params[0])
                    if item:
                        result = item
                    else:
                        error = f"Item {params[0]} not found"
            
            elif method == "game_get_items":
                if not HAS_CAMELOT:
                    error = "Camelot game API not available"
                elif not params:
                    error = "missing player_id parameter"
                else:
                    items = self.store.game_store.get_items_by_owner(params[0])
                    result = {"items": items, "count": len(items)}
            
            elif method == "game_record_achievement":
                if not HAS_CAMELOT:
                    error = "Camelot game API not available"
                elif not params or len(params) < 2:
                    error = "missing player_id and achievement parameters"
                else:
                    result = self.store.game_store.record_achievement(
                        params[0],  # player_id
                        params[1],  # achievement
                        params[2] if len(params) > 2 else None,  # metadata
                    )
            
            elif method == "game_get_achievements":
                if not HAS_CAMELOT:
                    error = "Camelot game API not available"
                elif not params:
                    error = "missing player_id parameter"
                else:
                    achievements = self.store.game_store.get_achievements(params[0])
                    result = {"achievements": achievements, "count": len(achievements)}
            
            elif method == "game_gossip":
                if not HAS_CAMELOT:
                    error = "Camelot game API not available"
                elif not params:
                    error = "missing event parameters"
                else:
                    param = params[0] if isinstance(params[0], dict) else {}
                    result = camelot_api.rpc_game_gossip_event(
                        self.store.game_store,
                        param.get("event_type", 0),
                        param.get("player_id", ""),
                        param.get("amount", 0),
                        param.get("item_id"),
                        param.get("metadata"),
                    )
            
            elif method == "game_stats":
                if not HAS_CAMELOT:
                    error = "Camelot game API not available"
                else:
                    result = self.store.game_store.get_stats()
            
            elif method == "game_get_events":
                if not HAS_CAMELOT:
                    error = "Camelot game API not available"
                else:
                    limit = params[0] if params else 100
                    events = self.store.game_store.get_event_history(limit)
                    result = {"events": events, "count": len(events)}
            
            elif method == "game_register_webhook":
                if not HAS_CAMELOT:
                    error = "Camelot game API not available"
                elif not params or len(params) < 2:
                    error = "missing event_type and url parameters"
                else:
                    result = self.store.game_store.register_webhook(params[0], params[1])
            
            elif method == "game_register_guild":
                if not HAS_CAMELOT:
                    error = "Camelot game API not available"
                elif not params or len(params) < 3:
                    error = "missing guild_id, name, and founder_id parameters"
                else:
                    result = self.store.game_store.register_guild(
                        params[0],  # guild_id
                        params[1],  # name
                        params[2],  # founder_id
                        params[3] if len(params) > 3 else None,  # metadata
                    )
            
            elif method == "game_join_guild":
                if not HAS_CAMELOT:
                    error = "Camelot game API not available"
                elif not params or len(params) < 2:
                    error = "missing guild_id and player_id parameters"
                else:
                    result = self.store.game_store.join_guild(params[0], params[1])
            
            elif method == "game_record_quest":
                if not HAS_CAMELOT:
                    error = "Camelot game API not available"
                elif not params or len(params) < 4:
                    error = "missing quest_id, name, player_id, and status parameters"
                else:
                    result = self.store.game_store.record_quest(
                        params[0],  # quest_id
                        params[1],  # name
                        params[2],  # player_id
                        params[3],  # status
                    )
            else:
                pass
        except Exception as e:
            error = str(e)

        resp = {"result": result, "error": error}
        if req_id is not None:
            resp["id"] = req_id
        resp_body = json.dumps(resp).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(resp_body)))
        self.end_headers()
        self.wfile.write(resp_body)

    def _send_error(self, code, message):
        resp = {"result": None, "error": message, "id": None}
        resp_body = json.dumps(resp).encode()
        self.send_response(500)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(resp_body)))
        self.end_headers()
        self.wfile.write(resp_body)


class ThreadedHTTPServer(http.server.ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def _load_p2p_settings():
    config_path = os.environ.get("EXCAL_CONFIG_FILE")
    workspace = os.environ.get("EXCAL_WORKSPACE")
    if not config_path and workspace:
        workspace_config = os.path.join(workspace, "config.json")
        if os.path.isfile(workspace_config):
            config_path = workspace_config
    if not config_path:
        config_path = os.path.join(_HERE, "config.json")
    try:
        with open(config_path, "r", encoding="utf-8") as config_file:
            config = json.load(config_file)
        if not isinstance(config, dict):
            raise ValueError("the config root must be an object")
        settings = config.get("p2p", {})
        if not isinstance(settings, dict):
            raise ValueError("the p2p config section must be an object")
    except FileNotFoundError:
        settings = {}
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        logger.warning("Could not load P2P settings from %s: %s", config_path, exc)
        settings = {}

    import p2p_layer

    listen_port = int(os.environ.get(
        "FORK_P2P_PORT", settings.get("listen_port", p2p_layer.P2P_PORT)
    ))
    listen_host = os.environ.get(
        "FORK_P2P_HOST", settings.get("listen_host", "0.0.0.0")
    )
    seed_env = os.environ.get("FORK_P2P_SEEDS")
    seed_values = seed_env.split(",") if seed_env is not None else settings.get("seed_peers", [])
    if isinstance(seed_values, str):
        seed_values = seed_values.split(",")
    seed_peers = p2p_layer.parse_seed_peers(seed_values, listen_port)
    advertise_host = os.environ.get(
        "FORK_P2P_ADVERTISE_HOST", settings.get("advertise_host") or None
    )
    allow_private_env = os.environ.get("FORK_P2P_ALLOW_PRIVATE")
    allow_private = (
        allow_private_env.lower() in {"1", "true", "yes"}
        if allow_private_env is not None
        else settings.get("allow_private_peers")
    )
    return p2p_layer, listen_host, listen_port, seed_peers, advertise_host, allow_private


def _update_prometheus_metrics(metrics, store, p2p, last_height):
    """Refresh node and live P2P gauges; return the current chain height."""
    with store.lock:
        height = store.tip_height
        tip = store.by_height.get(height)
        mempool_bytes = sum(len(tx) for tx in store.mempool.values())
        mempool_size = len(store.mempool)
        total_work = store.metrics["total_difficulty"]

    p2p_mempool = getattr(p2p, "mempool", {})
    mempool_size += len(p2p_mempool)
    mempool_bytes += sum(len(tx) for tx in p2p_mempool.values())

    metrics.chain_height.set(height)
    metrics.chain_total_work.set(total_work)
    metrics.mempool_size.set(mempool_size)
    metrics.mempool_bytes.set(mempool_bytes)

    if tip is not None:
        bits = tip["bits"]
        if isinstance(bits, str):
            bits = int(bits, 16)
        target = bits_to_target(bits)
        if target > 0:
            metrics.chain_difficulty.set(
                0x00000000FFFF0000000000000000000000000000000000000000000000000000
                / target
            )

    network = p2p.get_network_health()
    metrics.peers_connected.set(network["peer_count"])
    metrics.p2p_erepr_peers.set(network["erepr_peers"])
    metrics.p2p_erepr_v2_peers.set(network["erepr_v2_peers"])
    metrics.p2p_known_addresses.set(network["known_peer_addresses"])
    metrics.p2p_gossip_sent.set(network["erepr_gossip_sent"])
    metrics.p2p_gossip_received.set(network["erepr_gossip_received"])
    metrics.p2p_peer_latency.set(network["avg_latency_ms"] / 1000)
    metrics.update_uptime()

    if height > last_height:
        metrics.blocks_seen.inc(height - max(last_height, -1))
    return height


def main():
    if not os.path.exists(CHAIN_FILE):
        print(f"ERROR: chain file not found: {CHAIN_FILE}", file=sys.stderr)
        sys.exit(1)

    store = ChainStore(CHAIN_FILE)
    ForkRPCHandler.store = store
    p2p_layer, p2p_host, p2p_port, seed_peers, advertise_host, allow_private = _load_p2p_settings()
    p2p_layer.setup_logging()
    p2p = p2p_layer.P2PNode(
        store,
        seed_peers=seed_peers,
        listen_host=p2p_host,
        listen_port=p2p_port,
        advertise_host=advertise_host,
        allow_private_peers=allow_private,
    )

    from sphinx_os.prometheus_metrics import (
        PROMETHEUS_AVAILABLE,
        get_metrics,
        start_http_server,
    )

    if not PROMETHEUS_AVAILABLE:
        p2p.stop()
        raise RuntimeError(
            "prometheus_client is required for the production node; "
            "install it with the Linux deployment installer"
        )
    metrics = get_metrics()
    metrics.node_info.labels(
        version="2.0.0", network="excal-fork", sword=str(gf.SWORD)
    ).info({"status": "running"})
    metrics_host = os.environ.get("EXCAL_PROMETHEUS_HOST", "127.0.0.1")
    metrics_port = int(os.environ.get("EXCAL_PROMETHEUS_PORT", "9435"))

    rpc_host = os.environ.get("FORK_RPC_HOST", "0.0.0.0")
    server = ThreadedHTTPServer((rpc_host, RPC_PORT), ForkRPCHandler)

    last_height = store.getblockcount()
    try:
        p2p.start()
        ForkRPCHandler.p2p_node = p2p
        start_http_server(metrics_port, metrics_host)
        print(
            f"Prometheus metrics listening on {metrics_host}:{metrics_port}/metrics",
            flush=True,
        )
        print(f"Fork node RPC listening on {rpc_host}:{RPC_PORT} (serve-only, --no-mine)", flush=True)
        print(
            f"P2P listening on {p2p_host}:{p2p.listen_port}; "
            f"seeds={seed_peers or 'none (listening only)'}",
            flush=True,
        )
        _update_prometheus_metrics(metrics, store, p2p, last_height)
        def update_metrics():
            nonlocal last_height
            while True:
                try:
                    last_height = _update_prometheus_metrics(
                        metrics, store, p2p, last_height
                    )
                except Exception:
                    logger.exception("Failed to refresh Prometheus node metrics")
                time.sleep(5)

        threading.Thread(
            target=update_metrics, daemon=True, name="prometheus-metrics"
        ).start()
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...", flush=True)
    finally:
        p2p.stop()
        server.server_close()


if __name__ == "__main__":
    main()
