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
import os
import sys

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
    "messerene_operator",
    "p2p",
]

def main():
    import PyInstaller.__main__

    bundle_binary = "--no-binary" not in sys.argv
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
