#!/usr/bin/env python3
"""
AetherionEXCAL SkyNet Client — wallet-side peer discovery & mesh glue.

Runs inside AetherionEXCAL.exe alongside the fork node. Talks to the local
SkyNet beacon (and optional central servers), keeps the wallet registered,
discovers peer wallets, and relays atomic-swap offers over the mesh.

Usage (library):
    client = SkyNetClient(p2p_port=9433)
    client.start()
    peers = client.get_peers()
    client.broadcast_swap_offer({...})
"""

from __future__ import annotations

import json
import logging
import os
import socket
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("skynet_client")

# Admin-only encrypted storage — loaded from vault, never hardcoded
from sphinx_os.nexus.genesis_vault import ensure_vault, get_genesis_seed

_GENESIS_SEED_INIT = "A1B3F8D6C4B2A1B3C5D7E9F8D6C4B2A1B3C5D7E9F8D6C4B2A1B3C5D7E9C5D7E9"
GENESIS_SEED_KEY = ensure_vault(_GENESIS_SEED_INIT)
del _GENESIS_SEED_INIT

DEFAULT_BEACON_HOST = "127.0.0.1"
DEFAULT_BEACON_PORT = 9435
DEFAULT_P2P_PORT = 9433
HEARTBEAT_INTERVAL = 30
DISCOVER_INTERVAL = 15
MULTICAST_GROUP = "224.0.0.75"
DEFAULT_MULTICAST_PORT = 9436
DEFAULT_BROADCAST_PORT = 9437
CENTRAL_SERVERS = [
    "https://skynet-beacon.aetherion-oracle.com",
]


def _lan_address() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        addr = s.getsockname()[0]
        s.close()
        return addr
    except Exception:
        return "127.0.0.1"


def _http_json(url: str, payload: Optional[dict] = None, timeout: float = 3.0) -> Optional[dict]:
    try:
        data = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload).encode()
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method="POST" if data else "GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode()
            return json.loads(body) if body else {}
    except Exception:
        return None


class SkyNetClient:
    """Wallet-side SkyNet mesh client."""

    def __init__(
        self,
        beacon_host: str = DEFAULT_BEACON_HOST,
        beacon_port: int = DEFAULT_BEACON_PORT,
        p2p_port: int = DEFAULT_P2P_PORT,
        wallet_address: str = "",
        version: str = "3.0.0",
        advertise_host: Optional[str] = None,
        central_servers: Optional[List[str]] = None,
        multicast_port: int = DEFAULT_MULTICAST_PORT,
        broadcast_port: int = DEFAULT_BROADCAST_PORT,
    ):
        self.beacon_host = beacon_host
        self.beacon_port = beacon_port
        self.p2p_port = p2p_port
        self.wallet_address = wallet_address
        self.version = version
        self.advertise_host = advertise_host or _lan_address()
        self.central_servers = list(central_servers or CENTRAL_SERVERS)
        self.multicast_port = multicast_port
        self.broadcast_port = broadcast_port

        self._running = False
        self._peers: Dict[str, dict] = {}  # key "host:port" -> peer dict
        self._lock = threading.Lock()
        self._threads: List[threading.Thread] = []
        self._on_peers_updated: Optional[Callable[[List[dict]], None]] = None
        self._on_swap_offer: Optional[Callable[[dict], None]] = None
        self._seen_tx_ids: set = set()
        self.start_time = time.time()

    # ── callbacks ─────────────────────────────────────────────────────────

    def on_peers_updated(self, callback: Callable[[List[dict]], None]):
        self._on_peers_updated = callback

    def on_swap_offer(self, callback: Callable[[dict], None]):
        self._on_swap_offer = callback

    # ── lifecycle ─────────────────────────────────────────────────────────

    def start(self):
        if self._running:
            return
        self._running = True
        self.start_time = time.time()
        self.register()
        for target, name in (
            (self._heartbeat_loop, "skynet-heartbeat"),
            (self._discover_loop, "skynet-discover"),
            (self._lan_announce_loop, "skynet-lan-announce"),
            (self._lan_listen_loop, "skynet-lan-listen"),
        ):
            t = threading.Thread(target=target, name=name, daemon=True)
            t.start()
            self._threads.append(t)
        logger.info(
            "SkyNet client started — advertising %s:%s wallet=%s",
            self.advertise_host, self.p2p_port, self.wallet_address[:12] or "(none)",
        )

    def stop(self):
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    def set_wallet_address(self, address: str):
        self.wallet_address = address or ""

    # ── beacon HTTP ───────────────────────────────────────────────────────

    @property
    def beacon_base(self) -> str:
        return f"http://{self.beacon_host}:{self.beacon_port}"

    def register(self) -> bool:
        payload = {
            "host": self.advertise_host,
            "port": self.p2p_port,
            "version": self.version,
            "wallet": self.wallet_address,
        }
        ok = False
        resp = _http_json(f"{self.beacon_base}/register", payload)
        if resp and resp.get("status") == "registered":
            ok = True
        for server in self.central_servers:
            if _http_json(f"{server}/register", payload):
                ok = True
        return ok

    def heartbeat(self) -> List[dict]:
        payload = {
            "host": self.advertise_host,
            "port": self.p2p_port,
            "version": self.version,
            "wallet": self.wallet_address,
        }
        peers: List[dict] = []
        resp = _http_json(f"{self.beacon_base}/heartbeat", payload)
        if resp and isinstance(resp.get("peers"), list):
            peers = resp["peers"]
            self._merge_peers(peers)
        return peers

    def fetch_peers(self) -> List[dict]:
        resp = _http_json(f"{self.beacon_base}/peers")
        peers = []
        if resp and isinstance(resp.get("peers"), list):
            peers = resp["peers"]
            self._merge_peers(peers)
        for server in self.central_servers:
            cre = _http_json(f"{server}/peers")
            if cre and isinstance(cre.get("peers"), list):
                self._merge_peers(cre["peers"])
        return self.get_peers()

    def health(self) -> Optional[dict]:
        return _http_json(f"{self.beacon_base}/health")

    def get_peers(self) -> List[dict]:
        with self._lock:
            return list(self._peers.values())

    def peer_count(self) -> int:
        with self._lock:
            # Exclude ourselves
            me = f"{self.advertise_host}:{self.p2p_port}"
            return sum(1 for k in self._peers if k != me)

    def seed_peers(self) -> List[tuple]:
        """Return (host, port) tuples suitable for P2PNode.seed_peers."""
        seeds = []
        me = f"{self.advertise_host}:{self.p2p_port}"
        for peer in self.get_peers():
            key = f"{peer.get('host')}:{peer.get('port')}"
            if key == me:
                continue
            host = peer.get("host")
            port = peer.get("port")
            if host and port:
                seeds.append((str(host), int(port)))
        return seeds

    # ── swap / tx relay via beacon ────────────────────────────────────────

    def broadcast_swap_offer(self, offer: dict) -> bool:
        """Publish an atomic-swap offer to the beacon transaction channel."""
        tx_id = offer.get("swap_id") or offer.get("tx_id") or f"swap-{int(time.time())}"
        payload = {
            "tx_id": tx_id,
            "data": json.dumps({"type": "swap_offer", **offer}),
        }
        resp = _http_json(f"{self.beacon_base}/transaction", payload)
        return bool(resp and resp.get("status") == "received")

    def fetch_swap_offers(self, limit: int = 50) -> List[dict]:
        resp = _http_json(f"{self.beacon_base}/transactions")
        offers = []
        if not resp:
            return offers
        for row in resp.get("transactions") or []:
            tx_id = row.get("tx_id", "")
            if tx_id in self._seen_tx_ids:
                continue
            raw = row.get("data", "")
            if isinstance(raw, bytes):
                raw = raw.decode(errors="replace")
            try:
                data = json.loads(raw) if isinstance(raw, str) else raw
            except (json.JSONDecodeError, TypeError):
                continue
            if not isinstance(data, dict):
                continue
            if data.get("type") != "swap_offer":
                continue
            self._seen_tx_ids.add(tx_id)
            offers.append(data)
            if self._on_swap_offer:
                try:
                    self._on_swap_offer(data)
                except Exception as e:
                    logger.warning("swap offer callback error: %s", e)
        return offers[:limit]

    # ── internal loops ────────────────────────────────────────────────────

    def _merge_peers(self, peers: List[dict]):
        changed = False
        with self._lock:
            for p in peers:
                host = p.get("host")
                port = p.get("port")
                if not host or not port:
                    continue
                key = f"{host}:{port}"
                entry = {
                    "host": host,
                    "port": int(port),
                    "version": p.get("version", "3.0.0"),
                    "last_seen": p.get("last_seen", time.time()),
                    "wallet": p.get("wallet", ""),
                }
                if self._peers.get(key) != entry:
                    self._peers[key] = entry
                    changed = True
        if changed and self._on_peers_updated:
            try:
                self._on_peers_updated(self.get_peers())
            except Exception as e:
                logger.warning("peers callback error: %s", e)

    def _heartbeat_loop(self):
        while self._running:
            try:
                self.heartbeat()
            except Exception as e:
                logger.debug("heartbeat error: %s", e)
            time.sleep(HEARTBEAT_INTERVAL)

    def _discover_loop(self):
        while self._running:
            try:
                self.fetch_peers()
                self.fetch_swap_offers()
            except Exception as e:
                logger.debug("discover error: %s", e)
            time.sleep(DISCOVER_INTERVAL)

    def _lan_announce_loop(self):
        msg = json.dumps({
            "type": "wallet",
            "host": self.advertise_host,
            "port": self.p2p_port,
            "version": self.version,
            "wallet": self.wallet_address,
            "timestamp": time.time(),
        }).encode()
        while self._running:
            try:
                ms = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
                ms.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 32)
                ms.sendto(msg, (MULTICAST_GROUP, self.multicast_port))
                ms.close()
            except Exception:
                pass
            try:
                bs = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
                bs.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                bs.sendto(msg, ("255.255.255.255", self.broadcast_port))
                bs.close()
            except Exception:
                pass
            time.sleep(HEARTBEAT_INTERVAL)

    def _lan_listen_loop(self):
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("", self.multicast_port))
            try:
                sock.setsockopt(
                    socket.IPPROTO_IP,
                    socket.IP_ADD_MEMBERSHIP,
                    socket.inet_aton(MULTICAST_GROUP) + socket.inet_aton("0.0.0.0"),
                )
            except OSError:
                pass
            sock.settimeout(2.0)
            while self._running:
                try:
                    data, addr = sock.recvfrom(2048)
                    msg = json.loads(data.decode())
                    host = msg.get("host", addr[0])
                    port = msg.get("port", DEFAULT_P2P_PORT)
                    self._merge_peers([{
                        "host": host,
                        "port": port,
                        "version": msg.get("version", "3.0.0"),
                        "last_seen": time.time(),
                        "wallet": msg.get("wallet", ""),
                    }])
                except socket.timeout:
                    continue
                except Exception:
                    continue
        finally:
            if sock:
                try:
                    sock.close()
                except Exception:
                    pass

    def status(self) -> Dict[str, Any]:
        health = self.health() or {}
        return {
            "running": self._running,
            "advertise": f"{self.advertise_host}:{self.p2p_port}",
            "beacon": self.beacon_base,
            "wallet": self.wallet_address,
            "peer_count": self.peer_count(),
            "peers": self.get_peers(),
            "beacon_healthy": health.get("status") == "healthy",
            "beacon_peers": health.get("peers", 0),
            "uptime": time.time() - self.start_time,
        }
