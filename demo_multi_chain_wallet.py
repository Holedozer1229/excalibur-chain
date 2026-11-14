#!/usr/bin/env python3
"""Demo: Multi-Chain Wallet Receiver.

This script demonstrates the multi-chain wallet receiver, generating
addresses for Bitcoin, EXCAL, Monero, Tari, and Qubic from a single
master seed, then showing the balance dashboard.

Usage:
    python demo_multi_chain_wallet.py
"""

import sys
import os
import json
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sphinx_os.nexus.multi_chain_wallet import (
    ChainType,
    WalletGenerator,
    BalanceMonitor,
    TransactionAlert,
    export_wallet,
    import_wallet,
    create_multi_chain_wallet,
    create_wallet_monitor,
)


def main():
    print("=" * 70)
    print("  MULTI-CHAIN WALLET RECEIVER DEMO")
    print("=" * 70)
    print()

    # -----------------------------------------------------------------------
    # 1. Generate wallets from a single master seed
    # -----------------------------------------------------------------------
    print("1. Generating multi-chain wallets from a single master seed...")
    print()

    master_seed = bytes.fromhex(
        "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    )
    wallet = create_multi_chain_wallet(label="My Multi-Chain Wallet", master_seed=master_seed)

    print(f"   Master Seed: {wallet.master_seed_hex[:16]}...")
    print(f"   Label: {wallet.label}")
    print(f"   Chains: {len(wallet.wallets)}")
    print()

    # -----------------------------------------------------------------------
    # 2. Display all generated addresses
    # -----------------------------------------------------------------------
    print("2. Generated Addresses:")
    print()

    for chain in ChainType:
        chain_wallet = wallet.wallets.get(chain)
        if chain_wallet:
            print(f"   {chain.value.upper():8s} | {chain_wallet.address}")

    print()

    # -----------------------------------------------------------------------
    # 3. Show EXCAL address details
    # -----------------------------------------------------------------------
    print("3. EXCAL Address Details:")
    print()

    excal_wallet = wallet.wallets.get(ChainType.EXCAL)
    if excal_wallet:
        print(f"   Address: {excal_wallet.address}")
        print(f"   Public Key: {excal_wallet.public_key[:32]}...")
        print(f"   Derivation: {excal_wallet.derivation_path}")
        print(f"   Network: {excal_wallet.metadata.get('network', 'unknown')}")
        print(f"   Type: {excal_wallet.metadata.get('type', 'unknown')}")

    print()

    # -----------------------------------------------------------------------
    # 4. Show BTC address details
    # -----------------------------------------------------------------------
    print("4. Bitcoin Address Details:")
    print()

    btc_wallet = wallet.wallets.get(ChainType.BTC)
    if btc_wallet:
        print(f"   Address: {btc_wallet.address}")
        print(f"   Public Key: {btc_wallet.public_key[:32]}...")
        print(f"   Derivation: {btc_wallet.derivation_path}")
        print(f"   Type: {btc_wallet.metadata.get('type', 'unknown')}")

    print()

    # -----------------------------------------------------------------------
    # 5. Show Monero address details
    # -----------------------------------------------------------------------
    print("5. Monero Address Details:")
    print()

    xmr_wallet = wallet.wallets.get(ChainType.XMR)
    if xmr_wallet:
        print(f"   Address: {xmr_wallet.address}")
        print(f"   Public Key: {xmr_wallet.public_key[:32]}...")
        print(f"   Type: {xmr_wallet.metadata.get('type', 'unknown')}")

    print()

    # -----------------------------------------------------------------------
    # 6. Show Tari address details
    # -----------------------------------------------------------------------
    print("6. Tari Address Details:")
    print()

    tari_wallet = wallet.wallets.get(ChainType.TARI)
    if tari_wallet:
        print(f"   Address: {tari_wallet.address}")
        print(f"   Public Key: {tari_wallet.public_key[:32]}...")
        print(f"   Type: {tari_wallet.metadata.get('type', 'unknown')}")

    print()

    # -----------------------------------------------------------------------
    # 7. Show Qubic address details
    # -----------------------------------------------------------------------
    print("7. Qubic Address Details:")
    print()

    qubic_wallet = wallet.wallets.get(ChainType.QUBIC)
    if qubic_wallet:
        print(f"   Address: {qubic_wallet.address}")
        print(f"   Public Key: {qubic_wallet.public_key[:32]}...")
        print(f"   Type: {qubic_wallet.metadata.get('type', 'unknown')}")

    print()

    # -----------------------------------------------------------------------
    # 8. Balance Monitor Dashboard
    # -----------------------------------------------------------------------
    print("8. Balance Monitor Dashboard:")
    print()

    monitor = create_wallet_monitor(wallet, poll_interval=60)
    monitor.check_all_balances()
    print(monitor.format_dashboard())
    print()

    # -----------------------------------------------------------------------
    # 9. Export and Import
    # -----------------------------------------------------------------------
    print("9. Export and Import Test:")
    print()

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        export_path = f.name

    try:
        export_wallet(wallet, export_path)
        print(f"   Exported to: {export_path}")

        imported = import_wallet(export_path)
        print(f"   Imported label: {imported.label}")
        print(f"   Imported chains: {len(imported.wallets)}")

        # Verify addresses match
        for chain in ChainType:
            original = wallet.wallets.get(chain)
            restored = imported.wallets.get(chain)
            if original and restored:
                match = original.address == restored.address
                print(f"   {chain.value.upper():8s} | Address match: {match}")

    finally:
        if os.path.exists(export_path):
            os.unlink(export_path)

    print()

    # -----------------------------------------------------------------------
    # 10. Deterministic seed test
    # -----------------------------------------------------------------------
    print("10. Deterministic Seed Test:")
    print()

    wallet1 = create_multi_chain_wallet(master_seed=master_seed)
    wallet2 = create_multi_chain_wallet(master_seed=master_seed)

    for chain in ChainType:
        addr1 = wallet1.wallets.get(chain)
        addr2 = wallet2.wallets.get(chain)
        if addr1 and addr2:
            match = addr1.address == addr2.address
            print(f"   {chain.value.upper():8s} | Same address: {match}")

    print()
    print("=" * 70)
    print("  DEMO COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
