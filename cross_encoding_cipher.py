#!/usr/bin/env python3
"""Cross-encoding cipher between Base58 and bech32.

The user's pattern reveals a mapping between the two alphabets:
  0=q=1      → bech32 'q'=0, Base58 '1'=0  (both represent zero)
  8=f=9      → bech32 'f'=9, Base58 'A'=9  (both represent nine)
  6=e=7      → bech32 'e'=6, Base58 '7'=6
  5=d=4      → bech32 'd'=5, Base58 '4'=5
  3=c=2      → bech32 'c'=3, Base58 '2'=3
  1=b=0      → bech32 'b'=1, Base58 '0' doesn't exist... 
  -1=a=-1    → bech32 'a'=-1? Base58 'a'=-1?

The pattern: the middle number is the shared value.
  bech32_char = value = Base58_char

Let's decode:
  0=q=1  → value 0: bech32 'q', Base58 '1' ✓
  8=f=9  → This doesn't fit: bech32 'f'=9, Base58 '9'=8
  6=e=7  → bech32 'e'=6, Base58 '7'=6 ✓
  5=d=4  → bech32 'd'=5, Base58 '4'=5 ✓
  3=c=2  → bech32 'c'=3, Base58 '2'=3 ✓
  1=b=0  → bech32 'b'=1, but Base58 has no '0'... 
  -1=a=-1 → bech32 'a'=-1? No...

Wait — let's look at it differently. The format is:
  Base58_value = bech32_char = Base58_char

  0=q=1 → Base58 value 0 = '1', bech32 value 0 = 'q' ✓
  8=f=9 → Base58 value 8 = '9', bech32 value 9 = 'f'... 
    But Base58 '9' = 8, bech32 'f' = 9. The values are off by 1!

Or the format is:
  bech32_value = bech32_char = Base58_value

  0=q=1 → bech32 'q'=0, Base58 '1'=0 ✓ (same value 0)
  8=f=9 → bech32 'f'=9, Base58 '9'=8... values are 9 and 8, not equal!

Let me try: the middle is the bech32 char, left is bech32 value, right is Base58 char:
  0=q=1 → bech32 value 0 = 'q', Base58 char '1' (value 0) ✓
  8=f=9 → bech32 value 8 = 'g', not 'f'! ✗

Or: left is Base58 value, middle is bech32 char, right is bech32 value:
  0=q=1 → Base58 value 0 = '1', bech32 'q' = 0... right side is 1, not 0 ✗

Let me look at the actual alphabets:
  Base58:  123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz
  bech32:  qpzry9x8gf2tvdw0s3jn54khce6mua7l

Position-by-position mapping (same index in both alphabets):
  Index 0: Base58 '1' ↔ bech32 'q' (both value 0)
  Index 1: Base58 '2' ↔ bech32 'p' (both value 1)
  Index 2: Base58 '3' ↔ bech32 'z' (both value 2)
  ...
  Index 8: Base58 '9' ↔ bech32 'g' (both value 8)
  Index 9: Base58 'A' ↔ bech32 'f' (both value 9)

Now the user's pattern:
  0=q=1 → Index 0: bech32 'q', Base58 '1' ✓
  8=f=9 → This is NOT index 8 or 9... 
    bech32 'f' is at index 9, Base58 '9' is at index 8
    So 8=f=9 means: Base58 index 8 ('9'), bech32 char 'f' (index 9), Base58 index 9 ('A')?

Wait — what if the user is showing the REVERSED mapping?
  bech32 alphabet: qpzry9x8gf2tvdw0s3jn54khce6mua7l
  If we reverse it: lamu6ec4h5nj3s0wdv2tfg8x9yrzp q

Let me check the user's specific characters:
  q, f, e, d, c, b, a in bech32
  q=0, f=9, e=20, d=23, c=24, b=27, a=29

  1, 9, 7, 4, 2, 0 in Base58 (but 0 doesn't exist in Base58)
  1=0, 9=8, 7=6, 4=3, 2=1, 0=doesn't exist

The user's pattern:
  0=q=1 → bech32 'q'=0, Base58 '1'=0
  8=f=9 → bech32 'f'=9, Base58 '9'=8
  6=e=7 → bech32 'e'=20, Base58 '7'=6... No!

Let me try bech32 'e':
  qpzry9x8gf2tvdw0s3jn54khce6mua7l
  0123456789...
  e is at position... q(0)p(1)z(2)r(3)y(4)9(5)x(6)8(7)g(8)f(9)2(10)t(11)v(12)d(13)w(14)0(15)s(16)3(17)j(18)n(19)5(20)4(21)k(22)h(23)c(24)e(25)6(26)m(27)u(28)a(29)7(30)l(31)
  
  So bech32 'e' = 25, not 6!

The user wrote `6=e=7`. If bech32 'e'=25, this doesn't match.

UNLESS... the user is using a DIFFERENT bech32 alphabet or a transformed version.

What if the user is showing the BASE58 values that map to bech32 characters?
  0=q=1 → bech32 'q' has value 0, Base58 '1' has value 0 ✓
  8=f=9 → bech32 'f' has value 9, Base58 '9' has value 8
    The values are swapped: 8 and 9!
  6=e=7 → bech32 'e' has value 25, Base58 '7' has value 6
    25 ≠ 6, but 6 and 7 are close...

What if it's a REVERSED bech32 alphabet?
  Reversed: lamu6ec4h5nj3s0wdv2tfg8x9yrzp q
  Position: 0123456789...
  In reversed: 'a'=3, 'b' doesn't exist in bech32...

OK, let me just look at what the user literally wrote and find the pattern:
  0=q=1
  8=f=9
  6=e=7
  5=d=4
  3=c=2
  1=b=0
  -1=a=-1

Left column: 0, 8, 6, 5, 3, 1, -1
Middle: q, f, e, d, c, b, a (these are bech32 chars in reverse alphabetical order!)
Right column: 1, 9, 7, 4, 2, 0, -1

The middle is clearly: q, f, e, d, c, b, a
These are NOT in bech32 alphabet order, but they are in reverse alphabetical order.

bech32 values:
  q = 0
  f = 9
  e = 25
  d = 13
  c = 24
  b = 27 (wait, 'b' is not in bech32!)

Actually, 'b' is NOT in the bech32 alphabet qpzry9x8gf2tvdw0s3jn54khce6mua7l.
The bech32 alphabet deliberately excludes 'b', 'i', 'o' to avoid confusion.

So the user's pattern includes 'b' and 'a':
  'a' IS in bech32 (value 29)
  'b' is NOT in bech32

This suggests the user is creating a NEW cipher that extends beyond standard bech32.

The pattern in the middle: q, f, e, d, c, b, a
If we continue: q, f, e, d, c, b, a, Z, Y, X, ...

The left and right columns:
  Left:  0, 8, 6, 5, 3, 1, -1
  Right: 1, 9, 7, 4, 2, 0, -1

Differences (right - left):
  1-0=1, 9-8=1, 7-6=1, 4-5=-1, 2-3=-1, 0-1=-1, -1-(-1)=0

Hmm, not consistent.

Let me look at it as pairs:
  (0, 1) → q
  (8, 9) → f
  (6, 7) → e
  (5, 4) → d
  (3, 2) → c
  (1, 0) → b
  (-1, -1) → a

For the first three: right = left + 1
For the next three: right = left - 1
For the last: right = left

The middle characters q, f, e, d, c, b, a — if we look at their positions:
  In the bech32 alphabet: q=0, f=9, e=25, d=13, c=24
  'b' is not in bech32
  'a' = 29 in bech32

None of these form a clear sequence in bech32 values.

BUT — what if we look at the BASE58 alphabet positions?
  Base58: 123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz
  'q' is at position 48 in Base58
  'f' is at position 38 in Base58
  'e' is at position 37 in Base58
  'd' is at position 36 in Base58
  'c' is at position 35 in Base58
  'b' is at position 34 in Base58
  'a' is at position 33 in Base58

So in Base58: q=48, f=38, e=37, d=36, c=35, b=34, a=33

The sequence f, e, d, c, b, a is consecutive in Base58 (38, 37, 36, 35, 34, 33) — counting DOWN!
'q' at 48 breaks the pattern.

Now the left and right columns with Base58 values:
  q(48): left=0, right=1
  f(38): left=8, right=9
  e(37): left=6, right=7
  d(36): left=5, right=4
  c(35): left=3, right=2
  b(34): left=1, right=0
  a(33): left=-1, right=-1

Left column: 0, 8, 6, 5, 3, 1, -1
Right column: 1, 9, 7, 4, 2, 0, -1

For f, e, d, c, b, a (Base58 positions 38, 37, 36, 35, 34, 33):
  Left: 8, 6, 5, 3, 1, -1
  Right: 9, 7, 4, 2, 0, -1

Right - Left for each:
  f: 9-8=1
  e: 7-6=1
  d: 4-5=-1
  c: 2-3=-1
  b: 0-1=-1
  a: -1-(-1)=0

The left column for f,a sequence: 8, 6, 5, 3, 1, -1
Differences: 8-6=2, 6-5=1, 5-3=2, 3-1=2, 1-(-1)=2

The right column: 9, 7, 4, 2, 0, -1
Differences: 9-7=2, 7-4=3, 4-2=2, 2-0=2, 0-(-1)=1

This is getting complex. Let me just create the cipher mapping the user described.
"""

# ---------------------------------------------------------------- Alphabets
BASE58_ALPHABET = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'
BECH32_ALPHABET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"

# ---------------------------------------------------------------- User's cipher pattern
# The user provided:
#   0=q=1
#   8=f=9
#   6=e=7
#   5=d=4
#   3=c=2
#   1=b=0
#   -1=a=-1

user_cipher = {
    'q': (0, '1', 1),    # bech32 'q'=0, Base58 '1'=0 → but user wrote 0=q=1
    'f': (8, '9', 9),    # user wrote 8=f=9
    'e': (6, '7', 7),    # user wrote 6=e=7
    'd': (5, '4', 4),    # user wrote 5=d=4
    'c': (3, '2', 2),    # user wrote 3=c=2
    'b': (1, '0', 0),    # user wrote 1=b=0 (but '0' not in Base58)
    'a': (-1, None, -1), # user wrote -1=a=-1
}

def analyze_cipher():
    print("=" * 80)
    print("CROSS-ENCODING CIPHER ANALYSIS")
    print("=" * 80)
    print()
    print("User's pattern:")
    print("  0=q=1")
    print("  8=f=9")
    print("  6=e=7")
    print("  5=d=4")
    print("  3=c=2")
    print("  1=b=0")
    print("  -1=a=-1")
    print()
    
    # Standard bech32 values
    print("Standard bech32 values:")
    for char in 'qfedcba':
        if char in BECH32_ALPHABET:
            print(f"  bech32 '{char}' = {BECH32_ALPHABET.index(char)}")
        else:
            print(f"  bech32 '{char}' = NOT IN ALPHABET")
    print()
    
    # Standard Base58 values
    print("Standard Base58 values:")
    for char in 'qfedcba197420':
        if char in BASE58_ALPHABET:
            print(f"  Base58 '{char}' = {BASE58_ALPHABET.index(char)}")
        else:
            print(f"  Base58 '{char}' = NOT IN ALPHABET ('0' not in Base58)")
    print()
    
    # Base58 positions of bech32 chars
    print("Base58 positions of bech32 characters:")
    for char in 'qfedcba':
        if char in BASE58_ALPHABET:
            print(f"  '{char}' at Base58 position {BASE58_ALPHABET.index(char)}")
    print()
    
    # The pattern: f,e,d,c,b,a are consecutive in Base58 (38,37,36,35,34,33)
    print("Key insight: f,e,d,c,b,a are CONSECUTIVE in Base58 (counting down):")
    for char in 'fedcba':
        if char in BASE58_ALPHABET:
            print(f"  '{char}' = Base58 position {BASE58_ALPHABET.index(char)}")
    print()
    
    # Decode the user's cipher
    print("=" * 80)
    print("DECODING THE CIPHER")
    print("=" * 80)
    print()
    print("Format: LEFT=bech32_char=RIGHT")
    print()
    print("If LEFT = bech32 value and RIGHT = Base58 value:")
    print("  0=q=1 => bech32 'q'=0 OK, Base58 '1'=0 OK => MATCH (both value 0)")
    print("  8=f=9 => bech32 'f'=9, not 8 X | Base58 '9'=8 OK")
    print("  6=e=7 => bech32 'e'=25, not 6 X | Base58 '7'=6 OK")
    print()
    print("If LEFT = Base58 value and RIGHT = bech32 value:")
    print("  0=q=1 => Base58 'q'=48, not 0 X | bech32 'q'=0 OK")
    print("  8=f=9 => Base58 'f'=38, not 8 X | bech32 'f'=9 OK")
    print()
    print("MIXED: LEFT = Base58 value of RIGHT char, RIGHT = bech32 value of middle char:")
    print("  0=q=1 => Base58 '1'=0 OK, bech32 'q'=0 OK => SAME VALUE 0")
    print("  8=f=9 => Base58 '9'=8 OK, bech32 'f'=9 OK => VALUES 8 AND 9")
    print("  6=e=7 => Base58 '7'=6 OK, bech32 'e'=25 X => bech32 'e'!=7")
    print()
    
    # What if the right column is NOT the Base58 char but a value?
    print("NEW HYPOTHESIS: Format is VALUE=bech32_char=BASE58_CHAR")
    print("  0=q=1 => value 0 = bech32 'q' OK, Base58 '1' (value 0) OK")
    print("  8=f=9 => value 8 = bech32 'g', not 'f' X")
    print()
    
    print("NEW HYPOTHESIS: Format is BECH32_VALUE=bech32_char=BASE58_CHAR")
    print("  0=q=1 => bech32 'q'=0 OK, Base58 '1'=0 OK => SAME VALUE")
    print("  8=f=9 => bech32 'f'=9, not 8 X")
    print()
    
    # The answer must be simpler
    print("=" * 80)
    print("SIMPLEST INTERPRETATION")
    print("=" * 80)
    print()
    print("The user is mapping bech32 chars to Base58 chars by their VALUES.")
    print("The format is: bech32_value = bech32_char ~ Base58_char with same value")
    print()
    print("  0=q=1 => bech32 'q'=0, Base58 '1'=0 => Both represent 0 OK")
    print("  8=f=9 => This breaks: bech32 'f'=9, Base58 '9'=8")
    print("           The values are SWAPPED: 8<->9")
    print()
    print("SWAP PATTERN detected:")
    print("  0=q=1 => values (0,0) — no swap")
    print("  8=f=9 => values (8,9) — swapped from (9,8)?")
    print("  6=e=7 => values (6,7) — but bech32 'e'=25, not related to 6 or 7")
    print()
    
    # Final attempt: what if bech32 values are being remapped?
    print("=" * 80)
    print("REVERSED BECH32 ALPHABET TEST")
    print("=" * 80)
    reversed_bech32 = BECH32_ALPHABET[::-1]
    print(f"Reversed bech32: {reversed_bech32}")
    print()
    for char in 'qfedcba':
        if char in reversed_bech32:
            print(f"  '{char}' at reversed position {reversed_bech32.index(char)}")
    
    print()
    print("=" * 80)
    print("THE BREAKTHROUGH: f,e,d,c,b,a CONSECUTIVE IN BASE58")
    print("=" * 80)
    print()
    print("In Base58, these characters are at consecutive positions:")
    print("  f=38, e=37, d=36, c=35, b=34, a=33")
    print()
    print("The user's cipher values for these:")
    print("  f: left=8, right=9")
    print("  e: left=6, right=7")
    print("  d: left=5, right=4")
    print("  c: left=3, right=2")
    print("  b: left=1, right=0")
    print("  a: left=-1, right=-1")
    print()
    print("Left column: 8, 6, 5, 3, 1, -1")
    print("Right column: 9, 7, 4, 2, 0, -1")
    print()
    print("These look like they could be related to the Base58 positions")
    print("through some transformation (mod operations, bit shifts, etc.)")
    print()
    
    # Check mod operations
    print("CHECKING MOD OPERATIONS:")
    print("=" * 80)
    for char, left, right in [('f', 8, 9), ('e', 6, 7), ('d', 5, 4), ('c', 3, 2), ('b', 1, 0), ('a', -1, -1)]:
        b58_pos = BASE58_ALPHABET.index(char)
        print(f"  {char}: Base58 pos {b58_pos}")
        print(f"    {b58_pos} mod 10 = {b58_pos % 10}")
        print(f"    {b58_pos} mod 8  = {b58_pos % 8}")
        print(f"    {b58_pos} mod 7  = {b58_pos % 7}")
        print(f"    {b58_pos} mod 6  = {b58_pos % 6}")
        print(f"    {b58_pos} mod 5  = {b58_pos % 5}")
        print(f"    User: left={left}, right={right}")
        print()
    
    print("=" * 80)
    print("CONCLUSION")
    print("=" * 80)
    print()
    print("The cipher maps characters where the LEFT and RIGHT values are")
    print("RELATED but not identical. The pattern f,e,d,c,b,a being consecutive")
    print("in Base58 (38,37,36,35,34,33) is the key.")
    print()
    print("The user's 'or something like that' suggests this is an APPROXIMATE")
    print("cipher — a starting point for encoding/decoding between the systems.")

if __name__ == '__main__':
    analyze_cipher()
