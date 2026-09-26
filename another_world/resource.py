# Game resources: the MEMLIST.BIN directory, the BANKxx files it points into,
# and the ByteKiller decompressor most entries are packed with.
from __future__ import annotations

import os
from typing import Final

from tpy import Own, int32, uint8, uint32

# Resource types, as MEMLIST.BIN records them.
RT_SOUND = 0
RT_MUSIC = 1
RT_BITMAP = 2
RT_PALETTE = 3
RT_BYTECODE = 4
RT_POLY_CINEMATIC = 5
RT_POLY_SHAPES = 6

STATE_NOT_NEEDED = 0
STATE_LOADED = 1
STATE_LOAD_ME = 2
STATE_END_OF_LIST = 0xFF

GAME_PART_FIRST: Final[int32] = 16000
GAME_PART_LAST: Final[int32] = 16009
PART_INTRO: Final[int32] = 16001

# Per game part: the palette, bytecode, cinematic polygons and shared shapes
# (0 = none) it loads, as MEMLIST indices.
PARTS: list[tuple[int32, int32, int32, int32]] = [
    (0x14, 0x15, 0x16, 0x00),  # 16000 copy protection
    (0x17, 0x18, 0x19, 0x00),  # 16001 intro
    (0x1A, 0x1B, 0x1C, 0x11),  # 16002 water
    (0x1D, 0x1E, 0x1F, 0x11),  # 16003 jail
    (0x20, 0x21, 0x22, 0x11),  # 16004 city
    (0x23, 0x24, 0x25, 0x00),  # 16005 arena
    (0x26, 0x27, 0x28, 0x11),  # 16006 baths
    (0x29, 0x2A, 0x2B, 0x11),  # 16007 final
    (0x7D, 0x7E, 0x7F, 0x00),  # 16008 password screen
    (0x7D, 0x7E, 0x7F, 0x00),  # 16009 password screen
]


def be16(data: bytes, pos: int32) -> int32:
    hi = int32(data[pos])
    lo = int32(data[pos + 1])
    return (hi << 8) | lo


def be32(data: bytes, pos: int32) -> uint32:
    hi = uint32(be16(data, pos))
    lo = uint32(be16(data, pos + 2))
    return (hi << 16) | lo


class MemEntry:
    state: int32
    kind: int32
    rank: int32
    bank: int32
    offset: int32
    packed_size: int32
    size: int32

    def __init__(self, state: int32, kind: int32, rank: int32, bank: int32,
                 offset: int32, packed_size: int32, size: int32) -> None:
        self.state = state
        self.kind = kind
        self.rank = rank
        self.bank = bank
        self.offset = offset
        self.packed_size = packed_size
        self.size = size


def read_memlist(data_dir: str, entries: list[MemEntry]) -> None:
    path = os.path.join(data_dir, "MEMLIST.BIN")
    with open(path, "rb") as f:
        raw = f.read()
    pos = 0
    while int32(raw[pos]) != STATE_END_OF_LIST:
        entries.append(MemEntry(
            int32(raw[pos]), int32(raw[pos + 1]), int32(raw[pos + 6]),
            int32(raw[pos + 7]), int32(be32(raw, pos + 8)),
            int32(be32(raw, pos + 12)), int32(be32(raw, pos + 16))))
        pos += 20


class _BitReader:
    """ByteKiller's input: 32-bit words read from the end of the packed data
    towards its start, each shifted out low bit first. A word's highest set
    bit is a sentinel marking where its payload ends."""

    data: bytes
    pos: int32
    chk: uint32
    crc: uint32

    def __init__(self, data: bytes, pos: int32) -> None:
        self.data = data
        self.pos = pos
        self.chk = 0
        self.crc = 0

    def word(self) -> uint32:
        v = be32(self.data, self.pos)
        self.pos -= 4
        return v

    def bit(self) -> int32:
        b = int32(self.chk & 1)
        self.chk >>= 1
        if self.chk == 0:
            # A fresh word: its top bit is shifted in as 1 so the word runs
            # dry exactly when its payload does.
            self.chk = self.word()
            self.crc ^= self.chk
            b = int32(self.chk & 1)
            self.chk = (self.chk >> 1) | 0x80000000
        return b

    def bits(self, n: int32) -> int32:
        v = 0
        for _ in range(n):
            v = (v << 1) | self.bit()
        return v


def unpack(packed: bytes) -> bytes:
    """Decompress one ByteKiller stream. The output is written back to front;
    a back-reference copies from bytes already written above the cursor."""
    r = _BitReader(packed, len(packed) - 4)
    size = int32(r.word())
    out = bytearray(size)
    r.crc = r.word()
    r.chk = r.word()
    r.crc ^= r.chk
    dst = size - 1
    remaining = size
    while remaining > 0:
        literal_count = 0
        copy_count = 0
        copy_bits = 0
        if r.bit() == 0:
            if r.bit() == 0:
                literal_count = r.bits(3) + 1
            else:
                copy_count = 2
                copy_bits = 8
        else:
            c = r.bits(2)
            if c == 3:
                literal_count = r.bits(8) + 9
            elif c < 2:
                copy_count = c + 3
                copy_bits = c + 9
            else:
                copy_count = r.bits(8) + 1
                copy_bits = 12
        if literal_count > 0:
            remaining -= literal_count
            for _ in range(literal_count):
                out[dst] = uint8(r.bits(8))
                dst -= 1
        else:
            distance = r.bits(copy_bits)
            remaining -= copy_count
            for _ in range(copy_count):
                out[dst] = out[dst + distance]
                dst -= 1
    if r.crc != 0:
        raise ValueError("ByteKiller checksum mismatch")
    return bytes(out)




class Resources:
    """The loaded state of every MEMLIST entry, and the four segments the
    current game part runs from."""

    data_dir: str
    entries: list[MemEntry]
    banks: dict[int32, bytes]
    loaded: dict[int32, bytes]
    current_part: int32
    requested_part: int32
    palettes: bytes
    bytecode: bytes
    cinematic: bytes
    shapes: bytes

    def __init__(self, data_dir: str) -> None:
        self.data_dir = data_dir
        self.entries = []
        read_memlist(data_dir, self.entries)
        self.banks = {}
        self.loaded = {}
        self.current_part = 0
        self.requested_part = 0
        self.palettes = b""
        self.bytecode = b""
        self.cinematic = b""
        self.shapes = b""

    def read(self, index: int32) -> bytes:
        e = self.entries[index]
        if e.bank not in self.banks:
            path = os.path.join(self.data_dir, f"BANK{e.bank:02X}")
            with open(path, "rb") as f:
                self.banks[e.bank] = f.read()
        packed = self.banks[e.bank][e.offset:e.offset + e.packed_size]
        if e.packed_size == e.size:
            return packed
        return unpack(packed)

    def load_marked(self) -> Own[list[bytes]]:
        """Loads every entry marked LOAD_ME, highest rank first. Bitmaps are
        not kept: they are returned, for the caller to put into page 0."""
        bitmaps: list[bytes] = []
        while True:
            best = -1
            best_rank = 0
            for i in range(len(self.entries)):
                candidate = self.entries[i]
                if candidate.state == STATE_LOAD_ME and best_rank <= candidate.rank:
                    best_rank = candidate.rank
                    best = i
            if best < 0:
                return bitmaps
            e = self.entries[best]
            if e.bank == 0:
                e.state = STATE_NOT_NEEDED
                continue
            data = self.read(best)
            if e.kind == RT_BITMAP:
                bitmaps.append(data)
                e.state = STATE_NOT_NEEDED
            else:
                self.loaded[best] = data
                e.state = STATE_LOADED

    def is_loaded(self, index: int32) -> bool:
        return index < len(self.entries) and self.entries[index].state == STATE_LOADED

    def request(self, index: int32) -> Own[list[bytes]]:
        """Loads one entry, or, for an id past the list, asks for that game
        part to start at the next frame."""
        if index > len(self.entries):
            self.requested_part = index
            return []
        e = self.entries[index]
        if e.state == STATE_NOT_NEEDED:
            e.state = STATE_LOAD_ME
            return self.load_marked()
        return []

    def invalidate_media(self) -> None:
        """Drops sounds, music and bitmaps, keeping the part's segments."""
        for e in self.entries:
            if e.kind <= RT_BITMAP or e.kind > 6:
                e.state = STATE_NOT_NEEDED

    def segment(self, which: int32) -> bytes:
        """The current part's bytecode, palettes, cinematic polygons or
        shared shapes (0-3)."""
        if which == 0:
            return self.bytecode
        if which == 1:
            return self.palettes
        if which == 2:
            return self.cinematic
        return self.shapes

    def entry(self, index: int32) -> bytes:
        return self.loaded[index]

    def setup_part(self, part: int32) -> None:
        if part == self.current_part:
            return
        if part < GAME_PART_FIRST or part > GAME_PART_LAST:
            raise ValueError(f"invalid game part {part}")
        pal, code, cine, shapes = PARTS[part - GAME_PART_FIRST]
        for e in self.entries:
            e.state = STATE_NOT_NEEDED
        self.entries[pal].state = STATE_LOAD_ME
        self.entries[code].state = STATE_LOAD_ME
        self.entries[cine].state = STATE_LOAD_ME
        if shapes != 0:
            self.entries[shapes].state = STATE_LOAD_ME
        self.load_marked()
        self.palettes = self.read(pal)
        self.bytecode = self.read(code)
        self.cinematic = self.read(cine)
        if shapes != 0:
            self.shapes = self.read(shapes)
        self.current_part = part
