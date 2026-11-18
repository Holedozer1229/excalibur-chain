#!/usr/bin/env python3
"""
The Cross-Encoding Cipher: Base58 <-> bech32

DISCOVERED FORMULA:
For any character at Base58 position p:
  LEFT  = 2p - 68  (if p >= 37)  or  2p - 67  (if p <= 36)
  RIGHT = 2p - 67  (if p >= 37)  or  2p - 68  (if p <= 36)

This can be written elegantly as:
  CENTER = 2p - 67.5
  LEFT  = floor(CENTER)
  RIGHT = ceil(CENTER)

The user's pattern:
  0=q=1   (q at Base58 pos 48: LEFT=2*48-68=28... wait, that gives 28, not 0!)

Let me re-verify.
"""

BASE58_ALPHABET = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'
BECH32_ALPHABET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"

print("=" * 80)
print("VERIFICATION OF THE CIPHER FORMULA")
print("=" * 80)
print()

# User's data
user_data = {
    'q': (0, 1),
    'f': (8, 9),
    'e': (6, 7),
    'd': (5, 4),
    'c': (3, 2),
    'b': (1, 0),
    'a': (-1, -1),
}

print("Testing formula: LEFT = 2p - 68, RIGHT = 2p - 67 (for p >= 37)")
print("                 LEFT = 2p - 67, RIGHT = 2p - 68 (for p <= 36)")
print()

all_match = True
for char, (expected_left, expected_right) in user_data.items():
    p = BASE58_ALPHABET.index(char)
    
    if p >= 37:
        left = 2 * p - 68
        right = 2 * p - 67
    else:
        left = 2 * p - 67
        right = 2 * p - 68
    
    left_match = left == expected_left
    right_match = right == expected_right
    
    if not (left_match and right_match):
        all_match = False
    
    status = "OK" if (left_match and right_match) else "FAIL"
    print(f"  {char}: p={p:2d}, LEFT={left:3d} (expected {expected_left:3d}) {'OK' if left_match else 'FAIL'}, "
          f"RIGHT={right:3d} (expected {expected_right:3d}) {'OK' if right_match else 'FAIL'} => {status}")

print()
if all_match:
    print("ALL MATCHES CONFIRMED!")
else:
    print("SOME MATCHES FAILED — formula needs adjustment")

print()
print("=" * 80)
print("BUT WAIT — q at position 48:")
print("=" * 80)
print()

p_q = BASE58_ALPHABET.index('q')
print(f"  q is at Base58 position {p_q}")
print(f"  Formula: LEFT = 2*{p_q} - 68 = {2*p_q - 68}")
print(f"  Formula: RIGHT = 2*{p_q} - 67 = {2*p_q - 67}")
print(f"  User expects: LEFT=0, RIGHT=1")
print(f"  Formula gives: LEFT={2*p_q - 68}, RIGHT={2*p_q - 67}")
print()
print(f"  MATCH: LEFT={2*p_q - 68 == 0}, RIGHT={2*p_q - 67 == 1}")
print()

# 2*48-68 = 96-68 = 28, not 0!
# 2*48-67 = 96-67 = 29, not 1!

# So the formula does NOT work for q!
# It only works for f,e,d,c,b,a (positions 38,37,36,35,34,33)

print("=" * 80)
print("CORRECTION: The formula only works for f,e,d,c,b,a (p=33-38)")
print("It does NOT work for q (p=48)")
print("=" * 80)
print()

# Let me check what formula works for q
print("For q (p=48), user expects LEFT=0, RIGHT=1:")
print(f"  2*48 - X = 0 => X = 96")
print(f"  2*48 - Y = 1 => Y = 95")
print()
print("So for q: LEFT = 2p - 96, RIGHT = 2p - 95")
print()
print("For f (p=38), user expects LEFT=8, RIGHT=9:")
print(f"  2*38 - X = 8 => X = 68")
print(f"  2*38 - Y = 9 => Y = 67")
print()
print("The offset changes from 96/95 for q to 68/67 for f,e,d,c,b,a")
print()

# What determines the offset?
# q: p=48, offset=96 (LEFT) and 95 (RIGHT)
# f: p=38, offset=68 (LEFT) and 67 (RIGHT)
# e: p=37, offset=68 (LEFT) and 67 (RIGHT)
# d: p=36, offset=67 (LEFT) and 68 (RIGHT)
# ...

# For q: 2p - 96 = 0, so offset = 96 = 2*48 = 2p
# For f: 2p - 68 = 8, so offset = 68 = 2*34 = 2*(p-4)
# For e: 2p - 68 = 6, so offset = 68 = 2*34 = 2*(p-3)

# Hmm, not clean.

# Let me try: what if the formula uses bech32 value instead of Base58 position?
print("=" * 80)
print("ALTERNATIVE: Using bech32 value instead of Base58 position")
print("=" * 80)
print()

for char, (expected_left, expected_right) in user_data.items():
    if char in BECH32_ALPHABET:
        b32 = BECH32_ALPHABET.index(char)
        p = BASE58_ALPHABET.index(char)
        
        # Try: LEFT = b32 - X
        # q: b32=0, LEFT=0 => X=0
        # f: b32=9, LEFT=8 => X=1
        # e: b32=25, LEFT=6 => X=19
        # Not clean
        
        # Try: LEFT = p - b32
        # q: 48-0=48, not 0
        # f: 38-9=29, not 8
        
        # Try: LEFT = (p + b32) - X
        # q: 48+0=48, 48-48=0 => X=48
        # f: 38+9=47, 47-39=8 => X=39
        # Not clean
        
        print(f"  {char}: b58_pos={p}, bech32_val={b32}")
        print(f"    User: LEFT={expected_left}, RIGHT={expected_right}")
        print(f"    p - b32 = {p - b32}")
        print(f"    b32 - p = {b32 - p}")
        print(f"    p + b32 = {p + b32}")
        print(f"    p * b32 = {p * b32}")
    else:
        p = BASE58_ALPHABET.index(char)
        print(f"  {char}: b58_pos={p}, bech32_val=NOT IN ALPHABET")
        print(f"    User: LEFT={expected_left}, RIGHT={expected_right}")
    print()

print("=" * 80)
print("THE REAL PATTERN: Looking at the user's format again")
print("=" * 80)
print()
print("The user wrote: 0=q=1, 8=f=9, 6=e=7, 5=d=4, 3=c=2, 1=b=0, -1=a=-1")
print()
print("What if LEFT and RIGHT are NOT derived from Base58 position,")
print("but are the bech32 and Base58 VALUES of the middle character?")
print()
print("0=q=1:")
print("  bech32 'q' = 0 (LEFT)")
print("  Base58 'q' = 48, but user wrote 1 (RIGHT)")
print("  Base58 '1' = 0, which matches LEFT=0")
print("  So RIGHT=1 might mean Base58 character '1' (which has value 0)")
print()
print("8=f=9:")
print("  bech32 'f' = 9, but user wrote 8 (LEFT)")
print("  Base58 'f' = 38, but user wrote 9 (RIGHT)")
print("  Base58 '9' = 8, which matches LEFT=8")
print("  So LEFT=8 might mean Base58 character '9' (which has value 8)")
print("  And RIGHT=9 is the bech32 value of 'f'")
print()
print("THIS IS IT! The format is:")
print("  BASE58_VALUE_OF_RIGHT_CHAR = MIDDLE_CHAR = BECH32_VALUE_OF_MIDDLE_CHAR")
print()
print("Let me verify:")
print()

for char, (expected_left, expected_right) in user_data.items():
    print(f"  {expected_left}={char}={expected_right}")
    
    # RIGHT should be bech32 value of middle char
    if char in BECH32_ALPHABET:
        b32_val = BECH32_ALPHABET.index(char)
        print(f"    bech32 '{char}' = {b32_val} (RIGHT={expected_right}, match={b32_val == expected_right})")
    else:
        print(f"    '{char}' not in bech32 (RIGHT={expected_right})")
    
    # LEFT should be Base58 value of some character
    # The right side character
    if expected_right < 10:
        right_char = str(expected_right)
        if right_char in BASE58_ALPHABET:
            b58_val = BASE58_ALPHABET.index(right_char)
            print(f"    Base58 '{right_char}' = {b58_val} (LEFT={expected_left}, match={b58_val == expected_left})")
        else:
            print(f"    '{right_char}' not in Base58")
    print()
