"""Rosetta KNOT preimage-witness bridge for EXCAL.

KNOT is a staged preimage lock, not a public-key signature. This helper
builds the exact 56-byte native witness and verifies the descriptor
commitment before returning the chain-specific Rosetta extension object.
"""
from txscript import parse_tx, sighash_all, sign_knot_input, lock_knot_for_descriptor
from genesis_fork import knot_activation


class KnotSignerError(Exception):
    pass


def build_knot_signature(unsigned_transaction, input_index, lock_hex,
                         t_star_hex, descriptor_hex, spend_height):
    tx = parse_tx(bytes.fromhex(unsigned_transaction))
    i = int(input_index)
    if i < 0 or i >= len(tx["vin"]):
        raise KnotSignerError("input_index out of range")
    if int(spend_height) < knot_activation():
        raise KnotSignerError("KNOT is not activated at target spend height")
    lock = bytes.fromhex(lock_hex)
    descriptor = bytes.fromhex(descriptor_hex)
    t_star = int.from_bytes(bytes.fromhex(t_star_hex), "big")
    if len(bytes.fromhex(t_star_hex)) != 16:
        raise KnotSignerError("t_star must be exactly 16 bytes")
    if lock_knot_for_descriptor(descriptor) != lock:
        raise KnotSignerError("KNOT descriptor does not match lock")
    witness = sign_knot_input(tx, i, lock, t_star, descriptor)
    digest = sighash_all(tx, i, lock)
    return {
        "signing_payload": {
            "account_identifier": {"address": "lock:" + lock.hex()},
            "hex_bytes": digest.hex(),
            "signature_type": "excal_knot",
        },
        "signature_type": "excal_knot",
        "hex_bytes": witness.hex(),
    }
