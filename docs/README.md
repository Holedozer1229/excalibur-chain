# AetherionEXCAL — the fork you can check

**EXCAL is the new Qrevolution.** A live Bitcoin fork whose block 0 is **Bitcoin block 968,698**, powered by [Aetherion Oracle](https://www.aetherion-oracle.com).

> **🎉 Q-Day is here!** EREPR (Entanglement-Resonance Echo Peer Routing) — our novel quantum-inspired P2P gossip protocol — is live. Nodes discover each other through resonance matching on a toroidal manifold, forming entanglement bonds for authenticated gossip wave propagation. Welcome to the quantum era of P2P.

It does not ask to be believed. Everything below is a measurement you
can re-run.

## What's actually here

- **A living chain.** ~25,600 blocks past the anchor, responsive DAA
  (60-block window, 60-second spacing, 4× clamp), deep-reorg guard.
- **Post-quantum locks, live, not promised.** Since height 25,212 the
  chain enforces PQH locks — `0x02 ‖ hash160(Trifold root)` — spent by
  hash-only Trifold witnesses (~25 KB). No elliptic curves in the spend
  path. The first PQH spend is on-chain (blocks 25,272 / 25,274).
- **A countersigned lineage.** Fork block 25,344 carries a Trifold
  (hash-only) signature over the byte-exact Bitcoin genesis header;
  block 25,351 signs block 25,344's header. Every link verifies with
  nothing but SHA-256.
- **Mine it with any GPU or CPU.** `stratum_fork.py` is a stratum shim in
  front of the node RPC: point a standard SHA-256d stratum miner at
  it and you are mining EXCAL, paid to the node wallet. On Windows,
  `cpu_miner_mp.py` provides a multiprocessing CPU miner that bypasses
  Python's GIL for true parallel hashing (~150+ MH/s on 4 cores vs
  ~0.4 MH/s with threads). `start-mining.bat` launches the full stack
  (node + stratum + CPU miner) in one click. Templates
  follow the chain's window strategy — difficulty is frozen inside
  each 60-block window and retargets exactly at window boundaries,
  so mid-window block cost is a known constant.
- **Sponsor No. 1 is unclaimed.** The first paying sponsor takes a
  permanent, one-of-one seat at the head of the ledger: `FIRST.md`.
- **Sponsored heights are open.** Pick a future block height, pay
  BTC with a self-describing OP_RETURN order, and the live payment
  watcher registers it after one confirmation. When the chain
  reaches that height, its coinbase pays your lock and seals your
  tag automatically. Terms and exact payment format: `SPONSOR.md`;
  the upcoming ~600-block GPU flood inventory: `FLOOD.md`.
- **Verify it in seconds.** `genealogy_verify.py` is a stdlib-only
  reference verifier: it walks the chain from the Bitcoin anchor and
  checks every header, every AuxPoW attachment, and every difficulty
  transition (24,400 self-PoW + 1,431 AuxPoW blocks, including 599
  accepted under the consensus grace rule, replicated exactly).
  Full run: under 10 seconds. Its DAA replication predicted the
  live window-boundary retarget at height 25,680 to the bit — and
  the first stratum-mined block followed at 25,681, ground through
  `stratum_fork.py` by an independent miner implementation and
  accepted by the node. Latest verified checkpoint: height 25,831
  (`genealogy_checkpoint.json`).

## The numbers that matter

- Fork-native proof-of-work since the anchor: ~1.04 × 10¹² hashes.
- A single 6-GPU rig (~90 GH/s) re-bases that in about 90 minutes:
  the catch-up simulation (`grace_miner.py`) shows ~628 blocks and
  ~5 × 10¹⁴ of new fork-native work before difficulty equilibrates
  at the 60-second spacing — a ~500× multiplication of the chain's
  security basis in one afternoon.

## Run it

First, set the workspace directory (where `chain.jsonl` lives):

**Linux / macOS:**
```
export EXCAL_WORKSPACE=/path/to/your/workspace
```

**Windows (PowerShell):**
```
$env:EXCAL_WORKSPACE="C:\path\to\your\workspace"
```

**Windows (Command Prompt):**
```
set EXCAL_WORKSPACE=C:\path\to\your\workspace
```

The `chain.jsonl` file contains the fork chain data and is required by
`genealogy_verify.py` and other scripts. It is gitignored because it is
large (~several MB). If you do not have it, run the fork node first to
generate it, or obtain it from the project maintainer.

```
python3 genealogy_verify.py     # check the whole chain from the anchor
python3 window_planner.py       # current window: frozen bits, blocks
                                # left, exact expected cost per block
python3 grace_miner.py          # strategy validation + flood simulation
```

To start the stratum shim for GPU miners:

**Linux / macOS:**
```
STRATUM_HOST=0.0.0.0 python3 stratum_fork.py
```

**Windows (PowerShell):**
```
$env:STRATUM_HOST="0.0.0.0"; python3 stratum_fork.py
```

**Windows (Command Prompt):**
```
set STRATUM_HOST=0.0.0.0
python3 stratum_fork.py
```

### Windows mining

On Windows, start the full mining stack with one click:

```
start-mining.bat
```

This launches the fork node (RPC :9432), the stratum shim (:9434), and a
multiprocessing CPU miner (`cpu_miner_mp.py`) that runs non-stop with
auto-reconnect. It uses separate processes (not threads) to bypass
Python's GIL, achieving ~150+ MH/s on 4 cores — a 69× speedup over
the threaded version. For even more hashrate, point a standard SHA-256d
GPU stratum miner at `127.0.0.1:9434`.

Environment variables for the CPU miner:

```
MINER_THREADS=4    python cpu_miner_mp.py   # number of worker processes
MINER_WORKER=cpu-0 python cpu_miner_mp.py   # worker name
```

A threaded fallback (`cpu_miner.py`) is also available but is much slower
(~0.4 MH/s) due to Python's GIL.

## Honest scope

EXCAL has no market and no price; this repo claims neither. Trifold's
security is hash-only — the novelty is the arrangement (ternary Merkle
tree, pattern-fold key schedule), not a new hardness assumption, and it
is unreviewed. The bridge design in `genealogy-bridge-spec.md` is a
specification with a working reference verifier, not a deployed bridge.
What is claimed is exactly what the verifier checks.

## Powder lots — crowdfund the finale

The Dr. Time broadcast trilogy (AETHER/v2, the 1A1z tribute, the QDAY
countersignature) is armed and waiting on funding. Buy a powder lot
from ~1,200 sats: your own UTXO fires the act you choose, on autopilot,
with a public proof chain. See [POWDER.md](POWDER.md).

## Phase Omega — the chain countersigns itself (live from height 25,901)

Every block's coinbase now carries a Trifold (hash-only, post-quantum)
signature over its parent's header: block N countersigns block N−1,
under published epoch roots. Verify the top of the chain yourself with
`omega_verify.py`. Design, roots, and honest costs: [OMEGA.md](OMEGA.md).

## SphinxOS Nexus — Grand Unified Quantum Blockchain Organism

The `sphinx_os/` package implements the Nexus Orchestrator, fusing five
subsystems into one self-organizing organism:

- **Quantum-Spacetime Fabric** — Quantum state simulator with density
  matrix tracking, von Neumann entanglement entropy, and spacetime
  curvature evolution.
- **Conscious Consensus Engine** — Block consensus driven by Integrated
  Information Theory (IIT v8) φ-scores with validator registration,
  block proposals, and supermajority finalization.
- **Holographic P2P Layer** — Peer-to-peer networking with entanglement-based
  routing, gossip protocol, message encryption, priority queues with TTL,
  peer discovery, and bandwidth/latency simulation.
- **Self-Organizing Treasury** — Autonomous treasury with NFT-based
  governance, type-aware fee splitting, compound yield, and auto-deployment.
- **Nexus Orchestrator** — Unified stepping with cross-layer entropy,
  feedback loops, and phase transitions (Vacuum → Inflation → Condensation
  → Crystallization → Consciousness).

Run the demo:
```
python demo_nexus.py
```

## zkSync Era Integration — URUU Token with Custom Bonding Curve

The EXCAL ecosystem now bridges to [zkSync Era](https://era.zksync.io),
Ethereum's leading Layer 2 scaling solution, via the **URUU token** and a
custom **sigmoid bonding curve**.

**URUU Token:**
- **Max supply:** 1,000,000 URUU
- **Price curve:** Sigmoid (S-shape) — slow early growth, accelerated
  middle phase, stabilization near ceiling
- **Price range:** 0.01–10.0 EXCAL per URUU
- **Trading fee:** 0.3%
- **Reserve currency:** EXCAL

**Bonding Curve:** The curve uses a mathematical sigmoid function where
price is determined by supply. Quantum entanglement entropy from the
Nexus fabric influences curve steepness, and conscious consensus φ scores
shift the inflection point — making it a truly quantum-influenced pricing
mechanism.

**zkSync Era Bridge:**
- **Bridge fee:** 0.1%
- **Mechanism:** Lock-and-mint with SHA-256 cryptographic proofs
- **Tokens:** EXCAL, URUU, wEXCAL
- **Confirmations:** 12 blocks

See [TOKENOMICS.md](TOKENOMICS.md) for full details on the bonding curve
mathematics and bridge flow.

## EREPR — Entanglement-Resonance Echo Peer Routing (Q-Day Protocol)

**Welcome to Q-Day!** EREPR is a novel P2P discovery and gossip protocol
that replaces traditional flooding/DHT with quantum-inspired resonance matching.

How it works:
1. **Resonance Signatures** — Each node generates a unique signature mapped
   to a point on a toroidal manifold (T²)
2. **Echo Broadcast** — Nodes periodically broadcast their signature as an
   "echo" packet with HMAC challenge
3. **Resonance Matching** — Receiving nodes compute a resonance score based
   on toroidal distance, frequency alignment, and phase coherence
4. **Entanglement Bonds** — If resonance exceeds threshold, nodes form a
   bidirectional bond with a shared secret (echo → match → confirm handshake)
5. **Gossip Wave Propagation** — Messages propagate through bonds with
   amplitude decay — stronger bonds carry messages further
6. **Natural Churn Resistance** — Bonds decay without heartbeats; nodes
   must re-echo to maintain connections

Why it's novel:
- No DHT, no flooding, no bootstrap servers
- Nodes self-organize like tuning forks finding each other
- Toroidal manifold ensures uniform distribution — no hotspots
- Wave propagation naturally limits gossip depth — no infinite loops
- Entanglement bonds provide implicit authentication

```python
from sphinx_os.nexus import EREPRProtocol, EchoMessage, GossipWave

# Initialize a node
node = EREPRProtocol("my_node", b"secret")
node.initialize()

# Receive an echo and form a bond
echo = EchoMessage.from_json(received_data)
bond = node.receive_echo(echo)

# Send gossip through entanglement bonds
wave = node.create_gossip_wave({"type": "tx", "data": "..."})
targets = node.forward_wave(wave)
```

See [`sphinx_os/nexus/erepr_protocol.py`](sphinx_os/nexus/erepr_protocol.py)
for the full implementation.


## AetherionEXCAL — Unified Installer (Single Executable)

`AetherionEXCAL.exe` is the **single unified installer** that installs
everything on your device and starts the full system:

**What it does on launch:**
1. **Starts the fork node** — RPC server on port 9432 (background)
2. **Opens the wallet GUI** — Aetherion-themed with onboarding wizard
3. **Initializes EREPR P2P** — Nodes discover each other via resonance
4. **Ready to mine** — CPU mining + GPU stratum server integrated

**Features:**
- **Aetherion-themed UI** — Deep space aesthetics with electric purple/cyan
  gradients, glassmorphism cards, and animated particle backgrounds
- **Encrypted key storage** — Private keys encrypted at rest using AES-256-GCM
  with scrypt key derivation (NIST SP 800-132 compliant) — no plaintext keys
- **Multi-wallet profiles** — Each user/peer creates their own wallet profile
- **Address validation** — 20-char uppercase hex format enforced before sending
- **Node management** — Start/stop fork node from Settings tab
- **Node status** — Real-time node health indicator in sidebar
- **EREPR P2P** — Quantum-inspired peer discovery and gossip
- **CPU mining** — Multi-threaded SHA-256d mining
- **GPU stratum** — Integrated stratum server for GPU miners
- **User onboarding** — Guided 5-step tour for new users
- **Help system** — Context-sensitive help with quick tips
- **Prometheus monitoring** — Real-time metrics at `http://127.0.0.1:9435/metrics`

**Run the unified installer:**
```
AetherionEXCAL.exe          # GUI mode (default)
AetherionEXCAL.exe generate # CLI mode
AetherionEXCAL.exe balance
AetherionEXCAL.exe help
```

**Build (Windows):**
```
pyinstaller AetherionEXCAL.spec
```

**Build (Mac):**
```
./build_aetherion.sh
```

Compiled executables:
- `dist/AetherionEXCAL.exe` (Windows, 33.9 MB) — **Unified installer** (node + wallet + mining + EREPR)
- `dist/AetherionEXCAL-StratumMiner.exe` (Windows, 9.6 MB) — Standalone Stratum miner

**Website:** https://www.aetherion-oracle.com

## Holo-wallet — CLI P2P Wallet for SphinxOS Nexus

`holo_wallet.py` is a full CLI wallet integrated with the Holographic P2P
layer. It supports key generation (SHA-256 addresses), hash-only transaction
signing, balance tracking, encrypted messaging, gossip broadcast, peer
listing, and network topology export.

```
python holo_wallet.py generate      # Generate a new key pair
python holo_wallet.py balance       # Show wallet balance
python holo_wallet.py send --to ABC123 --amount 10.5
python holo_wallet.py peers         # List connected peers
python holo_wallet.py topology --format json   # Export network topology
python holo_wallet.py encrypt --to peer_0 --message "secret"
python holo_wallet.py gossip --message "hello network"
python holo_wallet.py status        # Full wallet and network status
```

A compiled Windows executable is available at `dist/Holo-wallet.exe`.
Build it with: `pyinstaller --onefile --name Holo-wallet holo_wallet.py`

## Self-serve — Bitcoin fork claim tools

The `self-serve/` directory contains tools for claiming and delivering
seeds on the Bitcoin fork:

- `claim_btc.py` — Claim BTC from fork UTXOs
- `deliver_seed.py` — Deliver encrypted claim seeds
- `decrypt_seed.py` — Decrypt received claim seeds
- `taker_claim.py` — Taker-side claim workflow
- `taker_htlc.py` — HTLC-based taker transactions

The `self-serve/vendor/` directory contains shared utility modules
(btc_htlc, secp256k1, txscript, etc.), and `self-serve/tests/` contains
security tests for the deliver_seed module.

## Governance — Knights of the Round Table

EXCAL governance is controlled by the **Knights of the Round Table**,
a sovereign council elected by 3-of-5 threshold voting. Each Knight
holds a MuSig2 (BIP-327) key share; the aggregate key controls the
Taproot treasury derived from the 13-word prophecy code.

**MuSig2 (BIP-327) threshold signing:**
- **Key aggregation:** Q = Σ a_i · P_i with BIP-327 scaling factors
- **Additive inverse handling:** When Q has an odd y-coordinate, the
  x-only representation recovers −Q (same x, y becomes p − y). The
  signer applies g_v = −1 mod N to their secret key so the signature
  verifies against the even-y recovered point — production-ready per
  BIP-327 specification.
- **FROST DKG:** Distributed key generation with Feldman VSS
- **AI Oracle Knights:** 5 specialization types (Sentinel, Treasurer,
  Oracle, Bridge, Curve) with risk-based proposal analysis
- **Knight NFTs:** 13 NFTs (12 Mythical + 1 Legendary King) with
  ZK rarity proofs

See [GOVERNANCE.md](GOVERNANCE.md) for the full election process,
proposal types, and decentralization guarantees.

## Production Deployment

**AetherionEXCAL is production-ready and deployed.**

- **Test suite:** 439 tests, all passing (MuSig2, FROST, AI Oracle Knights, Knight NFTs, Knights of the Round Table, bonding curve, zkSync bridge, SphinxOS Nexus core, Stratum miner)
- **Executables:** Windows and Mac builds available in `dist/`
- **GitHub Pages:** Live documentation at https://excalibur-chain.github.io/excalibur-chain/
- **Coinbase Rosetta:** API configuration files ready for exchange integration

**Quick start for live P2P deployment:**
```
# Run the GUI wallet (production)
python excal_wallet.py

# Or run the CLI wallet
python holo_wallet.py generate
python holo_wallet.py status

# Run the Nexus demo
python demo_nexus.py

# Start mining
start-mining.bat

# Run the external Stratum miner
python stratum_miner.py server --host 0.0.0.0 --port 3333
python stratum_miner.py cpu --threads 4
python stratum_miner.py benchmark --threads 4 --duration 10
```

## Documentation

Full documentation is available at the [GitHub Pages site](https://excalibur-chain.github.io/excalibur-chain/):

- [SphinxOS Nexus](docs/sphinx_os.md) — Quantum blockchain operating system
- [Holo-wallet](docs/holo_wallet.md) — CLI P2P wallet guide
- [Tokenomics](docs/TOKENOMICS.md) — Supply, lock types, and economics
- [Governance](docs/GOVERNANCE.md) — Knights of the Round Table, MuSig2, AI Oracles, NFTs
- [Phase Omega](docs/OMEGA.md) — Block countersigning details
- [Sponsorship](docs/SPONSOR.md) — Block sponsorship terms
- [Powder Lots](docs/POWDER.md) — Crowdfunded Bitcoin broadcasts
- [Audit Report](docs/AUDIT.md) — Security audit and test coverage

## Summary

AetherionEXCAL unifies:
1. **Bitcoin fork** with post-quantum Trifold locks and live proof-of-work
2. **SphinxOS Nexus** — Quantum blockchain organism with 8 integrated subsystems (+ EREPR)
3. **EREPR P2P** — Entanglement-Resonance Echo Peer Routing (Q-Day protocol)
4. **Knights of the Round Table** — Sovereign governance with MuSig2 (BIP-327) threshold signing
5. **AI Oracle Knights** — 5 specialization types with risk-based proposal analysis
6. **Knight NFTs** — 13 NFTs (12 Mythical + 1 Legendary King) with ZK rarity proofs
7. **Unified Installer** — Single executable: node + wallet + mining + EREPR
8. **zkSync Era bridge** — Cross-chain URUU token with custom sigmoid bonding curve
9. **FROST DKG** — Distributed key generation for production multi-party signing

**EXCAL is the new Qrevolution.** Visit [www.aetherion-oracle.com](https://www.aetherion-oracle.com).
