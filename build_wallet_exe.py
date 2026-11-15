#!/usr/bin/env python3
"""Build the EXCAL wallet as a PyInstaller one-file executable.

Cross-platform: run on Linux for a Linux binary, on Windows for the
real .exe. PyInstaller CANNOT cross-compile — a Windows .exe must be
built on Windows (see build_exe.bat / README-WINDOWS-BUILD.md).

Usage:
    python3 build_wallet_exe.py [--no-binary]

--no-binary skips bundling the aethergate-operator binary (Frostgate
commands then need the binary on the machine, as before).

Output: excalibur-dist/excalibur (Linux/macOS) or excalibur.exe (Windows).
The build is pure stdlib + the workspace's own modules; no pip packages
beyond PyInstaller itself.
"""
import hashlib
import os
import sys
import tempfile

WS = os.path.dirname(os.path.abspath(__file__))
SEP = ";" if sys.platform == "win32" else ":"

HIDDEN_IMPORTS = [
    "lightledger",
    "txscript",
    "secp256k1",
    "genesis_fork",
    "txpq",
    "knot_math",
    "trifold_lockbox",
    "file_locks",
    "spent_leaf_registry",
    "messerene_operator",
    "p2p",
    # Lazily imported by excalibur_wallet/cli.py (2026-11-14 audit D4):
    "knot_wallet",
    "spent_leaf_registry",
    "wallet_crypto",
]

def _write_version_file():
    """Hash the wallet sources and write the hash to a temp file.

    The hash (same algorithm as excalibur_wallet.cli._source_hash) is
    bundled as excalibur_wallet/_build_version.txt so a frozen exe can
    report `excalibur --version` honestly. The file lives in /tmp, not
    in the source tree. Added 2026-11-14 (audit D6).
    """
    h = hashlib.sha256()
    pkg = os.path.join(WS, "excalibur_wallet")
    for name in sorted(os.listdir(pkg)):
        if name.endswith(".py"):
            with open(os.path.join(pkg, name), "rb") as f:
                h.update(f.read())
    digest = h.hexdigest()[:12]
    tmpdir = tempfile.mkdtemp(prefix="excalibur-version-")
    path = os.path.join(tmpdir, "_build_version.txt")
    with open(path, "w") as f:
        f.write(digest + "\n")
    print(f"source hash: {digest}")
    return path


def main():
    import PyInstaller.__main__

    bundle_binary = "--no-binary" not in sys.argv
    version_file = _write_version_file()
    args = [
        "--onefile",
        "--name", "excalibur",
        "--noconfirm",
        "--clean",
        "--paths", WS,
        "--distpath", os.path.join(WS, "excalibur-dist"),
        "--workpath", os.path.join(WS, "build-excalibur-exe"),
        "--specpath", os.path.join(WS, "build-excalibur-exe"),
    ]
    for mod in HIDDEN_IMPORTS:
        args += ["--hidden-import", mod]
    args += ["--add-data",
             os.path.join(WS, "excalibur_wallet", "bip39_english.txt")
             + SEP + "excalibur_wallet"]
    args += ["--add-data",
             version_file + SEP + "excalibur_wallet"]
    if bundle_binary:
        for cand in ("aethergate-operator", "aethergate-operator.exe"):
            p = os.path.join(WS, "aethergate", "target", "release", cand)
            if os.path.isfile(p):
                args += ["--add-binary", p + SEP + "."]
                print(f"bundling Frostgate operator binary: {p}")
                break
        else:
            print("NOTE: aethergate-operator binary not found — "
                  "Frostgate commands will need it on the machine.")
    args.append(os.path.join(WS, "excalibur_wallet", "__main__.py"))
    print("PyInstaller args:", " ".join(args))
    PyInstaller.__main__.run(args)

    out = os.path.join(WS, "excalibur-dist",
                       "excalibur.exe" if sys.platform == "win32"
                       else "excalibur")
    if os.path.isfile(out):
        print(f"\nBUILT: {out} ({os.path.getsize(out):,} bytes)")
    else:
        print("\nBUILD FAILED: no output binary", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
