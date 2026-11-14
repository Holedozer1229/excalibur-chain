"""BTC Burn Wormhole — Maps Bitcoin burns to quantum wormhole events.

Monitors known BTC burn addresses via mempool.space API and maps each burn
to a quantum wormhole event in the spacetime fabric. Collects burned BTC
value as EXCAL on the bonding curve.
"""

import hashlib
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np

from sphinx_os.nexus.quantum_spacetime import QuantumSpacetimeFabric, WormholeEvent
from sphinx_os.nexus.bonding_curve import CustomBondingCurve as BondingCurve


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------

@dataclass
class BurnTransaction:
    """A Bitcoin burn transaction."""
    txid: str
    address: str
    amount_btc: float
    amount_sats: int
    block_height: Optional[int] = None
    timestamp: Optional[int] = None


@dataclass
class BurnWormholeEvent:
    """A burn mapped to a wormhole event."""
    burn: BurnTransaction
    wormhole: WormholeEvent
    excal_collected: float
    fabric_step: int


# Known burn addresses
# Includes legacy (Base58) and SegWit (bech32) burn addresses.
#
# DECODING ANALYSIS (using f=9 bech32 insight):
#
# Bech32 burn addresses use repeating patterns:
#   'q' = 0 in bech32 (all-zero witness program)
#   'f' = 9 in bech32 (pattern 0x4A 0x52 0x94 0xA5 0x29 repeating)
#   The 5-bit encoding creates clean repeating byte patterns
#
# Base58 addresses analyzed:
#   1111111111111111111114oLvT2 -> Payload is ALL ZEROS (20x 0x00)
#     This is the Base58 equivalent of the bech32 'q' pattern
#   1BitcoinEaterAddressDontSendf59kuE -> Payload: 759d6677091e973b9e9d99f19c68fbf43e3f05f9
#     No simple repeating pattern in payload bytes
#   1CounterpartyXXXXXXXXXXXXXXXUWLpVr -> Payload: 818895f3dc2c178629d3d2d8fa3ec4a3f8179821
#     Has 15 repeating 'X' chars but no clean byte pattern
#
# INVALID ADDRESSES (removed from list):
#   1EaterXXXXXXXXXXXXXXXXXXXXXXXXXXXXX -> 21-byte payload (should be 20), invalid checksum
#   1BurnBurnBurnBurnBurnBurnBurnBurnXb -> 21-byte payload (should be 20), invalid checksum
#   In Base58, each char = log2(58) ~ 5.857 bits, so repeating chars don't create
#   clean byte patterns like bech32 does. The checksum constraint makes pure
#   repeating patterns virtually impossible in Base58.
#
# τ(28) = 24647168 is used as a script parameter for burn detection
BURN_ADDRESSES = [
    # Legacy Base58 burn addresses (valid checksums confirmed)
    "1CounterpartyXXXXXXXXXXXXXXXUWLpVr",  # Counterparty protocol, 2131 BTC burned
    "1111111111111111111114oLvT2",  # All-zero hash payload, 809 BTC burned
    "1BitcoinEaterAddressDontSendf59kuE",  # Satoshi-era burn, 13,419 BTC burned
    # Bech32 burn addresses (repeating 'q' = all-zero witness program)
    "bc1qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqthqst8",  # P2WSH all-zeros (32 bytes)
    "bc1qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqq9e75rs",  # P2WPKH all-zeros (20 bytes)
    # Bech32 burn addresses (repeating 'f' = 9 in bech32, witness program 0x4A5294A529 repeating)
    "bc1qfffffffffffffffffffffffffffffffffffffffffffffffffffqe708k7",  # P2WSH f-pattern (32 bytes)
    "bc1qffffffffffffffffffffffffffffffff82jzwn",  # P2WPKH f-pattern (20 bytes)
]

# τ(28) Ramanujan tau function value - used as script parameter for burn detection
# tau(28) = tau(4)*tau(7) = -1472 * -16744 = 24647168 (multiplicative property, gcd(4,7)=1)
TAU_28 = 24647168


def encode_script_num(value: int) -> bytes:
    """Encode an integer as a Bitcoin script number."""
    if value == 0:
        return b""
    neg = value < 0
    a = abs(value)
    out = bytearray()
    while a:
        out.append(a & 0xFF)
        a >>= 8
    if out[-1] & 0x80:
        out.append(0x80 if neg else 0x00)
    elif neg:
        out[-1] |= 0x80
    return bytes(out)


def create_tau28_burn_script() -> bytes:
    """Create a burn script using τ(28) as a script parameter.

    Returns a simple script that pushes τ(28) = 24647168 onto the stack.
    This can be used to identify burns associated with the Messerene pattern.
    """
    # Push tau(28) as a script number
    tau_bytes = encode_script_num(TAU_28)
    return bytes([len(tau_bytes)]) + tau_bytes


# ---------------------------------------------------------------------------
# BTC Burn Wormhole
# ---------------------------------------------------------------------------

class BTCBurnWormhole:
    """Monitors BTC burns and maps them to quantum wormhole events.

    Args:
        burn_addresses: List of burn addresses to monitor.
        seed: Random seed for fabric.
    """

    def __init__(self, burn_addresses: Optional[List[str]] = None,
                 seed: Optional[int] = None):
        self.burn_addresses = burn_addresses or BURN_ADDRESSES
        self.fabric = QuantumSpacetimeFabric(seed=seed)
        self.curve = BondingCurve()
        self.burn_events: List[BurnWormholeEvent] = []
        self.rng = np.random.RandomState(seed)

    def fetch_burns(self) -> List[BurnTransaction]:
        """Fetch burn transactions from mempool.space API.

        Returns:
            List of burn transactions.
        """
        burns = []
        import requests

        for address in self.burn_addresses:
            try:
                url = f"https://mempool.space/api/address/{address}/txs"
                resp = requests.get(url, timeout=10)
                if resp.status_code != 200:
                    continue
                txs = resp.json()[:5]  # Last 5 txs per address
                for tx in txs:
                    # Find vout to burn address
                    for vout in tx.get('vout', []):
                        for out in vout.get('spent', False) or [vout]:
                            scripts = out.get('scriptpubkey_address', '')
                            if scripts == address:
                                sats = out.get('value', 0)
                                burns.append(BurnTransaction(
                                    txid=tx['txid'],
                                    address=address,
                                    amount_btc=sats / 100_000_000,
                                    amount_sats=sats,
                                    block_height=tx.get('status', {}).get('block_height'),
                                    timestamp=tx.get('status', {}).get('block_time'),
                                ))
            except Exception:
                continue

        return burns

    def map_to_wormhole(self, burn: BurnTransaction) -> Optional[BurnWormholeEvent]:
        """Map a burn transaction to a wormhole event.

        Args:
            burn: The burn transaction.

        Returns:
            BurnWormholeEvent or None if no wormhole formed.
        """
        # Use TXID as seed for fabric evolution
        seed_bytes = hashlib.sha256(burn.txid.encode()).digest()
        seed_int = int.from_bytes(seed_bytes[:4], 'big')

        # Evolve fabric
        self.fabric.rng = np.random.RandomState(seed_int)
        wormholes = self.fabric.evolve(num_steps=10)

        if not wormholes:
            # Force a wormhole for the burn event
            wh = WormholeEvent(
                endpoint_a=0,
                endpoint_b=1,
                entanglement_entropy=0.7,
                formation_step=self.fabric.step,
                curvature=1.0,
            )
            wormholes = [wh]
            self.fabric.wormholes.append(wh)
            self.fabric.active_wormholes.append(wh)

        # Collect EXCAL based on burn amount
        excal_per_sat = 0.1  # 0.1 EXCAL per satoshi burned
        excal_collected = burn.amount_sats * excal_per_sat

        event = BurnWormholeEvent(
            burn=burn,
            wormhole=wormholes[0],
            excal_collected=excal_collected,
            fabric_step=self.fabric.step,
        )
        self.burn_events.append(event)
        return event

    def collect_excal(self, event: BurnWormholeEvent) -> float:
        """Collect EXCAL from a burn wormhole event.

        Args:
            event: The burn wormhole event.

        Returns:
            EXCAL amount collected.
        """
        # Add to bonding curve
        self.curve.add_liquidity(event.excal_collected)
        return event.excal_collected
