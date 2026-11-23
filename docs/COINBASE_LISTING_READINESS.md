# Coinbase Listing Readiness — EXCAL

**Status date:** 2026-11-23  
**Purpose:** Engineering evidence pack for an already-submitted Coinbase asset-listing application.  
**Scope:** Documentation and readiness tracking only. This document does not claim Coinbase approval, a completed audit, production readiness, or a listing date.

## Executive status

EXCAL is a native blockchain asset, not merely a token contract on a network Coinbase already supports. Coinbase's issuer FAQ says a utility token on an unsupported blockchain requires a Rosetta implementation; it describes roughly six weeks as typical for that implementation after approval, followed by Coinbase validation and wallet integration. Coinbase controls review and prioritization.

**Do not represent EXCAL as Coinbase-integrated until a complete Rosetta implementation has been independently tested and accepted by Coinbase.**

## Verified repository facts and open gates

| Area | Current evidence | Status / required proof |
|---|---|---|
| Source | Public repository: https://github.com/Holedozer1229/excalibur-chain | Available |
| Native chain | EXCAL repository contains its own chain implementation and fork parameters | Document exact production network identity, chain ID, genesis hash and current tip |
| Consensus | Current implementation uses Bitcoin-style SHA-256d PoW; Aetherion ergotropic PoW is design-only in draft PR #17 | Do not describe Aetherion PoW as active |
| Fork choice | Draft PR #21 changes deep-reorg handling to cumulative-work-only selection | Consensus-sensitive; requires deterministic multi-node reorg tests and coordinated rollout |
| P2P | Draft PR #20 changes fork-network P2P bind defaults | Public reachability and independent peer convergence not yet demonstrated |
| Bitcoin inheritance | Draft PRs #15/#16 document and harden snapshot handling around Bitcoin height 968,698 | Exact complete UTXO set, independent Core MuHash checks, script compatibility and activation proof remain blockers |
| Wallet/signatures | Repository changes must preserve current signature rules until compatibility is demonstrated | Publish supported script types, sighash rules, signing vectors and negative tests |
| Rosetta | No verified accepted Rosetta implementation is established by this readiness record | Build, test and document Rosetta before claiming native Coinbase integration readiness |
| Security audit | No completed independent audit is evidenced by this record | Commission independent consensus, wallet, P2P and snapshot review; publish scope and remediation status |
| Network operations | Draft community-node work exists | Publish operator guide, seed discovery, monitoring, incident response, upgrade policy and reproducible build hashes |
| Explorer/API | Must be verified against the live production network | Publish stable explorer, documented read APIs and independently reproducible chain status |
| Token economics | Project convention: 100,000,000 swords = 1 EXCAL; intended unit mapping 1 sword = 1 satoshi | Clearly distinguish denomination from market-price peg; publish issuance, supply, rewards, allocations and unlocks |
| Legal/compliance | Not established by this engineering review | Obtain counsel review; publish issuer/team, jurisdiction, distribution and risk disclosures |

## Today: prioritized completion sequence

### P0 — Do not misstate readiness
1. Freeze claims that EXCAL is audited, Coinbase-approved, Coinbase-integrated, or live on Coinbase unless documentary evidence exists.
2. Keep Bitcoin inherited balances disabled until exact-height snapshot completeness, independent MuHash validation and script-spend compatibility are proven.
3. Keep experimental Aetherion PoW and FROST signing disabled from consensus/funds paths until separately validated and reviewed.
4. Do not merge consensus-sensitive PR #21 or activate PR #20 without successful multi-node tests and a coordinated rollout plan.

### P1 — Coinbase integration evidence
1. Identify the exact production network: chain ID/network identifier, genesis hash, anchor hash, consensus parameters, current height and canonical node release.
2. Implement the Coinbase-required Rosetta API for the actual production chain. At minimum, document and test network discovery, network status, block retrieval, account/balance lookup, construction/preprocess/metadata/payloads/combine/parse/hash/submit flows as applicable to the supported transaction model.
3. Add Rosetta conformance tests, deterministic fixtures, replay tests, reorg behavior tests and a public staging endpoint.
4. Publish reproducible node and Rosetta builds, checksums, container images, deployment instructions, rate limits and service-level monitoring.
5. Demonstrate independent node synchronization and peer convergence from a clean data directory.

### P2 — Due diligence packet
1. Whitepaper and protocol specification.
2. Token supply, issuance, allocation, treasury, rewards and unlock schedule.
3. Team/issuer identity and contact information suitable for formal due diligence.
4. Governance, upgrade authority, emergency controls and decentralization disclosures.
5. Security audit(s), scope, findings and remediation evidence.
6. Legal analysis and jurisdiction/risk disclosures.
7. Public explorer, wallet, source code, release artifacts, network status and incident contacts.
8. Genuine adoption, holder, usage and liquidity metrics with methodology; never manufacture volume or holders.

## Submission follow-up

Coinbase's published guidance says teams should submit accurate, complete information and respond promptly to requests. Do not send repeated generic status requests. If a material correction or new evidence is ready, send one concise update through the official issuer channel, clearly separating completed facts from work in progress.

Suggested update structure:
- Asset: EXCAL (native blockchain)
- Original application reference: [insert Coinbase reference]
- Repository: https://github.com/Holedozer1229/excalibur-chain
- Production network: [chain ID, genesis hash, explorer, node release]
- New evidence since submission: [only verifiable completed items]
- Known limitations: [explicitly list unresolved items]
- Integration support: [Rosetta endpoint and conformance results, only when ready]
- Technical contact: [official project contact]

## Release gate

A Coinbase-ready claim may be made only when all applicable evidence is public and reproducible. This document is a gap register, not a certification. Draft PRs are not production releases; unexecuted tests are not passing tests; an exported snapshot is not a verified UTXO set; and an application is not an approval.
