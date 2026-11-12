"""frostgate.py — Frostgate 3-of-5 FROST threshold vault in the wallet.

The vault is the Aethergate federation (repo Holedozer1229/aethergate,
entry name Frostgate — the wallet uses Lux's name, "Frostgate", and
notes the repo name where it matters). The signing math is the real
Rust code: ZF frost crates (RFC 9591) via the aethergate-operator CLI
(dealerless DKG, threshold signing, Taproot key-path spends). This
module only shells out to that binary and parses its output — the
FROST math is never re-implemented in Python, and nothing here
simulates a signature.

What the wallet offers (testnet-only for now; no mainnet funds, no
real bridge execution):
  * frostgate init    — fresh dealerless DKG (5 operators, threshold 3)
  * frostgate address — the vault's P2TR address (testnet tb1p by default)
  * frostgate status  — group key, threshold, operators, address
  * frostgate sign    — threshold-sign a 32-byte message with any 3 of
                        the 5 operators; the CLI verifies the signature
                        under the group key before printing it
  * frostgate spend   — threshold-spend a funded vault UTXO (key-path,
                        Taproot); prints the signed tx hex, NEVER
                        broadcasts — the operator CLI has no broadcast
                        flag at all

Default vault: the Nov 1 testnet federation at
~/workspace/aethergate/ceremony (group key 03990e13…, regtest address
bcrt1pwssqg8qsphwfpeq3afuxfne6yg2pvrdpe4n6yy3af3lvgn8ksygqq2hhjr).
Its operator key files are 0600 and live only in that dir; the wallet
never reads them — the Rust process loads them for signing, and the
wallet never sees a share.

Honest limits (from the Nov 1 federation doc, which is the source of
truth): the vault controls NO existing address (not the EXCAL miner
key, not the Aether genesis key, not any BTC mainnet address). Its
signatures are BIP340 Taproot signatures for its own fresh FROST
group key. It cannot sign EXCAL fork PKH spends. The coordinator is
trusted for liveness; frost-secp256k1-tr was outside the NCC audit
scope of the FROST core. Local rehearsal keeps all 5 operator files
on one machine; production splits them across 5 operator machines
with the coordinator relay.
"""
import json
import os
import subprocess
import sys

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Frozen (PyInstaller one-file) builds extract to a temp dir, so the
# bundle-relative WORKSPACE is wrong for the vault ceremony dir. On a
# dev machine the real ceremony lives under ~/workspace — prefer that
# when it exists; otherwise stay bundle-relative.
if getattr(sys, "frozen", False):
    _home_ceremony = os.path.join(os.path.expanduser("~"), "workspace",
                                  "aethergate", "ceremony")
    if os.path.isdir(_home_ceremony):
        WORKSPACE = os.path.join(os.path.expanduser("~"), "workspace")
DEFAULT_VAULT_DIR = os.path.join(WORKSPACE, "aethergate", "ceremony")
AETHERGATE_DIR = os.path.join(WORKSPACE, "aethergate")
NOV1_GROUP_KEY = "03990e130e323ea483b5dcec366d46ad5315ede134fa126f06232e476d4f160410"


class FrostgateError(Exception):
    pass


def find_operator_cli():
    """Path to the built aethergate-operator binary, or None.

    Frozen (PyInstaller one-file) builds carry the binary inside the
    bundle (_MEIPASS) — check there first, then the workspace paths.
    """
    candidates = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(os.path.join(meipass, "aethergate-operator"))
    candidates += [
        os.path.join(AETHERGATE_DIR, "target", "release",
                     "aethergate-operator"),
        os.path.join(AETHERGATE_DIR, "target", "debug",
                     "aethergate-operator"),
        os.path.join(WORKSPACE, "aethergate-wf", "target", "release",
                     "aethergate-operator"),
        os.path.join(WORKSPACE, "aethergate-wf", "target", "debug",
                     "aethergate-operator"),
    ]
    for c in candidates:
        if os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    return None


def _run_cli(args, timeout=180):
    cli = find_operator_cli()
    if cli is None:
        raise FrostgateError(
            "Frostgate operator binary not built. Build it with:\n"
            "  cd ~/workspace/aethergate && cargo build --release "
            "-p aethergate-operator")
    try:
        proc = subprocess.run([cli] + args, capture_output=True,
                              timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise FrostgateError(f"could not run Frostgate CLI: {e}")
    out = proc.stdout.decode(errors="replace")
    err = proc.stderr.decode(errors="replace")
    if proc.returncode != 0:
        raise FrostgateError(
            f"Frostgate CLI failed (exit {proc.returncode}): "
            f"{(err or out).strip()[:500]}")
    return out


def _parse_group_key(output):
    for line in output.splitlines():
        if "Group verifying key:" in line:
            return line.split(":", 1)[1].strip()
    return None


def init_vault(vault_dir, operators=5, threshold=3):
    """Run a fresh dealerless DKG into `vault_dir`. Returns
    {group_key, vault_dir, operators, threshold}. Refuses to
    overwrite an existing ceremony (operator files are key material)."""
    if os.path.exists(os.path.join(vault_dir, "group.json")):
        raise FrostgateError(
            f"a ceremony already exists at {vault_dir} — refusing to "
            f"overwrite key material (use a new --dir for a new vault)")
    out = _run_cli(["dkg", "--operators", str(operators),
                    "--threshold", str(threshold), "--out", vault_dir])
    gk = _parse_group_key(out)
    if not gk:
        raise FrostgateError(f"DKG output did not include a group key: "
                             f"{out[:300]}")
    return {"group_key": gk, "vault_dir": vault_dir,
            "operators": operators, "threshold": threshold}


def vault_address(vault_dir=DEFAULT_VAULT_DIR, network="testnet"):
    """The vault's P2TR key-path address. network: testnet (default),
    regtest, mainnet. Mainnet is allowed only explicitly — and the
    wallet never funds or broadcasts from it."""
    if network not in ("testnet", "regtest", "mainnet"):
        raise FrostgateError("network must be testnet, regtest or mainnet")
    out = _run_cli(["federation-address", "--ceremony", vault_dir,
                    "--network", network])
    addr = out.strip().splitlines()[-1].strip()
    if not addr:
        raise FrostgateError("federation-address printed nothing")
    return addr


def vault_status(vault_dir=DEFAULT_VAULT_DIR):
    """Public vault facts from group.json + the testnet address."""
    group_path = os.path.join(vault_dir, "group.json")
    if not os.path.exists(group_path):
        raise FrostgateError(f"no ceremony at {vault_dir} "
                             f"(run `frostgate init` first)")
    with open(group_path) as f:
        g = json.load(f)
    try:
        addr = vault_address(vault_dir, "testnet")
    except FrostgateError:
        addr = None
    return {"vault_dir": vault_dir,
            "num_operators": g.get("num_operators"),
            "threshold": g.get("threshold"),
            "group_key": g.get("group_verifying_key_hex"),
            "address_testnet": addr,
            "is_nov1_federation": (
                g.get("group_verifying_key_hex") == NOV1_GROUP_KEY)}


def threshold_sign(vault_dir, message_hex, signers=(1, 2, 3)):
    """Threshold-sign a message with `signers` (default 1,2,3).
    message_hex: hex of the message (32 bytes is the norm — a Taproot
    sighash or a digest). Returns {"signature": hex64, "signers": [...],
    "verified": True}. The Rust CLI verifies under the group key
    before printing; a bad aggregate never reaches this return."""
    msg = str(message_hex).strip()
    if msg.lower().startswith("0x"):
        msg = msg[2:]
    try:
        raw = bytes.fromhex(msg)
    except ValueError:
        raise FrostgateError("message must be hex")
    if len(raw) != 32:
        raise FrostgateError(
            f"message must be 32 bytes (a sighash/digest); got {len(raw)}")
    signers_s = ",".join(str(int(s)) for s in signers)
    out = _run_cli(["sign-message", "--ceremony", vault_dir,
                    "--signers", signers_s, "--message", msg])
    sig = out.strip().splitlines()[-1].strip()
    if len(sig) != 128:
        raise FrostgateError(f"unexpected signature from CLI: {sig[:80]}")
    try:
        bytes.fromhex(sig)
    except ValueError:
        raise FrostgateError("CLI signature is not hex")
    return {"signature": sig, "signers": list(signers),
            "verified": True}


def threshold_spend(vault_dir, prev_txid, prev_vout, prev_value_sats,
                    dest_address, fee_sats=500, network="testnet",
                    signers=(1, 2, 3)):
    """Threshold-spend a funded vault UTXO (Taproot key-path).
    Returns {"raw_tx_hex": ...}. DRY-RUN ONLY by construction: the
    operator CLI prints the signed tx hex and has no broadcast flag;
    this wallet adds none. The caller reviews the hex; broadcasting
    is a separate, explicit user action outside this wallet."""
    signers_s = ",".join(str(int(s)) for s in signers)
    out = _run_cli(["taproot-spend", "--ceremony", vault_dir,
                    "--signers", signers_s,
                    "--prev-txid", prev_txid,
                    "--prev-vout", str(int(prev_vout)),
                    "--prev-value", str(int(prev_value_sats)),
                    "--dest", dest_address,
                    "--fee", str(int(fee_sats)),
                    "--network", network])
    raw = out.strip().splitlines()[-1].strip()
    if not raw:
        raise FrostgateError("taproot-spend printed no transaction")
    return {"raw_tx_hex": raw, "broadcast": False}
