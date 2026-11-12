import hashlib
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
)
import deliver_seed as watcher
TXID = "ab" * 32
def p2wsh(script):
    return (b"\x00\x20" + hashlib.sha256(script).digest()).hex()
def op_return(tag, pubkey):
    payload = tag.encode() + pubkey
    return (b"\x6a" + bytes([len(payload)]) + payload).hex()
class WatcherSecurityTests(unittest.TestCase):
    def setUp(self):
        self.lot = {
            "lot": "test",
            "label": "test lot",
            "tag": "EXCALTEST",
            "secret_hash": "11" * 32,
            "ask_sats": 100000,
            "issue": 12,
        }
        self.pubkey = bytes.fromhex(
            "02" + "22" * 32
        )
    def test_matching_script_selects_committed_output(self):
        script = b"test witness script"
        tx = {
            "txid": TXID,
            "vout": [
                {
                    "scriptpubkey": p2wsh(b"wrong script"),
                    "value": 100000,
                },
                {
                    "scriptpubkey": p2wsh(script),
                    "value": 100000,
                },
                {
                    "scriptpubkey": op_return("EXCALTEST", self.pubkey),
                    "value": 0,
                },
            ],
        }
        found = watcher.find_delivery_key(
            tx, [self.lot], witness_script=script
        )
        self.assertIsNotNone(found)
        self.assertEqual(found[2], 1)
        self.assertEqual(found[4], bytes.fromhex(p2wsh(script)))
    def test_mismatched_script_is_rejected(self):
        tx = {
            "txid": TXID,
            "vout": [
                {
                    "scriptpubkey": p2wsh(b"funded script"),
                    "value": 100000,
                },
                {
                    "scriptpubkey": op_return("EXCALTEST", self.pubkey),
                    "value": 0,
                },
            ],
        }
        found = watcher.find_delivery_key(
            tx, [self.lot], witness_script=b"comment script"
        )
        self.assertIsNone(found)
    def test_ambiguous_matching_outputs_are_rejected(self):
        script = b"same witness script"
        tx = {
            "txid": TXID,
            "vout": [
                {"scriptpubkey": p2wsh(script), "value": 100000},
                {"scriptpubkey": p2wsh(script), "value": 100000},
                {
                    "scriptpubkey": op_return("EXCALTEST", self.pubkey),
                    "value": 0,
                },
            ],
        }
        with self.assertRaises(ValueError):
            watcher.find_delivery_key(
                tx, [self.lot], witness_script=script
            )
    def test_wrong_transaction_id_is_rejected(self):
        tx = {
            "txid": "cd" * 32,
            "status": {
                "confirmed": True,
                "block_height": 100,
            },
        }
        with self.assertRaisesRegex(ValueError, "different txid"):
            watcher.verify_confirmed_tx(tx, TXID, 100)
    def test_unconfirmed_transaction_is_rejected(self):
        tx = {
            "txid": TXID,
            "status": {
                "confirmed": False,
                "block_height": None,
            },
        }
        with self.assertRaisesRegex(ValueError, "not confirmed"):
            watcher.verify_confirmed_tx(tx, TXID, 100)
    def test_confirmation_depth_is_enforced(self):
        tx = {
            "txid": TXID,
            "status": {
                "confirmed": True,
                "block_height": 100,
            },
        }
        with self.assertRaisesRegex(ValueError, "1 confirmations"):
            watcher.verify_confirmed_tx(
                tx, TXID, 100, min_confirmations=2
            )
        self.assertEqual(
            watcher.verify_confirmed_tx(
                tx, TXID, 100, min_confirmations=1
            ),
            1,
        )
    def test_missing_issue_script_is_not_marked_seen(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_file = os.path.join(tmp, "watch_state.json")
            tx = {
                "txid": TXID,
                "vout": [
                    {
                        "scriptpubkey": p2wsh(b"unknown script"),
                        "value": 100000,
                    },
                    {
                        "scriptpubkey": op_return(
                            "EXCALTEST", self.pubkey
                        ),
                        "value": 0,
                    },
                ],
            }
            with patch.object(watcher, "STATE_FILE", state_file), \
                 patch.object(watcher, "all_lots", return_value=[self.lot]), \
                 patch.object(watcher, "signal_txs", return_value=[tx]), \
                 patch.object(watcher, "issue_witness_scripts", return_value={}):
                watcher.check_once()
                watcher.check_once()
                # With the seen-marking removed, a candidate with no
                # posted script writes no state at all; load_state()
                # returns the empty default when the file is absent.
                state = watcher.load_state()
                lot_state = state["lots"].get("test", {})
                self.assertNotIn(TXID, lot_state.get("seen", []))
                self.assertIsNone(lot_state.get("delivered_txid"))
    def test_blockcypher_confirmation_metadata_is_preserved(self):
        bc_tx = {
            "hash": TXID,
            "confirmations": 3,
            "block_height": 100,
            "outputs": [
                {"script": "0020" + "33" * 32, "value": 100000}
            ],
        }
        tx = watcher.bc_tx_to_mempool_shape(bc_tx)
        self.assertTrue(tx["status"]["confirmed"])
        self.assertEqual(tx["status"]["block_height"], 100)
        self.assertEqual(tx["status"]["confirmations"], 3)
if __name__ == "__main__":
    unittest.main(verbosity=2)
