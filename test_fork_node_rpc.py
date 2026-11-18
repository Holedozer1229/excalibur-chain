import http.client
import json
import threading
import unittest
from types import SimpleNamespace

import fork_node
import txscript


class ChainExplorerRpcTests(unittest.TestCase):
    def setUp(self):
        self.store = fork_node.ChainStore.__new__(fork_node.ChainStore)
        self.store.lock = threading.Lock()
        self.store.tip_height = 2
        self.store.by_height = {
            height: {
                "height": height,
                "hash": f"{height:064x}",
                "prev": f"{max(0, height - 1):064x}",
                "merkle": "0" * 64,
                "time": 1_700_000_000 + height,
                "bits": 0x207FFFFF,
                "nonce": height,
                "txs": [bytes([height])],
            }
            for height in range(3)
        }
        self.store.by_hash = {block["hash"]: block for block in self.store.by_height.values()}
        self.store.mempool = {}
        fork_node.ForkRPCHandler.store = self.store
        fork_node.ForkRPCHandler.p2p_node = None

    def tearDown(self):
        fork_node.ForkRPCHandler.p2p_node = None

    def test_block_summary_resolves_height_and_hash_without_raw_transactions(self):
        block = self.store.getblocksummary(2)
        self.assertEqual(block["height"], 2)
        self.assertEqual(block["tx_count"], 1)
        self.assertEqual(block["txids"], [txscript.txid_display(b"\x02")])
        self.assertNotIn("txs", block)
        self.assertEqual(self.store.getblocksummary(block["hash"]), block)

    def test_recent_blocks_are_newest_first_and_count_is_bounded(self):
        self.assertEqual([b["height"] for b in self.store.getrecentblocks(2)], [2, 1])
        self.assertEqual(len(self.store.getrecentblocks(1000)), 3)

    def test_mempool_reports_and_deduplicates_local_and_peer_transactions(self):
        local_tx = b"local transaction"
        peer_tx = b"peer transaction"
        self.store.mempool = {"local": local_tx}
        fork_node.ForkRPCHandler.p2p_node = SimpleNamespace(
            mempool={"local": local_tx, "peer": peer_tx}
        )

        pool = self.store.getmempoolinfo()

        self.assertEqual(pool["size"], 2)
        self.assertEqual(pool["bytes"], len(local_tx) + len(peer_tx))
        self.assertEqual(
            {row["txid"] for row in pool["transactions"]},
            {txscript.txid_display(local_tx), txscript.txid_display(peer_tx)},
        )

    def test_rpc_dispatch_exposes_recent_blocks_summaries_and_mempool(self):
        server = fork_node.ThreadedHTTPServer(("127.0.0.1", 0), fork_node.ForkRPCHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=2)
            for method, params in (
                ("getrecentblocks", [2]),
                ("getblocksummary", [2]),
                ("getmempoolinfo", []),
            ):
                body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
                connection.request("POST", "/", body, {"Content-Type": "application/json"})
                response = connection.getresponse()
                payload = json.loads(response.read())
                self.assertEqual(response.status, 200)
                self.assertIsNone(payload["error"])
                self.assertIsNotNone(payload["result"])
            connection.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
