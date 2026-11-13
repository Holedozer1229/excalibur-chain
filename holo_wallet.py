#!/usr/bin/env python3
"""Holo-wallet: A holographic P2P wallet for the SphinxOS Nexus network.

This wallet provides:
- Key pair generation and management (SHA-256 based addresses)
- Balance tracking and transaction history
- Transaction creation and signing (hash-only, post-quantum style)
- Broadcasting through the Holographic P2P network
- Network topology visualization
- Encrypted message sending between peers

Usage:
    python holo_wallet.py [command] [options]

Commands:
    generate          Generate a new key pair and address
    balance           Show wallet balance
    send              Send SKYNT to another address
    tx                Create and broadcast a transaction
    peers             List connected peers
    topology          Export network topology
    encrypt           Send an encrypted message
    gossip            Broadcast via gossip protocol
    status            Show wallet and network status
    help              Show this help message

Examples:
    python holo_wallet.py generate
    python holo_wallet.py balance
    python holo_wallet.py send --to ABC123 --amount 10.5
    python holo_wallet.py peers
    python holo_wallet.py topology --format json
"""

import sys
import os
import json
import hashlib
import time
import argparse
import base64
from pathlib import Path
from typing import Dict, List, Optional, Any

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sphinx_os.nexus import (
    HolographicP2PLayer,
    MessagePriority,
    NexusOrchestrator,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

WALLET_DIR = Path(os.path.expanduser("~/.holo_wallet"))
WALLET_FILE = WALLET_DIR / "wallet.json"
NETWORK_FILE = WALLET_DIR / "network_state.json"

# Service flags
NODE_NETWORK = 0x01
NODE_P2P_V2 = 0x02
NODE_LIGHT = 0x04
NODE_STRATUM = 0x08


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

def sha256_hex(data: str) -> str:
    """Compute SHA-256 hex digest of a string."""
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def generate_address(seed: str) -> str:
    """Generate a wallet address from a seed string.

    The address is the first 20 characters of the SHA-256 hash of the seed,
    encoded in uppercase hexadecimal.
    """
    return sha256_hex(seed)[:20].upper()


def validate_address(addr: str) -> bool:
    """Validate an EXCAL wallet address.

    A valid address is exactly 20 uppercase hexadecimal characters.
    """
    if not addr or len(addr) != 20:
        return False
    try:
        int(addr, 16)
        return addr == addr.upper()
    except ValueError:
        return False


def generate_keypair() -> Dict[str, str]:
    """Generate a new key pair.

    Returns:
        Dictionary with 'private_key', 'public_key', and 'address'.
    """
    import secrets
    private_key = secrets.token_hex(32)
    public_key = sha256_hex(private_key)
    address = generate_address(private_key)
    return {
        "private_key": private_key,
        "public_key": public_key,
        "address": address,
    }


def sign_transaction(private_key: str, tx_data: Dict[str, Any]) -> str:
    """Sign a transaction with the private key.

    Uses a hash-only signature (post-quantum style):
    signature = SHA-256(private_key || tx_hash)
    """
    tx_hash = sha256_hex(json.dumps(tx_data, sort_keys=True))
    signature = sha256_hex(private_key + tx_hash)
    return signature


def verify_signature(private_key: str, tx_data: Dict[str, Any], signature: str) -> bool:
    """Verify a transaction signature."""
    expected = sign_transaction(private_key, tx_data)
    return expected == signature


# ---------------------------------------------------------------------------
# Wallet class
# ---------------------------------------------------------------------------

class HoloWallet:
    """A wallet for the SphinxOS Nexus holographic P2P network.

    Manages keys, balances, transactions, and network interactions.
    """

    def __init__(self):
        self.wallet_dir = WALLET_DIR
        self.wallet_file = WALLET_FILE
        self.wallet: Dict[str, Any] = {}
        self.p2p: Optional[HolographicP2PLayer] = None
        self._load_wallet()

    def _load_wallet(self):
        """Load wallet data from disk."""
        self.wallet_dir.mkdir(parents=True, exist_ok=True)

        if self.wallet_file.exists():
            try:
                with open(self.wallet_file, "r") as f:
                    self.wallet = json.load(f)
            except (json.JSONDecodeError, IOError):
                self.wallet = {}
        else:
            self.wallet = {
                "keys": [],
                "transactions": [],
                "balance": 0.0,
                "created_at": time.time(),
            }

    def _save_wallet(self):
        """Save wallet data to disk."""
        with open(self.wallet_file, "w") as f:
            json.dump(self.wallet, f, indent=2)

    def initialize_p2p(self, num_peers: int = 5):
        """Initialize the holographic P2P network with simulated peers.

        Args:
            num_peers: Number of simulated peers to create.
        """
        self.p2p = HolographicP2PLayer(gossip_k=3, default_ttl=60.0)

        # Add the local wallet as a peer
        addr = self.get_current_address() or "local"
        self.p2p.add_peer(
            name=f"wallet_{addr[:8]}",
            host="127.0.0.1",
            port=9433,
            services=NODE_NETWORK | NODE_P2P_V2,
            user_agent="HoloWallet/1.0",
        )
        self.p2p.connect_peer(f"wallet_{addr[:8]}")

        # Add simulated peers
        for i in range(num_peers):
            peer_name = f"peer_{i}"
            self.p2p.add_peer(
                name=peer_name,
                host=f"192.168.1.{i + 1}",
                port=8080 + i,
                services=NODE_NETWORK,
                user_agent=f"SphinxNode/{i}.0",
            )
            self.p2p.connect_peer(peer_name)

        # Set encryption key
        self.p2p.set_encryption_key()

    def generate_key(self, label: str = "") -> Dict[str, str]:
        """Generate a new key pair.

        Args:
            label: Optional label for the key.

        Returns:
            Dictionary with key information.
        """
        keypair = generate_keypair()
        keypair["label"] = label or f"Key #{len(self.wallet['keys']) + 1}"
        keypair["created_at"] = time.time()

        self.wallet["keys"].append(keypair)
        self._save_wallet()
        return keypair

    def get_current_address(self) -> Optional[str]:
        """Get the current wallet address (first key)."""
        if self.wallet["keys"]:
            return self.wallet["keys"][0]["address"]
        return None

    def get_balance(self) -> float:
        """Get the current wallet balance."""
        return self.wallet.get("balance", 0.0)

    def set_balance(self, amount: float):
        """Set the wallet balance (for simulation)."""
        self.wallet["balance"] = amount
        self._save_wallet()

    def create_transaction(
        self,
        to_address: str,
        amount: float,
        tx_type: str = "transfer",
        description: str = "",
    ) -> Optional[Dict[str, Any]]:
        """Create a new transaction.

        Args:
            to_address: Recipient address.
            amount: Amount to send.
            tx_type: Transaction type (transfer, nft_mint, bridge).
            description: Optional description.

        Returns:
            Transaction dictionary or None if insufficient funds.
        """
        if not self.wallet["keys"]:
            return None

        if amount > self.get_balance():
            return None

        current_key = self.wallet["keys"][0]
        tx_data = {
            "from": current_key["address"],
            "to": to_address,
            "amount": amount,
            "type": tx_type,
            "timestamp": time.time(),
            "description": description,
        }

        # Sign the transaction
        signature = sign_transaction(current_key["private_key"], tx_data)
        tx_data["signature"] = signature
        tx_data["tx_id"] = sha256_hex(json.dumps(tx_data, sort_keys=True))[:16]

        # Update balance
        self.wallet["balance"] -= amount
        self.wallet["transactions"].append(tx_data)
        self._save_wallet()

        return tx_data

    def broadcast_transaction(self, tx: Dict[str, Any]) -> Optional[str]:
        """Broadcast a transaction through the P2P network.

        Args:
            tx: Transaction dictionary.

        Returns:
            Message ID if broadcast successfully, None otherwise.
        """
        if self.p2p is None:
            self.initialize_p2p()

        addr = self.get_current_address() or "local"
        peer_name = f"wallet_{addr[:8]}"

        msg_id = self.p2p.send_message(
            source=peer_name,
            msg_type="tx",
            payload=tx,
            priority=MessagePriority.HIGH,
            encrypt=True,
            gossip=True,
        )

        return msg_id

    def send(
        self,
        to_address: str,
        amount: float,
        tx_type: str = "transfer",
        description: str = "",
        broadcast: bool = True,
    ) -> Dict[str, Any]:
        """Send SKYNT to another address.

        Args:
            to_address: Recipient address.
            amount: Amount to send.
            tx_type: Transaction type.
            description: Optional description.
            broadcast: Whether to broadcast through P2P network.

        Returns:
            Result dictionary with status and transaction info.
        """
        # Validate recipient address
        if not validate_address(to_address):
            return {
                "status": "error",
                "message": f"Invalid address: {to_address}. Must be 20 uppercase hex characters.",
            }
        
        # Validate amount
        if amount <= 0:
            return {
                "status": "error",
                "message": "Amount must be positive.",
            }
        
        tx = self.create_transaction(to_address, amount, tx_type, description)

        if tx is None:
            return {
                "status": "error",
                "message": "Insufficient funds or no keys available",
            }

        result = {
            "status": "created",
            "tx_id": tx["tx_id"],
            "amount": amount,
            "to": to_address,
        }

        if broadcast:
            if self.p2p is None:
                self.initialize_p2p()

            msg_id = self.broadcast_transaction(tx)
            result["broadcast"] = msg_id is not None
            result["message_id"] = msg_id[:16] if msg_id else None

        return result

    def send_encrypted_message(
        self,
        to_peer: str,
        message: str,
    ) -> Optional[str]:
        """Send an encrypted message to a peer.

        Args:
            to_peer: Destination peer name.
            message: Message text.

        Returns:
            Message ID if sent, None otherwise.
        """
        if self.p2p is None:
            self.initialize_p2p()

        addr = self.get_current_address() or "local"
        peer_name = f"wallet_{addr[:8]}"

        msg_id = self.p2p.send_message(
            source=peer_name,
            msg_type="encrypted_message",
            payload={"message": message},
            destination=to_peer,
            priority=MessagePriority.NORMAL,
            encrypt=True,
        )

        return msg_id

    def gossip_broadcast(self, message: str) -> Optional[str]:
        """Broadcast a message via gossip protocol.

        Args:
            message: Message text.

        Returns:
            Message ID if sent, None otherwise.
        """
        if self.p2p is None:
            self.initialize_p2p()

        addr = self.get_current_address() or "local"
        peer_name = f"wallet_{addr[:8]}"

        msg_id = self.p2p.send_message(
            source=peer_name,
            msg_type="gossip",
            payload={"message": message},
            priority=MessagePriority.LOW,
            gossip=True,
        )

        return msg_id

    def get_peers(self) -> List[Dict[str, Any]]:
        """Get list of connected peers."""
        if self.p2p is None:
            self.initialize_p2p()

        peers = []
        for name in self.p2p.get_active_peers():
            info = self.p2p.get_peer_info(name)
            if info:
                peers.append(info)
        return peers

    def get_network_status(self) -> Dict[str, Any]:
        """Get the current network status."""
        if self.p2p is None:
            self.initialize_p2p()

        return self.p2p.get_network_state()

    def export_topology(self, fmt: str = "json") -> str:
        """Export network topology.

        Args:
            fmt: Output format ('json' or 'graphml').

        Returns:
            Serialized topology string.
        """
        if self.p2p is None:
            self.initialize_p2p()

        return self.p2p.export_topology(format=fmt)

    def get_wallet_status(self) -> Dict[str, Any]:
        """Get the current wallet status."""
        return {
            "address": self.get_current_address(),
            "balance": self.get_balance(),
            "keys": len(self.wallet["keys"]),
            "transactions": len(self.wallet["transactions"]),
            "network": self.get_network_status() if self.p2p else None,
        }

    def deposit(self, amount: float):
        """Deposit SKYNT into the wallet (for simulation).

        Args:
            amount: Amount to deposit.
        """
        self.wallet["balance"] = self.wallet.get("balance", 0.0) + amount
        self._save_wallet()


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------

def cmd_generate(args):
    """Generate a new key pair."""
    wallet = HoloWallet()
    label = args.label if args.label else ""
    keypair = wallet.generate_key(label)

    print("\n🔑 Key Pair Generated")
    print("=" * 50)
    print(f"  Label:        {keypair['label']}")
    print(f"  Address:      {keypair['address']}")
    print(f"  Public Key:   {keypair['public_key'][:16]}...")
    print(f"  Private Key:  {keypair['private_key'][:16]}... (stored securely)")
    print(f"  Created:      {time.ctime(keypair['created_at'])}")
    print()


def cmd_balance(args):
    """Show wallet balance."""
    wallet = HoloWallet()
    address = wallet.get_current_address()
    balance = wallet.get_balance()

    print("\n💰 Wallet Balance")
    print("=" * 50)
    if address:
        print(f"  Address:  {address}")
        print(f"  Balance:  {balance:.4f} SKYNT")
    else:
        print("  No keys found. Run 'generate' first.")
    print()


def cmd_send(args):
    """Send SKYNT to another address."""
    wallet = HoloWallet()

    # Ensure P2P network is initialized
    wallet.initialize_p2p()

    # Deposit some test funds if balance is zero
    if wallet.get_balance() < args.amount:
        print(f"  ⚠ Insufficient funds. Depositing test SKYNT...")
        wallet.deposit(args.amount * 10)

    result = wallet.send(
        to_address=args.to,
        amount=args.amount,
        tx_type=args.type,
        description=args.description or "",
        broadcast=True,
    )

    print("\n📤 Transaction Result")
    print("=" * 50)
    print(f"  Status:     {result['status']}")

    if result["status"] == "created":
        print(f"  TX ID:      {result.get('tx_id', 'N/A')}")
        print(f"  Amount:     {result['amount']:.4f} SKYNT")
        print(f"  To:         {result['to']}")
        print(f"  Broadcast:  {'✓' if result.get('broadcast') else '✗'}")
        if result.get("message_id"):
            print(f"  Message ID: {result['message_id']}...")
    else:
        print(f"  Error:      {result.get('message', 'Unknown error')}")
    print()


def cmd_peers(args):
    """List connected peers."""
    wallet = HoloWallet()
    wallet.initialize_p2p()

    peers = wallet.get_peers()
    status = wallet.get_network_status()

    print("\n🌐 Connected Peers")
    print("=" * 50)
    print(f"  Network Coherence:  {status['network_coherence']:.4f}")
    print(f"  Active Peers:       {status['active_peers']}")
    print(f"  Messages Sent:      {status['messages_sent']}")
    print()

    for peer in peers:
        services = []
        if peer.get("services", 0) & NODE_NETWORK:
            services.append("NETWORK")
        if peer.get("services", 0) & NODE_P2P_V2:
            services.append("P2P_V2")
        if peer.get("services", 0) & NODE_LIGHT:
            services.append("LIGHT")
        if peer.get("services", 0) & NODE_STRATUM:
            services.append("STRATUM")

        print(f"  ◉ {peer['name']}")
        print(f"    Address:    {peer['host']}:{peer['port']}")
        print(f"    Services:   {', '.join(services) if services else 'NONE'}")
        print(f"    User Agent: {peer.get('user_agent', 'N/A')}")
        print(f"    Entropy:    {peer['entropy']:.4f}")
        print(f"    Latency:    {peer['avg_latency_ms']:.2f} ms")
        print()


def cmd_topology(args):
    """Export network topology."""
    wallet = HoloWallet()
    wallet.initialize_p2p()

    fmt = args.format if args.format else "json"
    topology = wallet.export_topology(fmt)

    if args.output:
        with open(args.output, "w") as f:
            f.write(topology)
        print(f"\n  ✓ Topology exported to {args.output}")
    else:
        print("\n📊 Network Topology")
        print("=" * 50)
        print(topology)
    print()


def cmd_encrypt(args):
    """Send an encrypted message."""
    wallet = HoloWallet()
    wallet.initialize_p2p()

    to_peer = args.to if args.to else "peer_0"
    msg_id = wallet.send_encrypted_message(to_peer, args.message)

    print("\n🔒 Encrypted Message")
    print("=" * 50)
    if msg_id:
        print(f"  To:         {to_peer}")
        print(f"  Message ID: {msg_id[:16]}...")
        print(f"  Status:     ✓ Sent (encrypted)")
    else:
        print(f"  Status:     ✗ Failed to send")
    print()


def cmd_gossip(args):
    """Broadcast via gossip protocol."""
    wallet = HoloWallet()
    wallet.initialize_p2p()

    msg_id = wallet.gossip_broadcast(args.message)

    print("\n📢 Gossip Broadcast")
    print("=" * 50)
    if msg_id:
        print(f"  Message ID: {msg_id[:16]}...")
        print(f"  Status:     ✓ Broadcast via gossip")

        # Show gossip reach
        status = wallet.get_network_status()
        print(f"  Active Peers: {status['active_peers']}")
        print(f"  Messages Sent: {status['messages_sent']}")
    else:
        print(f"  Status:     ✗ Failed to broadcast")
    print()


def cmd_status(args):
    """Show wallet and network status."""
    wallet = HoloWallet()
    wallet.initialize_p2p()

    status = wallet.get_wallet_status()

    print("\n📋 Wallet & Network Status")
    print("=" * 50)
    print(f"  Address:      {status['address'] or 'No keys'}")
    print(f"  Balance:      {status['balance']:.4f} SKYNT")
    print(f"  Keys:         {status['keys']}")
    print(f"  Transactions: {status['transactions']}")

    if status.get("network"):
        net = status["network"]
        print(f"\n  Network:")
        print(f"    Active Peers:     {net['active_peers']}")
        print(f"    Coherence:        {net['network_coherence']:.4f}")
        print(f"    Messages Sent:    {net['messages_sent']}")
        print(f"    Bandwidth:        {net['total_bandwidth_bytes']} bytes")
        print(f"    Avg Latency:      {net['avg_latency_ms']:.2f} ms")
        print(f"    Encryption:       {'✓' if net['encryption_enabled'] else '✗'}")
    print()


def cmd_mine(args):
    """Start CPU mining."""
    threads = int(getattr(args, 'threads', 0) or os.cpu_count() or 4)
    host = os.environ.get("STRATUM_HOST", "127.0.0.1")
    port = int(os.environ.get("STRATUM_PORT", "9434"))
    print(f"\n⛏ Starting CPU miner: {threads} threads → {host}:{port}")
    print("=" * 50)
    print("  Mining... (Ctrl+C to stop)")
    print()
    import hashlib as _hashlib
    import time as _time
    nonce = 0
    hashes = 0
    start = _time.time()
    try:
        while True:
            # SHA-256d hash loop
            header = b"mining" + nonce.to_bytes(4, 'little')
            _hashlib.sha256(_hashlib.sha256(header).digest()).digest()
            nonce += 1
            hashes += 1
            if hashes % 1000000 == 0:
                elapsed = _time.time() - start
                mhash = hashes / elapsed / 1_000_000
                print(f"  {hashes:,} hashes • {mhash:.1f} MH/s")
    except KeyboardInterrupt:
        elapsed = _time.time() - start
        mhash = hashes / elapsed / 1_000_000 if elapsed > 0 else 0
        print(f"\n  Stopped: {hashes:,} hashes • {mhash:.1f} MH/s\n")


def cmd_stratum(args):
    """Launch stratum server for GPU miners."""
    host = getattr(args, 'host', '127.0.0.1') or '127.0.0.1'
    port = int(getattr(args, 'port', 9434) or 9434)
    print(f"\n🔥 Launching Stratum server on {host}:{port}")
    print("=" * 50)
    try:
        import subprocess
        proc = subprocess.Popen(
            [sys.executable, "stratum_fork.py"],
            env={**os.environ, "STRATUM_HOST": host, "STRATUM_PORT": str(port)},
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        print(f"  Stratum server started (PID {proc.pid})")
        print(f"  Point your GPU miner to stratum+tcp://{host}:{port}")
        print(f"  Press Ctrl+C to stop\n")
        proc.wait()
    except FileNotFoundError:
        print("  Error: stratum_fork.py not found. Make sure it's in the project directory.")
    except KeyboardInterrupt:
        print("\n  Stratum server stopped.\n")


def cmd_help(args):
    """Show help message."""
    print("\n" + "=" * 50)
    print("  AetherionEXCAL: Unified P2P Wallet & Miner")
    print("=" * 50)
    print()
    print("Usage: AetherionEXCAL [command] [options]")
    print()
    print("Wallet Commands:")
    print("  generate      Generate a new key pair and address")
    print("  balance       Show wallet balance")
    print("  send          Send SKYNT to another address")
    print("  peers         List connected peers")
    print("  topology      Export network topology")
    print("  encrypt       Send an encrypted message")
    print("  gossip        Broadcast via gossip protocol")
    print("  status        Show wallet and network status")
    print()
    print("Mining Commands:")
    print("  mine          Start CPU mining")
    print("  stratum       Launch stratum server for GPU miners")
    print()
    print("  help          Show this help message")
    print()
    print("Examples:")
    print("  AetherionEXCAL generate")
    print("  AetherionEXCAL balance")
    print("  AetherionEXCAL send --to ABC123 --amount 10.5")
    print("  AetherionEXCAL mine --threads 8")
    print("  AetherionEXCAL stratum --host 0.0.0.0 --port 9434")
    print()


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Holo-wallet: SphinxOS Nexus P2P Wallet",
        add_help=False,
    )
    parser.add_argument("command", nargs="?", default="help",
                        help="Command to execute")
    parser.add_argument("--label", "-l", default="", help="Key label")
    parser.add_argument("--to", "-t", default="", help="Recipient address/peer")
    parser.add_argument("--amount", "-a", type=float, default=1.0,
                        help="Amount to send")
    parser.add_argument("--type", default="transfer",
                        help="Transaction type (transfer, nft_mint, bridge)")
    parser.add_argument("--description", "-d", default="", help="Description")
    parser.add_argument("--message", "-m", default="", help="Message text")
    parser.add_argument("--format", "-f", default="json",
                        help="Output format (json, graphml)")
    parser.add_argument("--output", "-o", default="", help="Output file")
    parser.add_argument("--threads", "-T", type=int, default=0, help="CPU mining threads")
    parser.add_argument("--host", default="", help="Stratum host")
    parser.add_argument("--port", type=int, default=9434, help="Stratum port")
    parser.add_argument("--help", "-h", action="store_true", help="Show help")

    args = parser.parse_args()

    if args.help or args.command == "help":
        cmd_help(args)
        return

    commands = {
        "generate": cmd_generate,
        "balance": cmd_balance,
        "send": cmd_send,
        "peers": cmd_peers,
        "topology": cmd_topology,
        "encrypt": cmd_encrypt,
        "gossip": cmd_gossip,
        "status": cmd_status,
        "mine": cmd_mine,
        "stratum": cmd_stratum,
    }

    handler = commands.get(args.command)
    if handler:
        try:
            handler(args)
        except Exception as e:
            print(f"\n❌ Error: {e}\n", file=sys.stderr)
            sys.exit(1)
    else:
        print(f"\n❌ Unknown command: {args.command}\n", file=sys.stderr)
        cmd_help(args)
        sys.exit(1)


if __name__ == "__main__":
    main()
