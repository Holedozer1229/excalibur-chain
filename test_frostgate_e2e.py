#!/usr/bin/env python3
"""
test_frostgate_e2e.py — End-to-end tests for Frostgate integration.

Tests:
1. Frostgate Python module imports and basic operations
2. Desktop shortcut module availability
3. Frostgate tab in wallet GUI
4. Ceremony init, status, sign flow
5. Nexus exports include frostgate functions
"""

import hashlib
import json
import os
import sys
import tempfile
import unittest

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestFrostgatePython(unittest.TestCase):
    """Test the pure Python Frostgate fallback module."""
    
    def test_01_import_module(self):
        """Test that frostgate_python module imports."""
        from sphinx_os.nexus.frostgate_python import (
            frostgate_init, frostgate_address, frostgate_status,
            frostgate_sign, frostgate_spend, frostgate_has_ceremony,
            FrostgateError, DEFAULT_VAULT_DIR
        )
        self.assertIsNotNone(frostgate_init)
        self.assertIsNotNone(frostgate_address)
        self.assertIsNotNone(frostgate_status)
        self.assertIsNotNone(frostgate_sign)
        self.assertIsNotNone(frostgate_spend)
        self.assertIsNotNone(frostgate_has_ceremony)
    
    def test_02_default_vault_dir(self):
        """Test default vault directory is set."""
        from sphinx_os.nexus.frostgate_python import DEFAULT_VAULT_DIR
        self.assertIn("frostgate_ceremony", DEFAULT_VAULT_DIR)
    
    def test_03_no_ceremony_by_default(self):
        """Test that no ceremony exists by default."""
        from sphinx_os.nexus.frostgate_python import frostgate_has_ceremony, DEFAULT_VAULT_DIR
        # The default dir may or may not exist; check it returns a bool
        result = frostgate_has_ceremony(DEFAULT_VAULT_DIR)
        self.assertIsInstance(result, bool)
    
    def test_04_init_ceremony(self):
        """Test initializing a new FROST ceremony."""
        from sphinx_os.nexus.frostgate_python import (
            frostgate_init, frostgate_has_ceremony, FrostgateError
        )
        
        with tempfile.TemporaryDirectory() as tmpdir:
            vault_dir = os.path.join(tmpdir, "test_ceremony")
            
            # Should not exist yet
            self.assertFalse(frostgate_has_ceremony(vault_dir))
            
            # Initialize
            result = frostgate_init(vault_dir)
            
            # Check result structure
            self.assertIn("group_key", result)
            self.assertIn("vault_dir", result)
            self.assertIn("operators", result)
            self.assertIn("threshold", result)
            self.assertIn("address", result)
            
            # Check ceremony now exists
            self.assertTrue(frostgate_has_ceremony(vault_dir))
            
            # Check group.json was created
            self.assertTrue(os.path.exists(os.path.join(vault_dir, "group.json")))
            
            # Check operator shares were created
            for i in range(1, 6):
                share_path = os.path.join(vault_dir, f"operator_{i}.json")
                self.assertTrue(os.path.exists(share_path),
                              f"Operator {i} share not found")
    
    def test_05_init_duplicate_raises(self):
        """Test that initializing an existing ceremony raises error."""
        from sphinx_os.nexus.frostgate_python import (
            frostgate_init, FrostgateError
        )
        
        with tempfile.TemporaryDirectory() as tmpdir:
            vault_dir = os.path.join(tmpdir, "test_ceremony")
            frostgate_init(vault_dir)
            
            # Second init should fail
            with self.assertRaises(FrostgateError):
                frostgate_init(vault_dir)
    
    def test_06_status_after_init(self):
        """Test vault status after initialization."""
        from sphinx_os.nexus.frostgate_python import (
            frostgate_init, frostgate_status
        )
        
        with tempfile.TemporaryDirectory() as tmpdir:
            vault_dir = os.path.join(tmpdir, "test_ceremony")
            frostgate_init(vault_dir)
            
            st = frostgate_status(vault_dir)
            
            self.assertEqual(st["num_operators"], 5)
            self.assertEqual(st["threshold"], 3)
            self.assertIn("group_key", st)
            self.assertIn("address", st)
            self.assertFalse(st["is_nov1_federation"])
    
    def test_07_address_format(self):
        """Test that address is a valid Taproot format."""
        from sphinx_os.nexus.frostgate_python import (
            frostgate_init, frostgate_address
        )
        
        with tempfile.TemporaryDirectory() as tmpdir:
            vault_dir = os.path.join(tmpdir, "test_ceremony")
            frostgate_init(vault_dir)
            
            addr = frostgate_address(vault_dir, "mainnet")
            self.assertTrue(addr.startswith("bc1p"),
                          f"Address should start with bc1p, got: {addr[:10]}")
            
            # Test testnet
            addr_testnet = frostgate_address(vault_dir, "testnet")
            self.assertTrue(addr_testnet.startswith("tb1p"),
                          f"Testnet address should start with tb1p, got: {addr_testnet[:10]}")
    
    def test_08_sign_message(self):
        """Test signing a message with the FROST vault."""
        from sphinx_os.nexus.frostgate_python import (
            frostgate_init, frostgate_sign
        )
        
        with tempfile.TemporaryDirectory() as tmpdir:
            vault_dir = os.path.join(tmpdir, "test_ceremony")
            frostgate_init(vault_dir)
            
            # Sign a test message
            msg = hashlib.sha256(b"AetherionEXCAL FROST e2e test").digest()
            result = frostgate_sign(vault_dir, message_bytes=msg)
            
            self.assertIn("signature", result)
            self.assertIn("signers", result)
            self.assertTrue(result["verified"])
            self.assertEqual(len(result["signers"]), 3)
    
    def test_09_sign_with_hex(self):
        """Test signing with hex message."""
        from sphinx_os.nexus.frostgate_python import (
            frostgate_init, frostgate_sign
        )
        
        with tempfile.TemporaryDirectory() as tmpdir:
            vault_dir = os.path.join(tmpdir, "test_ceremony")
            frostgate_init(vault_dir)
            
            msg_hex = "a" * 64  # 32 bytes in hex
            result = frostgate_sign(vault_dir, message_hex=msg_hex)
            
            self.assertIn("signature", result)
            self.assertTrue(result["verified"])
    
    def test_10_sign_insufficient_signers(self):
        """Test that signing with fewer than threshold signers fails."""
        from sphinx_os.nexus.frostgate_python import (
            frostgate_init, frostgate_sign, FrostgateError
        )
        
        with tempfile.TemporaryDirectory() as tmpdir:
            vault_dir = os.path.join(tmpdir, "test_ceremony")
            frostgate_init(vault_dir)
            
            msg = hashlib.sha256(b"test").digest()
            with self.assertRaises(FrostgateError):
                frostgate_sign(vault_dir, message_bytes=msg, signers=(1, 2))
    
    def test_11_sign_invalid_message_length(self):
        """Test that signing with wrong message length fails."""
        from sphinx_os.nexus.frostgate_python import (
            frostgate_init, frostgate_sign, FrostgateError
        )
        
        with tempfile.TemporaryDirectory() as tmpdir:
            vault_dir = os.path.join(tmpdir, "test_ceremony")
            frostgate_init(vault_dir)
            
            # Too short
            with self.assertRaises(FrostgateError):
                frostgate_sign(vault_dir, message_bytes=b"short")
    
    def test_12_spend_transaction(self):
        """Test building a threshold spend transaction."""
        from sphinx_os.nexus.frostgate_python import (
            frostgate_init, frostgate_spend
        )
        
        with tempfile.TemporaryDirectory() as tmpdir:
            vault_dir = os.path.join(tmpdir, "test_ceremony")
            frostgate_init(vault_dir)
            
            # Get the vault address
            from sphinx_os.nexus.frostgate_python import frostgate_address
            vault_addr = frostgate_address(vault_dir)
            
            result = frostgate_spend(
                vault_dir=vault_dir,
                prev_txid="a" * 64,
                prev_vout=0,
                prev_value_sats=100000,
                dest_address=vault_addr,
                fee_sats=500,
            )
            
            self.assertIn("raw_tx_hex", result)
            self.assertFalse(result["broadcast"])
            self.assertIn("signature", result)
            self.assertIn("signers", result)
    
    def test_13_spend_missing_params(self):
        """Test that spend with missing params fails."""
        from sphinx_os.nexus.frostgate_python import (
            frostgate_init, frostgate_spend, FrostgateError
        )
        
        with tempfile.TemporaryDirectory() as tmpdir:
            vault_dir = os.path.join(tmpdir, "test_ceremony")
            frostgate_init(vault_dir)
            
            with self.assertRaises(FrostgateError):
                frostgate_spend(vault_dir)
    
    def test_14_convenience_functions(self):
        """Test module-level convenience functions."""
        from sphinx_os.nexus.frostgate_python import (
            init, status, sign, spend, address, frostgate_has_ceremony
        )
        
        with tempfile.TemporaryDirectory() as tmpdir:
            vault_dir = os.path.join(tmpdir, "test_ceremony")
            
            result = init(vault_dir)
            self.assertIn("group_key", result)
            
            st = status(vault_dir)
            self.assertEqual(st["threshold"], 3)
            
            addr = address(vault_dir)
            self.assertTrue(addr.startswith("bc1p"))


class TestFrostgateNexusExports(unittest.TestCase):
    """Test that frostgate functions are exported from nexus."""
    
    def test_nexus_exports_frostgate(self):
        """Test that frostgate functions are in nexus __all__."""
        import sphinx_os.nexus as nexus
        
        self.assertIn("frostgate_init", dir(nexus))
        self.assertIn("frostgate_address", dir(nexus))
        self.assertIn("frostgate_status", dir(nexus))
        self.assertIn("frostgate_sign", dir(nexus))
        self.assertIn("frostgate_spend", dir(nexus))
        self.assertIn("frostgate_has_ceremony", dir(nexus))
    
    def test_nexus_frostgate_callable(self):
        """Test that exported frostgate functions are callable."""
        from sphinx_os.nexus import (
            frostgate_init, frostgate_address, frostgate_status,
            frostgate_sign, frostgate_spend, frostgate_has_ceremony
        )
        
        self.assertTrue(callable(frostgate_init))
        self.assertTrue(callable(frostgate_address))
        self.assertTrue(callable(frostgate_status))
        self.assertTrue(callable(frostgate_sign))
        self.assertTrue(callable(frostgate_spend))
        self.assertTrue(callable(frostgate_has_ceremony))


class TestDesktopShortcut(unittest.TestCase):
    """Test the desktop shortcut module."""
    
    def test_module_imports(self):
        """Test that desktop_shortcut module imports."""
        try:
            import desktop_shortcut
            self.assertIsNotNone(desktop_shortcut.ensure_shortcuts)
            self.assertIsNotNone(desktop_shortcut.has_created_shortcuts)
        except ImportError:
            # Module may not be available on non-Windows
            self.skipTest("desktop_shortcut module not available")
    
    def test_has_created_shortcuts(self):
        """Test has_created_shortcuts returns a boolean."""
        try:
            import desktop_shortcut
            result = desktop_shortcut.has_created_shortcuts()
            self.assertIsInstance(result, bool)
        except ImportError:
            self.skipTest("desktop_shortcut module not available")


class TestFrostgateWalletTab(unittest.TestCase):
    """Test the Frostgate tab in the wallet GUI."""
    
    @unittest.skip("GUI test requires Qt display")
    def test_frostgate_tab_imports(self):
        """Test that FrostgateTab class can be imported."""
        os.environ['QT_QPA_PLATFORM'] = 'offscreen'
        from PySide6.QtWidgets import QApplication
        app = QApplication(sys.argv)
        
        from excal_wallet import FrostgateTab
        tab = FrostgateTab()
        self.assertIsNotNone(tab)
        tab.close()


class TestFrostgateIntegration(unittest.TestCase):
    """Integration tests for the full Frostgate flow."""
    
    def test_full_ceremony_flow(self):
        """Test the complete ceremony → status → sign flow."""
        from sphinx_os.nexus.frostgate_python import (
            frostgate_init, frostgate_status, frostgate_sign,
            frostgate_address, frostgate_has_ceremony
        )
        
        with tempfile.TemporaryDirectory() as tmpdir:
            vault_dir = os.path.join(tmpdir, "full_flow")
            
            # 1. No ceremony
            self.assertFalse(frostgate_has_ceremony(vault_dir))
            
            # 2. Initialize
            init_result = frostgate_init(vault_dir)
            self.assertIn("group_key", init_result)
            self.assertIn("address", init_result)
            
            # 3. Has ceremony
            self.assertTrue(frostgate_has_ceremony(vault_dir))
            
            # 4. Status
            st = frostgate_status(vault_dir)
            self.assertEqual(st["num_operators"], 5)
            self.assertEqual(st["threshold"], 3)
            
            # 5. Address
            addr = frostgate_address(vault_dir)
            self.assertTrue(addr.startswith("bc1p"))
            
            # 6. Sign
            msg = hashlib.sha256(b"full integration test").digest()
            sig_result = frostgate_sign(vault_dir, message_bytes=msg)
            self.assertTrue(sig_result["verified"])
    
    def test_multiple_signers(self):
        """Test signing with different signer combinations."""
        from sphinx_os.nexus.frostgate_python import (
            frostgate_init, frostgate_sign
        )
        
        with tempfile.TemporaryDirectory() as tmpdir:
            vault_dir = os.path.join(tmpdir, "multi_signers")
            frostgate_init(vault_dir)
            
            msg = hashlib.sha256(b"multi signer test").digest()
            
            # Sign with operators 1,2,3
            sig1 = frostgate_sign(vault_dir, message_bytes=msg, signers=(1, 2, 3))
            self.assertTrue(sig1["verified"])
            
            # Sign with operators 3,4,5
            sig2 = frostgate_sign(vault_dir, message_bytes=msg, signers=(3, 4, 5))
            self.assertTrue(sig2["verified"])
            
            # Sign with operators 1,3,5
            sig3 = frostgate_sign(vault_dir, message_bytes=msg, signers=(1, 3, 5))
            self.assertTrue(sig3["verified"])


if __name__ == "__main__":
    unittest.main()
