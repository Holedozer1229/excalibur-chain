"""Prometheus metrics for the Excalibur Chain P2P ledger.

Provides real-time observability for:
- Peer connections and network health
- Transaction throughput and latency
- Gossip protocol propagation
- Wallet operations and balances
- Node uptime and resource usage

Usage:
    from sphinx_os.prometheus_metrics import get_metrics, start_http_server

    # Access metrics anywhere
    metrics = get_metrics()
    metrics.peers_connected.set(5)
    metrics.transactions_total.inc()

    # Start HTTP server on port 9435 (default)
    start_http_server(9435)
"""

import time
import threading
from typing import Optional

try:
    from prometheus_client import (
        Counter,
        Gauge,
        Histogram,
        Info,
        CollectorRegistry,
        generate_latest,
        CONTENT_TYPE_LATEST,
        start_http_server as _start_http_server,
    )
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    # Fallback stubs when prometheus_client is not installed
    Counter = None
    Gauge = None
    Histogram = None
    Info = None


class PrometheusMetrics:
    """Centralized Prometheus metrics for the Excalibur Chain."""

    def __init__(self):
        self._registry = None
        self._initialized = False
        self._start_time = time.time()

    def initialize(self):
        """Initialize all metrics. Safe to call multiple times."""
        if self._initialized:
            return
        if not PROMETHEUS_AVAILABLE:
            self._create_stubs()
            self._initialized = True
            return

        from prometheus_client import CollectorRegistry
        self._registry = CollectorRegistry()

        # --- Node Info ---
        self.node_info = Info(
            'excalibur_node',
            'Excalibur Chain node information',
            labelnames=['version', 'network', 'sword'],
            registry=self._registry,
        )

        # --- Uptime ---
        self.uptime_seconds = Gauge(
            'excalibur_uptime_seconds',
            'Node uptime in seconds',
            registry=self._registry,
        )

        # --- Peer Metrics ---
        self.peers_connected = Gauge(
            'excalibur_peers_connected',
            'Number of connected P2P peers',
            registry=self._registry,
        )

        self.peers_total = Counter(
            'excalibur_peers_total',
            'Total peers ever connected',
            registry=self._registry,
        )

        self.peers_disconnected = Counter(
            'excalibur_peers_disconnected_total',
            'Total peer disconnections',
            registry=self._registry,
        )

        self.network_coherence = Gauge(
            'excalibur_network_coherence',
            'P2P network coherence score (0-1)',
            registry=self._registry,
        )
        self.p2p_erepr_peers = Gauge(
            'excalibur_p2p_erepr_peers',
            'Connected P2P peers advertising EREPR support',
            registry=self._registry,
        )
        self.p2p_erepr_v2_peers = Gauge(
            'excalibur_p2p_erepr_v2_peers',
            'Connected P2P peers advertising EREPR v2 support',
            registry=self._registry,
        )
        self.p2p_known_addresses = Gauge(
            'excalibur_p2p_known_addresses',
            'Known peer addresses available for P2P discovery',
            registry=self._registry,
        )
        self.p2p_gossip_sent = Gauge(
            'excalibur_p2p_gossip_sent',
            'EREPR gossip messages sent since this node started',
            registry=self._registry,
        )
        self.p2p_gossip_received = Gauge(
            'excalibur_p2p_gossip_received',
            'EREPR gossip messages received since this node started',
            registry=self._registry,
        )
        self.p2p_peer_latency = Gauge(
            'excalibur_p2p_peer_latency_seconds',
            'Average latency of connected P2P peers',
            registry=self._registry,
        )

        # --- Transaction Metrics ---
        self.transactions_total = Counter(
            'excalibur_transactions_total',
            'Total transactions processed',
            labelnames=['type', 'status'],
            registry=self._registry,
        )

        self.transaction_amount = Histogram(
            'excalibur_transaction_amount_skynt',
            'Transaction amounts in SKYNT',
            buckets=[0.1, 1, 10, 100, 1000, 10000, 100000],
            registry=self._registry,
        )

        self.transaction_latency = Histogram(
            'excalibur_transaction_latency_seconds',
            'Transaction processing latency',
            buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 10.0],
            registry=self._registry,
        )

        # --- Gossip Protocol Metrics ---
        self.gossip_messages_sent = Counter(
            'excalibur_gossip_messages_sent_total',
            'Total gossip messages sent',
            registry=self._registry,
        )

        self.gossip_messages_received = Counter(
            'excalibur_gossip_messages_received_total',
            'Total gossip messages received',
            registry=self._registry,
        )

        self.gossip_propagation_time = Histogram(
            'excalibur_gossip_propagation_seconds',
            'Gossip message propagation time',
            buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 5.0],
            registry=self._registry,
        )

        # --- Message Metrics ---
        self.messages_sent = Counter(
            'excalibur_messages_sent_total',
            'Total P2P messages sent',
            labelnames=['type', 'priority'],
            registry=self._registry,
        )

        self.messages_received = Counter(
            'excalibur_messages_received_total',
            'Total P2P messages received',
            labelnames=['type'],
            registry=self._registry,
        )

        self.messages_encrypted = Counter(
            'excalibur_messages_encrypted_total',
            'Total encrypted messages sent',
            registry=self._registry,
        )

        # --- Wallet Metrics ---
        self.wallet_balance = Gauge(
            'excalibur_wallet_balance_skynt',
            'Current wallet balance in SKYNT',
            registry=self._registry,
        )

        self.wallet_keys = Gauge(
            'excalibur_wallet_keys',
            'Number of keys in the wallet',
            registry=self._registry,
        )

        self.wallet_profiles = Gauge(
            'excalibur_wallet_profiles',
            'Number of wallet profiles',
            registry=self._registry,
        )

        # --- Bandwidth Metrics ---
        self.bytes_sent = Counter(
            'excalibur_bytes_sent_total',
            'Total bytes sent over P2P',
            registry=self._registry,
        )

        self.bytes_received = Counter(
            'excalibur_bytes_received_total',
            'Total bytes received over P2P',
            registry=self._registry,
        )

        # --- Error Metrics ---
        self.errors_total = Counter(
            'excalibur_errors_total',
            'Total errors encountered',
            labelnames=['component', 'error_type'],
            registry=self._registry,
        )

        # --- Chain Metrics ---
        self.chain_height = Gauge(
            'excalibur_chain_height',
            'Current blockchain height (latest block number)',
            registry=self._registry,
        )

        self.chain_difficulty = Gauge(
            'excalibur_chain_difficulty',
            'Current mining difficulty',
            registry=self._registry,
        )

        self.chain_total_work = Gauge(
            'excalibur_chain_total_work',
            'Total cumulative work in the chain',
            registry=self._registry,
        )

        # --- Block Metrics ---
        self.blocks_mined = Counter(
            'excalibur_blocks_mined_total',
            'Total blocks mined by this node',
            registry=self._registry,
        )
        self.blocks_seen = Counter(
            'excalibur_blocks_seen_total',
            'Total blocks accepted by this node after startup',
            registry=self._registry,
        )

        self.block_height = Gauge(
            'excalibur_last_block_height',
            'Height of the last mined block',
            registry=self._registry,
        )

        self.block_size = Histogram(
            'excalibur_block_size_bytes',
            'Block sizes in bytes',
            buckets=[1000, 5000, 10000, 50000, 100000, 500000, 1000000],
            registry=self._registry,
        )

        self.block_transactions = Histogram(
            'excalibur_block_transactions',
            'Number of transactions per block',
            buckets=[1, 5, 10, 25, 50, 100, 250, 500],
            registry=self._registry,
        )

        self.block_time = Histogram(
            'excalibur_block_time_seconds',
            'Time between blocks',
            buckets=[10, 30, 60, 120, 300, 600],
            registry=self._registry,
        )

        # --- Mempool Metrics ---
        self.mempool_size = Gauge(
            'excalibur_mempool_size',
            'Number of transactions in the mempool',
            registry=self._registry,
        )

        self.mempool_bytes = Gauge(
            'excalibur_mempool_bytes',
            'Total size of mempool transactions in bytes',
            registry=self._registry,
        )

        self.mempool_fee_rate = Histogram(
            'excalibur_mempool_fee_rate',
            'Transaction fee rates in mempool (swords/byte)',
            buckets=[0.001, 0.01, 0.1, 1, 10, 100],
            registry=self._registry,
        )

        # --- Mining Metrics ---
        self.mining_hashrate = Gauge(
            'excalibur_mining_hashrate',
            'Current mining hashrate (hashes/second)',
            registry=self._registry,
        )

        self.mining_hashes_total = Counter(
            'excalibur_mining_hashes_total',
            'Total hashes computed by this node',
            registry=self._registry,
        )

        self.mining_active = Gauge(
            'excalibur_mining_active',
            'Whether mining is active (1) or inactive (0)',
            registry=self._registry,
        )

        self.mining_nonce = Gauge(
            'excalibur_mining_nonce',
            'Current mining nonce value',
            registry=self._registry,
        )

        # --- RPC Metrics ---
        self.rpc_requests_total = Counter(
            'excalibur_rpc_requests_total',
            'Total RPC requests',
            labelnames=['method', 'status'],
            registry=self._registry,
        )

        self.rpc_latency = Histogram(
            'excalibur_rpc_latency_seconds',
            'RPC request latency',
            buckets=[0.001, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0],
            registry=self._registry,
        )

        # --- P2P Metrics ---
        self.p2p_inventory_sent = Counter(
            'excalibur_p2p_inventory_sent_total',
            'Total inventory items sent',
            labelnames=['type'],
            registry=self._registry,
        )

        self.p2p_inventory_received = Counter(
            'excalibur_p2p_inventory_received_total',
            'Total inventory items received',
            labelnames=['type'],
            registry=self._registry,
        )

        self.p2p_bandwidth_sent = Counter(
            'excalibur_p2p_bandwidth_sent_bytes',
            'Total P2P bandwidth sent',
            registry=self._registry,
        )

        self.p2p_bandwidth_received = Counter(
            'excalibur_p2p_bandwidth_received_bytes',
            'Total P2P bandwidth received',
            registry=self._registry,
        )

        # --- SkyNet Beacon Metrics ---
        self.beacon_peers = Gauge(
            'excalibur_beacon_peers',
            'Number of peers registered with the beacon',
            registry=self._registry,
        )

        self.beacon_heartbeats = Counter(
            'excalibur_beacon_heartbeats_total',
            'Total heartbeats received',
            registry=self._registry,
        )

        # --- Lock Type Metrics ---
        self.lock_types_total = Counter(
            'excalibur_lock_types_total',
            'Transactions by lock type',
            labelnames=['lock_type'],
            registry=self._registry,
        )

        self._initialized = True

    def _create_stubs(self):
        """Create no-op stubs when prometheus_client is unavailable."""
        class _NoOp:
            def __getattr__(self, name):
                return self
            def __call__(self, *args, **kwargs):
                return self
            def labels(self, **kwargs):
                return self
        self.node_info = _NoOp()
        self.uptime_seconds = _NoOp()
        self.peers_connected = _NoOp()
        self.peers_total = _NoOp()
        self.peers_disconnected = _NoOp()
        self.network_coherence = _NoOp()
        self.p2p_erepr_peers = _NoOp()
        self.p2p_erepr_v2_peers = _NoOp()
        self.p2p_known_addresses = _NoOp()
        self.p2p_gossip_sent = _NoOp()
        self.p2p_gossip_received = _NoOp()
        self.p2p_peer_latency = _NoOp()
        self.transactions_total = _NoOp()
        self.transaction_amount = _NoOp()
        self.transaction_latency = _NoOp()
        self.gossip_messages_sent = _NoOp()
        self.gossip_messages_received = _NoOp()
        self.gossip_propagation_time = _NoOp()
        self.messages_sent = _NoOp()
        self.messages_received = _NoOp()
        self.messages_encrypted = _NoOp()
        self.wallet_balance = _NoOp()
        self.wallet_keys = _NoOp()
        self.wallet_profiles = _NoOp()
        self.bytes_sent = _NoOp()
        self.bytes_received = _NoOp()
        self.errors_total = _NoOp()
        self.chain_height = _NoOp()
        self.chain_difficulty = _NoOp()
        self.chain_total_work = _NoOp()
        self.blocks_mined = _NoOp()
        self.blocks_seen = _NoOp()
        self.block_height = _NoOp()
        self.block_size = _NoOp()
        self.block_transactions = _NoOp()
        self.block_time = _NoOp()
        self.mempool_size = _NoOp()
        self.mempool_bytes = _NoOp()
        self.mempool_fee_rate = _NoOp()
        self.mining_hashrate = _NoOp()
        self.mining_hashes_total = _NoOp()
        self.mining_active = _NoOp()
        self.mining_nonce = _NoOp()
        self.rpc_requests_total = _NoOp()
        self.rpc_latency = _NoOp()
        self.p2p_inventory_sent = _NoOp()
        self.p2p_inventory_received = _NoOp()
        self.p2p_bandwidth_sent = _NoOp()
        self.p2p_bandwidth_received = _NoOp()
        self.beacon_peers = _NoOp()
        self.beacon_heartbeats = _NoOp()
        self.lock_types_total = _NoOp()

    def update_uptime(self):
        """Update the uptime gauge."""
        if self._initialized:
            self.uptime_seconds.set(time.time() - self._start_time)

    def get_latest(self) -> str:
        """Return the latest metrics in Prometheus text format."""
        if not PROMETHEUS_AVAILABLE or not self._registry:
            return "# Prometheus client not available\n"
        from prometheus_client import generate_latest
        return generate_latest(self._registry).decode("utf-8")


# Global singleton
_metrics: Optional[PrometheusMetrics] = None
_lock = threading.Lock()


def get_metrics() -> PrometheusMetrics:
    """Get the global Prometheus metrics singleton."""
    global _metrics
    if _metrics is None:
        with _lock:
            if _metrics is None:
                _metrics = PrometheusMetrics()
                _metrics.initialize()
    return _metrics


def start_http_server(port: int = 9435, addr: str = "127.0.0.1") -> Optional[threading.Thread]:
    """Start the Prometheus HTTP metrics server.

    Args:
        port: Port to serve metrics on (default: 9435)
        addr: Address to bind to (default: 127.0.0.1)

    Returns:
        Thread object if started, None if prometheus_client is unavailable.
    """
    if not PROMETHEUS_AVAILABLE:
        print(f"[Prometheus] prometheus_client not installed; metrics server disabled. "
              f"Install with: pip install prometheus-client")
        return None

    metrics = get_metrics()
    if metrics._registry is None:
        return None

    try:
        _start_http_server(port, addr, registry=metrics._registry)
        print(f"[Prometheus] Metrics server started on http://{addr}:{port}/metrics")
        return None  # Runs in its own thread internally
    except OSError:
        raise


def stop_http_server():
    """Stop the Prometheus HTTP metrics server (no-op for prometheus_client)."""
    pass
