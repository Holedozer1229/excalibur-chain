"""infancy.py — infancy security for the young fork + wallet.

The fork is young: few peers, thin hashpower, a short chain. The
known attack vectors against a young chain are replay, eclipse,
51% / deep reorg, and double-spend. This module is the wallet-side
defence for each one. Nothing here is a consensus change — these are
checks the wallet runs before it trusts a tip, a balance, or a
broadcast. A failed check refuses the action and says why.

  1. REPLAY (cross-chain): fork txs and Bitcoin txs cannot be
     replayed onto each other — fork outputs are opcode-free locks,
     Bitcoin outputs are scripts. Enforced structurally in
     broadcast.check_replay_safe before any network call. This module
     only reports the property; the enforcement lives in broadcast.py.
  2. ECLIPSE (one peer lying about the tip): the wallet never
     advances its tip on a single peer's word. check_tip_agreement
     dials every configured peer's hello and requires at least two
     independent sources (peers, or a peer plus the local node's RPC
     tip) to agree on the same (height, hash) before a P2P sync
     applies blocks. One peer alone is refused with the reason.
  3. 51% / DEEP REORG: the wallet treats payments as settled only
     at depth. PAYMENT_MIN_CONF = 6 (Bitcoin convention); coinbase
     maturity is 100 blocks by consensus (txscript.COINBASE_MATURITY).
     confirmations() reports the depth of a tx from the node, and the
     ledger's local scan already discards its cache and rescans from
     genesis when the next record's prev does not match the cached tip
     (reorg-safe by construction).
  4. DOUBLE-SPEND: before any broadcast, every input is checked
     still-unspent against the node that will receive the tx
     (broadcast.check_inputs_unspent_fork / _bitcoin), and after
     submit the tx must be visible in that node's mempool. The fork
     mempool refuses replacements (no RBF), so a first-seen tx cannot
     be silently swapped for a conflicting one.

security_report() runs the checks that can run cheaply and returns a
list of {name, status, detail} for `wallet security`.
"""
import json
import os
import socket
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from txscript import COINBASE_MATURITY
from . import p2p_sync
from .ledger import RpcError

PAYMENT_MIN_CONF = 6
ECLIPSE_MIN_SOURCES = 2


class InfancyError(Exception):
    pass


def peer_tip(peer, timeout=10):
    """Dial one peer, read its hello, return (height, hash).
    Raises InfancyError on any failure — a peer that will not say its
    tip is not a source."""
    host, port = peer
    try:
        from p2p import _is_tailnet_host, _connect_via_tunnel_proxy
        if _is_tailnet_host(host):
            sock = _connect_via_tunnel_proxy(host, port, timeout=timeout)
        else:
            sock = socket.create_connection((host, port), timeout=timeout)
    except Exception as e:
        raise InfancyError(f"peer {host}:{port} unreachable: {e}")
    sock.settimeout(timeout)
    try:
        p2p_sync._send(sock, {"t": "hello",
                              "magic": p2p_sync.FORK_MAGIC,
                              "height": -1, "hash": "00" * 32, "port": 0})
        deadline = time.time() + timeout
        while time.time() < deadline:
            msg = p2p_sync._recv_msg(sock)
            if msg.get("t") == "hello":
                if msg.get("magic") != p2p_sync.FORK_MAGIC:
                    raise InfancyError(
                        f"peer {host}:{port} has the wrong network magic")
                return int(msg.get("height", -1)), str(msg.get("hash", ""))
        raise InfancyError(f"peer {host}:{port} sent no hello")
    except InfancyError:
        raise
    except Exception as e:
        raise InfancyError(f"peer {host}:{port} hello failed: {e}")
    finally:
        try:
            sock.close()
        except OSError:
            pass


def check_tip_agreement(peers, local_tip=None, rpc_tip=None):
    """Require >= ECLIPSE_MIN_SOURCES agreeing on one tip.

    peers: [(host, port), ...]. local_tip / rpc_tip: (height, hash)
    tuples from the wallet cache / live node RPC. Returns
    {"sources": n, "agreeing": n, "tip": (h, hash) or None,
     "ok": bool, "detail": str}. ok=False refuses a P2P sync."""
    votes = {}
    sources = 0
    errors = []
    for peer in peers or []:
        try:
            tip = peer_tip(peer)
        except InfancyError as e:
            errors.append(str(e))
            continue
        sources += 1
        votes.setdefault(tip, []).append(f"peer {peer[0]}:{peer[1]}")
    for label, tip in (("local cache", local_tip),
                       ("node RPC", rpc_tip)):
        if tip is not None:
            sources += 1
            votes.setdefault(tuple(tip), []).append(label)
    if not votes:
        return {"sources": 0, "agreeing": 0, "tip": None, "ok": False,
                "detail": "no tip source answered (peers unreachable, "
                          "no local tip, no RPC tip)"
                          + (f"; {'; '.join(errors)}" if errors else "")}
    best_tip, best_voters = max(votes.items(), key=lambda kv: len(kv[1]))
    agreeing = len(best_voters)
    ok = agreeing >= ECLIPSE_MIN_SOURCES
    detail = (f"{agreeing} of {sources} sources agree on tip "
              f"h{best_tip[0]} {best_tip[1][:16]}… "
              f"({', '.join(best_voters)})")
    if not ok:
        detail += (" — REFUSED: a single source could be an eclipse; "
                   "need 2 agreeing sources (a second peer, or the "
                   "local node RPC tip)")
    if errors:
        detail += f"; unreachable: {'; '.join(errors)}"
    return {"sources": sources, "agreeing": agreeing,
            "tip": best_tip, "ok": ok, "detail": detail}


def confirmations(txid, network, rpc=None, btc_rpc=None):
    """Confirmations of a txid, or None when the node cannot say.

    Fork: the node has no getrawtransaction — a tx in the mempool is
    0 confirmations; anything else is 'unknown (mined or dropped —
    check wallet history)'. Bitcoin: getrawtransaction (verbose) gives
    the real confirmation count; in-mempool is 0."""
    if network == "fork":
        from .ledger import RpcClient
        rpc = rpc or RpcClient()
        try:
            mempool = rpc.call("getrawmempool")
        except RpcError:
            return None
        if txid in mempool:
            return 0
        return None
    if btc_rpc is None:
        raise InfancyError("bitcoin confirmations need a Bitcoin RPC client")
    try:
        tx = btc_rpc.call("getrawtransaction", [txid, True])
    except Exception:
        tx = None
    if tx:
        return int(tx.get("confirmations", 0))
    try:
        if btc_rpc.call("getmempoolentry", [txid]):
            return 0
    except Exception:
        pass
    return None


def settled(value_conf, kind="payment"):
    """Is this depth settled? Payments: 6 conf. Coinbase: 100 (and
    the consensus maturity already enforces it for spends)."""
    need = COINBASE_MATURITY if kind == "coinbase" else PAYMENT_MIN_CONF
    if value_conf is None:
        return False, f"unknown depth (need {need} conf)"
    return value_conf >= need, (
        f"{value_conf} conf (need {need})"
        if value_conf >= need else
        f"only {value_conf} conf (need {need} — not settled)")


def security_report(datadir, rpc=None, peers=None, btc_rpc=None):
    """Cheap checks for `wallet security`. Returns a list of dicts
    {name, status: PASS|WARN|FAIL, detail}."""
    out = []
    out.append({"name": "replay (cross-chain)", "status": "PASS",
                "detail": "structural: fork outputs are opcode-free "
                          "locks, Bitcoin outputs are scripts — a tx "
                          "valid on one chain is invalid on the other, "
                          "and broadcast.py refuses cross-network "
                          "submits before any network call"})
    out.append({"name": "double-spend (pre-broadcast)", "status": "PASS",
                "detail": "broadcast checks every input still-unspent "
                          "on the receiving node and verifies mempool "
                          "acceptance after submit; fork mempool has "
                          "no RBF (first-seen tx cannot be replaced)"})
    out.append({"name": "reorg / settlement depth", "status": "PASS",
                "detail": f"payments settle at {PAYMENT_MIN_CONF} conf, "
                          f"coinbase at {COINBASE_MATURITY} (consensus); "
                          f"local scan discards its cache and rescans "
                          f"from genesis on a prev mismatch"})
    # Eclipse: needs live peer answers.
    if peers:
        try:
            rpc_tip = None
            if rpc is not None:
                try:
                    rpc_tip = rpc.tip()
                except RpcError:
                    rpc_tip = None
            res = check_tip_agreement(peers, rpc_tip=rpc_tip)
            out.append({"name": "eclipse (tip agreement)",
                        "status": "PASS" if res["ok"] else "FAIL",
                        "detail": res["detail"]})
        except Exception as e:
            out.append({"name": "eclipse (tip agreement)",
                        "status": "FAIL", "detail": str(e)})
    else:
        out.append({"name": "eclipse (tip agreement)", "status": "WARN",
                    "detail": "no peers configured (seeds.json is "
                              "empty) — P2P sync uses the local node "
                              "only; add --peers host:port,host:port "
                              "to check tip agreement across peers"})
    # Broadcast history.
    log_path = os.path.join(datadir, "broadcast_log.jsonl")
    n = 0
    if os.path.isfile(log_path):
        with open(log_path) as f:
            n = sum(1 for line in f if line.strip())
    out.append({"name": "broadcast history", "status": "PASS",
                "detail": f"{n} broadcast(s) recorded in "
                          f"broadcast_log.jsonl (txid/network/height "
                          f"only — no keys, no raw txs)"})
    return out
