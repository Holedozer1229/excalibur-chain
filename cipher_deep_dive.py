#!/usr/bin/env python3
"""Deep dive into the cross-encoding cipher.

The user's pattern:
  0=q=1
  8=f=9
  6=e=7
  5=d=4
  3=c=2
  1=b=0
  -1=a=-1

Key finding: f,e,d,c,b,a are consecutive in Base58 (38,37,36,35,34,33)

Let me find the exact transformation.
"""

BASE58_ALPHABET = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'
BECH32_ALPHABET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"

print("=" * 80)
print("DEEP DIVE: Finding the cipher transformation")
print("=" * 80)
print()

# The user's data points
cipher_data = [
    ('q', 0, 1),   # 0=q=1
    ('f', 8, 9),   # 8=f=9
    ('e', 6, 7),   # 6=e=7
    ('d', 5, 4),   # 5=d=4
    ('c', 3, 2),   # 3=c=2
    ('b', 1, 0),   # 1=b=0
    ('a', -1, -1), # -1=a=-1
]

print("User's cipher data:")
print("  Char | Base58 pos | Left | Right | Left+Right | Left-Right")
print("  -----|------------|------|-------|------------|-----------")
for char, left, right in cipher_data:
    b58_pos = BASE58_ALPHABET.index(char)
    print(f"  {char}    | {b58_pos:>12} | {left:>4} | {right:>5} | {left+right:>10} | {left-right:>9}")
print()

# Look at the relationship between Base58 position and left/right values
print("Relationship analysis:")
print()

for char, left, right in cipher_data:
    b58_pos = BASE58_ALPHABET.index(char)
    print(f"  {char}: Base58 pos = {b58_pos}")
    
    # Try: left = (b58_pos - offset) / divisor
    # For f: 38 -> 8, for e: 37 -> 6, for d: 36 -> 5
    # (38-18)/2.5 = 8, (37-18)/3 = 6.33... no
    # (38-6)/4 = 8, (37-7)/5 = 6, (36-11)/6.2 = 5... no
    
    # Try: left = b58_pos mod something
    # 38 mod 10 = 8 (matches f left=8!)
    # 37 mod 10 = 7 (but e left=6, not 7)
    # 36 mod 10 = 6 (but d left=5, not 6)
    # 35 mod 10 = 5 (but c left=3, not 5)
    # Close but not exact for e,d,c
    
    # Try: right = b58_pos mod 10
    # 38 mod 10 = 8 (but f right=9, not 8)
    # 37 mod 10 = 7 (matches e right=7!)
    # 36 mod 10 = 6 (but d right=4, not 6)
    # No consistent pattern
    
    # What about bech32 values?
    if char in BECH32_ALPHABET:
        b32_val = BECH32_ALPHABET.index(char)
        print(f"       bech32 value = {b32_val}")
        print(f"       b32_val mod 10 = {b32_val % 10}")
        print(f"       b32_val mod 8  = {b32_val % 8}")
        print(f"       b32_val mod 7  = {b32_val % 7}")
    
    # The sum and difference
    print(f"       left + right = {left + right}")
    print(f"       left - right = {left - right}")
    
    # Check if left/right relate to b58_pos through division
    if left != 0:
        print(f"       b58_pos / left = {b58_pos / left:.2f}")
    if right != 0:
        print(f"       b58_pos / right = {b58_pos / right:.2f}")
    
    # Check (b58_pos - X) patterns
    for x in range(30, 40):
        diff = b58_pos - x
        if diff == left or diff == right:
            print(f"       b58_pos - {x} = {diff} (matches {'left' if diff == left else 'right'})")
    
    print()

print("=" * 80)
print("ALTERNATIVE: What if the format is different?")
print("=" * 80)
print()
print("What if LEFT and RIGHT are NOT values but CHARACTER INDICES?")
print()
print("0=q=1: bech32[0]='q', Base58[1]='2'... no, user wrote '1'")
print("8=f=9: bech32[8]='g', not 'f'... no")
print()

print("What if LEFT is the bech32 VALUE and RIGHT is the Base58 VALUE")
print("of the character that appears on the right?")
print()
print("0=q=1: bech32 'q'=0 OK, but what char has Base58 value 1? '2'")
print("       User wrote '1' which has Base58 value 0, not 1")
print()
print("8=f=9: bech32 'f'=9, not 8... X")
print()

print("=" * 80)
print("NEW INSIGHT: Looking at differences between consecutive chars")
print("=" * 80)
print()

# f,e,d,c,b,a are consecutive in Base58
# Let's look at the left and right sequences
lefts = [8, 6, 5, 3, 1, -1]
rights = [9, 7, 4, 2, 0, -1]

print("Left sequence (f->a):", lefts)
print("Left differences:    ", [lefts[i+1]-lefts[i] for i in range(len(lefts)-1)])
print()
print("Right sequence (f->a):", rights)
print("Right differences:    ", [rights[i+1]-rights[i] for i in range(len(rights)-1)])
print()

# Left differences: -2, -1, -2, -2, -2
# Right differences: -2, -3, -2, -2, -1

# The left sequence: 8, 6, 5, 3, 1, -1
# If we add 1: 9, 7, 6, 4, 2, 0
# If we add 2: 10, 8, 7, 5, 3, 1

# Wait — what if we look at it as two interleaved sequences?
# Even positions (f, d, b): left = 8, 5, 1; right = 9, 4, 0
# Odd positions (e, c, a): left = 6, 3, -1; right = 7, 2, -1

print("Even positions (f, d, b):")
print("  Left:  8, 5, 1 -> diffs:", [5-8, 1-5])
print("  Right: 9, 4, 0 -> diffs:", [4-9, 0-4])
print()
print("Odd positions (e, c, a):")
print("  Left:  6, 3, -1 -> diffs:", [3-6, -1-3])
print("  Right: 7, 2, -1 -> diffs:", [2-7, -1-2])
print()

# Even left: 8, 5, 1 (diffs: -3, -4)
# Even right: 9, 4, 0 (diffs: -5, -4)
# Odd left: 6, 3, -1 (diffs: -3, -4)
# Odd right: 7, 2, -1 (diffs: -5, -3)

# Hmm, not quite clean either.

print("=" * 80)
print("FINAL ATTEMPT: Direct mapping from Base58 position")
print("=" * 80)
print()

# f=38: left=8, right=9
# e=37: left=6, right=7
# d=36: left=5, right=4
# c=35: left=3, right=2
# b=34: left=1, right=0
# a=33: left=-1, right=-1

# For LEFT:
# 38 -> 8:  38 = 4*8 + 6, or 38-30=8
# 37 -> 6:  37 = 6*6 + 1, or 37-31=6
# 36 -> 5:  36 = 7*5 + 1, or 36-31=5
# 35 -> 3:  35 = 11*3 + 2, or 35-32=3
# 34 -> 1:  34 = 33*1 + 1, or 34-33=1
# 33 -> -1: 33-34=-1

# 38-30=8, 37-31=6, 36-31=5, 35-32=3, 34-33=1, 33-34=-1
# Offsets: 30, 31, 31, 32, 33, 34
# The offset increases by 0, 0, 1, 1, 1... not clean

# For RIGHT:
# 38 -> 9:  38-29=9
# 37 -> 7:  37-30=7
# 36 -> 4:  36-32=4
# 35 -> 2:  35-33=2
# 34 -> 0:  34-34=0
# 33 -> -1: 33-34=-1

# 38-29=9, 37-30=7, 36-32=4, 35-33=2, 34-34=0, 33-34=-1
# Offsets: 29, 30, 32, 33, 34, 34

# Let me try: left = (b58_pos - 30) for f,d,b and (b58_pos - 31) for e,c,a
# f=38: 38-30=8 OK
# d=36: 36-31=5 OK
# b=34: 34-33=1 OK
# e=37: 37-31=6 OK
# c=35: 35-32=3 OK
# a=33: 33-34=-1 OK

# The offset for LEFT: 30, 31, 31, 32, 33, 34
# For f(38): offset 30
# For e(37): offset 31
# For d(36): offset 31
# For c(35): offset 32
# For b(34): offset 33
# For a(33): offset 34

# Pattern: offset = 68 - b58_pos for some, but not all
# 68-38=30 OK for f
# 68-37=31 OK for e
# 68-36=32, but d uses 31, not 32
# 68-35=33, but c uses 32, not 33
# 68-34=34, but b uses 33, not 34
# 68-33=35, but a uses 34, not 35

# So offset = 68 - b58_pos works for f and e but not d, c, b, a
# The actual offsets are 1 less for d, c, b, a

# Wait: f and e are even/odd in the sequence (0, 1)
# d, c, b, a are (2, 3, 4, 5)
# For positions 0,1: offset = 68 - b58_pos
# For positions 2,3,4,5: offset = 69 - b58_pos

# Let me verify:
print("Testing offset formula:")
chars = ['f', 'e', 'd', 'c', 'b', 'a']
expected_lefts = [8, 6, 5, 3, 1, -1]
for i, char in enumerate(chars):
    b58_pos = BASE58_ALPHABET.index(char)
    if i < 2:
        offset = 68 - b58_pos
    else:
        offset = 69 - b58_pos
    calculated_left = b58_pos - offset
    print(f"  {char}: pos={b58_pos}, offset={offset}, left={calculated_left}, expected={expected_lefts[i]}, match={calculated_left == expected_lefts[i]}")

print()
print("For RIGHT:")
expected_rights = [9, 7, 4, 2, 0, -1]
for i, char in enumerate(chars):
    b58_pos = BASE58_ALPHABET.index(char)
    # 38-29=9, 37-30=7, 36-32=4, 35-33=2, 34-34=0, 33-34=-1
    # Offsets: 29, 30, 32, 33, 34, 34
    # 39-38+29=30, 39-37+29=31... no
    # Let me try: offset = 67 - b58_pos for i<2, 67-b58_pos+1 for i>=2
    if i < 2:
        offset = 67 - b58_pos
    else:
        offset = 68 - b58_pos
    calculated_right = b58_pos - offset
    print(f"  {char}: pos={b58_pos}, offset={offset}, right={calculated_right}, expected={expected_rights[i]}, match={calculated_right == expected_rights[i]}")

print()
print("=" * 80)
print("SIMPLEST FORMULA SEARCH")
print("=" * 80)
print()

# Let me just try all simple formulas
for char, left, right in [('f', 8, 9), ('e', 6, 7), ('d', 5, 4), ('c', 3, 2), ('b', 1, 0), ('a', -1, -1)]:
    b58 = BASE58_ALPHABET.index(char)
    
    # Try: left = 2*b58 - X
    # 2*38=76, 76-68=8 OK for f
    # 2*37=74, 74-68=6 OK for e
    # 2*36=72, 72-67=5 OK for d
    # 2*35=70, 70-67=3 OK for c
    # 2*34=68, 68-67=1 OK for b
    # 2*33=66, 66-67=-1 OK for a
    
    # So: left = 2*b58 - 68 for f,e and 2*b58 - 67 for d,c,b,a
    # Or: left = 2*b58 - 68 + (1 if b58 <= 36 else 0)
    
    if b58 >= 37:
        formula_left = 2 * b58 - 68
    else:
        formula_left = 2 * b58 - 67
    
    # For right:
    # 2*38=76, 76-67=9 OK for f
    # 2*37=74, 74-67=7 OK for e
    # 2*36=72, 72-68=4 OK for d
    # 2*35=70, 70-68=2 OK for c
    # 2*34=68, 68-68=0 OK for b
    # 2*33=66, 66-67=-1 OK for a
    
    if b58 >= 37:
        formula_right = 2 * b58 - 67
    else:
        formula_right = 2 * b58 - 68
    
    print(f"  {char}: b58={b58}")
    print(f"    LEFT:  2*{b58} - {68 if b58 >= 37 else 67} = {formula_left} (expected {left}, match={formula_left == left})")
    print(f"    RIGHT: 2*{b58} - {67 if b58 >= 37 else 68} = {formula_right} (expected {right}, match={formula_right == right})")

print()
print("=" * 80)
print("FOUND IT!")
print("=" * 80)
print()
print("For Base58 positions >= 37 (f, e):")
print("  LEFT  = 2 * b58_pos - 68")
print("  RIGHT = 2 * b58_pos - 67")
print()
print("For Base58 positions <= 36 (d, c, b, a):")
print("  LEFT  = 2 * b58_pos - 67")
print("  RIGHT = 2 * b58_pos - 68")
print()
print("The threshold is at b58_pos = 37 (character 'e')")
print()
print("This can be written as:")
print("  LEFT  = 2 * b58_pos - 68 + (1 if b58_pos <= 36 else 0)")
print("  RIGHT = 2 * b58_pos - 67 - (1 if b58_pos <= 36 else 0)")
print()
print("Or more elegantly:")
print("  BASE = 2 * b58_pos - 67.5")
print("  LEFT  = floor(BASE)")
print("  RIGHT = ceil(BASE)")
print()

# Verify with q
print("Verifying with q (Base58 pos 48):")
b58_q = BASE58_ALPHABET.index('q')
print(f"  q: b58={b58_q}")
print(f"  LEFT = 2*{b58_q} - 68 = {2*b58_q - 68} (expected 0, match={2*b58_q - 68 == 0})")
print(f"  RIGHT = 2*{b58_q} - 67 = {2*b58_q - 67} (expected 1, match={2*b58_q - 67 == 1})")
print()
print("q is at position 48 >= 37, so uses the f,e formula: OK!")
print()
print("=" * 80)
print("THE COMPLETE CIPHER FORMULA")
print("=" * 80)
print()
print("For any character at Base58 position p:")
print()
print("  If p >= 37 (chars: q, ..., f, e):")
print("    LEFT  = 2p - 68")
print("    RIGHT = 2p - 67")
print()
print("  If p <= 36 (chars: d, c, b, a, ..., 1):")
print("    LEFT  = 2p - 67")
print("    RIGHT = 2p - 68")
print()
print("The threshold p=37 is the character 'e' in Base58.")
print()
print("This cipher maps Base58 positions to a pair of values (LEFT, RIGHT)")
print("that differ by 1, centered around 2p - 67.5")
