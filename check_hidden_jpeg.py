#!/usr/bin/env python3
"""Analyze the hidden JPEG files to understand their structure."""

import struct

def analyze_jpeg(filepath):
    print(f"\n{'='*60}")
    print(f"Analyzing: {filepath}")
    print(f"{'='*60}")
    
    with open(filepath, 'rb') as f:
        data = f.read()
    
    print(f"File size: {len(data)} bytes")
    print(f"First 20 bytes hex: {data[:20].hex()}")
    
    # Check for SOI marker
    has_soi = data[:2] == b'\xff\xd8'
    print(f"Has SOI marker (FFD8): {has_soi}")
    
    # Check for double SOI
    has_double_soi = data[:4] == b'\xff\xd8\xff\xd8'
    print(f"Has double SOI: {has_double_soi}")
    
    # Find all JPEG markers
    markers = []
    i = 2  # Skip SOI
    while i < len(data) - 1:
        if data[i] == 0xff:
            marker = data[i + 1]
            if marker != 0xff and marker != 0x00:  # Not stuffing
                if marker in [0xc0, 0xc2, 0xdb, 0xc4, 0xda, 0xd9, 0xe0, 0xe1, 0xed, 0xc3, 0xc1]:
                    name = {
                        0xc0: "SOF0 (Baseline)",
                        0xc2: "SOF2 (Progressive)",
                        0xc3: "SOF3 (Lossless)",
                        0xdb: "DQT (Quantization)",
                        0xc4: "DHT (Huffman)",
                        0xda: "SOS (Start Scan)",
                        0xd9: "EOI (End)",
                        0xe0: "APP0 (JFIF)",
                        0xe1: "APP1 (Exif)",
                        0xed: "APP13",
                        0xc1: "SOF1"
                    }.get(marker, f"0x{marker:02x}")
                    markers.append((i, name, marker))
                i += 2
            else:
                i += 1
        else:
            i += 1
    
    print(f"\nJPEG markers found: {len(markers)}")
    for offset, name, marker in markers:
        print(f"  Offset {offset:6d}: {name}")
    
    # Check for EOI marker at end
    has_eoi = data[-2:] == b'\xff\xd9'
    print(f"\nHas EOI marker at end: {has_eoi}")
    
    # Look for data after EOI
    eoi_pos = data.find(b'\xff\xd9')
    if eoi_pos >= 0:
        after_eoi = len(data) - eoi_pos - 2
        print(f"Bytes after EOI: {after_eoi}")
        if after_eoi > 0:
            print(f"  First 64 bytes after EOI: {data[eoi_pos+2:eoi_pos+66].hex()}")
    
    # Try to read SOF0 for image dimensions
    for offset, name, marker in markers:
        if marker == 0xc0 or marker == 0xc2:  # SOF0 or SOF2
            if offset + 10 <= len(data):
                length = struct.unpack('>H', data[offset+2:offset+4])[0]
                precision = data[offset+4]
                height = struct.unpack('>H', data[offset+5:offset+7])[0]
                width = struct.unpack('>H', data[offset+7:offset+9])[0]
                components = data[offset+9]
                print(f"\nImage dimensions: {width}x{height}, {components} components, {precision}-bit precision")
    
    # Check for Exif data
    for offset, name, marker in markers:
        if marker == 0xe1:  # APP1
            if offset + 6 <= len(data):
                app1_data = data[offset+2:offset+14]
                if app1_data[:6] == b'Exif\x00\x00':
                    print(f"\nFound Exif data at offset {offset}")
                    # Try to read some Exif tags
                    exif_start = offset + 14
                    if exif_start + 8 <= len(data):
                        endian = data[exif_start:exif_start+2]
                        if endian == b'MM':  # Big endian
                            print("  Endianness: Big endian (Motorola)")
                        elif endian == b'II':  # Little endian
                            print("  Endianness: Little endian (Intel)")
    
    return data

# Analyze all three files
files = ['hidden_image.jpeg', 'hidden_reconstructed2.jpeg', 'hidden_with_soi.jpeg']
for f in files:
    try:
        analyze_jpeg(f)
    except FileNotFoundError:
        print(f"File not found: {f}")

# Compare the files
print(f"\n{'='*60}")
print("File Comparison")
print(f"{'='*60}")

data1 = open('hidden_image.jpeg', 'rb').read()
data2 = open('hidden_reconstructed2.jpeg', 'rb').read()
data3 = open('hidden_with_soi.jpeg', 'rb').read()

print(f"hidden_image.jpeg: {len(data1)} bytes")
print(f"hidden_reconstructed2.jpeg: {len(data2)} bytes")
print(f"hidden_with_soi.jpeg: {len(data3)} bytes")

# Check if hidden_with_soi is same as hidden_image
if data1 == data3:
    print("\nhidden_with_soi.jpeg is identical to hidden_image.jpeg")

# Find differences between hidden_image and hidden_reconstructed2
if data1 != data2:
    print(f"\nhidden_image and hidden_reconstructed2 differ:")
    min_len = min(len(data1), len(data2))
    diffs = []
    for i in range(min_len):
        if data1[i] != data2[i]:
            diffs.append(i)
    
    if len(data1) != len(data2):
        print(f"  Different lengths: {len(data1)} vs {len(data2)}")
    
    print(f"  {len(diffs)} byte differences in first {min_len} bytes")
    if diffs:
        print(f"  First difference at offset: {diffs[0]}")
        print(f"  Last difference at offset: {diffs[-1]}")
