import unittest
from types import SimpleNamespace

from rosetta.excal_rosetta import ExcalRosetta, CURRENCY, _display_hash
from rosetta.construction import Construction
from txscript import lock_type
import secp256k1 as secp


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

    def test_construction_payload_types_cover_all_native_locks(self):
        pub = secp.compress(secp.priv_to_pub(1))
        locks = {
            "pkh": b"\x00" + b"\x11" * 20,
            "open": b"\xff",
            "pqh": b"\x02" + b"\x22" * 20,
            "htlc": b"\x03" + b"\x33" * 20,
            "qhtlc": b"\x04" + b"\x44" * 20,
            "bridge": b"\x05" + b"\x55" * 32,
            "knot": b"\x06" + b"\x66" * 20,
            "p2pk": b"\x21" + pub + b"\xac",
            "anyone": b"\x51",
        }
        expected = {"pkh": "ecdsa", "open": None, "pqh": "trifold",
                    "htlc": "ecdsa", "qhtlc": "trifold", "bridge": "ecdsa",
                    "knot": "excal_knot", "p2pk": "ecdsa", "anyone": None}
        for i, (name, lock) in enumerate(locks.items(), 1):
            self.assertEqual(lock_type(lock), name)
            prev = bytes([i]) * 32
            coin = prev[::-1].hex() + ":0"
            legacy = name in ("p2pk", "anyone")
            height = 0 if legacy else 100000
            out_lock = bytes([0x51]) if legacy else bytes([0]) + bytes([0xaa]) * 20
            out_type = lock_type(out_lock)
            cs = SimpleNamespace(
                utxo={(prev, 0): [(10000, lock, False, 0)]},
                tip=lambda: {"height": height, "hash": bytes(32)})
            builder = Construction(cs)
            result = builder.handle("/construction/payloads", {
                "metadata": {
                    "inputs": [{"coin": coin, "value": 10000,
                                "lock": lock.hex(), "lock_type": name}],
                    "outputs": [{"value": 9000, "lock": out_lock.hex(),
                                 "lock_type": out_type}],
                    "fee": 1000}})
            types = [p["signature_type"] for p in result["payloads"]]
            self.assertEqual(types, [] if expected[name] is None else [expected[name]])

    def test_hash_format_is_display_order(self):
        raw = bytes(range(32))
        self.assertEqual(_display_hash(raw), raw[::-1].hex())


if __name__ == "__main__":
    unittest.main()
