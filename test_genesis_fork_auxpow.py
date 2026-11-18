import struct
import unittest
from unittest.mock import patch

import genesis_fork as gf


class AuxPowTargetTests(unittest.TestCase):
    def setUp(self):
        self.original_network = next(
            name for name, params in gf.NETWORKS.items() if params is gf.network()
        )
        gf.use_network("fork")

    def tearDown(self):
        gf.use_network(self.original_network)

    def test_parent_header_needs_child_work_not_parent_chain_consensus(self):
        block = {
            "version": 1,
            "prev": bytes(32),
            "merkle": bytes(32),
            "time": 1_700_000_000,
            "bits": 0x207FFFFF,
            "nonce": 0,
            "txs": [],
        }
        child_hash = gf._header_hash_of(block)
        coinbase = (
            b"merged-mining"
            + gf.AUXPOW_MAGIC
            + child_hash
            + struct.pack("<II", 1, 0)
        )
        parent_header = (
            struct.pack("<I", 1)
            + bytes(32)
            + gf.txid(coinbase)
            + struct.pack("<III", 1_700_000_001, 0x01000001, 0)
        )
        parent_target = gf.bits_to_target(0x01000001)
        child_target = gf.bits_to_target(block["bits"])
        nonce = 0
        while int.from_bytes(gf.sha256d(parent_header), "big") > child_target:
            nonce += 1
            parent_header = parent_header[:76] + struct.pack("<I", nonce)

        self.assertEqual(parent_target, 0)
        self.assertLessEqual(int.from_bytes(gf.sha256d(parent_header), "big"), child_target)
        block["auxpow"] = {
            "parent_header": parent_header,
            "parent_coinbase": coinbase,
            "coinbase_branch": [],
            "coinbase_index": 0,
        }

        with patch("genesis_fork.validate_block", return_value=None):
            self.assertIsNone(gf.validate_auxpow(block, {}, 23785, []))


if __name__ == "__main__":
    unittest.main()
