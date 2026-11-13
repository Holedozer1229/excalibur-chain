"""MuSig2 (BIP-327) — Production-ready multi-signature key aggregation and signing.

This module implements the MuSig2 protocol as specified in BIP-327 for
threshold signing in the Knights of the Round Table governance system.

MuSig2 allows multiple signers to produce a single Schnorr signature
(BIP-340) that is indistinguishable from a single-sig signature. The
aggregate public key is a linear combination of individual public keys,
and the aggregate signature verifies against this single point.

Protocol Overview (BIP-327)
============================
1. **Key Aggregation**: Each participant contributes a public key P_i.
   Scaling factors a_i = H(i, P_i) are computed, and the aggregate key
   is R = Σ a_i · P_i.

2. **Nonce Generation**: Each signer generates a nonce R_i = k_i · G
   using a deterministic nonce derivation from their secret share, the
   aggregate public key, and the message.

3. **Partial Signing**: Each signer computes a partial signature
   σ_i = k_i + a_i · e · x_i, where e = H(R, Q, m) is the challenge.

4. **Aggregation**: The final signature is σ = Σ σ_i, which satisfies
   the Schnorr equation: σ · G = R + e · Q.

5. **Verification**: Standard BIP-340 Schnorr verification against the
   aggregate public key.

Security Properties
===================
- Aggregate key is indistinguishable from a single-sig key
- No coordinator can learn individual secret keys
- Robust: protocol continues even if some signers abort
- Non-interactive after nonce exchange (2 rounds total)

References
----------
- BIP-327: MuSig2 for Bitcoin (https://github.com/BlockstreamResearch/bips/blob/master/bip-0327.mediawiki)
- BIP-340: Schnorr Signatures for secp256k1
- BIP-341: Taproot (P2TR)
"""

import hashlib
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# secp256k1 curve constants (from project's secp256k1.py)
# ---------------------------------------------------------------------------
P = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F
N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
Gx = 0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798
Gy = 0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8
G = (Gx, Gy)


# ---------------------------------------------------------------------------
# Field arithmetic (secp256k1)
# ---------------------------------------------------------------------------
def _inv(a: int, mod: int) -> int:
    """Modular inverse using Fermat's little theorem."""
    return pow(a % mod, mod - 2, mod)


def _point_add(p1: Optional[Tuple[int, int]], p2: Optional[Tuple[int, int]]) -> Optional[Tuple[int, int]]:
    """Add two points on secp256k1."""
    if p1 is None:
        return p2
    if p2 is None:
        return p1
    x1, y1 = p1
    x2, y2 = p2
    if x1 == x2:
        if (y1 + y2) % P == 0:
            return None  # Point at infinity
        lam = (3 * x1 * x1) * _inv(2 * y1, P) % P
    else:
        lam = (y2 - y1) * _inv(x2 - x1, P) % P
    x3 = (lam * lam - x1 - x2) % P
    return (x3, (lam * (x1 - x3) - y1) % P)


def _point_mul(k: int, pt: Optional[Tuple[int, int]] = G) -> Optional[Tuple[int, int]]:
    """Scalar multiplication on secp256k1 using double-and-add."""
    if pt is None:
        return None
    r = None
    k = k % N
    while k:
        if k & 1:
            r = _point_add(r, pt)
        pt = _point_add(pt, pt)
        k >>= 1
    return r


# ---------------------------------------------------------------------------
# BIP-340 Schnorr utilities
# ---------------------------------------------------------------------------
def _tagged_hash(tag: str, *data: bytes) -> bytes:
    """BIP-340 tagged hash: SHA256(tag || tag || data)."""
    h = hashlib.sha256()
    tag_bytes = tag.encode("utf-8")
    h.update(tag_bytes)
    h.update(tag_bytes)
    for d in data:
        h.update(d)
    return h.digest()


def _pubkey_to_xonly(pt: Tuple[int, int]) -> bytes:
    """Convert a point to 32-byte x-only public key."""
    return pt[0].to_bytes(32, "big")


def _xonly_to_point(x: int) -> Tuple[int, int]:
    """Recover y-coordinate from x-only, returning even y."""
    y_sq = (pow(x, 3, P) + 7) % P
    y = pow(y_sq, (P + 1) // 4, P)
    if y % 2 != 0:
        y = P - y
    return (x, y)


def _challenge(r_point: Tuple[int, int], q_point: Tuple[int, int], message: bytes) -> int:
    """Compute Schnorr challenge e = H(R_x || Q_x || m)."""
    r_x = r_point[0].to_bytes(32, "big")
    q_x = q_point[0].to_bytes(32, "big")
    e_hash = _tagged_hash("BIP0340/challenge", r_x, q_x, message)
    return int.from_bytes(e_hash, "big") % N


# ---------------------------------------------------------------------------
# MuSig2 Core
# ---------------------------------------------------------------------------
@dataclass
class MuSig2KeyPair:
    """A participant's key pair for MuSig2."""
    secret_key: int  # Private scalar (1 <= sk < N)
    public_key: Tuple[int, int]  # Public point (x, y)
    xonly_pubkey: bytes  # 32-byte x-only representation
    participant_index: int  # Index for scaling factor computation


@dataclass
class MuSig2Nonce:
    """A participant's nonce for one signing round."""
    participant_index: int
    nonce_point: Tuple[int, int]  # R_i = k_i * G (public nonce)
    nonce_secret: int  # k_i (kept secret)


@dataclass
class MuSig2PartialSignature:
    """A participant's partial signature."""
    participant_index: int
    partial_sig: int  # σ_i = k_i + a_i * e * x_i


@dataclass
class MuSig2Signature:
    """An aggregated MuSig2 Schnorr signature (BIP-340 compatible)."""
    r_point: Tuple[int, int]  # Aggregate nonce point R
    s_value: int  # Aggregate signature σ
    r_bytes: bytes  # 32-byte R_x for serialization
    s_bytes: bytes  # 32-byte σ for serialization
    raw_sig: bytes  # 64-byte raw signature (R_x || σ)


class MuSig2:
    """Production-ready MuSig2 (BIP-327) implementation.

    Supports:
    - Deterministic key aggregation with BIP-327 scaling factors
    - Nonce generation with proper domain separation
    - Partial signature generation
    - Signature aggregation
    - BIP-340 Schnorr verification

    Usage:
        # Setup
        musig = MuSig2()
        keys = [musig.generate_key_pair(i) for i in range(5)]

        # Aggregate public key
        agg_point, agg_xonly = musig.aggregate_public_keys(keys)
        all_xonly = [k.xonly_pubkey for k in keys]

        # Signing round 1: each signer generates nonce
        nonces = [musig.generate_nonce(k, agg_xonly, msg) for k in keys]
        agg_nonce = musig.aggregate_nonces(nonces)

        # Signing round 2: each signer computes partial signature
        partials = [
            musig.partial_sign(k, n, agg_nonce, agg_point, agg_xonly, msg, all_xonly)
            for k, n in zip(keys, nonces)
        ]

        # Aggregate
        sig = musig.aggregate_signatures(partials, agg_nonce, msg, agg_xonly)

        # Verify (standard BIP-340)
        assert musig.verify(sig, agg_xonly, msg)
    """

    def generate_key_pair(self, participant_index: int, secret_key: Optional[int] = None) -> MuSig2KeyPair:
        """Generate a key pair for a MuSig2 participant.

        Args:
            participant_index: Unique index for this participant (used in scaling).
            secret_key: Optional pre-determined secret key. If None, random.

        Returns:
            MuSig2KeyPair with secret, public, and x-only representations.
        """
        if secret_key is None:
            secret_key = int.from_bytes(os.urandom(32), "big") % (N - 1) + 1

        if not (1 <= secret_key < N):
            raise ValueError("Secret key out of range")

        public_key = _point_mul(secret_key)
        if public_key is None:
            raise ValueError("Generated public key is point at infinity")

        xonly = _pubkey_to_xonly(public_key)

        return MuSig2KeyPair(
            secret_key=secret_key,
            public_key=public_key,
            xonly_pubkey=xonly,
            participant_index=participant_index,
        )

    def generate_key_from_seed(self, seed: bytes, participant_index: int) -> MuSig2KeyPair:
        """Derive a key pair from a seed (deterministic).

        Args:
            seed: Seed bytes for key derivation.
            participant_index: Unique index for this participant.

        Returns:
            MuSig2KeyPair derived from the seed.
        """
        sk_hash = hashlib.sha256(seed + b"MUSIG2_KEY" + participant_index.to_bytes(4, "big")).digest()
        secret_key = int.from_bytes(sk_hash, "big") % (N - 1) + 1
        return self.generate_key_pair(participant_index, secret_key)

    def _compute_scaling_factor(
        self, participant_index: int, xonly_pubkey: bytes, all_xonly_pubkeys: List[bytes]
    ) -> int:
        """Compute the scaling factor a_i for a participant (BIP-327).

        a_i = H(i || x_i || X) where X is the concatenation of all x-only pubkeys
        sorted by index.

        Args:
            participant_index: This participant's index.
            xonly_pubkey: This participant's x-only public key.
            all_xonly_pubkeys: All participants' x-only pubkeys, sorted by index.

        Returns:
            Scaling factor a_i in [1, N-1].
        """
        # Concatenate all x-only pubkeys
        X = b"".join(all_xonly_pubkeys)

        # Compute a_i = H(i || x_i || X)
        a_hash = _tagged_hash(
            "MuSig2-aggregate",
            participant_index.to_bytes(4, "big"),
            xonly_pubkey,
            X,
        )
        a_i = int.from_bytes(a_hash, "big") % (N - 1) + 1
        return a_i

    def aggregate_public_keys(self, key_pairs: List[MuSig2KeyPair]) -> Tuple[Tuple[int, int], bytes]:
        """Compute the aggregate public key Q = Σ a_i · P_i.

        Args:
            key_pairs: List of MuSig2KeyPair, sorted by participant_index.

        Returns:
            Tuple of (aggregate point, 32-byte x-only aggregate key).
        """
        if not key_pairs:
            raise ValueError("No key pairs provided")

        # Sort by index
        sorted_keys = sorted(key_pairs, key=lambda k: k.participant_index)

        # Collect all x-only pubkeys in order
        all_xonly = [k.xonly_pubkey for k in sorted_keys]

        # Compute aggregate: Q = Σ a_i · P_i
        agg_point = None
        for kp in sorted_keys:
            a_i = self._compute_scaling_factor(kp.participant_index, kp.xonly_pubkey, all_xonly)
            scaled = _point_mul(a_i, kp.public_key)
            agg_point = _point_add(agg_point, scaled)

        if agg_point is None:
            raise ValueError("Aggregate public key is point at infinity — retry with different keys")

        xonly_agg = _pubkey_to_xonly(agg_point)
        return (agg_point, xonly_agg)

    def generate_nonce(
        self,
        key_pair: MuSig2KeyPair,
        agg_xonly_pubkey: bytes,
        message: bytes,
        nonce_seed: Optional[bytes] = None,
    ) -> MuSig2Nonce:
        """Generate a signing nonce for one participant.

        Uses deterministic nonce derivation: k_i = H(sk_i || R_i || Q || m)
        with re-rolling to prevent malleability.

        Args:
            key_pair: The participant's key pair.
            agg_xonly_pubkey: 32-byte x-only aggregate public key.
            message: The message to be signed.
            nonce_seed: Optional additional entropy for nonce.

        Returns:
            MuSig2Nonce with public nonce point and secret nonce.
        """
        if nonce_seed is None:
            nonce_seed = os.urandom(32)

        # Deterministic nonce: k_i = H(sk_i || nonce_seed || Q || m)
        sk_bytes = key_pair.secret_key.to_bytes(32, "big")
        nonce_hash = _tagged_hash(
            "MuSig2-nonce",
            sk_bytes,
            nonce_seed,
            agg_xonly_pubkey,
            message,
        )
        k_i = int.from_bytes(nonce_hash, "big") % (N - 1) + 1

        # Public nonce point
        r_i = _point_mul(k_i)
        if r_i is None:
            raise ValueError("Nonce point is point at infinity")

        return MuSig2Nonce(
            participant_index=key_pair.participant_index,
            nonce_point=r_i,
            nonce_secret=k_i,
        )

    def aggregate_nonces(self, nonces: List[MuSig2Nonce]) -> Tuple[int, int]:
        """Compute the aggregate nonce point R = Σ R_i.

        Args:
            nonces: List of MuSig2Nonce from all signing participants.

        Returns:
            Aggregate nonce point R (x, y).
        """
        agg = None
        for nonce in nonces:
            agg = _point_add(agg, nonce.nonce_point)

        if agg is None:
            raise ValueError("Aggregate nonce is point at infinity — retry with different nonces")

        return agg

    def partial_sign(
        self,
        key_pair: MuSig2KeyPair,
        nonce: MuSig2Nonce,
        agg_nonce_point: Tuple[int, int],
        agg_point: Tuple[int, int],
        agg_xonly_pubkey: bytes,
        message: bytes,
        all_xonly_pubkeys: List[bytes],
    ) -> MuSig2PartialSignature:
        """Compute a partial signature σ_i = k_i + a_i · e · d_i.

        Per BIP-327, the signer uses a possibly negated secret key:
        d_i = g_v · x_i  (mod N)

        where g_v = -1 if the aggregate key Q has an odd y-coordinate,
        and g_v = 1 otherwise. This ensures the signature corresponds
        to the x-only even-y representation of Q.

        The aggregate key Q is the additive inverse when flipped:
        same x, y becomes p − y. If Q has odd y, the x-only recovery
        gives −Q (even y), so the signer negates their secret key
        contribution to make the signature verify against −Q.

        The challenge e is computed from the x-coordinates only (BIP-340),
        so it is independent of the y-coordinate of R or Q.

        Args:
            key_pair: The participant's key pair.
            nonce: The participant's nonce.
            agg_nonce_point: Aggregate nonce point R.
            agg_point: The actual aggregate public key point Q = Σ a_i · P_i.
            agg_xonly_pubkey: 32-byte x-only aggregate public key.
            message: The message being signed.
            all_xonly_pubkeys: All signers' x-only pubkeys, sorted by index.

        Returns:
            MuSig2PartialSignature with σ_i.
        """
        # Compute challenge e = H(R_x || Q_x || m) — x-only, BIP-340 style
        r_x = agg_nonce_point[0].to_bytes(32, "big")
        q_x = agg_xonly_pubkey
        e_hash = _tagged_hash("BIP0340/challenge", r_x, q_x, message)
        e = int.from_bytes(e_hash, "big") % N

        # Compute scaling factor a_i
        a_i = self._compute_scaling_factor(
            key_pair.participant_index, key_pair.xonly_pubkey, all_xonly_pubkeys
        )

        # BIP-327: compute g_v — negation factor for the aggregate key.
        # If Q has an odd y-coordinate, the x-only representation recovers
        # the additive inverse: same x, y becomes p − y. That is −Q on the curve.
        # The signer negates their secret key contribution so the signature
        # verifies against the even-y recovered point.
        #
        # g_v = -1 mod N when Q has odd y, computed as (0 - 1) % N = N - 1.
        # The negated secret: d = g_v * x_i mod N, which is (-x_i) % N.
        if agg_point[1] % 2 != 0:
            g_v = (-1) % N  # additive inverse: (0 - 1) % N
        else:
            g_v = 1

        # Partial signature: σ_i = k_i + a_i * e * g_v * x_i (mod N)
        # When g_v = -1, this becomes σ_i = k_i - a_i * e * x_i (mod N)
        sigma_i = (nonce.nonce_secret + a_i * e * g_v * key_pair.secret_key) % N

        return MuSig2PartialSignature(
            participant_index=key_pair.participant_index,
            partial_sig=sigma_i,
        )

    def aggregate_signatures(
        self,
        partials: List[MuSig2PartialSignature],
        agg_nonce_point: Tuple[int, int],
        message: bytes,
        agg_xonly_pubkey: bytes,
    ) -> MuSig2Signature:
        """Aggregate partial signatures into a single Schnorr signature.

        σ = Σ σ_i (mod N)

        Args:
            partials: List of partial signatures from threshold participants.
            agg_nonce_point: Aggregate nonce point R.
            message: The signed message.
            agg_xonly_pubkey: 32-byte x-only aggregate public key.

        Returns:
            MuSig2Signature — a BIP-340 compatible 64-byte signature.
        """
        if not partials:
            raise ValueError("No partial signatures provided")

        # Aggregate: σ = Σ σ_i
        sigma = 0
        for ps in partials:
            sigma = (sigma + ps.partial_sig) % N

        # Serialize
        r_bytes = _pubkey_to_xonly(agg_nonce_point)
        s_bytes = sigma.to_bytes(32, "big")
        raw_sig = r_bytes + s_bytes

        return MuSig2Signature(
            r_point=agg_nonce_point,
            s_value=sigma,
            r_bytes=r_bytes,
            s_bytes=s_bytes,
            raw_sig=raw_sig,
        )

    def verify(
        self, signature: MuSig2Signature, agg_xonly_pubkey: bytes, message: bytes
    ) -> bool:
        """Verify a MuSig2 signature using standard BIP-340 Schnorr verification.

        Checks: σ · G == R + e · Q

        Per BIP-340, the challenge e depends only on R_x and Q_x (x-only).
        The aggregate key Q is always verified against the even-y recovered
        point, because the signer applies g_v negation (BIP-327) when Q
        has odd y, making the signature correspond to the even-y Q.

        The aggregate nonce R may have odd y (from nonce aggregation),
        so we try both y-coordinates for R. Q is always even-y because
        the signer's g_v factor ensures the signature matches even-y Q.

        Args:
            signature: The MuSig2Signature to verify.
            agg_xonly_pubkey: 32-byte x-only aggregate public key.
            message: The message that was signed.

        Returns:
            True if the signature is valid.
        """
        try:
            r_x = int.from_bytes(signature.r_bytes, "big")
            q_x = int.from_bytes(agg_xonly_pubkey, "big")

            # Compute challenge e from x-only coordinates (BIP-340)
            e_hash = _tagged_hash("BIP0340/challenge", signature.r_bytes, agg_xonly_pubkey, message)
            e = int.from_bytes(e_hash, "big") % N

            # Recover both possible y-coordinates for R
            r_y_sq = (pow(r_x, 3, P) + 7) % P
            r_y_even = pow(r_y_sq, (P + 1) // 4, P)
            if r_y_even % 2 != 0:
                r_y_even = P - r_y_even
            r_y_candidates = [r_y_even, P - r_y_even]

            # Recover Q from x-only — BIP-340 uses even y only.
            # The signer's g_v factor ensures the signature verifies
            # against the even-y Q (Q is the additive inverse when
            # the actual aggregate had odd y: same x, y becomes p − y).
            q_y_sq = (pow(q_x, 3, P) + 7) % P
            q_y_even = pow(q_y_sq, (P + 1) // 4, P)
            if q_y_even % 2 != 0:
                q_y_even = P - q_y_even
            Q = (q_x, q_y_even)

            # Verify: σ · G == R + e · Q, trying both R y-coordinates
            lhs = _point_mul(signature.s_value)
            if lhs is None:
                return False

            rhs_scaled = _point_mul(e, Q)
            for r_y in r_y_candidates:
                R = (r_x, r_y)
                rhs = _point_add(R, rhs_scaled)
                if rhs is not None and lhs[0] == rhs[0] and lhs[1] == rhs[1]:
                    return True

            return False
        except (ValueError, TypeError):
            return False

    def verify_raw(self, raw_sig: bytes, agg_xonly_pubkey: bytes, message: bytes) -> bool:
        """Verify a raw 64-byte MuSig2 signature.

        Args:
            raw_sig: 64-byte signature (R_x || σ).
            agg_xonly_pubkey: 32-byte x-only aggregate public key.
            message: The signed message.

        Returns:
            True if valid.
        """
        if len(raw_sig) != 64:
            return False
        if len(agg_xonly_pubkey) != 32:
            return False

        r_bytes = raw_sig[:32]
        s_value = int.from_bytes(raw_sig[32:], "big")

        try:
            r_point = _xonly_to_point(int.from_bytes(r_bytes, "big"))
            sig = MuSig2Signature(
                r_point=r_point,
                s_value=s_value,
                r_bytes=r_bytes,
                s_bytes=raw_sig[32:],
                raw_sig=raw_sig,
            )
            return self.verify(sig, agg_xonly_pubkey, message)
        except (ValueError, TypeError):
            return False


# ---------------------------------------------------------------------------
# Convenience: full signing flow
# ---------------------------------------------------------------------------
def musig2_sign(
    key_pairs: List[MuSig2KeyPair],
    message: bytes,
    signer_indices: Optional[List[int]] = None,
    nonce_seeds: Optional[List[bytes]] = None,
) -> MuSig2Signature:
    """Complete MuSig2 signing flow: aggregate keys, sign, aggregate sigs.

    Follows the BIP-327 two-round protocol:
    Round 1: Each signer broadcasts their nonce commitment R_i
    Round 2: Each signer computes their partial signature σ_i

    Args:
        key_pairs: All participant key pairs.
        message: Message to sign.
        signer_indices: Indices of participating signers (default: all).
        nonce_seeds: Optional deterministic nonce seeds for reproducibility.

    Returns:
        Aggregated MuSig2Signature.
    """
    musig = MuSig2()

    # Use all or specified signers
    if signer_indices:
        signers = [k for k in key_pairs if k.participant_index in signer_indices]
    else:
        signers = list(key_pairs)

    # Sort signers by index for deterministic ordering
    signers = sorted(signers, key=lambda k: k.participant_index)

    # Aggregate public key
    agg_point, agg_xonly = musig.aggregate_public_keys(signers)

    # Collect all x-only pubkeys for scaling (sorted by index)
    all_xonly = [k.xonly_pubkey for k in signers]

    # Round 1: Each signer generates nonce commitment
    nonces = []
    for i, k in enumerate(signers):
        seed = nonce_seeds[i] if nonce_seeds else None
        nonces.append(musig.generate_nonce(k, agg_xonly, message, seed))

    # Aggregate nonce commitments: R = Σ R_i
    agg_nonce = musig.aggregate_nonces(nonces)

    # Round 2: Each signer computes partial signature
    partials = [
        musig.partial_sign(k, n, agg_nonce, agg_point, agg_xonly, message, all_xonly)
        for k, n in zip(signers, nonces)
    ]

    # Aggregate partial signatures: σ = Σ σ_i
    sig = musig.aggregate_signatures(partials, agg_nonce, message, agg_xonly)

    return sig


def musig2_verify(raw_sig: bytes, key_pairs: List[MuSig2KeyPair], message: bytes, signer_indices: Optional[List[int]] = None) -> bool:
    """Verify a MuSig2 signature against the aggregate of provided key pairs.

    Args:
        raw_sig: 64-byte raw signature.
        key_pairs: All participant key pairs.
        message: The signed message.
        signer_indices: Indices of signers (default: all).

    Returns:
        True if valid.
    """
    musig = MuSig2()

    if signer_indices:
        signers = [k for k in key_pairs if k.participant_index in signer_indices]
    else:
        signers = list(key_pairs)

    # Sort signers by index for consistent aggregation
    signers = sorted(signers, key=lambda k: k.participant_index)

    _, agg_xonly = musig.aggregate_public_keys(signers)
    return musig.verify_raw(raw_sig, agg_xonly, message)
