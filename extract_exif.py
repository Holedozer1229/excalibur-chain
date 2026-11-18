import struct

data = open('logo.jpeg', 'rb').read()

exif_start = data.find(b'Exif\x00\x00')
if exif_start >= 0:
    seg_start = exif_start - 4
    seg_len = (data[seg_start+2] << 8) | data[seg_start+3]
    exif_data = data[seg_start+4:seg_start+2+seg_len]
    print(f'EXIF segment: {len(exif_data)} bytes')
    
    endian = '<'
    if exif_data[:2] == b'MM':
        endian = '>'
    elif exif_data[:2] == b'II':
        endian = '<'
    print(f'Byte order: {endian}, header: {exif_data[:4]}')
    
    ifd_count_offset = struct.unpack(endian + 'H', exif_data[4:6])[0]
    print(f'IFD0 entries: {ifd_count_offset}')
    
    offset = 8
    for i in range(ifd_count_offset):
        entry = exif_data[offset:offset+12]
        tag, dtype, count = struct.unpack(endian + 'HHI', entry[:8])
        value_data = entry[8:12]
        
        tag_names = {
            0x010E: 'Make', 0x010F: 'Model', 0x0110: 'Orientation',
            0x8298: 'Copyright', 0x9C9B: 'XPTitle', 0x9C9C: 'XPComment',
            0x9286: 'UserComment', 0x0131: 'NewSubfileType',
            0x0100: 'ImageWidth', 0x0101: 'ImageLength',
            0x0102: 'BitsPerSample', 0x0103: 'Compression',
            0x011A: 'XResolution', 0x011B: 'YResolution',
            0x0128: 'ResolutionUnit', 0x8769: 'ExifIFDPointer',
        }
        tag_name = tag_names.get(tag, f'0x{tag:04X}')
        
        if dtype == 2:
            if count <= 4:
                value = value_data[:count-1].decode('ascii', errors='replace')
            else:
                str_offset = struct.unpack(endian + 'I', value_data)[0]
                value = exif_data[str_offset:str_offset+count-1].decode('ascii', errors='replace')
            print(f'  Tag {tag_name} ({tag}): {value}')
        elif dtype == 3:
            if count == 1:
                value = struct.unpack(endian + 'H', value_data[:2])[0]
            elif count == 4:
                value = struct.unpack(endian + 'II', value_data)
            else:
                value_offset = struct.unpack(endian + 'I', value_data)[0]
                value = 'offset ' + str(value_offset)
            print(f'  Tag {tag_name} ({tag}): {value}')
        elif dtype == 4:
            value = struct.unpack(endian + 'I', value_data)[0]
            print(f'  Tag {tag_name} ({tag}): {value}')
        else:
            print(f'  Tag {tag_name} ({tag}): type={dtype}, count={count}')
        
        offset += 12
    
    print()
    print('All printable strings in EXIF:')
    current = b''
    for b in exif_data:
        if 32 <= b <= 126:
            current += bytes([b])
        else:
            if len(current) > 5:
                print('  ' + current.decode('ascii'))
            current = b''
    if len(current) > 5:
        print('  ' + current.decode('ascii'))
