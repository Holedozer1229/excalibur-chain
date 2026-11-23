# URUU + FrostGate key-control architecture for EXCAL

Status: integration design only. This document does not activate signing, recovery, key rotation, or treasury movement.

## 1. Roles and source code

### URUU Secure Recovery — policy and recovery workflow

Reuse the state-machine and data-model concepts from `Holedozer1229/Uruu-Secure-Recovery`:
- recovery request and policy commitments,
- guardian roster and approval records,
- quorum requirement,
- timelock,
- contest/dispute path,
- append-only recovery event history,
- explicit recovery lifecycle and audit record.

**Do not reuse its current cryptographic functions as production security.** The checked-in `artifacts/api-server/src/lib/crypto.ts` labels its operations as simulated: `mockVerifierSign` is HMAC with a demo fallback secret, and `mockVerify` accepts sufficiently long proof blobs without verifying a proof. The current guardian-approval route stores the supplied signature but does not cryptographically verify it. Its quorum is hardcoded to 2 in the initiate route. These are prototype behaviors, not key-control guarantees.

### FrostGate — threshold signing gate

Use the existing FROST implementation in `Holedozer1229/aethergate` as the threshold-signing reference:
- `aethergate-federation` uses the Zcash Foundation FROST crates and a distributed key-generation API.
- The existing examples exercise 3-of-5 signing and BIP340/Taproot key-path signatures.
- A signer consumes its pending nonce pair once; the coordinator aggregates and verifies signature shares.

This repository currently calls the component Aethergate/FROST, not FrostGate. “FrostGate” in this design means the policy-enforced gate in front of that threshold signer.

**Do not treat this code as production-ready custody.** Its DKG transport is in-process/in-memory, the coordinator is trusted for liveness and message integrity, operator key packages are serialized to JSON files (0600 on Unix, but not encrypted or HSM-sealed), and the FROST Taproot ciphersuite is documented by that repository as outside the cited NCC Group audit scope. Authenticated operator channels, signer-side intent verification, secure share storage, crash-safe session handling, and independent security review are required.

## 2. Separation of duties

1. **URUU policy engine** decides whether a recovery request is eligible to proceed. It never receives private key shares.
2. **Guardian identities** authenticate and sign a domain-separated approval statement binding the request ID, account/key commitment, policy hash, destination or new-key commitment, amount/asset if applicable, expiry, and nonce.
3. **FrostGate policy gate** checks the complete recovery state: valid proof from a real verifier, guardian quorum, timelock elapsed, no active contest, policy version still current, and no replay.
4. **FROST operators** independently verify the exact canonical signing intent before producing their own signature shares. A coordinator cannot substitute a different destination or amount.
5. **EXCAL node/wallet** validates the resulting transaction using its native consensus and script rules. A valid threshold signature does not bypass consensus.
6. **AVTA/Aetherion** can attest to reproducible observations and verification results, but cannot authorize signing or change recovery state.

## 3. Required state machine

```text
INITIATED
  -> PROOF_VERIFIED
  -> GUARDIAN_QUORUM_MET
  -> TIMELOCK_PENDING
  -> READY_FOR_THRESHOLD_SIGNING
  -> THRESHOLD_SIGNED
  -> BROADCAST
  -> CONFIRMED

Any non-final state may enter CONTESTED.
CONTESTED -> RESOLVED_APPROVED | REJECTED
REJECTED and EXPIRED are terminal.
```

No transition is permitted merely because a UI reports an approval count. Every guardian signature must be verified against a registered guardian public key, and the approval message must bind the exact request and policy fields. State transitions must be atomic and replay-protected.

## 4. Canonical signing intent

Before any FROST session, all signers must independently verify a canonical intent containing at least:
- schema and policy version,
- chain ID / network magic and genesis hash,
- operation type (recovery, treasury release, or key rotation),
- request ID and unique nonce,
- source outpoints and amounts,
- destination script/address and exact amount/fee,
- new-key commitment where relevant,
- expiry and timelock evidence,
- hash of the verified proof/AVTA evidence bundle.

The signers then sign the exact chain-native signing digest. Do not sign a generic JSON claim and do not let the coordinator choose an arbitrary digest after guardian approval.

## 5. EXCAL compatibility gate — blocking

The Aethergate code produces 64-byte BIP340 Schnorr signatures for its Taproot key-path flow. EXCAL's active transaction/script implementation must be inspected to establish whether that exact signature type and sighash semantics are consensus-valid on EXCAL.

Until proven:
- do not substitute FROST BIP340 signatures for EXCAL's existing wallet signatures;
- do not modify consensus, script validation, transaction serialization, address derivation, or issuance;
- do not route ordinary user keys through the federation;
- keep the threshold key limited to a separately scoped recovery/treasury authority;
- do not broadcast or move real EXCAL.

If EXCAL does not natively support the required Schnorr/Taproot semantics, the FROST gate must target a compatible off-chain authorization artifact or wait for a separately reviewed protocol design. It must not silently change EXCAL consensus.

## 6. Deployment requirements before real custody

- Independent 5-operator deployment, with operators under separate control and infrastructure.
- Distributed DKG over authenticated, mutually authenticated channels; no trusted dealer.
- Each operator's secret share stored in HSM/secure enclave or encrypted, access-controlled storage; never committed to Git or placed in frontend code.
- Signer-side parsing and verification of canonical intent; no blind signing.
- Unique session IDs, fresh nonce commitments, one-time share generation, replay rejection, and safe abort/restart handling.
- Real Ed25519 guardian authentication and real proof verification; no HMAC demo key and no synthetic proof acceptance.
- Timelock and contest enforcement independent of the web UI.
- Key rotation, guardian removal, quorum changes, recovery cancellation, and emergency pause governed by explicit policy.
- Test vectors, adversarial tests, recovery drills, external audit, and testnet rehearsal before mainnet custody.

## 7. Integration order

1. Keep the existing URUU demo isolated; add a production policy interface rather than upgrading its mock crypto in place.
2. Build a read-only EXCAL chain/network identity adapter.
3. Implement the URUU policy state machine with real guardian signature verification and audit events.
4. Build a FrostGate signer-intent verifier around the existing FROST library.
5. Prove EXCAL signature compatibility on regtest/testnet with independent verification.
6. Run failure/recovery drills and security review.
7. Only then consider an explicitly authorized, narrowly scoped key-control deployment.

## 8. Non-goals

This design does not recover an existing private key, derive user secrets, custody a user's seed phrase, create a BTC peg, change EXCAL consensus, or prove the correctness of Aetherion's symbolic outputs. Users must never be asked to enter wallet seed phrases or private keys into URUU/Aetherion.
