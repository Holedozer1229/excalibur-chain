# AetherionEXCAL — Letter to Coinbase Listing Team

---

**Date:** November 12, 2026

**To:** Coinbase Listing Committee
**From:** AetherionEXCAL Project Team
**Subject:** Exchange Listing Request — EXCAL (AetherionEXCAL)

---

Dear Coinbase Listing Team,

I am writing to formally request consideration for listing **EXCAL** (AetherionEXCAL) on the Coinbase exchange. EXCAL is a live, production-ready blockchain that combines Bitcoin's proven proof-of-work security with post-quantum cryptographic protections, and we have implemented a complete **Coinbase Rosetta API** integration to facilitate seamless exchange connectivity.

## Why EXCAL?

**EXCAL is the new Qrevolution.** It is a Bitcoin fork anchored at Bitcoin block 968,698, with over 25,600 blocks of verified proof-of-work. Unlike concept projects or simulations, EXCAL is a **living chain** with active mining, a full wallet ecosystem, and comprehensive documentation.

### What Makes EXCAL Unique

1. **Post-Quantum Security from Day One** — EXCAL uses SHA-256 hash-only signatures with no elliptic curves in the spend path. From height 25,212, PQH (Post-Quantum Hash) locks are enforced, and from height 25,901, every block carries a Trifold countersignature over its parent's header. This makes EXCAL one of the first production blockchains with post-quantum security guarantees.

2. **Bitcoin-Compatible Mining** — EXCAL uses SHA-256d proof-of-work, compatible with standard mining hardware. CPU and GPU mining are both supported, and merge mining (AuxPoW) is accepted from height 23,785. This ensures broad miner participation and network security.

3. **Responsive Difficulty Adjustment** — Unlike Bitcoin's 2,016-block retarget interval, EXCAL retargets every 60 blocks (~60 minutes), keeping block times stable at 60 seconds even during dramatic hashrate changes.

4. **21 Million Supply Cap** — EXCAL mirrors Bitcoin's supply schedule: 21M max supply, 50 EXCAL initial block subsidy, halving every 210,000 blocks. This creates familiar, predictable tokenomics for traders and investors.

## Rosetta API Compliance

We understand that Coinbase values standardized, well-documented APIs for blockchain integration. That is why we have implemented a **complete Coinbase Rosetta API** configuration:

- **Data API** — Full support for network status, block retrieval, transaction listing, mempool queries, and account balance lookups
- **Construction API** — Complete transaction building pipeline: derive, preprocess, metadata, payloads, combine, and parse
- **Configuration Files** — All Rosetta CLI configuration files are provided and validated
- **Standard Error Codes** — Consistent error handling following Rosetta specification

All Rosetta configuration files are available in the `coinbase/` directory of our repository and can be validated using the Rosetta CLI:

```bash
rosetta-cli check:data --configuration-file coinbase/rosetta-cli/config.json --network mainnet
rosetta-cli check:construction --configuration-file coinbase/rosetta-cli/config.json --network mainnet
```

## Security Posture

Security is foundational to EXCAL:

- **AES-256-GCM encryption** for all key storage and network messaging — no plaintext keys
- **scrypt KDF** (N=2^14) for passphrase-derived key encryption (NIST SP 800-132 compliant)
- **SHA-256 hash-only signatures** — no elliptic curves vulnerable to quantum attacks
- **Post-quantum Trifold** block countersigning (ternary Merkle tree, 729 leaves per epoch)
- **126 passing unit tests** covering all core modules
- **Full security audit** with all critical issues resolved

## Tokenomics Summary

| Parameter | Value |
|---|---|
| Ticker | EXCAL |
| Max Supply | 21,000,000 EXCAL |
| Block Time | 60 seconds |
| Consensus | SHA-256d Proof-of-Work |
| Halving | Every 210,000 blocks (~3.27 years) |
| Initial Subsidy | 50 EXCAL |
| Transaction Fees | None (subsidy-only) |

## Wallet Ecosystem

EXCAL provides a complete wallet ecosystem for users:

- **AetherionEXCAL GUI Wallet** — Premium desktop wallet with AES-256-GCM encryption, multi-wallet profiles, P2P networking, and Prometheus monitoring
- **Holo-wallet** — Command-line wallet for scripting and automation
- **Compiled executables** — Windows (.exe) and Mac builds available

## Documentation

All documentation is publicly available and can be independently verified:

- **Website:** https://www.aetherion-oracle.com
- **Tokenomics:** [TOKENOMICS.md](../TOKENOMICS.md)
- **Governance:** [GOVERNANCE.md](../GOVERNANCE.md)
- **Security Audit:** [AUDIT.md](../AUDIT.md)
- **Rosetta API:** [coinbase/rosetta.md](rosetta.md)
- **Listing Proposal:** [coinbase/listing-proposal.md](listing-proposal.md)

## Honest Scope

We want to be transparent: EXCAL currently has no established market and no price. No return is promised or implied. What we offer is:

- A **live, verifiable blockchain** with 25,600+ blocks of proof-of-work
- **Post-quantum security** that protects against future quantum computing threats
- **Full Rosetta API compliance** for straightforward exchange integration
- **Complete transparency** — all code, data, and decisions are public and auditable

## Next Steps

We would welcome the opportunity to:

1. **Demonstrate** the Rosetta API integration and walk through the validation process
2. **Provide** access to testnet for Coinbase's integration team
3. **Discuss** listing requirements and any additional documentation needed
4. **Answer** any technical questions about the EXCAL protocol, security, or tokenomics

## Contact

- **Website:** https://www.aetherion-oracle.com
- **GitHub:** https://github.com/excalibur-chain/excalibur-chain
- **Rosetta Files:** `coinbase/` directory in the repository

Thank you for your time and consideration. We believe EXCAL's post-quantum security, Bitcoin-compatible mining, and Rosetta API compliance make it a strong candidate for Coinbase listing. We look forward to the possibility of working together.

Sincerely,

**The AetherionEXCAL Team**
https://www.aetherion-oracle.com

---

*This letter is provided for informational purposes. EXCAL is a live blockchain with verifiable on-chain data. All claims can be independently verified using the tools and documentation referenced above. No financial return is promised or implied.*
