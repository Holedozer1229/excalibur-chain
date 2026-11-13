"""bip39.py — BIP39 mnemonics for the Excalibur wallet.

Standard BIP39 (https://github.com/bitcoin/bips/blob/master/bip-0039.mediawiki):
  * entropy 128 bits -> 12 words, 256 bits -> 24 words
  * checksum = first ENT/32 bits of SHA256(entropy), appended to entropy
  * seed = PBKDF2-HMAC-SHA512(mnemonic, "mnemonic" + passphrase, 2048)

The wordlist is the canonical BIP39 English list (2048 words), shipped
as bip39_english.txt next to this module. Nothing here is invented:
the test vector entropy 0x00*16 -> "abandon" x11 + "about" is the
published BIP39 vector and is asserted in the test suite.
"""
import hashlib
import os

_WORDS = None


def _load_words():
    global _WORDS
    if _WORDS is None:
        here = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(here, "bip39_english.txt")) as f:
            words = [w.strip() for w in f if w.strip()]
        if len(words) != 2048 or len(set(words)) != 2048:
            raise RuntimeError("BIP39 wordlist must be exactly 2048 unique words")
        _WORDS = words
    return _WORDS


def wordlist():
    """The canonical BIP39 English wordlist (2048 unique words)."""
    return list(_load_words())


def validate_mnemonic(mnemonic: str) -> bool:
    """True iff the mnemonic has valid words and a valid checksum."""
    try:
        mnemonic_to_entropy(mnemonic)
        return True
    except (ValueError, TypeError):
        return False


def entropy_to_mnemonic(entropy: bytes) -> str:
    """Entropy (16 or 32 bytes) -> mnemonic words. Raises on bad length."""
    if len(entropy) not in (16, 32):
        raise ValueError("entropy must be 16 bytes (12 words) or 32 bytes (24 words)")
    words = _load_words()
    ent_bits = len(entropy) * 8
    cs_bits = ent_bits // 32
    h = hashlib.sha256(entropy).digest()
    # entropy bits + checksum bits, read 11 bits at a time
    data = int.from_bytes(entropy, "big") << cs_bits
    data |= h[0] >> (8 - cs_bits)
    total = ent_bits + cs_bits
    out = []
    for i in range(total // 11):
        shift = total - 11 * (i + 1)
        out.append(words[(data >> shift) & 0x7FF])
    return " ".join(out)


def mnemonic_to_entropy(mnemonic: str) -> bytes:
    """Mnemonic -> entropy. Validates every word and the checksum."""
    words = _load_words()
    index = {w: i for i, w in enumerate(words)}
    parts = mnemonic.strip().split()
    if len(parts) not in (12, 24):
        raise ValueError("mnemonic must be 12 or 24 words")
    data = 0
    for w in parts:
        if w not in index:
            raise ValueError(f"not a BIP39 word: {w!r}")
        data = (data << 11) | index[w]
    total = len(parts) * 11
    cs_bits = total // 33
    ent_bits = total - cs_bits
    entropy = (data >> cs_bits).to_bytes(ent_bits // 8, "big")
    # checksum: first cs_bits of SHA256(entropy)
    h = hashlib.sha256(entropy).digest()
    expect = h[0] >> (8 - cs_bits)
    if (data & ((1 << cs_bits) - 1)) != expect:
        raise ValueError("mnemonic checksum mismatch")
    return entropy


def generate_mnemonic(strength_bits: int = 128) -> str:
    """Fresh mnemonic from a cryptographic RNG. 128 -> 12 words, 256 -> 24."""
    if strength_bits not in (128, 256):
        raise ValueError("strength must be 128 or 256 bits")
    return entropy_to_mnemonic(os.urandom(strength_bits // 8))


def mnemonic_to_seed(mnemonic: str, passphrase: str = "") -> bytes:
    """BIP39 seed: PBKDF2-HMAC-SHA512(mnemonic, "mnemonic"+passphrase, 2048)."""
    # Validate first: a mistyped mnemonic must fail here, not silently
    # derive a different wallet.
    mnemonic_to_entropy(mnemonic)
    return hashlib.pbkdf2_hmac(
        "sha512", mnemonic.strip().encode("utf-8"),
        ("mnemonic" + passphrase).encode("utf-8"), 2048, 64)
