# The 20th Anniversary Edition: every resource a file of its own under the
# game directory (DAT/FILEnnn.DAT), its 320x200 backgrounds gzipped BMP
# images (BGZ/), its strings the lines of TXT/<lang>.txt, and the start
# values its game expects.
from __future__ import annotations

from typing import Final

import gzip

from tpy import Own, int32, int64, uint8

from .anniversary_strings import FALLBACK_STRINGS, STRING_IDS
from .files import find_file

WRITES_UP_DOWN: Final[bool] = True
HAS_PROTECTION: Final[bool] = False
INTRO_SKIP: Final[bool] = False
TYPED_CODES: Final[bool] = True

# The 320x200 backgrounds; the other ids the game asks for are its HD
# pictures (3000 and up) and sound preloads (2000 and up), which the
# original resolution has no use for.
BITMAPS: list[int32] = [67, 68, 69, 70, 71, 72, 73, 83, 144, 145]


def find_root(data_dir: str) -> str:
    """The directory holding DAT/, BGZ/ and TXT/: the one given, or its
    game/, or its game/game/ when given the GOG install root."""
    roots: list[str] = []
    roots.append(data_dir)
    roots.append(find_file(data_dir, "game"))
    roots.append(find_file(find_file(data_dir, "game"), "game"))
    for root in roots:
        if find_file(find_file(root, "DAT"), "FILE017.DAT") != "":
            return root
    return ""


def game_file(root: str, sub: str, name: str) -> str:
    """`sub/name` in the game directory, found case-insensitively, so a copy
    from a Windows install works too."""
    path = find_file(find_file(root, sub), name)
    if path == "":
        raise FileNotFoundError(f"{root}: {sub}/{name} is missing")
    return path


def read_dat(root: str, index: int32) -> bytes:
    path = game_file(root, "DAT", f"FILE{index:03d}.DAT")
    with open(path, "rb") as f:
        return f.read()


def read_bitmap(root: str, index: int32) -> Own[list[bytes]]:
    """The background `index` as one palette index per pixel, if it is one;
    a picture the install lacks is skipped, as rawgl does."""
    found: list[bytes] = []
    if index in BITMAPS:
        name = f"file{index:03d}.bgz"
        path = find_file(find_file(root, "BGZ"), name)
        if path != "":
            with gzip.open(path) as f:
                found.append(decode_bmp(f.read(), name))
    return found


def _le32(data: bytes, pos: int32) -> int64:
    """An unsigned little-endian long."""
    return int64(data[pos]) | (int64(data[pos + 1]) << 8) \
        | (int64(data[pos + 2]) << 16) | (int64(data[pos + 3]) << 24)


def decode_bmp(data: bytes, name: str) -> bytes:
    """A 20th Anniversary background: an 8-bit 320x200 BMP whose pixel
    values are the palette indices; the palette it carries is not used."""
    if len(data) < 54 or data[0:2] != b"BM" or _le32(data, 0x12) != 320 \
            or _le32(data, 0x16) != 200 or int32(data[0x1C]) != 8 or _le32(data, 0x1E) != 0:
        raise ValueError(f"{name}: not an uncompressed 320x200 8-bit BMP")
    if _le32(data, 0x0A) + 320 * 200 > len(data):
        raise ValueError(f"{name}: the BMP is cut short")
    start = int32(_le32(data, 0x0A))
    out = bytearray()
    # BMP rows run bottom-up.
    for y in range(199, -1, -1):
        row = start + y * 320
        for x in range(320):
            # The pictures use indices 0-15 only; the mask keeps a stray
            # value from reaching past the 16-color palette.
            out.append(uint8(int32(data[row + x]) & 0xF))
    return bytes(out)


def _decode_text_line(line: bytes) -> str:
    """One line of a 20th Anniversary TXT file in the DOS string form:
    `\\n` breaks the line and `\\2x` / `\\3x` name a glyph by number.
    Characters the 8x8 font lacks (tabs, accented letters) become spaces,
    which keep their column as the original's drawing does."""
    out: list[str] = []
    i = 0
    n = len(line)
    while i < n:
        c = int32(line[i])
        if c == 0x5C and i + 1 < n:  # backslash
            e = int32(line[i + 1])
            if e == 0x6E:  # n
                out.append("\n")
                i += 2
                continue
            if (e == 0x32 or e == 0x33) and i + 2 < n:
                code = (e - 0x30) * 10 + (int32(line[i + 2]) - 0x30)
                if 0x20 <= code < 0x7F:
                    out.append(chr(code))
                else:
                    out.append(" ")
                i += 3
                continue
            i += 2
            continue
        if c == 0x0D:
            out.append("\n")
        elif 0x20 <= c < 0x7F:
            out.append(chr(c))
        else:
            out.append(" ")
        i += 1
    return "".join(out)


def read_strings(root: str, lang: str) -> Own[dict[int32, str]]:
    """The strings in `lang` (EN, FR, DE, ES or IT), by the id the bytecode
    draws them with."""
    # The Windows install has TXT/<lang>.txt, the Linux one TXT/Linux/.
    txt = find_file(root, "TXT")
    path = find_file(txt, f"{lang}.txt")
    if path == "":
        path = find_file(find_file(txt, "Linux"), f"{lang}.txt")
    lines: list[bytes] = []
    if path != "":
        with open(path, "rb") as f:
            lines = f.read().split(b"\n")
    table: dict[int32, str] = {}
    for i in range(len(STRING_IDS)):
        sid = STRING_IDS[i]
        # 0x193 is listed twice; rawgl's lookup stops at the first.
        if sid in table:
            continue
        if i < len(lines):
            line = lines[i]
            # A Windows copy of the file ends its lines with CR LF.
            if len(line) > 0 and int32(line[len(line) - 1]) == 0x0D:
                line = line[:len(line) - 1]
            table[sid] = _decode_text_line(line)
        else:
            table[sid] = FALLBACK_STRINGS[i]
    return table


# The continue screen's prompt and its "ACCESS CODE:" label.
CONTINUE_SCREEN: list[int32] = [0x13D, 0x13C]


def fill_continue_screen(table: dict[int32, str]) -> None:
    """Gives the continue screen's lines, which the edition leaves blank,
    the built-in text."""
    for i in range(len(STRING_IDS)):
        sid = STRING_IDS[i]
        if sid in CONTINUE_SCREEN and table[sid].strip() == "":
            table[sid] = FALLBACK_STRINGS[i]


def start_vars(v: list[int32]) -> None:
    """The edition's game has its protection check stubbed out, so it needs
    none of the protection values."""


def part_vars(v: list[int32]) -> None:
    # Set at every part start, as rawgl does: normal difficulty, and the
    # original sounds rather than the remastered ones.
    v[0xBF] = 1
    v[0xDE] = 0
