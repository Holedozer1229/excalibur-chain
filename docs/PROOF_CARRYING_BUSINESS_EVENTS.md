# EXCAL Proof-Carrying Business Events (PCBE)
## Design proposal — off-consensus, independently verifiable business evidence

**Status:** application-layer reference implementation added; production use remains blocked pending tests, independent verifier agreement, durable replay storage, trust-root governance, privacy review, and external security review.  
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


## Reference implementation profile (initial, non-production)

The first Python implementation lives in `pcbe/core.py`; focused adversarial tests live in `tests/test_pcbe.py`. It intentionally implements a restricted deterministic-CBOR data model (null, booleans, signed integers, byte/text strings, arrays, and text-keyed maps; no floats, tags, indefinite lengths, or non-text keys).

The implementation fixes these v1 details:

- Evidence digest: `SHA-256("EXCAL-PCBE-EVIDENCE-v1" || deterministic_cbor([media_type, exact_bytes]))`.
- Merkle leaf: `SHA-256(0x00 || evidence_digest)`; node: `SHA-256(0x01 || left || right)`; an unpaired final node is promoted unchanged. Evidence order is significant.
- Event digest: `SHA-256("EXCAL-PCBE-EVENT-v1" || deterministic_cbor(event_without_signatures))`.
- Ed25519 attestation message: domain-separated deterministic-CBOR array containing event digest, role, key ID, policy version, and fixed context string.
- The verification policy must pin both network name and 32-byte genesis hash; a mismatch is rejected.
- Non-empty predecessor lists return `UNVERIFIABLE` until a predecessor resolver is configured. No predecessor relationship is silently assumed valid.
- Replay registry is an in-memory reference implementation only. A production verifier must provide durable, atomic, network-scoped replay storage.
- Verification requires an explicit fresh revocation snapshot; missing, future-dated, or stale trust/revocation data returns `UNVERIFIABLE`.

The implementation is not yet a complete PCBE deployment: it does not provide a production trust-root distribution mechanism, durable replay database, predecessor-chain resolver, evidence-byte retrieval service, HTTP API, CLI, or independent second implementation. Its local Ed25519 profile must be reviewed against the issuer ecosystem before interoperability claims. The test workflow is not evidence of passing until GitHub Actions actually executes the test steps successfully.

## Acceptance criteria

- Two independently implemented verifiers produce byte-identical event digests and equivalent verification outcomes for all published vectors.
- Every malformed or ambiguous input is rejected.
- No private business payload is written to EXCAL.
- No PCBE outcome can bypass EXCAL's current signature validation or URUU/FROST authorization gates.
- The verifier can explain *why* an event is valid, invalid, incomplete, expired, revoked, disputed, or unverifiable.
- Security review, privacy review, operational key controls, and production test evidence are published before any production claim.

## Standards alignment

Use established standards where they fit: deterministic CBOR (RFC 8949), W3C Verifiable Credentials Data Model 2.0 and Data Integrity 1.0 where credential exchange is needed, and mature signature/hash suites. This design is a proposed EXCAL application protocol, not a claim of standards certification or a novel cryptographic primitive.


## Cross-domain expansion: EXCAL Verified Infrastructure

PCBE is a common evidence and verification substrate with separately versioned domain profiles. Each profile defines event schemas, trusted issuer roles, evidence requirements, validation procedures, retention rules, and dispute handling. Domain-specific checks must not be confused with the base cryptographic envelope.

### Shared architecture

1. Producers: spacecraft, ground stations, quantum processors, AI pipelines, enterprises, and authorized people create signed event bundles.
2. Evidence adapters normalize source records while preserving original bytes, source identity, timestamps, calibration/configuration context, and provenance.
3. PCBE envelope commits to the event, evidence, network/domain, policy version, nonce, and role-bound attestations.
4. Independent verifiers validate signatures, issuer authority, schema, replay protection, evidence commitments, and domain-specific rules.
5. Optional EXCAL anchor records a minimal commitment after privacy and fee review. The anchor does not certify the underlying fact.
6. Evidence remains encrypted/off-chain; access is granted to authorized reviewers, with selective disclosure where supported.

Profiles are independent modules. A failure or upgrade in one domain must not silently alter another profile or EXCAL consensus.

### Space operations profile

Suggested event types: spacecraft.component_registered, launch.readiness_attested, mission.telemetry_window, orbit.maneuver_executed, docking.contact_confirmed, cargo.custody_transferred, maintenance.performed, and mission.milestone_reached.

Required context may include spacecraft and component identifiers (preferably pairwise or pseudonymous where possible), mission ID, event time plus clock source/uncertainty, telemetry interval commitment, sensor identity, calibration record, software/firmware build, operator role, and ground-station receipt. High-consequence events should require independent attestations from distinct organizations or systems, not merely multiple keys controlled by one operator.

Validation limits: signatures prove which key attested to a telemetry record, not that the sensor was correctly installed or physically accurate. Profiles must define clock drift, packet loss, sensor calibration, fault tolerance, ground-station corroboration, and emergency override procedures. EXCAL is not a flight-control system and must never sit in a real-time safety-critical control loop. Mission commands and safety decisions remain with certified mission systems and accountable operators.

### Quantum computing profile

Suggested event types: quantum.job_submitted, quantum.circuit_committed, quantum.device_calibrated, quantum.job_executed, quantum.result_attested, and quantum.error_correction_reported.

Commit to the circuit/program representation, compiler and transpiler versions, backend/device identity, calibration snapshot, job parameters, shot count, timestamps, software/container digest, and result artifact. Where appropriate, include randomized benchmarking or calibration evidence, error rates, confidence intervals, and reproducibility metadata. Keep proprietary circuits and raw results off-chain unless the owner explicitly authorizes disclosure.

Validation limits: a signed result establishes provenance and integrity, not computational correctness. Verification may require rerunning circuits, comparing independent devices, checking known-answer circuits, analyzing statistical uncertainty, and accounting for noise and calibration drift. A quantum job output must not be treated as a cryptographic proof merely because it came from quantum hardware. Quantum-resistant cryptography is a separate migration track: inventory algorithms, define crypto-agility, and adopt standardized post-quantum algorithms only after interoperability and security review. Do not invent a quantum signature or claim quantum advantage.

### AI data and model lifecycle profile

Suggested event types: ai.dataset_registered, ai.consent_recorded, ai.preprocessing_run, ai.training_run, ai.model_evaluated, ai.model_released, ai.inference_attested, and ai.model_revoked.

Commit to dataset manifests and versioned lineage, collection/consent/licensing basis, transformation code and parameters, training configuration, model weights/artifact digest, evaluation datasets and metrics, safety review, deployment build, and inference context. Record model and tool versions and distinguish human-authored, model-generated, and externally sourced content. For inference attestations, state the limits of the execution environment and whether hardware-backed attestation was actually verified.

Privacy and governance: do not publish raw prompts, personal data, training examples, model weights, secrets, or customer payloads by default. A hash does not make personal data anonymous if the source can be linked or guessed. Support deletion/retention obligations for off-chain content while retaining only lawful, minimal commitments. Consent, licensing, provenance, and copyright status require evidence and legal policy; a signature alone does not establish that training was lawful.

Validation limits: provenance does not prove that a dataset is representative, unbiased, licensed, or factually correct. Model evaluation must be task-specific, reproducible where possible, and independently reviewable. AI-generated summaries and Aetherion anomaly scores remain advisory; they cannot self-certify their own correctness or authorize funds.

### Profile governance and interoperability

- Publish a registry of profile identifiers, schema versions, required roles, evidence types, and verifier conformance vectors.
- Use explicit version negotiation; unknown profile versions fail closed as UNVERIFIABLE.
- Require domain experts and independent security reviewers to approve profile changes.
- Preserve original source artifacts and cryptographic provenance; normalized data must never replace the source record.
- Define trusted timestamp sources and uncertainty for each profile. Do not assume all clocks are synchronized.
- Separate proof of integrity, proof of origin, proof of authority, proof of execution, and proof of a real-world outcome. Each is a distinct claim with distinct evidence.
- Never let a domain profile change EXCAL consensus, issuance, existing spend signatures, or wallet authorization.

### Commercial deployment path

Start with a low-risk, auditable pilot: AI dataset/model lineage or supply-chain component provenance. Then add space and quantum profiles using synthetic or non-safety-critical test data, independent verifier implementations, and domain-expert review. Only after measured conformance, threat modeling, privacy review, and operational audits should any profile be used for high-value commercial settlement or mission-critical records.

These profiles define a scalable architecture and candidate use cases. They are not yet implemented, certified, flight-qualified, quantum-verified, or production-ready.
