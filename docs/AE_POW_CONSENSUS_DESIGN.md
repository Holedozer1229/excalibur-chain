# Aetherion Ergotropic Proof of Work (AE-PoW) — consensus design gate

**Status: proposal only. Not active consensus.**

## Objective

Make EXCAL mining produce a publicly verifiable Aetherion ergotropic computation rather than merely searching SHA-256d nonces. The computation must be useful as a reproducible scientific/engineering workload, while remaining permissionless, deterministic, and costly to produce relative to verification.

This document deliberately does not claim that the existing Aetherion/Dyson miner is already consensus-grade.

## Repository baseline (reviewed 2026-11-23)

- The current chain header/block validation imports Bitcoin-style `bits_to_target`, `required_bits`, and `validate_block` from `genesis_fork.py`; current mining clients construct SHA-256d header work.
- `cpu_miner.py` is a conventional Stratum nonce-search client.
- `dyson_miner.py` contains candidate generation using floating-point calculations, approximate zeta-zero values, and random Miller–Rabin bases. It is useful as an exploratory workload, but those choices are not deterministic consensus primitives.
- The whitepaper currently states that EXCAL proof-of-work is SHA-256d. This proposal would be a material consensus change and must not be described as live until activated by a network upgrade.

## Non-negotiable AE-PoW properties

1. **Determinism:** identical block challenge and parameters produce identical proof bytes and verification result on every supported implementation. No wall clock, ambient randomness, network calls, GPU-dependent rounding, Python floats, or platform-specific math in consensus.
2. **Bounded verification:** a full node can verify a submitted proof with bounded CPU, memory, and input sizes. Verification must be substantially cheaper than generating a valid proof.
3. **Unforgeable challenge binding:** proof commits to chain ID, parent block hash, height, difficulty epoch, algorithm version, and a domain-separated challenge. A proof from one fork, height, or parent cannot be replayed elsewhere.
4. **Difficulty and work accounting:** define a measurable work function with a monotone target. The chain must compare cumulative work across branches using the same consensus work definition; no subjective ergotropy score may directly decide fork choice.
5. **Reproducible implementation:** publish a small reference verifier, independent second implementation, canonical test vectors, malformed-proof corpus, and deterministic build instructions.
6. **No privileged oracle:** the Aetherion oracle may publish seeds/commitments or useful datasets, but it cannot be trusted to attest that a miner did work. Every node independently verifies the proof.
7. **Economic safety:** issuance, subsidy, halving, transaction validation, and UTXO rules remain unchanged by the PoW algorithm migration unless separately specified and activated.

## Proposed proof architecture

A block header commits to:

- `pow_version`
- `aetherion_challenge` = domain-separated hash of (chain ID, parent hash, height, epoch, canonical parameter-set hash)
- `work_commitment` = hash of canonical proof encoding
- `nonce` or proof search counter

A proof package contains:

- algorithm/version identifier;
- challenge echoed verbatim;
- canonical integer/fixed-point state encoding;
- initial state and parameter-set identifiers;
- iteration/trajectory commitment;
- claimed ergotropic observable(s), encoded as integers with fixed scale;
- final commitment and proof-of-work digest.

The verifier recomputes the deterministic transition and observable from the challenge and proof. It rejects noncanonical encodings, out-of-range values, excess iterations, invalid transitions, incorrect observable values, and a final digest that does not satisfy the epoch target.

The ergotropic observable is a *work witness*, not a floating-point beauty score. It must be defined algebraically with exact integer or fixed-point arithmetic and a public rounding rule. The target should apply to a domain-separated digest of the verified work commitment, not to an opaque score selected by the miner.

## Research gate: define the actual ergotropic primitive

Before coding consensus, the Aetherion research must specify:

- the exact finite-dimensional state space and allowed initial states;
- the transition operator and all constants as canonical integers/rationals;
- the exact definition of ergotropy/work extracted, including any optimization and tie-breaking;
- whether the proof is a full trajectory, a succinct proof, or a verifiable computation trace;
- the cost model for generation and verification;
- memory-hardness/ASIC-resistance claims, if any, supported by measurements rather than assertion;
- attack analysis for precomputation, grinding, proof reuse, seed manipulation, and cheap fake trajectories.

Do not use approximate Riemann-zero values, runtime random primality tests, floating-point Lorenz integration, or unversioned parameter files in consensus. Such computations can remain optional mining heuristics until replaced by a precisely specified deterministic primitive.

## Upgrade and deployment plan

### Phase 0 — freeze current rules

Keep SHA-256d as the only accepted PoW. Add no silent fallback and do not reinterpret old block headers.

### Phase 1 — research/reference implementation

Implement the exact AE-PoW primitive in an isolated module. Add:
- canonical serializer/parser;
- pure reference prover and verifier;
- fixed test vectors and negative tests;
- two independent implementations;
- benchmarks on CPU and GPU;
- proof-size and worst-case verifier-cost limits.

No node consensus changes in this phase.

### Phase 2 — testnet and adversarial evaluation

Run a separate test network with a new chain ID and explicit `pow_version`. Test mining pools, solo mining, stale work, reorgs, difficulty adjustment, denial-of-service bounds, and heterogeneous implementations. Compare effective work and energy costs with SHA-256d; publish raw measurements.

### Phase 3 — activation proposal

Only after independent review, specify a height-locked or epoch-locked activation with:
- exact activation height and version signaling;
- deterministic transition rules;
- cumulative-work calculation across the boundary;
- reorg behavior and checkpoint policy;
- emergency stop/rollback rules that do not permit discretionary rewriting.

Require independent node operators to upgrade. No unilateral activation from a website, oracle response, or miner setting.

### Phase 4 — mainnet activation

Activate only after testnet, independent audits, reproducible builds, and a public consensus test suite pass. Publish the exact activation parameters and signed release hashes.

## Relationship to Bitcoin and the EXCAL denomination

The intended unit convention remains:

- 100,000,000 swords = 1 EXCAL;
- 1 sword = 1 satoshi as a denomination mapping;
- therefore 1 EXCAL = 1 BTC in unit scale.

This is not a redeemability guarantee, Bitcoin peg, or market-price promise. A PoW change does not create inherited BTC balances. Bitcoin ownership inheritance remains a separate snapshot, script-compatibility, and activation project.

## Acceptance criteria

AE-PoW is not ready for mainnet until all are true:

- [ ] exact mathematical specification is public;
- [ ] independent prover/verifier implementations agree on every vector;
- [ ] malformed and adversarial proof corpus is rejected consistently;
- [ ] verification cost and worst-case resource use are bounded;
- [ ] difficulty and cumulative-work rules are formally specified and tested;
- [ ] reorgs across activation are tested;
- [ ] mining is permissionless without the Aetherion website/oracle;
- [ ] at least one independent operator mines and validates using independently built software;
- [ ] security review is public and unresolved critical findings are closed.

**Current status:** proposal/design gate only. Existing EXCAL mainnet consensus remains SHA-256d until a separately reviewed upgrade is activated.
