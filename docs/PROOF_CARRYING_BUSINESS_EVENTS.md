# EXCAL Proof-Carrying Business Events (PCBE)
## Design proposal — off-consensus, independently verifiable business evidence

**Status:** proposal / implementation boundary  
**Target:** EXCAL application layer; no consensus or wallet-rule changes  
**Branch:** `feat/proof-carrying-business-events`

## Executive idea

Make a business event portable with its evidence. An invoice, shipment handoff, inspection, warranty registration, escrow milestone, game achievement, or settlement instruction can be represented by a canonical event envelope plus commitments to supporting evidence and signatures from the parties that actually attest to it.

A verifier should be able to answer precise questions:

- Were the bytes and claims altered after they were signed?
- Which identified party attested to which claim, under which role and policy?
- Was the attestation valid at the relevant time, and has it since been revoked?
- Does the evidence satisfy a published business rule?
- Is the event already consumed, expired, disputed, or superseded?

This is not an oracle for objective truth. Cryptography proves integrity, origin under a key, and protocol conditions. It does not prove that a sensor was honest, a shipment physically arrived, or an issuer told the truth. Those claims require accountable evidence sources, independent checks, and dispute procedures.

## Non-negotiable boundaries

1. **Off-consensus first.** PCBE is an application-layer protocol. It does not alter EXCAL block validity, transaction serialization, signature rules, difficulty, issuance, fork choice, or existing balances.
2. **No new cryptography.** Use established hashes, signatures, canonicalization, and Merkle constructions. Do not invent a cipher, signature scheme, hash, or home-grown zero-knowledge proof.
3. **Separate identity from authority.** A valid signature means a key signed bytes. A verifier must separately establish the key's organization, role, authority, validity interval, and revocation status.
4. **No AI truth votes.** Aetherion may classify anomalies or suggest challenges, but its output is advisory. Deterministic policy and independent evidence decide acceptance.
5. **Privacy by default.** Do not put invoices, names, addresses, customer records, trade secrets, or raw sensor data on-chain. Publish only commitments and the minimum metadata needed.
6. **Fail closed.** Unknown algorithms, unsupported script types, missing trust roots, expired authorizations, invalid signatures, duplicate nonces, and ambiguous encodings are rejected.
7. **No automatic funds movement.** A PCBE acceptance result cannot itself authorize a wallet spend. Payment remains subject to EXCAL's existing transaction and signing rules and any separately approved custody policy.

## Version 1 event envelope

Use deterministic CBOR (RFC 8949 deterministic encoding) for the signed binary representation. A JSON diagnostic form may be provided, but JSON text must never be signed directly unless a documented canonicalization profile is applied.

Required fields:

| Field | Meaning |
|---|---|
| `protocol` | Fixed identifier, e.g. `excal.pcbe` |
| `version` | Integer protocol version |
| `network` | Explicit EXCAL network ID and genesis hash |
| `event_id` | Random 256-bit unique identifier |
| `event_type` | Registered type and schema version |
| `subject_commitment` | Domain-separated commitment to the referenced business object |
| `claims` | Typed, minimal claims being attested |
| `evidence` | Evidence digests, media types, source and retention references |
| `policy_id` | Immutable policy identifier and version |
| `issued_at`, `expires_at` | Bounded validity interval |
| `nonce` | Unique challenge / replay-protection value |
| `predecessors` | Optional prior event IDs and commitments |
| `attachments_root` | Merkle root of evidence digests, or null |
| `signatures` | Detached role-bound signatures over the envelope digest |

Compute:
`event_digest = SHA-256("EXCAL-PCBE-EVENT-v1" || deterministic_cbor(envelope_without_signatures))`.

Each evidence item is committed with a separate domain:
`evidence_digest = SHA-256("EXCAL-PCBE-EVIDENCE-v1" || media_type || exact_bytes)`.

The attachments Merkle tree must specify leaf/node prefixes, ordering, odd-node handling, and proof encoding in test vectors before implementation. Never concatenate ambiguous variable-length fields; use deterministic CBOR or explicit length-prefixing.

## Attestations and business policy

An attestation signs the event digest plus the signer's declared role, key identifier, policy version, and signing context. The policy defines which roles are required (for example seller, carrier, buyer, inspector), whether signatures must be independent, whether one organization may fill multiple roles, and which evidence types are mandatory.

A verifier returns one of these machine-readable outcomes:

- `VALID`: all cryptographic and configured policy checks pass.
- `INVALID`: a cryptographic, encoding, network, or policy check fails.
- `INCOMPLETE`: required evidence or attestations are absent.
- `EXPIRED`: the event is outside its allowed validity interval.
- `REVOKED`: a required key, credential, or authorization is revoked.
- `DISPUTED`: a recognized dispute is open; do not treat as settled.
- `UNVERIFIABLE`: required trust data or verifier capability is unavailable.

The report includes verifier version, policy hash, checked inputs, signature results, revocation freshness, and a digest of the report. Do not collapse these states into a single confidence score.

## Trust and key lifecycle

- Support a pluggable signature suite. The first profile should use a mature, maintained library and a well-defined algorithm already supported by the issuer ecosystem. Ed25519 may be used for application attestations where appropriate; EXCAL-native spend signatures remain separate.
- Publish organization trust roots and role delegations with validity intervals and revocation status.
- Require key rotation, compromise response, audit logs, and multi-party approval for high-value issuer keys.
- URUU recovery policy may govern recovery of designated organization/guardian keys only after its real cryptographic verification and operational controls have been independently audited.
- FROST may be integrated as an optional threshold-signing backend only after DKG, nonce safety, share storage, operator independence, and transcript verification are reviewed. PCBE does not assume FROST keys are production-ready.
- Never derive wallet keys from public prophecy text, business identifiers, I Ching values, phonetic transforms, or Riemann-zero data.

## Disputes and evidence retention

Events can be challenged by referencing the event digest and a typed reason. A dispute record identifies the challenger, evidence commitments, response deadline, adjudication policy, and final outcome. The protocol must preserve the original signed event; corrections are new events that supersede, never rewrite, prior records.

Evidence bytes remain off-chain under the data controller's retention and access policy. A digest alone is not proof that the underlying evidence was authentic or truthful. Verifiers need access to the bytes or to a trusted evidence provider when the business rule requires content inspection.

## EXCAL anchoring (optional, later phase)

An accepted event may optionally anchor only:
- event digest;
- attachments root;
- policy identifier/version;
- coarse event type;
- expiry or status pointer if required.

Do not anchor personal data, raw documents, full signatures if not needed, or correlatable identifiers by default. Anchoring is an audit timestamp/ordering aid, not a statement that EXCAL consensus validated the underlying business facts.

Before enabling anchoring, specify transaction encoding, fees, spam limits, pruning/retention, privacy analysis, and independent verifier behavior. This phase must not change consensus.

## Aetherion role

Aetherion's Caduceus / dual-pillar / I Ching / spectral / phonetic pipeline may generate *advisory* anomaly features or propose counterexamples. Every such output must identify the exact input digest, code/model version, deterministic parameters, and output digest. It cannot issue a `VALID` decision, satisfy a required signer role, change policy, or authorize settlement. A separate deterministic verifier evaluates the published policy.

The ternary kernel `{-1, 0, 1, 3}` is not used as a cryptographic primitive. If used for feature encoding, its mapping (including `3 -> (-1,0,1)`) must be versioned and tested, and it must not affect signature or hash semantics.

## Business applications

1. **Trade finance / invoice settlement:** buyer, seller, and logistics provider attest to purchase order, delivery milestone, and invoice digest; payment is proposed only after policy checks and separately authorized by existing EXCAL signing rules.
2. **Supply-chain provenance:** manufacturers, carriers, and inspectors sign custody transitions; selective disclosure limits what a counterparty sees.
3. **Warranty and service history:** service providers attest to work performed and parts used; later buyers verify provenance without receiving private customer records.
4. **Insurance claims:** evidence providers attest to scoped observations; claims remain subject to insurer policy and human/legal review.
5. **Camelot Fair:** server-signed match results and anti-cheat evidence can be verified before reward settlement; client-reported achievements alone are insufficient.

## MVP implementation sequence

1. Write deterministic serialization and fixed test vectors.
2. Implement envelope hashing and evidence Merkle proofs.
3. Implement signature verification and trust-root / role / revocation checks.
4. Implement replay protection and explicit verifier outcomes.
5. Add adversarial tests: altered bytes, wrong network/genesis, expired key, revoked key, duplicate nonce, role substitution, malformed CBOR, reordered attachments, missing evidence, stale revocation data, and conflicting predecessor.
6. Build a CLI verifier that works offline from an evidence bundle and pinned trust snapshot.
7. Add a read-only HTTP API for verification reports.
8. Run two independent implementations against the same vectors before considering EXCAL anchoring.
9. Obtain an external cryptographic and privacy review before production or handling funds.

## Acceptance criteria

- Two independently implemented verifiers produce byte-identical event digests and equivalent verification outcomes for all published vectors.
- Every malformed or ambiguous input is rejected.
- No private business payload is written to EXCAL.
- No PCBE outcome can bypass EXCAL's current signature validation or URUU/FROST authorization gates.
- The verifier can explain *why* an event is valid, invalid, incomplete, expired, revoked, disputed, or unverifiable.
- Security review, privacy review, operational key controls, and production test evidence are published before any production claim.

## Standards alignment

Use established standards where they fit: deterministic CBOR (RFC 8949), W3C Verifiable Credentials Data Model 2.0 and Data Integrity 1.0 where credential exchange is needed, and mature signature/hash suites. This design is a proposed EXCAL application protocol, not a claim of standards certification or a novel cryptographic primitive.
