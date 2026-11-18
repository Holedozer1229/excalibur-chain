#!/usr/bin/env python3
"""Test that load_registry() validates sponsor locks and rejects malformed entries.

Covers stratum_fork.py weakness #7: the sponsor registry is loaded from JSON
without validation.  A malformed sponsors file could cause the stratum server
to produce invalid coinbases.
"""
import json
import os
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

import stratum_fork
from stratum_fork import load_registry, log


def _write_sponsors(path, data):
    """Write a sponsors.json file and return the path."""
    with open(path, "w") as f:
        json.dump(data, f)
    return path


def test_valid_pkh_lock():
    """A valid 42-char PKH lock hex should be accepted."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        # Valid PKH lock: 0x00 prefix + 20 bytes (42 hex chars)
        lock_hex = "00" + "a" * 40
        path = f.name
        data = {"100": {"lock": lock_hex, "tag": "test"}}
        json.dump(data, f)

    old_file = stratum_fork.SPONSORS_FILE
    try:
        stratum_fork.SPONSORS_FILE = path
        reg = load_registry()
        assert 100 in reg, "Valid PKH lock should be accepted"
        assert reg[100][0] == bytes.fromhex(lock_hex)
        print("PASS: valid PKH lock accepted")
    finally:
        stratum_fork.SPONSORS_FILE = old_file
        os.unlink(path)


def test_valid_hash160_lock():
    """A valid 40-char hash160 (no 0x00 prefix) should be accepted (lock_pkh wraps it)."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        # 40 hex chars = 20 bytes (hash160); lock_pkh adds the 0x00 prefix
        hash160_hex = "b" * 40
        path = f.name
        data = {"200": {"lock": hash160_hex, "tag": "sponsor"}}
        json.dump(data, f)

    old_file = stratum_fork.SPONSORS_FILE
    try:
        stratum_fork.SPONSORS_FILE = path
        reg = load_registry()
        assert 200 in reg, "Valid hash160 lock should be accepted"
        # lock_pkh adds 0x00 prefix
        expected = bytes.fromhex("00" + hash160_hex)
        assert reg[200][0] == expected
        print("PASS: valid hash160 lock accepted")
    finally:
        stratum_fork.SPONSORS_FILE = old_file
        os.unlink(path)


def test_invalid_lock_length():
    """A lock with invalid length (not a valid scriptPubKey) should be rejected."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        # 42 hex chars but first byte is 0xFF (not a valid lock type)
        lock_hex = "ff" + "a" * 40
        path = f.name
        data = {"300": {"lock": lock_hex, "tag": "bad"}}
        json.dump(data, f)

    old_file = stratum_fork.SPONSORS_FILE
    try:
        stratum_fork.SPONSORS_FILE = path
        reg = load_registry()
        assert 300 not in reg, "Invalid lock type should be rejected"
        print("PASS: invalid lock length rejected")
    finally:
        stratum_fork.SPONSORS_FILE = old_file
        os.unlink(path)


def test_malformed_hex():
    """A lock with non-hex characters should be rejected."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        path = f.name
        data = {"400": {"lock": "not_hex_data", "tag": "bad"}}
        json.dump(data, f)

    old_file = stratum_fork.SPONSORS_FILE
    try:
        stratum_fork.SPONSORS_FILE = path
        reg = load_registry()
        assert 400 not in reg, "Malformed hex should be rejected"
        print("PASS: malformed hex rejected")
    finally:
        stratum_fork.SPONSORS_FILE = old_file
        os.unlink(path)


def test_missing_lock_field():
    """An entry missing the 'lock' field should not crash the loader."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        path = f.name
        data = {"500": {"tag": "no_lock"}}
        json.dump(data, f)

    old_file = stratum_fork.SPONSORS_FILE
    try:
        stratum_fork.SPONSORS_FILE = path
        reg = load_registry()
        # Should either skip the entry or return empty dict on error
        assert 500 not in reg, "Missing lock field should be rejected"
        print("PASS: missing lock field handled")
    finally:
        stratum_fork.SPONSORS_FILE = old_file
        os.unlink(path)


def test_valid_pqh_lock():
    """A valid PQH lock (0x02 prefix + 20 bytes) should be accepted."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        # PQH lock: 0x02 prefix + 20 bytes (42 hex chars)
        lock_hex = "02" + "c" * 40
        path = f.name
        data = {"600": {"lock": lock_hex, "tag": "pqh"}}
        json.dump(data, f)

    old_file = stratum_fork.SPONSORS_FILE
    try:
        stratum_fork.SPONSORS_FILE = path
        reg = load_registry()
        assert 600 in reg, "Valid PQH lock should be accepted"
        print("PASS: valid PQH lock accepted")
    finally:
        stratum_fork.SPONSORS_FILE = old_file
        os.unlink(path)


def test_mixed_valid_invalid():
    """A file with both valid and invalid entries should accept only the valid ones."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        path = f.name
        data = {
            "700": {"lock": "00" + "a" * 40, "tag": "valid"},       # valid PKH
            "701": {"lock": "ff" + "a" * 40, "tag": "invalid"},     # invalid type
            "702": {"lock": "02" + "b" * 40, "tag": "valid_pqh"},   # valid PQH
        }
        json.dump(data, f)

    old_file = stratum_fork.SPONSORS_FILE
    try:
        stratum_fork.SPONSORS_FILE = path
        reg = load_registry()
        assert 700 in reg, "Valid PKH should be accepted"
        assert 701 not in reg, "Invalid lock type should be rejected"
        assert 702 in reg, "Valid PQH should be accepted"
        print("PASS: mixed valid/invalid entries handled correctly")
    finally:
        stratum_fork.SPONSORS_FILE = old_file
        os.unlink(path)


def test_missing_file():
    """A missing sponsors file should return an empty dict, not crash."""
    old_file = stratum_fork.SPONSORS_FILE
    try:
        stratum_fork.SPONSORS_FILE = "/nonexistent/path/sponsors.json"
        reg = load_registry()
        assert reg == {}, "Missing file should return empty dict"
        print("PASS: missing file returns empty dict")
    finally:
        stratum_fork.SPONSORS_FILE = old_file


if __name__ == "__main__":
    test_valid_pkh_lock()
    test_valid_hash160_lock()
    test_invalid_lock_length()
    test_malformed_hex()
    test_missing_lock_field()
    test_valid_pqh_lock()
    test_mixed_valid_invalid()
    test_missing_file()
    print("\nAll tests passed!")
