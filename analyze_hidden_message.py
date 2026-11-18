#!/usr/bin/env python3
"""Analyze the XOR encoding and look for hidden messages in the JPEG files."""

import hashlib
import struct

def analyze_xor_pattern():
    """Analyze the XOR pattern between hidden_image and a valid JPEG."""
    print("="*60)
    print("XOR Pattern Analysis")
    print("="*60)
    
    with open('hidden_image.jpeg', 'rb') as f:
        hidden = f.read()
    
    with open('hidden_reconstructed2.jpeg', 'rb') as f:
        reconstructed = f.read()
    
    # The hidden file starts with 0x0000, should be 0xFFD8
    # XOR key for first 2 bytes: 0x00 ^ 0xFF = 0xFF, 0x00 ^ 0xD8 = 0xD8
    print(f"Hidden first 20 bytes:   {hidden[:20].hex()}")
    print(f"Reconstructed first 20:  {reconstructed[:20].hex()}")
    
    # XOR the first 20 bytes
    xor_bytes = bytes(a ^ b for a, b in zip(hidden[:20], reconstructed[:20]))
    print(f"XOR of first 20 bytes:   {xor_bytes.hex()}")
    
    # Check if it's a simple single-byte XOR
    print(f"\nChecking for single-byte XOR pattern...")
    for key in range(256):
        # Check first 10 bytes
        match = True
        for i in range(min(10, len(hidden))):
            if hidden[i] ^ key != reconstructed[i]:
                match = False
                break
        if match:
            print(f"  Single-byte XOR key: 0x{key:02x}")
            break
    else:
        print("  No single-byte XOR key found")
    
    # Check if it's a repeating XOR key
    print(f"\nChecking for repeating XOR key...")
    for key_len in range(1, 33):
        key = bytes(hidden[i] ^ reconstructed[i] for i in range(key_len))
        match = True
        for i in range(min(100, len(hidden))):
            if hidden[i] ^ key[i % key_len] != reconstructed[i]:
                match = False
                break
        if match:
            print(f"  Repeating XOR key length {key_len}: {key.hex()}")
            # Try to decode the key as text
            try:
                text = key.decode('ascii')
                if all(32 <= b <= 126 for b in key):
                    print(f"  Key as ASCII: '{text}'")
            except:
                pass
            break
    
    # Since the files are completely different, let's look at the structure
    print(f"\nNote: The files are completely different (different JPEG structure)")
    print(f"  hidden_image: Progressive JPEG (SOF2), 24 markers")
    print(f"  reconstructed: Baseline JPEG (SOF0), 10 markers")
    print(f"  They are not simple XOR encryptions of each other")
    
    return hidden, reconstructed

def check_for_steganography():
    """Check for steganographic data in the reconstructed image."""
    print(f"\n{'='*60}")
    print("Steganography Analysis")
    print(f"{'='*60}")
    
    with open('hidden_reconstructed2.jpeg', 'rb') as f:
        data = f.read()
    
    # Look for data after EOI
    eoi_pos = data.find(b'\xff\xd9')
    if eoi_pos >= 0:
        after_eoi = data[eoi_pos+2:]
        print(f"Bytes after EOI marker: {len(after_eoi)}")
        if len(after_eoi) > 0:
            print(f"  Data: {after_eoi[:100].hex()}")
            # Try to decode as text
            try:
                text = after_eoi.decode('utf-8')
                print(f"  As UTF-8: {text[:200]}")
            except:
                pass
    else:
        print("No EOI marker found")
    
    # Check for hidden data in comment markers (0xFFFE)
    i = 0
    while i < len(data) - 1:
        if data[i] == 0xff and data[i+1] == 0xfe:  # COM marker
            if i + 4 <= len(data):
                length = struct.unpack('>H', data[i+2:i+4])[0]
                if i + 4 + length <= len(data):
                    comment = data[i+4:i+4+length]
                    print(f"\nComment marker at offset {i}:")
                    try:
                        text = comment.decode('utf-8')
                        print(f"  Text: {text[:200]}")
                    except:
                        print(f"  Hex: {comment[:100].hex()}")
        i += 1
    
    # Check for hidden data in APPn markers
    print(f"\nChecking APPn markers for hidden data...")
    i = 0
    while i < len(data) - 3:
        if data[i] == 0xff and 0xe0 <= data[i+1] <= 0xef:
            app_num = data[i+1] - 0xe0
            length = struct.unpack('>H', data[i+2:i+4])[0]
            if i + 4 + length <= len(data):
                app_data = data[i+4:i+4+length]
                # Check for non-standard APP data
                if app_num == 0:  # JFIF
                    print(f"APP0 (JFIF) at offset {i}: {app_data[:20]}")
                elif app_num == 1:  # Exif
                    print(f"APP1 (Exif) at offset {i}: {length} bytes")
                    # Check for unusual Exif data
                    if length > 1000:
                        print(f"  Warning: Unusually large Exif data")
                else:
                    print(f"APP{app_num} at offset {i}: {length} bytes")
                    # Try to show first few bytes
                    try:
                        text = app_data[:50].decode('utf-8')
                        if all(32 <= ord(c) <= 126 or c in '\n\r\t' for c in text):
                            print(f"  Text: {text}")
                    except:
                        print(f"  Hex: {app_data[:50].hex()}")
        i += 1
    
    # Check LSB steganography in image data
    print(f"\nChecking LSB (Least Significant Bit) steganography...")
    # Extract SOS segment (image data)
    sos_pos = data.find(b'\xff\xda')
    eoi_pos = data.find(b'\xff\xd9')
    if sos_pos >= 0 and eoi_pos >= 0:
        sos_data = data[sos_pos+2:eoi_pos]
        print(f"SOS segment size: {len(sos_data)} bytes")
        
        # Extract LSBs
        lsb_bits = ''.join(str(b & 1) for b in sos_data[:1000])  # First 1000 bytes
        lsb_bytes = bytes(int(lsb_bits[i:i+8], 2) for i in range(0, len(lsb_bits)-7, 8))
        
        # Check if LSBs contain readable text
        printable = sum(1 for b in lsb_bytes if 32 <= b <= 126)
        print(f"LSB first 100 bytes: {lsb_bytes[:100]}")
        print(f"Printable chars in first 100 LSB bytes: {printable}/{len(lsb_bytes[:100])}")
        
        if printable > len(lsb_bytes[:100]) * 0.7:
            print("  Possible LSB steganography detected!")
            print(f"  Text: {lsb_bytes[:100]}")

def check_hidden_image_structure():
    """Check the original hidden_image.jpeg for clues."""
    print(f"\n{'='*60}")
    print("Original Hidden Image Analysis")
    print(f"{'='*60}")
    
    with open('hidden_image.jpeg', 'rb') as f:
        data = f.read()
    
    # The file starts with 0x0000 instead of 0xFFD8
    # This could be:
    # 1. XOR with 0xFFD8 (but files are different structure)
    # 2. Intentional corruption
    # 3. Part of a puzzle
    
    # Check if adding SOI makes it valid
    with_soi = b'\xff\xd8' + data
    print(f"Adding SOI marker creates {len(with_soi)} byte file")
    
    # Check the SHA256 mentioned in the issue
    sha256 = hashlib.sha256(data).hexdigest()
    print(f"SHA256 of hidden_image.jpeg: {sha256}")
    
    # The issue mentions: ea7f07291b213cc488618d00174b7333226903edec29d5be322259a86eea6da8
    expected_sha = "ea7f07291b213cc488618d00174b7333226903edec29d5be322259a86eea6da8"
    if sha256 == expected_sha:
        print("SHA256 matches the hash in the issue!")
    else:
        print(f"SHA256 does not match expected: {expected_sha}")
    
    # Check the first 64 bytes mentioned
    print(f"\nFirst 64 bytes hex: {data[:64].hex()}")
    print(f"First 128 bytes hex: {data[:128].hex()}")
    
    # The hex starts with 0000ffdb0043000503040404030504040405050506070c08070707070f0b0b09
    # This is a DQT marker (0xFFDB) at offset 2
    # The 0x0000 at the start is likely intentional - part of the puzzle

if __name__ == '__main__':
    analyze_xor_pattern()
    check_for_steganography()
    check_hidden_image_structure()
