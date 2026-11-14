import os
import tempfile
import unittest

import genesis_fork
import txscript
from wallet_transactions import (
    address_lock,
    amount_to_swords,
    build_pqh_transaction,
    create_pqh_key,
)


class TestConsensusWalletTransactions(unittest.TestCase):
    def test_address_amount_and_transaction_match_consensus(self):
        genesis_fork.use_network("fork")
        seed = bytes.fromhex("01" * 32)
        sender = create_pqh_key(seed)
        address_lock(sender["address"])
        recipient = "AB" * 20
        self.assertEqual(amount_to_swords("0.5"), 50_000_000)
        with self.assertRaises(ValueError):
            amount_to_swords("0.000000001")

        lock = txscript.lock_pqh_for_root(bytes.fromhex(sender["public_key"]))
        utxos = [{
            "txid": "11" * 32,
            "vout": 0,
            "value": 200_000_000,
            "script": lock.hex(),
            "coinbase": False,
            "height": 1,
            "tip_height": 30_000,
        }]
        with tempfile.TemporaryDirectory() as state_dir:
            raw = build_pqh_transaction(
                seed=seed,
                address=sender["address"],
                utxos=utxos,
                recipient=recipient,
                amount="0.5",
                state_dir=os.path.join(state_dir, "trifold"),
                registry_path=os.path.join(state_dir, "spent.jsonl"),
            )

        ok, reason, fee = txscript.validate_tx(
            raw,
            {(bytes.fromhex("11" * 32), 0): [
                (200_000_000, lock, False, 1)
            ]},
            30_001,
        )
        self.assertTrue(ok, reason)
        self.assertEqual(fee, 1_000)
        parsed = txscript.parse_tx(raw)
        self.assertEqual(parsed["vout"][0]["script"], address_lock(recipient))
        self.assertEqual(parsed["vout"][0]["value"], 50_000_000)

    def test_insufficient_funds_does_not_sign_or_reserve_leaf(self):
        seed = bytes.fromhex("02" * 32)
        sender = create_pqh_key(seed)
        lock = txscript.lock_pqh_for_root(bytes.fromhex(sender["public_key"]))
        with tempfile.TemporaryDirectory() as state_dir:
            with self.assertRaisesRegex(ValueError, "insufficient confirmed balance"):
                build_pqh_transaction(
                    seed=seed,
                    address=sender["address"],
                    utxos=[{
                        "txid": "22" * 32,
                        "vout": 0,
                        "value": 1,
                        "script": lock.hex(),
                        "coinbase": False,
                        "height": 1,
                        "tip_height": 30_000,
                    }],
                    recipient="CD" * 20,
                    amount="1",
                    state_dir=os.path.join(state_dir, "trifold"),
                    registry_path=os.path.join(state_dir, "spent.jsonl"),
                )
            self.assertFalse(os.path.exists(os.path.join(state_dir, "spent.jsonl")))


if __name__ == "__main__":
    unittest.main()
