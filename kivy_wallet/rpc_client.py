"""rpc_client.py — JSON-RPC client for the Excalibur node.

Wraps the 16 RPC methods exposed by node_rpc.py into a clean async API.
Used by both the Kivy wallet and the React Native wrapper.

Default endpoint: http://127.0.0.1:9432
"""
import json
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional


class RpcError(Exception):
    """Raised when the node returns an error."""
    pass


class RpcClient:
    """Synchronous JSON-RPC client for the Excalibur node.

    Usage:
        client = RpcClient("http://127.0.0.1:9432")
        height = client.getblockcount()
        balance = client.getbalance([])
    """

    def __init__(self, url: str = "http://127.0.0.1:9432"):
        self.url = url.rstrip("/")

    def _call(self, method: str, params: list = None) -> Any:
        """Send a JSON-RPC request and return the result."""
        if params is None:
            params = []
        payload = json.dumps({
            "method": method,
            "params": params,
            "id": 1
        }).encode("utf-8")

        req = urllib.request.Request(
            self.url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as e:
            raise RpcError(f"Cannot connect to node at {self.url}: {e}")
        except Exception as e:
            raise RpcError(f"RPC error: {e}")

        if result.get("error"):
            raise RpcError(result["error"])
        return result.get("result")

    # ── Chain queries ──────────────────────────────────────────────

    def getblockcount(self) -> int:
        """Return the current chain height."""
        return self._call("getblockcount")

    def getbestblockhash(self) -> str:
        """Return the hash of the current best block."""
        return self._call("getbestblockhash")

    def getchaintips(self) -> List[Dict]:
        """Return all chain tips."""
        return self._call("getchaintips")

    def getblock(self, block_hash: str) -> Dict:
        """Return block details by hash."""
        return self._call("getblock", [block_hash])

    # ── Mempool ────────────────────────────────────────────────────

    def getrawmempool(self) -> List[str]:
        """Return transaction IDs in the mempool."""
        return self._call("getrawmempool")

    def getmempoolinfo(self) -> Dict:
        """Return mempool size and byte count."""
        return self._call("getmempoolinfo")

    # ── Transactions ───────────────────────────────────────────────

    def sendrawtransaction(self, tx_hex: str) -> str:
        """Broadcast a raw transaction. Returns the txid."""
        return self._call("sendrawtransaction", [tx_hex])

    def submitblock(self, block_hex: str) -> None:
        """Submit a mined block."""
        return self._call("submitblock", [block_hex])

    # ── Wallet ─────────────────────────────────────────────────────

    def getnewaddress(self) -> str:
        """Generate a new receive address."""
        return self._call("getnewaddress")

    def getpkhaddress(self) -> str:
        """Return the current PKH address."""
        return self._call("getpkhaddress")

    def getbalance(self, minconf: int = 1) -> int:
        """Return balance in swords."""
        return self._call("getbalance", [minconf])

    def getutxos(self, address: Optional[str] = None) -> List[Dict]:
        """Return UTXO list, optionally filtered by address."""
        params = [address] if address else []
        return self._call("getutxos", params)

    def sendtoaddress(self, address: str, amount: int,
                      fee_rate: Optional[int] = None) -> str:
        """Send swords to an address. Returns the txid."""
        params = [address, amount]
        if fee_rate is not None:
            params.append(fee_rate)
        return self._call("sendtoaddress", params)

    # ── Network ────────────────────────────────────────────────────

    def getpeerinfo(self) -> List[Dict]:
        """Return connected peer information."""
        return self._call("getpeerinfo")

    # ── Fee estimation ─────────────────────────────────────────────

    def estimatesmartfee(self, conf_target: int = 6) -> Dict:
        """Estimate fee rate for a confirmation target."""
        return self._call("estimatesmartfee", [conf_target])

    # ── Tunnel capsule (cross-chain) ───────────────────────────────

    def buildtunnelcapsule(self, params: Dict) -> Dict:
        """Build a tunnel capsule for cross-chain operations."""
        return self._call("buildtunnelcapsule", [params])

    def validatetunnelcapsule(self, capsule: str) -> bool:
        """Validate a tunnel capsule."""
        return self._call("validatetunnelcapsule", [capsule])

    # ── Convenience ────────────────────────────────────────────────

    def get_status(self) -> Dict:
        """Return a combined status snapshot."""
        try:
            height = self.getblockcount()
        except RpcError:
            height = None
        try:
            best_hash = self.getbestblockhash()
        except RpcError:
            best_hash = None
        try:
            peers = self.getpeerinfo()
        except RpcError:
            peers = []
        try:
            mempool = self.getmempoolinfo()
        except RpcError:
            mempool = {}

        return {
            "height": height,
            "best_hash": best_hash,
            "peer_count": len(peers),
            "peers": peers,
            "mempool": mempool,
            "connected": height is not None,
        }

    def balance_to_excal(self, swords: int) -> float:
        """Convert swords to EXCAL."""
        return swords / 100_000_000

    def excal_to_swords(self, excal: float) -> int:
        """Convert EXCAL to swords."""
        return int(excal * 100_000_000)
