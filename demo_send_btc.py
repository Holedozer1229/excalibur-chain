#!/usr/bin/env python3
"""demo_send_btc.py — Send BTC on mainnet.

Creates and broadcasts a real Bitcoin transaction.
Usage: python demo_send_btc.py --to <address> --mnemonic "<12 words>" --amount <btc>
"""
import argparse
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sphinx_os.nexus.btc_mainnet_sender import BTCMainnetSender


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--to', required=True, help='Destination BTC address')
    parser.add_argument('--mnemonic', required=True, help='12-word wallet mnemonic')
    parser.add_argument('--amount', type=float, required=True, help='BTC amount')
    args = parser.parse_args()

    print("\n" + "="*60)
    print("  BTC MAINNET SENDER")
    print("="*60 + "\n")

    sender = BTCMainnetSender()

    # Derive address from mnemonic
    from sphinx_os.nexus.btc_wallet_generator import BTCWalletGenerator
    gen = BTCWalletGenerator()
    seed = gen.derive_seed(args.mnemonic)
    priv = gen.derive_private_key(seed)
    _, address = gen.derive_address(priv)

    print(f"From: {address}")
    print(f"To: {args.to}")
    print(f"Amount: {args.amount} BTC\n")

    # Fetch UTXOs
    print("Fetching UTXOs...")
    utxos = sender.fetch_utxos(address)
    if not utxos:
        print("No UTXOs found. Wallet has no BTC.")
        return

    total = sum(u.value_sats for u in utxos) / 100_000_000
    print(f"Found {len(utxos)} UTXOs ({total:.8f} BTC)\n")

    if total < args.amount:
        print(f"Insufficient funds: {total:.8f} < {args.amount}")
        return

    # Create, sign, broadcast
    tx = sender.create_transaction(args.to, args.amount, utxos, change_address=address)
    tx_hex = sender.sign_transaction(tx, args.mnemonic)
    print(f"Signed TX: {tx_hex[:32]}...")

    success, result = sender.broadcast(tx_hex)
    if success:
        print(f"Broadcasted! TXID: {result}")
    else:
        print(f"Failed: {result}")


if __name__ == "__main__":
    main()
