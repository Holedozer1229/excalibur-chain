# AetherionEXCAL v3.0.1 — Quantum Spacetime & SkyNet Hardening

**Release Tag:** `v3.0.1`  
**Author:** Travis Dale Jones (`Holedozer1229`)  
**Date:** November 17, 2026  
**Commit:** `HEAD`  

---

## Overview

AetherionEXCAL v3.0.1 delivers comprehensive stability enhancements, full static inspection resolution, and hardened decentralized networking across the entire Aetherion-Excalibur ecosystem.

This release compiles updated Windows executables with integrated Inno Setup installer packaging, incorporating all recent fixes for quantum spacetime simulation, EREPR P2P gossiping, and Trifold lockbox consensus rules.

---

## What's Changed

### 1. Quantum Spacetime Fabric & Orchestrator
- **Unitary Operator Tensoring**: Added multi-qubit Kronecker product expansion (`_build_full_operator`) to evaluate arbitrary gate matrices (`H`, `X`, `T`, `S`, and custom unitary operators).
- **Curvature Wave Equation Integration**: Coupled 2D discrete Laplacian spatial curvature evolution with damping to model spacetime perturbation dynamics.
- **Dynamic Wormhole Topology**: Automated detection of high-curvature coordinate pairs and entanglement-threshold causal bridges.
- **State Vector & Purity**: Added pure state vector density matrix projection ($Tr(\rho^2)$) and von Neumann entropy computation.

### 2. SkyNet & EREPR Protocol Hardening
- **Handshake Echo Accounting**: Corrected initial entanglement bond count to ensure initial handshake echo messages are accurately registered prior to periodic heartbeats.
- **P2P Resonance Tracking**: Enhanced toroidal phase coherence and frequency matching across distributed nodes.

### 3. Consensus & Cryptographic Verifications
- **Trifold Lockbox Safety**: Corrected non-dust value minimums and loop assertion invariants in UTXO state validation.
- **Python Bytecode Integrity**: Resolved all syntax, encoding (CP1252 to UTF-8), and unbound local variable defects across 100% of codebase modules.
- **Author Attribution**: Unified author attribution across all manuscripts, arXiv submissions, and whitepapers strictly to **Travis Dale Jones**.

### 4. Decentralized Web & IPFS Domain Registration
- **IPNS Domain**: `k51qzi5uqu5dhgx5v1zp19ly9boliz5hd1vmbc6h5cj955z0eicir1vgk07z0k`
- **IPFS Content Identifier (CIDv1)**: `bafybeibq4jkcsm6nzdmbol5k3mpotpkjhj63guuxci6r57sa6kecqorsr4`
- **DNSLink DNS Records**:
  - `_dnslink.skynet.aetherion-oracle.com`: `dnslink=/ipns/k51qzi5uqu5dhgx5v1zp19ly9boliz5hd1vmbc6h5cj955z0eicir1vgk07z0k`
  - `_dnslink.aetherionexcal.eth`: `dnslink=/ipfs/bafybeibq4jkcsm6nzdmbol5k3mpotpkjhj63guuxci6r57sa6kecqorsr4`
- **Decentralized Gateway Access**:
  - `https://dweb.link/ipns/k51qzi5uqu5dhgx5v1zp19ly9boliz5hd1vmbc6h5cj955z0eicir1vgk07z0k`
  - `https://bafybeibq4jkcsm6nzdmbol5k3mpotpkjhj63guuxci6r57sa6kecqorsr4.ipfs.dweb.link/`

---

## Release Artifacts & Checksums

| Asset | File Size | SHA-256 Checksum |
| :--- | :--- | :--- |
| **`AetherionEXCAL-Setup-3.0.0.exe`** | 138,992,754 bytes | `28522F18195193321CBCACED8507D9E7A973B1943AC29260C9D6747613C778B3` |
| **`AetherionEXCAL.exe`** | 38,488,565 bytes | `B696DA96D2AD3DCFD6FE27188E82A0A0B65B00563BC5D3E812FC8457B4E47817` |
| **`AetherionEXCAL-Beacon.exe`** | 26,606,147 bytes | `BF7CD1863391BB2C460A8DE269F68E858A4EF71ED91AC11CDB5B5C271C02B468` |
| **`AetherionEXCAL-StratumMiner.exe`** | 10,061,154 bytes | `ED703EC3FB52A4557DA543525D6DE7EB82DFE03D8691D1A3B82ADA350F3728E1` |
| **`AetherionEXCAL-P2P.exe`** | 37,312,132 bytes | `6561BBEC014E597C5705255A11A6B1D05594F0C50E9D0E1A800B4F4DD65AA80E` |

---

## Quick Start

### Windows Installation
1. Download **`AetherionEXCAL-Setup-3.0.0.exe`**.
2. Run the installer to install the full suite (Desktop Wallet, SkyNet Beacon, Stratum Miner, and P2P Client).
3. Check the option **"Start SkyNet Beacon on login"** to participate in the decentralized discovery mesh.

### Standalone Wallet Execution
```powershell
.\dist\AetherionEXCAL.exe
```

### SkyNet Beacon (Always-On Discovery)
```powershell
.\dist\AetherionEXCAL-Beacon.exe
```
