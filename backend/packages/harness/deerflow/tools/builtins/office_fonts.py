"""Bounded TrueType Unicode coverage for explicit, authorized PDF font bytes."""

import bisect
import struct

MAX_FONT_BYTES = 32 * 1024 * 1024


def _unpack(data, offset, format):
    size = struct.calcsize(format)
    if offset < 0 or offset + size > len(data):
        raise ValueError("Truncated PDF font")
    return struct.unpack_from(format, data, offset)


def font_character_map(data):
    """Return validated Unicode-to-glyph IDs, retaining character aliases."""
    if not isinstance(data, bytes) or not 12 <= len(data) <= MAX_FONT_BYTES:
        raise ValueError("PDF font size unavailable")
    offset = 0
    if data[:4] == b"ttcf":
        count = _unpack(data, 8, ">I")[0]
        if not 1 <= count <= 64:
            raise ValueError("PDF font collection unavailable")
        offset = _unpack(data, 12, ">I")[0]  # PDFium selects the first face.
    if data[offset : offset + 4] not in {b"\x00\x01\x00\x00", b"true"}:
        raise ValueError("PDF font requires a TrueType outline")
    count = _unpack(data, offset + 4, ">H")[0]
    if not 1 <= count <= 256:
        raise ValueError("PDF font table count unavailable")
    tables = {}
    table_bytes = 0
    for index in range(count):
        tag, _, start, size = _unpack(data, offset + 12 + index * 16, ">4sIII")
        if tag in tables or start + size > len(data):
            raise ValueError("PDF font table unavailable")
        table_bytes += size
        if table_bytes > len(data):
            raise ValueError("PDF font total table budget exceeded")
        tables[tag] = data[start : start + size]
    if not {b"cmap", b"glyf", b"loca", b"maxp", b"head", b"OS/2"}.issubset(tables):
        raise ValueError("PDF font tables unavailable")
    embedding = _unpack(tables[b"OS/2"], 8, ">H")[0]
    if embedding & (0x0002 | 0x0200):
        raise ValueError("PDF font embedding unavailable")
    glyphs = _unpack(tables[b"maxp"], 4, ">H")[0]
    cmap = tables[b"cmap"]
    count = _unpack(cmap, 2, ">H")[0]
    if not 1 <= count <= 256:
        raise ValueError("PDF font character map unavailable")
    maps = []
    seen = set()
    mapped_entries = 0
    for index in range(count):
        platform, encoding, start = _unpack(cmap, 4 + index * 8, ">HHI")
        if not (platform == 0 or (platform == 3 and encoding in {1, 10})):
            continue
        if start in seen:
            continue
        seen.add(start)
        kind = _unpack(cmap, start, ">H")[0]
        if kind == 12:
            _, _, size, _, groups = _unpack(cmap, start, ">HHIII")
            if groups > 100_000 or size < 16 + groups * 12 or start + size > len(cmap):
                raise ValueError("PDF font character groups unavailable")
            mapped_entries += groups
            if mapped_entries > 100_000:
                raise ValueError("PDF font total character map limit exceeded")
            entries, ends = [], []
            previous = -1
            for i in range(groups):
                first, last, gid = _unpack(cmap, start + 16 + i * 12, ">III")
                if not previous < first <= last <= 0x10FFFF or gid + last - first >= glyphs:
                    raise ValueError("PDF font character group unavailable")
                entries.append((first, last, gid))
                ends.append(last)
                previous = last
            maps.append((12, entries, ends))
        elif kind == 4:
            _, size, _, doubled = _unpack(cmap, start, ">HHHH")
            segments = doubled // 2
            if doubled % 2 or not 1 <= segments <= 8192 or size < 16 + segments * 8 or start + size > len(cmap):
                raise ValueError("PDF font character segments unavailable")
            mapped_entries += segments
            if mapped_entries > 100_000:
                raise ValueError("PDF font total character map limit exceeded")
            table = cmap[start : start + size]
            ends = [_unpack(table, 14 + i * 2, ">H")[0] for i in range(segments)]
            starts = [_unpack(table, 16 + segments * 2 + i * 2, ">H")[0] for i in range(segments)]
            if any(first > last for first, last in zip(starts, ends)) or any(ends[i] >= starts[i + 1] for i in range(segments - 1)):
                raise ValueError("PDF font character segment order unavailable")
            maps.append((4, (table, starts, segments), ends))
    if not maps:
        raise ValueError("PDF font Unicode character map unavailable")

    def covered(code):
        for kind, entries, ends in maps:
            index = bisect.bisect_left(ends, code)
            if index == len(ends):
                continue
            if kind == 12:
                first, _, glyph = entries[index]
                if first <= code and 0 < glyph + code - first < glyphs:
                    return glyph + code - first
            elif code <= 0xFFFF:
                table, starts, segments = entries
                if code < starts[index]:
                    continue
                delta = _unpack(table, 16 + segments * 4 + index * 2, ">h")[0]
                range_position = 16 + segments * 6 + index * 2
                displacement = _unpack(table, range_position, ">H")[0]
                glyph = _unpack(table, range_position + displacement + 2 * (code - starts[index]), ">H")[0] if displacement else code
                if glyph:
                    glyph = (glyph + delta) & 0xFFFF
                if 0 < glyph < glyphs:
                    return glyph
        return 0

    return covered


def font_coverage(data):
    """Preserve the existing boolean coverage interface."""
    characters = font_character_map(data)
    return lambda code: bool(characters(code))
