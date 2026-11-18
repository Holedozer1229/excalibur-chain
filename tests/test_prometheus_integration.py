import threading
import unittest

from fork_node import _update_prometheus_metrics
from sphinx_os.prometheus_metrics import PROMETHEUS_AVAILABLE, PrometheusMetrics


class FakeMetric:
    def __init__(self):
        self.value = 0

    def set(self, value):
        self.value = value

    def inc(self, value=1):
        self.value += value


class FakeMetrics:
    def __init__(self):
        self.chain_height = FakeMetric()
        self.chain_total_work = FakeMetric()
        self.mempool_size = FakeMetric()
        self.mempool_bytes = FakeMetric()
        self.chain_difficulty = FakeMetric()
        self.peers_connected = FakeMetric()
        self.p2p_erepr_peers = FakeMetric()
        self.p2p_erepr_v2_peers = FakeMetric()
        self.p2p_known_addresses = FakeMetric()
        self.p2p_gossip_sent = FakeMetric()
        self.p2p_gossip_received = FakeMetric()
        self.p2p_peer_latency = FakeMetric()
        self.blocks_seen = FakeMetric()
        self.uptime_updates = 0

    def update_uptime(self):
        self.uptime_updates += 1


class FakeStore:
    def __init__(self):
        self.lock = threading.Lock()
        self.tip_height = 9
        self.by_height = {
            9: {"bits": 0x1D00FFFF},
        }
        self.mempool = {"tx1": b"transaction"}
        self.metrics = {"total_difficulty": 1234}


class FakeP2P:
    mempool = {"tx2": b"peer transaction"}

    def get_network_health(self):
        return {
            "peer_count": 3,
            "erepr_peers": 2,
            "erepr_v2_peers": 1,
            "known_peer_addresses": 8,
            "erepr_gossip_sent": 11,
            "erepr_gossip_received": 12,
            "avg_latency_ms": 250,
        }


class PrometheusNodeIntegrationTests(unittest.TestCase):
    def test_metrics_reflect_chain_mempool_and_p2p_state(self):
        metrics = FakeMetrics()
        store = FakeStore()

        height = _update_prometheus_metrics(metrics, store, FakeP2P(), 8)

        self.assertEqual(height, 9)
        self.assertEqual(metrics.chain_height.value, 9)
        self.assertEqual(metrics.chain_total_work.value, 1234)
        self.assertEqual(metrics.mempool_size.value, 2)
        self.assertEqual(
            metrics.mempool_bytes.value,
            len(b"transaction") + len(b"peer transaction"),
        )
        self.assertEqual(metrics.peers_connected.value, 3)
        self.assertEqual(metrics.p2p_erepr_peers.value, 2)
        self.assertEqual(metrics.p2p_erepr_v2_peers.value, 1)
        self.assertEqual(metrics.p2p_known_addresses.value, 8)
        self.assertEqual(metrics.p2p_gossip_sent.value, 11)
        self.assertEqual(metrics.p2p_gossip_received.value, 12)
        self.assertEqual(metrics.p2p_peer_latency.value, 0.25)
        self.assertEqual(metrics.blocks_seen.value, 1)
        self.assertEqual(metrics.uptime_updates, 1)

    def test_metrics_do_not_count_existing_chain_as_new_blocks(self):
        metrics = FakeMetrics()

        _update_prometheus_metrics(metrics, FakeStore(), FakeP2P(), 9)

        self.assertEqual(metrics.blocks_seen.value, 0)

    @unittest.skipUnless(PROMETHEUS_AVAILABLE, "prometheus-client is not installed")
    def test_prometheus_registry_exports_p2p_and_chain_metrics(self):
        metrics = PrometheusMetrics()
        metrics.initialize()
        metrics.chain_height.set(123)
        metrics.peers_connected.set(4)
        metrics.p2p_erepr_peers.set(3)

        output = metrics.get_latest()

        self.assertIn("excalibur_chain_height 123.0", output)
        self.assertIn("excalibur_peers_connected 4.0", output)
        self.assertIn("excalibur_p2p_erepr_peers 3.0", output)


if __name__ == "__main__":
    unittest.main()
