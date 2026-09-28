# The resource list the DOS and Amiga releases run from: one entry per
# resource, where it sits in which bank, and whether it is loaded.
from __future__ import annotations

from tpy import int32

# Resource types, as the list records them.
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
