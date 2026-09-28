# The DOS release: MEMLIST.BIN, the resource list its BANKxx files are read
# through, and the start values its game expects.
from __future__ import annotations

from typing import Final

from tpy import int32

from ..binary import be32
from .files import find_file
from .memlist import STATE_END_OF_LIST, MemEntry

WRITES_UP_DOWN: Final[bool] = True
HAS_PROTECTION: Final[bool] = True
# The DOS intro ends at the action key by itself.
INTRO_SKIP: Final[bool] = False


def memlist_path(data_dir: str) -> str:
    return find_file(data_dir, "memlist.bin")


def read_memlist(path: str, entries: list[MemEntry]) -> None:
    with open(path, "rb") as f:
        raw = f.read()
    pos = 0
    while int32(raw[pos]) != STATE_END_OF_LIST:
        entries.append(MemEntry(
            int32(raw[pos]), int32(raw[pos + 1]), int32(raw[pos + 6]),
            int32(raw[pos + 7]), int32(be32(raw, pos + 8)),
            int32(be32(raw, pos + 12)), int32(be32(raw, pos + 16))))
        pos += 20


def start_vars(v: list[int32]) -> None:
    # Values the copy-protection screen would have left behind.
    v[0xBC] = 0x10
    v[0xC6] = 0x80
    v[0xF2] = 4000
    v[0xDC] = 33


def part_vars(v: list[int32]) -> None:
    v[0xE4] = 0x14
