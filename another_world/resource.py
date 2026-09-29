# Game resources: which release the data directory holds, the resource
# list the DOS and Amiga releases share, and the four segments the current
# game part runs from. What each release does its own way lives in
# releases/.
from __future__ import annotations

from typing import Final

from tpy import Own, int32, uint8

from .codes import read_code_strings, read_codes, read_letter_labels, relabel
from .releases import amiga, anniversary, dos
from .releases.bytekiller import unpack
from .releases.files import find_file
from .releases.memlist import (RT_BITMAP, STATE_LOAD_ME, STATE_LOADED, STATE_NOT_NEEDED,
                               MemEntry)
from .text import string_table

RELEASE_DOS = 0
RELEASE_AMIGA = 1
RELEASE_20TH = 2

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


def decode_planar(src: bytes) -> bytes:
    """A DOS or Amiga background: 4 bit planes of 8000 bytes, the leftmost
    pixel in the high bit, into one palette index per pixel."""
    out = bytearray()
    for k in range(8000):
        b0 = int32(src[k])
        b1 = int32(src[8000 + k])
        b2 = int32(src[16000 + k])
        b3 = int32(src[24000 + k])
        for bit in range(8):
            shift = 7 - bit
            out.append(uint8(((b0 >> shift) & 1) | (((b1 >> shift) & 1) << 1)
                             | (((b2 >> shift) & 1) << 2) | (((b3 >> shift) & 1) << 3)))
    return bytes(out)


class Resources:
    """The game data of one release: for DOS and Amiga the loaded state of
    every entry of its resource list, for the 20th Anniversary Edition its
    files; and the four segments the current game part runs from."""

    data_dir: str
    release: int32
    # The 20th Anniversary Edition's game directory.
    nth_root: str
    # The Amiga floppy images the banks were read from, for error messages.
    disks: list[str]
    entries: list[MemEntry]
    banks: dict[int32, bytes]
    loaded: dict[int32, bytes]
    current_part: int32
    requested_part: int32
    palettes: bytes
    bytecode: bytes
    cinematic: bytes
    shapes: bytes
    # What the release's game expects of the engine.
    writes_up_down: bool
    has_protection: bool
    intro_skip: bool
    typed_codes: bool
    # The letters the password screen shows for those it takes, where they
    # differ, and the other way round, as lowercase keys.
    letter_labels: dict[int32, int32]
    label_keys: dict[int32, int32]

    def __init__(self, data_dir: str) -> None:
        self.data_dir = data_dir
        self.release = RELEASE_DOS
        self.entries = []
        self.banks = {}
        self.disks = []
        self.loaded = {}
        self.current_part = 0
        self.requested_part = 0
        self.palettes = b""
        self.bytecode = b""
        self.cinematic = b""
        self.shapes = b""
        self.writes_up_down = True
        self.has_protection = True
        self.intro_skip = False
        self.typed_codes = True
        self.letter_labels = {}
        self.label_keys = {}
        self.nth_root = anniversary.find_root(data_dir)
        memlist = dos.memlist_path(data_dir)
        if self.nth_root != "":
            self.release = RELEASE_20TH
            self.writes_up_down = anniversary.WRITES_UP_DOWN
            self.has_protection = anniversary.HAS_PROTECTION
            self.intro_skip = anniversary.INTRO_SKIP
            self.typed_codes = anniversary.TYPED_CODES
            text = anniversary.read_strings(self.nth_root, "EN")
            self.letter_labels = read_letter_labels(self._part_bytecode(GAME_PART_LAST), text)
            for taken in self.letter_labels:
                self.label_keys[self.letter_labels[taken] | 0x20] = taken | 0x20
        elif memlist != "":
            dos.read_memlist(memlist, self.entries)
            self.writes_up_down = dos.WRITES_UP_DOWN
            self.has_protection = dos.HAS_PROTECTION
            self.intro_skip = dos.INTRO_SKIP
            self.typed_codes = dos.TYPED_CODES
        elif amiga.has_data(data_dir):
            self.release = RELEASE_AMIGA
            amiga.read_disks(data_dir, self.banks, self.disks)
            if 1 not in self.banks:
                self.banks[1] = self._read_bank_file(1)
            amiga.read_entries(data_dir, self.banks[1], self.entries)
            self.writes_up_down = amiga.WRITES_UP_DOWN
            self.has_protection = amiga.HAS_PROTECTION
            self.intro_skip = amiga.INTRO_SKIP
            self.typed_codes = amiga.TYPED_CODES
        else:
            raise FileNotFoundError(
                f"{data_dir}: no 20th Anniversary game directory, MEMLIST.BIN, "
                ".adf disk images or bank01")

    def start_vars(self, v: list[int32]) -> None:
        """Sets the variables the release's game expects at its start."""
        if self.release == RELEASE_20TH:
            anniversary.start_vars(v)
        elif self.release == RELEASE_AMIGA:
            amiga.start_vars(v)
        else:
            dos.start_vars(v)

    def part_vars(self, v: list[int32]) -> None:
        """Sets the variables the release's game expects at a part start."""
        if self.release == RELEASE_20TH:
            anniversary.part_vars(v)
        elif self.release == RELEASE_AMIGA:
            amiga.part_vars(v)
        else:
            dos.part_vars(v)

    def strings(self) -> Own[dict[int32, str]]:
        """The text the bytecode draws, by string id."""
        if self.release == RELEASE_20TH:
            table = anniversary.read_strings(self.nth_root, "EN")
            anniversary.fill_continue_screen(table)
        else:
            table = string_table()
        # The continue screen shows the code of the checkpoint the game
        # restarts at, as the password screen takes it: the built-in table
        # has the DOS codes, and the 20th Anniversary Edition's are blank.
        codes = self.checkpoint_codes()
        parts: list[int32] = []
        for name in codes:
            part = codes[name][0]
            if part not in parts:
                parts.append(part)
        for part in parts:
            drawn = read_code_strings(self._part_bytecode(part), part, codes)
            for string_id, name in drawn.items():
                table[string_id] = name
        return table

    def _read_bank_file(self, bank: int32) -> bytes:
        path = find_file(self.data_dir, f"bank{bank:02x}")
        if path == "":
            raise FileNotFoundError(
                f"{self.data_dir}: no bank{bank:02X} {amiga.bank_source(self.disks)}")
        with open(path, "rb") as f:
            return f.read()

    def _has_bank(self, bank: int32) -> bool:
        return bank in self.banks or find_file(self.data_dir, f"bank{bank:02x}") != ""

    def read(self, index: int32) -> bytes:
        e = self.entries[index]
        if e.bank not in self.banks:
            self.banks[e.bank] = self._read_bank_file(e.bank)
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
            # Only the bank the Amiga release lacks by design is skipped;
            # any other missing bank is an error when it is read.
            if e.bank == 0 or (self.release == RELEASE_AMIGA and e.bank == amiga.ABSENT_BANK
                               and not self._has_bank(e.bank)):
                e.state = STATE_NOT_NEEDED
                continue
            data = self.read(best)
            if e.kind == RT_BITMAP:
                bitmaps.append(decode_planar(data))
                e.state = STATE_NOT_NEEDED
            else:
                self.loaded[best] = data
                e.state = STATE_LOADED

    def is_loaded(self, index: int32) -> bool:
        return index < len(self.entries) and self.entries[index].state == STATE_LOADED

    def request(self, index: int32) -> Own[list[bytes]]:
        """Loads one entry, or, for a game part number, asks for that part
        to start at the next frame. Ids that name nothing are ignored."""
        if index >= GAME_PART_FIRST:
            self.requested_part = index
            return []
        if self.release == RELEASE_20TH:
            return anniversary.read_bitmap(self.nth_root, index)
        if index >= len(self.entries):
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
        if self.release != RELEASE_20TH:
            for e in self.entries:
                e.state = STATE_NOT_NEEDED
            self.entries[pal].state = STATE_LOAD_ME
            self.entries[code].state = STATE_LOAD_ME
            self.entries[cine].state = STATE_LOAD_ME
            if shapes != 0:
                self.entries[shapes].state = STATE_LOAD_ME
            self.load_marked()
        self.palettes = self._load(pal)
        self.bytecode = self._load(code)
        self.cinematic = self._load(cine)
        if shapes != 0:
            self.shapes = self._load(shapes)
        self.current_part = part

    def checkpoint_codes(self) -> Own[dict[str, tuple[int32, int32]]]:
        """The password screen's codes, spelled as it shows them, each mapped
        to (part, checkpoint)."""
        codes = read_codes(self._part_bytecode(GAME_PART_LAST))
        if len(self.letter_labels) == 0:
            return codes
        shown: dict[str, tuple[int32, int32]] = {}
        for name in codes:
            start = codes[name]
            shown[relabel(name, self.letter_labels)] = (start[0], start[1])
        return shown

    def taken_key(self, key: int32) -> int32:
        """The key the password screen takes for a lowercase letter typed,
        so that a letter types what the screen shows for it."""
        if key in self.label_keys:
            return self.label_keys[key]
        return key

    def _part_bytecode(self, part: int32) -> bytes:
        return self._load(PARTS[part - GAME_PART_FIRST][1])

    def _load(self, index: int32) -> bytes:
        """One part segment: its own file in the 20th Anniversary Edition,
        a resource list entry elsewhere."""
        if self.release == RELEASE_20TH:
            return anniversary.read_dat(self.nth_root, index)
        return self.read(index)
