"""test_excalibur_wallet.py — tests for the EXCAL wallet.

Plain-script style (like test_wallet_crypto.py): check(name, cond),
print "ok: name" per pass. Run: python3 test_excalibur_wallet.py

Sections: unit (BIP39, keys, SSS, wallet file, txbuild on a synthetic
chain, locks, KNOT refusal) then live (real chain scan, live RPC tip,
live checkpoint attestations, live URUU contract, live Frostgate Rust
CLI). Live sections SKIP (not fail) when the live service is
unreachable — a skip is reported as such, never as a pass.

No secrets are printed: mnemonics, seeds, shares and signatures are
checked by length/hash only, never echoed.
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from excalibur_wallet import bip39, keys, sss, wallet as wallet_mod
from excalibur_wallet.wallet import Wallet, WalletError
from excalibur_wallet.locks import (parse_lock_hex, lock_status,
                                    knot_lock_refuse, htlc_lock,
                                    qhtlc_lock, KnotRefused)
from excalibur_wallet.txbuild import (build_send, build_htlc_claim,
                                      build_htlc_refund,
                                      build_qhtlc_claim,
                                      build_qhtlc_refund,
                                      build_pqh_spend,
                                      build_knot_lock_test,
                                      build_knot_spend_test,
                                      parse_amount, TxBuildError)
from excalibur_wallet import frostgate
from excalibur_wallet import uruu

PASSED = []
FAILED = []
SKIPPED = []


def check(name, cond):
    if cond:
        PASSED.append(name)
        print(f"ok: {name}")
    else:
        FAILED.append(name)
        print(f"FAIL: {name}")


def skip(name, reason):
    SKIPPED.append(name)
    print(f"skip: {name} ({reason})")


SWORD = 100_000_000


def _fake_utxo(txid_hex, vout, value, lock, coinbase=True, cb_h=0):
    return {"txid": txid_hex, "vout": vout, "value": value,
            "lock": lock.hex() if isinstance(lock, bytes) else lock,
            "coinbase": coinbase, "cb_h": cb_h, "mature": True}


def _funding_txid(tag):
    return hashlib.sha256(tag.encode()).hexdigest()


# ============================================================== BIP39
def test_bip39():
    words = bip39.wordlist()
    check("bip39 wordlist is 2048 unique words", len(words) == 2048
          and len(set(words)) == 2048 and words[0] == "abandon"
          and words[-1] == "zoo")
    m12 = bip39.generate_mnemonic(128)
    check("bip39 12-word mnemonic validates",
          len(m12.split()) == 12 and bip39.validate_mnemonic(m12))
    m24 = bip39.generate_mnemonic(256)
    check("bip39 24-word mnemonic validates",
          len(m24.split()) == 24 and bip39.validate_mnemonic(m24))
    check("bip39 bad checksum rejected",
          not bip39.validate_mnemonic("abandon " * 11 + "zoo"))
    check("bip39 unknown word rejected",
          not bip39.validate_mnemonic("abandon " * 11 + "notaword"))
    s1 = bip39.mnemonic_to_seed(m12)
    s2 = bip39.mnemonic_to_seed(m12)
    check("bip39 seed deterministic (64 bytes)", len(s1) == 64 and s1 == s2)
    check("bip39 different mnemonic, different seed",
          bip39.mnemonic_to_seed(m12) != bip39.mnemonic_to_seed(m24))
    check("bip39 entropy round-trip",
          bip39.mnemonic_to_entropy(m12) is not None
          and bip39.entropy_to_mnemonic(
              bip39.mnemonic_to_entropy(m12)) == m12)


# ============================================================== keys
def test_keys():
    seed = bytes(range(64))
    a1 = keys.address_for_priv(keys.receive_key(seed, 0))
    a2 = keys.address_for_priv(keys.receive_key(seed, 0))
    check("keys derivation deterministic", a1 == a2)
    check("keys receive != change address",
          keys.address_for_priv(keys.receive_key(seed, 0))
          != keys.address_for_priv(keys.change_key(seed, 0)))
    check("keys address is a 42-char PKH lock hex",
          len(a1) == 42 and a1.startswith("00"))
    priv = keys.receive_key(seed, 0)
    pub = keys.priv_to_pub_compressed(priv)
    check("keys pubkey compresses to 33 bytes", len(pub) == 33)
    check("keys address matches pubkey hash",
          keys.address_for_priv(priv) == a1)
    check("keys different indices, different addresses",
          keys.address_for_priv(keys.receive_key(seed, 0))
          != keys.address_for_priv(keys.receive_key(seed, 1)))
    check("keys BIP39 test vector (abandon x11 + about)",
          bip39.entropy_to_mnemonic(bytes(16))
          == "abandon " * 11 + "about")


# ============================================================== SSS
def test_sss():
    seed = os.urandom(64)
    shares = sss.split(seed, 5, 3)
    check("sss split gives 5 distinct shares",
          len(shares) == 5 and len({x for x, _ in shares}) == 5)
    check("sss any 3 of 5 recombine",
          sss.combine(shares[:3]) == seed
          and sss.combine([shares[0], shares[2], shares[4]]) == seed
          and sss.combine(shares[2:]) == seed)
    check("sss fewer than threshold does NOT give the seed",
          sss.combine(shares[:2]) != seed)
    enc = sss.encode_share(*shares[0])
    check("sss hex encode/decode round-trip",
          sss.decode_share(enc) == shares[0])
    check("sss share is hex", all(c in "0123456789abcdef" for c in enc))
    try:
        sss.split(seed, 5, 6)
        check("sss threshold > shares rejected", False)
    except ValueError:
        check("sss threshold > shares rejected", True)


# ============================================================== wallet file
def test_wallet_file():
    tmp = tempfile.mkdtemp(prefix="excal-wallet-test-")
    pw = b"test-passphrase-123"
    w, mnemonic = Wallet.create(tmp, pw, words=12)
    check("wallet create returns 12-word mnemonic",
          len(mnemonic.split()) == 12)
    check("wallet file exists, mode 600",
          os.path.isfile(w.path)
          and (os.stat(w.path).st_mode & 0o777) == 0o600)
    with open(w.path, "rb") as f:
        raw = f.read()
    check("wallet file is encrypted (no mnemonic in plaintext)",
          mnemonic.encode().split()[0] not in raw
          and b"abandon" not in raw)
    w2 = Wallet.load(tmp, pw)
    check("wallet load with correct passphrase",
          w2.receive_address() == w.receive_address())
    try:
        Wallet.load(tmp, b"wrong-passphrase")
        check("wallet load with wrong passphrase fails", False)
    except WalletError:
        check("wallet load with wrong passphrase fails", True)
    try:
        Wallet.create(tmp, pw)
        check("wallet create refuses to overwrite", False)
    except WalletError:
        check("wallet create refuses to overwrite", True)
    a0 = w.receive_address()
    idx0, addr0 = w.fresh_receive(pw)
    idx1, addr1 = w.fresh_receive(pw)
    check("wallet fresh_receive advances index",
          idx0 == 0 and addr0 == a0 and idx1 == 1 and addr1 != a0
          and w._data["next_receive"] == 2)
    # SSS restore round-trip through the CLI path
    shares = sss.split(w._seed, 5, 3)
    tmp2 = tempfile.mkdtemp(prefix="excal-wallet-restore-")
    w3 = Wallet.create_from_seed(tmp2, pw, sss.combine(shares[:3]))
    check("wallet SSS restore reproduces the same first address",
          w3.receive_address() == a0)
    # Legacy import
    tmp3 = tempfile.mkdtemp(prefix="excal-wallet-legacy-")
    priv = keys.receive_key(bytes(range(64)), 0)
    pub = keys.priv_to_pub_compressed(priv).hex()
    w4 = Wallet.import_legacy(tmp3, pw, f"{priv:064x}", pub)
    check("wallet legacy import address matches key",
          w4.receive_address() == keys.address_for_priv(priv))
    # Trifold / PQH
    root = w.trifold_key().root
    check("wallet PQH address is a 42-char 0x02 lock",
          w.pqh_address().startswith("02")
          and len(w.pqh_address()) == 42)


# ============================================================== txbuild (synthetic chain)
def test_txbuild():
    priv = 0x123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
    pub = keys.priv_to_pub_compressed(priv)
    from txscript import lock_pkh_for_pubkey
    lock = lock_pkh_for_pubkey(pub)
    lock_hex = lock.hex()
    funding = [_fake_utxo(_funding_txid("fund-a"), 0, 10 * SWORD, lock)]
    dest_priv = 0x9999
    dest_lock = lock_pkh_for_pubkey(keys.priv_to_pub_compressed(dest_priv))
    change_lock = lock
    res = build_send(funding, {lock_hex: priv}, dest_lock, 2 * SWORD,
                     change_lock, fee_rate=1, height=200)
    check("txbuild send validates locally (validate_tx OK)",
          res["validated"] is True)
    check("txbuild send fee is positive and small",
          0 < res["fee"] < 10_000)
    check("txbuild send txid is 64 hex chars",
          len(res["txid"]) == 64)
    check("txbuild send change returns to the wallet",
          any(o["lock"] == lock_hex for o in res["outputs"]))
    # insufficient funds
    try:
        build_send(funding, {lock_hex: priv}, dest_lock, 20 * SWORD,
                   change_lock, fee_rate=1, height=200)
        check("txbuild send refuses overspend", False)
    except TxBuildError:
        check("txbuild send refuses overspend", True)
    # dust
    try:
        build_send(funding, {lock_hex: priv}, dest_lock, 500,
                   change_lock, fee_rate=1, height=200)
        check("txbuild send refuses dust output", False)
    except TxBuildError:
        check("txbuild send refuses dust output", True)
    # amount parsing
    check("txbuild parse_amount swords", parse_amount("1000") == 1000)
    check("txbuild parse_amount EXCAL decimal",
          parse_amount("1.5") == 150_000_000)
    try:
        parse_amount("0.000000001")
        check("txbuild parse_amount rejects sub-sword", False)
    except TxBuildError:
        check("txbuild parse_amount rejects sub-sword", True)


def test_htlc():
    from txscript import lock_pkh_for_pubkey
    secret = bytes(range(32))
    claim_priv = 0x1111
    refund_priv = 0x2222
    claim_pub = keys.priv_to_pub_compressed(claim_priv)
    refund_pub = keys.priv_to_pub_compressed(refund_priv)
    lock, desc = htlc_lock(secret, claim_pub, refund_pub, 41000)
    funding = [_fake_utxo(_funding_txid("htlc-fund"), 0, 5 * SWORD, lock)]
    dest = lock_pkh_for_pubkey(keys.priv_to_pub_compressed(0x3333))
    res = build_htlc_claim(funding[0], dest, 1000, secret, desc,
                           claim_priv, height=40000)
    check("htlc claim validates locally", res["validated"] is True)
    # wrong secret
    try:
        build_htlc_claim(funding[0], dest, 1000, bytes(32), desc,
                         claim_priv, height=40000)
        check("htlc claim refuses wrong secret", False)
    except TxBuildError:
        check("htlc claim refuses wrong secret", True)
    # refund before timeout
    try:
        build_htlc_refund(funding[0], dest, 1000, desc, refund_priv,
                          height=40000)
        check("htlc refund refuses before timeout", False)
    except TxBuildError:
        check("htlc refund refuses before timeout", True)
    res2 = build_htlc_refund(funding[0], dest, 1000, desc, refund_priv,
                             height=42000)
    check("htlc refund validates after timeout", res2["validated"] is True)


def test_qhtlc_pqh():
    from txscript import lock_pkh_for_pubkey, lock_pqh_for_root
    from trifold_lockbox import TrifoldKey
    from spent_leaf_registry import SpentLeafRegistry
    tmp = tempfile.mkdtemp(prefix="excal-pqh-reg-")
    reg = SpentLeafRegistry(os.path.join(tmp, "spent_pqh_registry.json"))
    secret = bytes(range(32))
    claim_key = TrifoldKey(os.urandom(32))
    refund_key = TrifoldKey(os.urandom(32))
    lock, desc = qhtlc_lock(secret, claim_key.root, refund_key.root,
                            51000)
    funding = [_fake_utxo(_funding_txid("qhtlc-fund"), 0, 5 * SWORD, lock)]
    dest = lock_pkh_for_pubkey(keys.priv_to_pub_compressed(0x4444))
    res = build_qhtlc_claim(funding[0], dest, 1000, secret, desc,
                            claim_key, height=50000, registry=reg)
    check("qhtlc claim validates locally", res["validated"] is True)
    check("qhtlc claim burned exactly one leaf",
          claim_key.next_index == 1)
    check("qhtlc claim leaf recorded in the registry",
          reg.is_spent(claim_key.root, 0))
    res2 = build_qhtlc_refund(funding[0], dest, 1000, desc, refund_key,
                              height=52000, registry=reg)
    check("qhtlc refund validates after timeout", res2["validated"] is True)
    check("qhtlc refund added a second registry pair",
          len(reg.as_set()) == 2)
    # PQH spend with the same throwaway registry
    pqh_key = TrifoldKey(os.urandom(32))
    pqh_lock = lock_pqh_for_root(pqh_key.root)
    funding2 = [_fake_utxo(_funding_txid("pqh-fund"), 0, 5 * SWORD,
                           pqh_lock)]
    res3 = build_pqh_spend(funding2[0], dest, 1000, pqh_key, height=30000,
                           registry=reg)
    check("pqh spend validates locally", res3["validated"] is True)
    check("pqh spend recorded the leaf in the registry",
          reg.is_spent(pqh_key.root, 0))
    check("pqh spend burned exactly one leaf",
          pqh_key.next_index == 1)
    # The guard itself: re-recording the same pair must be refused.
    try:
        reg.record(pqh_key.root, 0)
        check("spent-leaf guard refuses a replayed pair", False)
    except RuntimeError:
        check("spent-leaf guard refuses a replayed pair", True)
    # A second spend with the same key advances to a FRESH leaf (no reuse).
    res4 = build_pqh_spend(funding2[0], dest, 1000, pqh_key, height=30000,
                           registry=reg)
    check("pqh second spend uses a fresh leaf and validates",
          res4["validated"] is True and pqh_key.next_index == 2
          and len(reg.as_set()) == 4)


def test_knot():
    from txscript import lock_pkh_for_pubkey
    try:
        knot_lock_refuse(44515)
        check("knot refused on the live fork (tip < 100000)", False)
    except KnotRefused:
        check("knot refused on the live fork (tip < 100000)", True)
    try:
        knot_lock_refuse(100001)
        check("knot allowed at/above activation height", True)
    except KnotRefused:
        check("knot allowed at/above activation height", False)
    priv = 0x5555
    pub = keys.priv_to_pub_compressed(priv)
    lock = lock_pkh_for_pubkey(pub)
    funding = [{"prev": bytes.fromhex(_funding_txid("knot-fund")),
                "idx": 0, "value": 5 * SWORD, "lock": lock}]
    res = build_knot_lock_test(funding, priv, 1 * SWORD, 2, 3, 10,
                               0x80000000, 123456789, 1000)
    from genesis_fork import knot_activation
    act = knot_activation()
    check("knot lock tx validates at activation height",
          res["validated_at_height"] == act)
    from txscript import txid_internal
    lock_prev = txid_internal(res["raw"])
    res2 = build_knot_spend_test(
        lock_prev, 0, 1 * SWORD, res["lock"], res["descriptor"],
        123456789,
        lock_pkh_for_pubkey(keys.priv_to_pub_compressed(0x6666)), 1000)
    check("knot spend tx validates at activation height",
          res2["validated_at_height"] == act)


def test_locks():
    check("locks parse PKH hex",
          parse_lock_hex("00" + "ab" * 20) == bytes.fromhex("00" + "ab" * 20))
    try:
        parse_lock_hex("zz")
        check("locks reject non-hex", False)
    except ValueError:
        check("locks reject non-hex", True)
    # parse_lock_hex parses a KNOT lock (it is a well-formed lock);
    # the refusal happens at build time, not parse time.
    check("locks parse KNOT hex (refusal is at build time)",
          parse_lock_hex("06" + "ab" * 20) == bytes.fromhex("06" + "ab" * 20))
    try:
        from txscript import lock_pkh_for_pubkey
        _priv = 0x7777
        _lock = lock_pkh_for_pubkey(keys.priv_to_pub_compressed(_priv))
        _fund = [_fake_utxo(_funding_txid("knot-dest"), 0, 5 * SWORD,
                            _lock)]
        build_send(_fund, {_lock.hex(): _priv},
                   bytes.fromhex("06" + "ab" * 20), 1 * SWORD, _lock,
                   fee_rate=1, height=44516)
        check("locks build_send refuses a KNOT destination", False)
    except (TxBuildError, KnotRefused):
        check("locks build_send refuses a KNOT destination", True)
    sts = {s["type"]: s for s in lock_status(44515)}
    check("locks PKH active at live tip", sts["pkh"]["active"] is True)
    check("locks KNOT staged at live tip", sts["knot"]["active"] is False)
    check("locks QHTLC active at live tip", sts["qhtlc"]["active"] is True)


# ============================================================== live chain / RPC
def test_live_chain():
    from excalibur_wallet.ledger import Ledger
    tmp = tempfile.mkdtemp(prefix="excal-ledger-live-")
    led = Ledger(tmp)
    try:
        tip_h, tip_hash = led.rpc.tip()
    except Exception as e:
        skip("live RPC tip", f"node RPC unavailable ({e})")
        return
    check("live RPC tip is a sane height", 40000 < tip_h < 100000)
    stats = led.sync_local([])
    # Race-tolerant: the chain grows ~1 block/min and the scan takes
    # minutes, so the file tip may lag the RPC tip read above by a
    # block or two (flush timing) — never by more. Exact equality
    # fails spuriously whenever a block lands mid-scan.
    check("live local chain scan reaches the RPC tip",
          stats["tip_height"] >= tip_h - 2)
    check("live chain scan read >40k records",
          stats["scanned_records"] > 40000)


def test_live_checkpoints():
    from excalibur_wallet.checkpoints import verify_chain_attestations
    try:
        rep = verify_chain_attestations()
    except Exception as e:
        skip("live checkpoint attestations", f"chain scan failed ({e})")
        return
    check("live Dr. Time attestation at 43750 verified",
          any(m["height"] == 43750 for m in rep["verified"]))
    check("live checkpoint lineage legs all found in chain",
          all(leg["found"] for leg in rep["lineage"]))


def test_live_uruu():
    try:
        info = uruu.token_info()
    except uruu.UruuError as e:
        skip("live URUU contract read", f"zkSync RPC unavailable ({e})")
        return
    check("live URUU symbol is URUU", info["symbol"] == "URUU")
    check("live URUU total supply is exactly 100,000,000",
          info["total_supply"] == 100_000_000)
    check("live URUU decimals 18", info["decimals"] == 18)
    b = uruu.balance_of("0x0000000000000000000000000000000000000000")
    check("live URUU zero-address balance is 0",
          b["balance_base_units"] == 0)


def test_live_frostgate():
    cli = frostgate.find_operator_cli()
    check("frostgate operator binary exists (release build)",
          cli is not None and os.path.isfile(cli))
    if cli is None:
        return
    try:
        st = frostgate.vault_status()
    except frostgate.FrostgateError as e:
        skip("frostgate Nov 1 ceremony status", str(e))
        return
    check("frostgate Nov 1 ceremony is 3-of-5",
          st["threshold"] == 3 and st["num_operators"] == 5)
    check("frostgate Nov 1 group key matches the doc",
          st["group_key"] == frostgate.NOV1_GROUP_KEY)
    # The Nov 1 doc's printed TESTNET address is wrong and is NOT used
    # here: it decodes to witness version 5 with a different key, while
    # the live binary derives tb1pwssq… (same program as the doc's
    # regtest address, re-encoded for testnet). The doc's regtest
    # address is correct and is checked below.
    check("frostgate Nov 1 testnet address (live binary derivation)",
          st["address_testnet"] ==
          "tb1pwssqg8qsphwfpeq3afuxfne6yg2pvrdpe4n6yy3af3lvgn8ksygqdna38e")
    check("frostgate Nov 1 regtest address matches the doc",
          frostgate.vault_address(frostgate.DEFAULT_VAULT_DIR,
                                  "regtest") ==
          "bcrt1pwssqg8qsphwfpeq3afuxfne6yg2pvrdpe4n6yy3af3lvgn8ksygqq2hhjr")
    # threshold signing on the throwaway ceremony (never the Nov 1 one)
    tmp_ceremony = "/tmp/fg-test-ceremony"
    if not os.path.isdir(tmp_ceremony):
        skip("frostgate threshold sign", "no temp ceremony at "
             "/tmp/fg-test-ceremony")
        return
    msg = "00" * 31 + "01"
    r1 = frostgate.threshold_sign(tmp_ceremony, msg, (1, 2, 3))
    r2 = frostgate.threshold_sign(tmp_ceremony, msg, (2, 4, 5))
    check("frostgate threshold sign returns a 64-byte sig, verified",
          len(r1["signature"]) == 128 and r1["verified"] is True)
    check("frostgate different signer sets give different sigs",
          r1["signature"] != r2["signature"])
    addr = frostgate.vault_address(tmp_ceremony, "testnet")
    check("frostgate temp ceremony testnet address is tb1p…",
          addr.startswith("tb1p"))


# ============================================ broadcast + infancy (2026-11-14)
def _fork_send_fixture():
    """A locally-built, locally-verified fork send + its funding UTXO."""
    from txscript import lock_pkh_for_pubkey
    priv = 0x123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
    pub = keys.priv_to_pub_compressed(priv)
    lock = lock_pkh_for_pubkey(pub)
    funding = _fake_utxo(_funding_txid("bcast-fund"), 0, 10 * SWORD, lock)
    dest_lock = lock_pkh_for_pubkey(keys.priv_to_pub_compressed(0x9999))
    res = build_send([funding], {lock.hex(): priv}, dest_lock, 2 * SWORD,
                     lock, fee_rate=1, height=200)
    return res, funding, lock


def _bitcoin_shaped_raw():
    """A minimal Bitcoin-shaped tx (P2PKH output script). No signatures
    — the shape check is what is tested here; a real submit would be
    refused at testmempoolaccept, never at parse."""
    from txscript import ser_tx
    prev_display = hashlib.sha256(b"btc-prev").hexdigest()
    p2pkh = bytes.fromhex("76a914" + "11" * 20 + "88ac")
    t = {"version": 1,
         "vin": [{"prev": bytes.fromhex(prev_display)[::-1], "idx": 0,
                  "script": b"", "seq": 0xFFFFFFFF}],
         "vout": [{"value": 100_000, "script": p2pkh}],
         "locktime": 0}
    return ser_tx(t).hex(), prev_display


class _FakeForkRpc:
    """Fork node stub: tip, getutxos, sendrawtransaction, getrawmempool."""
    def __init__(self, funding, spendable=True):
        self.funding = funding
        self.spendable = spendable
        self.calls = []
        self.submitted = []

    def tip(self):
        return 199, "00" * 32

    def getutxos(self, lock):
        if not self.spendable:
            return []
        f = self.funding
        return [{"txid": f["txid"], "vout": f["vout"], "value": f["value"],
                 "mature": True, "coinbase": True}]

    def call(self, method, params=None):
        from txscript import txid_internal
        self.calls.append(method)
        if method == "sendrawtransaction":
            txid_int = txid_internal(bytes.fromhex(params[0])).hex()
            self.submitted.append(txid_int)
            return txid_int
        if method == "getrawmempool":
            return list(self.submitted)
        raise ValueError(method)


class _FakeBtcRpc:
    """Bitcoin Core stub: gettxout, testmempoolaccept, sendrawtransaction,
    getmempoolentry, getrawtransaction."""
    def __init__(self, allowed=True, reason=""):
        self.allowed = allowed
        self.reason = reason
        self.calls = []
        self.submitted = []

    def gettxout(self, txid, vout):
        return {"value": 0.001}

    def call(self, method, params=None):
        from txscript import txid_display
        self.calls.append(method)
        if method == "testmempoolaccept":
            return [{"txid": txid_display(bytes.fromhex(params[0])),
                     "allowed": self.allowed,
                     "reject-reason": self.reason or "ok"}]
        if method == "sendrawtransaction":
            txid = txid_display(bytes.fromhex(params[0]))
            self.submitted.append(txid)
            return txid
        if method == "getmempoolentry":
            return {"fees": {"base": 1000}} if params[0] in self.submitted \
                else None
        if method == "getrawtransaction":
            return None
        raise ValueError(method)


def test_broadcast_replay():
    from excalibur_wallet.broadcast import (
        parse_raw_tx, looks_like_fork_tx, check_replay_safe,
        BroadcastError)
    res, _funding, _lock = _fork_send_fixture()
    raw, parsed, txid, _ti = parse_raw_tx(res["raw_hex"])
    check("broadcast fork tx parses, txid matches build",
          txid == res["txid"])
    check("broadcast fork tx looks like a fork tx",
          looks_like_fork_tx(parsed))
    check("broadcast fork tx allowed on the fork path",
          check_replay_safe(parsed, "fork") == "fork")
    try:
        check_replay_safe(parsed, "bitcoin")
        check("broadcast fork tx refused on the bitcoin path", False)
    except BroadcastError:
        check("broadcast fork tx refused on the bitcoin path", True)
    btc_hex, _prev = _bitcoin_shaped_raw()
    _raw, btc_parsed, _t, _i = parse_raw_tx(btc_hex)
    check("broadcast bitcoin-shaped tx is not a fork tx",
          not looks_like_fork_tx(btc_parsed))
    check("broadcast bitcoin tx allowed on the bitcoin path",
          check_replay_safe(btc_parsed, "bitcoin") == "bitcoin")
    try:
        check_replay_safe(btc_parsed, "fork")
        check("broadcast bitcoin tx refused on the fork path", False)
    except BroadcastError:
        check("broadcast bitcoin tx refused on the fork path", True)
    try:
        parse_raw_tx("zz")
        check("broadcast bad hex refused", False)
    except BroadcastError:
        check("broadcast bad hex refused", True)
    try:
        parse_raw_tx("00" * 100001)
        check("broadcast oversize tx refused", False)
    except BroadcastError:
        check("broadcast oversize tx refused", True)


def test_broadcast_fork_fake_rpc():
    from excalibur_wallet.broadcast import broadcast_fork, BroadcastError
    res, funding, _lock = _fork_send_fixture()
    fake = _FakeForkRpc(funding)
    out = broadcast_fork(res["raw_hex"], rpc=fake, inputs=[funding],
                         height=200, dry_run=True)
    check("broadcast fork dry-run validates, does not submit",
          out["dry_run"] is True
          and "sendrawtransaction" not in fake.calls)
    out = broadcast_fork(res["raw_hex"], rpc=fake, inputs=[funding],
                         height=200)
    check("broadcast fork submits + verifies mempool",
          out["mempool"] is True and out["txid"] == res["txid"]
          and out["network"] == "fork")
    fake_spent = _FakeForkRpc(funding, spendable=False)
    try:
        broadcast_fork(res["raw_hex"], rpc=fake_spent, inputs=[funding],
                       height=200)
        check("broadcast fork refuses a spent input", False)
    except BroadcastError:
        check("broadcast fork refuses a spent input", True)


def test_broadcast_bitcoin_fake_rpc():
    from excalibur_wallet.broadcast import broadcast_bitcoin, BroadcastError
    btc_hex, _prev = _bitcoin_shaped_raw()
    fake = _FakeBtcRpc(allowed=True)
    out = broadcast_bitcoin(btc_hex, btc_rpc=fake)
    check("broadcast bitcoin submits + verifies mempool",
          out["mempool"] is True and out["network"] == "bitcoin")
    fake_dry = _FakeBtcRpc(allowed=True)
    out = broadcast_bitcoin(btc_hex, btc_rpc=fake_dry, dry_run=True)
    check("broadcast bitcoin dry-run does not submit",
          out["dry_run"] is True and fake_dry.submitted == [])
    # Replay: a fork tx to the bitcoin path refuses before any RPC call.
    res, _f, _l = _fork_send_fixture()
    fake_replay = _FakeBtcRpc(allowed=True)
    try:
        broadcast_bitcoin(res["raw_hex"], btc_rpc=fake_replay)
        check("broadcast bitcoin refuses a fork tx", False)
    except BroadcastError:
        check("broadcast bitcoin refuses a fork tx", True)
    check("broadcast bitcoin replay refusal touches no RPC",
          fake_replay.calls == [])
    fake_bad = _FakeBtcRpc(allowed=False,
                           reason="bad-txns-inputs-missingorspent")
    try:
        broadcast_bitcoin(btc_hex, btc_rpc=fake_bad)
        check("broadcast bitcoin refuses a mempool rejection", False)
    except BroadcastError:
        check("broadcast bitcoin refuses a mempool rejection", True)


def test_infancy():
    from excalibur_wallet import infancy as inf
    real_peer_tip = inf.peer_tip
    try:
        inf.peer_tip = lambda p, timeout=10: (100, "aa" * 32)
        res = inf.check_tip_agreement([("127.0.0.1", 9433)],
                                      rpc_tip=(100, "aa" * 32))
        check("infancy tip agreement: peer + RPC agree",
              res["ok"] is True and res["agreeing"] == 2)
        res = inf.check_tip_agreement([("127.0.0.1", 9433)])
        check("infancy tip agreement: single peer refused",
              res["ok"] is False)
        inf.peer_tip = lambda p, timeout=10: (
            100 if p[1] == 9433 else 101, "aa" * 32)
        res = inf.check_tip_agreement([("127.0.0.1", 9433),
                                       ("127.0.0.1", 9434)])
        check("infancy tip agreement: conflicting peers refused",
              res["ok"] is False)
    finally:
        inf.peer_tip = real_peer_tip
    ok, _d = inf.settled(6)
    check("infancy settled at 6 confirmations", ok is True)
    ok, _d = inf.settled(3)
    check("infancy not settled at 3 confirmations", ok is False)
    ok, _d = inf.settled(None)
    check("infancy unknown depth not settled", ok is False)
    rep = inf.security_report(tempfile.mkdtemp(prefix="excal-sec-"))
    by_name = {r["name"]: r["status"] for r in rep}
    check("infancy security report: replay PASS",
          by_name.get("replay (cross-chain)") == "PASS")
    check("infancy security report: no peers is WARN",
          by_name.get("eclipse (tip agreement)") == "WARN")


def test_cli_broadcast():
    tmp = tempfile.mkdtemp(prefix="excal-bcast-cli-")
    cli = [sys.executable, "-m", "excalibur_wallet"]

    def run(*args):
        return subprocess.run(cli + ["--datadir", tmp] + list(args),
                              capture_output=True, text=True, timeout=60)

    r = run("wallet", "broadcast", "--help")
    check("cli wallet broadcast --help works",
          r.returncode == 0 and "--yes" in r.stdout)
    r = run("wallet", "broadcast", "--network", "fork", "--tx", "00")
    check("cli wallet broadcast refuses without --yes",
          r.returncode != 0
          and "REFUSED without --yes" in (r.stdout + r.stderr))
    r = run("wallet", "security")
    check("cli wallet security prints the report",
          r.returncode == 0 and "replay" in r.stdout
          and "eclipse" in r.stdout)


def test_cli_smoke():
    tmp = tempfile.mkdtemp(prefix="excal-cli-smoke-")
    pwfile = os.path.join(tmp, "pw.txt")
    with open(pwfile, "w") as f:
        f.write("smoke-passphrase")
    os.chmod(pwfile, 0o600)
    datadir = os.path.join(tmp, "wallet-data")
    cli = [sys.executable, "-m", "excalibur_wallet"]

    def run(*args):
        return subprocess.run(cli + ["--datadir", datadir,
                                     "--passphrase-file", pwfile] + list(args),
                              capture_output=True, text=True, timeout=300)

    r = run("wallet", "create", "--words", "12")
    check("cli wallet create succeeds", r.returncode == 0
          and "first receive address" in r.stdout)
    r = run("wallet", "address")
    check("cli wallet address prints a PKH lock",
          r.returncode == 0 and r.stdout.strip().split(":")[-1].strip()
          .startswith("00"))
    r = run("wallet", "info")
    check("cli wallet info succeeds", r.returncode == 0
          and "kind: mnemonic" in r.stdout)
    r = run("wallet", "locks")
    check("cli wallet locks lists KNOT as staged",
          r.returncode == 0 and "KNOT" in r.stdout and "staged" in r.stdout)
    r = run("wallet", "split", "--threshold", "3", "--shares", "5")
    n_share_lines = sum(1 for ln in r.stdout.splitlines()
                        if ln.strip().startswith("share "))
    check("cli wallet split prints 5 shares",
          r.returncode == 0 and n_share_lines == 5)
    shares = [ln.split(": ", 1)[1].strip()
              for ln in r.stdout.splitlines()
              if ln.strip().startswith("share ")]
    datadir2 = os.path.join(tmp, "wallet-data-2")
    r2 = subprocess.run(cli + ["--datadir", datadir2,
                               "--passphrase-file", pwfile,
                               "wallet", "restore", "--shares"] + shares,
                        capture_output=True, text=True, timeout=120)
    check("cli wallet restore from SSS shares succeeds",
          r2.returncode == 0 and "first receive address" in r2.stdout)
    r = run("ledger", "tip")
    check("cli ledger tip prints a height",
          r.returncode == 0 and "height" in r.stdout)
    r = run("checkpoint", "verify")
    check("cli checkpoint verify finds the 43750 attestation",
          r.returncode == 0 and "43750" in r.stdout)
    r = run("frostgate", "status")
    check("cli frostgate status shows the Nov 1 vault",
          r.returncode == 0 and "3-of-5" in r.stdout)
    r = run("frostgate", "address")
    check("cli frostgate address prints tb1p…",
          r.returncode == 0 and "tb1p" in r.stdout)
    r = run("node", "status")
    check("cli node status runs", r.returncode == 0
          and ("fork node" in r.stdout))


def main():
    test_bip39()
    test_keys()
    test_sss()
    test_wallet_file()
    test_txbuild()
    test_htlc()
    test_qhtlc_pqh()
    test_knot()
    test_locks()
    test_live_chain()
    test_live_checkpoints()
    test_live_uruu()
    test_live_frostgate()
    test_broadcast_replay()
    test_broadcast_fork_fake_rpc()
    test_broadcast_bitcoin_fake_rpc()
    test_infancy()
    test_cli_broadcast()
    test_cli_smoke()
    print()
    print(f"PASSED: {len(PASSED)}  FAILED: {len(FAILED)}  "
          f"SKIPPED: {len(SKIPPED)}")
    if FAILED:
        print("failures:")
        for f in FAILED:
            print(f"  - {f}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
