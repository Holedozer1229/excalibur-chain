"""excalibur_wallet — the Excalibur fork wallet.

A P2P ledger wallet with full functions, powered by Aetherion QAI
(light-ledger checkpoint attestations) and URUU (read-only zkSync Era
view), with a Frostgate 3-of-5 FROST threshold vault as a custody
option alongside the single-key wallet.

Layout:
  bip39.py       BIP39 mnemonics (12/24 words) + seed derivation
  keys.py        deterministic key/address derivation from the seed
  wallet.py      encrypted wallet file (AES-256-CTR + HMAC, wallet_crypto)
  ledger.py      balance / UTXOs / history — RPC-first, local-chain fallback
  txbuild.py     send: build + sign EVERY input + verify locally, no broadcast
  locks.py       lock constructors for every live lock type (KNOT refused)
  checkpoints.py QAI-audited Trifold checkpoint attestation verification
  p2p_sync.py    header-first sync from a live P2P peer (seeds bootstrap)
  uruu.py        read-only URUU view via public zkSync Era RPC
  sss.py         Shamir's Secret Sharing seed backup (k-of-n)
  frostgate.py   Frostgate 3-of-5 FROST vault via the real Rust operator CLI
  cli.py         the unified `excalibur` command line

Rules the whole package lives by (Lux's standing orders):
  * Real-deal-only: no demos, no simulated data, no fake balances.
  * Full spend-and-sign, always: build the full tx, sign EVERY input,
    verify every signature locally BEFORE anything is submitted — and
    this wallet never broadcasts. There is no broadcast command.
  * Seeds, private keys and passphrases are never printed or logged.
  * KNOT (0x06) is staged, not activated: the wallet refuses to create
    KNOT outputs for the live fork. Test-chain KNOT builds are labelled
    as such and are not broadcastable.
  * Pure stdlib, Windows-compatible: no fork(), no bare fcntl, no
    Unix-only paths. The live fork modules are reused, never reinvented.
"""
__version__ = "0.1.0"
