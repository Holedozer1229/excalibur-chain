"""kivy_wallet — Kivy-based cross-platform mobile wallet for AetherionEXCAL.

Full-featured wallet with complete parity to the CLI wallet:
- Dashboard: chain height, mempool, peers, mining status
- Wallet: create, import seed, view address, check balance
- Send/Receive: build/sign/broadcast transactions, view UTXOs
- Locks: HTLC, QHTLC, PKH, PQH operations
- Explorer: block and transaction browsing
- Light Ledger: checkpoint verification
- Settings: RPC endpoint, network selection

Connects to the existing JSON-RPC backend (node_rpc.py, port 9432).
"""
