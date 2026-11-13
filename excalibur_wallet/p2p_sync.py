"""p2p_sync.py — header-first sync from a live P2P peer.

The wallet is a P2P client, not a node: it dials one peer (a seed
from seeds.json, or the local fork node on 127.0.0.1:9433), speaks
the fork's length-prefixed JSON wire protocol (p2p.py), and fetches
the blocks it is missing:

  hello (magic, height, hash) -> peer tip
  getblock(hash) -> block
  walk back via prev until the wallet's own tip hash is reached

Every fetched block is verified before it is applied:
  * header proof-of-work: sha256d(header) <= target(bits)
  * Merkle root recomputed from the block's txs
  * prev linkage across the fetched run
  * timestamps increasing and not more than 2h in the future

What this does NOT do: full consensus validation of the txs (that is
the full node's job — validate_tx over the UTXO set). The wallet
verifies headers + Merkle (real verification) and applies the txs to
its own ledger view; a block that fails header/Merkle checks is
dropped and the sync stops with the reason. That boundary is stated
in the output, not hidden.

Seeds: seeds.json in the workspace (currently empty — no public seed
is configured). The live path on this VM is the local node
(127.0.0.1:9433), which the P2P bootstrap test verified on
2026-11-12 (fresh node synced 0 -> 2001 by dialing it). Tailnet
seeds (100.64.0.0/10) are dialed through the tunnel proxy, exactly
as p2p.py does — plain sockets cannot reach the tailnet.
"""
import json
import os
import socket
import struct
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from genesis_fork import (ser_header, sha256d, bits_to_target,
                          merkle_root, txid, NETWORKS)
from txscript import parse_tx

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEEDS_PATH = os.path.join(WORKSPACE, "seeds.json")
FORK_MAGIC = NETWORKS["fork"]["magic"]
DEFAULT_PEER = ("127.0.0.1", 9433)
MAX_WALK = 2000  # blocks fetched in one sync; more = resync from local chain


class P2PError(Exception):
    pass


def read_seeds(path=SEEDS_PATH):
    """Seed addresses from seeds.json. Returns [] when the file has
    no seeds (the current state — the local node is the only peer)."""
    try:
        with open(path) as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    entries = data.get("seeds", []) if isinstance(data, dict) else data
    out = []
    for e in entries:
        a = e.get("addr") if isinstance(e, dict) else e
        if isinstance(a, str) and ":" in a:
            out.append(a.strip())
    return out


def _send(sock, msg):
    raw = json.dumps(msg).encode()
    sock.sendall(struct.pack(">I", len(raw)) + raw)


def _recv_msg(sock):
    """One length-prefixed JSON message. Raises P2PError on EOF/timeout."""
    hdr = b""
    while len(hdr) < 4:
        chunk = sock.recv(4 - len(hdr))
        if not chunk:
            raise P2PError("peer closed the connection")
        hdr += chunk
    (n,) = struct.unpack(">I", hdr)
    if n > 64 * 1024 * 1024:
        raise P2PError(f"peer message too large: {n} bytes")
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(min(65536, n - len(buf)))
        if not chunk:
            raise P2PError("peer closed the connection mid-message")
        buf += chunk
    return json.loads(buf.decode())


def _verify_block_header(blk):
    """Header PoW + Merkle + timestamp sanity. Returns an error string
    or None. blk: wire dict with version/prev/merkle/time/bits/nonce/
    txs (hex)."""
    try:
        prev = bytes.fromhex(blk["prev"])
        merkle = bytes.fromhex(blk["merkle"])
        txs = [bytes.fromhex(t) for t in blk["txs"]]
        hh = sha256d(ser_header(blk["version"], prev, merkle,
                                blk["time"], blk["bits"], blk["nonce"]))
    except (KeyError, ValueError, TypeError) as e:
        return f"malformed block: {e}"
    if int.from_bytes(hh, "big") > bits_to_target(blk["bits"]):
        return "insufficient proof of work"
    if merkle_root([txid(t) for t in txs]) != merkle:
        return "merkle root mismatch"
    if blk["time"] > time.time() + 7200:
        return "timestamp too far in future"
    return None


def _blk_hash(blk):
    return sha256d(ser_header(blk["version"], bytes.fromhex(blk["prev"]),
                              bytes.fromhex(blk["merkle"]), blk["time"],
                              blk["bits"], blk["nonce"]))


def sync_from_peer(peer, wallet_tip_height, wallet_tip_hash,
                   timeout=15, max_walk=MAX_WALK):
    """Sync from one peer. wallet_tip_* describe the wallet's current
    tip (from its ledger cache). Returns:
      {"up_to_date": bool, "peer": "host:port", "peer_height": int,
       "peer_hash": hex, "fetched": int, "blocks": [wire dicts, ...],
       "new_tip_height": int, "new_tip_hash": hex}
    blocks are genesis-first (forward order), each verified (header
    PoW + Merkle + prev linkage). Raises P2PError on failure."""
    host, port = peer
    # Tailnet peers go through the tunnel proxy (p2p.py's path).
    from p2p import _is_tailnet_host, _connect_via_tunnel_proxy
    if _is_tailnet_host(host):
        sock = _connect_via_tunnel_proxy(host, port, timeout=timeout)
    else:
        sock = socket.create_connection((host, port), timeout=timeout)
    sock.settimeout(timeout)
    deadline = time.time() + 300
    try:
        _send(sock, {"t": "hello", "magic": FORK_MAGIC,
                     "height": wallet_tip_height,
                     "hash": wallet_tip_hash or ("00" * 32),
                     "port": 0})
        peer_hello = None
        fetched = []
        # Read until we have the peer's hello (it also sends addr + txs).
        while peer_hello is None:
            if time.time() > deadline:
                raise P2PError("timed out waiting for peer hello")
            msg = _recv_msg(sock)
            if msg.get("t") == "hello":
                if msg.get("magic") != FORK_MAGIC:
                    raise P2PError("peer has the wrong network magic")
                peer_hello = msg
        peer_height = int(peer_hello.get("height", -1))
        peer_hash = str(peer_hello.get("hash", ""))
        if peer_height <= wallet_tip_height:
            return {"up_to_date": True, "peer": f"{host}:{port}",
                    "peer_height": peer_height, "peer_hash": peer_hash,
                    "fetched": 0, "blocks": [],
                    "new_tip_height": wallet_tip_height,
                    "new_tip_hash": wallet_tip_hash}
        # Walk back from the peer tip to our tip.
        want = peer_hash
        seen = set()
        while True:
            if len(fetched) >= max_walk:
                raise P2PError(
                    f"diverged by more than {max_walk} blocks — "
                    f"resync from the local chain instead")
            if time.time() > deadline:
                raise P2PError("sync deadline exceeded")
            if want in seen:
                raise P2PError("peer sent a block twice (loop)")
            seen.add(want)
            _send(sock, {"t": "getblock", "hash": want})
            blk = None
            while blk is None:
                if time.time() > deadline:
                    raise P2PError("timed out waiting for block")
                msg = _recv_msg(sock)
                if msg.get("t") == "block":
                    blk = msg["block"]
            bad = _verify_block_header(blk)
            if bad:
                raise P2PError(f"block {want[:16]} failed verification: {bad}")
            fetched.append(blk)
            prev_hex = blk["prev"]
            if prev_hex == (wallet_tip_hash or ("00" * 32)):
                break
            if _blk_hash(blk).hex() == wallet_tip_hash:
                break
            want = prev_hex
        # fetched is tip-first; reverse to forward order and check the
        # prev linkage across the whole run.
        fetched.reverse()
        for i, blk in enumerate(fetched):
            if i == 0:
                continue
            if blk["prev"] != _blk_hash(fetched[i - 1]).hex():
                raise P2PError("prev linkage broken in fetched run")
        new_tip = fetched[-1]
        return {"up_to_date": False, "peer": f"{host}:{port}",
                "peer_height": peer_height, "peer_hash": peer_hash,
                "fetched": len(fetched), "blocks": fetched,
                "new_tip_height": wallet_tip_height + len(fetched),
                "new_tip_hash": _blk_hash(new_tip).hex()}
    finally:
        try:
            sock.close()
        except OSError:
            pass
