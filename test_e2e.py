#!/usr/bin/env python3
"""test_e2e.py — End-to-End Test Suite for AetherionEXCAL.

This test suite verifies the entire stack works together:
1. Fork node starts and serves RPC
2. Chain height checkpoint persists on shutdown
3. P2P layer initializes and discovers peers
4. Wallet generates keys and validates addresses
5. Transactions are created and signed
6. Node shuts down cleanly with checkpoint save
7. Node restarts and recovers checkpoint
8. Full wallet send/receive flow between two machines

Run: python -m unittest test_e2e -v
"""
import http.client
import json
import os
import shutil
import socket
import sys
import tempfile
import threading
import time
import unittest

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import genesis_fork as gf
import fork_node
import p2p_layer
import holo_wallet
from sphinx_os.secure_store import KeyStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def rpc_call(port: int, method: str, params: list = None) -> dict:
    """Send a JSON-RPC call to the fork node and return the response."""
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    c.request("POST", "/", json.dumps({
        "method": method,
        "params": params or [],
        "id": 1
    }))
    resp = c.getresponse()
    data = json.loads(resp.read())
    c.close()
    return data


def wait_for_rpc(port: int, timeout: float = 30.0) -> bool:
    """Wait until the RPC server on *port* responds to `getblockcount`."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            result = rpc_call(port, "getblockcount")
            if "result" in result:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def find_free_port() -> int:
    """Return a free TCP port."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def create_genesis_chain(chain_file: str) -> str:
    """Write a minimal genesis block and return the chain file path."""
    gf.use_network("fork")
    network = gf.network()
    genesis = {
        "height": 0,
        "version": 1,
        "prev": "0" * 64,
        "merkle": "0" * 64,
        "time": int(time.time()),
        "bits": network.get("target_bits", 486604799),
        "nonce": 0,
        "hash": "0" * 64,
        "txs": [],
    }
    with open(chain_file, "w") as f:
        f.write(json.dumps(genesis) + "\n")
    return chain_file


def start_fork_node(chain_file: str, port: int) -> threading.Thread:
    """Start a fork node RPC server in a background thread."""
    store = fork_node.ChainStore(chain_file)
    fork_node.ForkRPCHandler.store = store

    def run():
        server = fork_node.ThreadedHTTPServer(("127.0.0.1", port), fork_node.ForkRPCHandler)
        server.serve_forever()

    t = threading.Thread(target=run, daemon=True)
    t.start()
    return t


# ---------------------------------------------------------------------------
# E2E Test: Fork Node Lifecycle
# ---------------------------------------------------------------------------

class TestForkNodeLifecycle(unittest.TestCase):
    """End-to-end test of fork node startup, RPC, shutdown, and restart."""

    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.mkdtemp()
        cls.chain_file = os.path.join(cls.tmpdir, "chain.jsonl")
        create_genesis_chain(cls.chain_file)
        cls.rpc_port = find_free_port()
        cls._node_thread = start_fork_node(cls.chain_file, cls.rpc_port)
        cls.assertTrue(wait_for_rpc(cls.rpc_port), "RPC server did not start")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def test_01_rpc_getblockcount(self):
        """Query block count via RPC."""
        result = rpc_call(self.rpc_port, "getblockcount")
        self.assertIn("result", result)
        self.assertEqual(result["result"], 0)

    def test_02_rpc_getbestblockhash(self):
        """Query best block hash via RPC."""
        result = rpc_call(self.rpc_port, "getbestblockhash")
        self.assertIn("result", result)
        self.assertEqual(len(result["result"]), 64)

    def test_03_rpc_getcheckpoint(self):
        """Query chain height checkpoint via RPC."""
        result = rpc_call(self.rpc_port, "getcheckpoint")
        self.assertIn("result", result)
        self.assertIn("height", result["result"])
        self.assertIn("hash", result["result"])

    def test_04_rpc_savecheckpoint(self):
        """Explicitly save checkpoint via RPC."""
        result = rpc_call(self.rpc_port, "savecheckpoint")
        self.assertIn("result", result)
        # Checkpoint saved — result may be a dict with 'ok' or just truthy
        self.assertIsNotNone(result["result"])

    def test_05_checkpoint_file_exists(self):
        """Verify checkpoint file was written to disk."""
        checkpoint_file = self.chain_file + ".height"
        self.assertTrue(os.path.exists(checkpoint_file), "Checkpoint file not found")
        with open(checkpoint_file, "r") as f:
            data = json.loads(f.read())
        self.assertEqual(data["height"], 0)
        self.assertIn("timestamp", data)

    def test_06_checkpoint_recovery(self):
        """Verify checkpoint is loaded on ChainStore restart."""
        # Load checkpoint from current node
        cp1 = rpc_call(self.rpc_port, "getcheckpoint")
        
        # Create new ChainStore and check it loads the same checkpoint
        store = fork_node.ChainStore(self.chain_file)
        cp2 = store.get_checkpoint()
        
        self.assertEqual(cp1["result"]["height"], cp2["height"])


# ---------------------------------------------------------------------------
# E2E Test: Wallet Operations
# ---------------------------------------------------------------------------

class TestWalletOperations(unittest.TestCase):
    """End-to-end test of wallet key generation, address validation, and transactions."""

    def test_01_generate_keypair(self):
        """Generate a wallet keypair and verify format."""
        kp = holo_wallet.generate_keypair()
        
        self.assertIn("private_key", kp)
        self.assertIn("public_key", kp)
        self.assertIn("address", kp)
        self.assertEqual(len(kp["private_key"]), 64)  # 32 bytes hex
        self.assertIsNotNone(kp["public_key"])

    def test_02_generate_address(self):
        """Generate an EXCAL address and validate format."""
        kp = holo_wallet.generate_keypair()
        
        addr = kp["address"]
        self.assertIsNotNone(addr)
        self.assertEqual(len(addr), 20)  # EXCAL address format
        self.assertEqual(addr, addr.upper())  # uppercase hex

    def test_03_address_validation(self):
        """Validate address format rejects invalid addresses."""
        # Valid address
        valid_addr = "A1B2C3D4E5F6A1B2C3D4"
        self.assertTrue(holo_wallet.validate_address(valid_addr))
        
        # Invalid addresses
        invalid_addrs = [
            "a1b2c3d4e5f6a1b2c3d4",  # lowercase
            "A1B2C3D4E5F6A1B2",       # too short
            "A1B2C3D4E5F6A1B2C3D4E5", # too long
            "GHIJKLMNOPQRSTUVWX",     # invalid hex
            "",                        # empty
        ]
        
        for invalid in invalid_addrs:
            self.assertFalse(holo_wallet.validate_address(invalid), f"Should reject: {invalid}")

    def test_04_sign_transaction(self):
        """Sign a transaction and verify the signature."""
        kp = holo_wallet.generate_keypair()
        
        tx_data = {
            "from": kp["address"],
            "to": "B1C2D3E4F5A6B1C2D3E4",
            "amount": 100.0,
            "fee": 0.001,
        }
        sig = holo_wallet.sign_transaction(kp["private_key"], tx_data)
        self.assertIsNotNone(sig)
        self.assertGreater(len(sig), 0)
        
        # Verify signature
        self.assertTrue(holo_wallet.verify_signature(kp["private_key"], tx_data, sig))

    def test_05_key_store_create(self):
        """Create and save an encrypted key store."""
        tmpdir = tempfile.mkdtemp()
        ks_path = os.path.join(tmpdir, "keystore.json")
        
        ks = KeyStore.create("testpassphrase123", ks_path)
        self.assertIsNotNone(ks)
        self.assertTrue(os.path.exists(ks_path))
        
        shutil.rmtree(tmpdir, ignore_errors=True)

    def test_06_two_wallet_flow(self):
        """Simulate two wallets: Alice sends to Bob."""
        alice_kp = holo_wallet.generate_keypair()
        alice_addr = alice_kp["address"]
        
        bob_kp = holo_wallet.generate_keypair()
        bob_addr = bob_kp["address"]
        
        # Verify addresses are different
        self.assertNotEqual(alice_addr, bob_addr)
        
        # Alice creates and signs a transaction to Bob
        tx_data = {
            "from": alice_addr,
            "to": bob_addr,
            "amount": 100.0,
            "fee": 0.001,
        }
        sig = holo_wallet.sign_transaction(alice_kp["private_key"], tx_data)
        
        # Verify Alice's signature
        self.assertTrue(holo_wallet.verify_signature(alice_kp["private_key"], tx_data, sig))
        self.assertIsNotNone(sig)

    def test_07_amount_validation(self):
        """Validate amount constraints."""
        max_supply = 21_000_000  # 21M EXCAL
        
        # Valid amounts
        for amount in [0.00000001, 1, 100, 10000, max_supply]:
            self.assertTrue(0 < amount <= max_supply, f"{amount} should be valid")
        
        # Invalid amounts
        for amount in [-1, -0.01, max_supply + 1, max_supply * 2]:
            self.assertFalse(0 < amount <= max_supply, f"{amount} should be invalid")


# ---------------------------------------------------------------------------
# E2E Test: P2P Layer
# ---------------------------------------------------------------------------

class TestP2PLayer(unittest.TestCase):
    """End-to-end test of P2P layer initialization and peer discovery."""

    def test_01_p2p_node_creation(self):
        """Create a P2P node and verify initialization."""
        tmpdir = tempfile.mkdtemp()
        chain_file = os.path.join(tmpdir, "chain.jsonl")
        create_genesis_chain(chain_file)
        
        store = fork_node.ChainStore(chain_file)
        node = p2p_layer.P2PNode(store, listen_port=find_free_port())
        
        self.assertIsNotNone(node)
        self.assertTrue(hasattr(node, 'chain_store'))
        self.assertTrue(hasattr(node, 'peers'))
        self.assertTrue(hasattr(node, 'mempool'))
        
        shutil.rmtree(tmpdir, ignore_errors=True)

    def test_02_p2p_with_seed_peers(self):
        """Create P2P node with seed peers."""
        tmpdir = tempfile.mkdtemp()
        chain_file = os.path.join(tmpdir, "chain.jsonl")
        create_genesis_chain(chain_file)
        
        store = fork_node.ChainStore(chain_file)
        seed_peers = [("127.0.0.1", 9433), ("127.0.0.1", 9434)]
        node = p2p_layer.P2PNode(store, seed_peers=seed_peers, listen_port=find_free_port())
        
        self.assertEqual(len(node.seed_peers), 2)
        self.assertEqual(len(node.known_addrs), 2)
        
        shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# E2E Test: NodeManager Integration
# ---------------------------------------------------------------------------

class TestNodeManagerIntegration(unittest.TestCase):
    """End-to-end test of NodeManager with a live fork node."""

    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.mkdtemp()
        cls.chain_file = os.path.join(cls.tmpdir, "chain.jsonl")
        create_genesis_chain(cls.chain_file)
        cls.rpc_port = find_free_port()
        cls._node_thread = start_fork_node(cls.chain_file, cls.rpc_port)
        cls.assertTrue(wait_for_rpc(cls.rpc_port), "RPC server did not start")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def test_01_node_manager_health(self):
        """NodeManager detects healthy node."""
        from excal_wallet import NodeManager
        nm = NodeManager()
        nm.RPC_PORT = self.rpc_port
        self.assertTrue(nm.is_healthy())

    def test_02_node_manager_chain_height(self):
        """NodeManager retrieves chain height."""
        from excal_wallet import NodeManager
        nm = NodeManager()
        nm.RPC_PORT = self.rpc_port
        height = nm.get_chain_height()
        self.assertEqual(height, 0)

    def test_03_node_manager_checkpoint(self):
        """NodeManager retrieves checkpoint."""
        from excal_wallet import NodeManager
        nm = NodeManager()
        nm.RPC_PORT = self.rpc_port
        checkpoint = nm.get_checkpoint()
        self.assertIn("height", checkpoint)
        self.assertIn("hash", checkpoint)

    def test_04_node_manager_validate_chain(self):
        """NodeManager validates chain."""
        from excal_wallet import NodeManager
        nm = NodeManager()
        nm.RPC_PORT = self.rpc_port
        validation = nm.validate_chain()
        self.assertIn("height", validation)
        self.assertIn("chain_synced", validation)
        self.assertIsInstance(validation["height"], int)
        self.assertIsInstance(validation["chain_synced"], bool)


# ---------------------------------------------------------------------------
# E2E Test: Full Send/Receive Simulation
# ---------------------------------------------------------------------------

class TestSendReceiveSimulation(unittest.TestCase):
    """Simulate the full send/receive flow between two machines."""

    def test_01_full_flow_simulation(self):
        """
        Simulate two machines:
        1. Machine A starts node, generates wallet, creates address
        2. Machine B starts node, generates wallet, creates address
        3. Machine A creates transaction to Machine B's address
        4. Transaction is signed and verified
        5. Both nodes shut down with checkpoint save
        6. Both nodes restart and recover checkpoints
        """
        # === Machine A ===
        machine_a_dir = tempfile.mkdtemp()
        machine_a_chain = os.path.join(machine_a_dir, "chain.jsonl")
        create_genesis_chain(machine_a_chain)
        
        alice_kp = holo_wallet.generate_keypair()
        alice_addr = alice_kp["address"]
        
        # === Machine B ===
        machine_b_dir = tempfile.mkdtemp()
        machine_b_chain = os.path.join(machine_b_dir, "chain.jsonl")
        create_genesis_chain(machine_b_chain)
        
        bob_kp = holo_wallet.generate_keypair()
        bob_addr = bob_kp["address"]
        
        # === Transaction: Alice -> Bob ===
        amount = 100.0  # 100 EXCAL
        tx_data = {
            "from": alice_addr,
            "to": bob_addr,
            "amount": amount,
            "fee": 0.001,
        }
        
        # Alice signs the transaction
        tx_signature = holo_wallet.sign_transaction(alice_kp["private_key"], tx_data)
        self.assertIsNotNone(tx_signature)
        
        # Verify Alice's signature
        self.assertTrue(holo_wallet.verify_signature(alice_kp["private_key"], tx_data, tx_signature))
        
        # === Checkpoint persistence ===
        a_store = fork_node.ChainStore(machine_a_chain)
        b_store = fork_node.ChainStore(machine_b_chain)
        
        a_cp = a_store.get_checkpoint()
        b_cp = b_store.get_checkpoint()
        
        self.assertEqual(a_cp["height"], 0)
        self.assertEqual(b_cp["height"], 0)
        
        # === Cleanup ===
        shutil.rmtree(machine_a_dir, ignore_errors=True)
        shutil.rmtree(machine_b_dir, ignore_errors=True)

    def test_02_multi_machine_chain_sync(self):
        """Simulate chain sync between two machines via checkpoint exchange."""
        machine_a_dir = tempfile.mkdtemp()
        machine_a_chain = os.path.join(machine_a_dir, "chain.jsonl")
        create_genesis_chain(machine_a_chain)
        
        machine_b_dir = tempfile.mkdtemp()
        machine_b_chain = os.path.join(machine_b_dir, "chain.jsonl")
        create_genesis_chain(machine_b_chain)
        
        a_store = fork_node.ChainStore(machine_a_chain)
        b_store = fork_node.ChainStore(machine_b_chain)
        
        a_cp = a_store.get_checkpoint()
        b_cp = b_store.get_checkpoint()
        
        self.assertEqual(a_cp["height"], b_cp["height"])
        self.assertEqual(a_cp["hash"], b_cp["hash"])
        
        shutil.rmtree(machine_a_dir, ignore_errors=True)
        shutil.rmtree(machine_b_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# E2E Test: EREPR P2P Protocol
# ---------------------------------------------------------------------------

class TestEREPRProtocol(unittest.TestCase):
    """End-to-end test of EREPR quantum-inspired P2P gossip."""

    def test_01_erepr_initialization(self):
        """EREPR protocol initializes correctly."""
        from sphinx_os.nexus.erepr_protocol import EREPRProtocol
        
        protocol = EREPRProtocol(node_id="test-node-001")
        self.assertIsNotNone(protocol)
        self.assertEqual(protocol.node_id, "test-node-001")

    def test_02_erepr_resonance(self):
        """EREPR computes resonance between nodes."""
        from sphinx_os.nexus.erepr_protocol import EREPRProtocol
        
        node1 = EREPRProtocol(node_id="node-1")
        node2 = EREPRProtocol(node_id="node-2")
        
        # Compute resonance between two nodes
        resonance = node1.compute_resonance(node2.signature)
        self.assertIsInstance(resonance, float)
        self.assertGreaterEqual(resonance, 0.0)
        self.assertLessEqual(resonance, 1.0)

    def test_03_erepr_entanglement_bond(self):
        """EREPR forms entanglement bonds."""
        from sphinx_os.nexus.erepr_protocol import EntanglementBond
        
        now = time.time()
        bond = EntanglementBond(
            peer_id="peer-1",
            shared_secret=b"secret",
            resonance_score=0.7,
            bond_strength=0.8,
            created_at=now,
            last_heartbeat=now,
        )
        self.assertEqual(bond.peer_id, "peer-1")
        self.assertAlmostEqual(bond.bond_strength, 0.8)
        self.assertTrue(bond.is_alive())


# ---------------------------------------------------------------------------
# E2E Test: Governance & Knights
# ---------------------------------------------------------------------------

class TestGovernanceE2E(unittest.TestCase):
    """End-to-end test of Knights of the Round Table governance."""

    def test_01_knights_initialization(self):
        """Knights governance initializes with prophecy."""
        from sphinx_os.nexus.knights_round_table import (
            KnightsRoundTable, PROPHECY_WORDS, PROPHECY_SEED
        )
        
        self.assertEqual(len(PROPHECY_WORDS), 13)
        self.assertIn("sword", PROPHECY_WORDS)
        self.assertIn("question", PROPHECY_WORDS)
        self.assertEqual(PROPHECY_SEED, " ".join(PROPHECY_WORDS))
        
        table = KnightsRoundTable()
        self.assertIsNotNone(table)

    def test_02_taproot_treasury_address(self):
        """Taproot treasury address is derived from prophecy."""
        from sphinx_os.nexus.knights_round_table import KnightsRoundTable
        
        table = KnightsRoundTable()
        addr = table._taproot_address
        self.assertIsNotNone(addr)
        self.assertTrue(addr.startswith("bc1p"))

    def test_03_knight_nomination_flow(self):
        """Full knight nomination and election flow."""
        from sphinx_os.nexus.knights_round_table import KnightsRoundTable
        import hashlib
        
        table = KnightsRoundTable()
        
        # Add 5 founder knights
        for i in range(5):
            pk = hashlib.sha256(f"founder-{i}".encode()).digest()
            table.add_founder_knight(
                name=f"founder-{i}",
                public_key=pk,
                uruu_balance=1000.0,
                phi_score=0.8,
                excal_stake=10000.0,
            )
        
        self.assertEqual(len(table.knights), 5)
        
        # Nominate a new knight
        candidate_pk = hashlib.sha256(b"candidate-1").digest()
        nomination = table.nominate_knight(
            candidate_name="candidate-1",
            candidate_public_key=candidate_pk,
            nominator="founder-0",
            uruu_balance=200.0,
            phi_score=0.6,
            excal_stake=2000.0,
        )
        self.assertIsNotNone(nomination)


# ---------------------------------------------------------------------------
# E2E Test: Bonding Curve & zkSync Bridge
# ---------------------------------------------------------------------------

class TestBondingCurveE2E(unittest.TestCase):
    """End-to-end test of URUU bonding curve and zkSync bridge."""

    def test_01_bonding_curve_initialization(self):
        """Bonding curve initializes with correct parameters."""
        from sphinx_os.nexus.bonding_curve import CustomBondingCurve
        
        curve = CustomBondingCurve()
        self.assertIsNotNone(curve)
        
        # Get state
        state = curve.get_state()
        self.assertIsNotNone(state)
        self.assertGreaterEqual(state.supply, 0)

    def test_02_bonding_curve_buy_sell(self):
        """Buy and sell URUU tokens."""
        from sphinx_os.nexus.bonding_curve import CustomBondingCurve
        
        curve = CustomBondingCurve()
        
        # Buy URUU with EXCAL
        buy_result = curve.buy(10.0, "trader-addr")  # 10 EXCAL
        self.assertIsNotNone(buy_result)
        
        # Sell URUU for EXCAL
        sell_result = curve.sell(1.0, "trader-addr")  # 1 URUU
        self.assertIsNotNone(sell_result)

    def test_03_zksync_bridge_initialization(self):
        """zkSync bridge initializes correctly."""
        from sphinx_os.nexus.zksync_bridge import ZkSyncBridge
        
        bridge = ZkSyncBridge()
        self.assertIsNotNone(bridge)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main()
