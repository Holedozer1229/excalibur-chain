# Aetherion Verifiable Attestations (AVTA v1)

AVTA is an evidence envelope and verifier for reproducible claims. It is an
observer/audit layer. It is **not** part of EXCAL consensus, block validation,
wallet signing, issuance, or settlement.

## What a valid result means

A verifier returns `valid` only when all of the following hold:

1. The envelope matches the exact versioned schema.
2. The caller supplies inputs and evidence matching the committed SHA-256 digests.
3. The caller supplies the exact method source bytes matching the method digest.
4. The attestation is within its signed validity window.
5. The Ed25519 signature verifies against a locally trusted issuer key.

A signature proves possession of a key. The local `trusted_issuers` registry
is what binds that key to an issuer identifier. A digest proves byte/data
identity, not factual correctness. A `claimed_result` of `verified` is a
claim by the issuer, not a substitute for independently rerunning the method.

The four claimed result states are `verified`, `rejected`, `inconclusive`,
and `disputed`. There is no aggregate truth score.

## Envelope fields

- `schema`: `aetherion.avta.v1`
- `claim`: bounded human-readable proposition
- `method`: `id`, `version`, and SHA-256 of exact method source bytes
- `inputs_sha256`, `evidence_sha256`: commitments to canonical JSON values
- `counterexample_sha256`: optional commitment to a canonical JSON counterexample
- `result`: one of the four explicit result states
- `issued_at`, `expires_at`: Unix seconds
- `nonce`: unique caller-generated lowercase hex value (replay tracking is the registry's responsibility)
- `issuer_id`: identifier resolved through a local trust registry
- `signature`: base64 Ed25519 signature over canonical JSON of all preceding fields

Canonical JSON sorts keys, uses compact separators and UTF-8, and rejects
floating-point values. Numeric evidence should use integers or exact strings.

## Minimal use

```python
from aetherion_verifier import digest, sign_attestation, verify_attestation

payload = {
    "schema": "aetherion.avta.v1",
    "claim": "The supplied block record matches the node's reported tip",
    "method": {
        "id": "excal-tip-cross-check",
        "version": "1",
        "sha256": "<sha256 of exact method source bytes>",
    },
    "inputs_sha256": digest({"height": 123}),
    "result": "verified",
    "evidence_sha256": digest({"reported_hash": "<64 hex>"}),
    "counterexample_sha256": None,
    "issued_at": 1_800_000_000,
    "expires_at": 1_800_003_600,
    "nonce": "0123456789abcdef0123456789abcdef",
    "issuer_id": "observer-01",
}
# private_key is a cryptography.hazmat.primitives.asymmetric.ed25519 key.
signed = sign_attestation(payload, private_key)
result = verify_attestation(
    signed,
    inputs={"height": 123},
    evidence={"reported_hash": "<64 hex>"},
    method_source=exact_method_source_bytes,
    trusted_issuers={"observer-01": raw_32_byte_public_key},
)
```

## EXCAL observer

Run from the repository root:

```bash
python -m aetherion_verifier.excal_observer
```

The module is a library entry point; use `observe_tip("http://127.0.0.1:9432")`
from a local script. It only calls `getblockcount`, `getbestblockhash`,
and `getblockbyheight`. The node RPC must remain private and loopback-bound.
Do not expose port 9432 to the public internet: the current RPC handler has no
authentication layer.

## Deliberate limitations

- No consensus changes or ledger anchoring.
- No automatic block rejection, peer banning, transaction freezing, or payout.
- No identity trust without an operator-managed issuer registry.
- No replay prevention without a persistent nonce registry.
- No claim that one RPC endpoint proves the chain is honest.
- The observer cross-checks a single node's own RPC responses; it is not a
  substitute for `genealogy_verify.py`, full node validation, or independent
  peer comparison.
