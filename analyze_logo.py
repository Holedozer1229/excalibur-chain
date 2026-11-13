from PIL import Image
import numpy as np

# Open the hidden image
img = Image.open('hidden_reconstructed2.jpeg').convert('L')
arr = np.array(img)

# Threshold to pure black/white
binary = (arr < 128).astype(np.uint8)

# The logo has distinct elements:
# - A star (6-pointed)
# - A sword in the center
# - A flame on the left
# - Circuit-like border
# - Chain links at the bottom

# Try reading the image as a grid of cells
# Each cell could represent a bit (black=1, white=0)

# Divide into 32x32 grid (1024/32 = 32 cells per side)
cell_size = 32
grid_h = arr.shape[0] // cell_size
grid_w = arr.shape[1] // cell_size
print(f'Grid: {grid_w}x{grid_h} cells')

grid = np.zeros((grid_h, grid_w), dtype=np.uint8)
for y in range(grid_h):
    for x in range(grid_w):
        cell = arr[y*cell_size:(y+1)*cell_size, x*cell_size:(x+1)*cell_size]
        # If more than 50% black, it's a 1
        grid[y, x] = 1 if np.mean(cell < 128) > 0.5 else 0

# Convert grid to bits
bits = ''
for y in range(grid_h):
    for x in range(grid_w):
        bits += str(grid[y, x])

print(f'Total bits: {len(bits)}')

# Convert to bytes
byte_count = len(bits) // 8
data = bytes([int(bits[i:i+8], 2) for i in range(0, len(bits)-7, 8)])

# Look for text
printable = ''
for b in data:
    if 32 <= b <= 126:
        printable += chr(b)
    else:
        printable += '.'
print(f'First 200 chars: {printable[:200]}')

# Search for keywords
for keyword in ['GENESIS', 'private', 'key', 'sword', 'legend', '5K', 'L5']:
    pos = printable.find(keyword)
    if pos >= 0:
        print(f'Found {keyword} at position {pos}')
        print(printable[pos:pos+100])

# Also try the first 64 bits as a hex key
if len(bits) >= 64:
    hex_key = hex(int(bits[:64], 2))[2:].zfill(32)
    print(f'First 64 bits as hex: {hex_key}')

# Try different grid sizes
for cell_size in [16, 64, 128]:
    grid_h = arr.shape[0] // cell_size
    grid_w = arr.shape[1] // cell_size
    bits = ''
    for y in range(grid_h):
        for x in range(grid_w):
            cell = arr[y*cell_size:(y+1)*cell_size, x*cell_size:(x+1)*cell_size]
            bits += '1' if np.mean(cell < 128) > 0.5 else '0'
    
    if len(bits) >= 8:
        byte_count = len(bits) // 8
        data = bytes([int(bits[i:i+8], 2) for i in range(0, len(bits)-7, 8)])
        printable = ''
        for b in data:
            if 32 <= b <= 126:
                printable += chr(b)
            else:
                printable += '.'
        print(f'Cell size {cell_size}: {printable[:100]}')
