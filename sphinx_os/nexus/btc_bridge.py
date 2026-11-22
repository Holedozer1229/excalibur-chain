#!/usr/bin/env python3
"""
AetherionEXCAL BTC Bridge — EXCAL ↔ Bitcoin atomic HTLC bridge for wallets.

Wraps AtomicSwapProtocol and builds Bitcoin P2WSH HTLC lock parameters so
AetherionEXCAL.exe can propose, track, and complete cross-chain swaps over
SkyNet, while keeping Bitcoin transaction signing local to the wallet or its
configured Bitcoin Core wallet.
"""

from __future__ import annotations

import hashlib
import base64
import json
import logging
import os
import struct
import time
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_CEILING
from typing import Dict, List, Optional, Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from .atomic_swap import (
    AtomicSwapProtocol,
    AtomicSwap,
    AtomicSwapError,
    SwapDirection,
    SwapStatus,
    BTC_REFUND_BLOCKS,
    EXCAL_REFUND_BLOCKS,
)

logger = logging.getLogger("btc_bridge")


def bitcoin_network_params(network: Optional[str] = None) -> tuple:
    """Return Bitcoin address HRP and WIF prefix for the configured network."""
    network = network or os.environ.get("AETHERION_BTC_NETWORK", "main")
    params = {
        "main": ("bc", 0x80),
        "test": ("tb", 0xEF),
        "signet": ("tb", 0xEF),
        "regtest": ("bcrt", 0xEF),
    }
    if network not in params:
        raise ValueError("AETHERION_BTC_NETWORK must be main, test, signet, or regtest")
    return params[network]


BITCOIN_GENESIS_HASHES = {
    "main": "000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f",
    "test": "000000000933ea01ad0ee984209779baaec3ced90fa3f408719526f8d77f4943",
    "signet": "00000008819873e925422c1ff0f99f7cc9bbb232af63a077a480a3633bee1ef6",
    "regtest": "0f9188f13cb7b2c71f2a335e3a4fc328bf5beb436012afca590b1a11466e2206",
}


class BitcoinCoreRPC:
    """Bitcoin Core RPC client for verifying, funding, and broadcasting BTC HTLCs."""

    def __init__(self, timeout: int = 15, config: Optional[dict] = None):
        config = config or {}
        self.network = config.get(
            "network", os.environ.get("AETHERION_BTC_NETWORK", "main")
        )
        self.url = config.get(
            "rpc_url",
            os.environ.get("AETHERION_BTC_RPC_URL", "http://127.0.0.1:8332"),
        )
        wallet = config.get("wallet", os.environ.get("AETHERION_BTC_RPC_WALLET"))
        self.wallet_url = (
            self.url.rstrip("/") + "/wallet/" + quote(wallet, safe="")
            if wallet else None
        )
        self.timeout = timeout
        parsed = urlparse(self.url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise ValueError("AETHERION_BTC_RPC_URL must be an HTTP(S) URL")
        if parsed.scheme != "https" and parsed.hostname not in (
            "127.0.0.1", "localhost", "::1"
        ):
            raise ValueError("Bitcoin Core RPC on non-local hosts requires HTTPS")
        self._auth = self._load_auth(config)

    @staticmethod
    def _load_auth(config: Optional[dict] = None) -> str:
        config = config or {}
        cookie_path = config.get(
            "cookie_file", os.environ.get("AETHERION_BTC_RPC_COOKIE_FILE")
        )
        if cookie_path:
            with open(cookie_path, encoding="utf-8") as cookie_file:
                token = cookie_file.read().strip()
            if ":" not in token:
                raise ValueError("Bitcoin Core RPC cookie has an invalid format")
        else:
            user = config.get("rpc_user", os.environ.get("AETHERION_BTC_RPC_USER"))
            password = config.get(
                "rpc_password", os.environ.get("AETHERION_BTC_RPC_PASSWORD")
            )
            if not user or not password:
                raise RuntimeError(
                    "Configure Bitcoin Core RPC with AETHERION_BTC_RPC_COOKIE_FILE "
                    "or AETHERION_BTC_RPC_USER and AETHERION_BTC_RPC_PASSWORD"
                )
            token = f"{user}:{password}"
        return "Basic " + base64.b64encode(token.encode("utf-8")).decode("ascii")

    def _call_url(self, url: str, method: str, params: Optional[list] = None) -> Any:
        payload = json.dumps({
            "jsonrpc": "2.0",
            "id": "aetherion-excal",
            "method": method,
            "params": params or [],
        }).encode("utf-8")
        request = Request(
            url,
            data=payload,
            headers={
                "Authorization": self._auth,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise RuntimeError(f"Bitcoin Core RPC HTTP error {exc.code}") from exc
        except URLError as exc:
            raise RuntimeError("Unable to connect to Bitcoin Core RPC") from exc
        if result.get("error"):
            error = result["error"]
            raise RuntimeError(
                f"Bitcoin Core RPC {method} failed: {error.get('message', 'unknown error')}"
            )
        return result.get("result")

    def call(self, method: str, params: Optional[list] = None) -> Any:
        return self._call_url(self.url, method, params)

    def call_wallet(self, method: str, params: Optional[list] = None) -> Any:
        if not self.wallet_url:
            raise RuntimeError(
                "Set AETHERION_BTC_RPC_WALLET to a loaded, funded Bitcoin Core wallet "
                "to sign and broadcast BTC funding transactions"
            )
        return self._call_url(self.wallet_url, method, params)

    def _check_network(self) -> dict:
        expected_network = self.network
        bitcoin_network_params(expected_network)
        if expected_network not in BITCOIN_GENESIS_HASHES:
            raise ValueError(f"No canonical Bitcoin genesis hash is configured for {expected_network}")
        network = self.call("getblockchaininfo")
        if network.get("chain") != expected_network:
            raise RuntimeError(
                f"Bitcoin Core network is {network.get('chain')!r}; "
                f"expected {expected_network!r}"
            )
        genesis_hash = self.call("getblockhash", [0])
        expected_genesis = BITCOIN_GENESIS_HASHES[expected_network]
        if genesis_hash != expected_genesis:
            raise RuntimeError(
                f"Bitcoin Core genesis hash is {genesis_hash!r}; "
                f"expected {expected_genesis!r} for {expected_network!r}"
            )
        return network

    def get_tip_height(self) -> int:
        """Return the block height after confirming the configured network."""
        self._check_network()
        height = self.call("getblockcount")
        if not isinstance(height, int) or height < 0:
            raise RuntimeError("Bitcoin Core returned an invalid block height")
        return height

    def prepare_funding(self, address: str, amount_sats: int) -> dict:
        """Create an unsigned funding PSBT and return Core's exact fee quote."""
        if amount_sats <= 0:
            raise ValueError("Bitcoin HTLC amount must be positive")
        self._check_network()
        amount_btc = float(Decimal(amount_sats) / Decimal(100_000_000))
        result = self.call_wallet(
            "walletcreatefundedpsbt",
            [[], [{address: amount_btc}], 0, {"lockUnspents": False}, True],
        )
        if not isinstance(result, dict) or not result.get("psbt"):
            raise RuntimeError("Bitcoin Core did not return a funding PSBT")
        fee = Decimal(str(result.get("fee", 0))) * 100_000_000
        if fee != fee.to_integral_value() or fee < 0:
            raise RuntimeError("Bitcoin Core returned an invalid funding fee")
        return {
            "psbt": result["psbt"],
            "fee_sats": int(fee),
            "address": address,
            "amount_sats": amount_sats,
        }

    def broadcast_funding(self, psbt: str, script_pubkey: str, amount_sats: int) -> dict:
        """Sign and broadcast a prepared PSBT using the configured Core wallet."""
        self._check_network()
        processed = self.call_wallet("walletprocesspsbt", [psbt])
        if not isinstance(processed, dict) or not processed.get("complete"):
            raise RuntimeError("Bitcoin Core wallet could not sign the funding transaction")
        finalized = self.call_wallet("finalizepsbt", [processed["psbt"]])
        if (
            not isinstance(finalized, dict)
            or not finalized.get("complete")
            or not finalized.get("hex")
        ):
            raise RuntimeError("Bitcoin Core could not finalize the funding transaction")
        decoded = self.call("decoderawtransaction", [finalized["hex"]])
        matching = []
        for output in decoded.get("vout", []):
            output_script = output.get("scriptPubKey", {}).get("hex", "").lower()
            output_value = Decimal(str(output.get("value", 0))) * 100_000_000
            if output_script == script_pubkey.lower() and output_value == amount_sats:
                matching.append(output.get("n"))
        if len(matching) != 1 or not isinstance(matching[0], int):
            raise RuntimeError("Signed funding transaction does not contain one exact HTLC output")
        txid = self.call("sendrawtransaction", [finalized["hex"]])
        if txid != decoded.get("txid"):
            raise RuntimeError("Bitcoin Core returned a mismatched funding transaction ID")
        return {"txid": txid, "vout": matching[0]}

    def estimate_fee_rate(self, confirmation_target: int = 6) -> int:
        """Return the greater of the node's estimated and relay fee rates, in sat/vB."""
        estimate = self.call("estimatesmartfee", [confirmation_target])
        if not isinstance(estimate, dict) or estimate.get("feerate") is None:
            raise RuntimeError("Bitcoin Core has no fee estimate for BTC transaction signing")
        relay = self.call("getmempoolinfo")
        try:
            estimate_rate = Decimal(str(estimate["feerate"])) * 100_000
            relay_rate = Decimal(str(relay["minrelaytxfee"])) * 100_000
        except (KeyError, ArithmeticError, ValueError) as exc:
            raise RuntimeError("Bitcoin Core returned an invalid fee estimate") from exc
        if not estimate_rate.is_finite() or not relay_rate.is_finite():
            raise RuntimeError("Bitcoin Core returned a non-finite fee estimate")
        rate = int(max(estimate_rate, relay_rate).to_integral_value(rounding=ROUND_CEILING))
        if rate < 1:
            raise RuntimeError("Bitcoin Core fee estimate is below 1 sat/vB")
        return rate

    def broadcast_spend(
        self,
        txid: str,
        vout: int,
        amount_sats: int,
        witness_script: bytes,
        destination_script: bytes,
        private_key: bytes,
        expected_pubkey: bytes,
        fee_sats: int,
        secret_preimage: Optional[bytes] = None,
        refund_height: Optional[int] = None,
    ) -> dict:
        """Sign and broadcast a single-input P2WSH HTLC claim or refund."""
        self._check_network()
        funding = self.call("getrawtransaction", [txid, True])
        if funding.get("txid", "").lower() != txid.lower():
            raise RuntimeError("Bitcoin Core returned a different funding transaction ID")
        if not isinstance(funding.get("confirmations"), int) or funding["confirmations"] < 1:
            raise RuntimeError("Bitcoin HTLC funding transaction is not confirmed")
        outputs = funding.get("vout", [])
        if not isinstance(vout, int) or not 0 <= vout < len(outputs):
            raise ValueError("Bitcoin funding output index is out of range")
        output = outputs[vout]
        expected_script = (bytes([OP_0]) + _push(hashlib.sha256(witness_script).digest())).hex()
        if output.get("scriptPubKey", {}).get("hex", "").lower() != expected_script:
            raise RuntimeError("Bitcoin funding output does not match the HTLC witness script")
        actual_amount = Decimal(str(output.get("value", 0))) * 100_000_000
        if actual_amount != amount_sats:
            raise RuntimeError("Bitcoin HTLC output amount does not match the recorded swap")
        if refund_height is not None:
            tip = self.get_tip_height()
            if tip < refund_height:
                raise RuntimeError(
                    f"Bitcoin refund timeout has not been reached (tip {tip}, timeout {refund_height})"
                )
        if fee_sats <= 0 or fee_sats >= amount_sats:
            raise ValueError("Bitcoin transaction fee must be positive and less than the HTLC amount")

        raw_tx, spent_txid, actual_fee = sign_htlc_spend(
            txid=txid,
            vout=vout,
            amount_sats=amount_sats,
            destination_script=destination_script,
            witness_script=witness_script,
            private_key=private_key,
            expected_pubkey=expected_pubkey,
            fee_sats=fee_sats,
            secret_preimage=secret_preimage,
            refund_height=refund_height,
        )
        broadcast_txid = self.call("sendrawtransaction", [raw_tx])
        if broadcast_txid != spent_txid:
            raise RuntimeError("Bitcoin Core returned a mismatched spend transaction ID")
        return {"txid": broadcast_txid, "fee_sats": actual_fee}

    def verify_funding(self, txid: str, vout: int, script_pubkey: str, amount_sats: int) -> dict:
        """Require a confirmed, exact-value HTLC output on the configured Bitcoin network."""
        if len(txid) != 64 or any(c not in "0123456789abcdefABCDEF" for c in txid):
            raise ValueError("Bitcoin transaction ID must be 64 hexadecimal characters")
        if amount_sats <= 0:
            raise ValueError("Bitcoin HTLC amount must be positive")
        self._check_network()
        transaction = self.call("getrawtransaction", [txid, True])
        if transaction.get("txid", "").lower() != txid.lower():
            raise RuntimeError("Bitcoin Core returned a different transaction ID")
        confirmations = transaction.get("confirmations", 0)
        if not isinstance(confirmations, int) or confirmations < 1:
            raise RuntimeError("Bitcoin HTLC funding transaction is not confirmed")
        outputs = transaction.get("vout", [])
        if not isinstance(vout, int) or not 0 <= vout < len(outputs):
            raise ValueError("Bitcoin funding output index is out of range")
        output = outputs[vout]
        actual_script = output.get("scriptPubKey", {}).get("hex", "").lower()
        if actual_script != script_pubkey.lower():
            raise RuntimeError("Bitcoin output script does not match the swap HTLC")
        amount = Decimal(str(output.get("value", 0))) * 100_000_000
        if amount != amount.to_integral_value():
            raise RuntimeError("Bitcoin Core returned an invalid BTC amount precision")
        actual_sats = int(amount)
        if actual_sats != amount_sats:
            raise RuntimeError(
                f"Bitcoin HTLC output is {actual_sats} satoshis; expected {amount_sats}"
            )
        return {"txid": txid, "vout": vout, "confirmations": confirmations}

    def verify_spend(
        self,
        txid: str,
        funding_txid: str,
        funding_vout: int,
        witness_script: bytes,
        secret_hash: Optional[bytes] = None,
        refund_height: Optional[int] = None,
    ) -> dict:
        """Verify a confirmed HTLC spend and its claim preimage or refund locktime."""
        self._check_network()
        if len(txid) != 64 or any(c not in "0123456789abcdefABCDEF" for c in txid):
            raise ValueError("Bitcoin transaction ID must be 64 hexadecimal characters")
        transaction = self.call("getrawtransaction", [txid, True])
        if transaction.get("txid", "").lower() != txid.lower():
            raise RuntimeError("Bitcoin Core returned a different transaction ID")
        if not isinstance(transaction.get("confirmations"), int) or transaction["confirmations"] < 1:
            raise RuntimeError("Bitcoin HTLC spend transaction is not confirmed")
        matching_inputs = [
            item for item in transaction.get("vin", [])
            if item.get("txid", "").lower() == funding_txid.lower()
            and item.get("vout") == funding_vout
        ]
        if not matching_inputs:
            raise RuntimeError("Bitcoin transaction does not spend the recorded HTLC output")

        expected_script = witness_script.hex()
        if not any(
            item.get("txinwitness", [])
            and item["txinwitness"][-1].lower() == expected_script
            for item in matching_inputs
        ):
            raise RuntimeError("Bitcoin spend does not use the recorded HTLC witness script")

        if secret_hash is not None:
            if len(secret_hash) != 32:
                raise ValueError("HTLC secret hash must be 32 bytes")
            for item in matching_inputs:
                witness = item.get("txinwitness", [])
                if len(witness) < 3 or witness[-2] not in ("01", "1"):
                    continue
                for witness_item in witness[:-2]:
                    try:
                        preimage = bytes.fromhex(witness_item)
                    except ValueError:
                        continue
                    if hashlib.sha256(preimage).digest() == secret_hash:
                        return {
                            "txid": txid,
                            "confirmations": transaction["confirmations"],
                        }
            raise RuntimeError("Bitcoin HTLC claim witness does not reveal the correct preimage")

        if refund_height is not None:
            if transaction.get("locktime", 0) < refund_height:
                raise RuntimeError("Bitcoin refund transaction locktime is before the HTLC timeout")
            if any(item.get("sequence", 0xFFFFFFFF) == 0xFFFFFFFF for item in matching_inputs):
                raise RuntimeError("Bitcoin refund input disables the required locktime")
            if not any(
                len(item.get("txinwitness", [])) >= 3
                and item["txinwitness"][-2] == ""
                and item["txinwitness"][-1].lower() == expected_script
                for item in matching_inputs
            ):
                raise RuntimeError("Bitcoin spend does not use the HTLC refund branch")
            block_hash = transaction.get("blockhash")
            if not block_hash:
                raise RuntimeError("Bitcoin Core did not return the confirmed spend block")
            block = self.call("getblockheader", [block_hash, True])
            if block.get("height", -1) <= refund_height:
                raise RuntimeError("Bitcoin HTLC refund timeout has not been reached")
        return {"txid": txid, "confirmations": transaction["confirmations"]}


def _compact_size(value: int) -> bytes:
    if value < 0:
        raise ValueError("CompactSize value cannot be negative")
    if value < 253:
        return bytes([value])
    if value <= 0xFFFF:
        return b"\xfd" + struct.pack("<H", value)
    if value <= 0xFFFFFFFF:
        return b"\xfe" + struct.pack("<I", value)
    return b"\xff" + struct.pack("<Q", value)


def _varbytes(value: bytes) -> bytes:
    return _compact_size(len(value)) + value


def _double_sha256(value: bytes) -> bytes:
    return hashlib.sha256(hashlib.sha256(value).digest()).digest()


def estimate_htlc_spend_vsize(
    witness_script: bytes, destination_script: bytes, claiming: bool
) -> int:
    """Estimate a P2WSH HTLC spend vsize conservatively using a 73-byte signature."""
    sequence = 0xFFFFFFFD if claiming else 0xFFFFFFFE
    prevout = b"\x00" * 36
    output = struct.pack("<Q", 1) + _varbytes(destination_script)
    stripped = (
        struct.pack("<I", 2) + b"\x01" + prevout + b"\x00"
        + struct.pack("<I", sequence) + b"\x01" + output + b"\x00" * 4
    )
    stack_lengths = [73, 32, 1, len(witness_script)] if claiming else [
        73, 0, len(witness_script)
    ]
    witness_size = len(_compact_size(len(stack_lengths))) + sum(
        len(_varbytes(b"\x00" * size)) for size in stack_lengths
    )
    weight = len(stripped) * 4 + 2 + witness_size
    return (weight + 3) // 4


def sign_htlc_spend(
    txid: str,
    vout: int,
    amount_sats: int,
    destination_script: bytes,
    witness_script: bytes,
    private_key: bytes,
    expected_pubkey: bytes,
    fee_sats: int,
    secret_preimage: Optional[bytes] = None,
    refund_height: Optional[int] = None,
) -> tuple:
    """Build and locally sign one native-SegWit HTLC claim or refund."""
    if (secret_preimage is None) == (refund_height is None):
        raise ValueError("Choose exactly one HTLC branch")
    if len(private_key) != 32 or len(expected_pubkey) != 33:
        raise ValueError("HTLC signing requires a 32-byte key and compressed public key")
    if len(txid) != 64 or any(c not in "0123456789abcdefABCDEF" for c in txid):
        raise ValueError("Bitcoin transaction ID must be 64 hexadecimal characters")
    if not 0 <= vout <= 0xFFFFFFFF or amount_sats <= fee_sats:
        raise ValueError("Bitcoin HTLC outpoint or amount is invalid")
    if not destination_script or not witness_script:
        raise ValueError("Bitcoin destination and HTLC witness scripts are required")
    if secret_preimage is not None:
        if (
            len(secret_preimage) != 32
            or not witness_script.startswith(b"\x63\xa8\x20")
            or witness_script[35:37] != b"\x88\x21"
            or witness_script[70:72] != b"\xac\x67"
            or hashlib.sha256(secret_preimage).digest() != witness_script[3:35]
            or expected_pubkey != witness_script[37:70]
        ):
            raise ValueError("HTLC claim preimage does not match the witness script")
    else:
        if not isinstance(refund_height, int) or not 1 <= refund_height < LOCKTIME_THRESHOLD:
            raise ValueError("Bitcoin refund height must be a valid block height")
        if (
            len(witness_script) < 36
            or witness_script[-36] != 0x21
            or witness_script[-35:-2] != expected_pubkey
            or witness_script[-2:] != b"\xac\x68"
        ):
            raise ValueError("The wallet key does not match the HTLC refund branch")

    try:
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import ec, utils
        from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    except ImportError as exc:
        raise RuntimeError("Bitcoin transaction signing requires the cryptography package") from exc

    signing_key = ec.derive_private_key(int.from_bytes(private_key, "big"), ec.SECP256K1())
    actual_pubkey = signing_key.public_key().public_bytes(
        Encoding.X962, PublicFormat.CompressedPoint
    )
    if actual_pubkey != expected_pubkey:
        raise ValueError("The unlocked wallet key does not match the HTLC public key")

    prevout = bytes.fromhex(txid)[::-1] + struct.pack("<I", vout)
    sequence = 0xFFFFFFFD if secret_preimage is not None else 0xFFFFFFFE
    locktime = 0 if secret_preimage is not None else refund_height
    serialized_output = struct.pack("<Q", amount_sats - fee_sats) + _varbytes(destination_script)
    digest_preimage = (
        struct.pack("<I", 2)
        + _double_sha256(prevout)
        + _double_sha256(struct.pack("<I", sequence))
        + prevout
        + _varbytes(witness_script)
        + struct.pack("<Q", amount_sats)
        + struct.pack("<I", sequence)
        + _double_sha256(serialized_output)
        + struct.pack("<I", locktime)
        + struct.pack("<I", 1)
    )
    digest = _double_sha256(digest_preimage)
    signature = signing_key.sign(digest, ec.ECDSA(utils.Prehashed(hashes.SHA256())))
    r, s = utils.decode_dss_signature(signature)
    order = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
    if s > order // 2:
        s = order - s
    signature = utils.encode_dss_signature(r, s) + b"\x01"

    stripped = (
        struct.pack("<I", 2)
        + _compact_size(1)
        + prevout
        + b"\x00"
        + struct.pack("<I", sequence)
        + _compact_size(1)
        + serialized_output
        + struct.pack("<I", locktime)
    )
    witness_items = (
        [signature, secret_preimage, b"\x01", witness_script]
        if secret_preimage is not None
        else [signature, b"", witness_script]
    )
    witness = _compact_size(len(witness_items)) + b"".join(
        _varbytes(item) for item in witness_items
    )
    raw_tx = (
        struct.pack("<I", 2)
        + b"\x00\x01"
        + _compact_size(1)
        + prevout
        + b"\x00"
        + struct.pack("<I", sequence)
        + _compact_size(1)
        + serialized_output
        + witness
        + struct.pack("<I", locktime)
    )
    return raw_tx.hex(), _double_sha256(stripped)[::-1].hex(), fee_sats


# Bitcoin script opcodes used by the HTLC
OP_0 = 0x00
OP_IF = 0x63
OP_ELSE = 0x67
OP_ENDIF = 0x68
OP_DROP = 0x75
OP_EQUALVERIFY = 0x88
OP_SHA256 = 0xA8
OP_CHECKSIG = 0xAC
OP_CHECKLOCKTIMEVERIFY = 0xB1
LOCKTIME_THRESHOLD = 500_000_000

CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"


def _push(data: bytes) -> bytes:
    n = len(data)
    if n < 76:
        return bytes([n]) + data
    if n <= 255:
        return bytes([76, n]) + data
    raise ValueError("push too large")


def _encode_num(n: int) -> bytes:
    if n == 0:
        return b""
    neg = n < 0
    abs_n = -n if neg else n
    result = bytearray()
    while abs_n:
        result.append(abs_n & 0xFF)
        abs_n >>= 8
    if result[-1] & 0x80:
        result.append(0x80 if neg else 0x00)
    elif neg:
        result[-1] |= 0x80
    return bytes(result)


def _bech32_polymod(values):
    GEN = [0x3b6a57b2, 0x26508e6d, 0x1ea119fa, 0x3d4233dd, 0x2a1462b3]
    chk = 1
    for v in values:
        b = chk >> 25
        chk = ((chk & 0x1ffffff) << 5) ^ v
        for i in range(5):
            chk ^= GEN[i] if ((b >> i) & 1) else 0
    return chk


def _bech32_hrp_expand(hrp: str):
    return [ord(x) >> 5 for x in hrp] + [0] + [ord(x) & 31 for x in hrp]


def _bech32_create_checksum(hrp: str, data, bech32m=False):
    """Create bech32 or bech32m checksum.

    BIP-173 bech32: polymod(data + checksum) ^ 1
    BIP-350 bech32m: polymod(data + checksum) ^ 0x2bc830a3
    """
    values = _bech32_hrp_expand(hrp) + data
    const = 0x2bc830a3 if bech32m else 1
    polymod = _bech32_polymod(values + [0, 0, 0, 0, 0, 0]) ^ const
    return [(polymod >> 5 * (5 - i)) & 31 for i in range(6)]


def _convertbits(data, frombits, tobits, pad=True):
    acc = 0
    bits = 0
    ret = []
    maxv = (1 << tobits) - 1
    for value in data:
        if value < 0 or (value >> frombits):
            return None
        acc = (acc << frombits) | value
        bits += frombits
        while bits >= tobits:
            bits -= tobits
            ret.append((acc >> bits) & maxv)
    if pad:
        if bits:
            ret.append((acc << (tobits - bits)) & maxv)
    elif bits >= frombits or ((acc << (tobits - bits)) & maxv):
        return None
    return ret


def bech32_encode(hrp: str, witver: int, witprog: bytes) -> str:
    """BIP-173 bech32 encode (for witness version 0)."""
    data = [witver] + _convertbits(list(witprog), 8, 5)
    combined = data + _bech32_create_checksum(hrp, data, bech32m=False)
    return hrp + "1" + "".join([CHARSET[d] for d in combined])


def bech32m_encode(hrp: str, witver: int, witprog: bytes) -> str:
    """BIP-350 bech32m encode (for witness version 1+ / Taproot)."""
    data = [witver] + _convertbits(list(witprog), 8, 5)
    combined = data + _bech32_create_checksum(hrp, data, bech32m=True)
    return hrp + "1" + "".join([CHARSET[d] for d in combined])


def bech32_decode(addr: str):
    """BIP-173 bech32 decode. Returns (hrp, witver, program_bytes)."""
    addr = addr.lower()
    pos = addr.rfind("1")
    if pos < 1 or pos + 7 > len(addr):
        raise ValueError("bad bech32 address")
    hrp, tail = addr[:pos], addr[pos + 1:]
    vals = [CHARSET.index(c) for c in tail]
    if _bech32_polymod(_bech32_hrp_expand(hrp) + vals) != 1:
        raise ValueError("bad bech32 checksum")
    prog = _convertbits(vals[1:-6], 5, 8, False)
    if prog is None:
        raise ValueError("bad bech32 program bits")
    return hrp, vals[0], bytes(prog)


def bech32m_decode(addr: str):
    """BIP-350 bech32m decode. Returns (hrp, witver, program_bytes)."""
    addr = addr.lower()
    pos = addr.rfind("1")
    if pos < 1 or pos + 7 > len(addr):
        raise ValueError("bad bech32m address")
    hrp, tail = addr[:pos], addr[pos + 1:]
    vals = [CHARSET.index(c) for c in tail]
    const = 0x2bc830a3
    if _bech32_polymod(_bech32_hrp_expand(hrp) + vals) != const:
        raise ValueError("bad bech32m checksum")
    prog = _convertbits(vals[1:-6], 5, 8, False)
    if prog is None:
        raise ValueError("bad bech32m program bits")
    return hrp, vals[0], bytes(prog)


# ─── Base58check helpers for WIF ─────────────────────────────────

_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def _b58encode(data: bytes) -> str:
    """Encode bytes to base58 string."""
    n = int.from_bytes(data, "big")
    out = []
    while n > 0:
        n, rem = divmod(n, 58)
        out.append(_B58[rem])
    for b in data:
        if b == 0:
            out.append("1")
        else:
            break
    return "".join(reversed(out))


def _b58check_encode(payload: bytes) -> str:
    """Base58check encode: payload + 4-byte checksum."""
    chk = hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]
    return _b58encode(payload + chk)


def _b58check_decode(s: str) -> bytes:
    """Base58check decode: verify checksum and return payload."""
    n = 0
    for c in s:
        n = n * 58 + _B58.index(c)
    leading = len(s) - len(s.lstrip("1"))
    raw = n.to_bytes(leading + (n.bit_length() + 7) // 8, "big")
    payload, checksum = raw[:-4], raw[-4:]
    if hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4] != checksum:
        raise ValueError("bad base58check checksum")
    return payload


def bech32_to_wif(bech32_addr: str, version_byte: int = 0x80) -> str:
    """Convert a bech32-encoded private key to WIF (base58check) format.

    Decodes the bech32 address to extract the raw data (private key bytes),
    then re-encodes as WIF with the given version byte (0x80 = mainnet,
    0xef = testnet) and compressed flag (0x01).

    Args:
        bech32_addr: The bech32 or bech32m encoded address containing the key.
        version_byte: WIF version prefix (0x80 for mainnet, 0xef for testnet).

    Returns:
        WIF string (base58check encoded).
    """
    # Try bech32m first (Taproot-style), fall back to bech32
    try:
        hrp, witver, prog = bech32m_decode(bech32_addr)
    except ValueError:
        hrp, witver, prog = bech32_decode(bech32_addr)

    if len(prog) != 32:
        raise ValueError(f"expected 32-byte key data, got {len(prog)} bytes")

    # WIF = version_byte + private_key + 0x01 (compressed flag)
    payload = bytes([version_byte]) + prog + bytes([0x01])
    return _b58check_encode(payload)


def private_key_to_wif(private_key, version_byte: int = 0x80, compressed: bool = True) -> str:
    """Convert a raw private key to WIF (base58check) format.

    This is the reverse of bech32_to_wif(): it takes a private key directly
    (hex string or bytes) and encodes it as WIF, following the same pattern
    used in messerene_operator.py.

    Args:
        private_key: 32-byte private key as bytes or hex string.
        version_byte: WIF version prefix (0x80 for mainnet, 0xef for testnet).
        compressed: Whether to append the 0x01 compression flag.

    Returns:
        WIF string (base58check encoded).

    Example:
        >>> private_key_to_wif("00" * 31 + "01")
        'KwDiBf89QgGbjEhKnhXJuH7LrciVrZi3qYjgd9M7rFU73sVHnoWn'
    """
    if isinstance(private_key, str):
        private_key = bytes.fromhex(private_key)
    if len(private_key) != 32:
        raise ValueError(f"private key must be 32 bytes, got {len(private_key)}")

    payload = bytes([version_byte]) + private_key
    if compressed:
        payload += bytes([0x01])
    return _b58check_encode(payload)


def wif_to_private_key(wif: str) -> tuple:
    """Decode a WIF string back to the raw private key.

    Returns:
        (private_key_bytes, version_byte, compressed) tuple.

    Raises:
        ValueError: If the WIF checksum is invalid or format is wrong.
    """
    payload = _b58check_decode(wif)
    version_byte = payload[0]
    if len(payload) == 33:
        # Uncompressed
        return payload[1:], version_byte, False
    elif len(payload) == 34:
        # Compressed (trailing 0x01)
        if payload[-1] != 0x01:
            raise ValueError("invalid compression flag in WIF")
        return payload[1:-1], version_byte, True
    else:
        raise ValueError(f"invalid WIF length: {len(payload)}")


def hash160(data: bytes) -> bytes:
    """SHA256 + RIPEMD160 hash (used for Bitcoin address derivation)."""
    try:
        return hashlib.new("ripemd160", hashlib.sha256(data).digest()).digest()
    except ValueError:
        # Fallback pure-Python RIPEMD160 if hashlib variant not available
        def _ripemd160(data: bytes) -> bytes:
            """Pure Python RIPEMD-160 implementation."""
            # Constants
            K1 = [0x00000000, 0x5A827999, 0x6ED9EBA1, 0x8F1BBCDC, 0xA953FD4E]
            K2 = [0x50A28BE6, 0x5C4DD124, 0x6D703EF3, 0x7A6D76E9, 0x00000000]
            # Initial values
            h0, h1, h2, h3, h4 = 0x67452301, 0xEFCDAB89, 0x98BADCFE, 0x10325476, 0xC3D2E1F0
            # Padding
            msg = bytearray(data)
            msg.append(0x80)
            while len(msg) % 64 != 56:
                msg.append(0)
            msg += (8 * len(data)).to_bytes(8, 'little')
            # Process each 512-bit chunk
            for i in range(0, len(msg), 64):
                chunk = msg[i:i+64]
                X = [int.from_bytes(chunk[j:j+4], 'little') for j in range(0, 32, 4)]
                # Left line
                al, bl, cl, dl, el = h0, h1, h2, h3, h4
                for j in range(80):
                    if 0 <= j < 16:
                        f = (bl ^ cl ^ dl)
                        k = K1[0]
                        r = 7
                    elif 16 <= j < 32:
                        f = (bl & cl) | (bl & dl) | (cl & dl)
                        k = K1[1]
                        r = 6
                    elif 32 <= j < 48:
                        f = (bl | ~cl) ^ dl
                        k = K1[2]
                        r = 5
                    elif 48 <= j < 64:
                        f = (bl & dl) | (cl & ~dl)
                        k = K1[3]
                        r = 4
                    elif 64 <= j < 80:
                        f = bl ^ (cl | ~dl)
                        k = K1[4]
                        r = 3
                    perm = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15,
                            7, 4, 13, 1, 10, 6, 15, 3, 12, 0, 9, 5, 2, 14, 11, 8,
                            3, 10, 14, 4, 9, 15, 8, 1, 2, 7, 0, 6, 13, 11, 5, 12,
                            1, 9, 11, 10, 0, 8, 12, 4, 13, 3, 7, 15, 14, 5, 6, 2,
                            4, 0, 5, 9, 7, 12, 2, 10, 14, 1, 3, 8, 11, 6, 15, 13]
                    t = ((al << r) | (al >> (32 - r))) & 0xFFFFFFFF
                    t = (t + f + el + X[perm[j]] + k) & 0xFFFFFFFF
                    el = dl
                    dl = (cl << 10) | (cl >> 22)
                    cl = bl
                    bl = al
                    al = t
                # Right line
                ar, br, cr, dr, er = h0, h1, h2, h3, h4
                for j in range(80):
                    if 0 <= j < 16:
                        f2 = (br ^ cr ^ dr)
                        k2 = K2[0]
                        r2 = 11
                    elif 16 <= j < 32:
                        f2 = (br & cr) | (br & dr) | (cr & dr)
                        k2 = K2[1]
                        r2 = 14
                    elif 32 <= j < 48:
                        f2 = (br | ~cr) ^ dr
                        k2 = K2[2]
                        r2 = 15
                    elif 48 <= j < 64:
                        f2 = (br & dr) | (cr & ~dr)
                        k2 = K2[3]
                        r2 = 12
                    elif 64 <= j < 80:
                        f2 = br ^ (cr | ~dr)
                        k2 = K2[4]
                        r2 = 9
                    perm2 = [5, 14, 7, 0, 9, 2, 11, 4, 13, 6, 15, 8, 1, 10, 3, 12,
                             6, 11, 3, 7, 0, 13, 5, 10, 14, 15, 8, 12, 4, 9, 1, 2,
                             15, 5, 1, 3, 7, 14, 6, 9, 11, 8, 12, 2, 10, 0, 4, 13,
                             8, 6, 4, 1, 3, 11, 15, 0, 5, 12, 2, 13, 9, 7, 10, 14,
                             12, 15, 10, 4, 1, 5, 8, 7, 6, 2, 13, 14, 0, 3, 9, 11]
                    t2 = ((ar << r2) | (ar >> (32 - r2))) & 0xFFFFFFFF
                    t2 = (t2 + f2 + er + X[perm2[j]] + k2) & 0xFFFFFFFF
                    er = dr
                    dr = (cr << 10) | (cr >> 22)
                    cr = br
                    br = ar
                    ar = t2
                h0 = (h1 + cl + dr) & 0xFFFFFFFF
                h1 = (h2 + dl + er) & 0xFFFFFFFF
                h2 = (h3 + el + ar) & 0xFFFFFFFF
                h3 = (h4 + al + br) & 0xFFFFFFFF
                h4 = (h0 + bl + cr) & 0xFFFFFFFF
            return h0.to_bytes(4, 'little') + h1.to_bytes(4, 'little') + h2.to_bytes(4, 'little') + h3.to_bytes(4, 'little') + h4.to_bytes(4, 'little')
        return _ripemd160(hashlib.sha256(data).digest())


def private_key_to_btc_address(private_key, hrp: str = "bc", witness_version: int = 0) -> str:
    """Derive a Bitcoin P2WPKH (bc1q...) address from a private key.

    Uses secp256k1 to compute the compressed public key, then hashes it
    with SHA256+RIPEMD160 to produce the 20-byte public key hash,
    finally encoding it as a bech32/bech32m address.

    Args:
        private_key: 32-byte private key as bytes or hex string.
        hrp: Human readable part ("bc" for mainnet, "tb" for testnet).
        witness_version: Witness version (0 for P2WPKH bech32, 1+ for bech32m).

    Returns:
        Bitcoin bech32 address string (e.g., "bc1q...").

    Example:
        >>> private_key_to_btc_address("00" * 31 + "01")
        'bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4'
    """
    # Import secp256k1 from project root
    import sys, os
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    import secp256k1 as secp

    # Normalize private key to bytes
    if isinstance(private_key, str):
        private_key = bytes.fromhex(private_key)
    if len(private_key) != 32:
        raise ValueError(f"private key must be 32 bytes, got {len(private_key)}")

    # Derive compressed public key
    d = int.from_bytes(private_key, "big")
    point = secp.priv_to_pub(d)
    compressed_pub = secp.compress(point)

    # Hash the compressed public key: RIPEMD160(SHA256(pub))
    pk_hash = hash160(compressed_pub)

    # Encode as bech32 address
    if witness_version == 0:
        return bech32_encode(hrp, witness_version, pk_hash)
    else:
        return bech32m_encode(hrp, witness_version, pk_hash)


def build_btc_htlc_script(
    claim_pubkey: bytes,
    refund_pubkey: bytes,
    secret_hash: bytes,
    timeout_height: int,
) -> bytes:
    """P2WSH HTLC: claim with preimage+sig, or refund after timeout."""
    if len(claim_pubkey) != 33 or claim_pubkey[0] not in (2, 3):
        raise ValueError("claim_pubkey must be 33-byte compressed")
    if len(refund_pubkey) != 33 or refund_pubkey[0] not in (2, 3):
        raise ValueError("refund_pubkey must be 33-byte compressed")
    if len(secret_hash) != 32:
        raise ValueError("secret_hash must be 32 bytes")
    if not (0 < timeout_height < LOCKTIME_THRESHOLD):
        raise ValueError("timeout_height must be a block height")
    return (
        bytes([OP_IF])
        + bytes([OP_SHA256]) + _push(secret_hash) + bytes([OP_EQUALVERIFY])
        + _push(claim_pubkey) + bytes([OP_CHECKSIG])
        + bytes([OP_ELSE])
        + _push(_encode_num(timeout_height)) + bytes([OP_CHECKLOCKTIMEVERIFY, OP_DROP])
        + _push(refund_pubkey) + bytes([OP_CHECKSIG])
        + bytes([OP_ENDIF])
    )


def btc_htlc_lock(
    claim_pubkey: bytes,
    refund_pubkey: bytes,
    secret_hash: bytes,
    timeout_height: int,
    hrp: str = "bc",
) -> dict:
    """Build BTC lock address + scripts for funding (unsigned)."""
    script = build_btc_htlc_script(claim_pubkey, refund_pubkey, secret_hash, timeout_height)
    prog = hashlib.sha256(script).digest()
    return {
        "witness_script_hex": script.hex(),
        "witness_script_hash": prog.hex(),
        "script_pubkey_hex": (bytes([OP_0]) + _push(prog)).hex(),
        "address": bech32_encode(hrp, 0, prog),
        "claim_pubkey": claim_pubkey.hex(),
        "refund_pubkey": refund_pubkey.hex(),
        "secret_hash": secret_hash.hex(),
        "timeout": timeout_height,
    }


@dataclass
class BridgeOffer:
    """SkyNet-serializable swap offer."""
    swap_id: str
    direction: str
    excal_amount: int
    btc_amount: int
    secret_hash: str
    excal_refund_address: str
    btc_refund_address: str
    btc_lock_address: str = ""
    btc_witness_script_hex: str = ""
    btc_timeout: int = 0
    proposer_wallet: str = ""
    proposer_host: str = ""
    proposer_port: int = 0
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "type": "swap_offer",
            "swap_id": self.swap_id,
            "direction": self.direction,
            "excal_amount": self.excal_amount,
            "btc_amount": self.btc_amount,
            "secret_hash": self.secret_hash,
            "excal_refund_address": self.excal_refund_address,
            "btc_refund_address": self.btc_refund_address,
            "btc_lock_address": self.btc_lock_address,
            "btc_witness_script_hex": self.btc_witness_script_hex,
            "btc_timeout": self.btc_timeout,
            "proposer_wallet": self.proposer_wallet,
            "proposer_host": self.proposer_host,
            "proposer_port": self.proposer_port,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "BridgeOffer":
        return cls(
            swap_id=d.get("swap_id", ""),
            direction=d.get("direction", ""),
            excal_amount=int(d.get("excal_amount", 0)),
            btc_amount=int(d.get("btc_amount", 0)),
            secret_hash=d.get("secret_hash", ""),
            excal_refund_address=d.get("excal_refund_address", ""),
            btc_refund_address=d.get("btc_refund_address", ""),
            btc_lock_address=d.get("btc_lock_address", ""),
            btc_witness_script_hex=d.get("btc_witness_script_hex", ""),
            btc_timeout=int(d.get("btc_timeout", 0)),
            proposer_wallet=d.get("proposer_wallet", ""),
            proposer_host=d.get("proposer_host", ""),
            proposer_port=int(d.get("proposer_port", 0)),
            created_at=float(d.get("created_at", time.time())),
        )


class BtcBridge:
    """Wallet-facing EXCAL ↔ BTC bridge engine."""

    def __init__(self, data_dir: Optional[str] = None):
        self.protocol = AtomicSwapProtocol(data_dir=data_dir)
        self._incoming: Dict[str, BridgeOffer] = {}

    def create_excal_to_btc_offer(
        self,
        excal_amount_swords: int,
        btc_amount_sats: int,
        excal_refund_address: str,
        btc_refund_address: str,
        claim_pubkey: Optional[bytes] = None,
        refund_pubkey: Optional[bytes] = None,
        btc_tip_height: int = 0,
        proposer_wallet: str = "",
        proposer_host: str = "",
        proposer_port: int = 0,
        hrp: str = "bc",
    ) -> dict:
        """Create swap + optional BTC HTLC lock params + SkyNet offer dict."""
        swap = self.protocol.create_swap(
            direction=SwapDirection.EXCAL_TO_BTC,
            excal_amount=excal_amount_swords,
            btc_amount=btc_amount_sats,
            excal_refund_address=excal_refund_address,
            btc_refund_address=btc_refund_address,
        )

        lock = {}
        timeout = 0
        if claim_pubkey and refund_pubkey and btc_tip_height > 0:
            timeout = btc_tip_height + BTC_REFUND_BLOCKS
            lock = btc_htlc_lock(
                claim_pubkey=claim_pubkey,
                refund_pubkey=refund_pubkey,
                secret_hash=swap.secret_hash,
                timeout_height=timeout,
                hrp=hrp,
            )

        offer = BridgeOffer(
            swap_id=swap.swap_id,
            direction=swap.direction.value,
            excal_amount=swap.excal_amount,
            btc_amount=swap.btc_amount,
            secret_hash=swap.secret_hash.hex(),
            excal_refund_address=excal_refund_address,
            btc_refund_address=btc_refund_address,
            btc_lock_address=lock.get("address", ""),
            btc_witness_script_hex=lock.get("witness_script_hex", ""),
            btc_timeout=timeout,
            proposer_wallet=proposer_wallet,
            proposer_host=proposer_host,
            proposer_port=proposer_port,
        )
        return {
            "swap": self.protocol.get_swap_summary(swap.swap_id),
            "offer": offer.to_dict(),
            "btc_lock": lock,
            # Preimage stays local — never put on SkyNet
            "secret_preimage": swap.secret_preimage.hex() if swap.secret_preimage else "",
        }

    def ingest_remote_offer(self, offer_dict: dict) -> BridgeOffer:
        offer = BridgeOffer.from_dict(offer_dict)
        self._incoming[offer.swap_id] = offer
        return offer

    def list_local_swaps(self) -> List[dict]:
        return [self.protocol.get_swap_summary(s.swap_id) for s in self.protocol.list_swaps()]

    def list_incoming_offers(self) -> List[dict]:
        return [o.to_dict() for o in self._incoming.values()]

    def mark_excal_locked(self, swap_id: str, funding_txid: str, funding_vout: int = 0,
                          lock_script_hex: str = "") -> dict:
        script = bytes.fromhex(lock_script_hex) if lock_script_hex else b""
        swap = self.protocol.lock_excal(swap_id, funding_txid, funding_vout, script)
        return self.protocol.get_swap_summary(swap.swap_id)

    def mark_btc_locked(self, swap_id: str, funding_txid: str, funding_vout: int = 0,
                        lock_script_hex: str = "") -> dict:
        script = bytes.fromhex(lock_script_hex) if lock_script_hex else b""
        swap = self.protocol.lock_btc(swap_id, funding_txid, funding_vout, script)
        return self.protocol.get_swap_summary(swap.swap_id)

    def mark_claimed(self, swap_id: str, chain: str, claim_txid: str,
                     secret_preimage_hex: str) -> dict:
        preimage = bytes.fromhex(secret_preimage_hex)
        if chain.lower() == "excal":
            swap = self.protocol.claim_excal(swap_id, preimage, claim_txid)
        elif chain.lower() == "btc":
            swap = self.protocol.claim_btc(swap_id, preimage, claim_txid)
        else:
            raise AtomicSwapError(f"unknown chain {chain}")
        return self.protocol.get_swap_summary(swap.swap_id)

    def health(self) -> dict:
        report = self.protocol.health_report()
        report["incoming_offers"] = len(self._incoming)
        report["component"] = "BtcBridge"
        return report


# ─── Pictographic Key Extraction via Inverse Wormhole Metrics ─────────────

def extract_pictographic_key(
    num_steps: int = 10,
    num_qubits: int = 4,
    grid_size: int = 16,
    wormhole_threshold: float = 0.3,
    seed_override: Optional[bytes] = None,
) -> dict:
    """Extract a pictographic private key using inverse wormhole metrics.

    Algorithm:
    1. Initialize a QuantumSpacetimeFabric with the given parameters.
    2. Apply quantum gates (Hadamard-like perturbations) seeded from
       the Genesis pictographs gematria values to create entanglement.
    3. Evolve the spacetime curvature for ``num_steps`` iterations.
    4. Detect wormhole endpoints from high-curvature regions.
    5. Invert the curvature tensor at wormhole endpoints to extract
       entropy bytes — the "inverse wormhole metric".
    6. Map the extracted entropy to BIP39 pictographic word indices.
    7. Derive a BIP39 seed and extract the first 32 bytes as a private key.

    Args:
        num_steps: Number of curvature evolution steps.
        num_qubits: Number of qubits in the quantum fabric.
        grid_size: Size of the spacetime grid.
        wormhole_threshold: Curvature threshold for wormhole detection.
        seed_override: Optional seed bytes to deterministically initialize
            the fabric (for reproducible extraction).

    Returns:
        Dictionary with:
        - ``private_key_hex``: 32-byte private key as hex string.
        - ``wif``: WIF-encoded private key (mainnet, compressed).
        - ``mnemonic``: BIP39 mnemonic derived from the pictographic seed.
        - ``wormhole_nodes``: Detected wormhole endpoint coordinates.
        - ``metrics``: Quantum-spacetime metrics (entropy, curvature, purity).
        - ``pictograph_indices``: BIP39 indices derived from inverse metrics.
    """
    import sys, os

    project_root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    )
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    # Import quantum-spacetime fabric
    from sphinx_os.nexus.quantum_spacetime import QuantumSpacetimeFabric

    # Import pictographic constants
    from sphinx_os.nexus.bip39_pictographic import (
        BIP39_WORDS,
        GENESIS_GEMATRIA,
        bip39_entropy_to_mnemonic,
        bip39_mnemonic_to_seed,
    )

    # ── Step 1: Initialize the fabric ──────────────────────────────
    fabric = QuantumSpacetimeFabric(
        num_qubits=num_qubits,
        grid_size=grid_size,
        wormhole_threshold=wormhole_threshold,
    )

    # Deterministic seed override for reproducibility
    if seed_override is not None:
        import numpy as np
        np.random.seed(int.from_bytes(seed_override[:4], "big"))

    # ── Step 2: Apply quantum gates from gematria values ───────────
    # Each gematria value determines a rotation angle for a Hadamard-like gate
    import numpy as np

    for gem in GENESIS_GEMATRIA:
        theta = gem / 300.0 * np.pi  # Normalize by max gematria (Shin=300)
        # Hadamard-like rotation gate
        gate = np.array(
            [
                [np.cos(theta), -np.sin(theta)],
                [-np.sin(theta), np.cos(theta)],
            ],
            dtype=np.complex128,
        )
        qubit = gem % num_qubits
        fabric.apply_quantum_gate(gate, [qubit])

    # ── Step 3: Evolve curvature ───────────────────────────────────
    metrics_list = []
    for _ in range(num_steps):
        metrics = fabric.unified_step()
        metrics_list.append(metrics)

    # ── Step 4: Detect wormholes ───────────────────────────────────
    fabric.detect_wormholes()
    wormhole_nodes = fabric.wormhole_nodes

    # ── Step 5: Inverse wormhole metric extraction ─────────────────
    # Invert the curvature tensor at wormhole endpoints to extract entropy.
    # The inverse metric is defined as: g_inv = 1 / |curvature| at each
    # wormhole endpoint, sampled as float bytes.

    curvature = fabric.curvature
    entropy_bytes = bytearray()

    if len(wormhole_nodes) >= 2:
        # Extract curvature values at wormhole endpoints
        for (x, y) in wormhole_nodes:
            val = curvature[x, y]
            # Inverse: 1/|val|, clamped to avoid division by zero
            inv_val = 1.0 / (abs(val) + 1e-10)
            # Pack as 8-byte double
            entropy_bytes.extend(struct.pack(">d", inv_val))

        # Also extract the curvature gradient between endpoints as entropy
        x1, y1 = wormhole_nodes[0]
        x2, y2 = wormhole_nodes[1]
        dx = abs(x2 - x1)
        dy = abs(y2 - y1)
        gradient = np.sqrt(
            (curvature[x2, y2] - curvature[x1, y1]) ** 2
            + (curvature[x1, y2] - curvature[x2, y1]) ** 2
        ) / (dx + dy + 1)
        entropy_bytes.extend(struct.pack(">d", gradient))
    else:
        # No wormholes detected — use curvature extrema as fallback
        max_idx = np.unravel_index(np.argmax(curvature), curvature.shape)
        min_idx = np.unravel_index(np.argmin(curvature), curvature.shape)
        for idx in [max_idx, min_idx]:
            val = curvature[idx]
            inv_val = 1.0 / (abs(val) + 1e-10)
            entropy_bytes.extend(struct.pack(">d", inv_val))

    # Pad or truncate to 32 bytes for private key
    entropy_bytes = bytes(entropy_bytes)
    if len(entropy_bytes) < 32:
        # Hash-extend if not enough entropy
        while len(entropy_bytes) < 32:
            entropy_bytes += hashlib.sha256(entropy_bytes).digest()
    private_key_bytes = entropy_bytes[:32]

    # ── Step 6: Map to BIP39 pictographic indices ──────────────────
    pictograph_indices = []
    for i in range(24):
        # Use 4 bytes at a time from entropy to derive index
        chunk = private_key_bytes[i % 32:i % 32 + 4]
        if len(chunk) < 4:
            chunk = chunk + b"\x00" * (4 - len(chunk))
        idx = int.from_bytes(chunk, "big") % 2048
        pictograph_indices.append(idx)

    mnemonic_words = [BIP39_WORDS[idx] for idx in pictograph_indices]
    mnemonic = " ".join(mnemonic_words[:12])  # 12-word mnemonic

    # ── Step 7: Derive BIP39 seed and extract private key ──────────
    seed = bip39_mnemonic_to_seed(mnemonic)
    derived_key = seed[:32]

    # Encode as WIF
    wif = private_key_to_wif(derived_key.hex())

    # Collect final metrics
    final_metrics = {
        "entanglement_entropy": fabric.compute_entanglement_entropy(),
        "curvature_rms": float(np.sqrt(np.mean(fabric.curvature ** 2))),
        "quantum_purity": fabric.compute_quantum_purity(),
        "wormhole_count": len(wormhole_nodes),
        "steps": num_steps,
    }

    return {
        "private_key_hex": derived_key.hex(),
        "wif": wif,
        "mnemonic": mnemonic,
        "wormhole_nodes": wormhole_nodes,
        "metrics": final_metrics,
        "pictograph_indices": pictograph_indices[:24],
    }
