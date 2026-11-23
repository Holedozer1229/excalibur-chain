# EXCAL — Coinbase Evidence Register

Use this register to attach verifiable evidence to the existing Coinbase application. Update a row to **PASS** only when the linked artifact exists, is reproducible, and has been reviewed. A draft PR, design note, or unexecuted test is not a pass.

| ID | Evidence item | Status | Evidence / next action |
|---|---|---|---|
| E-01 | Application reference and submitted answers | OWNER INPUT REQUIRED | Store the Coinbase application ID and a copy of submitted answers privately; do not commit personal or confidential data |
| E-02 | Production chain ID, genesis hash, anchor hash and network parameters | NOT VERIFIED | Publish canonical network identity and independently verify against live nodes |
| E-03 | Current production height and block hash | NOT VERIFIED | Publish explorer/API proof and cross-check from independent operators |
| E-04 | Reproducible node release and checksums | NOT VERIFIED | Build from tagged source and publish hashes and build instructions |
| E-05 | Independent node synchronization and peer convergence | NOT VERIFIED | Run at least three independently operated nodes; record clean-sync, restart and partition/recovery results |
| E-06 | Consensus, fork-choice and reorg test suite | BLOCKED | PR #21 is draft; run competing-branch, restart, reorg-depth and convergence tests before rollout |
| E-07 | P2P reachability and operator documentation | IN PROGRESS | PR #20 is draft; validate inbound peers from outside operator networks; keep unauthenticated RPC private |
| E-08 | Rosetta implementation and conformance | NOT VERIFIED | Build the native-chain Rosetta implementation and publish endpoint plus conformance/replay results |
| E-09 | Wallet transaction/signature vectors | NOT VERIFIED | Document transaction serialization, sighash, supported scripts, signing and verification test vectors |
| E-10 | Bitcoin UTXO snapshot at height 968,698 | BLOCKED | Obtain exact-height complete export with manifest; two independent Bitcoin Core MuHash checks required |
| E-11 | Bitcoin script and ownership compatibility | BLOCKED | Prove each inherited script class remains spendable under EXCAL rules; do not silently credit unsupported scripts |
| E-12 | Token supply and distribution | OWNER INPUT REQUIRED | Publish exact initial/current supply, issuance, allocations, vesting, treasury and distribution methodology |
| E-13 | Legal and regulatory analysis | OWNER / COUNSEL | Obtain qualified counsel review and publish appropriate factual disclosures |
| E-14 | Independent security audit | NOT VERIFIED | Commission review covering consensus, networking, wallet, snapshot import and privileged operations |
| E-15 | Explorer and public API | NOT VERIFIED | Provide production URLs, documented endpoints and independent uptime/consistency checks |
| E-16 | Governance and upgrade controls | NOT VERIFIED | Document who can propose, approve, deploy and roll back protocol changes |
| E-17 | Incident response and disclosure | NOT VERIFIED | Publish security contact, vulnerability disclosure process, incident response and release policy |
| E-18 | Genuine usage, holders and liquidity | OWNER INPUT REQUIRED | Publish sourced on-chain metrics and methodology; do not use fabricated or wash activity |

## Definitions
- **PASS:** completed, independently reproducible evidence linked.
- **IN PROGRESS:** implementation or validation underway; not complete.
- **BLOCKED:** a required dependency is missing.
- **OWNER INPUT REQUIRED:** information only the issuer/project owner can supply.
- **NOT VERIFIED:** no adequate evidence has been attached to this register.

## Change control
Never mark a row PASS solely because a pull request was opened or merged. Record the release tag, commit SHA, test command, test output, operator/source, timestamp and artifact checksum for each completed item.
