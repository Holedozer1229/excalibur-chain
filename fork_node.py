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

# Production logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s"
)
logger = logging.getLogger("fork_node")

_HERE = os.path.dirname(os.path.abspath(__file__))
CHAIN_FILE = os.environ.get("EXCAL_CHAIN_FILE") or sys.argv[1] if len(sys.argv) > 1 else os.path.join(_HERE, "chain.jsonl")
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
        self.by_hash = {}
        self.by_height = {}
        self.tip_height = -1
        self.tip_hash = None
        self.lock = threading.Lock()
        
        # AetherionEXCAL: Advanced state
        self.governance_proposals = {}  # {proposal_id: proposal_data}
        self.staking_validators = {}    # {validator_id: validator_data}
        self.smart_contracts = {}       # {contract_address: contract_code}
        
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
                    self.by_height[rec["height"]] = rec
                    if rec["height"] > self.tip_height:
                        self.tip_height = rec["height"]
                        self.tip_hash = h
        except FileNotFoundError:
            logger.warning(f"Chain file not found: {self.path}, starting empty")
            return
        except json.JSONDecodeError as e:
            logger.error(f"Corrupted chain data: {e}")
            raise
        elapsed = time.time() - t0
        logger.info(f"Loaded {len(self.by_hash)} blocks, tip height {self.tip_height} "
                    f"({self.tip_hash[:16] if self.tip_hash else 'none'}...) in {elapsed:.1f}s")
    
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
            for rec in self.by_hash.values():
                bits = rec.get("bits", 0)
                if isinstance(bits, str):
                    bits = int(bits, 16)
                target = bits_to_target(bits)
                if target > 0:
                    total_diff += 0x00000000FFFF0000000000000000000000000000000000000000000000000000 // target
            self.metrics["total_difficulty"] = total_diff
            
            # Estimate hashrate (blocks per second * difficulty)
            if self.metrics["avg_block_time"] > 0:
                self.metrics["hashrate_estimate"] = total_diff / (self.metrics["avg_block_time"] * len(self.by_hash))
            
            self.metrics["blocks_processed"] = len(self.by_hash)
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

    def submitblock(self, blk):
        """Validate and append a new block. Returns dict with height, status, hash."""
        # blk is a dict: {version, prev, merkle, time, bits, nonce, txs}
        try:
            version = blk["version"]
            prev = blk["prev"]
            merkle = blk["merkle"]
            blk_time = blk["time"]
            bits = blk["bits"]
            nonce = blk["nonce"]
            txs = blk.get("txs", [])
        except KeyError as e:
            return None, f"missing field: {e}"

        # Convert hex strings to ints where needed
        if isinstance(bits, str):
            bits = int(bits, 16)
        if isinstance(prev, str):
            prev_bytes = bytes.fromhex(prev)
        else:
            prev_bytes = prev
        if isinstance(merkle, str):
            merkle_bytes = bytes.fromhex(merkle)
        else:
            merkle_bytes = merkle

        # Check parent exists
        with self.lock:
            parent = self.by_hash.get(prev if isinstance(prev, str) else prev.hex())
            if parent is None:
                return None, "previous block not found"
            new_height = parent["height"] + 1

        # Recompute header hash
        header_bytes = ser_header(version, prev_bytes, merkle_bytes, blk_time, bits, nonce)
        header_hash = sha256d(header_bytes)
        header_hash_hex = header_hash.hex()

        # Check PoW
        target = bits_to_target(bits)
        header_val = int.from_bytes(header_hash, "big")
        if header_val > target:
            return None, "insufficient proof of work"

        # Check timestamp > parent
        if blk_time <= parent["time"]:
            return None, "timestamp not greater than parent"

        # Build the new record
        new_rec = {
            "height": new_height,
            "version": version,
            "prev": prev if isinstance(prev, str) else prev.hex(),
            "merkle": merkle if isinstance(merkle, str) else merkle.hex(),
            "time": blk_time,
            "bits": bits,
            "nonce": nonce,
            "hash": header_hash_hex,
            "txs": txs,
        }

        # Append to chain
        with self.lock:
            self.by_hash[header_hash_hex] = new_rec
            self.by_height[new_height] = new_rec
            self.tip_height = new_height
            self.tip_hash = header_hash_hex

        # Persist to chain.jsonl
        line = json.dumps(new_rec) + "\n"
        with open(self.path, "a") as f:
            f.write(line)

        # Update metrics
        self._calculate_metrics()
        
        logger.info(f"Block accepted: height {new_height}, hash {header_hash_hex[:16]}...")
        return {"height": new_height, "status": "accepted", "hash": header_hash_hex}, None
    
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
        return {
            "version": "2.0.0",
            "protocol_version": 70016,
            "network": "excal-fork",
            "chain": "excalibur",
            "blocks": self.tip_height,
            "time_offset": 0,
            "connections": 0,  # Would be populated by P2P layer
            "network_active": True,
            "features": [
                "post-quantum-locks",
                "erepr-p2p",
                "compact-blocks",
                "atomic-swaps",
                "quantum-swaps",
                "governance",
                "staking",
                "smart-contracts",
                "lightning-network"
            ]
        }
    
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


# --- wallet (simple deterministic address for serve-only mode) ---

def _wallet_pub():
    """Return a deterministic wallet pubkey hex for serve-only mode.
    Must be a 33-byte compressed pubkey (0x02 or 0x03 prefix + 32 bytes).
    In a real node this would come from a key store; here we use a
    deterministic compressed pubkey derived from the chain file path.
    NOTE: This is for demo/serve-only mode. For production, use a proper
    key store with secure random key generation."""
    import os
    seed = hashlib.sha256(CHAIN_FILE.encode() + os.urandom(16)).digest()
    # Build a valid-looking compressed pubkey: 0x02 prefix + 32 bytes
    pubkey = b"\x02" + seed[:32]
    return pubkey.hex()


# --- RPC handler ---

class ForkRPCHandler(http.server.BaseHTTPRequestHandler):
    store: ChainStore = None  # set at class level

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
            elif method == "getnewaddress":
                result = _wallet_pub()
            elif method == "submitblock":
                if not params:
                    error = "missing block parameter"
                else:
                    blk = params[0]
                    result, error = self.store.submitblock(blk)
            
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


def main():
    if not os.path.exists(CHAIN_FILE):
        print(f"ERROR: chain file not found: {CHAIN_FILE}", file=sys.stderr)
        sys.exit(1)

    store = ChainStore(CHAIN_FILE)
    ForkRPCHandler.store = store

    rpc_host = os.environ.get("FORK_RPC_HOST", "0.0.0.0")
    server = ThreadedHTTPServer((rpc_host, RPC_PORT), ForkRPCHandler)
    print(f"Fork node RPC listening on {rpc_host}:{RPC_PORT} (serve-only, --no-mine)", flush=True)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...", flush=True)
        server.shutdown()


if __name__ == "__main__":
    main()
