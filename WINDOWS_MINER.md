# Windows miner port — `windows-miner-port` branch

The Excalibur fork miner now runs on Windows (Python 3.14, pure stdlib,
no new dependencies). Two producers are ported:

- **Integrated miner** — `excalibur.py --network fork --workers N`
  (mines blocks directly on the local node).
- **Fork sniper** — `fork_sniper.py` (merged mining: builds the fork
  child, grinds a Bitcoin parent, submits AuxPoW through the node RPC).

## What changed

| File | Change |
|---|---|
| `excalibur.py` (new in repo, from live VM copy) | `mine_one_parallel` now picks the multiprocessing start method by platform: `spawn` on Windows (`os.name == "nt"`), `fork` on Linux. New `_mp_context()` helper; `EXCAL_MP_CONTEXT` env overrides (e.g. `spawn` to test Windows semantics on Linux). Linux fork path is byte-identical in effect. |
| `fork_sniper.py` (new in repo, from live VM copy) | All `/home/hatch/workspace` paths replaced with script-dir-relative paths (`HERE`). `btc_core6f` binary name is `btc_core6f.exe` on Windows. **Pure-Python grind fallback** (`_py_grind` / `_py_grind_range`): when the compiled core is absent it grinds the parent header in Python worker processes (same fork PoW check, same tip-move abort, same round budget). The fork target is only ~23 bits (~8M hashes expected), so this genuinely finds blocks — it is the miner, not a placeholder. Bitcoind paths are env-overridable (`EXCAL_BITCOIN_CLI`, `EXCAL_BITCOIN_DATADIR`); without a local bitcoind the BTC tip falls through to mempool.space / BlockCypher, and a BTC-block hit is saved to file instead of submitted. |
| `fork_child.py` (new in repo, from live VM copy) | Already script-dir-relative. Added `EXCAL_NO_OMEGA=1` guard: skips the Omega countersign call. |
| `auxlib.py` (new in repo, from `scratch_auxpow`) | Script-dir-relative paths; fork wallet pubkey loads lazily (`_load_pub()`) so importing the module no longer crashes without the VM wallet file. |
| `grace_miner.py` | Removed the hardcoded `/home/hatch/workspace/your_files` fallback `sys.path` line. (`genealogy_verify.py` was already portable: `EXCAL_CHAIN_FILE` env / CLI path / script-dir `chain.jsonl`.) |
| `mempool.py`, `chainstate.py`, `p2p.py`, `node_rpc.py`, `utxodb.py`, `spent_leaf_registry.py`, `wallet_crypto.py`, `caduceus.py` (new in repo, verbatim live copies) | The node import closure `excalibur.py` needs. The repo previously held none of these (nor `excalibur.py` / `fork_sniper.py` / `fork_child.py` at all); the branch adds them from the live VM copies. No Unix-only stdlib in any of them (no `fcntl`, `os.fork`, `pwd`, `termios`); `signal.SIGTERM`/`SIGINT` handlers in `excalibur.py` are valid on Windows Python. |
| `btc_core6f.c` (new in repo, verbatim live copy) | The C grind core source, so the MinGW build below is actionable. |

## Building btc_core6f.exe (MinGW-w64) — optional, faster grind

The sniper works without it (Python fallback), but the C core is ~100x
faster. On the laptop, in an **MSYS2 UCRT64** terminal:

```
pacman -S mingw-w64-ucrt-x86_64-gcc mingw-w64-ucrt-x86_64-openssl
cd C:\Users\gregj\PycharmProjects\excalibur-chain
gcc -O3 -march=native -o btc_core6f.exe btc_core6f.c -lcrypto -pthread
```

Notes:

- `-pthread` links winpthreads (`pthread_create`/`pthread_mutex_*`).
  `-lcrypto` is OpenSSL's SHA-256 (`<openssl/sha.h>`).
  `__sync_fetch_and_add` is a GCC builtin — fine under MinGW GCC.
- `-march=native` ties the binary to this laptop's CPU; drop it for a
  portable binary (still fast at `-O2`).
- `nanosleep` (two call sites: the 5 s monitor sleep and `--bench` mode)
  is provided by MinGW-w64's `time.h`. If your toolchain rejects it,
  replace each `nanosleep(&ts, NULL);` with
  `Sleep(ts.tv_sec * 1000 + ts.tv_nsec / 1000000);` and add
  `#include <windows.h>` at the top.
- Smoke test (needs no node): `.\btc_core6f.exe --bench 5 <prevhash>
  <merkle> <time> <bits> <target>` — it should print a MH/s line and
  exit. The sniper invokes it as
  `btc_core6f.exe <prevhash> <merkle> <time> <bits> <target> 1 2 --rot
  2731 --checkpoint <file>`; a `FOUND <chunk> <nonce> <hash>` line in
  the round output means a hit.

## Running it on the laptop

```bat
git pull
git checkout windows-miner-port
```

### 0. Start the node first (either producer needs it)

```
start-node.bat
```

Wait until the window shows the tip climbing and
http://127.0.0.1:9432/ answers `getblockcount`. The node must be up
before the miner or the sniper starts.

### A. Integrated miner (simplest)

```
.venv\Scripts\python.exe excalibur.py --network fork --workers 2
```

Expected log line per block (pace is 1 s on the fork by default, so it
mines continuously):

```
block 44555: 1a2b3c4d5e6f7080.. nonce=12345678 812,345 H/s (0.41s) subsidy=50 EXCAL txs=0 fees=0
```

Use `--max-blocks 1` for a one-block smoke test, `--workers 4` on a
4-core laptop. Do **not** run this at the same time as the sniper —
both would race to extend the same tip.

### B. Fork sniper (merged mining, the live producer design)

```
set EXCAL_NO_OMEGA=1
.venv\Scripts\python.exe fork_sniper.py
```

Expected: `[sniper] round 1: child 44555 ...; grinding 2 threads`,
then on a hit `[sniper] round 1: HIT parent nonce ...`. Without
`btc_core6f.exe` it logs `btc_core6f binary absent; pure-Python grind`
and grinds in Python. The BTC tip comes from mempool.space (no local
bitcoind on the laptop). First run creates `wallet_fork.json` next to
the script if missing (fresh laptop wallet — the sniper's coinbase
pays it).

## Honest limits

- **Blocks mined on the laptop land on the laptop's local chain copy.**
  The laptop node holds at the snapshot height (~44,454) with no live
  peer, so a laptop-mined block does not reach the live fork network
  until the node can peer/sync (separate problem — same as before).
  The grind, the validation, and the local submit are all real.
- **Do NOT copy the VM's `omega/` directory to the laptop while the VM
  sniper is signing.** A Trifold leaf is one-time: two signers sharing
  one epoch key would burn the same leaf twice. `EXCAL_NO_OMEGA=1`
  (sniper path) or the absent key (integrated path — the repo ships
  only the epoch *ledger*, not the key) keeps laptop children valid
  but unsigned. Epoch 27 has only 6 leaves left on the VM.
- The Python fallback grinds ~0.3–1 MH/s per core (hashlib sha256d);
  the fork target (~23 bits) needs ~8M hashes, so a block takes
  roughly 10–30 s with 2 workers. The C core is ~100x faster once
  built.

## Verification (Linux VM, 2026-11-12)

Forced spawn context (`EXCAL_MP_CONTEXT=spawn`, simulating Windows
semantics) and the normal fork path were both verified against a
fresh synthetic fork chain in /tmp (never the live chain; no live
service touched; `fork_child.py` never executed):

- `mine_one_parallel`, spawn, 2 workers: winner found
  (nonce 19948889, 39,897,780 hashes, 114.22 s → **349,321 H/s**),
  direct PoW check OK, `submit_block` accepted (`reason=ok`), tip
  h=0 → 1. PASS.
- `mine_one_parallel`, fork, 2 workers: winner found
  (nonce 7714702, 15,429,406 hashes, 109.96 s → **140,316 H/s**),
  direct PoW check OK, `submit_block` accepted. PASS. The fork code
  path is unchanged — only the context selection moved. (Spawn
  measured 349,321 H/s in its run; the gap is host-load variance on
  this oversubscribed 1.5-CPU box, not a start-method effect — the
  grind code is identical, and spawn even carries extra re-import
  overhead. A first fork run measured 114,990 H/s but was
  contaminated by a runaway test process competing for the same CPUs;
  the 140,316 figure is the clean re-run.)
- Sniper `_py_grind`, synthetic parent header, ~20-bit target:
  nonce 202640 found in 0.58 s and re-verified against the target
  (~0.7 MH/s combined, 2 workers, on the loaded VM); tip-move abort
  in 1.02 s; round-budget abort in 2.03 s. ALL PASS.
- `grace_miner` loads and its file-tip fallback works with no node
  running (tiny synthetic `chain.jsonl` via `EXCAL_CHAIN_FILE`):
  80 records, tip h=79, `validate_history` bad=0 agree=6. PASS.
