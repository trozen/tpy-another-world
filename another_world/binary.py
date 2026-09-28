# Big-endian integers, the byte order of every release's bytecode, shapes
# and palettes.
from __future__ import annotations

from tpy import int32, uint32


def be16(data: bytes, pos: int32) -> int32:
    hi = int32(data[pos])
    lo = int32(data[pos + 1])
    return (hi << 8) | lo


def be32(data: bytes, pos: int32) -> uint32:
    hi = uint32(be16(data, pos))
    lo = uint32(be16(data, pos + 2))
    return (hi << 16) | lo
