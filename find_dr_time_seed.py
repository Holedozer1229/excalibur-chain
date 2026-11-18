#!/usr/bin/env python3
"""Find the seed that produces the canonical DR Time root 7083fbeb..."""

import hashlib
import sys
import os
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from trifold_lockbox import TrifoldKey

BAD_BLOCK_HASH = "0000000000790ab3f22ec756ad43b6ab569abf0bddeb97c67a6f7b1470a7ec1c"
CANONICAL_ROOT = "7083fbebd6bfbd5f82fd40827cf36bc30da81524914011e69488b5a63e7bfe55"

bad_block_bytes = bytes.fromhex(BAD_BLOCK_HASH)

# Try different seed derivations
candidates = [
    ("SHA256(bad_block_hash)", hashlib.sha256(bad_block_bytes).digest()),
    ("SHA256('Dr. Time: ' + bad_block)", hashlib.sha256(b"Dr. Time: " + bad_block_bytes).digest()),
    ("SHA256('DR. TIME: ' + bad_block)", hashlib.sha256(b"DR. TIME: " + bad_block_bytes).digest()),
    ("SHA256('dr_time: ' + bad_block)", hashlib.sha256(b"dr_time: " + bad_block_bytes).digest()),
    ("SHA256('overflow: ' + bad_block)", hashlib.sha256(b"overflow: " + bad_block_bytes).digest()),
    ("SHA256('Dr.Time: ' + bad_block)", hashlib.sha256(b"Dr.Time: " + bad_block_bytes).digest()),
    ("SHA256(bad_block + 'Dr. Time')", hashlib.sha256(bad_block_bytes + b"Dr. Time").digest()),
    ("SHA256('DR. TIME OVERFLOW')", hashlib.sha256(b"DR. TIME OVERFLOW").digest()),
    ("SHA256('Dr. Time overflow')", hashlib.sha256(b"Dr. Time overflow").digest()),
    ("SHA256('overflow countersignature')", hashlib.sha256(b"overflow countersignature").digest()),
    ("SHA256('Dr. Time: overflow')", hashlib.sha256(b"Dr. Time: overflow").digest()),
    ("SHA256('DR. TIME')", hashlib.sha256(b"DR. TIME").digest()),
    ("SHA256('Dr. Time')", hashlib.sha256(b"Dr. Time").digest()),
    ("SHA256('dr_time_overflow')", hashlib.sha256(b"dr_time_overflow").digest()),
    ("SHA256('Dr. Time overflow countersignature')", hashlib.sha256(b"Dr. Time overflow countersignature").digest()),
    ("SHA256('DR. TIME OVERFLOW COUNTERSIGNATURE')", hashlib.sha256(b"DR. TIME OVERFLOW COUNTERSIGNATURE").digest()),
    ("SHA256('overflow')", hashlib.sha256(b"overflow").digest()),
    ("SHA256('Dr. Time 2026-11-11')", hashlib.sha256(b"Dr. Time 2026-11-11").digest()),
    ("SHA256('Dr. Time: 2010 value-overflow')", hashlib.sha256(b"Dr. Time: 2010 value-overflow").digest()),
    ("SHA256('Dr. Time: bad block 74638')", hashlib.sha256(b"Dr. Time: bad block 74638").digest()),
    ("SHA256('Dr. Time: ' + full_hash_str)", hashlib.sha256(b"Dr. Time: 0000000000790ab3f22ec756ad43b6ab569abf0bddeb97c67a6f7b1470a7ec1c").digest()),
    ("SHA256('Dr. Time: ' + bad_block[:4])", hashlib.sha256(b"Dr. Time: " + bad_block_bytes[:4]).digest()),
    ("SHA256(bad_block[:4])", hashlib.sha256(bad_block_bytes[:4]).digest()),
    ("SHA256('Dr. Time: 74638')", hashlib.sha256(b"Dr. Time: 74638").digest()),
    ("SHA256('Dr. Time: value-overflow')", hashlib.sha256(b"Dr. Time: value-overflow").digest()),
    ("SHA256('Dr. Time: value overflow')", hashlib.sha256(b"Dr. Time: value overflow").digest()),
    ("SHA256('Dr. Time: 184467440737')", hashlib.sha256(b"Dr. Time: 184467440737").digest()),
    ("SHA256('Dr. Time: 184467440737.09551616')", hashlib.sha256(b"Dr. Time: 184467440737.09551616").digest()),
    ("SHA256('Dr. Time: 184467440737.09551616 BTC')", hashlib.sha256(b"Dr. Time: 184467440737.09551616 BTC").digest()),
    ("SHA256('Dr. Time: 184467440737.09551616 BTC from nothing')", hashlib.sha256(b"Dr. Time: 184467440737.09551616 BTC from nothing").digest()),
    ("SHA256('Dr. Time: 184,467,440,737.09551616 BTC')", hashlib.sha256(b"Dr. Time: 184,467,440,737.09551616 BTC").digest()),
    ("SHA256('Dr. Time: 184,467,440,737.09551616 BTC from nothing')", hashlib.sha256(b"Dr. Time: 184,467,440,737.09551616 BTC from nothing").digest()),
    ("SHA256('Dr. Time: Bitcoin bad block 74638')", hashlib.sha256(b"Dr. Time: Bitcoin bad block 74638").digest()),
    ("SHA256('Dr. Time: Bitcoin bad block 74638 header')", hashlib.sha256(b"Dr. Time: Bitcoin bad block 74638 header").digest()),
    ("SHA256('Dr. Time: Bitcoin bad block 74638 — the value-overflow block')", hashlib.sha256(b"Dr. Time: Bitcoin bad block 74638 \u2014 the value-overflow block").digest()),
    ("SHA256('Dr. Time: the value-overflow block')", hashlib.sha256(b"Dr. Time: the value-overflow block").digest()),
    ("SHA256('Dr. Time: the 2010 value-overflow block')", hashlib.sha256(b"Dr. Time: the 2010 value-overflow block").digest()),
    ("SHA256('Dr. Time: 2010')", hashlib.sha256(b"Dr. Time: 2010").digest()),
    ("SHA256('Dr. Time: 2010-08-15')", hashlib.sha256(b"Dr. Time: 2010-08-15").digest()),
    ("SHA256('Dr. Time: 1281891957')", hashlib.sha256(b"Dr. Time: 1281891957").digest()),
    ("SHA256('Dr. Time: 28192719')", hashlib.sha256(b"Dr. Time: 28192719").digest()),
    ("SHA256('Dr. Time: 0x1c00800e')", hashlib.sha256(b"Dr. Time: 0x1c00800e").digest()),
    ("SHA256('Dr. Time: 469794830')", hashlib.sha256(b"Dr. Time: 469794830").digest()),
    ("SHA256('Dr. Time: 0000000000790ab3')", hashlib.sha256(b"Dr. Time: 0000000000790ab3").digest()),
    ("SHA256('Dr. Time: 0000000000790ab3f22ec756ad43b6ab569abf0bddeb97c67a6f7b1470a7ec1c')", hashlib.sha256(b"Dr. Time: 0000000000790ab3f22ec756ad43b6ab569abf0bddeb97c67a6f7b1470a7ec1c").digest()),
    ("SHA256('Dr. Time: 1d5e512a9723cbef373b970eb52f1e9598ad67e7408077a82fdac194b65333c9')", hashlib.sha256(b"Dr. Time: 1d5e512a9723cbef373b970eb52f1e9598ad67e7408077a82fdac194b65333c9").digest()),
    ("SHA256('Dr. Time: 1d5e512a')", hashlib.sha256(b"Dr. Time: 1d5e512a").digest()),
    ("SHA256('Dr. Time: overflow tx')", hashlib.sha256(b"Dr. Time: overflow tx").digest()),
    ("SHA256('Dr. Time: overflow transaction')", hashlib.sha256(b"Dr. Time: overflow transaction").digest()),
    ("SHA256('Dr. Time: overflow transaction 1d5e512a')", hashlib.sha256(b"Dr. Time: overflow transaction 1d5e512a").digest()),
    ("SHA256('Dr. Time: overflow transaction 1d5e512a9723cbef373b970eb52f1e9598ad67e7408077a82fdac194b65333c9')", hashlib.sha256(b"Dr. Time: overflow transaction 1d5e512a9723cbef373b970eb52f1e9598ad67e7408077a82fdac194b65333c9").digest()),
    ("SHA256('Dr. Time: 184467440737.09551616 BTC out of nothing')", hashlib.sha256(b"Dr. Time: 184467440737.09551616 BTC out of nothing").digest()),
    ("SHA256('Dr. Time: 184,467,440,737.09551616 BTC out of nothing')", hashlib.sha256(b"Dr. Time: 184,467,440,737.09551616 BTC out of nothing").digest()),
    ("SHA256('Dr. Time: 184467440737.09551616 BTC out of nothing')", hashlib.sha256(b"Dr. Time: 184467440737.09551616 BTC out of nothing").digest()),
    ("SHA256('Dr. Time: 184,467,440,737.09551616 BTC out of nothing')", hashlib.sha256(b"Dr. Time: 184,467,440,737.09551616 BTC out of nothing").digest()),
    ("SHA256('Dr. Time: 184467440737.09551616 BTC out of nothing')", hashlib.sha256(b"Dr. Time: 184467440737.09551616 BTC out of nothing").digest()),
    ("SHA256('Dr. Time: 184,467,440,737.09551616 BTC out of nothing')", hashlib.sha256(b"Dr. Time: 184,467,440,737.09551616 BTC out of nothing").digest()),
    ("SHA256('Dr. Time: 184467440737.09551616 BTC out of nothing')", hashlib.sha256(b"Dr. Time: 184467440737.09551616 BTC out of nothing").digest()),
    ("SHA256('Dr. Time: 184,467,440,737.09551616 BTC out of nothing')", hashlib.sha256(b"Dr. Time: 184,467,440,737.09551616 BTC out of nothing").digest()),
    ("SHA256('Dr. Time: 184467440737.09551616 BTC out of nothing')", hashlib.sha256(b"Dr. Time: 184467440737.09551616 BTC out of nothing").digest()),
    ("SHA256('Dr. Time: 184,467,440,737.09551616 BTC out of nothing')", hashlib.sha256(b"Dr. Time: 184,467,440,737.09551616 BTC out of nothing").digest()),
]

found = False
for label, seed in candidates:
    try:
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
            tmp = f.name
        key = TrifoldKey(seed, height=6, state_path=tmp)
        if key.root.hex() == CANONICAL_ROOT:
            print(f"MATCH: {label}")
            print(f"  Seed: {seed.hex()}")
            print(f"  Root: {key.root.hex()}")
            found = True
        os.unlink(tmp)
    except Exception as e:
        pass

if not found:
    print("No match found in candidates.")
    print(f"Target root: {CANONICAL_ROOT}")
    
    # Try the header hex as seed
    HEADER_HEX = "01000000846e2b968653ef0a25a92c12e8884d76919907df8e3079e665686000000000005eecb6808d6de56a05211483d86fc6c7d17cda46c3388dd0c8139e4114ba8e61751e684c0e80001ccf2fae01"
    header_bytes = bytes.fromhex(HEADER_HEX)
    
    extra = [
        ("SHA256(header_bytes)", hashlib.sha256(header_bytes).digest()),
        ("SHA256('Dr. Time: ' + header)", hashlib.sha256(b"Dr. Time: " + header_bytes).digest()),
        ("SHA256('Dr. Time: ' + header[:80])", hashlib.sha256(b"Dr. Time: " + header_bytes[:80]).digest()),
        ("SHA256('Dr. Time: ' + header[:40])", hashlib.sha256(b"Dr. Time: " + header_bytes[:40]).digest()),
        ("SHA256('Dr. Time: ' + header[:20])", hashlib.sha256(b"Dr. Time: " + header_bytes[:20]).digest()),
        ("SHA256('Dr. Time: ' + header[:10])", hashlib.sha256(b"Dr. Time: " + header_bytes[:10]).digest()),
        ("SHA256('Dr. Time: ' + header[:8])", hashlib.sha256(b"Dr. Time: " + header_bytes[:8]).digest()),
        ("SHA256('Dr. Time: ' + header[:4])", hashlib.sha256(b"Dr. Time: " + header_bytes[:4]).digest()),
        ("SHA256('Dr. Time: ' + header[:2])", hashlib.sha256(b"Dr. Time: " + header_bytes[:2]).digest()),
        ("SHA256('Dr. Time: ' + header[:1])", hashlib.sha256(b"Dr. Time: " + header_bytes[:1]).digest()),
        ("SHA256('Dr. Time: ' + header_hex_str)", hashlib.sha256(b"Dr. Time: " + HEADER_HEX.encode()).digest()),
        ("SHA256('Dr. Time: ' + header_hex_str[:80])", hashlib.sha256(b"Dr. Time: " + HEADER_HEX[:80].encode()).digest()),
        ("SHA256('Dr. Time: ' + header_hex_str[:40])", hashlib.sha256(b"Dr. Time: " + HEADER_HEX[:40].encode()).digest()),
        ("SHA256('Dr. Time: ' + header_hex_str[:20])", hashlib.sha256(b"Dr. Time: " + HEADER_HEX[:20].encode()).digest()),
        ("SHA256('Dr. Time: ' + header_hex_str[:10])", hashlib.sha256(b"Dr. Time: " + HEADER_HEX[:10].encode()).digest()),
        ("SHA256('Dr. Time: ' + header_hex_str[:8])", hashlib.sha256(b"Dr. Time: " + HEADER_HEX[:8].encode()).digest()),
        ("SHA256('Dr. Time: ' + header_hex_str[:4])", hashlib.sha256(b"Dr. Time: " + HEADER_HEX[:4].encode()).digest()),
        ("SHA256('Dr. Time: ' + header_hex_str[:2])", hashlib.sha256(b"Dr. Time: " + HEADER_HEX[:2].encode()).digest()),
        ("SHA256('Dr. Time: ' + header_hex_str[:1])", hashlib.sha256(b"Dr. Time: " + HEADER_HEX[:1].encode()).digest()),
    ]
    
    for label, seed in extra:
        try:
            with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
                tmp = f.name
            key = TrifoldKey(seed, height=6, state_path=tmp)
            if key.root.hex() == CANONICAL_ROOT:
                print(f"MATCH: {label}")
                print(f"  Seed: {seed.hex()}")
                print(f"  Root: {key.root.hex()}")
                found = True
            os.unlink(tmp)
        except Exception as e:
            pass

    if not found:
        print("Still no match. The canonical seed is unknown.")
