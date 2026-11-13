# EXCAL wallet — Windows .exe build

The wallet is a unified `excalibur` CLI (BIP39 wallet, ledger, QAI
checkpoints, URUU view, Frostgate 3-of-5 vault). It is pure Python
stdlib — no pip packages needed to *run* it — but a one-file `.exe`
needs PyInstaller, and **PyInstaller cannot cross-compile**: a Windows
`.exe` must be built on Windows. The Linux binary in `excalibur-dist/`
does not run on Windows.

## Build it (on the laptop, one double-click)

1. In the repo folder (`C:\Users\gregj\PycharmProjects\excalibur-chain\`)
   make sure these are present:
   - `excalibur_wallet/` (the wallet package)
   - `lightledger.py`, `txscript.py`, `secp256k1.py`, `genesis_fork.py`,
     `txpq.py`, `knot_math.py`, `trifold_lockbox.py`,
     `messerene_operator.py`, `p2p.py` (top-level node modules — the
     wallet imports them; the build script bundles them in)
   - `build_wallet_exe.py` and `build_exe.bat`
   - the chain snapshot is NOT needed for the build (only to run a
     local node later)
2. Double-click `build_exe.bat`. It installs PyInstaller (once) and
   builds `excalibur-dist\excalibur.exe`.
3. Run it: `excalibur-dist\excalibur.exe --help`

## What is bundled in the .exe

- The whole `excalibur_wallet` package + the top-level node modules
  above + the BIP39 English wordlist.
- The `aethergate-operator` Rust binary, when it was built on the
  build machine (`aethergate/target/release/`). If it is missing at
  build time, Frostgate commands fail with a clear "not built" error
  instead of crashing — build it with
  `cargo build --release -p aethergate-operator` and rebuild the .exe.
- The Frostgate vault ceremony dir is NOT bundled. `frostgate status`
  and friends look for it under `aethergate/ceremony` next to the
  workspace, or take an explicit `--dir`.

## Known limits

- Send builds, signs and verifies locally only — there is NO broadcast
  path in the wallet by design. Nothing moves funds from the .exe.
- The URUU anchor contract is not deployed yet, so checkpoints verify
  as *attested but pending* until their fraud window passes; bootstrap
  from a checkpoint correctly refuses until it is final.
- Frostgate is testnet-only. The Nov 1 doc's printed testnet address
  is wrong — use the address the live binary derives
  (`tb1pwssqg8qsphwfpeq3afuxfne6yg2pvrdpe4n6yy3af3lvgn8ksygqdna38e`).
- The wallet reads the live fork node on RPC 9432 when it is up, and
  falls back to the local `chain.jsonl` file. On first run on the
  laptop, start the node first (`start-node.bat`) and wait for the tip
  to climb, or the ledger commands read the chain file only.

## Linux build (VM)

Same script, from the workspace root:

    ~/workspace/venvs/pyinstaller/bin/python build_wallet_exe.py

Output: `excalibur-dist/excalibur`. Verified: `--help`, `checkpoint
verify`, `ledger tip`, `frostgate address` all run from the frozen
binary.
