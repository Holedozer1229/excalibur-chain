"""Offline PCBE v1 verifier CLI.

Reads an evidence bundle (see pcbe/bundle.py), verifies it with the
reference verifier and prints the verification report as JSON. Works
fully offline from the bundle and its pinned trust snapshot; it never
touches the network, EXCAL consensus, wallets or payment authorization.

Usage:
    python3 -m pcbe.cli verify --bundle bundle.json [--now 1800000000]
    python3 -m pcbe.cli example --out bundle.json [--now 1800000000]

Exit codes: 0 = VALID, 1 = any other outcome, 2 = usage or bundle error.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .bundle import BUNDLE_FORMAT, bundle_from_json, bundle_to_json
from .core import PCBEError, ReplayRegistry, verify_event


def _cmd_verify(args: argparse.Namespace) -> int:
    try:
        text = Path(args.bundle).read_text(encoding="utf-8")
    except OSError as exc:
        print(f"pcbe: cannot read bundle: {exc}", file=sys.stderr)
        return 2
    try:
        bundle = bundle_from_json(text)
    except PCBEError as exc:
        print(f"pcbe: invalid bundle: {exc}", file=sys.stderr)
        return 2
    replay = ReplayRegistry()
    for genesis, nonce in bundle.get("replay_seen", []):
        replay.record(genesis, nonce)
    report = verify_event(
        bundle["event"], bundle["policy"], bundle["trust"],
        replay=replay,
        now=args.now,
        dispute_open=bundle.get("dispute_open", False),
        revocation_updated_at=bundle.get("revocation_updated_at"),
    )
    print(json.dumps(report, sort_keys=True, indent=2))
    return 0 if report["outcome"] == "VALID" else 1


def _cmd_example(args: argparse.Namespace) -> int:
    try:
        from .example import build_example
    except ImportError as exc:
        print(f"pcbe: {exc}", file=sys.stderr)
        return 2
    try:
        bundle = build_example(args.now)
    except RuntimeError as exc:
        print(f"pcbe: {exc}", file=sys.stderr)
        return 2
    try:
        Path(args.out).write_text(bundle_to_json(bundle), encoding="utf-8")
    except OSError as exc:
        print(f"pcbe: cannot write bundle: {exc}", file=sys.stderr)
        return 2
    print(f"wrote example bundle ({BUNDLE_FORMAT}) to {args.out}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pcbe", description="Offline EXCAL PCBE v1 verifier.")
    sub = parser.add_subparsers(dest="command", required=True)
    verify = sub.add_parser("verify", help="verify an evidence bundle")
    verify.add_argument("--bundle", required=True, help="bundle JSON file")
    verify.add_argument("--now", type=int, default=None,
                        help="verification time as Unix seconds (default: wall clock)")
    verify.set_defaults(func=_cmd_verify)
    example = sub.add_parser("example", help="write a deterministic example bundle")
    example.add_argument("--out", required=True, help="output bundle JSON file")
    example.add_argument("--now", type=int, default=1_800_000_000,
                         help="example event time as Unix seconds")
    example.set_defaults(func=_cmd_example)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
