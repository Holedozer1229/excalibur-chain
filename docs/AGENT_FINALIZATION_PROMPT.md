# EXCAL / EXS — Agent Finalization Prompt

Use this prompt with your repository agent. Work in the existing repositories; implement, test, commit, and push real changes. Do not stop at another plan.

## Repositories and branches

### EXCAL
Repository: `Holedozer1229/excalibur-chain`

- Rosetta PR #23: `feature/excal-rosetta-native-v1`
- Known head when this prompt was prepared: `cbe952cb9bdc0d45571a1db6a4579f7ad42fc953`
- Business Events PR #24: `feat/proof-carrying-business-events`
- Known head: `1ff8a73838d18f2fdc4bd527a0733ac6c750f0d7`

### EXS
Repository: `Holedozer1229/Excalibur-EXS`

- Security Rebuild PR #67: `security/rebuild-spec-v0.1`
- Known head: `1ac9020436d8fa2581950c3b639e8124ccf0a988`

These are starting references, not permission to overwrite newer remote work.

## 1. Inspect before editing

1. Fetch both repositories and inspect all three branches, PRs, commits, working trees, remotes and CI.
2. Reconcile remote changes. Preserve uncommitted work; never reset, force-push, or overwrite another contributor's changes.
3. Confirm exact starting commit and working-tree state.
4. Keep EXCAL and EXS work separate and on their existing branches.

## 2. Finish EXCAL Rosetta — PR #23

Complete and verify the Rosetta Data and Construction APIs against actual canonical chain state.

- Data API: network/list, network/options, network/status, block, block transaction, account balance, mempool and historical UTXO/balance reconstruction.
- Construction API: derive, preprocess, metadata, payloads, combine, parse, hash and submit.
- Verify transaction encodings, supported lock/witness paths, activation rules, coinbase maturity, replay protection, timeout/refund behavior, historical prevouts and fee reconciliation.
- Do not fabricate blocks, balances, status, mempool acceptance or peer relay.
- Clearly distinguish local mempool admission from actual network propagation.
- Run focused tests, full relevant test suite, compile/lint/format checks and official rosetta-cli conformance where feasible.
- Fix actual defects and add deterministic regression tests. Never weaken or delete tests to get green CI.
- Document unsupported features and custom signature extensions.

## 3. Implement Proof-Carrying Business Events — PR #24

Turn the existing specification into a working, tested implementation.

- Deterministic serialization; domain-separated commitments; evidence hashes; role-bound signatures; expiry; replay protection; predecessor validation.
- Verifier outcomes: VALID, INVALID, INCOMPLETE, EXPIRED, REVOKED, DISPUTED and UNVERIFIABLE.
- Add positive, negative, tamper, expiry and reproducibility tests plus test vectors.
- A valid signature proves integrity/key control, not that a real-world claim is true.
- Keep PII and sensitive evidence off-chain by default.
- No automatic payment authorization and no EXCAL consensus/genesis/wallet changes.

## 4. Complete EXS Security Rebuild — PR #67

Implement only what can be safely completed and tested; keep unresolved items explicitly marked.

- Remove unsafe wallet/key derivation and address-generation behavior.
- Never derive wallet secrets from public prophecy text, public genesis data or public salts.
- Never print, log, commit or transmit private keys, seed phrases or recovery secrets.
- Use reviewed secp256k1, BIP340, BIP341 and Bech32m implementations with official known-answer vectors.
- Do not represent mock guardian approvals, synthetic signatures or simulated FROST as production cryptography.
- Audit Trifold, HTLC, QHTLC, KNOT and Taproot separately; demonstrate compatibility with real implementations and vectors before claiming security.
- Reconcile conflicting genesis, supply and treasury specifications. Do not mine, fund, activate or replace genesis.
- Make consensus-critical arithmetic deterministic and integer-based; add reproducibility tests.
- Keep a clear threat model, migration plan, limitations and independent-review checklist.

## 5. Non-negotiable architecture constraints

- Preserve existing EXCAL consensus, genesis, chain history, wallet rules and signature behavior.
- Do not silently replace or reset EXCAL. ExcalOmega EXS is a separate proposed genesis chain.
- Aetherion, Caduceus, I Ching, Riemann-zero analysis and ternary logic may be advisory/analytics only; never consensus truth or cryptographic primitives.
- Public prophecy words are not secret entropy.
- No fake nodes, mock balances, simulated peer delivery or placeholder signatures presented as real.
- No unsupported claims of cryptographic security, production readiness, test success, deployment or exchange acceptance.
- Do not merge PRs, change default branches, alter genesis, fund wallets or deploy production infrastructure without explicit authorization.

## 6. Commit and push

For each existing branch:

1. Implement the highest-priority safe fixes.
2. Run targeted tests and the full relevant suite.
3. Run configured formatting, lint, static checks and builds.
4. Inspect the complete diff for secrets, accidental changes and regressions.
5. Commit coherent changes with descriptive messages.
6. Push to the existing remote branch; do not force-push.
7. Verify the remote head equals the new commit SHA.
8. Update the corresponding PR with changes, exact test evidence, limitations and remaining blockers.

If CI fails before executing test steps, diagnose runner infrastructure separately and run equivalent checks in a reproducible local/available environment. Never report infrastructure failure as a code-test failure or as a passing test.

## 7. Final report

Report:

- Branches updated and exact commit SHAs.
- Files changed.
- Exact test commands and pass/fail counts.
- CI links and current status.
- Remaining security, consensus, interoperability and deployment blockers.
- What is genuinely complete versus experimental.
- Exact next steps for Coinbase integration readiness.

Push all safe, completed changes to their existing branches. Leave pull requests open until release gates are satisfied. Do not claim Coinbase readiness or listing approval without evidence.
