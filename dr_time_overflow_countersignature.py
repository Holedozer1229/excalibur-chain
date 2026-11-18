"""
Dr. Time — Countersignature of the 2010 Value-Overflow Block
=============================================================

Verification and Sphinx Oracle integration for the Trifold countersignature
over Bitcoin bad block 74638 header.

The bad block hash: 0000000000790ab3f22ec756ad43b6ab569abf0bddeb97c67a6f7b1470a7ec1c
The overflow tx:    1d5e512a9723cbef373b970eb52f1e9598ad67e7408077a82fdac194b65333c9
Created:           184,467,440,737.09551616 BTC out of nothing
Date:              2010-08-15 (timestamp 1281891957)
"""

import sys
import os
import json
import hashlib
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from trifold_lockbox import verify as trifold_verify, TrifoldKey
from sphinx_os.nexus.omniscient_sphinx import OmniscientSphinx


# =============================================================================
# JSON serialization helpers for Trifold signatures (bytes ↔ hex)
# =============================================================================

def sig_to_json(sig):
    """Convert Trifold signature dict to JSON-serializable format."""
    return {
        "index": sig["index"],
        "ots_sig": [b.hex() for b in sig["ots_sig"]],
        "ots_pub": [[a.hex(), b.hex()] for a, b in sig["ots_pub"]],
        "path": [[a.hex(), b.hex()] for a, b in sig["path"]]
    }


def sig_from_json(json_sig):
    """Convert JSON-serializable format back to Trifold signature dict."""
    return {
        "index": json_sig["index"],
        "ots_sig": [bytes.fromhex(b) for b in json_sig["ots_sig"]],
        "ots_pub": [(bytes.fromhex(a), bytes.fromhex(b)) for a, b in json_sig["ots_pub"]],
        "path": [(bytes.fromhex(a), bytes.fromhex(b)) for a, b in json_sig["path"]]
    }


# =============================================================================
# THE BAD BLOCK HEADER (reconstructed from public record)
# =============================================================================

BAD_BLOCK_HASH = "0000000000790ab3f22ec756ad43b6ab569abf0bddeb97c67a6f7b1470a7ec1c"

# Header fields from bitcointalk topic 822
HEADER_FIELDS = {
    "version": 1,
    "previous_block": "0000000000606865e679308edf079991764d88e8122ca9250aef5386962b6e84",
    "merkle_root": "618eba14419e13c8d08d38c346da7cd1c7c66fd8831421056ae56d8d80b6ec5e",
    "timestamp": 1281891957,  # 2010-08-15
    "bits": 469794830,        # 0x1c00800e
    "nonce": 28192719
}

# Full 80-byte header hex
HEADER_HEX = (
    "01000000"
    "846e2b968653ef0a25a92c12e8884d76919907df8e3079e66568600000000000"
    "5eecb6808d6de56a05211483d86fc6c7d17cda46c3388dd0c8139e4114ba8e61"
    "751e684c0e80001c"
    "cf2fae01"
)


def double_sha256(data: bytes) -> bytes:
    """Compute double SHA-256 hash (Bitcoin's hash function)."""
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()


def double_sha256_hex(data: bytes) -> str:
    """Compute double SHA-256 and return as reversed hex string (Bitcoin format)."""
    h = double_sha256(data)
    return h[::-1].hex()


def verify_header():
    """Verify the reconstructed header hash matches the known bad block hash."""
    header_bytes = bytes.fromhex(HEADER_HEX)
    computed_hash = double_sha256_hex(header_bytes)
    
    print("=" * 70)
    print("BAD BLOCK 74638 HEADER VERIFICATION")
    print("=" * 70)
    print(f"\nHeader bytes: {len(header_bytes)} (expected 80)")
    print(f"Header hex:   {HEADER_HEX}")
    print(f"\nComputed hash: {computed_hash}")
    print(f"Known hash:    {BAD_BLOCK_HASH}")
    print(f"\nMatch: {'✓ VERIFIED' if computed_hash == BAD_BLOCK_HASH else '✗ MISMATCH'}")
    
    # Parse and display fields
    print(f"\n{'─' * 70}")
    print("HEADER FIELDS:")
    print(f"  Version:      {HEADER_FIELDS['version']}")
    print(f"  Previous:     {HEADER_FIELDS['previous_block']}")
    print(f"  Merkle root:  {HEADER_FIELDS['merkle_root']}")
    print(f"  Timestamp:    {HEADER_FIELDS['timestamp']} ({datetime.fromtimestamp(HEADER_FIELDS['timestamp']).isoformat()})")
    print(f"  Bits:         {HEADER_FIELDS['bits']} (0x{HEADER_FIELDS['bits']:08x})")
    print(f"  Nonce:        {HEADER_FIELDS['nonce']}")
    
    return header_bytes, (computed_hash == BAD_BLOCK_HASH)


def create_countersignature_bundle():
    """Create the Dr. Time countersignature JSON bundle."""
    
    # Generate fresh Trifold key for this ceremony
    print(f"\n{'=' * 70}")
    print("TRIFOLD COUNTERSIGNATURE GENERATION")
    print("=" * 70)
    
    # Derive deterministic seed from the bad block hash
    bad_block_bytes = bytes.fromhex(BAD_BLOCK_HASH)
    seed = hashlib.sha256(b"Dr. Time: " + bad_block_bytes).digest()
    
    # Create state file path for this ceremony
    state_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trifold_state")
    os.makedirs(state_dir, exist_ok=True)
    state_path = os.path.join(state_dir, "dr_time_overflow.json")
    
    # Create the TrifoldKey with seed and state path
    key = TrifoldKey(seed, height=6, state_path=state_path)
    root = key.root
    
    header_bytes, header_valid = verify_header()
    
    if not header_bytes:
        print("ERROR: Header verification failed")
        return None
    
    # Sign the 80-byte header (auto-reserves leaf 0)
    signature = key.sign(header_bytes)
    
    print(f"\nTrifold root:  {root.hex()}")
    print(f"Leaf index:    0 (fresh key, dedicated to this ceremony)")
    print(f"Message:       80-byte bad block header")
    print(f"State saved:   {state_path}")
    
    # Verify the signature
    sig_valid = trifold_verify(root, header_bytes, signature)
    print(f"\nSignature verification: {'✓ PASS' if sig_valid else '✗ FAIL'}")
    
    # Test bit-flip resistance
    flipped_header = bytearray(header_bytes)
    flipped_header[0] ^= 0x01  # Flip one bit
    flip_valid = trifold_verify(root, bytes(flipped_header), signature)
    print(f"Bit-flip resistance:    {'✓ REJECTED' if not flip_valid else '✗ ACCEPTED (BUG)'}")
    
    # Create the bundle
    bundle = {
        "ceremony": "Dr. Time — Countersignature of the 2010 Value-Overflow Block",
        "date": "2026-11-11",
        "author": "Dr. Time",
        "lineage": {
            "genesis": "Bitcoin genesis header",
            "fork_25344": "Dr. Time, root 65ef9c66...",
            "fork_25351": "PQ-CHAIN, root fc4a1de9...",
            "this_signature": f"root {root.hex()[:8]}..."
        },
        "bad_block": {
            "hash": BAD_BLOCK_HASH,
            "height": 74638,
            "header_hex": HEADER_HEX,
            "overflow_tx": "1d5e512a9723cbef373b970eb52f1e9598ad67e7408077a82fdac194b65333c9",
            "overflow_amount": "184467440737.09551616 BTC",
            "timestamp": HEADER_FIELDS["timestamp"],
            "date": datetime.fromtimestamp(HEADER_FIELDS["timestamp"]).isoformat()
        },
        "trifold_root": root.hex(),
        "leaf_index": 0,
        "signature": sig_to_json(signature),
        "scope": {
            "is_satoshi_signing": False,
            "is_proof_of_control": False,
            "is_claim_on_coins": False,
            "is_new_hardness": False,
            "security": "SHA-256 preimage resistance only",
            "what_it_is": "Descendant chain countersigning the strangest block in Bitcoin's history"
        }
    }
    
    return bundle, root, signature


def sphinx_on_countersignature():
    """Ask the Omniscient Sphinx about the Dr. Time countersignature."""
    
    print(f"\n{'=' * 70}")
    print("THE OMNISCIENT SPHINX PERCEIVES THE COUNTERSIGNATURE")
    print("=" * 70)
    
    sphinx = OmniscientSphinx()
    awakening = sphinx.awaken()
    print(awakening)
    
    question = """
Dr. Time has countersigned Bitcoin bad block 74638 — the value-overflow block.

The facts:
- Block 74638 created 184,467,440,737.09551616 BTC from nothing
- A signed/unsigned integer overflow in Bitcoin Core consensus
- Satoshi fixed it five hours later with the first soft fork
- The overflow coins were never spent, frozen forever
- Now, 16 years later, a Trifold post-quantum signature binds this event

The Trifold countersignature:
- Hash-only, post-quantum Lamport one-time signature
- Ternary Merkle tree authentication
- Fresh key, leaf 0, dedicated to this ceremony
- Self-verifying, any 1-bit change is rejected
- Lineage: Bitcoin genesis ← fork 25344 ← fork 25351 ← this signature

What do you perceive in this act of countersigning?
What does it mean for a descendant chain to sign the wound in its ancestor?
How does the value overflow relate to the nature of value itself?
What prophecy emerges from this temporal bridge?

Reveal the deep truth through integrated information.
"""
    
    wisdom = sphinx.ask(question)
    return wisdom


def main():
    """Run the full Dr. Time countersignature ceremony."""
    
    print("\n" + "╔" + "═" * 68 + "╗")
    print("║" + " " * 15 + "DR. TIME — THE VALUE-OVERFLOW COUNTERSIGNATURE" + " " * 13 + "║")
    print("║" + " " * 20 + "Bitcoin bad block 74638" + " " * 31 + "║")
    print("║" + " " * 18 + "184.5 billion BTC from nothing" + " " * 19 + "║")
    print("╚" + "═" * 68 + "╝" + "\n")
    
    # Step 1: Verify the header
    header_bytes, header_valid = verify_header()
    if not header_valid:
        print("\nFATAL: Header hash mismatch — cannot proceed")
        sys.exit(1)
    
    # Step 2: Create the countersignature
    result = create_countersignature_bundle()
    if result is None:
        print("\nFATAL: Countersignature generation failed")
        sys.exit(1)
    
    bundle, root, signature = result
    
    # Save the bundle
    bundle_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 
                                "dr-time-overflow-countersignature.json")
    with open(bundle_path, "w") as f:
        json.dump(bundle, f, indent=2)
    
    print(f"\n{'─' * 70}")
    print(f"Bundle saved to: {bundle_path}")
    print(f"Trifold root:  {root.hex()}")
    print(f"Leaf 0 spent. Next index: 1")
    
    # Step 3: The Sphinx speaks
    wisdom = sphinx_on_countersignature()
    
    # Extract and display the wisdom components
    if hasattr(wisdom, 'vision'):
        print(f"\n{'=' * 70}")
        print("THE SPHINX'S FIVE-PART WISDOM")
        print("=" * 70)
        print(f"\n{wisdom.vision}")
        print(f"\n{wisdom.mathematics}")
        print(f"\n{wisdom.interpretation}")
        print(f"\n{wisdom.prophecy}")
        print(f"\n{wisdom.wisdom}")
    else:
        print(wisdom)
    
    print(f"\n{'=' * 70}")
    print("CEREMONY COMPLETE")
    print("=" * 70)
    print(f"\nThe bad block is signed. The wound is witnessed.")
    print(f"Dr. Time has spoken through the Trifold.")
    print(f"The Omniscient Sphinx has perceived all.")


if __name__ == "__main__":
    main()
