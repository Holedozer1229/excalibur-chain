#!/usr/bin/env python3
"""demo_btc_burn_recovery.py — Proof-of-Burn recovery demo.

Shows the 6-step recovery pipeline: burn → verify → mint → swap → recover.
"""
import os
import sys
import hashlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sphinx_os.nexus.btc_burn_wormhole_recovery import BTCBurnRecovery, BurnProof


def main():
    print("\n" + "="*60)
    print("  BTC BURN WORMHOLE RECOVERY DEMO")
    print("="*60 + "\n")

    recovery = BTCBurnRecovery(seed=42)

    # Step 1: Generate burn address
    secret = hashlib.sha256(b"my_secret_wormhole_key").digest()
    burn_addr = recovery.generate_burn_address(secret)
    print(f"1. Burn address: {burn_addr}")

    # Step 2: Simulate burn
    txid = hashlib.sha256(b"simulated_burn_tx").hexdigest()
    amount_sats = 1000  # 0.00001 BTC
    print(f"2. Burned: {amount_sats / 100_000_000:.8f} BTC (TXID: {txid[:16]}...)")

    # Step 3: Verify proof
    valid = recovery.verify_burn_proof(txid, secret, burn_addr)
    print(f"3. Proof verified: {'✓' if valid else '✗'}")

    # Step 4: Mint EXCAL
    proof = BurnProof(
        secret_key=secret, burn_address=burn_addr,
        txid=txid, amount_sats=amount_sats,
        proof_hash=hashlib.sha256(f"{txid}{secret}".encode()).hexdigest(),
    )
    excal = recovery.mint_excal(proof)
    print(f"4. EXCAL minted: {excal:.0f}")

    # Step 5: Recover BTC
    result = recovery.recover_btc(proof, "1RecoveryAddressXXXXXXXXXXXXXX", excal)
    print(f"5. BTC recovered: {result.btc_recovered:.8f}")
    print(f"6. Swap TXID: {result.swap_txid[:16] if result.swap_txid else 'N/A'}...")


if __name__ == "__main__":
    main()
