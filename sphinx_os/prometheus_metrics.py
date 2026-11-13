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
    except OSError as e:
        print(f"[Prometheus] Failed to start metrics server on port {port}: {e}")
        return None


def stop_http_server():
    """Stop the Prometheus HTTP metrics server (no-op for prometheus_client)."""
    pass
