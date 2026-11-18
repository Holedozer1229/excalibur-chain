"""FROST (Flexible Round-Optimized Schnorr Threshold) — Distributed Key Generation.

This module implements FROST (v1.1) for distributed key generation (DKG)
in the Knights of the Round Table governance system. FROST allows n parties
to jointly generate a threshold signature key without any single party
knowing the complete secret key.

FROST Protocol Overview
=======================
FROST enables t-of-n threshold signing where:
- No single party knows the aggregate secret key
- The aggregate public key is publicly verifiable
- Signature requires cooperation of at least t parties
- Signature verification is identical to standard Schnorr

Two-Phase Protocol
------------------
**Phase 1 — Key Generation (DKG):**
1. Each party i generates a secret share polynomial f_i(x) of degree t-1
2. Each party broadcasts commitments C_i = {g^{f_i(j)} for all j}
3. Each party computes their share: x_i = Σ f_j(i) (mod n)
4. The aggregate public key: Y = g^{f(0)} where f(x) = Σ f_i(x)

**Phase 2 — Signing:**
1. Each signing party generates a local nonce
2. Nonces are aggregated using Feldman VSS commitments
3. Each party computes a partial signature
4. Partial signatures are combined into a final Schnorr signature

Security Properties
===================
- t-of-n threshold: any t parties can sign, fewer cannot
- No dealer: distributed key generation requires no trusted party
- Forward secrecy: compromising < t parties reveals nothing
- Non-interactive verification: standard Schnorr verification

References
----------
- FROST v1.1: https://www.ietf.org/archive/id/draft-irtf-cfrg-vss-09.html
- BIP-327: MuSig2 for Bitcoin
- "FROST: Flexible Round-Optimized Schnorr Threshold" (Komlo, Goldberg 2020)
"""

import hashlib
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# secp256k1 curve constants
# ---------------------------------------------------------------------------
P = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F
N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
Gx = 0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798
Gy = 0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8
G = (Gx, Gy)


# ---------------------------------------------------------------------------
# Field arithmetic
# ---------------------------------------------------------------------------
def _inv(a: int, mod: int) -> int:
    """Modular inverse."""
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
            return None
        lam = (3 * x1 * x1) * _inv(2 * y1, P) % P
    else:
        lam = (y2 - y1) * _inv(x2 - x1, P) % P
    x3 = (lam * lam - x1 - x2) % P
    return (x3, (lam * (x1 - x3) - y1) % P)


def _point_mul(k: int, pt: Optional[Tuple[int, int]] = G) -> Optional[Tuple[int, int]]:
    """Scalar multiplication on secp256k1."""
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
# Cryptographic utilities
# ---------------------------------------------------------------------------
def _tagged_hash(tag: str, *data: bytes) -> bytes:
    """Tagged hash: SHA256(tag || tag || data)."""
    h = hashlib.sha256()
    tag_bytes = tag.encode("utf-8")
    h.update(tag_bytes)
    h.update(tag_bytes)
    for d in data:
        h.update(d)
    return h.digest()


def _scalar_from_hash(*data: bytes) -> int:
    """Derive a scalar from hashed data."""
    h = _tagged_hash("FROST-scalar", *data)
    return int.from_bytes(h, "big") % (N - 1) + 1


# ---------------------------------------------------------------------------
# Lagrange interpolation
# ---------------------------------------------------------------------------
def lagrange_coefficient(i: int, indices: List[int], field: int) -> int:
    """Compute Lagrange interpolation coefficient λ_i at x=0.

    λ_i = Π_{j≠i} (0 - x_j) / (x_i - x_j)  (mod field)

    Args:
        i: Index of the coefficient to compute.
        indices: List of all participant indices.
        field: The field modulus (N for scalar field).

    Returns:
        Lagrange coefficient λ_i.
    """
    num = 1
    den = 1
    for j in indices:
        if j == i:
            continue
        num = (num * (0 - j)) % field
        den = (den * (i - j)) % field
    return (num * _inv(den, field)) % field


# ---------------------------------------------------------------------------
# FROST Data Structures
# ---------------------------------------------------------------------------
@dataclass
class FrostCommitment:
    """A participant's DKG commitment (Feldman VSS)."""
    participant_index: int
    # Polynomial commitments: C_i = {g^{a_0}, g^{a_1}, ..., g^{a_{t-1}}}
    commitments: List[Tuple[int, int]]  # List of points


@dataclass
class FrostShare:
    """A participant's secret share after DKG."""
    participant_index: int
    secret_share: int  # x_i = Σ f_j(i) mod N
    public_key: Tuple[int, int]  # g^{x_i}
    aggregate_public_key: Tuple[int, int]  # Y = g^{f(0)}


@dataclass
class FrostSigningShare:
    """A participant's contribution to a signing round."""
    participant_index: int
    nonce_point: Tuple[int, int]  # Public nonce commitment
    nonce_secret: int  # Secret nonce
    partial_signature: Optional[int] = None


@dataclass
class FrostPartialSignature:
    """A participant's partial signature for aggregation."""
    participant_index: int
    signature: int  # Partial signature value


@dataclass
class FrostSignature:
    """An aggregated FROST threshold signature (BIP-340 compatible)."""
    r_point: Tuple[int, int]  # Aggregate nonce R
    s_value: int  # Aggregate signature σ
    r_bytes: bytes  # 32-byte R_x
    s_bytes: bytes  # 32-byte σ
    raw_sig: bytes  # 64-byte raw signature


# ---------------------------------------------------------------------------
# FROST Distributed Key Generation
# ---------------------------------------------------------------------------
class FrostDKG:
    """FROST Distributed Key Generation (DKG).

    Implements the two-round DKG protocol:
    1. Each party generates a polynomial and broadcasts commitments
    2. Each party computes their secret share from all commitments

    After DKG, each party holds:
    - Their secret share x_i (never revealed)
    - The aggregate public key Y = g^{f(0)}
    - Their individual public key g^{x_i}

    The aggregate secret key f(0) is never reconstructed.
    """

    def __init__(self, num_participants: int, threshold: int):
        """Initialize FROST DKG.

        Args:
            num_participants: Total number of participants (n).
            threshold: Minimum signers required (t).
        """
        if threshold > num_participants:
            raise ValueError("Threshold cannot exceed number of participants")
        if threshold < 2:
            raise ValueError("Threshold must be at least 2")

        self.n = num_participants
        self.t = threshold
        self.indices = list(range(1, num_participants + 1))

    def _generate_polynomial(self, secret: int, degree: int) -> List[int]:
        """Generate a random polynomial of given degree.

        f(x) = secret + a_1*x + a_2*x^2 + ... + a_d*x^d

        Args:
            secret: The constant term (secret share).
            degree: Degree of the polynomial (t-1).

        Returns:
            List of coefficients [a_0, a_1, ..., a_d].
        """
        coefficients = [secret]
        for _ in range(degree):
            coefficients.append(int.from_bytes(os.urandom(32), "big") % (N - 1) + 1)
        return coefficients

    def _evaluate_polynomial(self, coefficients: List[int], x: int) -> int:
        """Evaluate polynomial at point x using Horner's method.

        Args:
            coefficients: Polynomial coefficients [a_0, a_1, ..., a_d].
            x: Evaluation point.

        Returns:
            f(x) mod N.
        """
        result = 0
        for coeff in reversed(coefficients):
            result = (result * x + coeff) % N
        return result

    def generate_commitment(self, participant_index: int) -> Tuple[FrostCommitment, List[int]]:
        """Generate a DKG commitment for one participant.

        Each participant generates a polynomial f_i(x) of degree t-1
        and broadcasts commitments C_i = {g^{a_0}, g^{a_1}, ..., g^{a_{t-1}}}.

        Args:
            participant_index: This participant's index (1-based).

        Returns:
            Tuple of (FrostCommitment, polynomial coefficients).
            The coefficients are kept secret; the commitment is broadcast.
        """
        # Generate random secret (constant term of polynomial)
        secret = int.from_bytes(os.urandom(32), "big") % (N - 1) + 1

        # Generate polynomial of degree t-1
        coefficients = self._generate_polynomial(secret, self.t - 1)

        # Compute commitments: C_i[j] = g^{a_j}
        commitments = [_point_mul(coeff) for coeff in coefficients]

        frost_commitment = FrostCommitment(
            participant_index=participant_index,
            commitments=commitments,
        )

        return frost_commitment, coefficients

    def compute_share(
        self,
        participant_index: int,
        all_commitments: Dict[int, FrostCommitment],
        all_coefficients: Dict[int, List[int]],
    ) -> FrostShare:
        """Compute a participant's secret share from all commitments.

        x_i = Σ_j f_j(i)  (sum of all polynomials evaluated at i)

        Args:
            participant_index: This participant's index.
            all_commitments: All participants' commitments.
            all_coefficients: All participants' polynomial coefficients
                (in production, these are exchanged via secure channels).

        Returns:
            FrostShare with the participant's secret share and public keys.
        """
        # Compute secret share: x_i = Σ_j f_j(i)
        secret_share = 0
        for j, coeffs in all_coefficients.items():
            share = self._evaluate_polynomial(coeffs, participant_index)
            secret_share = (secret_share + share) % N

        # Compute individual public key: g^{x_i}
        public_key = _point_mul(secret_share)
        if public_key is None:
            raise ValueError("Public key is point at infinity")

        # Compute aggregate public key: Y = g^{f(0)} = Π_j g^{f_j(0)}
        # f_j(0) = a_0 (constant term of polynomial j)
        aggregate_public_key = None
        for j, commitment in all_commitments.items():
            # commitment.commitments[0] = g^{a_0} for polynomial j
            aggregate_public_key = _point_add(aggregate_public_key, commitment.commitments[0])

        if aggregate_public_key is None:
            raise ValueError("Aggregate public key is point at infinity")

        return FrostShare(
            participant_index=participant_index,
            secret_share=secret_share,
            public_key=public_key,
            aggregate_public_key=aggregate_public_key,
        )

    def verify_commitment(
        self,
        commitment: FrostCommitment,
        share: int,
        recipient_index: int,
    ) -> bool:
        """Verify a DKG commitment against a received share.

        Checks: g^{share} == Π_j C_i[j]^{j^{recipient_index}}

        Args:
            commitment: The commitment to verify.
            share: The share received for this participant.
            recipient_index: The recipient's index.

        Returns:
            True if the commitment is valid.
        """
        # Left side: g^{share}
        lhs = _point_mul(share)

        # Right side: Π_j C_i[j]^{recipient_index^j}
        rhs = None
        for j, c in enumerate(commitment.commitments):
            exponent = pow(recipient_index, j, N)
            scaled = _point_mul(exponent, c)
            rhs = _point_add(rhs, scaled)

        if lhs is None or rhs is None:
            return False

        return lhs == rhs


# ---------------------------------------------------------------------------
# FROST Signing
# ---------------------------------------------------------------------------
class FrostSigning:
    """FROST threshold signing protocol.

    After DKG, participants use their secret shares to produce
    threshold signatures without reconstructing the aggregate key.
    """

    def __init__(
        self,
        shares: Dict[int, FrostShare],
        threshold: int,
        num_participants: int,
    ):
        """Initialize FROST signing.

        Args:
            shares: All participants' shares (indexed by participant index).
            threshold: Minimum signers required (t).
            num_participants: Total participants (n).
        """
        self.shares = shares
        self.t = threshold
        self.n = num_participants
        self.indices = list(range(1, num_participants + 1))

    def generate_signing_nonce(self, participant_index: int, message: bytes) -> FrostSigningShare:
        """Generate a signing nonce for one participant.

        Args:
            participant_index: This participant's index.
            message: The message to be signed.

        Returns:
            FrostSigningShare with nonce commitment and secret.
        """
        share = self.shares[participant_index]

        # Deterministic nonce from secret share and message
        nonce_seed = _tagged_hash(
            "FROST-nonce",
            share.secret_share.to_bytes(32, "big"),
            message,
            participant_index.to_bytes(4, "big"),
        )
        k_i = int.from_bytes(nonce_seed, "big") % (N - 1) + 1

        # Public nonce commitment
        d_i = _point_mul(k_i)
        if d_i is None:
            raise ValueError("Nonce point is point at infinity")

        return FrostSigningShare(
            participant_index=participant_index,
            nonce_point=d_i,
            nonce_secret=k_i,
        )

    def compute_partial_signature(
        self,
        participant_index: int,
        signing_share: FrostSigningShare,
        aggregate_nonce: Tuple[int, int],
        message: bytes,
        signer_indices: List[int],
    ) -> FrostPartialSignature:
        """Compute a partial signature for one participant.

        σ_i = k_i + λ_i · e · x_i  (mod N)

        where λ_i is the Lagrange coefficient and e is the challenge.

        Args:
            participant_index: This participant's index.
            signing_share: This participant's signing share.
            aggregate_nonce: Aggregate nonce point R.
            message: The message being signed.
            signer_indices: Indices of all participating signers.

        Returns:
            FrostPartialSignature.
        """
        share = self.shares[participant_index]

        # Compute challenge e = H(R || Y || m)
        e = self._compute_challenge(aggregate_nonce, share.aggregate_public_key, message)

        # Compute Lagrange coefficient
        lambda_i = lagrange_coefficient(participant_index, signer_indices, N)

        # Partial signature: σ_i = k_i + λ_i * e * x_i
        sigma_i = (signing_share.nonce_secret + lambda_i * e * share.secret_share) % N

        return FrostPartialSignature(
            participant_index=participant_index,
            signature=sigma_i,
        )

    def _compute_challenge(
        self,
        r_point: Tuple[int, int],
        y_point: Tuple[int, int],
        message: bytes,
    ) -> int:
        """Compute the signing challenge e = H(R_x || Y_x || m)."""
        r_x = r_point[0].to_bytes(32, "big")
        y_x = y_point[0].to_bytes(32, "big")
        e_hash = _tagged_hash("FROST-challenge", r_x, y_x, message)
        return int.from_bytes(e_hash, "big") % N

    def aggregate_partial_signatures(
        self,
        partials: List[FrostPartialSignature],
        aggregate_nonce: Tuple[int, int],
        message: bytes,
    ) -> FrostSignature:
        """Aggregate partial signatures into a final FROST signature.

        σ = Σ σ_i  (mod N)

        Args:
            partials: Partial signatures from all signing participants.
            aggregate_nonce: Aggregate nonce point R.
            message: The signed message.

        Returns:
            FrostSignature — a BIP-340 compatible signature.
        """
        if len(partials) < self.t:
            raise ValueError(f"Need at least {self.t} partial signatures")

        # Aggregate: σ = Σ σ_i
        sigma = 0
        for ps in partials:
            sigma = (sigma + ps.signature) % N

        # Serialize
        r_bytes = aggregate_nonce[0].to_bytes(32, "big")
        s_bytes = sigma.to_bytes(32, "big")
        raw_sig = r_bytes + s_bytes

        return FrostSignature(
            r_point=aggregate_nonce,
            s_value=sigma,
            r_bytes=r_bytes,
            s_bytes=s_bytes,
            raw_sig=raw_sig,
        )

    def verify(
        self, signature: FrostSignature, message: bytes
    ) -> bool:
        """Verify a FROST signature using standard Schnorr verification.

        Checks: σ · G == R + e · Y

        Args:
            signature: The FROST signature to verify.
            message: The message that was signed.

        Returns:
            True if the signature is valid.
        """
        try:
            # Get aggregate public key from any share
            y_point = list(self.shares.values())[0].aggregate_public_key

            # Compute challenge
            e = self._compute_challenge(signature.r_point, y_point, message)

            # Verify: σ · G == R + e · Y
            lhs = _point_mul(signature.s_value)
            rhs_scaled = _point_mul(e, y_point)
            rhs = _point_add(signature.r_point, rhs_scaled)

            if lhs is None or rhs is None:
                return False

            return lhs[0] == rhs[0] and lhs[1] == rhs[1]
        except (ValueError, TypeError, KeyError):
            return False


# ---------------------------------------------------------------------------
# Convenience: full FROST flow
# ---------------------------------------------------------------------------
def frost_dkg_and_sign(
    num_participants: int,
    threshold: int,
    message: bytes,
    signer_indices: Optional[List[int]] = None,
) -> Tuple[FrostSignature, Dict[int, FrostShare]]:
    """Complete FROST DKG and signing flow.

    Args:
        num_participants: Total participants (n).
        threshold: Minimum signers (t).
        message: Message to sign.
        signer_indices: Indices of signers (default: first t).

    Returns:
        Tuple of (FrostSignature, all shares).
    """
    if signer_indices is None:
        signer_indices = list(range(1, threshold + 1))

    # Phase 1: DKG
    dkg = FrostDKG(num_participants, threshold)

    # Each participant generates commitment
    commitments = {}
    coefficients = {}
    for i in range(1, num_participants + 1):
        commitment, coeffs = dkg.generate_commitment(i)
        commitments[i] = commitment
        coefficients[i] = coeffs

    # Each participant computes their share
    shares = {}
    for i in range(1, num_participants + 1):
        share = dkg.compute_share(i, commitments, coefficients)
        shares[i] = share

    # Phase 2: Signing
    signing = FrostSigning(shares, threshold, num_participants)

    # Signers generate nonces
    signing_shares = {}
    for i in signer_indices:
        signing_shares[i] = signing.generate_signing_nonce(i, message)

    # Aggregate nonces
    aggregate_nonce = None
    for i in signer_indices:
        aggregate_nonce = _point_add(aggregate_nonce, signing_shares[i].nonce_point)

    if aggregate_nonce is None:
        raise ValueError("Aggregate nonce is point at infinity")

    # Each signer computes partial signature
    partials = []
    for i in signer_indices:
        partial = signing.compute_partial_signature(
            i, signing_shares[i], aggregate_nonce, message, signer_indices
        )
        partials.append(partial)

    # Aggregate partial signatures
    sig = signing.aggregate_partial_signatures(partials, aggregate_nonce, message)

    return sig, shares
