import unittest
from types import SimpleNamespace

from rosetta.excal_rosetta import ExcalRosetta, CURRENCY, _display_hash
from rosetta.construction import Construction
from txscript import lock_type, ser_tx, txid_internal
import genesis_fork
from genesis_fork import qlock_activation
import secp256k1 as secp


class RosettaDataTests(unittest.TestCase):
    def setUp(self):
        # Pin the process-global network selection: importing fork_node
        # (or constructing a ChainStore, as the atomic-swap tests do)
        # flips genesis_fork's global to "fork" (qlock_activation 0).
        # These tests assume the import-time default (testnet, qlock 102);
        # without the pin they pass alone and fail in the full suite.
        genesis_fork.use_network("testnet")
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
        self.app = ExcalRosetta(self.cs, network="mainnet")
        self.net = {"network_identifier": {"blockchain": "excal", "network": "mainnet" }}

    def test_canonical_chain_path_does_not_require_by_height_map(self):
        records = [self.genesis, self.block1]
        cs = SimpleNamespace(
            index={self.genesis["hash"]: self.genesis,
                   self.block1["hash"]: self.block1},
            tip=lambda: {"height": 1, "hash": self.block1["hash"].hex()},
            _path_to=lambda tip_hash: records if tip_hash == self.block1["hash"] else [])
        app = ExcalRosetta(cs, network="mainnet")
        self.assertEqual(app._record(0)["hash"], self.genesis["hash"])
        self.assertEqual(app._record(1)["hash"], self.block1["hash"])

    def test_network_list(self):
        status, body = self.app.handle("/network/list", {})
        self.assertEqual(status, 200)
        self.assertEqual(body["network_identifiers"][0]["blockchain"], "excal")

    def test_network_options(self):
        status, body = self.app.handle("/network/options", self.net)
        self.assertEqual(status, 200)
        self.assertIn("coinbase", body["allow"]["operation_types"])
        # Historical lookup is a real capability: /account/balance with a
        # block identifier replays the canonical chain via ChainState
        # _fork_utxo (verified live at heights 100/1000/25000/42899/49899
        # against the 50k fork chain, exact to the sword). When a backend
        # cannot replay, the endpoint fails closed (code 5) instead.
        self.assertTrue(body["allow"]["historical_balance_lookup"])

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

    def test_historical_balance_fails_closed_without_replay_backend(self):
        req = dict(self.net, account_identifier={"address": "lock:00aa"},
                   block_identifier={"index": 0})
        status, body = self.app.handle("/account/balance", req)
        self.assertEqual(status, 500)
        self.assertEqual(body["code"], 5)

    def test_historical_balance_uses_chainstate_replay(self):
        script = bytes([0]) + bytes.fromhex("ab" * 20)
        key = (bytes.fromhex("33" * 32), 0)
        self.cs._fork_utxo = lambda block_hash: {key: [(777, script, False, 0)]}
        app = ExcalRosetta(self.cs, network="mainnet")
        req = dict(self.net,
                   account_identifier={"address": "lock:" + script.hex()},
                   block_identifier={"index": 0})
        status, body = app.handle("/account/balance", req)
        self.assertEqual(status, 200)
        self.assertEqual(body["balances"][0]["value"], "777")
        self.assertEqual(body["block_identifier"]["index"], 0)

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

    def test_grandfathered_p2pk_spend_survives_qlock_activation(self):
        pub = secp.compress(secp.priv_to_pub(1))
        p2pk = b"\x21" + pub + b"\xac"
        pkh = b"\x00" + b"\x77" * 20
        prev = bytes.fromhex("ab" * 32)
        coin = prev[::-1].hex() + ":0"
        height = qlock_activation()
        cs = SimpleNamespace(
            utxo={(prev, 0): [(10000, p2pk, False, 0)]},
            tip=lambda: {"height": height - 1, "hash": bytes(32)})
        builder = Construction(cs)
        result = builder.handle("/construction/payloads", {
            "metadata": {
                "inputs": [{"coin": coin, "value": 10000,
                            "lock": p2pk.hex(), "lock_type": "p2pk"}],
                "outputs": [{"value": 9000, "lock": pkh.hex(),
                             "lock_type": "pkh"}],
                "fee": 1000}})
        self.assertEqual([p["signature_type"] for p in result["payloads"]], ["ecdsa"])

    def test_new_p2pk_output_is_rejected_after_qlock_activation(self):
        pub = secp.compress(secp.priv_to_pub(1))
        p2pk = b"\x21" + pub + b"\xac"
        pkh = b"\x00" + b"\x77" * 20
        prev = bytes.fromhex("ac" * 32)
        coin = prev[::-1].hex() + ":0"
        height = qlock_activation()
        cs = SimpleNamespace(
            utxo={(prev, 0): [(10000, pkh, False, 0)]},
            tip=lambda: {"height": height - 1, "hash": bytes(32)})
        builder = Construction(cs)
        with self.assertRaisesRegex(ValueError, "legacy p2pk outputs are retired"):
            builder.handle("/construction/payloads", {
                "metadata": {
                    "inputs": [{"coin": coin, "value": 10000,
                                "lock": pkh.hex(), "lock_type": "pkh"}],
                    "outputs": [{"value": 9000, "lock": p2pk.hex(),
                                 "lock_type": "p2pk"}],
                    "fee": 1000}})

    def test_block_transaction_reports_fee_from_historical_prevout(self):
        lock = bytes([0]) + bytes.fromhex("77" * 20)
        coinbase = ser_tx({
            "version": 1,
            "vin": [{"prev": bytes(32), "idx": 0xffffffff,
                     "script": b"", "seq": 0xffffffff}],
            "vout": [{"value": 50000, "script": lock}],
            "locktime": 0})
        prev = txid_internal(coinbase)
        spend = ser_tx({
            "version": 1,
            "vin": [{"prev": prev, "idx": 0,
                     "script": b"", "seq": 0xffffffff}],
            "vout": [{"value": 49000, "script": lock}],
            "locktime": 0})
        self.cs.by_height[0]["txs"] = [coinbase]
        self.cs.by_height[1]["txs"] = [spend]
        app = ExcalRosetta(self.cs, network="mainnet")
        block = app._block(1)
        self.assertEqual(block["transactions"][0]["metadata"]["fee"], "1000")
        self.assertEqual(block["transactions"][0]["operations"][0]["amount"]["value"], "-50000")

    def test_testnet_uses_canonical_ticker(self):
        app = ExcalRosetta(self.cs, network="testnet")
        self.assertEqual(app.currency, {"symbol": "tEXCAL", "decimals": 8})

    def test_construction_parse_resolves_historical_spent_prevout(self):
        prev = bytes.fromhex("44" * 32)
        lock = bytes([0]) + bytes([0x55]) * 20
        dest = bytes([0]) + bytes([0x66]) * 20
        tx = {"version": 1,
              "vin": [{"prev": prev, "idx": 2, "script": b"", "seq": 0xffffffff}],
              "vout": [{"value": 9000, "script": dest}],
              "locktime": 0}
        raw = ser_tx(tx)
        cs = SimpleNamespace(
            utxo={},
            tip=lambda: {"height": 12, "hash": bytes(32)})
        lookup = lambda key: {"value": 10000, "script": lock} if key == (prev, 2) else None
        builder = Construction(cs, output_lookup=lookup)
        parsed = builder.handle("/construction/parse", {"transaction": raw.hex()})
        self.assertEqual(parsed["operations"][0]["amount"]["value"], "-10000")
        self.assertEqual(parsed["account_identifier_signers"][0]["address"],
                         "lock:" + lock.hex())

    def test_hash_format_is_display_order(self):
        raw = bytes(range(32))
        self.assertEqual(_display_hash(raw), raw[::-1].hex())

    def test_submit_uses_live_mempool_without_claiming_p2p_relay(self):
        raw = ser_tx({
            "version": 1,
            "vin": [{"prev": bytes.fromhex("11" * 32), "idx": 0,
                     "script": b"", "seq": 0xffffffff}],
            "vout": [{"value": 1, "script": b"\xff"}],
            "locktime": 0})
        calls = []
        pool = SimpleNamespace(add=lambda tx, utxo, height: (
            calls.append((tx, utxo, height)) or (True, "ok")))
        cs = SimpleNamespace(utxo={}, tip=lambda: {"height": 10, "hash": bytes(32)})
        builder = Construction(cs, mempool=pool)
        result = builder.handle("/construction/submit", {
            "signed_transaction": raw.hex()})
        self.assertEqual(len(calls), 1)
        self.assertTrue(result["metadata"]["mempool_accepted"])
        self.assertFalse(result["metadata"]["relay_attempted"])
        self.assertEqual(result["metadata"]["connected_peers"], 0)

    def test_submit_reports_mempool_rejection(self):
        raw = ser_tx({
            "version": 1,
            "vin": [{"prev": bytes.fromhex("22" * 32), "idx": 0,
                     "script": b"", "seq": 0xffffffff}],
            "vout": [{"value": 1, "script": b"\xff"}],
            "locktime": 0})
        pool = SimpleNamespace(add=lambda *_args: (False, "missing input"))
        cs = SimpleNamespace(utxo={}, tip=lambda: {"height": 10, "hash": bytes(32)})
        builder = Construction(cs, mempool=pool)
        with self.assertRaisesRegex(ValueError, "mempool rejected"):
            builder.handle("/construction/submit", {
                "signed_transaction": raw.hex()})


class RosettaNetworkIsolationTests(unittest.TestCase):
    """Regression: Construction gates must not follow the process-global
    network selection. Importing fork_node / constructing a ChainStore
    flips genesis_fork's global to "fork" (qlock_activation 0); a
    mainnet Construction must still allow legacy outputs at height 0,
    and a fork Construction must retire them there."""

    def setUp(self):
        genesis_fork.use_network("fork")
        self.addCleanup(genesis_fork.use_network, "testnet")
        self.assertEqual(qlock_activation(), 0)
        prev = bytes.fromhex("55" * 32)
        self.coin = prev[::-1].hex() + ":0"
        self.cs = SimpleNamespace(
            utxo={(prev, 0): [(10000, b"\x51", False, 0)]},
            tip=lambda: {"height": -1, "hash": bytes(32)})
        self.body = {"metadata": {
            "inputs": [{"coin": self.coin, "value": 10000,
                        "lock": "51", "lock_type": "anyone"}],
            "outputs": [{"value": 9000, "lock": "51",
                         "lock_type": "anyone"}],
            "fee": 1000}}

    def test_mainnet_construction_ignores_fork_global(self):
        builder = Construction(self.cs, network="mainnet")
        result = builder.handle("/construction/payloads", self.body)
        self.assertEqual(result["payloads"], [])

    def test_fork_construction_retires_legacy_outputs_at_height_zero(self):
        builder = Construction(self.cs, network="fork")
        with self.assertRaisesRegex(ValueError, "legacy anyone outputs are retired"):
            builder.handle("/construction/payloads", self.body)

    def test_unpinned_construction_still_follows_global(self):
        # Documents the remaining legacy behaviour: without a network the
        # global selection applies (and is what the full-suite failure was).
        builder = Construction(self.cs)
        with self.assertRaisesRegex(ValueError, "legacy anyone outputs are retired"):
            builder.handle("/construction/payloads", self.body)

    def test_app_gates_follow_chain_network_not_label(self):
        # Production mapping: Rosetta label "mainnet" served over the live
        # fork chain must enforce fork gates (qlock 0), not label gates.
        app = ExcalRosetta(self.cs, network="mainnet", chain_network="fork")
        self.assertEqual(app.construction.network, "fork")
        with self.assertRaisesRegex(ValueError, "legacy anyone outputs are retired"):
            app.construction.handle("/construction/payloads", self.body)

    def test_app_gates_default_to_label_without_chain_network(self):
        app = ExcalRosetta(self.cs, network="mainnet")
        self.assertEqual(app.construction.network, "mainnet")
        self.assertEqual(app.construction.handle("/construction/payloads", self.body)["payloads"], [])


class RosettaBlockCacheTests(unittest.TestCase):
    """Regression: _utxo_before replayed the whole canonical path through
    ChainState._fork_utxo on every /block and /network/status call
    (~14s at the 50k tip), so the official CLI timed out. Pre/post-block
    UTXO views are now cached per (height, block hash)."""

    def setUp(self):
        genesis_fork.use_network("testnet")
        self.lock1 = bytes([0]) + bytes.fromhex("11" * 20)
        self.lock2 = bytes([0]) + bytes.fromhex("22" * 20)
        self.cb1 = ser_tx({
            "version": 1,
            "vin": [{"prev": bytes(32), "idx": 0xffffffff,
                     "script": b"", "seq": 0xffffffff}],
            "vout": [{"value": 50000, "script": self.lock1}],
            "locktime": 0})
        self.cb1_txid = txid_internal(self.cb1)
        self.spend = ser_tx({
            "version": 1,
            "vin": [{"prev": self.cb1_txid, "idx": 0,
                     "script": b"", "seq": 0xffffffff}],
            "vout": [{"value": 49000, "script": self.lock2}],
            "locktime": 0})
        ghash = bytes.fromhex("11" * 32)
        b1hash = bytes.fromhex("22" * 32)
        b2hash = bytes.fromhex("33" * 32)
        self.genesis = {"height": 0, "hash": ghash, "time": 100,
                        "version": 1, "bits": 0x1f000100, "nonce": 0, "txs": []}
        self.block1 = {"height": 1, "hash": b1hash, "prev": ghash,
                       "time": 160, "version": 1, "bits": 0x1f000100,
                       "nonce": 1, "txs": [self.cb1]}
        self.block2 = {"height": 2, "hash": b2hash, "prev": b1hash,
                       "time": 220, "version": 1, "bits": 0x1f000100,
                       "nonce": 2, "txs": [self.spend]}
        self.by_height = {0: self.genesis, 1: self.block1, 2: self.block2}
        self.tip_hash = b2hash
        self.calls = []
        cs = SimpleNamespace(
            by_height=self.by_height, utxo={},
            tip=lambda: {"height": 2, "hash": self.tip_hash})
        cs._fork_utxo = self._fork_utxo
        self.cs = cs
        self.app = ExcalRosetta(cs, network="mainnet")

    def _fork_utxo(self, prev_hash):
        self.calls.append(bytes(prev_hash))
        if prev_hash == self.genesis["hash"]:
            return {}
        if prev_hash == self.block1["hash"]:
            return {(self.cb1_txid, 0): [(50000, self.lock1, True, 1)]}
        raise ValueError("unexpected replay for " + bytes(prev_hash).hex())

    def test_repeat_block_render_replays_once(self):
        self.app._block(1)
        self.app._block(1)
        self.assertEqual(len(self.calls), 1)

    def test_sequential_blocks_reuse_post_view(self):
        self.app._block(1)
        block2 = self.app._block(2)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(block2["transactions"][0]["metadata"]["fee"], "1000")

    def test_reorged_block_renders_new_transactions(self):
        self.app._block(1)
        cb_new = ser_tx({
            "version": 1,
            "vin": [{"prev": bytes(32), "idx": 0xffffffff,
                     "script": b"", "seq": 0xffffffff}],
            "vout": [{"value": 60000, "script": self.lock1}],
            "locktime": 0})
        b1hash2 = bytes.fromhex("44" * 32)
        self.by_height[1] = {"height": 1, "hash": b1hash2,
                             "prev": self.genesis["hash"], "time": 160,
                             "version": 1, "bits": 0x1f000100, "nonce": 9,
                             "txs": [cb_new]}
        self.tip_hash = b1hash2
        block = self.app._block(1)
        self.assertEqual(
            block["transactions"][0]["operations"][0]["amount"]["value"], "60000")

    def test_historical_balance_replays_once(self):
        net = {"network_identifier": {"blockchain": "excal", "network": "mainnet"}}
        req = dict(net, account_identifier={"address": "lock:" + self.lock1.hex()},
                   block_identifier={"index": 1})
        status, body = self.app.handle("/account/balance", req)
        self.assertEqual(status, 200)
        self.assertEqual(body["balances"][0]["value"], "50000")
        status, body = self.app.handle("/account/balance", req)
        self.assertEqual(status, 200)
        self.assertEqual(body["balances"][0]["value"], "50000")
        self.assertEqual(len(self.calls), 1)


if __name__ == "__main__":
    unittest.main()
