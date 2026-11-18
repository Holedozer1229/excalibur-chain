# BIP-XXXX: KNOT Lock — Möbius Torus-Knot Commitment for Quantum-Resistant Fund Control

## Abstract

This BIP defines the KNOT lock (type `0x06`), a quantum-resistant commitment lock based on Möbius-modulated torus knot computations. The KNOT lock provides a hash-lock equivalent where the commitment is a point on a (p,q) torus knot computed via deterministic fixed-point arithmetic, and the secret is a 128-bit parameter `t_star` that determines the knot point's position. This BIP also defines the Proof of Control protocol for demonstrating ownership of funds without revealing private keys.

## Motivation

### Quantum Resistance

Current Bitcoin lock types (P2PKH, P2WPKH, P2SH) rely on ECDSA signatures over secp256k1, which are vulnerable to Shor's algorithm on a fault-tolerant quantum computer. The KNOT lock uses only SHA-256 hashing and deterministic fixed-point arithmetic — no elliptic curve operations — making it quantum-resistant.

### Deterministic Consensus

The KNOT lock uses Q64 fixed-point arithmetic (64-bit integers with implicit 64-bit fractional part), ensuring bit-identical results across all nodes regardless of platform, CPU architecture, or floating-point implementation. This is essential for consensus validation.

### Proof of Control

The Proof of Control protocol allows a party to demonstrate ownership of funds locked in any address type (P2PKH, P2WPKH, P2SH, KNOT, PQH, HTLC, QHTLC) without revealing the private key or secret. This is useful for audits, regulatory compliance, and cross-chain verification.

## Specification

### KNOT Lock Descriptor

A KNOT lock descriptor is a 40-byte structure:

```
[0x06] [hash160(descriptor)]
```

Where `descriptor` is the SHA-256 hash of the concatenation:

```
descriptor = SHA-256(knot_commitment || t_star_hash)
```

- `knot_commitment`: 48 bytes — the knot point computed by `knot_math.knot_commitment(p, q, n_terms, eps_u32, t_star)`
- `t_star_hash`: 32 bytes — `SHA-256(t_star)` where `t_star` is a 16-byte (128-bit) random value

### Knot Computation

The knot point is computed using the Möbius-modulated (p,q) torus knot formula:

```
x(t) = (R + r*cos(q*t)) * cos(p*t)
y(t) = (R + r*cos(q*t)) * sin(p*t)
z(t) = r * sin(q*t)
```

Where:
- `p, q` are coprime integers in [1, 255] defining the knot type
- `R` is the major radius (fixed at 2 in Q64)
- `r` is the minor radius (fixed at 1 in Q64)
- `t` ranges from 0 to 2π, sampled at `n_terms` points
- `eps_u32` is the precision parameter in [1, 2^32-1]
- `t_star` determines the starting phase and amplitude modulation

The computation uses only integer arithmetic:
- All trigonometric functions are replaced by Taylor series with Q64 fixed-point coefficients
- All divisions use integer division (`//`) or bit shifts (`>>`)
- No floating-point operations are used

### Lock Type Byte

The KNOT lock uses type byte `0x06` in the lock script:

```
0x06 || hash160(descriptor)
```

This matches the existing lock type convention:
- `0x00`: PKH (Pay-to-Public-Key-Hash)
- `0x01`: BRIDGE (Cross-chain bridge)
- `0x02`: PQH (Pay-to-Quantum-Hash)
- `0x03`: HTLC (Hashed TimeLock Contract)
- `0x04`: QHTLC (Quantum HTLC)
- `0x05`: Reserved
- `0x06`: KNOT (Möbius Torus-Knot Commitment)

### Building a KNOT Lock Transaction

To create a KNOT-locked output:

1. Generate `t_star = os.urandom(16)` (128-bit cryptographically secure random value)
2. Choose knot parameters: `p, q` (coprime, in [1, 255]), `n_terms` (in [1, 1000]), `eps_u32` (in [1, 2^32-1])
3. Compute `knot_point = knot_commitment(p, q, n_terms, eps_u32, t_star)` (48 bytes)
4. Compute `t_star_hash = SHA-256(t_star)` (32 bytes)
5. Compute `descriptor = SHA-256(knot_point || t_star_hash)` (32 bytes)
6. Compute `lock = 0x06 || hash160(descriptor)` (21 bytes)
7. Create output with `lock` as the locking script

### Spending a KNOT Lock

To spend a KNOT-locked output, reveal `t_star`:

1. The spender provides `t_star` (16 bytes) as witness data
2. The validator recomputes `knot_point = knot_commitment(p, q, n_terms, eps_u32, t_star)`
3. The validator computes `descriptor = SHA-256(knot_point || SHA-256(t_star))`
4. The validator checks `hash160(descriptor) == lock[1:]`
5. If the check passes, the spend is valid

### Security Analysis

#### Preimage Resistance

The security rests on SHA-256 preimage resistance over a 128-bit `t_star` space. Without the `t_star` value, an attacker must:

1. Guess `t_star` from 2^128 possibilities
2. For each guess, compute the knot point (deterministic, fast)
3. Hash the result and compare against the lock

The expected number of attempts is 2^127, making brute-force infeasible.

#### Q64 Quantization

The Q64 fixed-point arithmetic quantizes the knot point to ~64 bits of precision per coordinate. Without hashing `t_star` directly, multiple `t_star` values could map to the same quantized knot point, reducing security to ~70 bits. By hashing `t_star` into the descriptor, full 128-bit security is maintained.

#### Consensus Safety

The deterministic fixed-point arithmetic ensures all nodes compute the same knot point for the same inputs. No floating-point operations, no platform-dependent functions, no external dependencies.

### Activation

The KNOT lock activates at block height 44,520 on the Excalibur fork chain. Transactions using KNOT locks before this height are rejected.

## Proof of Control Protocol

### Overview

The Proof of Control protocol allows demonstrating ownership of funds without revealing the private key or secret. It works for all lock types: PKH, PQH, HTLC, QHTLC, KNOT, and BRIDGE.

### PKH Proof of Control

For a P2PKH-locked output:

1. The prover signs a challenge message `m = SHA-256("excalibur-poc-" || address || nonce)` with the private key
2. The verifier checks the ECDSA signature against the public key hash in the lock
3. If valid, ownership is proven

### KNOT Proof of Control

For a KNOT-locked output:

1. The prover reveals `t_star` (the secret parameter)
2. The verifier recomputes the knot commitment and checks against the lock
3. If valid, ownership is proven

**Note:** This reveals the secret, making the funds spendable by anyone. For non-revealing proof, use a zero-knowledge proof of preimage knowledge.

### PQH Proof of Control

For a PQH-locked output:

1. The prover signs a challenge message using a fresh leaf from the Trifold key
2. The verifier checks the signature against the Merkle root in the lock
3. The spent leaf is recorded in the spent-leaf registry

## Implementation

The KNOT lock is implemented in the following files:

- `knot_math.py`: Deterministic fixed-point knot computation
- `knot_wallet.py`: KNOT lock transaction builder
- `txscript.py`: Lock parsing, witness validation, consensus rules
- `genesis_fork.py`: Activation height (44,520)
- `excalibur_wallet/locks.py`: Lock status and refusal logic

## Backward Compatibility

The KNOT lock is a new lock type that does not affect existing lock types. Nodes that don't support KNOT locks will reject KNOT transactions, which is the expected behavior before activation.

## Reference Implementation

See `knot_wallet.py` for the complete reference implementation.

## Security Considerations

- **Small t_star values**: Using small or guessable `t_star` values (e.g., `t_star=1`) reduces security to trivial. Always use `os.urandom(16)`.
- **Knot parameters**: The `p, q` values must be coprime. Non-coprime values produce a link (multiple components), not a single knot.
- **Activation height**: KNOT locks are only valid at or after block 44,520. Attempting to create KNOT locks before activation will raise `KnotRefused`.

## References

1. [Möbius strip](https://en.wikipedia.org/wiki/M%C3%B6bius_strip)
2. [Torus knot](https://en.wikipedia.org/wiki/Torus_knot)
3. [Fixed-point arithmetic](https://en.wikipedia.org/wiki/Fixed-point_arithmetic)
4. [SHA-256](https://en.wikipedia.org/wiki/SHA-2)
