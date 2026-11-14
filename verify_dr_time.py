"""Verify the Dr. Time countersignature bundle."""
import json, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from trifold_lockbox import verify
from dr_time_overflow_countersignature import sig_from_json, HEADER_HEX, BAD_BLOCK_HASH

bundle = json.load(open("dr-time-overflow-countersignature.json"))
header = bytes.fromhex(HEADER_HEX)
root = bytes.fromhex(bundle["trifold_root"])
sig = sig_from_json(bundle["signature"])

# Verify the signature
valid = verify(root, header, sig)
print("Signature verification:", "PASS" if valid else "FAIL")

# Verify header hash
import hashlib
h = hashlib.sha256(hashlib.sha256(header).digest()).digest()
computed = h[::-1].hex()
print("Header hash match:", "PASS" if computed == BAD_BLOCK_HASH else "FAIL")

# Test bit-flip resistance
flipped = bytearray(header)
flipped[40] ^= 0x01
flip_valid = verify(root, bytes(flipped), sig)
print("Bit-flip rejected:", "PASS" if not flip_valid else "FAIL")

print()
if valid and computed == BAD_BLOCK_HASH and not flip_valid:
    print("All verifications passed. The countersignature is valid.")
else:
    print("VERIFICATION FAILED")
    sys.exit(1)
