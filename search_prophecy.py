# The 13-word prophecy from the project
prophecy = ['sword', 'legend', 'pull', 'magic', 'kingdom', 'artist', 'stone', 'destroy', 'forget', 'fire', 'steel', 'honey', 'question']

# Check all data for these words
data = open('logo.jpeg', 'rb').read()
data_lower = data.lower()

for word in prophecy:
    pos = data_lower.find(word.encode())
    if pos >= 0:
        print(f'Found "{word}" at offset {pos}')
        context = data[max(0,pos-20):pos+len(word)+20]
        print(f'  Context: {context}')

# Also check the hidden image
hidden_data = open('hidden_reconstructed2.jpeg', 'rb').read()
hidden_lower = hidden_data.lower()

print()
print('Checking hidden image...')
for word in prophecy:
    pos = hidden_lower.find(word.encode())
    if pos >= 0:
        print(f'Found "{word}" at offset {pos}')
        context = hidden_data[max(0,pos-20):pos+len(word)+20]
        print(f'  Context: {context}')

# Try XOR with common keys
print()
print('Trying XOR decoding of appended data...')
after_ffd9 = data[12724:]  # Skip FF D9 and 00 00
for key in range(256):
    xored = bytes([b ^ key for b in after_ffd9[:200]])
    if b'GENESIS' in xored or b'genesis' in xored or b'private' in xored or b'key' in xored:
        print(f'XOR key 0x{key:02X}: {xored[:100]}')
    for word in prophecy:
        if word.encode() in xored.lower():
            print(f'XOR key 0x{key:02X}: found "{word}" -> {xored[:100]}')

# Try treating the hidden JPEG raw data as the key itself
print()
print('Analyzing hidden JPEG structure...')
# The hidden JPEG is 85063 bytes - could the key be derived from it?
import hashlib
h = hashlib.sha256(after_ffd9).hexdigest()
print(f'SHA256 of hidden data: {h}')

# Check if the first bytes could be a private key
print(f'First 64 bytes as hex: {after_ffd9[:32].hex()}')
print(f'First 128 bytes as hex: {after_ffd9[:64].hex()}')
