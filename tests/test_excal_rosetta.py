import unittest
from types import SimpleNamespace

from rosetta.excal_rosetta import ExcalRosetta, CURRENCY, _display_hash


class RosettaDataTests(unittest.TestCase):
    def setUp(self):
        # Minimal canonical chainstate-shaped fixture. Hashes are wire-order.
        ghash = bytes.fromhex("11" * 32)
        b1hash = bytes.fromhex("22" * 32)
        self.genesis = {"height": 0, "hash": ghash, "time": 100,
                        "version": 1, "bits": 0x1f000100, "nonce": 0,
                        "txs": []}
        self.block1 = {"height": 1, "hash": b1hash, "prev": ghash,
                       "time": 160, "version": 1, "bits": 0x1f000100,
                       "nonce": 1, "txs": []}
        self.cs = SimpleNamespace(
            by_height={0: self.genesis, 1: self.block1},
            utxo={},
            tip=lambda: {"height": 1, "hash": b1hash},
        )
        self.app = ExcalRosetta(self.cs, network="fork")
        self.net = {"network_identifier": {"blockchain": "EXCAL", "network": "fork" }}

    def test_network_list(self):
        status, body = self.app.handle("/network/list", {})
        self.assertEqual(status, 200)
        self.assertEqual(body["network_identifiers"][0]["blockchain"], "EXCAL")

    def test_network_options(self):
        status, body = self.app.handle("/network/options", self.net)
        self.assertEqual(status, 200)
        self.assertIn("MINING", body["allow"]["operation_types"])
        self.assertFalse(body["allow"]["historical_balance_lookup"])

    def test_network_status_uses_tip(self):
        status, body = self.app.handle("/network/status", self.net)
        self.assertEqual(status, 200)
        self.assertEqual(body["current_block_identifier"]["index"], 1)
        self.assertEqual(body["genesis_block_identifier"]["index"], 0)

    def test_wrong_network_fails_closed(self):
        status, body = self.app.handle("/network/status", {
            "network_identifier": {"blockchain": "GSF", "network": "mainnet"}})
        self.assertEqual(status, 500)
        self.assertEqual(body["code"], 1)

    def test_balance_exact_script(self):
        script = bytes.fromhex("00" + "ab" * 20)
        key = (bytes.fromhex("33" * 32), 0)
        self.cs.utxo = {key: (123456, script, False, 1)}
        req = dict(self.net, account_identifier={"address": "lock:" + script.hex()})
        status, body = self.app.handle("/account/balance", req)
        self.assertEqual(status, 200)
        self.assertEqual(body["balances"][0]["value"], "123456")
        self.assertEqual(body["balances"][0]["currency"], CURRENCY)

    def test_unknown_account_format_rejected(self):
        req = dict(self.net, account_identifier={"address": "1BitcoinAddress"})
        status, body = self.app.handle("/account/balance", req)
        self.assertEqual(status, 500)
        self.assertEqual(body["code"], 4)

    def test_historical_balance_explicitly_unsupported(self):
        req = dict(self.net, account_identifier={"address": "lock:00aa"},
                   block_identifier={"index": 0})
        status, body = self.app.handle("/account/balance", req)
        self.assertEqual(status, 500)
        self.assertEqual(body["code"], 5)

    def test_construction_is_not_falsely_advertised(self):
        status, body = self.app.handle("/construction/payloads", self.net)
        self.assertEqual(status, 501)
        self.assertEqual(body["code"], 6)

    def test_hash_format_is_display_order(self):
        raw = bytes(range(32))
        self.assertEqual(_display_hash(raw), raw[::-1].hex())


if __name__ == "__main__":
    unittest.main()
