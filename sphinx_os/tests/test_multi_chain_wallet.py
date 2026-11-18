#!/usr/bin/env python3
"""Tests for the multi-chain wallet receiver module."""

import os
import sys
import json
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sphinx_os.nexus.multi_chain_wallet import (
    ChainType,
    ChainWallet,
    BalanceInfo,
    TransactionAlert,
    MultiChainWallet,
    BTCAddressGenerator,
    EXCALAddressGenerator,
    MoneroAddressGenerator,
    TariAddressGenerator,
    QubicAddressGenerator,
    WalletGenerator,
    BalanceMonitor,
    export_wallet,
    import_wallet,
    create_multi_chain_wallet,
    create_wallet_monitor,
)


class TestChainType(unittest.TestCase):
    """Test ChainType enum."""

    def test_all_chains_present(self):
        chains = [c.value for c in ChainType]
        self.assertIn("bitcoin", chains)
        self.assertIn("excal", chains)
        self.assertIn("monero", chains)
        self.assertIn("tari", chains)
        self.assertIn("qubic", chains)

    def test_chain_count(self):
        self.assertEqual(len(ChainType), 5)


class TestChainWallet(unittest.TestCase):
    """Test ChainWallet dataclass."""

    def test_create_wallet(self):
        wallet = ChainWallet(
            chain=ChainType.EXCAL,
            address="ABCDEF1234567890ABCDEF1234567890ABCDEF12",
            private_key="0123456789abcdef" * 4,
        )
        self.assertEqual(wallet.chain, ChainType.EXCAL)
        self.assertEqual(len(wallet.address), 40)
        self.assertEqual(wallet.public_key, "")
        self.assertEqual(wallet.derivation_path, "")
        self.assertEqual(wallet.metadata, {})


class TestBalanceInfo(unittest.TestCase):
    """Test BalanceInfo dataclass."""

    def test_default_balance(self):
        balance = BalanceInfo(chain=ChainType.BTC, address="1ABC")
        self.assertEqual(balance.confirmed_balance, 0.0)
        self.assertEqual(balance.unconfirmed_balance, 0.0)
        self.assertEqual(balance.tx_count, 0)

    def test_custom_balance(self):
        balance = BalanceInfo(
            chain=ChainType.EXCAL,
            address="ABCDEF",
            confirmed_balance=100.0,
            tx_count=5,
        )
        self.assertEqual(balance.confirmed_balance, 100.0)
        self.assertEqual(balance.tx_count, 5)


class TestTransactionAlert(unittest.TestCase):
    """Test TransactionAlert dataclass."""

    def test_incoming_alert(self):
        alert = TransactionAlert(
            chain=ChainType.BTC,
            address="1ABC",
            tx_id="tx123",
            amount=1.5,
        )
        self.assertTrue(alert.is_incoming)
        self.assertEqual(alert.amount, 1.5)

    def test_outgoing_alert(self):
        alert = TransactionAlert(
            chain=ChainType.EXCAL,
            address="ABCDEF",
            tx_id="tx456",
            amount=50.0,
            is_incoming=False,
        )
        self.assertFalse(alert.is_incoming)


class TestBTCAddressGenerator(unittest.TestCase):
    """Test Bitcoin address generation."""

    def test_generate_returns_wallet(self):
        seed = b"\x01" * 32
        wallet = BTCAddressGenerator.generate(seed)
        self.assertIsInstance(wallet, ChainWallet)
        self.assertEqual(wallet.chain, ChainType.BTC)
        self.assertTrue(wallet.address.startswith("1"))
        self.assertTrue(len(wallet.address) > 20)

    def test_generate_has_keys(self):
        seed = b"\x02" * 32
        wallet = BTCAddressGenerator.generate(seed)
        self.assertEqual(len(wallet.private_key), 64)  # 32 bytes hex
        self.assertTrue(wallet.public_key)

    def test_deterministic(self):
        seed = b"\x03" * 32
        w1 = BTCAddressGenerator.generate(seed)
        w2 = BTCAddressGenerator.generate(seed)
        self.assertEqual(w1.address, w2.address)


class TestEXCALAddressGenerator(unittest.TestCase):
    """Test EXCAL address generation."""

    def test_generate_returns_wallet(self):
        seed = b"\x04" * 32
        wallet = EXCALAddressGenerator.generate(seed)
        self.assertIsInstance(wallet, ChainWallet)
        self.assertEqual(wallet.chain, ChainType.EXCAL)
        self.assertEqual(len(wallet.address), 40)

    def test_address_is_uppercase_hex(self):
        seed = b"\x05" * 32
        wallet = EXCALAddressGenerator.generate(seed)
        self.assertEqual(wallet.address, wallet.address.upper())
        int(wallet.address, 16)  # Should not raise

    def test_deterministic(self):
        seed = b"\x06" * 32
        w1 = EXCALAddressGenerator.generate(seed)
        w2 = EXCALAddressGenerator.generate(seed)
        self.assertEqual(w1.address, w2.address)

    def test_metadata(self):
        seed = b"\x07" * 32
        wallet = EXCALAddressGenerator.generate(seed)
        self.assertEqual(wallet.metadata.get("type"), "PQH")
        self.assertEqual(wallet.metadata.get("height"), 6)


class TestMoneroAddressGenerator(unittest.TestCase):
    """Test Monero address generation."""

    def test_generate_returns_wallet(self):
        seed = b"\x08" * 32
        wallet = MoneroAddressGenerator.generate(seed)
        self.assertIsInstance(wallet, ChainWallet)
        self.assertEqual(wallet.chain, ChainType.XMR)
        self.assertTrue(len(wallet.address) > 40)

    def test_deterministic(self):
        seed = b"\x09" * 32
        w1 = MoneroAddressGenerator.generate(seed)
        w2 = MoneroAddressGenerator.generate(seed)
        self.assertEqual(w1.address, w2.address)

    def test_metadata(self):
        seed = b"\x0a" * 32
        wallet = MoneroAddressGenerator.generate(seed)
        self.assertEqual(wallet.metadata.get("type"), "stealth")


class TestTariAddressGenerator(unittest.TestCase):
    """Test Tari address generation."""

    def test_generate_returns_wallet(self):
        seed = b"\x0b" * 32
        wallet = TariAddressGenerator.generate(seed)
        self.assertIsInstance(wallet, ChainWallet)
        self.assertEqual(wallet.chain, ChainType.TARI)
        # Base64 of "TR" + public_key starts with "VFK"
        self.assertTrue(wallet.address.startswith("VFK"))

    def test_deterministic(self):
        seed = b"\x0c" * 32
        w1 = TariAddressGenerator.generate(seed)
        w2 = TariAddressGenerator.generate(seed)
        self.assertEqual(w1.address, w2.address)

    def test_metadata(self):
        seed = b"\x0d" * 32
        wallet = TariAddressGenerator.generate(seed)
        self.assertEqual(wallet.metadata.get("type"), "borromean")


class TestQubicAddressGenerator(unittest.TestCase):
    """Test Qubic address generation."""

    def test_generate_returns_wallet(self):
        seed = b"\x0e" * 32
        wallet = QubicAddressGenerator.generate(seed)
        self.assertIsInstance(wallet, ChainWallet)
        self.assertEqual(wallet.chain, ChainType.QUBIC)
        self.assertEqual(len(wallet.address), 32)

    def test_address_is_alphanumeric(self):
        seed = b"\x0f" * 32
        wallet = QubicAddressGenerator.generate(seed)
        self.assertTrue(wallet.address.isalnum())

    def test_deterministic(self):
        seed = b"\x10" * 32
        w1 = QubicAddressGenerator.generate(seed)
        w2 = QubicAddressGenerator.generate(seed)
        self.assertEqual(w1.address, w2.address)


class TestWalletGenerator(unittest.TestCase):
    """Test multi-chain wallet generator."""

    def test_generate_single_chain(self):
        seed = b"\x11" * 32
        gen = WalletGenerator(seed)
        wallet = gen.generate(ChainType.EXCAL)
        self.assertEqual(wallet.chain, ChainType.EXCAL)

    def test_generate_all(self):
        seed = b"\x12" * 32
        gen = WalletGenerator(seed)
        multi = gen.generate_all(label="Test")
        self.assertEqual(len(multi.wallets), 5)
        self.assertEqual(multi.label, "Test")

    def test_deterministic_master_seed(self):
        seed = b"\x13" * 32
        gen1 = WalletGenerator(seed)
        gen2 = WalletGenerator(seed)

        for chain in ChainType:
            w1 = gen1.generate(chain)
            w2 = gen2.generate(chain)
            self.assertEqual(w1.address, w2.address,
                             f"Addresses differ for {chain.value}")

    def test_random_seed(self):
        gen = WalletGenerator()
        self.assertEqual(len(gen.master_seed), 32)

    def test_short_seed_hashed(self):
        gen = WalletGenerator(b"short")
        self.assertEqual(len(gen.master_seed), 32)

    def test_unsupported_chain(self):
        gen = WalletGenerator(b"\x14" * 32)
        # All chains are supported, so this should not raise
        for chain in ChainType:
            wallet = gen.generate(chain)
            self.assertIsInstance(wallet, ChainWallet)


class TestMultiChainWallet(unittest.TestCase):
    """Test MultiChainWallet container."""

    def test_create_wallet(self):
        wallet = MultiChainWallet(master_seed_hex="0123" * 16)
        self.assertEqual(wallet.master_seed_hex, "0123" * 16)
        self.assertEqual(wallet.wallets, {})
        self.assertEqual(wallet.label, "")


class TestBalanceMonitor(unittest.TestCase):
    """Test balance monitoring."""

    def setUp(self):
        seed = b"\x15" * 32
        gen = WalletGenerator(seed)
        self.wallet = gen.generate_all()
        self.monitor = BalanceMonitor(self.wallet.wallets, poll_interval=1)

    def test_initial_balances(self):
        for chain in ChainType:
            balance = self.monitor.get_balance(chain)
            self.assertEqual(balance.confirmed_balance, 0.0)

    def test_check_all_balances(self):
        balances = self.monitor.check_all_balances()
        self.assertEqual(len(balances), 5)

    def test_total_value_zero(self):
        total = self.monitor.get_total_value_usd()
        self.assertEqual(total, 0.0)

    def test_total_value_with_prices(self):
        # Set some balances
        self.monitor.balances[ChainType.BTC].confirmed_balance = 1.0
        self.monitor.balances[ChainType.EXCAL].confirmed_balance = 100.0

        prices = {
            ChainType.BTC: 100000.0,
            ChainType.EXCAL: 1.0,
            ChainType.XMR: 500.0,
            ChainType.TARI: 10.0,
            ChainType.QUBIC: 100.0,
        }
        total = self.monitor.get_total_value_usd(prices)
        self.assertEqual(total, 100000.0 + 100.0)

    def test_format_dashboard(self):
        dashboard = self.monitor.format_dashboard()
        self.assertIn("MULTI-CHAIN WALLET DASHBOARD", dashboard)
        self.assertIn("BITCOIN", dashboard)
        self.assertIn("EXCAL", dashboard)

    def test_alert_callback(self):
        alerts_received = []

        def on_alert(alert):
            alerts_received.append(alert)

        self.monitor.on_alert(on_alert)
        self.assertEqual(len(self.monitor.alert_callbacks), 1)

    def test_start_stop(self):
        self.monitor.start()
        self.assertTrue(self.monitor._running)
        self.monitor.stop()
        self.assertFalse(self.monitor._running)


class TestExportImport(unittest.TestCase):
    """Test wallet export and import."""

    def setUp(self):
        seed = b"\x16" * 32
        self.wallet = create_multi_chain_wallet(master_seed=seed)

    def test_export_creates_file(self):
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
            path = f.name

        try:
            export_wallet(self.wallet, path)
            self.assertTrue(os.path.exists(path))

            with open(path) as f:
                data = json.load(f)

            self.assertIn("master_seed_hex", data)
            self.assertIn("wallets", data)
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_import_restores_wallet(self):
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
            path = f.name

        try:
            export_wallet(self.wallet, path)
            imported = import_wallet(path)

            self.assertEqual(imported.master_seed_hex, self.wallet.master_seed_hex)
            self.assertEqual(len(imported.wallets), len(self.wallet.wallets))

            for chain in ChainType:
                original = self.wallet.wallets.get(chain)
                restored = imported.wallets.get(chain)
                self.assertIsNotNone(restored)
                self.assertEqual(original.address, restored.address)
        finally:
            if os.path.exists(path):
                os.unlink(path)


class TestConvenienceFunctions(unittest.TestCase):
    """Test convenience functions."""

    def test_create_multi_chain_wallet(self):
        wallet = create_multi_chain_wallet(label="Test")
        self.assertEqual(len(wallet.wallets), 5)
        self.assertEqual(wallet.label, "Test")

    def test_create_wallet_monitor(self):
        wallet = create_multi_chain_wallet()
        monitor = create_wallet_monitor(wallet)
        self.assertEqual(len(monitor.wallets), 5)


if __name__ == "__main__":
    unittest.main()
