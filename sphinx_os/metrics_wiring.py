"""Metrics wiring module for Excalibur Chain.

Connects all components to Prometheus metrics:
- Fork node: chain height, blocks, mempool, RPC
- P2P layer: peers, bandwidth, inventory
- SkyNet Beacon: peer registration, heartbeats
- Wallet: balance, keys, profiles
- Mining: hashrate, nonces, blocks mined

Usage:
    from sphinx_os.metrics_wiring import MetricsWiring

    # Initialize once at startup
    wiring = MetricsWiring()
    wiring.initialize()

    # Wire into fork node
    wiring.wire_fork_node(fork_node_instance)

    # Wire into P2P layer
    wiring.wire_p2p_layer(p2p_instance)

    # Wire into beacon
    wiring.wire_beacon(beacon_instance)

    # Periodic updates (call from main loop)
    wiring.update_all()
"""

import time
import threading
import logging
from typing import Optional, Any, Callable

logger = logging.getLogger("metrics_wiring")


class MetricsWiring:
    """Wires all Excalibur components to Prometheus metrics."""

    def __init__(self):
        self._metrics = None
        self._callbacks = {}
        self._update_thread = None
        self._stop_event = threading.Event()
        self._last_block_time = None
        self._last_block_height = None
        self._hash_start_time = time.time()
        self._hash_count = 0

    def initialize(self):
        """Initialize metrics and start the update thread."""
        from sphinx_os.prometheus_metrics import get_metrics, start_http_server

        self._metrics = get_metrics()

        # Set node info
        try:
            from genesis_fork import SWORD
            self._metrics.node_info.labels(
                version="2.0.0",
                network="excalibur-fork",
                sword=str(SWORD)
            ).info({"status": "running"})
        except Exception as e:
            logger.debug(f"Could not set node info: {e}")

        # Start HTTP server on port 9438
        try:
            start_http_server(9438)
        except Exception as e:
            logger.debug(f"Could not start metrics server: {e}")

        # Start background update thread
        self._update_thread = threading.Thread(
            target=self._update_loop, daemon=True, name="metrics-updater"
        )
        self._update_thread.start()

        logger.info("Metrics wiring initialized")

    def wire_fork_node(self, fork_node: Any):
        """Wire fork node metrics callbacks.

        Args:
            fork_node: Instance of ForkNode or similar
        """
        self._callbacks['fork_node'] = fork_node

        # Register block mined callback
        if hasattr(fork_node, 'on_block_mined'):
            fork_node.on_block_mined = self._on_block_mined

        # Register transaction received callback
        if hasattr(fork_node, 'on_transaction'):
            fork_node.on_transaction = self._on_transaction

        logger.info("Fork node metrics wired")

    def wire_p2p_layer(self, p2p_layer: Any):
        """Wire P2P layer metrics callbacks.

        Args:
            p2p_layer: Instance of P2P layer
        """
        self._callbacks['p2p'] = p2p_layer

        # Register peer connected callback
        if hasattr(p2p_layer, 'on_peer_connected'):
            p2p_layer.on_peer_connected = self._on_peer_connected

        # Register peer disconnected callback
        if hasattr(p2p_layer, 'on_peer_disconnected'):
            p2p_layer.on_peer_disconnected = self._on_peer_disconnected

        logger.info("P2P layer metrics wired")

    def wire_beacon(self, beacon: Any):
        """Wire SkyNet Beacon metrics callbacks.

        Args:
            beacon: Instance of SkyNet Beacon
        """
        self._callbacks['beacon'] = beacon

        # Register heartbeat callback
        if hasattr(beacon, 'on_heartbeat'):
            beacon.on_heartbeat = self._on_heartbeat

        logger.info("Beacon metrics wired")

    def wire_wallet(self, wallet: Any):
        """Wire wallet metrics callbacks.

        Args:
            wallet: Instance of wallet
        """
        self._callbacks['wallet'] = wallet

        logger.info("Wallet metrics wired")

    def _on_block_mined(self, block: Any):
        """Callback when a block is mined."""
        if not self._metrics:
            return

        self._metrics.blocks_mined.inc()

        if hasattr(block, 'height'):
            self._metrics.block_height.set(block.height)

        if hasattr(block, 'size'):
            self._metrics.block_size.observe(block.size)

        if hasattr(block, 'txs'):
            self._metrics.block_transactions.observe(len(block.txs))

        # Track block time
        now = time.time()
        if self._last_block_time is not None:
            block_time = now - self._last_block_time
            self._metrics.block_time.observe(block_time)
        self._last_block_time = now

        if hasattr(block, 'height'):
            self._last_block_height = block.height

        logger.debug(f"Block mined: height={getattr(block, 'height', '?')}")

    def _on_transaction(self, tx: Any):
        """Callback when a transaction is received."""
        if not self._metrics:
            return

        self._metrics.transactions_total.labels(
            type=getattr(tx, 'type', 'unknown'),
            status='received'
        ).inc()

        if hasattr(tx, 'amount'):
            self._metrics.transaction_amount.observe(tx.amount)

        # Track lock type
        if hasattr(tx, 'lock_type'):
            self._metrics.lock_types_total.labels(
                lock_type=tx.lock_type
            ).inc()

    def _on_peer_connected(self, peer: Any):
        """Callback when a peer connects."""
        if not self._metrics:
            return

        self._metrics.peers_total.inc()
        logger.debug(f"Peer connected: {getattr(peer, 'address', '?')}")

    def _on_peer_disconnected(self, peer: Any):
        """Callback when a peer disconnects."""
        if not self._metrics:
            return

        self._metrics.peers_disconnected.inc()
        logger.debug(f"Peer disconnected: {getattr(peer, 'address', '?')}")

    def _on_heartbeat(self, peer_id: str):
        """Callback when a heartbeat is received."""
        if not self._metrics:
            return

        self._metrics.beacon_heartbeats.inc()

    def record_rpc_request(self, method: str, latency: float, success: bool = True):
        """Record an RPC request.

        Args:
            method: RPC method name
            latency: Request latency in seconds
            success: Whether the request succeeded
        """
        if not self._metrics:
            return

        status = 'success' if success else 'error'
        self._metrics.rpc_requests_total.labels(method=method, status=status).inc()
        self._metrics.rpc_latency.observe(latency)

    def record_mining_hash(self):
        """Record a mining hash computation."""
        if not self._metrics:
            return

        self._hash_count += 1

    def update_mining_hashrate(self):
        """Update the mining hashrate gauge."""
        if not self._metrics:
            return

        elapsed = time.time() - self._hash_start_time
        if elapsed > 0:
            hashrate = self._hash_count / elapsed
            self._metrics.mining_hashrate.set(hashrate)
            self._metrics.mining_hashes_total.inc(self._hash_count)
            self._hash_count = 0
            self._hash_start_time = time.time()

    def update_chain_metrics(self, height: int, difficulty: float, mempool_size: int):
        """Update chain metrics.

        Args:
            height: Current chain height
            difficulty: Current mining difficulty
            mempool_size: Number of transactions in mempool
        """
        if not self._metrics:
            return

        self._metrics.chain_height.set(height)
        self._metrics.chain_difficulty.set(difficulty)
        self._metrics.mempool_size.set(mempool_size)

    def update_peer_count(self, count: int):
        """Update the peer count gauge.

        Args:
            count: Number of connected peers
        """
        if not self._metrics:
            return

        self._metrics.peers_connected.set(count)

    def update_wallet_metrics(self, balance: float, keys: int, profiles: int):
        """Update wallet metrics.

        Args:
            balance: Current wallet balance
            keys: Number of keys
            profiles: Number of profiles
        """
        if not self._metrics:
            return

        self._metrics.wallet_balance.set(balance)
        self._metrics.wallet_keys.set(keys)
        self._metrics.wallet_profiles.set(profiles)

    def update_beacon_metrics(self, peers: int):
        """Update beacon metrics.

        Args:
            peers: Number of registered peers
        """
        if not self._metrics:
            return

        self._metrics.beacon_peers.set(peers)

    def update_all(self):
        """Update all metrics from connected components."""
        if not self._metrics:
            return

        # Update uptime
        self._metrics.update_uptime()

        # Update mining hashrate
        self.update_mining_hashrate()

        # Update fork node metrics
        if 'fork_node' in self._callbacks:
            try:
                fn = self._callbacks['fork_node']
                if hasattr(fn, 'get_height'):
                    height = fn.get_height()
                    self._metrics.chain_height.set(height)
                if hasattr(fn, 'get_mempool_size'):
                    mempool = fn.get_mempool_size()
                    self._metrics.mempool_size.set(mempool)
            except Exception as e:
                logger.debug(f"Error updating fork node metrics: {e}")

        # Update P2P metrics
        if 'p2p' in self._callbacks:
            try:
                p2p = self._callbacks['p2p']
                if hasattr(p2p, 'get_peer_count'):
                    peers = p2p.get_peer_count()
                    self._metrics.peers_connected.set(peers)
            except Exception as e:
                logger.debug(f"Error updating P2P metrics: {e}")

        # Update beacon metrics
        if 'beacon' in self._callbacks:
            try:
                beacon = self._callbacks['beacon']
                if hasattr(beacon, 'get_peer_count'):
                    peers = beacon.get_peer_count()
                    self._metrics.beacon_peers.set(peers)
            except Exception as e:
                logger.debug(f"Error updating beacon metrics: {e}")

    def _update_loop(self):
        """Background update loop."""
        while not self._stop_event.is_set():
            try:
                self.update_all()
            except Exception as e:
                logger.debug(f"Error in metrics update loop: {e}")

            # Sleep for 5 seconds
            self._stop_event.wait(5)

    def stop(self):
        """Stop the metrics update thread."""
        self._stop_event.set()
        if self._update_thread:
            self._update_thread.join(timeout=5)
        logger.info("Metrics wiring stopped")


# Global singleton
_wiring: Optional[MetricsWiring] = None
_lock = threading.Lock()


def get_wiring() -> MetricsWiring:
    """Get the global metrics wiring singleton."""
    global _wiring
    if _wiring is None:
        with _lock:
            if _wiring is None:
                _wiring = MetricsWiring()
                _wiring.initialize()
    return _wiring


def initialize_metrics():
    """Initialize metrics wiring (convenience function)."""
    return get_wiring()
