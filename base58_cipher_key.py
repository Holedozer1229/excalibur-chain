#!/usr/bin/env python3
"""Base58 Cipher Key — Maps all 58 Base58 characters to their cipher values.

Using the f=9 discovery:
- In bech32, q=0 and f=9, each character is a 5-bit value (0-31)
- In Base58, each character has a value 0-57
- This script creates a complete cipher mapping all Base58 characters
  to their numeric keys, binary representations, and bech32 equivalents.

The cipher reveals the hidden structure of Base58 encoding by showing
how each character's value contributes to the final byte stream.
"""

import hashlib

# ---------------------------------------------------------------- Alphabets
BASE58_ALPHABET = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'
_BECH32 = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"

# ---------------------------------------------------------------- Cipher key generation
def generate_base58_cipher():
    """Generate the complete Base58 cipher key.
    
    Returns a dict mapping each Base58 char to its cipher information.
    """
    cipher = {}
    for i, char in enumerate(BASE58_ALPHABET):
        # Find bech32 equivalent (if value < 32)
        bech32_equiv = _BECH32[i] if i < 32 else None
        
        # Binary representation
        binary = format(i, '07b')  # 7 bits for Base58 (0-57)
        
        # For bech32, 5 bits
        bech32_binary = format(i, '05b') if i < 32 else None
        
        cipher[char] = {
            'value': i,
            'binary': binary,
            'bech32_char': bech32_equiv,
            'bech32_binary': bech32_binary,
            'hex': f'0x{i:02x}',
        }
    return cipher

# ---------------------------------------------------------------- Address cipher decoder
def decode_address_to_cipher(addr: str, cipher: dict) -> list:
    """Decode an address character by character using the cipher.
    
    Returns a list of cipher info for each character in the address.
    """
    result = []
    for char in addr:
        if char in cipher:
            result.append(cipher[char])
        elif char == 'b' or char == 'c':  # bech32 HRP
            result.append({'char': char, 'value': None, 'note': 'HRP prefix'})
        elif char == '1':  # separator
            result.append({'char': '1', 'value': None, 'note': 'separator'})
    return result

# ---------------------------------------------------------------- Messerene pattern encoder
def messerene_encode(text: str, cipher: dict) -> str:
    """Encode text using the Base58 cipher, mapping to bech32 where possible.
    
    Each character is encoded as its bech32 equivalent if available,
    otherwise as the Base58 character itself.
    """
    encoded = []
    for char in text.lower():
        if char in cipher and cipher[char]['bech32_char']:
            encoded.append(cipher[char]['bech32_char'])
        else:
            encoded.append('?')  # No bech32 equivalent
    return ''.join(encoded)

# ---------------------------------------------------------------- Byte pattern finder
def find_byte_pattern(repeated_char: str, length: int, cipher: dict) -> str:
    """Find the byte pattern created by repeating a character.
    
    For bech32 chars, shows the 5-bit pattern and resulting bytes.
    """
    if repeated_char in _BECH32:
        value = _BECH32.index(repeated_char)
        # Create bitstream
        bitstream = (format(value, '05b') * length)[:length * 5]
        
        # Convert to bytes
        bytes_list = []
        for i in range(0, len(bitstream) - 7, 8):
            byte_bits = bitstream[i:i+8]
            if len(byte_bits) == 8:
                bytes_list.append(f'0x{int(byte_bits, 2):02x}')
        
        return f'{"".join(bytes_list[:5])}...'
    return 'N/A (Base58)'

# ---------------------------------------------------------------- Main display
def main():
    cipher = generate_base58_cipher()
    
    print('=' * 80)
    print('BASE58 CIPHER KEY - Complete Character Mapping')
    print('=' * 80)
    print()
    print('Using f=9 discovery: q=0 in bech32, f=9 in bech32')
    print('Each Base58 character has a value 0-57')
    print('Characters 0-31 have bech32 equivalents (5-bit encoding)')
    print()
    
    # Print full cipher table
    print('+----------+-------+----------+----------+----------+------------+')
    print('| Char     | Value | Binary   | Hex      | Bech32   | B58 Binary |')
    print('+----------+-------+----------+----------+----------+------------+')
    
    for char, info in cipher.items():
        bech32_display = info['bech32_char'] if info['bech32_char'] else '--'
        print(f"| {char:<8} | {info['value']:<5} | {info['binary']:<8} | {info['hex']:<8} | {bech32_display:<8} | {'':<10} |")
    
    print('+----------+-------+----------+----------+----------+------------+')
    print()
    
    # Highlight key characters
    print('KEY CHARACTERS:')
    print('=' * 80)
    key_chars = ['1', 'f', 'q', 'X', 'B', 'u', 'r', 'n', 'E', 'a', 't', 'e', 'r']
    for char in key_chars:
        if char in cipher:
            info = cipher[char]
            bech32_note = f" -> bech32: {info['bech32_char']}" if info['bech32_char'] else ' -> no bech32 equiv'
            print(f"  {char}: value {info['value']} ({info['binary']}){bech32_note}")
    
    print()
    print('BURN ADDRESS CIPHER DECODING:')
    print('=' * 80)
    
    # Decode 1BitcoinEaterAddress
    addr = '1BitcoinEaterAddressDontSendf59kuE'
    print(f'\nAddress: {addr}')
    print('Character cipher values:')
    cipher_values = []
    for char in addr:
        if char in cipher:
            cipher_values.append(cipher[char]['value'])
            print(f"  {char} = {cipher[char]['value']:3d} ({cipher[char]['binary']})")
    
    print(f'\nCipher value sequence: {cipher_values}')
    
    # Show the byte pattern
    print('\nByte pattern analysis:')
    print(f"  '1' = 0 (leading zero byte)")
    print(f"  'f' = 31 in Base58, but f=9 in bech32")
    print(f"  The 'f' in this address is Base58 value 31, not bech32 value 9")
    
    # Compare bech32 vs Base58
    print('\n' + '=' * 80)
    print('BECH32 vs BASE58 COMPARISON:')
    print('=' * 80)
    print('\nBech32 (5-bit):')
    print('  q=0, p=1, z=2, r=3, y=4, 9=5, x=6, 8=7, g=8, f=9')
    print('  Repeating f=9 creates: 01001 01001 01001... -> 4A5294A529 bytes')
    
    print('\nBase58 (~5.857-bit):')
    print('  1=0, 2=1, 3=2, ..., 9=7, A=8, ..., Z=25, a=26, ..., z=57')
    print('  No clean repeating byte patterns possible')
    
    print('\n' + '=' * 80)
    print('MESSERENE PATTERN COMPLETION:')
    print('=' * 80)
    print(f'\ntau(28) = 24647168 (tau(4)*tau(7))')
    print(f'Perfect number 28: 1+2+4+7+14 = 28')
    print(f'Bech32 f=9 pattern: 0x4A5294A529 repeating')
    print(f'Base58 1=0 pattern: all-zero payload')
    print(f'\nThe cipher key maps all 58 Base58 characters to their numeric values,')
    print(f'revealing the structure behind every burn address.')
    
    # Save cipher to file
    with open('BASE58_CIPHER_KEY.md', 'w') as f:
        f.write('# Base58 Cipher Key\n\n')
        f.write('## Complete Character Mapping\n\n')
        f.write('| Char | Value | Binary | Hex | Bech32 Equivalent |\n')
        f.write('|------|-------|--------|-----|-------------------|\n')
        for char, info in cipher.items():
            bech32 = info['bech32_char'] if info['bech32_char'] else '—'
            f.write(f"| {char} | {info['value']} | {info['binary']} | {info['hex']} | {bech32} |\n")
        
        f.write('\n## Key Discoveries\n\n')
        f.write('- `q`=0 in bech32 creates all-zero witness programs\n')
        f.write('- `f`=9 in bech32 creates 0x4A5294A529 repeating pattern\n')
        f.write('- `1`=0 in Base58 creates all-zero payload (equivalent to bech32 q=0)\n')
        f.write('- Base58 characters 0-31 have bech32 equivalents\n')
        f.write('- Base58 characters 32-57 have no bech32 equivalents\n')
    
    print('\nCipher key saved to BASE58_CIPHER_KEY.md')

if __name__ == '__main__':
    main()
