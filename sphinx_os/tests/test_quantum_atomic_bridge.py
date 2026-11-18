#!/usr/bin/env python3
"""Tests for the Quantum Atomic Bridge."""
import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sphinx_os.nexus.quantum_atomic_bridge import (
    QuantumAtomicBridge,
    QuantumSwap,
    BridgePhase,
    SwapDirection,
)


class TestQuantumAtomicBridgeInit(unittest.TestCase):
    def test_initial_state(self):
        bridge = QuantumAtomicBridge()
        self.assertEqual(bridge.state.phase, BridgePhase.IDLE)
        self.assertFalse(bridge.state.wormhole_active)
        self.assertEqual(bridge.state.active_swaps, 0)

    def test_deterministic_seed(self):
        b1 = QuantumAtomicBridge(seed="aaaa" * 16)
        b2 = QuantumAtomicBridge(seed="aaaa" * 16)
        self.assertEqual(b1.seed, b2.seed)


class TestChainRegistration(unittest.TestCase):
    def test_register_chain(self):
        bridge = QuantumAtomicBridge()
        bridge.register_chain("excal", "excalibur")
        bridge.register_chain("btc", "bitcoin")
        self.assertIn("excal", bridge._chain_registry)
        self.assertIn("btc", bridge._chain_registry)


class TestEntanglement(unittest.TestCase):
    def test_entangle_chains(self):
        bridge = QuantumAtomicBridge()
        bridge.register_chain("excal", "excalibur")
        bridge.register_chain("btc", "bitcoin")
        result = bridge.entangle_chains("excal", "btc")
        self.assertTrue(result)
        self.assertEqual(bridge.state.phase, BridgePhase.ENTANGLEMENT)
        self.assertIn("excal", bridge.state.entangled_chains)
        self.assertIn("btc", bridge.state.entangled_chains)

    def test_entangle_unregistered_fails(self):
        bridge = QuantumAtomicBridge()
        result = bridge.entangle_chains("unknown1", "unknown2")
        self.assertFalse(result)


class TestWormholeDetection(unittest.TestCase):
    def test_wormhole_detection(self):
        bridge = QuantumAtomicBridge()
        bridge.register_chain("excal", "excalibur")
        bridge.register_chain("btc", "bitcoin")
        bridge.entangle_chains("excal", "btc")
        # Lower threshold to ensure detection
        result = bridge.detect_wormhole(threshold=0.1)
        self.assertTrue(result)
        self.assertTrue(bridge.state.wormhole_active)


class TestHTLCPreimage(unittest.TestCase):
    def test_generate_preimage(self):
        bridge = QuantumAtomicBridge()
        preimage = bridge.generate_htlc_preimage()
        self.assertEqual(len(preimage), 64)  # 32 bytes hex
        # Verify it's valid hex
        bytes.fromhex(preimage)

    def test_preimages_are_unique(self):
        bridge = QuantumAtomicBridge()
        p1 = bridge.generate_htlc_preimage()
        p2 = bridge.generate_htlc_preimage()
        self.assertNotEqual(p1, p2)


class TestSwapCreation(unittest.TestCase):
    def test_create_swap(self):
        bridge = QuantumAtomicBridge()
        bridge.register_chain("excal", "excalibur")
        bridge.register_chain("btc", "bitcoin")
        bridge.entangle_chains("excal", "btc")
        bridge.detect_wormhole(threshold=0.1)

        swap = bridge.create_swap(
            SwapDirection.EXCAL_TO_BTC,
            1.0,
            "excal",
            "btc",
        )
        self.assertIsNotNone(swap)
        self.assertEqual(swap.direction, SwapDirection.EXCAL_TO_BTC)
        self.assertEqual(swap.amount, 1.0)
        self.assertEqual(bridge.state.active_swaps, 1)

    def test_swap_hash_lock(self):
        bridge = QuantumAtomicBridge()
        bridge.register_chain("excal", "excalibur")
        bridge.register_chain("btc", "bitcoin")
        bridge.entangle_chains("excal", "btc")
        bridge.detect_wormhole(threshold=0.1)

        swap = bridge.create_swap(
            SwapDirection.EXCAL_TO_BTC, 1.0, "excal", "btc"
        )
        import hashlib
        expected = hashlib.sha256(bytes.fromhex(swap.preimage)).hexdigest()
        self.assertEqual(swap.hash_lock, expected)


class TestSwapExecution(unittest.TestCase):
    def test_execute_swap_success(self):
        bridge = QuantumAtomicBridge()
        bridge.register_chain("excal", "excalibur")
        bridge.register_chain("btc", "bitcoin")
        bridge.entangle_chains("excal", "btc")
        bridge.detect_wormhole(threshold=0.1)

        swap = bridge.create_swap(
            SwapDirection.EXCAL_TO_BTC, 1.0, "excal", "btc"
        )
        result = bridge.execute_swap(swap.swap_id, swap.preimage)
        self.assertTrue(result)
        self.assertEqual(swap.status, "completed")
        self.assertEqual(bridge.state.completed_swaps, 1)

    def test_execute_swap_wrong_preimage(self):
        bridge = QuantumAtomicBridge()
        bridge.register_chain("excal", "excalibur")
        bridge.register_chain("btc", "bitcoin")
        bridge.entangle_chains("excal", "btc")
        bridge.detect_wormhole(threshold=0.1)

        swap = bridge.create_swap(
            SwapDirection.EXCAL_TO_BTC, 1.0, "excal", "btc"
        )
        wrong = "0" * 64
        result = bridge.execute_swap(swap.swap_id, wrong)
        self.assertFalse(result)
        self.assertEqual(swap.status, "invalid_preimage")


class TestSwapFailure(unittest.TestCase):
    def test_fail_swap(self):
        bridge = QuantumAtomicBridge()
        bridge.register_chain("excal", "excalibur")
        bridge.register_chain("btc", "bitcoin")
        bridge.entangle_chains("excal", "btc")
        bridge.detect_wormhole(threshold=0.1)

        swap = bridge.create_swap(
            SwapDirection.EXCAL_TO_BTC, 1.0, "excal", "btc"
        )
        result = bridge.fail_swap(swap.swap_id, "timeout")
        self.assertTrue(result)
        self.assertEqual(swap.status, "failed:timeout")
        self.assertEqual(bridge.state.failed_swaps, 1)


class TestHealthReport(unittest.TestCase):
    def test_health_report(self):
        bridge = QuantumAtomicBridge()
        report = bridge.get_health_report()
        self.assertIn("phase", report)
        self.assertIn("wormhole_active", report)
        self.assertIn("active_swaps", report)
        self.assertEqual(report["phase"], "idle")


class TestReset(unittest.TestCase):
    def test_reset(self):
        bridge = QuantumAtomicBridge()
        bridge.register_chain("excal", "excalibur")
        bridge.reset()
        self.assertEqual(bridge.state.phase, BridgePhase.IDLE)
        self.assertEqual(len(bridge.swaps), 0)


if __name__ == "__main__":
    unittest.main()
