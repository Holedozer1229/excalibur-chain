# EXCAL community full-node operation

This is a permissionless community node launcher for the existing `fork`
network. It does not alter consensus, genesis, wallet signing, or issuance.

## Start a validating P2P node

From a checkout of this repository:

```bash
chmod +x scripts/excal-community-node.sh
scripts/excal-community-node.sh --peer YOUR_BOOTSTRAP_HOST:9433
```

The launcher selects the EXCAL fork network, listens for inbound P2P on
TCP 9433, keeps JSON-RPC on 127.0.0.1:9432, and disables local mining.
Replace the bootstrap placeholder with a peer address published by an EXCAL
operator; this repository currently does not contain a verified public seed.

To run a miner instead, start `excalibur.py` directly with
`--network fork --p2p-host 0.0.0.0`. Configure a wallet and protect its
keyfile before mining. A public node does not need to mine to validate and
relay the chain.

## Firewall

- Allow inbound TCP 9433 for P2P.
- Do not expose TCP 9432. The current JSON-RPC handler has no authentication.
- Keep wallet files, passphrases, and RPC access local to the operator.

## P2P defaults

When `--p2p-host` is omitted, the `fork` network now binds to
`0.0.0.0`. The legacy `mainnet` and `testnet` profiles remain loopback by
default. An explicit `--p2p-host` override always wins.

## What this does not establish

A listening socket is not a healthy public network. An operator must still
confirm inbound reachability, successful peer handshakes, block synchronization,
and agreement on the same best-chain hash with independent peers.

The tracked `chain.jsonl.height` file is a repository marker, not a live RPC
observation. Its current recorded height is 44,629; it does not prove a live
tip or peer count.

The Bitcoin inheritance snapshot is not present in the public repository.
The strict v2 importer work is still draft and requires a producer, two
independent snapshot reconstructions from Bitcoin Core at block 968,698,
consensus-pinned activation parameters, and original Bitcoin spend-condition
compatibility before inherited balances can be activated.

## Mainnet readiness gates

1. Reproducibly rebuild and verify the Bitcoin UTXO snapshot at the exact
   anchor block, including coinbase origin metadata and unspendable outputs.
2. Preserve original Bitcoin authorization conditions for every inherited
   script class or define a separately reviewed safe migration. Do not replace
   unsupported scripts with OPEN or administrator-controlled locks.
3. Pin snapshot commitment and activation height in versioned fork consensus
   parameters; all nodes must validate the same values.
4. Resolve the local-clock deep-reorg exception. Consensus acceptance must not
   depend on each node's wall clock or downtime.
5. Differential-test transaction, script, AuxPoW, difficulty, activation, and
   reorganization behavior against independent reference vectors.
6. Run at least three independently operated nodes through sync, competing
   branches, restart, and reorg tests.
7. Publish the genesis/consensus parameter manifest, release binaries, and
   reproducible node setup instructions.

Do not call EXCAL a Bitcoin-balance-preserving fork or activate inherited
balances until gates 1-3 pass. Do not call the public network operational
until gates 4-6 and real multi-operator connectivity are demonstrated.
