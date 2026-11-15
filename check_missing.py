#!/usr/bin/env python3
"""Check for missing BIP39 words."""
from sphinx_os.nexus.bip39_pictographic import BIP39_WORDS

# Canonical BIP39 words that might be missing
canonical_check = [
    'liar', 'lounge', 'wet', 'modem', 'law', 'sunset', 'sadness',
    'empower', 'enact', 'endorse', 'enemy', 'fitness', 'fury', 'myth',
    'odor', 'urge', 'web', 'handle', 'happiness', 'harmony'
]

print(f"Total words: {len(BIP39_WORDS)}")
print(f"Missing from canonical:")
missing = []
for w in canonical_check:
    if w not in BIP39_WORDS:
        missing.append(w)
        print(f"  {w}")

# Check for words that are NOT in canonical BIP39
non_canonical = ['empower', 'enact', 'endorse', 'enemy', 'fitness', 'fury', 'myth', 'odor', 'urge', 'web', 'sadness', 'sunset', 'handle']
print(f"\nNon-canonical words present:")
for w in non_canonical:
    if w in BIP39_WORDS:
        print(f"  {w}")

print(f"\nNeed to add: {2048 - len(BIP39_WORDS)} words to reach 2048")
