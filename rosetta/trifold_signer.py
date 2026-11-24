"""Local Rosetta signer bridge for the EXCAL wallet's native Trifold key.

The caller must pass an already-unlocked EXCAL Wallet object. This module
never reads a mnemonic, prompts for a passphrase, sends secrets over HTTP,
or bypasses the wallet's durable Trifold counter / spent-leaf registry.
"""
from txscript import (
    parse_tx, sighash_all, lock_pqh_for_root, lock_qhtlc_for_descriptor,
    parse_qhtlc_descriptor, sign_qhtlc_claim, sign_qhtlc_refund,
)
from txpq import sign_pqh_input


class TrifoldSignerError(Exception):
    pass


class ExcalTrifoldRosettaSigner:
    def __init__(self, wallet, registry=None):
        if not callable(getattr(wallet, "trifold_key", None)):
            raise TrifoldSignerError("an unlocked EXCAL Wallet with trifold_key() is required")
        self.wallet = wallet
        self.registry = registry

    def sign_payload(self, unsigned_transaction, input_index, lock_hex,
                     signature_type, mode=None, descriptor_hex=None,
                     secret_hex=None, spend_height=None):
        """Return a Rosetta Signature object for PQH or QHTLC.

        For QHTLC, mode is 'claim' or 'refund'; descriptor_hex is required,
        and secret_hex is required only for claim. The complete native
        scriptSig witness is returned in Signature.hex_bytes.
        """
        raw = bytes.fromhex(unsigned_transaction)
        tx = parse_tx(raw)
        i = int(input_index)
        if i < 0 or i >= len(tx["vin"]):
            raise TrifoldSignerError("input_index out of range")
        lock = bytes.fromhex(lock_hex)
        digest = sighash_all(tx, i, lock)
        key = self.wallet.trifold_key()

        if signature_type == "trifold-pqh":
            if lock_pqh_for_root(key.root) != lock:
                raise TrifoldSignerError("wallet Trifold root does not match PQH lock")
            witness = sign_pqh_input(key, digest, registry=self.registry)
            ros_type = "trifold"
        elif signature_type == "trifold-qhtlc":
            if not descriptor_hex:
                raise TrifoldSignerError("QHTLC descriptor is required")
            desc = bytes.fromhex(descriptor_hex)
            d = parse_qhtlc_descriptor(desc)
            if lock_qhtlc_for_descriptor(desc) != lock:
                raise TrifoldSignerError("QHTLC descriptor does not match lock")
            if mode == "claim":
                if not secret_hex:
                    raise TrifoldSignerError("QHTLC claim requires secret_hex")
                secret = bytes.fromhex(secret_hex)
                if len(secret) != 32:
                    raise TrifoldSignerError("QHTLC claim secret must be 32 bytes")
                import hashlib
                if hashlib.sha256(secret).digest() != d["secret_hash"]:
                    raise TrifoldSignerError("QHTLC claim secret does not match descriptor")
                witness = sign_qhtlc_claim(
                    tx, i, lock, key, bytes.fromhex(secret_hex), desc,
                    registry=self.registry)
            elif mode == "refund":
                if spend_height is None:
                    raise TrifoldSignerError("QHTLC refund requires target spend_height")
                if int(spend_height) < int(d["timeout"]):
                    raise TrifoldSignerError("QHTLC refund timeout has not matured; refusing to burn a Trifold leaf")
                witness = sign_qhtlc_refund(
                    tx, i, lock, key, desc, registry=self.registry)
            else:
                raise TrifoldSignerError("QHTLC mode must be claim or refund")
            ros_type = "trifold"
        else:
            raise TrifoldSignerError("unsupported Trifold signing request")

        return {
            "signing_payload": {
                "account_identifier": {"address": "lock:" + lock.hex()},
                "hex_bytes": digest.hex(),
                "signature_type": ros_type,
            },
            "signature_type": ros_type,
            "hex_bytes": witness.hex(),
        }
