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
There is no broadcast command in this wallet.
"""
import argparse
import getpass
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from .wallet import Wallet, WalletError
from .ledger import Ledger, RpcClient, RpcError
from .txbuild import (build_send, build_htlc_claim, build_htlc_refund,
                     build_qhtlc_claim, build_qhtlc_refund,
                     build_pqh_spend, build_knot_lock_test,
                     build_knot_spend_test, parse_amount, TxBuildError)
from .locks import (parse_lock_hex, lock_status, knot_lock_refuse,
                   htlc_lock, qhtlc_lock, KnotRefused)
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
    """UTXOs + validation height for a send. Prefers the live node
    RPC (indexed, current); falls back to the local chain scan.
    Returns (utxos, height, source)."""
    led = _ledger(args)
    locks = _watched(wallet)
    try:
        balances, (tip_height, tip_hash) = led.balance_via_rpc(locks)
        utxos = []
        for lock_hex, b in balances.items():
            for u in b["utxos"]:
                utxos.append({"txid": u["txid"], "vout": u["vout"],
                              "value": u["value"], "lock": lock_hex,
                              "coinbase": u["coinbase"],
                              "cb_h": u.get("cb_h", 0),
                              "mature": u["mature"]})
        return utxos, tip_height + 1, f"live node RPC (tip {tip_height})"
    except RpcError as e:
        print(f"node RPC unavailable ({e}) — falling back to local "
              f"chain scan", file=sys.stderr)
    stats = led.sync_local(locks)
    utxos = led.cached_utxos()
    return utxos, stats["tip_height"] + 1, (
        f"local chain scan (tip {stats['tip_height']}, "
        f"{stats['new_records']} new records)")


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
    print("NOT broadcast. This wallet never broadcasts. To submit, use "
          "the node's sendrawtransaction yourself — only on your "
          "explicit decision.")


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
            print(f"source: live node RPC (tip {tip_h})")
            print(f"mature:   {_fmt_swords(mature)}")
            print(f"immature: {_fmt_swords(immature)} (coinbase < 100 conf)")
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
    print(f"source: local chain scan (tip {bal['tip_height']}, "
          f"{stats['new_records']} new records this run)")
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
    except RpcError:
        stats = led.sync_local(locks)
        rows = led.cached_utxos()
        print(f"source: local chain scan (tip {stats['tip_height']})")
    if args.lock:
        rows = [r for r in rows if r["lock"] == args.lock.lower()]
    rows.sort(key=lambda r: -r["value"])
    if not rows:
        print("no UTXOs for this wallet")
        return
    for r in rows:
        print(f"{r['txid']}:{r['vout']}  {_fmt_swords(r['value'])}  "
              f"{'mature' if r['mature'] else 'IMMATURE'}  "
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
    _print_tx_result(res)


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
        balances, (_th, _t) = led.balance_via_rpc(_watched(wallet))
        for lock_hex, b in balances.items():
            for u in b["utxos"]:
                if u["txid"] == txid and u["vout"] == vout:
                    return {"txid": txid, "vout": vout,
                            "value": u["value"], "lock": lock_hex,
                            "coinbase": u["coinbase"],
                            "cb_h": u.get("cb_h", 0),
                            "mature": u["mature"]}
    except RpcError:
        pass
    led.sync_local(_watched(wallet))
    for r in led.cached_utxos():
        if r["txid"] == txid and r["vout"] == vout:
            return {"txid": txid, "vout": vout, "value": r["value"],
                    "lock": r["lock"], "coinbase": r["coinbase"],
                    "cb_h": r["cb_h"], "mature": r["mature"]}
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
        led = _ledger(args)
        try:
            height = led.rpc.tip()[0] + 1
        except RpcError:
            height = led._load_cache().get("tip_height", -1) + 1
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
        led = _ledger(args)
        try:
            height = led.rpc.tip()[0] + 1
        except RpcError:
            height = led._load_cache().get("tip_height", -1) + 1
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
        led = _ledger(args)
        try:
            height = led.rpc.tip()[0] + 1
        except RpcError:
            height = led._load_cache().get("tip_height", -1) + 1
        key = w.trifold_key()
        if mode == "claim":
            secret = bytes.fromhex(args.secret)
            res = build_qhtlc_claim(entry, dest_lock, args.fee, secret,
                                    desc, key, height)
        else:
            res = build_qhtlc_refund(entry, dest_lock, args.fee, desc,
                                     key, height)
    except (ValueError, TxBuildError, RuntimeError) as e:
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
        led = _ledger(args)
        try:
            height = led.rpc.tip()[0] + 1
        except RpcError:
            height = led._load_cache().get("tip_height", -1) + 1
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


# --------------------------------------------------------------------- main
def build_parser():
    ap = argparse.ArgumentParser(
        prog="excalibur",
        description="Excalibur wallet — P2P ledger wallet, Aetherion QAI "
                    "light ledger, URUU view, Frostgate vault.")
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
    p = qadd("refund", lambda a: _qhtlc_spend(a, "refund"),
             "refund a QHTLC (Trifold, timeout)")
    p.add_argument("--utxo", required=True, help="TXID:VOUT")
    p.add_argument("--dest", required=True)
    p.add_argument("--fee", type=int, default=1000)

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
