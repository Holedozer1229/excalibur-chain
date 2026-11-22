"""cli.py — the unified `excalibur` command line (wallet-first).

Usage: python3 -m excalibur_wallet [--datadir DIR]
         [--passphrase-file FILE] <command> [options]

The datadir holds the encrypted wallet file, the ledger cache, the
Trifold state and Frostgate vault references. Default:
~/workspace/excalibur-wallet-data (override with --datadir or
EXCAL_WALLET_DIR). The passphrase is read from --passphrase-file
(a 0600 file) or prompted interactively (getpass) — never from a
command-line argument, never echoed, never logged.

Every command that touches funds prints exactly what it did and what
it did NOT do. `wallet send` builds, signs and verifies — and stops.
Broadcast is a separate, explicit step: `wallet broadcast --file F
--network fork|bitcoin --yes` submits an already-built, already-
verified tx after re-checking it (replay, re-validation, unspent
inputs, mempool acceptance). Without --yes it refuses.
"""
import argparse
import getpass
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from .wallet import Wallet, WalletError
from .ledger import Ledger, RpcClient, RpcError
from . import broadcast as broadcast_mod
from .broadcast import BroadcastError
from . import infancy as infancy_mod
from .infancy import InfancyError
from .txbuild import (build_send, build_htlc_claim, build_htlc_refund,
                     build_qhtlc_claim, build_qhtlc_refund,
                     build_pqh_spend, build_knot_lock_test,
                     build_knot_spend_test, parse_amount, TxBuildError)
from .locks import (parse_lock_hex, lock_status, knot_lock_refuse,
                   htlc_lock, qhtlc_lock, KnotRefused)
from . import btc_htlc as btc_htlc_mod
from .btc_htlc import BtcHtlcError
from . import atomic_swap as swap_mod
from .atomic_swap import SwapError
from .checkpoints import verify_chain_attestations, verify_checkpoint_file
from . import p2p_sync
from . import uruu
from . import sss
from . import frostgate

DEFAULT_DATADIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "excalibur-wallet-data")
SWORD = 100_000_000


def _fmt_swords(v):
    return f"{v:,} swords ({v / SWORD:.8f} EXCAL)"


def _get_passphrase(args, confirm=False):
    if getattr(args, "passphrase_file", None):
        with open(args.passphrase_file, "rb") as f:
            pw = f.read().strip()
        if not pw:
            raise SystemExit("passphrase file is empty")
        return pw
    pw = getpass.getpass("Wallet passphrase: ").encode()
    if not pw:
        raise SystemExit("empty passphrase")
    if confirm:
        pw2 = getpass.getpass("Repeat passphrase: ").encode()
        if pw != pw2:
            raise SystemExit("passphrases do not match")
    return pw


def _load_wallet(args):
    pw = _get_passphrase(args)
    try:
        w = Wallet.load(args.datadir, pw)
    except WalletError as e:
        raise SystemExit(f"wallet: {e}")
    return w, pw


def _ledger(args):
    return Ledger(args.datadir)


def _watched(wallet):
    return wallet.watched_locks()


def _utxos_for_send(args, wallet):
    """Get spend candidates only from the node's validated UTXO state."""
    led = _ledger(args)
    locks = _watched(wallet)
    try:
        balances, (tip_height, tip_hash) = led.balance_via_rpc(locks)
        utxos = []
        for lock_hex, b in balances.items():
            for u in b["utxos"]:
                if u["pending_spend"]:
                    continue
                utxos.append({"txid": u["txid"], "vout": u["vout"],
                              "value": u["value"], "lock": lock_hex,
                              "coinbase": u["coinbase"],
                              "cb_h": u.get("cb_h", 0),
                              "mature": u["mature"],
                              "pending_spend": False})
        return utxos, tip_height + 1, f"live node RPC (tip {tip_height})"
    except RpcError as e:
        raise SystemExit(
            f"send refused: live node did not provide a validated UTXO set: {e}")


def _lock_to_priv(wallet):
    """{lock_hex: priv} for every address the wallet has derived."""
    from .keys import address_for_priv
    out = {}
    if wallet.kind == "legacy":
        priv = int(wallet._data["legacy_priv"], 16)
        out[address_for_priv(priv)] = priv
        return out
    for i in range(wallet._data["next_receive"]):
        priv = wallet.receive_priv(i)
        out[address_for_priv(priv)] = priv
    for i in range(wallet._data["next_change"]):
        priv = wallet.change_priv(i)
        out[address_for_priv(priv)] = priv
    return out


def _print_tx_result(res):
    print(f"txid:      {res['txid']}")
    print(f"fee:       {_fmt_swords(res['fee'])}")
    print("inputs:")
    for u in res["inputs"]:
        print(f"  {u['txid']}:{u['vout']}  {_fmt_swords(u['value'])}")
    print("outputs:")
    for o in res["outputs"]:
        print(f"  {_fmt_swords(o['value'])} -> {o['lock']}")
    print(f"validated: locally at height {res['validated_at_height']} "
          f"(validate_tx OK)")
    print(f"raw hex:   {res['raw_hex']}")
    print("NOT broadcast. Submit it with `wallet broadcast --tx <rawhex> "
          "--network fork --yes` — or save it first (`wallet send "
          "--save FILE`) and broadcast the file. Broadcast re-checks "
          "the tx (replay, re-validation, unspent inputs) before "
          "submitting, and verifies mempool acceptance after.")


# ------------------------------------------------------------------ wallet
def cmd_wallet_create(args):
    pw = _get_passphrase(args, confirm=True)
    try:
        w, mnemonic = Wallet.create(args.datadir, pw, words=args.words)
    except WalletError as e:
        raise SystemExit(f"wallet create: {e}")
    print(f"wallet created: {w.path} (AES-256 encrypted, chmod 600)")
    print(f"network: fork | kind: mnemonic ({args.words} words)")
    print()
    print("WRITE THIS MNEMONIC DOWN NOW — it is shown once, never again:")
    print(f"  {mnemonic}")
    print()
    print("It restores the whole wallet. Never photograph it, never paste")
    print("it into chat, never store it in the cloud. Consider `wallet")
    print("split` for a Shamir backup across separate places.")
    print(f"first receive address: {w.receive_address()}")


def cmd_wallet_restore(args):
    pw = _get_passphrase(args, confirm=True)
    if args.shares:
        shares = [sss.decode_share(s) for s in args.shares]
        seed = sss.combine(shares)
        try:
            w = Wallet.create_from_seed(args.datadir, pw, seed)
        except WalletError as e:
            raise SystemExit(f"wallet restore: {e}")
        print(f"wallet restored from {len(shares)} SSS shares: {w.path}")
        print(f"first receive address: {w.receive_address()}")
        print("NOTE: restored from seed — there is no mnemonic to show.")
        return
    if args.mnemonic:
        try:
            w, _ = Wallet.create(args.datadir, pw, mnemonic=args.mnemonic)
        except WalletError as e:
            raise SystemExit(f"wallet restore: {e}")
        print(f"wallet restored from mnemonic: {w.path}")
        print(f"first receive address: {w.receive_address()}")
        return
    raise SystemExit("restore needs --shares ... or --mnemonic '...'.")


def cmd_wallet_address(args):
    w, _pw = _load_wallet(args)
    print(f"receive address [{args.index if args.index is not None else w._data['next_receive']}]: "
          f"{w.receive_address(args.index)}")


def cmd_wallet_receive(args):
    w, pw = _load_wallet(args)
    idx, addr = w.fresh_receive(pw)
    print(f"fresh receive address [{idx}]: {addr}")
    print("Give this address to the sender. It is a PKH lock (hash of")
    print("your pubkey) — the pubkey stays hidden until you spend.")


def cmd_wallet_info(args):
    w, _pw = _load_wallet(args)
    print(f"wallet:    {w.path}")
    print(f"network:   {w.network} | kind: {w.kind} | "
          f"encrypted: {w.is_encrypted}")
    print(f"next receive index: {w._data['next_receive']} | "
          f"next change index: {w._data['next_change']}")
    print(f"current receive address: {w.receive_address()}")
    if w.kind == "mnemonic":
        print(f"PQH address (Trifold root): {w.pqh_address()}")
    print(f"recorded locks: {len(w._data.get('locks', []))}")
    try:
        st = frostgate.vault_status()
        print(f"Frostgate vault: {st['threshold']}-of-"
              f"{st['num_operators']} | group key "
              f"{st['group_key'][:16]}… | testnet "
              f"{st['address_testnet']}")
    except frostgate.FrostgateError as e:
        print(f"Frostgate vault: not available ({e})")


def cmd_wallet_balance(args):
    w, _pw = _load_wallet(args)
    led = _ledger(args)
    locks = _watched(w)
    via = args.via
    if via == "rpc":
        try:
            balances, (tip_h, _th) = led.balance_via_rpc(locks)
            mature = sum(b["mature"] for b in balances.values())
            immature = sum(b["immature"] for b in balances.values())
            spendable = sum(b["spendable"] for b in balances.values())
            pending = sum(b["pending_spend"] for b in balances.values())
            print(f"source: live node RPC (tip {tip_h})")
            print(f"spendable: {_fmt_swords(spendable)}")
            print(f"mature confirmed: {_fmt_swords(mature)}")
            print(f"immature: {_fmt_swords(immature)} (coinbase < 100 conf)")
            print(f"pending spend: {_fmt_swords(pending)}")
            print(f"total:    {_fmt_swords(mature + immature)}")
            return
        except RpcError as e:
            raise SystemExit(f"RPC balance failed: {e}")
    if via == "snapshot":
        if not args.snapshot or not args.manifest:
            raise SystemExit("snapshot mode needs --snapshot FILE "
                             "--manifest FILE")
        with open(args.manifest) as f:
            manifest = json.load(f)
        try:
            overlay, spent = led.load_snapshot(args.snapshot, manifest)
        except ValueError as e:
            raise SystemExit(f"snapshot failed verification: {e}")
        balances = led.balance_from_overlay(overlay, locks)
        mature = sum(b["mature"] for b in balances.values())
        print(f"source: verified light snapshot at height "
              f"{manifest['height']} (SHA-256 + Merkle roots OK)")
        print(f"mature:   {_fmt_swords(mature)}")
        print("NOTE: snapshot covers fork-created UTXOs only (the Bitcoin")
        print("snapshot base is not built on this VM) and is only as fresh")
        print(f"as its checkpoint (height {manifest['height']}).")
        return
    stats = led.sync_local(locks)
    bal = led.cached_balance()
    print(f"source: UNVALIDATED local chain scan (tip {bal['tip_height']}, "
          f"{stats['new_records']} new records this run)")
    print("diagnostic only: this scan does not validate consensus or authorize spending")
    print(f"mature:   {_fmt_swords(bal['mature'])}")
    print(f"immature: {_fmt_swords(bal['immature'])} (coinbase < 100 conf)")
    print(f"total:    {_fmt_swords(bal['mature'] + bal['immature'])}")


def cmd_wallet_utxos(args):
    w, _pw = _load_wallet(args)
    led = _ledger(args)
    locks = _watched(w)
    try:
        balances, (tip_h, _th) = led.balance_via_rpc(locks)
        rows = []
        for lock_hex, b in balances.items():
            for u in b["utxos"]:
                rows.append({**u, "lock": lock_hex})
        print(f"source: live node RPC (tip {tip_h})")
    except RpcError as exc:
        raise SystemExit(
            f"UTXO listing refused: live node did not provide a validated UTXO set: {exc}")
    if args.lock:
        rows = [r for r in rows if r["lock"] == args.lock.lower()]
    rows.sort(key=lambda r: -r["value"])
    if not rows:
        print("no UTXOs for this wallet")
        return
    for r in rows:
        print(f"{r['txid']}:{r['vout']}  {_fmt_swords(r['value'])}  "
              f"{'mature' if r['mature'] else 'IMMATURE'}  "
              f"{'PENDING-SPEND' if r.get('pending_spend', False) else 'unspent'}  "
              f"{'coinbase' if r['coinbase'] else 'payment'}  "
              f"lock {r['lock'][:12]}…")


def cmd_wallet_history(args):
    w, _pw = _load_wallet(args)
    led = _ledger(args)
    stats = led.sync_local(_watched(w))
    hist = led.cached_history()
    print(f"source: local chain scan (tip {stats['tip_height']})")
    rows = hist[-args.limit:]
    if not rows:
        print("no history for this wallet yet")
        return
    for ev in rows:
        sign = "+" if ev["value"] > 0 else ""
        print(f"h{ev['height']} {ev['kind']:7} {sign}"
              f"{_fmt_swords(abs(ev['value']))}  tx {ev['txid'][:16]}…")


def cmd_wallet_send(args):
    w, pw = _load_wallet(args)
    try:
        dest_lock = parse_lock_hex(args.to)
        amount = parse_amount(args.amount)
    except (ValueError, TxBuildError) as e:
        raise SystemExit(f"send: {e}")
    utxos, height, source = _utxos_for_send(args, w)
    print(f"UTXO source: {source}; validating at height {height}")
    idx = w._data["next_change"]
    change_lock = bytes.fromhex(w.change_address(idx))
    try:
        res = build_send(utxos, _lock_to_priv(w), dest_lock, amount,
                         change_lock, fee_rate=args.fee_rate, height=height)
    except (TxBuildError, KnotRefused) as e:
        raise SystemExit(f"send refused: {e}")
    w.next_change(pw)  # advance the change counter on success only
    if args.save:
        by_key = {(u["txid"], u["vout"]): u for u in utxos}
        saved_inputs = []
        for inp in res["inputs"]:
            u = by_key.get((inp["txid"], inp["vout"]), {})
            saved_inputs.append({"txid": inp["txid"],
                                 "vout": inp["vout"],
                                 "value": inp["value"],
                                 "lock": u.get("lock", ""),
                                 "coinbase": bool(u.get("coinbase", False)),
                                 "cb_h": int(u.get("cb_h", 0))})
        doc = {"network": "fork", "raw_hex": res["raw_hex"],
               "txid": res["txid"], "fee": res["fee"],
               "validated": True,
               "validated_at_height": res["validated_at_height"],
               "inputs": saved_inputs, "outputs": res["outputs"]}
        with open(args.save, "w") as f:
            json.dump(doc, f, indent=2)
        os.chmod(args.save, 0o600)
        print(f"saved (0600): {args.save} — broadcast it with "
              f"`wallet broadcast --file {args.save} --network fork --yes`")
    _print_tx_result(res)


def _load_broadcast_tx(args):
    """(raw_hex, inputs|None, height|None) from --file or --tx."""
    if args.file:
        with open(args.file) as f:
            text = f.read().strip()
        try:
            doc = json.loads(text)
        except ValueError:
            doc = text
        if isinstance(doc, dict) and "raw_hex" in doc:
            return (doc["raw_hex"], doc.get("inputs") or None,
                    doc.get("validated_at_height"))
        if isinstance(doc, str):
            return doc.strip(), None, None
        raise SystemExit("--file must be a saved-tx JSON (raw_hex) "
                         "or a plain hex file")
    if args.tx:
        return args.tx.strip(), None, None
    raise SystemExit("broadcast needs --file FILE or --tx HEX")


def _parse_btc_rpc(args):
    host, port = "127.0.0.1", 8332
    if args.btc_rpc:
        try:
            host, port = args.btc_rpc.rsplit(":", 1)
            port = int(port)
        except ValueError:
            raise SystemExit("--btc-rpc must be HOST:PORT")
    return host, port


def cmd_wallet_broadcast(args):
    if not args.yes:
        print("REFUSED without --yes. Broadcast moves funds "
              "irreversibly: the tx leaves this wallet and enters a "
              "mempool. Re-run with --yes to accept that, after "
              "checking the txid and the fee above.")
        raise SystemExit(1)
    raw_hex, inputs, _height = _load_broadcast_tx(args)
    network = args.network
    try:
        if network == "fork":
            led = _ledger(args)
            res = broadcast_mod.broadcast_fork(
                raw_hex, rpc=led.rpc, inputs=inputs, height=_height,
                dry_run=args.dry_run)
            height = led.rpc.tip()[0] if not args.dry_run else None
        else:
            host, port = _parse_btc_rpc(args)
            res = broadcast_mod.broadcast_bitcoin(
                raw_hex, host=host, port=port,
                config_path=args.btc_rpc_config, dry_run=args.dry_run)
            height = None
    except (BroadcastError, RpcError) as e:
        raise SystemExit(f"broadcast refused: {e}")
    print(f"network:   {res['network']}")
    print(f"txid:      {res['txid']}")
    if res.get("fee") is not None:
        print(f"fee:       {_fmt_swords(res['fee'])}")
    if res["dry_run"]:
        print("DRY RUN — validated, NOT submitted.")
        return
    print(f"mempool:   accepted ({res['txid'][:16]}… visible in the "
          f"node mempool)")
    log = broadcast_mod.append_broadcast_log(
        args.datadir, {"network": res["network"], "txid": res["txid"],
                       "height": height, "dry_run": False})
    print(f"logged:    {log}")
    print("Confirm it in a block with `wallet confirmations --txid "
          f"{res['txid']} --network {res['network']}` — a payment is "
          f"settled at {infancy_mod.PAYMENT_MIN_CONF} confirmations.")


def cmd_wallet_confirmations(args):
    txid = args.txid.lower()
    if len(txid) != 64:
        raise SystemExit("--txid must be 64 hex chars")
    try:
        if args.network == "fork":
            conf = infancy_mod.confirmations(txid, "fork",
                                             rpc=_ledger(args).rpc)
        else:
            host, port = _parse_btc_rpc(args)
            user, password = broadcast_mod.load_btc_credentials(
                args.btc_rpc_config)
            btc = broadcast_mod.BitcoinRpcClient(host, port, user,
                                                 password)
            conf = infancy_mod.confirmations(txid, "bitcoin", btc_rpc=btc)
    except (BroadcastError, InfancyError, RpcError) as e:
        raise SystemExit(f"confirmations: {e}")
    if conf is None:
        print(f"tx {txid}: not in the mempool — mined, dropped, or "
              f"unknown to this node. Check `wallet history`.")
        return
    ok, detail = infancy_mod.settled(conf)
    print(f"tx {txid}: {conf} confirmation(s) — {detail}")
    print("settled" if ok else "NOT settled yet — wait for more blocks")


def cmd_wallet_security(args):
    peers = []
    if args.peers:
        for p in args.peers.split(","):
            try:
                host, port = p.strip().rsplit(":", 1)
                peers.append((host, int(port)))
            except ValueError:
                raise SystemExit(f"--peers entry {p!r} must be HOST:PORT")
    try:
        rpc = _ledger(args).rpc
        rpc.tip()
    except RpcError:
        rpc = None
    print("infancy security — young fork, known attack vectors:")
    for chk in infancy_mod.security_report(args.datadir, rpc=rpc,
                                           peers=peers):
        print(f"  [{chk['status']:4}] {chk['name']}: {chk['detail']}")


def cmd_wallet_locks(args):
    w, _pw = _load_wallet(args)
    led = _ledger(args)
    try:
        tip_h, _th = led.rpc.tip()
    except RpcError:
        tip_h = led._load_cache().get("tip_height", -1)
    print(f"lock types at fork tip {tip_h}:")
    for st in lock_status(tip_h if tip_h >= 0 else 0):
        flag = "ACTIVE " if st["active"] else "staged "
        print(f"  {flag} 0x{st['version']:02x} {st['type']:6} "
              f"(activation {st['activation']}) — {st['note']}")


def cmd_wallet_split(args):
    w, _pw = _load_wallet(args)
    if w.kind != "mnemonic" or not w._seed:
        raise SystemExit("split needs a mnemonic wallet (seed in memory)")
    shares = sss.split(w._seed, args.shares, args.threshold)
    print(f"Shamir {args.threshold}-of-{args.shares} split of the wallet "
          f"seed. Any {args.threshold} of these rebuild the wallet; "
          f"fewer reveal nothing.")
    print("Store each share in a SEPARATE place (paper, metal, safe).")
    print("Never photograph them, never paste them into chat, never put")
    print("two shares in the same place.")
    for x, y in shares:
        print(f"  share {x}: {sss.encode_share(x, y)}")


def cmd_wallet_import_node(args):
    with open(args.wallet) as f:
        data = json.load(f)
    if isinstance(data, dict) and data.get("format", "").startswith(
            "excalibur-wallet-enc"):
        import wallet_crypto
        if not args.keyfile:
            raise SystemExit("encrypted node wallet needs --keyfile")
        with open(args.keyfile, "rb") as f:
            key = f.read().strip()
        data = json.loads(wallet_crypto.decrypt_bytes(data, key).decode())
    if not (isinstance(data, dict) and "priv" in data and "pub" in data):
        raise SystemExit("not a node wallet file (want {priv, pub})")
    pw = _get_passphrase(args, confirm=True)
    try:
        w = Wallet.import_legacy(args.datadir, pw, data["priv"],
                                 data["pub"])
    except WalletError as e:
        raise SystemExit(f"import: {e}")
    print(f"imported node wallet as legacy wallet: {w.path}")
    print(f"address: {w.receive_address()}")


# ------------------------------------------------------------------- locks
def _parse_utxo_ref(s):
    try:
        txid, vout = s.rsplit(":", 1)
        return txid, int(vout)
    except ValueError:
        raise SystemExit("--utxo must be TXID:VOUT")


def _find_wallet_utxo(args, wallet, txid, vout):
    led = _ledger(args)
    try:
        balances, (tip_height, _tip_hash) = led.balance_via_rpc(_watched(wallet))
        for lock_hex, b in balances.items():
            for u in b["utxos"]:
                if u["txid"] == txid and u["vout"] == vout:
                    if not u["mature"] or u["pending_spend"]:
                        raise SystemExit(
                            f"UTXO {txid}:{vout} is immature or already pending-spent")
                    return {"txid": txid, "vout": vout,
                            "value": u["value"], "lock": lock_hex,
                            "coinbase": u["coinbase"],
                            "cb_h": u.get("cb_h", 0),
                            "mature": u["mature"],
                            "tip_height": tip_height,
                            "pending_spend": False}
    except RpcError as exc:
        raise SystemExit(
            f"spend refused: live node did not provide a validated UTXO set: {exc}")
    raise SystemExit(f"UTXO {txid}:{vout} not found in this wallet")


def cmd_wallet_htlc_create(args):
    w, pw = _load_wallet(args)
    try:
        secret = bytes.fromhex(args.secret) if args.secret else None
        if secret is None:
            import secrets as _s
            secret = _s.token_bytes(32)
            print("generated secret (show once — give it to the claimer "
                  "out of band):")
            print(f"  {secret.hex()}")
        claim_pub = bytes.fromhex(args.claim_pubkey)
        refund_pub = bytes.fromhex(args.refund_pubkey)
        lock, desc = htlc_lock(secret, claim_pub, refund_pub,
                               args.timeout)
    except (ValueError, TxBuildError) as e:
        raise SystemExit(f"htlc create: {e}")
    w.record_lock({"kind": "htlc", "lock": lock.hex(),
                   "descriptor": desc.hex(),
                   "timeout": args.timeout,
                   "claim_pubkey": claim_pub.hex(),
                   "refund_pubkey": refund_pub.hex()}, pw)
    print(f"HTLC lock: {lock.hex()}")
    print(f"descriptor: {desc.hex()}")
    print(f"timeout (refund at height >=): {args.timeout}")
    print("Fund it with `wallet send --to <lock>`. The secret stays with")
    print("the claimer; the descriptor is revealed only at spend time.")


def cmd_wallet_htlc_claim(args):
    w, pw = _load_wallet(args)
    txid, vout = _parse_utxo_ref(args.utxo)
    entry = _find_wallet_utxo(args, w, txid, vout)
    rec = w.find_lock(entry["lock"])
    if rec is None:
        raise SystemExit("no HTLC descriptor recorded for this lock "
                         "(create it with `wallet htlc create` first)")
    try:
        dest_lock = parse_lock_hex(args.dest)
        secret = bytes.fromhex(args.secret)
        desc = bytes.fromhex(rec["descriptor"])
        height = entry["tip_height"] + 1
        # The claim key must be a wallet key.
        privs = _lock_to_priv(w)
        claim_pub = bytes.fromhex(rec["claim_pubkey"])
        from .keys import priv_to_pub_compressed
        claim_priv = None
        for _lk, priv in privs.items():
            if priv_to_pub_compressed(priv) == claim_pub:
                claim_priv = priv
                break
        if claim_priv is None:
            raise SystemExit("claim key is not a wallet key")
        res = build_htlc_claim(entry, dest_lock, args.fee, secret,
                               desc, claim_priv, height)
    except (ValueError, TxBuildError) as e:
        raise SystemExit(f"htlc claim refused: {e}")
    _print_tx_result(res)


def cmd_wallet_htlc_refund(args):
    w, _pw = _load_wallet(args)
    txid, vout = _parse_utxo_ref(args.utxo)
    entry = _find_wallet_utxo(args, w, txid, vout)
    rec = w.find_lock(entry["lock"])
    if rec is None:
        raise SystemExit("no HTLC descriptor recorded for this lock")
    try:
        dest_lock = parse_lock_hex(args.dest)
        desc = bytes.fromhex(rec["descriptor"])
        height = entry["tip_height"] + 1
        from .keys import priv_to_pub_compressed
        refund_pub = bytes.fromhex(rec["refund_pubkey"])
        refund_priv = None
        for _lk, priv in _lock_to_priv(w).items():
            if priv_to_pub_compressed(priv) == refund_pub:
                refund_priv = priv
                break
        if refund_priv is None:
            raise SystemExit("refund key is not a wallet key")
        res = build_htlc_refund(entry, dest_lock, args.fee, desc,
                                refund_priv, height)
    except (ValueError, TxBuildError) as e:
        raise SystemExit(f"htlc refund refused: {e}")
    _print_tx_result(res)


# ------------------------------------------------------- BTC HTLC (P2WSH)
# Standalone Bitcoin-side HTLC. This section funds a BTC P2WSH lock
# from the wallet's own Bitcoin P2WPKH UTXOs, and claims/refunds it
# with the wallet's keys. The funding UTXO is supplied explicitly
# (the wallet does not scan Bitcoin); broadcast.py does the unspent +
# testmempoolaccept checks before any submit. Nothing here broadcasts.
# The cross-chain flow that coordinates this leg with the EXCAL HTLC
# leg lives in `wallet swap` (atomic_swap.py) below.
def _btc_pub_to_priv(wallet):
    """{compressed_pubkey_bytes: priv} for every wallet key."""
    from .keys import priv_to_pub_compressed
    out = {}
    if wallet.kind == "legacy":
        priv = int(wallet._data["legacy_priv"], 16)
        out[priv_to_pub_compressed(priv)] = priv
        return out
    for i in range(wallet._data["next_receive"]):
        priv = wallet.receive_priv(i)
        out[priv_to_pub_compressed(priv)] = priv
    for i in range(wallet._data["next_change"]):
        priv = wallet.change_priv(i)
        out[priv_to_pub_compressed(priv)] = priv
    return out


def _print_btc_tx_result(res):
    print(f"txid:      {res['txid']}")
    print(f"wtxid:     {res['wtxid']}")
    print(f"fee:       {res['fee']:,} sats "
          f"({res['vsize']} vB at {res.get('fee_rate')} sats/vB)")
    print("inputs:")
    for u in res["inputs"]:
        print(f"  {u['txid']}:{u['vout']}  {u['value']:,} sats")
    print("outputs:")
    for o in res["outputs"]:
        print(f"  {o['value']:,} sats -> {o['script_pubkey'][:44]}…")
    print(f"raw hex:   {res['raw_hex']}")
    print(f"psbt:      {res['psbt']}")
    print("NOT broadcast. Submit it with `wallet broadcast --tx <rawhex> "
          "--network bitcoin --yes` — or save it first (`--save FILE`) "
          "and broadcast the file. Broadcast re-checks the tx (replay, "
          "unspent inputs, testmempoolaccept) before submitting, and "
          "verifies mempool acceptance after.")


def _btc_lock_record(lock, funding_txid=None):
    """Wallet lock-book record for a BTC HTLC (hashes only — never the
    secret). The 'lock' id is the P2WSH scriptPubKey hex."""
    rec = {"kind": "btc-htlc", "lock": lock["script_pubkey_hex"],
           "address": lock["address"],
           "witness_script": lock["witness_script_hex"],
           "secret_hash": lock["secret_hash"],
           "timeout": lock["timeout"],
           "claim_pubkey": lock["claim_pubkey"],
           "refund_pubkey": lock["refund_pubkey"],
           "network": lock["network"]}
    if funding_txid:
        rec["funding_txid"] = funding_txid
    return rec


def _btc_parse_hex_arg(s, name, want_len):
    try:
        b = bytes.fromhex(s)
    except ValueError:
        raise SystemExit(f"btc-htlc: --{name} must be hex")
    if len(b) != want_len:
        raise SystemExit(f"btc-htlc: --{name} must be {want_len} bytes "
                         f"(got {len(b)})")
    return b


def _btc_find_record(wallet, args):
    """Witness script for a claim/refund: explicit --witness-script,
    or a recorded lock found by --address."""
    if args.witness_script:
        try:
            return bytes.fromhex(args.witness_script)
        except ValueError:
            raise SystemExit("btc-htlc: --witness-script must be hex")
    if args.address:
        for e in wallet._data.get("locks", []):
            if e.get("kind") == "btc-htlc" \
                    and e.get("address") == args.address:
                return bytes.fromhex(e["witness_script"])
        raise SystemExit(f"btc-htlc: no recorded BTC HTLC for address "
                         f"{args.address} (create it with "
                         f"`wallet btc-htlc create` first)")
    raise SystemExit("btc-htlc: give --witness-script HEX or --address "
                     "of a recorded BTC HTLC")


def _btc_dest_spk(args):
    try:
        spk = btc_htlc_mod.script_pubkey_from_address(args.dest_address)
    except BtcHtlcError as e:
        raise SystemExit(f"btc-htlc: bad --dest-address: {e}")
    try:
        _hrp, _ver, _prog = btc_htlc_mod.bech32_decode(args.dest_address)
    except BtcHtlcError as e:
        raise SystemExit(f"btc-htlc: bad --dest-address: {e}")
    want = btc_htlc_mod.hrp_for_network(args.network)
    if _hrp != want:
        raise SystemExit(
            f"btc-htlc: --dest-address is on hrp {_hrp!r}, but "
            f"--network {args.network} wants {want!r}")
    return spk


def cmd_wallet_btc_htlc_show(args):
    try:
        claim_pub = _btc_parse_hex_arg(args.claim_pubkey, "claim-pubkey",
                                       33)
        refund_pub = _btc_parse_hex_arg(args.refund_pubkey,
                                        "refund-pubkey", 33)
        secret_hash = _btc_parse_hex_arg(args.secret_hash, "secret-hash",
                                         32)
        lock = btc_htlc_mod.build_lock(claim_pub, refund_pub, secret_hash,
                                       args.timeout, args.network)
    except BtcHtlcError as e:
        raise SystemExit(f"btc-htlc show: {e}")
    print(f"BTC HTLC P2WSH address ({args.network}): {lock['address']}")
    print(f"scriptPubKey: {lock['script_pubkey_hex']}")
    print(f"witness script: {lock['witness_script_hex']}")
    print(f"secret hash: {lock['secret_hash']}")
    print(f"timeout (refund at BTC height >=): {lock['timeout']}")
    print("Fund it with `wallet btc-htlc lock`. The secret stays with")
    print("the claimer; only its hash is in the lock.")


def cmd_wallet_btc_htlc_create(args):
    w, pw = _load_wallet(args)
    try:
        if args.secret:
            secret = _btc_parse_hex_arg(args.secret, "secret", 32)
        else:
            import secrets as _s
            secret = _s.token_bytes(32)
            print("generated secret (show once — give it to the claimer "
                  "out of band):")
            print(f"  {secret.hex()}")
        claim_pub = _btc_parse_hex_arg(args.claim_pubkey, "claim-pubkey",
                                       33)
        refund_pub = _btc_parse_hex_arg(args.refund_pubkey,
                                        "refund-pubkey", 33)
        secret_hash = btc_htlc_mod.secret_hash_of(secret)
        lock = btc_htlc_mod.build_lock(claim_pub, refund_pub, secret_hash,
                                       args.timeout, args.network)
    except BtcHtlcError as e:
        raise SystemExit(f"btc-htlc create: {e}")
    w.record_lock(_btc_lock_record(lock), pw)
    print(f"BTC HTLC P2WSH address ({args.network}): {lock['address']}")
    print(f"scriptPubKey: {lock['script_pubkey_hex']}")
    print(f"witness script: {lock['witness_script_hex']}")
    print(f"secret hash: {lock['secret_hash']}")
    print(f"timeout (refund at BTC height >=): {lock['timeout']}")
    print("Recorded in the wallet lock book. Fund it with "
          "`wallet btc-htlc lock --utxo TXID:VOUT ...`.")


def cmd_wallet_btc_htlc_lock(args):
    w, pw = _load_wallet(args)
    try:
        txid, vout = _parse_utxo_ref(args.utxo)
        if args.utxo_value is None or args.utxo_scriptpubkey is None:
            raise SystemExit("btc-htlc lock needs --utxo-value SATS and "
                             "--utxo-scriptpubkey HEX (the wallet does "
                             "not scan Bitcoin for the funding UTXO)")
        claim_pub = _btc_parse_hex_arg(args.claim_pubkey, "claim-pubkey",
                                       33)
        refund_pub = _btc_parse_hex_arg(args.refund_pubkey,
                                        "refund-pubkey", 33)
        if args.secret_hash:
            secret_hash = _btc_parse_hex_arg(args.secret_hash,
                                             "secret-hash", 32)
        elif args.secret:
            secret = _btc_parse_hex_arg(args.secret, "secret", 32)
            secret_hash = btc_htlc_mod.secret_hash_of(secret)
        else:
            raise SystemExit("btc-htlc lock needs --secret-hash HEX "
                             "(or --secret HEX to derive it)")
        from .keys import priv_to_pub_compressed
        idx = args.change_index
        if idx is None:
            idx = w._data["next_change"]
        change_pub = priv_to_pub_compressed(w.change_priv(idx))
        utxo = {"txid": txid, "vout": vout, "value": args.utxo_value,
                "script_pubkey": args.utxo_scriptpubkey}
        signal = _btc_signal_args(args)
        res = btc_htlc_mod.build_btc_htlc_lock(
            [utxo], _btc_pub_to_priv(w), args.amount, claim_pub,
            refund_pub, secret_hash, args.timeout, change_pub,
            fee_rate=args.fee_rate, network=args.network,
            signal=signal)
    except BtcHtlcError as e:
        raise SystemExit(f"btc-htlc lock refused: {e}")
    w.next_change(pw)  # advance the change counter on success only
    w.record_lock(_btc_lock_record(res["lock"], res["txid"]), pw)
    if args.save:
        doc = {"network": "bitcoin", "raw_hex": res["raw_hex"],
               "txid": res["txid"], "wtxid": res["wtxid"],
               "fee": res["fee"], "vsize": res["vsize"],
               "psbt": res["psbt"], "validated": True,
               "inputs": res["inputs"], "outputs": res["outputs"],
               "lock": res["lock"]}
        with open(args.save, "w") as f:
            json.dump(doc, f, indent=2)
        os.chmod(args.save, 0o600)
        print(f"saved (0600): {args.save} — broadcast it with "
              f"`wallet broadcast --file {args.save} --network bitcoin "
              f"--yes`")
    print(f"BTC HTLC funded: {res['address']} ({args.network})")
    print(f"timeout (refund at BTC height >=): {args.timeout}")
    _print_btc_signal(res)
    _print_btc_tx_result(res)


def _btc_spend_common(args, wallet):
    """Shared claim/refund setup: (script, signer priv, dest spk)."""
    txid, vout = _parse_utxo_ref(args.utxo)
    if args.utxo_value is None:
        raise SystemExit("btc-htlc claim/refund needs --utxo-value SATS "
                         "(the wallet does not scan Bitcoin for the "
                         "HTLC UTXO)")
    script = _btc_find_record(wallet, args)
    try:
        parsed = btc_htlc_mod.parse_witness_script(script)
    except BtcHtlcError as e:
        raise SystemExit(f"btc-htlc: bad witness script: {e}")
    dest_spk = _btc_dest_spk(args)
    return txid, vout, script, parsed, dest_spk


def cmd_wallet_btc_htlc_claim(args):
    w, _pw = _load_wallet(args)
    txid, vout, script, parsed, dest_spk = _btc_spend_common(args, w)
    try:
        secret = _btc_parse_hex_arg(args.secret, "secret", 32)
        from .keys import priv_to_pub_compressed
        claim_priv = None
        for pub, priv in _btc_pub_to_priv(w).items():
            if pub == parsed["claim_pubkey"]:
                claim_priv = priv
                break
        if claim_priv is None:
            raise SystemExit("claim key is not a wallet key")
        res = btc_htlc_mod.build_btc_htlc_claim(
            txid, vout, args.utxo_value, dest_spk, secret, script,
            claim_priv, fee=args.fee, fee_rate=args.fee_rate)
    except BtcHtlcError as e:
        raise SystemExit(f"btc-htlc claim refused: {e}")
    if args.save:
        _btc_save_spend(args, res)
    print("BTC HTLC claim (secret + claim key):")
    _print_btc_tx_result(res)


def cmd_wallet_btc_htlc_refund(args):
    w, _pw = _load_wallet(args)
    txid, vout, script, parsed, dest_spk = _btc_spend_common(args, w)
    try:
        from .keys import priv_to_pub_compressed
        refund_priv = None
        for pub, priv in _btc_pub_to_priv(w).items():
            if pub == parsed["refund_pubkey"]:
                refund_priv = priv
                break
        if refund_priv is None:
            raise SystemExit("refund key is not a wallet key")
        res = btc_htlc_mod.build_btc_htlc_refund(
            txid, vout, args.utxo_value, dest_spk, script,
            refund_priv, args.btc_height, fee=args.fee,
            fee_rate=args.fee_rate)
    except BtcHtlcError as e:
        raise SystemExit(f"btc-htlc refund refused: {e}")
    if args.save:
        _btc_save_spend(args, res)
    print(f"BTC HTLC refund (refund key, height {args.btc_height} >= "
          f"timeout {parsed['timeout']}):")
    _print_btc_tx_result(res)


def _btc_save_spend(args, res):
    doc = {"network": "bitcoin", "raw_hex": res["raw_hex"],
           "txid": res["txid"], "wtxid": res["wtxid"],
           "fee": res["fee"], "vsize": res["vsize"],
           "psbt": res["psbt"], "validated": True,
           "inputs": res["inputs"], "outputs": res["outputs"],
           "branch": res["branch"]}
    with open(args.save, "w") as f:
        json.dump(doc, f, indent=2)
    os.chmod(args.save, 0o600)
    print(f"saved (0600): {args.save} — broadcast it with "
          f"`wallet broadcast --file {args.save} --network bitcoin "
          f"--yes`")


# ------------------------------------------------------- atomic swap
# Cross-chain atomic swap: EXCAL HTLC leg + BTC P2WSH HTLC leg, one
# shared secret hash, staggered timeouts (BTC expires first). The
# maker locks EXCAL and claims BTC; the taker locks BTC and claims
# EXCAL. State lives in the wallet's "swaps" book (atomic_swap.py);
# the secret is NEVER stored — whoever needs it passes --secret.
# Nothing here broadcasts. EXCAL claim/refund build the spend entry
# from the swap record + an explicit --utxo (the fork validator
# checks the spend locally; broadcast.py re-checks the UTXO is
# unspent on the live node before submitting) — the wallet's watched
# set only covers receive/change locks, so the live-node UTXO lookup
# used by `wallet htlc claim` cannot see an HTLC UTXO.
def _swap_hex(s, name, want_len):
    try:
        b = bytes.fromhex(s)
    except ValueError:
        raise SystemExit(f"swap: --{name} must be hex")
    if len(b) != want_len:
        raise SystemExit(f"swap: --{name} must be {want_len} bytes "
                         f"(got {len(b)})")
    return b


def _swap_own_pubkey(wallet):
    """The wallet's identity key for a swap: receive index 0 (the
    legacy key for a legacy wallet)."""
    from .keys import priv_to_pub_compressed
    return priv_to_pub_compressed(wallet.receive_priv(0))


def _swap_load(args):
    w, pw = _load_wallet(args)
    rec = w.find_swap(args.swap_id)
    if rec is None:
        raise SystemExit(f"swap: no swap {args.swap_id} in this wallet "
                         f"(`wallet swap create` first)")
    return w, pw, rec


def _swap_require_role(rec, role):
    if rec["role"] != role:
        raise SystemExit(
            f"swap: this swap belongs to the {rec['role']} — the "
            f"{role} command does not apply to it")


def _swap_check_move(rec, to_state, role, fork_height=None,
                     btc_height=None):
    """Validate a transition without committing it (the build runs
    between the check and the commit, so a refused move never leaves
    a built tx behind)."""
    try:
        swap_mod.transition(rec, to_state, role=role,
                            fork_height=fork_height,
                            btc_height=btc_height)
    except SwapError as e:
        raise SystemExit(f"swap: {e}")


def _swap_commit(w, pw, rec, to_state, role, fork_height=None,
                 btc_height=None, leg=None, updates=None):
    new = swap_mod.transition(rec, to_state, role=role,
                              fork_height=fork_height,
                              btc_height=btc_height)
    if leg and updates:
        new[leg].update(updates)
    w.update_swap(rec["swap_id"], new, pw)
    return new


def _swap_print(rec):
    print(f"swap: {rec['swap_id']}  role: {rec['role']}  "
          f"state: {rec['state']}")
    print(f"secret hash: {rec['secret_hash']}")
    print(f"amounts: {rec['excal_amount']:,} swords EXCAL <-> "
          f"{rec['btc_amount']:,} sats BTC")
    print(f"maker: {rec['maker_pubkey']}")
    print(f"taker: {rec['taker_pubkey']}")
    print(f"timeouts: EXCAL fork {rec['excal_timeout']} / "
          f"BTC {rec['btc_timeout']}")
    leg_kind = rec.get("excal_leg_kind", "htlc")
    print(f"EXCAL leg ({leg_kind.upper()}): lock {rec['excal']['lock']}")
    if leg_kind == "qhtlc":
        print(f"  claim root: {rec['excal']['claim_root']}")
        print(f"  refund root: {rec['excal']['refund_root']}")
    print(f"  funding: {rec['excal']['funding_txid']}:"
          f"{rec['excal']['funding_vout']}  "
          f"claim: {rec['excal']['claim_txid']}  "
          f"refund: {rec['excal']['refund_txid']}")
    print(f"BTC leg: {rec['btc']['address']} ({rec['network']})")
    print(f"  funding: {rec['btc']['funding_txid']}:"
          f"{rec['btc']['funding_vout']}  "
          f"claim: {rec['btc']['claim_txid']}  "
          f"refund: {rec['btc']['refund_txid']}")


def _swap_record_htlc_lock(w, pw, rec):
    """Also record the EXCAL leg in the locks book (if absent) so
    `wallet htlc` / `wallet qhtlc` can see the same lock the swap
    tracks. The recorded kind follows the leg kind."""
    if w.find_lock(rec["excal"]["lock"]) is None:
        if rec.get("excal_leg_kind", "htlc") == "qhtlc":
            w.record_lock(
                {"kind": "qhtlc", "lock": rec["excal"]["lock"],
                 "descriptor": rec["excal"]["descriptor"],
                 "timeout": rec["excal_timeout"],
                 "claim_root": rec["excal"]["claim_root"],
                 "refund_root": rec["excal"]["refund_root"]}, pw)
        else:
            w.record_lock(
                {"kind": "htlc", "lock": rec["excal"]["lock"],
                 "descriptor": rec["excal"]["descriptor"],
                 "timeout": rec["excal_timeout"],
                 "claim_pubkey": rec["taker_pubkey"],
                 "refund_pubkey": rec["maker_pubkey"]}, pw)


def _btc_signal_args(args):
    """The watcher-signal dict for a BTC funding build, or None.

    Opt-in: --signal-tag is what turns it on (with --delivery-pubkey
    required). The OP_RETURN carries tag + delivery pubkey and a
    1,000-sat payment goes to the signal address, so the swap
    watcher sees the funding and delivers the encrypted claim seed.
    Without it, a wallet-built funding tx is invisible to the
    watcher — fine for a fresh HTLC swap, fatal for a QHTLC lot."""
    if not getattr(args, "signal_tag", None):
        return None
    if not getattr(args, "delivery_pubkey", None):
        raise SystemExit("watcher signal needs --delivery-pubkey HEX "
                         "(the taker's fresh delivery pubkey) with "
                         "--signal-tag")
    try:
        delivery_pub = bytes.fromhex(args.delivery_pubkey)
    except ValueError:
        raise SystemExit("watcher signal: --delivery-pubkey must be hex")
    if len(delivery_pub) != 33:
        raise SystemExit("watcher signal: --delivery-pubkey must be "
                         "33 bytes (compressed pubkey)")
    return {"tag": args.signal_tag.encode(),
            "delivery_pubkey": delivery_pub,
            "signal_address": getattr(
                args, "signal_address", None)
            or btc_htlc_mod.DEFAULT_SIGNAL_ADDRESS,
            "signal_sats": getattr(args, "signal_sats", 1000) or 1000}


def _print_btc_signal(res):
    """Print the watcher signal a funding tx carries (if any)."""
    sig = res.get("signal") if isinstance(res, dict) else None
    if not sig:
        return
    print(f"watcher signal: OP_RETURN tag "
          f"{bytes.fromhex(sig['tag']).decode(errors='replace')} + "
          f"delivery pubkey {sig['delivery_pubkey']}; "
          f"{sig['signal_sats']} sats to {sig['signal_address']}")
    print("Post the witness script for this funding on the lot's "
          "GitHub issue — the watcher verifies it, then publishes "
          "the encrypted claim seed.")


def _swap_network(args, rec):
    if args.network != rec["network"]:
        raise SystemExit(
            f"swap: --network {args.network} does not match the swap's "
            f"network {rec['network']}")
    return rec["network"]


def _swap_fork_entry(rec):
    """The funded EXCAL HTLC UTXO, from the record (explicit supply —
    see the section comment)."""
    return {"txid": rec["excal"]["funding_txid"],
            "vout": rec["excal"]["funding_vout"],
            "value": rec["excal_amount"],
            "lock": rec["excal"]["lock"],
            "coinbase": False, "cb_h": 0, "mature": True}


def cmd_wallet_swap_create(args):
    w, pw = _load_wallet(args)
    try:
        counterparty = _swap_hex(args.counterparty_pubkey,
                                 "counterparty-pubkey", 33)
        own = _swap_own_pubkey(w)
        if args.role == "maker":
            maker_pub, taker_pub = own, counterparty
        else:
            maker_pub, taker_pub = counterparty, own
        secret = secret_hash = None
        if args.role == "maker":
            if args.secret_hash:
                raise SystemExit("swap create (maker): do not pass "
                                 "--secret-hash — the maker creates "
                                 "the secret")
            secret = (_swap_hex(args.secret, "secret", 32)
                      if args.secret else swap_mod.new_secret())
        else:
            if args.secret:
                raise SystemExit("swap create (taker): pass "
                                 "--secret-hash, not --secret")
            if not args.secret_hash:
                raise SystemExit("swap create (taker): --secret-hash "
                                 "is required")
            secret_hash = _swap_hex(args.secret_hash, "secret-hash", 32)
        leg_kind = getattr(args, "excal_leg", "htlc")
        claim_root = refund_root = None
        if leg_kind == "qhtlc":
            if not args.claim_root or not args.refund_root:
                raise SystemExit("swap create (QHTLC leg): --claim-root "
                                 "and --refund-root are required (32-byte "
                                 "Trifold roots, hex)")
            claim_root = _swap_hex(args.claim_root, "claim-root", 32)
            refund_root = _swap_hex(args.refund_root, "refund-root", 32)
        rec = swap_mod.new_swap(
            args.role, maker_pub, taker_pub, args.excal_amount,
            args.btc_amount, args.excal_timeout, args.btc_timeout,
            args.fork_height, args.btc_height, secret=secret,
            secret_hash=secret_hash, network=args.network,
            excal_leg_kind=leg_kind, claim_root=claim_root,
            refund_root=refund_root)
    except SwapError as e:
        raise SystemExit(f"swap create refused: {e}")
    if w.find_swap(rec["swap_id"]) is not None:
        raise SystemExit(f"swap create refused: swap {rec['swap_id']} "
                         f"already exists in this wallet")
    w.record_swap(rec, pw)
    _swap_record_htlc_lock(w, pw, rec)
    if args.role == "maker":
        print("generated secret (show once — keep it: the taker learns "
              "it only when you claim the BTC leg):")
        print(f"  {secret.hex()}")
    else:
        print("taker swap: the secret is unknown to you until the maker "
              "claims the BTC leg and reveals it on chain.")
    _swap_print(rec)
    if args.role == "maker":
        print("next: `wallet swap fund-excal --swap-id "
              f"{rec['swap_id']}` — then the taker funds the BTC leg.")
    else:
        print("next: wait for the maker's EXCAL funding, then "
              "`wallet swap note-excal-funded --swap-id "
              f"{rec['swap_id']} --raw-hex <funding tx>`.")


def cmd_wallet_swap_show(args):
    _w, _pw, rec = _swap_load(args)
    _swap_print(rec)


def cmd_wallet_swap_list(args):
    w, _pw = _load_wallet(args)
    swaps = w._data.get("swaps", [])
    if not swaps:
        print("no swaps in this wallet")
        return
    for rec in swaps:
        print(f"{rec['swap_id']}  {rec['role']:<6} {rec['state']:<15} "
              f"{rec['excal_amount']:,} swords <-> "
              f"{rec['btc_amount']:,} sats  "
              f"EXCAL@{rec['excal_timeout']} BTC@{rec['btc_timeout']}")


def cmd_wallet_swap_fund_excal(args):
    w, pw, rec = _swap_load(args)
    _swap_require_role(rec, "maker")
    _swap_check_move(rec, "excal-funded", role="maker")
    utxos, height, source = _utxos_for_send(args, w)
    print(f"UTXO source: {source}; validating at height {height}")
    idx = w._data["next_change"]
    change_lock = bytes.fromhex(w.change_address(idx))
    try:
        res = swap_mod.build_excal_funding(
            rec, utxos, _lock_to_priv(w), change_lock,
            fee_rate=args.fee_rate, height=height)
    except SwapError as e:
        raise SystemExit(f"swap fund-excal refused: {e}")
    w.next_change(pw)  # advance the change counter on success only
    vout = next(i for i, o in enumerate(res["outputs"])
                if o["lock"] == rec["excal"]["lock"])
    _swap_commit(w, pw, rec, "excal-funded", role="maker", leg="excal",
                 updates={"funding_txid": res["txid"],
                          "funding_vout": vout})
    if args.save:
        doc = {"network": "fork", "raw_hex": res["raw_hex"],
               "txid": res["txid"], "fee": res["fee"],
               "validated": True,
               "validated_at_height": res["validated_at_height"],
               "inputs": res["inputs"], "outputs": res["outputs"]}
        with open(args.save, "w") as f:
            json.dump(doc, f, indent=2)
        os.chmod(args.save, 0o600)
        print(f"saved (0600): {args.save} — broadcast it with "
              f"`wallet broadcast --file {args.save} --network fork "
              f"--yes`")
    print(f"EXCAL leg funded: {res['txid']}:{vout} "
          f"({rec['excal_amount']:,} swords to the HTLC lock)")
    _print_tx_result(res)


def cmd_wallet_swap_note_excal_funded(args):
    w, pw, rec = _swap_load(args)
    # Either role: the maker records their own funding (built by
    # fund-excal or by `wallet send --to <lock>`); the taker records
    # the counterparty's funding after verifying it. The raw tx is
    # verified against the swap lock + amount either way.
    _swap_check_move(rec, "excal-funded", role=rec["role"])
    try:
        found = swap_mod.verify_excal_funding_raw(rec, args.raw_hex)
    except SwapError as e:
        raise SystemExit(f"swap note-excal-funded refused: {e}")
    _swap_record_htlc_lock(w, pw, rec)
    new = _swap_commit(w, pw, rec, "excal-funded", role=rec["role"],
                       leg="excal",
                       updates={"funding_txid": found["txid"],
                                "funding_vout": found["vout"]})
    print(f"EXCAL funding verified: {found['txid']}:{found['vout']} "
          f"pays {rec['excal_amount']:,} swords to the swap lock")
    _swap_print(new)


def cmd_wallet_swap_fund_btc(args):
    w, pw, rec = _swap_load(args)
    _swap_require_role(rec, "taker")
    _swap_check_move(rec, "btc-funded", role="taker")
    try:
        txid, vout = _parse_utxo_ref(args.utxo)
        if args.utxo_value is None or args.utxo_scriptpubkey is None:
            raise SystemExit("swap fund-btc needs --utxo-value SATS and "
                             "--utxo-scriptpubkey HEX (the wallet does "
                             "not scan Bitcoin for the funding UTXO)")
        from .keys import priv_to_pub_compressed
        idx = args.change_index
        if idx is None:
            idx = w._data["next_change"]
        change_pub = priv_to_pub_compressed(w.change_priv(idx))
        utxo = {"txid": txid, "vout": vout, "value": args.utxo_value,
                "script_pubkey": args.utxo_scriptpubkey}
        signal = _btc_signal_args(args)
        res = swap_mod.build_btc_funding(
            rec, utxo, _btc_pub_to_priv(w), change_pub,
            fee_rate=args.fee_rate, network=rec["network"],
            signal=signal)
    except SwapError as e:
        raise SystemExit(f"swap fund-btc refused: {e}")
    w.next_change(pw)  # advance the change counter on success only
    vout2 = next(i for i, o in enumerate(res["outputs"])
                 if o["script_pubkey"] == rec["btc"]["script_pubkey"])
    _swap_commit(w, pw, rec, "btc-funded", role="taker", leg="btc",
                 updates={"funding_txid": res["txid"],
                          "funding_vout": vout2})
    if args.save:
        doc = {"network": "bitcoin", "raw_hex": res["raw_hex"],
               "txid": res["txid"], "wtxid": res["wtxid"],
               "fee": res["fee"], "vsize": res["vsize"],
               "psbt": res["psbt"], "validated": True,
               "inputs": res["inputs"], "outputs": res["outputs"],
               "lock": res["lock"]}
        with open(args.save, "w") as f:
            json.dump(doc, f, indent=2)
        os.chmod(args.save, 0o600)
        print(f"saved (0600): {args.save} — broadcast it with "
              f"`wallet broadcast --file {args.save} --network bitcoin "
              f"--yes`")
    print(f"BTC leg funded: {res['txid']}:{vout2} "
          f"({rec['btc_amount']:,} sats to {rec['btc']['address']})")
    _print_btc_signal(res)
    _print_btc_tx_result(res)


def cmd_wallet_swap_note_btc_funded(args):
    w, pw, rec = _swap_load(args)
    # Either role: the maker records the counterparty's funding after
    # verifying it; the taker records their own (built by fund-btc or
    # by `wallet btc-htlc lock`). The raw tx is verified against the
    # swap P2WSH address + amount either way.
    _swap_check_move(rec, "btc-funded", role=rec["role"])
    try:
        found = swap_mod.verify_btc_funding_raw(rec, args.raw_hex)
    except SwapError as e:
        raise SystemExit(f"swap note-btc-funded refused: {e}")
    new = _swap_commit(w, pw, rec, "btc-funded", role=rec["role"],
                       leg="btc",
                       updates={"funding_txid": found["txid"],
                                "funding_vout": found["vout"]})
    print(f"BTC funding verified: {found['txid']}:{found['vout']} "
          f"pays {rec['btc_amount']:,} sats to "
          f"{rec['btc']['address']}")
    _swap_print(new)


def cmd_wallet_swap_claim_btc(args):
    w, pw, rec = _swap_load(args)
    _swap_require_role(rec, "maker")
    _swap_check_move(rec, "btc-claimed", role="maker")
    _swap_network(args, rec)
    try:
        secret = _swap_hex(args.secret, "secret", 32)
        dest_spk = _btc_dest_spk(args)
        res = swap_mod.build_btc_claim(
            rec, secret, dest_spk, _btc_pub_to_priv(w),
            fee_rate=args.fee_rate)
    except SwapError as e:
        raise SystemExit(f"swap claim-btc refused: {e}")
    _swap_commit(w, pw, rec, "btc-claimed", role="maker", leg="btc",
                 updates={"claim_txid": res["txid"]})
    if args.save:
        _btc_save_spend(args, res)
    print("BTC leg claimed — the secret is now public on chain; the "
          "taker claims the EXCAL leg with it next.")
    _print_btc_tx_result(res)


def cmd_wallet_swap_note_btc_claimed(args):
    w, pw, rec = _swap_load(args)
    _swap_require_role(rec, "taker")
    _swap_check_move(rec, "btc-claimed", role="taker")
    try:
        found = swap_mod.verify_btc_claim_raw(rec, args.raw_hex)
    except SwapError as e:
        raise SystemExit(f"swap note-btc-claimed refused: {e}")
    _swap_commit(w, pw, rec, "btc-claimed", role="taker", leg="btc",
                 updates={"claim_txid": found["txid"]})
    print(f"BTC leg claimed by the maker: {found['txid']} — the secret "
          f"is now public on chain:")
    print(f"  {found['secret'].hex()}")
    print("Claim the EXCAL leg with it: `wallet swap claim-excal "
          f"--swap-id {rec['swap_id']} --secret <above> ...`")


def cmd_wallet_swap_claim_excal(args):
    w, pw, rec = _swap_load(args)
    _swap_require_role(rec, "taker")
    _swap_check_move(rec, "complete", role="taker")
    try:
        txid, vout = _parse_utxo_ref(args.utxo)
        dest_lock = parse_lock_hex(args.dest)
        secret = _swap_hex(args.secret, "secret", 32)
        entry = _swap_fork_entry(rec)
        if entry["txid"] != txid or entry["vout"] != vout:
            raise SystemExit(
                f"swap claim-excal: --utxo {txid}:{vout} is not the "
                f"recorded EXCAL funding "
                f"{entry['txid']}:{entry['vout']}")
        kind = rec.get("excal_leg_kind", "htlc")
        trifold_key = None
        claim_priv = None
        if kind == "qhtlc":
            # The claim root belongs to the maker's seed, delivered
            # encrypted by the watcher — NOT to this wallet. The
            # seed is supplied per claim and never stored.
            if getattr(args, "claim_seed", None):
                try:
                    seed = bytes.fromhex(args.claim_seed)
                except ValueError:
                    raise SystemExit("swap claim-excal: --claim-seed "
                                     "must be hex")
                trifold_key = swap_mod.trifold_key_for_root(
                    seed, bytes.fromhex(rec["excal"]["claim_root"]),
                    state_dir=w.datadir)
            else:
                raise SystemExit(
                    "swap claim-excal (QHTLC leg): --claim-seed is "
                    "required — the decrypted claim seed from the "
                    "watcher (the wallet does not hold the maker's "
                    "seed)")
        else:
            if getattr(args, "claim_seed", None):
                raise SystemExit("swap claim-excal: --claim-seed "
                                 "applies to QHTLC legs only (this "
                                 "swap's EXCAL leg is HTLC)")
            for pub, priv in _btc_pub_to_priv(w).items():
                if pub == bytes.fromhex(rec["taker_pubkey"]):
                    claim_priv = priv
                    break
            if claim_priv is None:
                raise SystemExit("swap claim-excal: claim key (taker) is "
                                 "not a wallet key")
        res = swap_mod.build_excal_claim(
            rec, entry, dest_lock, args.fee, secret, claim_priv,
            args.fork_height + 1, trifold_key=trifold_key)
    except SwapError as e:
        raise SystemExit(f"swap claim-excal refused: {e}")
    _swap_commit(w, pw, rec, "complete", role="taker", leg="excal",
                 updates={"claim_txid": res["txid"]})
    print("EXCAL leg claimed — swap complete.")
    _print_tx_result(res)


def cmd_wallet_swap_note_excal_claimed(args):
    w, pw, rec = _swap_load(args)
    _swap_require_role(rec, "maker")
    _swap_check_move(rec, "complete", role="maker")
    _swap_commit(w, pw, rec, "complete", role="maker", leg="excal",
                 updates={"claim_txid": args.txid})
    print(f"EXCAL leg claimed by the taker: {args.txid} — swap "
          f"complete.")


def cmd_wallet_swap_refund_excal(args):
    w, pw, rec = _swap_load(args)
    _swap_require_role(rec, "maker")
    _swap_check_move(rec, "excal-refunded", role="maker",
                     fork_height=args.fork_height,
                     btc_height=args.btc_height)
    try:
        txid, vout = _parse_utxo_ref(args.utxo)
        dest_lock = parse_lock_hex(args.dest)
        entry = _swap_fork_entry(rec)
        if entry["txid"] != txid or entry["vout"] != vout:
            raise SystemExit(
                f"swap refund-excal: --utxo {txid}:{vout} is not the "
                f"recorded EXCAL funding "
                f"{entry['txid']}:{entry['vout']}")
        kind = rec.get("excal_leg_kind", "htlc")
        trifold_key = None
        refund_priv = None
        if kind == "qhtlc":
            if getattr(args, "refund_seed", None):
                try:
                    seed = bytes.fromhex(args.refund_seed)
                except ValueError:
                    raise SystemExit("swap refund-excal: --refund-seed "
                                     "must be hex")
                trifold_key = swap_mod.trifold_key_for_root(
                    seed, bytes.fromhex(rec["excal"]["refund_root"]),
                    state_dir=w.datadir)
            else:
                raise SystemExit(
                    "swap refund-excal (QHTLC leg): --refund-seed is "
                    "required — the maker's refund seed (the wallet "
                    "does not hold it)")
        else:
            if getattr(args, "refund_seed", None):
                raise SystemExit("swap refund-excal: --refund-seed "
                                 "applies to QHTLC legs only (this "
                                 "swap's EXCAL leg is HTLC)")
            for pub, priv in _btc_pub_to_priv(w).items():
                if pub == bytes.fromhex(rec["maker_pubkey"]):
                    refund_priv = priv
                    break
            if refund_priv is None:
                raise SystemExit("swap refund-excal: refund key (maker) "
                                 "is not a wallet key")
        res = swap_mod.build_excal_refund(
            rec, entry, dest_lock, args.fee, refund_priv,
            args.fork_height + 1, trifold_key=trifold_key)
    except SwapError as e:
        raise SystemExit(f"swap refund-excal refused: {e}")
    _swap_commit(w, pw, rec, "excal-refunded", role="maker",
                 fork_height=args.fork_height,
                 btc_height=args.btc_height, leg="excal",
                 updates={"refund_txid": res["txid"]})
    print(f"EXCAL leg refunded (fork height {args.fork_height} >= "
          f"timeout {rec['excal_timeout']}; BTC leg expired first).")
    _print_tx_result(res)


def cmd_wallet_swap_refund_btc(args):
    w, pw, rec = _swap_load(args)
    _swap_require_role(rec, "taker")
    _swap_check_move(rec, "btc-refunded", role="taker",
                     btc_height=args.btc_height)
    _swap_network(args, rec)
    try:
        dest_spk = _btc_dest_spk(args)
        res = swap_mod.build_btc_refund(
            rec, dest_spk, _btc_pub_to_priv(w), fee_rate=args.fee_rate,
            current_height=args.btc_height)
    except SwapError as e:
        raise SystemExit(f"swap refund-btc refused: {e}")
    _swap_commit(w, pw, rec, "btc-refunded", role="taker", leg="btc",
                 updates={"refund_txid": res["txid"]})
    if args.save:
        _btc_save_spend(args, res)
    print(f"BTC leg refunded (BTC height {args.btc_height} >= timeout "
          f"{rec['btc_timeout']}).")
    _print_btc_tx_result(res)


def cmd_wallet_qhtlc_create(args):
    w, pw = _load_wallet(args)
    try:
        secret = bytes.fromhex(args.secret) if args.secret else None
        if secret is None:
            import secrets as _s
            secret = _s.token_bytes(32)
            print("generated secret (show once — give it to the claimer "
                  "out of band):")
            print(f"  {secret.hex()}")
        claim_root = bytes.fromhex(args.claim_root)
        refund_root = bytes.fromhex(args.refund_root)
        lock, desc = qhtlc_lock(secret, claim_root, refund_root,
                                args.timeout)
    except (ValueError, TxBuildError) as e:
        raise SystemExit(f"qhtlc create: {e}")
    w.record_lock({"kind": "qhtlc", "lock": lock.hex(),
                   "descriptor": desc.hex(), "timeout": args.timeout,
                   "claim_root": claim_root.hex(),
                   "refund_root": refund_root.hex()}, pw)
    print(f"QHTLC lock: {lock.hex()}")
    print(f"descriptor: {desc.hex()}")
    print(f"timeout (refund at height >=): {args.timeout}")
    print("Hash-only end to end: no curve key anywhere in this lock.")


def _qhtlc_spend(args, mode):
    w, _pw = _load_wallet(args)
    txid, vout = _parse_utxo_ref(args.utxo)
    entry = _find_wallet_utxo(args, w, txid, vout)
    rec = w.find_lock(entry["lock"])
    if rec is None:
        raise SystemExit("no QHTLC descriptor recorded for this lock")
    try:
        dest_lock = parse_lock_hex(args.dest)
        desc = bytes.fromhex(rec["descriptor"])
        height = entry["tip_height"] + 1
        # The signing key: the wallet's own Trifold key by default,
        # or a Trifold key from an externally supplied seed (a
        # claim/refund seed delivered by the swap watcher for a lot
        # whose roots are not this wallet's — the seed is used for
        # this one spend and never stored).
        seed_arg = (args.claim_seed if mode == "claim"
                    else args.refund_seed)
        if seed_arg:
            try:
                seed = bytes.fromhex(seed_arg)
            except ValueError:
                raise SystemExit(f"qhtlc {mode}: --{mode}-seed must "
                                 f"be hex")
            from txscript import parse_qhtlc_descriptor
            want_root = parse_qhtlc_descriptor(desc)[
                "claim_root" if mode == "claim" else "refund_root"]
            key = swap_mod.trifold_key_for_root(
                seed, want_root, state_dir=w.datadir)
        else:
            key = w.trifold_key()
        if mode == "claim":
            secret = bytes.fromhex(args.secret)
            res = build_qhtlc_claim(entry, dest_lock, args.fee, secret,
                                    desc, key, height)
        else:
            res = build_qhtlc_refund(entry, dest_lock, args.fee, desc,
                                     key, height)
    except (ValueError, TxBuildError, RuntimeError, SwapError) as e:
        raise SystemExit(f"qhtlc {mode} refused: {e}")
    _print_tx_result(res)


def cmd_wallet_pqh_address(args):
    w, _pw = _load_wallet(args)
    key = w.trifold_key()
    print(f"Trifold root: {key.root.hex()}")
    print(f"PQH lock:     {w.pqh_address()}")
    print(f"leaves: {key.capacity}, next leaf: {key.next_index} "
          f"(forward-only, one-time)")


def cmd_wallet_pqh_spend(args):
    if not args.yes:
        print("REFUSED without --yes. A PQH spend records its one-time")
        print("leaf in the spent-leaf registry BEFORE signing: if local")
        print("validation then fails, that leaf is burned (never reusable).")
        print("Re-run with --yes to accept that.")
        raise SystemExit(1)
    w, _pw = _load_wallet(args)
    txid, vout = _parse_utxo_ref(args.utxo)
    entry = _find_wallet_utxo(args, w, txid, vout)
    try:
        dest_lock = parse_lock_hex(args.dest)
        height = entry["tip_height"] + 1
        res = build_pqh_spend(entry, dest_lock, args.fee,
                              w.trifold_key(), height)
    except (ValueError, TxBuildError, RuntimeError) as e:
        raise SystemExit(f"pqh spend refused: {e}")
    _print_tx_result(res)


def cmd_wallet_knot_lock(args):
    w, pw = _load_wallet(args)
    led = _ledger(args)
    try:
        tip_h, _th = led.rpc.tip()
    except RpcError:
        tip_h = led._load_cache().get("tip_height", -1)
    print("TEST-CHAIN ONLY. KNOT is staged, not activated on the live")
    print(f"fork (activation {100000}, tip {tip_h}). This tx validates")
    print("only at height 100000 and is NOT broadcastable on the live fork.")
    try:
        amount = parse_amount(args.amount)
        t_star = int(args.t_star, 16) if args.t_star else None
        if t_star is None:
            from knot_wallet import new_t_star
            t_star = new_t_star()
            print("generated t_star (show once — store it in a 0600 file,")
            print("losing it burns the coins):")
            print(f"  {t_star:032x}")
        utxos, height, source = _utxos_for_send(args, w)
        print(f"UTXO source: {source}")
        from .txbuild import select_utxos
        from .keys import address_for_priv
        spendable = [u for u in utxos
                     if u["lock"] in _lock_to_priv(w)]
        selected, _fee = select_utxos(spendable, amount, args.fee_rate)
        funding_priv = _lock_to_priv(w)[selected[0]["lock"]]
        # All funding inputs must share one key (knot_wallet's rule).
        if len({u["lock"] for u in selected}) != 1:
            raise SystemExit("knot lock needs all funding UTXOs from one "
                             "key — use a single-key funding set")
        funding = [{"prev": bytes.fromhex(u["txid"]), "idx": u["vout"],
                    "value": u["value"],
                    "lock": bytes.fromhex(u["lock"])} for u in selected]
        res = build_knot_lock_test(funding, funding_priv, amount,
                                   args.p, args.q, args.n_terms,
                                   args.eps, t_star, args.fee)
    except (ValueError, TxBuildError, RuntimeError) as e:
        raise SystemExit(f"knot lock refused: {e}")
    print(f"KNOT lock: {res['lock'].hex()}")
    print(f"descriptor: {res['descriptor'].hex()}")
    print(f"commitment: {res['commitment'].hex()}")
    print(f"validated at height: {res['validated_at_height']} "
          f"(fee {res['validated_fee']} swords)")
    print(f"raw hex: {res['raw'].hex()}")
    print("TEST-CHAIN ONLY — do not broadcast on the live fork.")


def cmd_wallet_knot_spend(args):
    print("TEST-CHAIN ONLY. KNOT is staged, not activated on the live")
    print("fork. This tx validates only at height 100000 and is NOT")
    print("broadcastable on the live fork.")
    try:
        txid, vout = _parse_utxo_ref(args.utxo)
        lock = bytes.fromhex(args.lock)
        desc = bytes.fromhex(args.descriptor)
        t_star = int(args.t_star, 16)
        dest_lock = parse_lock_hex(args.dest)
        res = build_knot_spend_test(bytes.fromhex(txid), vout,
                                    args.amount, lock, desc, t_star,
                                    dest_lock, args.fee)
    except (ValueError, TxBuildError, RuntimeError) as e:
        raise SystemExit(f"knot spend refused: {e}")
    print(f"txid: {res['txid'] if 'txid' in res else 'n/a'}")
    print(f"validated at height: {res['validated_at_height']} "
          f"(fee {res['validated_fee']} swords)")
    print(f"raw hex: {res['raw'].hex()}")
    print("TEST-CHAIN ONLY — do not broadcast on the live fork.")


# ------------------------------------------------------------------ ledger
def cmd_ledger_sync(args):
    w = None
    locks = None
    if args.wallet:
        try:
            w, _pw = _load_wallet(args)
            locks = _watched(w)
        except SystemExit:
            raise
    led = _ledger(args)
    via = args.via
    if via == "rpc":
        try:
            tip_h, tip_hash = led.rpc.tip()
        except RpcError as e:
            raise SystemExit(f"RPC sync failed: {e}")
        print(f"node tip: height {tip_h}, hash {tip_hash[:16]}…")
        print("RPC sync gives the tip only — balances come from "
              "`wallet balance --via rpc`, history from a local scan.")
        return
    if via == "p2p":
        if locks is None:
            raise SystemExit("p2p sync needs a wallet (--wallet) to know "
                             "which locks to track")
        cache = led._load_cache()
        tip_h = int(cache.get("tip_height", -1))
        tip_hash = cache.get("tip_hash")
        peer = tuple(args.peer.split(":")) if args.peer else None
        if peer is None:
            seeds = p2p_sync.read_seeds()
            if seeds:
                host, port = seeds[0].rsplit(":", 1)
                peer = (host, int(port))
            else:
                peer = p2p_sync.DEFAULT_PEER
        else:
            peer = (peer[0], int(peer[1]))
        print(f"dialing peer {peer[0]}:{peer[1]} (wallet tip {tip_h})…")
        try:
            res = p2p_sync.sync_from_peer(peer, tip_h, tip_hash)
        except p2p_sync.P2PError as e:
            raise SystemExit(f"P2P sync failed: {e}")
        if res["up_to_date"]:
            print(f"up to date: peer tip {res['peer_height']} == "
                  f"wallet tip {tip_h}")
            return
        applied = led.apply_blocks(res["blocks"], tip_h + 1, locks)
        print(f"P2P sync: fetched {res['fetched']} blocks from "
              f"{res['peer']} (header PoW + Merkle verified each)")
        print(f"new tip: height {applied['tip_height']}, "
              f"hash {applied['tip_hash'][:16]}…")
        print("Note: header+merkle verified; full tx validation is the")
        print("full node's job, not the wallet's.")
        return
    if locks is None:
        raise SystemExit("local sync needs a wallet (--wallet) to know "
                         "which locks to track")
    stats = led.sync_local(locks)
    print(f"local scan: {stats['scanned_records']} records read, "
          f"{stats['new_records']} new, tip {stats['tip_height']}"
          + (" (full rescan — tip continuity broke)" if stats["rescan"] else ""))


def cmd_ledger_tip(args):
    led = _ledger(args)
    try:
        tip_h, tip_hash = led.rpc.tip()
        print(f"tip (live node RPC): height {tip_h}, hash {tip_hash}")
        return
    except RpcError:
        pass
    cache = led._load_cache()
    print(f"tip (ledger cache): height {cache.get('tip_height')}, "
          f"hash {cache.get('tip_hash')}")
    print("node RPC unavailable — cache may be stale; run `ledger sync`.")


def cmd_checkpoint_verify(args):
    if args.file:
        rep = verify_checkpoint_file(args.file)
        print(f"checkpoint {rep['file']}: height {rep['height']}, "
              f"tip {str(rep['tip_hash'])[:16]}…")
        print(f"  attestation (Trifold): "
              f"{'VALID' if rep['attestation_valid'] else 'INVALID'} "
              f"(auditor root {str(rep['auditor_root'])[:16]}…, "
              f"leaf {rep['leaf_index']})")
        print(f"  status: {rep['status']} | anchor: {rep['anchor_leg']}")
        print(f"  anchor hash: {rep['anchor_hash'][:32]}…")
        print(f"  bootstrap from this checkpoint: "
              f"{'YES' if rep['bootstrap_ok'] else 'NO — needs final + attested'}")
        return
    rep = verify_chain_attestations()
    print(f"on-chain attestations (tip {rep['tip_height']}):")
    for mk in rep["verified"]:
        print(f"  VERIFIED  h{mk['height']} {mk['kind']}: "
              f"{mk['text']} ({mk['confirmations']} conf)")
    for mk in rep["unknown"]:
        print(f"  UNKNOWN   h{mk['height']} {mk['kind']}: {mk['text']} "
              f"(root not in the wallet's known set)")
    print("lineage (genesis <- 25344 <- 25351 <- 43750):")
    for leg in rep["lineage"]:
        print(f"  h{leg['height']} {leg['label']}: "
              f"{'marker found' if leg['found'] else 'NO MARKER IN CHAIN'}"
              + (f" — {leg['text']}" if leg['text'] else ""))
    print(rep["fallback"])


# -------------------------------------------------------------------- uruu
def cmd_uruu_info(args):
    try:
        info = uruu.token_info()
    except uruu.UruuError as e:
        raise SystemExit(f"URUU lookup unavailable: {e}")
    print(f"URUU: {info['name']} ({info['symbol']})")
    print(f"token: {info['token']} (zkSync Era, chain {info['chain_id']})")
    print(f"decimals: {info['decimals']} | total supply: "
          f"{info['total_supply']:,} URUU")


def cmd_uruu_balance(args):
    try:
        b = uruu.balance_of(args.address)
    except uruu.UruuError as e:
        raise SystemExit(f"URUU lookup unavailable: {e}")
    print(f"URUU balance of {b['address']}: {b['balance_uruu']:,.6f} URUU")
    print(f"  ({b['balance_base_units']:,} base units, "
          f"{b['decimals']} decimals)")


# --------------------------------------------------------------- frostgate
def cmd_frostgate_init(args):
    try:
        res = frostgate.init_vault(args.dir, args.operators,
                                   args.threshold)
    except frostgate.FrostgateError as e:
        raise SystemExit(f"frostgate init: {e}")
    print(f"Frostgate vault created: {res['vault_dir']}")
    print(f"  {res['threshold']}-of-{res['operators']} dealerless DKG")
    print(f"  group key: {res['group_key']}")
    print(f"  testnet address: "
          f"{frostgate.vault_address(args.dir, 'testnet')}")
    print("Operator key files are 0600 in that dir — never share them,")
    print("never commit them. Testnet only; no mainnet funds.")


def cmd_frostgate_address(args):
    try:
        addr = frostgate.vault_address(args.dir, args.network)
    except frostgate.FrostgateError as e:
        raise SystemExit(f"frostgate address: {e}")
    print(f"Frostgate vault address ({args.network}): {addr}")


def cmd_frostgate_status(args):
    try:
        st = frostgate.vault_status(args.dir)
    except frostgate.FrostgateError as e:
        raise SystemExit(f"frostgate status: {e}")
    print(f"vault: {st['vault_dir']}")
    print(f"  {st['threshold']}-of-{st['num_operators']} FROST federation")
    print(f"  group key: {st['group_key']}")
    print(f"  testnet address: {st['address_testnet']}")
    if st["is_nov1_federation"]:
        print("  this is the Nov 1 testnet federation (demo ceremony).")


def cmd_frostgate_sign(args):
    try:
        res = frostgate.threshold_sign(args.dir, args.message,
                                       tuple(int(s) for s in
                                             args.signers.split(",")))
    except frostgate.FrostgateError as e:
        raise SystemExit(f"frostgate sign: {e}")
    print(f"threshold signature (signers {res['signers']}, verified "
          f"under the group key by the Rust CLI):")
    print(f"  {res['signature']}")


def cmd_frostgate_spend(args):
    try:
        res = frostgate.threshold_spend(
            args.dir, args.prev_txid, args.prev_vout, args.prev_value,
            args.dest, fee_sats=args.fee, network=args.network,
            signers=tuple(int(s) for s in args.signers.split(",")))
    except frostgate.FrostgateError as e:
        raise SystemExit(f"frostgate spend: {e}")
    print("signed tx hex (DRY RUN — the operator CLI has no broadcast")
    print("flag and this wallet adds none):")
    print(f"  {res['raw_tx_hex']}")


def cmd_node_status(args):
    led = _ledger(args)
    try:
        tip_h, tip_hash = led.rpc.tip()
        print(f"fork node: UP (RPC 127.0.0.1:9432, tip {tip_h}, "
              f"{tip_hash[:16]}…)")
    except RpcError as e:
        print(f"fork node: DOWN ({e}) — wallet falls back to the local "
              f"chain scan; start the node before relying on RPC.")
    try:
        import socket as _s
        s = _s.create_connection(("127.0.0.1", 9433), timeout=3)
        s.close()
        print("P2P: listening on 127.0.0.1:9433")
    except OSError:
        print("P2P: 127.0.0.1:9433 not accepting connections")


def _source_hash():
    """SHA-256 (first 12 hex) over this package's .py sources, sorted.

    Lets anyone check what source an exe/CLI was built from: run
    `excalibur --version` and compare the hash with a fresh hash of the
    source tree. Added 2026-11-14 (audit D6: exe currency was mtime-only).

    In a PyInstaller exe the .py sources are embedded, not on disk, so
    the hash falls back to the build-time `_build_version.txt` bundled
    by build_wallet_exe.py (same hash, computed before the build).
    """
    pkg = os.path.dirname(os.path.abspath(__file__))
    names = []
    if os.path.isdir(pkg):
        names = [n for n in sorted(os.listdir(pkg)) if n.endswith(".py")]
    if names:
        h = hashlib.sha256()
        for name in names:
            with open(os.path.join(pkg, name), "rb") as f:
                h.update(f.read())
        return h.hexdigest()[:12]
    for base in (getattr(sys, "_MEIPASS", None), pkg):
        if not base:
            continue
        for cand in (os.path.join(base, "excalibur_wallet",
                                  "_build_version.txt"),
                     os.path.join(base, "_build_version.txt")):
            if os.path.isfile(cand):
                with open(cand) as f:
                    return f.read().strip()[:12]
    return "frozen-unknown"


# --------------------------------------------------------------------- main
def build_parser():
    ap = argparse.ArgumentParser(
        prog="excalibur",
        description="Excalibur wallet — P2P ledger wallet, Aetherion QAI "
                    "light ledger, URUU view, Frostgate vault.")
    ap.add_argument("--version", action="version",
                    version="excalibur-wallet sources " + _source_hash())
    ap.add_argument("--datadir", default=os.environ.get(
        "EXCAL_WALLET_DIR", DEFAULT_DATADIR),
        help="wallet datadir (default: %(default)s)")
    ap.add_argument("--passphrase-file",
                    help="0600 file holding the wallet passphrase")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add(name, fn, help_):
        p = sub.add_parser(name, help=help_)
        p.set_defaults(fn=fn)
        return p

    def add_signal_args(p):
        """Watcher-signal options for a BTC funding build (--signal-tag
        turns the signal on; the OP_RETURN carries tag + delivery
        pubkey and 1,000 sats go to the signal address, so the swap
        watcher sees the funding)."""
        p.add_argument("--signal-tag",
                       help="lot tag for the watcher signal (e.g. "
                       "EXCAL1K) — opts the funding tx into the "
                       "watcher signal; needs --delivery-pubkey")
        p.add_argument("--delivery-pubkey",
                       help="taker's fresh delivery pubkey hex "
                       "(33 bytes, compressed) for the watcher signal")
        p.add_argument("--signal-address", default=None,
                       help="watcher signal address (default: the "
                       "offer watcher's signal address)")
        p.add_argument("--signal-sats", type=int, default=1000,
                       help="signal payment in sats (default 1000)")

    # wallet
    w = add("wallet", None, "wallet commands")
    ws = w.add_subparsers(dest="wcmd", required=True)

    def wadd(name, fn, help_):
        p = ws.add_parser(name, help=help_)
        p.set_defaults(fn=fn)
        return p

    p = wadd("create", cmd_wallet_create, "create a new encrypted wallet")
    p.add_argument("--words", type=int, choices=[12, 24], default=12)
    p = wadd("restore", cmd_wallet_restore,
             "restore from mnemonic or SSS shares")
    p.add_argument("--mnemonic", help="12/24-word mnemonic (quoted)")
    p.add_argument("--shares", nargs="+",
                   help="SSS share hex strings (k of n)")
    p = wadd("address", cmd_wallet_address, "show a receive address")
    p.add_argument("--index", type=int, default=None)
    wadd("receive", cmd_wallet_receive, "a fresh receive address")
    wadd("info", cmd_wallet_info, "wallet summary")
    p = wadd("balance", cmd_wallet_balance, "balance")
    p.add_argument("--via", choices=["rpc", "local", "snapshot"],
                   default="rpc")
    p.add_argument("--snapshot", help="snapshot file (with --via snapshot)")
    p.add_argument("--manifest", help="snapshot manifest JSON")
    p = wadd("utxos", cmd_wallet_utxos, "list UTXOs")
    p.add_argument("--lock", help="filter by lock hex")
    p = wadd("history", cmd_wallet_history, "transaction history")
    p.add_argument("--limit", type=int, default=20)
    p = wadd("send", cmd_wallet_send,
             "build + sign + verify a payment (NO broadcast)")
    p.add_argument("--to", required=True, help="destination lock hex")
    p.add_argument("--amount", required=True,
                   help="swords (int) or EXCAL (decimal)")
    p.add_argument("--fee-rate", type=int, default=1,
                   help="swords per vbyte (default 1)")
    p.add_argument("--save", help="write the signed tx JSON (0600) for "
                   "`wallet broadcast --file`")
    p = wadd("broadcast", cmd_wallet_broadcast,
             "submit a built+verified tx (needs --yes)")
    p.add_argument("--file", help="saved-tx JSON from `wallet send --save`")
    p.add_argument("--tx", help="raw tx hex (instead of --file)")
    p.add_argument("--network", required=True,
                   choices=["fork", "bitcoin"],
                   help="which node receives the tx")
    p.add_argument("--dry-run", action="store_true",
                   help="validate + testmempoolaccept only, do not submit")
    p.add_argument("--yes", action="store_true",
                   help="accept that broadcast moves funds irreversibly")
    p.add_argument("--btc-rpc", default=None,
                   help="Bitcoin node HOST:PORT (default 127.0.0.1:8332)")
    p.add_argument("--btc-rpc-config",
                   help="0600 bitcoin.conf with rpcuser=/rpcpassword=")
    p = wadd("confirmations", cmd_wallet_confirmations,
             "confirmations of a txid (settled at 6)")
    p.add_argument("--txid", required=True, help="64-hex txid")
    p.add_argument("--network", required=True,
                   choices=["fork", "bitcoin"])
    p.add_argument("--btc-rpc", default=None,
                   help="Bitcoin node HOST:PORT (default 127.0.0.1:8332)")
    p.add_argument("--btc-rpc-config",
                   help="0600 bitcoin.conf with rpcuser=/rpcpassword=")
    p = wadd("security", cmd_wallet_security,
             "infancy security report (replay/eclipse/reorg/double-spend)")
    p.add_argument("--peers", help="comma list HOST:PORT to check tip "
                   "agreement across (eclipse check)")
    wadd("locks", cmd_wallet_locks, "lock types + activation status")
    p = wadd("split", cmd_wallet_split,
             "Shamir-split the seed into k-of-n shares")
    p.add_argument("--threshold", type=int, required=True)
    p.add_argument("--shares", type=int, required=True)
    p = wadd("import-node", cmd_wallet_import_node,
             "import a node wallet file (single key)")
    p.add_argument("--wallet", required=True)
    p.add_argument("--keyfile", help="keyfile for encrypted node wallets")

    p = wadd("htlc", None, "HTLC locks")
    hs = p.add_subparsers(dest="hcmd", required=True)

    def hadd(name, fn, help_):
        q = hs.add_parser(name, help=help_)
        q.set_defaults(fn=fn)
        return q

    p = hadd("create", cmd_wallet_htlc_create, "create an HTLC lock")
    p.add_argument("--secret", help="32-byte secret hex (generated if omitted)")
    p.add_argument("--claim-pubkey", required=True)
    p.add_argument("--refund-pubkey", required=True)
    p.add_argument("--timeout", type=int, required=True)
    p = hadd("claim", cmd_wallet_htlc_claim, "claim an HTLC (secret)")
    p.add_argument("--utxo", required=True, help="TXID:VOUT")
    p.add_argument("--dest", required=True)
    p.add_argument("--secret", required=True)
    p.add_argument("--fee", type=int, default=1000)
    p = hadd("refund", cmd_wallet_htlc_refund, "refund an HTLC (timeout)")
    p.add_argument("--utxo", required=True, help="TXID:VOUT")
    p.add_argument("--dest", required=True)
    p.add_argument("--fee", type=int, default=1000)

    p = wadd("btc-htlc", None, "Bitcoin HTLC (P2WSH, standalone)")
    bs = p.add_subparsers(dest="bcmd", required=True)

    def badd(name, fn, help_):
        q = bs.add_parser(name, help=help_)
        q.set_defaults(fn=fn)
        return q

    p = badd("show", cmd_wallet_btc_htlc_show,
             "derive a BTC HTLC address + script (no wallet needed)")
    p.add_argument("--claim-pubkey", required=True)
    p.add_argument("--refund-pubkey", required=True)
    p.add_argument("--secret-hash", required=True,
                   help="32-byte SHA256 of the secret, hex")
    p.add_argument("--timeout", type=int, required=True,
                   help="refund at BTC height >= this")
    p.add_argument("--network", default="mainnet",
                   choices=["mainnet", "testnet", "regtest", "signet"])
    p = badd("create", cmd_wallet_btc_htlc_create,
             "create a BTC HTLC lock (records it in the wallet)")
    p.add_argument("--secret", help="32-byte secret hex (generated if omitted)")
    p.add_argument("--claim-pubkey", required=True)
    p.add_argument("--refund-pubkey", required=True)
    p.add_argument("--timeout", type=int, required=True)
    p.add_argument("--network", default="mainnet",
                   choices=["mainnet", "testnet", "regtest", "signet"])
    p = badd("lock", cmd_wallet_btc_htlc_lock,
             "fund a BTC HTLC from a wallet P2WPKH UTXO (NO broadcast)")
    p.add_argument("--utxo", required=True, help="funding TXID:VOUT")
    p.add_argument("--utxo-value", type=int, required=True,
                   help="funding UTXO value in sats")
    p.add_argument("--utxo-scriptpubkey", required=True,
                   help="funding UTXO scriptPubKey hex (must be a wallet P2WPKH)")
    p.add_argument("--amount", type=int, required=True,
                   help="HTLC output value in sats")
    p.add_argument("--claim-pubkey", required=True)
    p.add_argument("--refund-pubkey", required=True)
    p.add_argument("--secret-hash",
                   help="32-byte SHA256 of the secret, hex")
    p.add_argument("--secret", help="32-byte secret hex (hash derived)")
    p.add_argument("--timeout", type=int, required=True)
    p.add_argument("--change-index", type=int, default=None,
                   help="wallet change key index (default: next)")
    p.add_argument("--fee-rate", type=int, default=5,
                   help="sats per vbyte (default 5)")
    p.add_argument("--network", default="mainnet",
                   choices=["mainnet", "testnet", "regtest", "signet"])
    p.add_argument("--save", help="write the signed tx JSON (0600) for "
                   "`wallet broadcast --file`")
    add_signal_args(p)
    p = badd("claim", cmd_wallet_btc_htlc_claim,
             "claim a BTC HTLC (secret + claim key, NO broadcast)")
    p.add_argument("--utxo", required=True, help="HTLC TXID:VOUT")
    p.add_argument("--utxo-value", type=int, required=True,
                   help="HTLC UTXO value in sats")
    p.add_argument("--secret", required=True, help="32-byte secret hex")
    p.add_argument("--dest-address", required=True,
                   help="destination SegWit v0 address (bc1q...)")
    p.add_argument("--witness-script",
                   help="witness script hex (or --address of a recorded lock)")
    p.add_argument("--address",
                   help="recorded BTC HTLC address (looks up the script)")
    p.add_argument("--fee", type=int, default=None,
                   help="explicit fee in sats (default: fee-rate * vsize)")
    p.add_argument("--fee-rate", type=int, default=5,
                   help="sats per vbyte (default 5)")
    p.add_argument("--network", default="mainnet",
                   choices=["mainnet", "testnet", "regtest", "signet"])
    p.add_argument("--save", help="write the signed tx JSON (0600)")
    p = badd("refund", cmd_wallet_btc_htlc_refund,
             "refund a BTC HTLC (refund key, after timeout, NO broadcast)")
    p.add_argument("--utxo", required=True, help="HTLC TXID:VOUT")
    p.add_argument("--utxo-value", type=int, required=True,
                   help="HTLC UTXO value in sats")
    p.add_argument("--dest-address", required=True,
                   help="destination SegWit v0 address (bc1q...)")
    p.add_argument("--witness-script",
                   help="witness script hex (or --address of a recorded lock)")
    p.add_argument("--address",
                   help="recorded BTC HTLC address (looks up the script)")
    p.add_argument("--btc-height", type=int, required=True,
                   help="current Bitcoin tip height (must be >= timeout)")
    p.add_argument("--fee", type=int, default=None,
                   help="explicit fee in sats (default: fee-rate * vsize)")
    p.add_argument("--fee-rate", type=int, default=5,
                   help="sats per vbyte (default 5)")
    p.add_argument("--network", default="mainnet",
                   choices=["mainnet", "testnet", "regtest", "signet"])
    p.add_argument("--save", help="write the signed tx JSON (0600)")

    p = wadd("swap", None,
             "Cross-chain atomic swap (EXCAL HTLC/QHTLC + BTC HTLC)")
    ss = p.add_subparsers(dest="scmd", required=True)

    def sadd(name, fn, help_):
        q = ss.add_parser(name, help=help_)
        q.set_defaults(fn=fn)
        return q

    p = sadd("create", cmd_wallet_swap_create,
             "create a swap (shared hashlock, staggered timeouts)")
    p.add_argument("--role", required=True, choices=["maker", "taker"],
                   help="maker locks EXCAL + claims BTC; taker locks "
                   "BTC + claims EXCAL")
    p.add_argument("--counterparty-pubkey", required=True,
                   help="counterparty compressed pubkey hex (33 bytes)")
    p.add_argument("--excal-amount", type=int, required=True,
                   help="EXCAL locked, in swords")
    p.add_argument("--btc-amount", type=int, required=True,
                   help="BTC locked, in sats")
    p.add_argument("--excal-timeout", type=int, required=True,
                   help="EXCAL refund at fork height >= this (must be "
                   "later than the BTC timeout in wall-clock terms)")
    p.add_argument("--btc-timeout", type=int, required=True,
                   help="BTC refund at BTC height >= this (expires first)")
    p.add_argument("--fork-height", type=int, required=True,
                   help="current fork tip height (timeout validation)")
    p.add_argument("--btc-height", type=int, required=True,
                   help="current Bitcoin tip height (timeout validation)")
    p.add_argument("--secret", help="32-byte secret hex (maker only; "
                   "generated if omitted — shown once, never stored)")
    p.add_argument("--secret-hash", help="32-byte secret hash hex "
                   "(taker only — the maker's published hash)")
    p.add_argument("--excal-leg", default="htlc",
                   choices=["htlc", "qhtlc"],
                   help="EXCAL leg kind: HTLC (ECDSA claim/refund "
                   "keys, default) or QHTLC (Trifold claim/refund "
                   "roots — needs --claim-root/--refund-root; "
                   "how the flow takes over the funded QHTLC lots)")
    p.add_argument("--claim-root", help="32-byte Trifold claim root "
                   "hex (QHTLC leg only)")
    p.add_argument("--refund-root", help="32-byte Trifold refund root "
                   "hex (QHTLC leg only)")
    p.add_argument("--network", default="mainnet",
                   choices=["mainnet", "testnet", "regtest", "signet"])
    p = sadd("show", cmd_wallet_swap_show,
             "show a swap's state + both legs")
    p.add_argument("--swap-id", required=True)
    p = sadd("list", cmd_wallet_swap_list, "list all swaps in the wallet")
    p = sadd("fund-excal", cmd_wallet_swap_fund_excal,
             "maker: fund the EXCAL leg from live-node UTXOs "
             "(NO broadcast)")
    p.add_argument("--swap-id", required=True)
    p.add_argument("--fee-rate", type=int, default=1,
                   help="swords per vbyte (default 1)")
    p.add_argument("--save", help="write the signed tx JSON (0600) for "
                   "`wallet broadcast --file`")
    p = sadd("note-excal-funded", cmd_wallet_swap_note_excal_funded,
             "record + verify an EXCAL funding tx (maker's own, or "
             "the counterparty's for the taker)")
    p.add_argument("--swap-id", required=True)
    p.add_argument("--raw-hex", required=True,
                   help="EXCAL funding tx, raw hex (verified against "
                   "the swap lock + amount)")
    p = sadd("fund-btc", cmd_wallet_swap_fund_btc,
             "taker: fund the BTC leg from a wallet P2WPKH UTXO "
             "(NO broadcast)")
    p.add_argument("--swap-id", required=True)
    p.add_argument("--utxo", required=True, help="funding TXID:VOUT")
    p.add_argument("--utxo-value", type=int, required=True,
                   help="funding UTXO value in sats")
    p.add_argument("--utxo-scriptpubkey", required=True,
                   help="funding UTXO scriptPubKey hex (must be a wallet "
                   "P2WPKH)")
    p.add_argument("--change-index", type=int, default=None,
                   help="wallet change key index (default: next)")
    p.add_argument("--fee-rate", type=int, default=5,
                   help="sats per vbyte (default 5)")
    p.add_argument("--save", help="write the signed tx JSON (0600)")
    add_signal_args(p)
    p = sadd("note-btc-funded", cmd_wallet_swap_note_btc_funded,
             "record + verify a BTC funding tx (taker's own, or the "
             "counterparty's for the maker)")
    p.add_argument("--swap-id", required=True)
    p.add_argument("--raw-hex", required=True,
                   help="BTC funding tx, raw hex (verified against "
                   "the swap P2WSH address + amount)")
    p = sadd("claim-btc", cmd_wallet_swap_claim_btc,
             "maker: claim the BTC leg with the secret (NO broadcast)")
    p.add_argument("--swap-id", required=True)
    p.add_argument("--secret", required=True, help="32-byte secret hex")
    p.add_argument("--dest-address", required=True,
                   help="destination SegWit v0 address (bc1q...)")
    p.add_argument("--fee-rate", type=int, default=5,
                   help="sats per vbyte (default 5)")
    p.add_argument("--network", default="mainnet",
                   choices=["mainnet", "testnet", "regtest", "signet"])
    p.add_argument("--save", help="write the signed tx JSON (0600)")
    p = sadd("note-btc-claimed", cmd_wallet_swap_note_btc_claimed,
             "taker: record + verify the maker's BTC claim (reveals "
             "the secret)")
    p.add_argument("--swap-id", required=True)
    p.add_argument("--raw-hex", required=True,
                   help="maker's BTC claim tx, raw hex (verified "
                   "against the swap funding + secret hash; the "
                   "revealed secret is printed)")
    p = sadd("claim-excal", cmd_wallet_swap_claim_excal,
             "taker: claim the EXCAL leg with the revealed secret "
             "(NO broadcast)")
    p.add_argument("--swap-id", required=True)
    p.add_argument("--secret", required=True,
                   help="32-byte secret hex (revealed by the maker's "
                   "BTC claim)")
    p.add_argument("--dest", required=True,
                   help="destination fork lock hex (21 bytes)")
    p.add_argument("--utxo", required=True,
                   help="recorded EXCAL funding TXID:VOUT")
    p.add_argument("--fee", type=int, default=1000,
                   help="fee in swords (default 1000)")
    p.add_argument("--fork-height", type=int, required=True,
                   help="current fork tip height (validation height is "
                   "tip+1)")
    p.add_argument("--claim-seed",
                   help="32-byte claim seed hex (QHTLC leg only — "
                   "the decrypted claim seed from the watcher; "
                   "never stored)")
    p = sadd("note-excal-claimed", cmd_wallet_swap_note_excal_claimed,
             "maker: record the taker's EXCAL claim (swap complete)")
    p.add_argument("--swap-id", required=True)
    p.add_argument("--txid", required=True,
                   help="taker's EXCAL claim txid")
    p = sadd("refund-excal", cmd_wallet_swap_refund_excal,
             "maker: refund the EXCAL leg after both timeouts "
             "(NO broadcast)")
    p.add_argument("--swap-id", required=True)
    p.add_argument("--dest", required=True,
                   help="destination fork lock hex (21 bytes)")
    p.add_argument("--utxo", required=True,
                   help="recorded EXCAL funding TXID:VOUT")
    p.add_argument("--fee", type=int, default=1000,
                   help="fee in swords (default 1000)")
    p.add_argument("--fork-height", type=int, required=True,
                   help="current fork tip height (must be >= the EXCAL "
                   "timeout)")
    p.add_argument("--btc-height", type=int, required=True,
                   help="current Bitcoin tip height (must be >= the BTC "
                   "timeout when the BTC leg was funded)")
    p.add_argument("--refund-seed",
                   help="32-byte refund seed hex (QHTLC leg only — "
                   "the maker's refund seed; never stored)")
    p = sadd("refund-btc", cmd_wallet_swap_refund_btc,
             "taker: refund the BTC leg after its timeout "
             "(NO broadcast)")
    p.add_argument("--swap-id", required=True)
    p.add_argument("--dest-address", required=True,
                   help="destination SegWit v0 address (bc1q...)")
    p.add_argument("--btc-height", type=int, required=True,
                   help="current Bitcoin tip height (must be >= timeout)")
    p.add_argument("--fee-rate", type=int, default=5,
                   help="sats per vbyte (default 5)")
    p.add_argument("--network", default="mainnet",
                   choices=["mainnet", "testnet", "regtest", "signet"])
    p.add_argument("--save", help="write the signed tx JSON (0600)")

    p = wadd("qhtlc", None, "QHTLC locks (hash-only)")
    qs = p.add_subparsers(dest="qcmd", required=True)

    def qadd(name, fn, help_):
        q = qs.add_parser(name, help=help_)
        q.set_defaults(fn=fn)
        return q

    p = qadd("create", cmd_wallet_qhtlc_create, "create a QHTLC lock")
    p.add_argument("--secret", help="32-byte secret hex (generated if omitted)")
    p.add_argument("--claim-root", required=True)
    p.add_argument("--refund-root", required=True)
    p.add_argument("--timeout", type=int, required=True)
    p = qadd("claim", lambda a: _qhtlc_spend(a, "claim"),
             "claim a QHTLC (secret + Trifold)")
    p.add_argument("--utxo", required=True, help="TXID:VOUT")
    p.add_argument("--dest", required=True)
    p.add_argument("--secret", required=True)
    p.add_argument("--fee", type=int, default=1000)
    p.add_argument("--claim-seed",
                   help="32-byte claim seed hex — the Trifold key is "
                   "derived from this seed instead of the wallet's "
                   "own key (externally-rooted lots)")
    p = qadd("refund", lambda a: _qhtlc_spend(a, "refund"),
             "refund a QHTLC (Trifold, timeout)")
    p.add_argument("--utxo", required=True, help="TXID:VOUT")
    p.add_argument("--dest", required=True)
    p.add_argument("--fee", type=int, default=1000)
    p.add_argument("--refund-seed",
                   help="32-byte refund seed hex — the Trifold key is "
                   "derived from this seed instead of the wallet's "
                   "own key (externally-rooted lots)")

    p = wadd("pqh", None, "PQH (Trifold) wallet key")
    ps = p.add_subparsers(dest="pcmd", required=True)

    def padd(name, fn, help_):
        q = ps.add_parser(name, help=help_)
        q.set_defaults(fn=fn)
        return q

    padd("address", cmd_wallet_pqh_address, "show the PQH address")
    p = padd("spend", cmd_wallet_pqh_spend,
             "spend a PQH UTXO (one-time leaf; needs --yes)")
    p.add_argument("--utxo", required=True, help="TXID:VOUT")
    p.add_argument("--dest", required=True)
    p.add_argument("--fee", type=int, default=1000)
    p.add_argument("--yes", action="store_true",
                   help="accept the one-time-leaf burn warning")

    p = wadd("knot", None, "KNOT locks (TEST-CHAIN ONLY)")
    ks = p.add_subparsers(dest="kcmd", required=True)

    def kadd(name, fn, help_):
        q = ks.add_parser(name, help=help_)
        q.set_defaults(fn=fn)
        return q

    p = kadd("lock", cmd_wallet_knot_lock,
             "build a KNOT funding tx (test-chain only)")
    p.add_argument("--amount", required=True)
    p.add_argument("--p", type=int, default=2)
    p.add_argument("--q", type=int, default=3)
    p.add_argument("--n-terms", type=int, default=50)
    p.add_argument("--eps", type=int, default=0x80000000)
    p.add_argument("--t-star", help="128-bit hex (generated if omitted)")
    p.add_argument("--fee", type=int, default=1000)
    p.add_argument("--fee-rate", type=int, default=1)
    p = kadd("spend", cmd_wallet_knot_spend,
             "spend a KNOT UTXO (test-chain only)")
    p.add_argument("--utxo", required=True, help="TXID:VOUT")
    p.add_argument("--lock", required=True)
    p.add_argument("--descriptor", required=True)
    p.add_argument("--t-star", required=True)
    p.add_argument("--amount", type=int, required=True)
    p.add_argument("--dest", required=True)
    p.add_argument("--fee", type=int, default=1000)

    # ledger
    p = add("ledger", None, "ledger sync / tip")
    ls = p.add_subparsers(dest="lcmd", required=True)

    def ladd(name, fn, help_):
        q = ls.add_parser(name, help=help_)
        q.set_defaults(fn=fn)
        return q

    p = ladd("sync", cmd_ledger_sync, "sync the wallet ledger")
    p.add_argument("--via", choices=["rpc", "local", "p2p"], default="local")
    p.add_argument("--wallet", action="store_true",
                   help="track this wallet's locks (needed for local/p2p)")
    p.add_argument("--peer", help="peer host:port for --via p2p")
    ladd("tip", cmd_ledger_tip, "show the chain tip")

    # checkpoint
    p = add("checkpoint", None, "QAI checkpoint attestations")
    cs = p.add_subparsers(dest="ccmd", required=True)
    p = cs.add_parser("verify", help="verify checkpoint attestations")
    p.add_argument("--file", help="lightledger checkpoint JSON file")
    p.set_defaults(fn=cmd_checkpoint_verify)

    # uruu
    p = add("uruu", None, "read-only URUU view (zkSync Era)")
    us = p.add_subparsers(dest="ucmd", required=True)
    p = us.add_parser("info", help="URUU token info (live contract)")
    p.set_defaults(fn=cmd_uruu_info)
    p = us.add_parser("balance", help="URUU balance of an ETH address")
    p.add_argument("--address", required=True)
    p.set_defaults(fn=cmd_uruu_balance)

    # frostgate
    p = add("frostgate", None, "Frostgate 3-of-5 FROST vault (testnet)")
    fs = p.add_subparsers(dest="fcmd", required=True)

    def fadd(name, fn, help_):
        q = fs.add_parser(name, help=help_)
        q.set_defaults(fn=fn)
        return q

    p = fadd("init", cmd_frostgate_init, "fresh dealerless DKG vault")
    p.add_argument("--dir", default=os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "excalibur-wallet-data", "frostgate-vault"))
    p.add_argument("--operators", type=int, default=5)
    p.add_argument("--threshold", type=int, default=3)
    p = fadd("address", cmd_frostgate_address, "vault P2TR address")
    p.add_argument("--dir", default=frostgate.DEFAULT_VAULT_DIR)
    p.add_argument("--network", default="testnet",
                   choices=["testnet", "regtest", "mainnet"])
    p = fadd("status", cmd_frostgate_status, "vault status")
    p.add_argument("--dir", default=frostgate.DEFAULT_VAULT_DIR)
    p = fadd("sign", cmd_frostgate_sign,
             "threshold-sign a 32-byte message")
    p.add_argument("--dir", default=frostgate.DEFAULT_VAULT_DIR)
    p.add_argument("--message", required=True, help="32-byte hex")
    p.add_argument("--signers", default="1,2,3")
    p = fadd("spend", cmd_frostgate_spend,
             "threshold-spend a vault UTXO (dry run, never broadcasts)")
    p.add_argument("--dir", default=frostgate.DEFAULT_VAULT_DIR)
    p.add_argument("--prev-txid", required=True)
    p.add_argument("--prev-vout", type=int, required=True)
    p.add_argument("--prev-value", type=int, required=True)
    p.add_argument("--dest", required=True)
    p.add_argument("--fee", type=int, default=500)
    p.add_argument("--network", default="testnet",
                   choices=["testnet", "regtest", "mainnet"])
    p.add_argument("--signers", default="1,2,3")

    add("node", None, "node status").add_subparsers(
        dest="ncmd", required=True).add_parser(
            "status", help="fork node RPC + P2P status").set_defaults(
                fn=cmd_node_status)
    return ap


def main(argv=None):
    ap = build_parser()
    args = ap.parse_args(argv)
    if args.fn is None:
        ap.print_help()
        return 2
    args.fn(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
