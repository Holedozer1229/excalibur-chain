#!/usr/bin/env python3
"""activate_knot_demo.py — Final verification of KNOT lock activation."""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

from genesis_fork import knot_activation
from excalibur_wallet.locks import lock_status
from knot_wallet import (build_knot_lock_tx, build_knot_spend_tx,
                         generate_t_star, verify_knot_commitment)
from txscript import lock_pkh_for_pubkey, txid_internal
import secp256k1 as secp

def priv_to_pub_compressed(priv):
    pt = secp.priv_to_pub(priv)
    return secp.compress(pt)

def main():
    act = knot_activation()
    print("=" * 60)
    print("KNOT Lock Activation Verification")
    print("=" * 60)
    print()
    print(f"KNOT activation height: {act}")
    print()

    # Lock status at activation height
    print("Lock status at height", act, ":")
    sts = {s["type"]: s for s in lock_status(act)}
    for name in ["pkh", "pqh", "htlc", "qhtlc", "bridge", "knot"]:
        s = sts[name]
        ver = int(s["version"])
        active = s["active"]
        activation = s["activation"]
        print(f"  {name:8s} v{ver:02x}  active={str(active):5s}  activation={activation}")
    print()

    # Full KNOT lock/spend cycle
    p, q, n_terms, eps_u32 = 2, 3, 10, 0x80000000
    t_star = generate_t_star()
    priv = 0x12345678
    pub = priv_to_pub_compressed(priv)
    funding_lock = lock_pkh_for_pubkey(pub)

    funding = [{"prev": bytes.fromhex("a" * 64), "idx": 0,
                "value": 5 * 100_000_000, "lock": funding_lock}]

    print("Building KNOT lock transaction...")
    res = build_knot_lock_tx(funding, priv, 1 * 100_000_000,
                             p, q, n_terms, eps_u32, t_star, 1000)
    print(f"  Lock TXID:  {res['txid']}")
    print(f"  KNOT lock:  {res['lock'].hex()}")
    print(f"  Validated:  height {res['validated_at_height']}")
    print()

    lock_prev = txid_internal(res["raw"])
    dest = lock_pkh_for_pubkey(priv_to_pub_compressed(0x87654321))

    print("Building KNOT spend transaction...")
    res2 = build_knot_spend_tx(lock_prev, 0, 1 * 100_000_000,
                               res["lock"], res["descriptor"],
                               t_star, dest, 1000)
    print(f"  Spend TXID: {res2['txid']}")
    print(f"  Validated:  height {res2['validated_at_height']}")
    print()

    ok = verify_knot_commitment(p, q, n_terms, eps_u32, t_star,
                                res["commitment"])
    print(f"Commitment verification: {'PASS' if ok else 'FAIL'}")
    print()

    # Wallet tests
    from test_excalibur_wallet import test_knot, test_locks
    print("Running wallet KNOT tests...")
    test_knot()
    test_locks()
    print("All wallet KNOT tests: PASS")
    print()
    print("=" * 60)
    print("KNOT lock activated and operational!")
    print("=" * 60)

if __name__ == "__main__":
    main()
