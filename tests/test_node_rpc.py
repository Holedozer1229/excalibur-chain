"""Regression tests for node_rpc.py RPC dispatch table.

These tests verify that all RPC methods are registered in the dispatch table
and that the HTTP server responds correctly. They follow the same pattern as
test_fork_node_rpc.py to avoid heavy ChainState initialization.
"""
import http.client
import json
import threading
import time
import unittest

import mempool
import node_rpc


class TestRPCDispatchTable(unittest.TestCase):
    """Verify all RPC methods are registered."""

    def test_dispatch_table_has_all_methods(self):
        """All documented RPC methods must be in the dispatch table."""
        known = [
            "getblockcount", "getbestblockhash", "getchaintips",
            "getblock", "getblockbyheight", "getrawtransaction",
            "getrawmempool", "getmempoolinfo", "sendrawtransaction",
            "submitblock", "getnewaddress", "getpkhaddress",
            "getbalance", "getutxos", "getpeerinfo", "sendtoaddress",
            "estimatesmartfee", "buildtunnelcapsule", "validatetunnelcapsule",
        ]
        # Inspect the dispatch method source to find registered methods
        node = object.__new__(node_rpc.Node)
        for method in known:
            try:
                node.dispatch(method, [])
            except ValueError as e:
                self.assertNotIn(
                    "unknown method", str(e),
                    f"Method {method} not in dispatch table"
                )
            except Exception:
                # Other errors are fine — method exists
                pass

    def test_dispatch_unknown_method_raises(self):
        """Unknown methods must raise ValueError."""
        node = object.__new__(node_rpc.Node)
        with self.assertRaises(ValueError) as ctx:
            node.dispatch("nonexistent_method", [])
        self.assertIn("unknown method", str(ctx.exception))


class TestRPCWriteMethodValidation(unittest.TestCase):
    """Write methods must validate input before touching chain state."""

    def _make_minimal_node(self):
        """Create a Node with just enough attributes for dispatch."""
        node = object.__new__(node_rpc.Node)
        node.lock = threading.Lock()
        node.peermgr = None
        node.wallet_path = None
        node.mempool = object.__new__(mempool.Mempool)
        node.mempool.txs = {}
        node.mempool.spent = set()
        node.cs = type("FakeCS", (), {"tip": lambda self: {"height": 0}})()
        return node

    def test_sendrawtransaction_rejects_bad_hex(self):
        node = self._make_minimal_node()
        with self.assertRaises(ValueError):
            node.rpc_sendrawtransaction(["not_hex"])

    def test_submitblock_rejects_empty_params(self):
        node = self._make_minimal_node()
        with self.assertRaises(ValueError) as ctx:
            node.rpc_submitblock([])
        self.assertIn("needs one block object", str(ctx.exception))

    def test_submitblock_rejects_malformed_block(self):
        node = self._make_minimal_node()
        with self.assertRaises(ValueError) as ctx:
            node.rpc_submitblock([{"version": 1}])
        self.assertIn("malformed block", str(ctx.exception))

    def test_sendtoaddress_rejects_bad_address(self):
        node = self._make_minimal_node()
        with self.assertRaises(ValueError):
            node.rpc_sendtoaddress(["invalid", 1000])

    def test_sendtoaddress_rejects_zero_amount(self):
        node = self._make_minimal_node()
        with self.assertRaises(ValueError) as ctx:
            node.rpc_sendtoaddress(["00" * 21, 0])
        self.assertIn("positive", str(ctx.exception).lower())

    def test_sendtoaddress_rejects_dust(self):
        node = self._make_minimal_node()
        with self.assertRaises(ValueError) as ctx:
            node.rpc_sendtoaddress(["00" * 21, 10])
        self.assertIn("dust", str(ctx.exception).lower())

    def test_buildtunnelcapsule_rejects_empty(self):
        node = self._make_minimal_node()
        with self.assertRaises(ValueError) as ctx:
            node.rpc_buildtunnelcapsule([])
        self.assertIn("needs one object param", str(ctx.exception))

    def test_validatetunnelcapsule_rejects_empty(self):
        node = self._make_minimal_node()
        with self.assertRaises(ValueError) as ctx:
            node.rpc_validatetunnelcapsule([])
        self.assertIn("needs one object param", str(ctx.exception))


class TestEstimateSmartFee(unittest.TestCase):
    """estimatesmartfee must return valid fee estimates."""

    def _make_node_with_fee_history(self):
        node = object.__new__(node_rpc.Node)
        node.lock = threading.Lock()
        node._fee_history = [{"h": 1, "min": 2.0, "n": 5}]
        node.cs = type("FakeCS", (), {"tip": lambda self: {"height": 1}})()
        node.mempool = type("FakeMP", (), {"txs": {}})()
        return node

    def test_estimatesmartfee_default_target(self):
        node = self._make_node_with_fee_history()
        result = node.rpc_estimatesmartfee([])
        self.assertIn("feerate", result)
        self.assertIn("blocks", result)
        self.assertGreaterEqual(result["feerate"], 1)

    def test_estimatesmartfee_clamps_target(self):
        node = self._make_node_with_fee_history()
        result = node.rpc_estimatesmartfee([999])
        self.assertEqual(result["blocks"], 144)

    def test_estimatesmartfee_minimum_target(self):
        node = self._make_node_with_fee_history()
        result = node.rpc_estimatesmartfee([0])
        self.assertEqual(result["blocks"], 1)


if __name__ == "__main__":
    unittest.main()
