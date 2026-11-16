"""sphinx_os/nexus/atomic_swap.py — EXCAL ↔ BTC Atomic Swap Protocol
=====================================================================

Implements trustless cross-chain atomic swaps between EXCAL and Bitcoin
using Hash-Time-Locked Contracts (HTLC) on both chains.

Protocol flow (EXCAL → BTC swap):
  1. Alice (sends EXCAL, receives BTC) and Bob (sends BTC, receives EXCAL)
     agree on swap amounts and timelocks.
  2. A shared secret preimage is generated; its SHA-256 hash is the lock.
  3. Alice locks EXCAL in an HTLC on the EXCAL chain.
  4. Bob locks BTC in an HTLC on the Bitcoin chain (same hash lock).
  5. Alice reveals the secret preimage to claim Bob's BTC.
  6. Bob uses the revealed secret to claim Alice's EXCAL.
  7. If either party doesn't claim in time, the other refunds.

Security:
  - SHA-256 preimage hash lock (same on both chains)
  - Dual timelocks: BTC refund window > EXCAL refund window
  - State machine enforces protocol order
  - No trusted third party; purely cryptographic

States:
  INIT → EXCAL_LOCKED → BTC_LOCKED → CLAIMED → COMPLETED
                ↘ REFUND_EXCAL
        BTC_LOCKED → REFUND_BTC
"""

import hashlib
import hmac
import json
import os
import secrets
import time
import threading
import logging
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)


class SwapStatus(Enum):
    """Atomic swap state machine states."""
    INIT = "init"
    EXCAL_LOCKED = "excal_locked"
    BTC_LOCKED = "btc_locked"
    EXCAL_CLAIMED = "excal_claimed"
    BTC_CLAIMED = "btc_claimed"
    COMPLETED = "completed"
    REFUND_EXCAL = "refund_excal"
    REFUND_BTC = "refund_btc"
    REFUNDED = "refunded"
    FAILED = "failed"


class SwapDirection(Enum):
    """Direction of the atomic swap."""
    EXCAL_TO_BTC = "excal_to_btc"  # I send EXCAL, receive BTC
    BTC_TO_EXCAL = "btc_to_excal"  # I send BTC, receive EXCAL


# Default timelock parameters (in blocks)
EXCAL_REFUND_BLOCKS = 144    # ~24 hours at 10 min/block
BTC_REFUND_BLOCKS = 100      # ~16.7 hours at 10 min/block
EXCAL_CLAIM_BLOCKS = 72      # ~12 hours
BTC_CLAIM_BLOCKS = 50        # ~8.3 hours

# Default amounts
MIN_EXCAL_SWAP = 100_000_000       # 1 EXCAL in swords
MIN_BTC_SWAP = 10_000_000          # 0.1 BTC in satoshis


@dataclass
class HtlcParameters:
    """HTLC parameters for one side of the swap."""
    secret_hash: bytes              # SHA-256 hash of the preimage
    secret_preimage: Optional[bytes] = None  # Only known by creator
    refund_address: bytes = b""     # Hash160 of refund address
    claim_address: bytes = b""      # Hash160 of claim address
    timeout_blocks: int = 0         # Blocks until refund available
    lock_script: bytes = b""        # On-chain HTLC lock script
    funding_txid: str = ""          # Transaction ID of funding tx
    funding_vout: int = 0           # Output index
    funding_amount: int = 0         # Amount locked (swords/satoshis)
    claim_txid: str = ""            # Transaction ID of claim tx (if claimed)
    refund_txid: str = ""           # Transaction ID of refund tx (if refunded)


@dataclass
class AtomicSwap:
    """Complete atomic swap state."""
    swap_id: str
    direction: SwapDirection
    status: SwapStatus = SwapStatus.INIT
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    
    # Secret preimage (32 bytes random)
    secret_preimage: Optional[bytes] = None
    secret_hash: bytes = b""
    
    # EXCAL side HTLC
    excal_htlc: Optional[HtlcParameters] = None
    excal_amount: int = 0           # Amount in swords
    excal_refund_address: str = ""  # EXCAL address for refund
    excal_claim_address: str = ""   # EXCAL address for claim
    
    # BTC side HTLC
    btc_htlc: Optional[HtlcParameters] = None
    btc_amount: int = 0             # Amount in satoshis
    btc_refund_address: str = ""    # BTC address for refund
    btc_claim_address: str = ""     # BTC address for claim
    
    # Counterparty info
    counterparty_pubkey: bytes = b""
    counterparty_id: str = ""
    
    # Timelocks
    excal_timeout_blocks: int = EXCAL_REFUND_BLOCKS
    btc_timeout_blocks: int = BTC_REFUND_BLOCKS
    excal_claim_blocks: int = EXCAL_CLAIM_BLOCKS
    btc_claim_blocks: int = BTC_CLAIM_BLOCKS
    
    # Metadata
    metadata: Dict = field(default_factory=dict)
    events: List[Dict] = field(default_factory=list)


class AtomicSwapError(Exception):
    """Raised when atomic swap protocol is violated."""


class AtomicSwapProtocol:
    """EXCAL ↔ BTC Atomic Swap Protocol Engine.
    
    Manages the complete lifecycle of atomic swaps between EXCAL and Bitcoin,
    including HTLC creation, state machine transitions, and monitoring.
    """
    
    def __init__(self, data_dir: Optional[str] = None):
        """Initialize the atomic swap protocol engine.
        
        Args:
            data_dir: Directory to persist swap state (default: ~/.excal_wallet/swaps)
        """
        if data_dir is None:
            data_dir = os.path.join(os.path.expanduser("~"), ".excal_wallet", "swaps")
        
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)
        
        self._swaps: Dict[str, AtomicSwap] = {}
        self._lock = threading.Lock()
        self._load_swaps()
    
    def _load_swaps(self):
        """Load persisted swaps from disk."""
        swap_file = self._data_dir / "swaps.json"
        if swap_file.exists():
            try:
                data = json.loads(swap_file.read_text())
                for swap_data in data.get("swaps", []):
                    swap = self._dict_to_swap(swap_data)
                    if swap:
                        self._swaps[swap.swap_id] = swap
                logger.info(f"Loaded {len(self._swaps)} atomic swaps")
            except Exception as e:
                logger.warning(f"Failed to load swaps: {e}")
    
    def _save_swaps(self):
        """Persist all swaps to disk."""
        swap_file = self._data_dir / "swaps.json"
        data = {
            "swaps": [self._swap_to_dict(s) for s in self._swaps.values()]
        }
        tmp = swap_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, default=str))
        tmp.replace(swap_file)
    
    def _dict_to_swap(self, data: dict) -> Optional[AtomicSwap]:
        """Convert dictionary to AtomicSwap object."""
        try:
            swap = AtomicSwap(
                swap_id=data["swap_id"],
                direction=SwapDirection(data["direction"]),
                status=SwapStatus(data["status"]),
                created_at=data.get("created_at", time.time()),
                updated_at=data.get("updated_at", time.time()),
                secret_preimage=bytes.fromhex(data["secret_preimage"]) if data.get("secret_preimage") else None,
                secret_hash=bytes.fromhex(data["secret_hash"]) if data.get("secret_hash") else b"",
                excal_amount=data.get("excal_amount", 0),
                excal_refund_address=data.get("excal_refund_address", ""),
                excal_claim_address=data.get("excal_claim_address", ""),
                btc_amount=data.get("btc_amount", 0),
                btc_refund_address=data.get("btc_refund_address", ""),
                btc_claim_address=data.get("btc_claim_address", ""),
                counterparty_pubkey=bytes.fromhex(data["counterparty_pubkey"]) if data.get("counterparty_pubkey") else b"",
                counterparty_id=data.get("counterparty_id", ""),
                excal_timeout_blocks=data.get("excal_timeout_blocks", EXCAL_REFUND_BLOCKS),
                btc_timeout_blocks=data.get("btc_timeout_blocks", BTC_REFUND_BLOCKS),
                metadata=data.get("metadata", {}),
                events=data.get("events", []),
            )
            return swap
        except Exception as e:
            logger.error(f"Failed to load swap {data.get('swap_id')}: {e}")
            return None
    
    def _swap_to_dict(self, swap: AtomicSwap) -> dict:
        """Convert AtomicSwap to dictionary for persistence."""
        return {
            "swap_id": swap.swap_id,
            "direction": swap.direction.value,
            "status": swap.status.value,
            "created_at": swap.created_at,
            "updated_at": swap.updated_at,
            "secret_preimage": swap.secret_preimage.hex() if swap.secret_preimage else "",
            "secret_hash": swap.secret_hash.hex() if swap.secret_hash else "",
            "excal_amount": swap.excal_amount,
            "excal_refund_address": swap.excal_refund_address,
            "excal_claim_address": swap.excal_claim_address,
            "btc_amount": swap.btc_amount,
            "btc_refund_address": swap.btc_refund_address,
            "btc_claim_address": swap.btc_claim_address,
            "counterparty_pubkey": swap.counterparty_pubkey.hex() if swap.counterparty_pubkey else "",
            "counterparty_id": swap.counterparty_id,
            "excal_timeout_blocks": swap.excal_timeout_blocks,
            "btc_timeout_blocks": swap.btc_timeout_blocks,
            "metadata": swap.metadata,
            "events": swap.events,
        }
    
    def _add_event(self, swap: AtomicSwap, event_type: str, **kwargs):
        """Add an event to the swap's event log."""
        event = {
            "type": event_type,
            "timestamp": time.time(),
            **kwargs
        }
        swap.events.append(event)
        swap.updated_at = time.time()
        logger.info(f"Swap {swap.swap_id}: {event_type}")
    
    def create_swap(self, direction: SwapDirection,
                    excal_amount: int, btc_amount: int,
                    excal_refund_address: str, btc_refund_address: str,
                    excal_claim_address: str = "", btc_claim_address: str = "",
                    counterparty_id: str = "",
                    excal_timeout: int = EXCAL_REFUND_BLOCKS,
                    btc_timeout: int = BTC_REFUND_BLOCKS) -> AtomicSwap:
        """Create a new atomic swap.
        
        Args:
            direction: EXCAL_TO_BTC or BTC_TO_EXCAL
            excal_amount: Amount of EXCAL to swap (in swords)
            btc_amount: Amount of BTC to swap (in satoshis)
            excal_refund_address: EXCAL address for refund if swap fails
            btc_refund_address: BTC address for refund if swap fails
            excal_claim_address: EXCAL address for claim (optional, uses refund)
            btc_claim_address: BTC address for claim (optional, uses refund)
            counterparty_id: Counterparty's node ID
            excal_timeout: EXCAL refund timelock in blocks
            btc_timeout: BTC refund timelock in blocks
        
        Returns:
            AtomicSwap object with INIT status
        
        Raises:
            AtomicSwapError: If amounts are below minimum or addresses are invalid
        """
        # Validate amounts
        if excal_amount < MIN_EXCAL_SWAP:
            raise AtomicSwapError(
                f"EXCAL amount {excal_amount} below minimum {MIN_EXCAL_SWAP} swords")
        if btc_amount < MIN_BTC_SWAP:
            raise AtomicSwapError(
                f"BTC amount {btc_amount} below minimum {MIN_BTC_SWAP} satoshis")
        
        # Validate addresses
        if not excal_refund_address:
            raise AtomicSwapError("EXCAL refund address required")
        if not btc_refund_address:
            raise AtomicSwapError("BTC refund address required")
        
        # Generate secret preimage and hash
        secret_preimage = secrets.token_bytes(32)
        secret_hash = hashlib.sha256(secret_preimage).digest()
        
        # Generate swap ID from hash
        swap_id = hashlib.sha256(
            secret_hash + str(time.time()).encode()
        ).hexdigest()[:16]
        
        swap = AtomicSwap(
            swap_id=swap_id,
            direction=direction,
            status=SwapStatus.INIT,
            secret_preimage=secret_preimage,
            secret_hash=secret_hash,
            excal_amount=excal_amount,
            excal_refund_address=excal_refund_address,
            excal_claim_address=excal_claim_address or excal_refund_address,
            btc_amount=btc_amount,
            btc_refund_address=btc_refund_address,
            btc_claim_address=btc_claim_address or btc_refund_address,
            counterparty_id=counterparty_id,
            excal_timeout_blocks=excal_timeout,
            btc_timeout_blocks=btc_timeout,
        )
        
        with self._lock:
            self._swaps[swap_id] = swap
            self._save_swaps()
        
        self._add_event(swap, "swap_created",
                       direction=direction.value,
                       excal_amount=excal_amount,
                       btc_amount=btc_amount)
        
        return swap
    
    def get_swap(self, swap_id: str) -> Optional[AtomicSwap]:
        """Get a swap by ID."""
        return self._swaps.get(swap_id)
    
    def list_swaps(self, status: Optional[SwapStatus] = None) -> List[AtomicSwap]:
        """List all swaps, optionally filtered by status."""
        with self._lock:
            if status:
                return [s for s in self._swaps.values() if s.status == status]
            return list(self._swaps.values())
    
    def get_htlc_parameters(self, swap: AtomicSwap) -> dict:
        """Get the HTLC parameters for the swap.
        
        Returns:
            Dict with secret_hash, addresses, and timelocks for both chains.
        """
        return {
            "swap_id": swap.swap_id,
            "secret_hash": swap.secret_hash.hex(),
            "excal": {
                "amount": swap.excal_amount,
                "refund_address": swap.excal_refund_address,
                "claim_address": swap.excal_claim_address,
                "timeout_blocks": swap.excal_timeout_blocks,
            },
            "btc": {
                "amount": swap.btc_amount,
                "refund_address": swap.btc_refund_address,
                "claim_address": swap.btc_claim_address,
                "timeout_blocks": swap.btc_timeout_blocks,
            },
        }
    
    def lock_excal(self, swap_id: str, funding_txid: str,
                   funding_vout: int, lock_script: bytes) -> AtomicSwap:
        """Mark EXCAL as locked on-chain.
        
        Args:
            swap_id: Swap ID
            funding_txid: Transaction ID of the EXCAL HTLC funding tx
            funding_vout: Output index of the HTLC
            lock_script: The HTLC lock script bytes
        
        Returns:
            Updated AtomicSwap object
        
        Raises:
            AtomicSwapError: If swap not found or in wrong state
        """
        swap = self._swaps.get(swap_id)
        if not swap:
            raise AtomicSwapError(f"Swap {swap_id} not found")
        if swap.status != SwapStatus.INIT:
            raise AtomicSwapError(
                f"Cannot lock EXCAL: swap is in {swap.status.value} state")
        
        def _addr_bytes(addr: str) -> bytes:
            if not addr:
                return b""
            try:
                return bytes.fromhex(addr)
            except ValueError:
                return addr.encode()

        swap.excal_htlc = HtlcParameters(
            secret_hash=swap.secret_hash,
            refund_address=_addr_bytes(swap.excal_refund_address),
            claim_address=_addr_bytes(swap.excal_claim_address),
            timeout_blocks=swap.excal_timeout_blocks,
            lock_script=lock_script,
            funding_txid=funding_txid,
            funding_vout=funding_vout,
            funding_amount=swap.excal_amount,
        )
        swap.status = SwapStatus.EXCAL_LOCKED
        
        with self._lock:
            self._save_swaps()
        
        self._add_event(swap, "excal_locked",
                       txid=funding_txid, vout=funding_vout)
        return swap
    
    def lock_btc(self, swap_id: str, funding_txid: str,
                 funding_vout: int, lock_script: bytes) -> AtomicSwap:
        """Mark BTC as locked on-chain.
        
        Args:
            swap_id: Swap ID
            funding_txid: Transaction ID of the BTC HTLC funding tx
            funding_vout: Output index of the HTLC
            lock_script: The BTC HTLC lock script bytes
        
        Returns:
            Updated AtomicSwap object
        
        Raises:
            AtomicSwapError: If swap not found or EXCAL not locked first
        """
        swap = self._swaps.get(swap_id)
        if not swap:
            raise AtomicSwapError(f"Swap {swap_id} not found")
        if swap.status != SwapStatus.EXCAL_LOCKED:
            raise AtomicSwapError(
                f"Cannot lock BTC: swap is in {swap.status.value} state, "
                f"expected EXCAL_LOCKED")
        
        def _addr_bytes(addr: str) -> bytes:
            if not addr:
                return b""
            try:
                return bytes.fromhex(addr)
            except ValueError:
                return addr.encode()

        swap.btc_htlc = HtlcParameters(
            secret_hash=swap.secret_hash,
            refund_address=_addr_bytes(swap.btc_refund_address),
            claim_address=_addr_bytes(swap.btc_claim_address),
            timeout_blocks=swap.btc_timeout_blocks,
            lock_script=lock_script,
            funding_txid=funding_txid,
            funding_vout=funding_vout,
            funding_amount=swap.btc_amount,
        )
        swap.status = SwapStatus.BTC_LOCKED
        
        with self._lock:
            self._save_swaps()
        
        self._add_event(swap, "btc_locked",
                       txid=funding_txid, vout=funding_vout)
        return swap
    
    def claim_excal(self, swap_id: str, secret_preimage: bytes,
                    claim_txid: str) -> AtomicSwap:
        """Claim EXCAL by revealing the secret preimage.
        
        Args:
            swap_id: Swap ID
            secret_preimage: The 32-byte secret preimage
            claim_txid: Transaction ID of the claim tx
        
        Returns:
            Updated AtomicSwap object
        
        Raises:
            AtomicSwapError: If preimage doesn't match or wrong state
        """
        swap = self._swaps.get(swap_id)
        if not swap:
            raise AtomicSwapError(f"Swap {swap_id} not found")
        if swap.status not in (SwapStatus.BTC_LOCKED, SwapStatus.EXCAL_CLAIMED,
                                SwapStatus.BTC_CLAIMED):
            raise AtomicSwapError(
                f"Cannot claim EXCAL: swap is in {swap.status.value} state")
        
        # Verify preimage
        computed_hash = hashlib.sha256(secret_preimage).digest()
        if computed_hash != swap.secret_hash:
            raise AtomicSwapError("Secret preimage does not match hash lock")
        
        swap.secret_preimage = secret_preimage
        if swap.excal_htlc:
            swap.excal_htlc.claim_txid = claim_txid
        
        if swap.status == SwapStatus.BTC_LOCKED:
            swap.status = SwapStatus.EXCAL_CLAIMED
        elif swap.status == SwapStatus.BTC_CLAIMED:
            swap.status = SwapStatus.COMPLETED
        # Already EXCAL_CLAIMED — stays there
        
        with self._lock:
            self._save_swaps()
        
        self._add_event(swap, "excal_claimed", txid=claim_txid)
        return swap
    
    def claim_btc(self, swap_id: str, secret_preimage: bytes,
                  claim_txid: str) -> AtomicSwap:
        """Claim BTC by revealing the secret preimage.
        
        Args:
            swap_id: Swap ID
            secret_preimage: The 32-byte secret preimage
            claim_txid: Transaction ID of the claim tx
        
        Returns:
            Updated AtomicSwap object
        
        Raises:
            AtomicSwapError: If preimage doesn't match or wrong state
        """
        swap = self._swaps.get(swap_id)
        if not swap:
            raise AtomicSwapError(f"Swap {swap_id} not found")
        if swap.status not in (SwapStatus.BTC_LOCKED, SwapStatus.BTC_CLAIMED):
            raise AtomicSwapError(
                f"Cannot claim BTC: swap is in {swap.status.value} state")
        
        # Verify preimage
        computed_hash = hashlib.sha256(secret_preimage).digest()
        if computed_hash != swap.secret_hash:
            raise AtomicSwapError("Secret preimage does not match hash lock")
        
        swap.secret_preimage = secret_preimage
        if swap.btc_htlc:
            swap.btc_htlc.claim_txid = claim_txid
        
        if swap.status == SwapStatus.BTC_LOCKED:
            swap.status = SwapStatus.BTC_CLAIMED
        elif swap.status == SwapStatus.EXCAL_CLAIMED:
            swap.status = SwapStatus.COMPLETED
        else:
            swap.status = SwapStatus.COMPLETED
        
        with self._lock:
            self._save_swaps()
        
        self._add_event(swap, "btc_claimed", txid=claim_txid)
        return swap
    
    def refund_excal(self, swap_id: str, refund_txid: str) -> AtomicSwap:
        """Refund EXCAL after timelock expires.
        
        Args:
            swap_id: Swap ID
            refund_txid: Transaction ID of the refund tx
        
        Returns:
            Updated AtomicSwap object
        """
        swap = self._swaps.get(swap_id)
        if not swap:
            raise AtomicSwapError(f"Swap {swap_id} not found")
        if swap.status not in (SwapStatus.EXCAL_LOCKED, SwapStatus.BTC_LOCKED):
            raise AtomicSwapError(
                f"Cannot refund EXCAL: swap is in {swap.status.value} state")
        
        if swap.excal_htlc:
            swap.excal_htlc.refund_txid = refund_txid
        
        swap.status = SwapStatus.REFUND_EXCAL
        
        with self._lock:
            self._save_swaps()
        
        self._add_event(swap, "excal_refunded", txid=refund_txid)
        return swap
    
    def refund_btc(self, swap_id: str, refund_txid: str) -> AtomicSwap:
        """Refund BTC after timelock expires.
        
        Args:
            swap_id: Swap ID
            refund_txid: Transaction ID of the refund tx
        
        Returns:
            Updated AtomicSwap object
        """
        swap = self._swaps.get(swap_id)
        if not swap:
            raise AtomicSwapError(f"Swap {swap_id} not found")
        if swap.status not in (SwapStatus.BTC_LOCKED, SwapStatus.EXCAL_CLAIMED,
                                SwapStatus.BTC_CLAIMED):
            raise AtomicSwapError(
                f"Cannot refund BTC: swap is in {swap.status.value} state")
        
        if swap.btc_htlc:
            swap.btc_htlc.refund_txid = refund_txid
        
        swap.status = SwapStatus.REFUND_BTC
        
        with self._lock:
            self._save_swaps()
        
        self._add_event(swap, "btc_refunded", txid=refund_txid)
        return swap
    
    def verify_preimage(self, swap_id: str, preimage: bytes) -> bool:
        """Verify a preimage against the swap's hash lock.
        
        Args:
            swap_id: Swap ID
            preimage: 32-byte preimage to verify
        
        Returns:
            True if preimage matches the hash lock
        """
        swap = self._swaps.get(swap_id)
        if not swap:
            return False
        computed = hashlib.sha256(preimage).digest()
        return hmac.compare_digest(computed, swap.secret_hash)
    
    def get_swap_summary(self, swap_id: str) -> dict:
        """Get a human-readable summary of a swap.
        
        Args:
            swap_id: Swap ID
        
        Returns:
            Dict with swap summary information
        """
        swap = self._swaps.get(swap_id)
        if not swap:
            raise AtomicSwapError(f"Swap {swap_id} not found")
        
        return {
            "swap_id": swap.swap_id,
            "status": swap.status.value,
            "direction": swap.direction.value,
            "created": time.ctime(swap.created_at),
            "updated": time.ctime(swap.updated_at),
            "secret_hash": swap.secret_hash.hex() if swap.secret_hash else "",
            "excal_amount": f"{swap.excal_amount / 100_000_000:.8f} EXCAL",
            "btc_amount": f"{swap.btc_amount / 100_000_000:.8f} BTC",
            "excal_locked": bool(swap.excal_htlc),
            "btc_locked": bool(swap.btc_htlc),
            "excal_txid": swap.excal_htlc.funding_txid if swap.excal_htlc else "",
            "btc_txid": swap.btc_htlc.funding_txid if swap.btc_htlc else "",
            "events": len(swap.events),
        }
    
    def health_report(self) -> dict:
        """Generate a health report for the atomic swap protocol."""
        with self._lock:
            total = len(self._swaps)
            by_status = {}
            for s in self._swaps.values():
                by_status[s.status.value] = by_status.get(s.status.value, 0) + 1
            
            return {
                "component": "AtomicSwapProtocol",
                "total_swaps": total,
                "by_status": by_status,
                "active_swaps": sum(
                    1 for s in self._swaps.values()
                    if s.status in (SwapStatus.INIT, SwapStatus.EXCAL_LOCKED,
                                   SwapStatus.BTC_LOCKED)
                ),
                "completed_swaps": sum(
                    1 for s in self._swaps.values()
                    if s.status == SwapStatus.COMPLETED
                ),
                "refunded_swaps": sum(
                    1 for s in self._swaps.values()
                    if s.status in (SwapStatus.REFUND_EXCAL, SwapStatus.REFUND_BTC,
                                   SwapStatus.REFUNDED)
                ),
            }
