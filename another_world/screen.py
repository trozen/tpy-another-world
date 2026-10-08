# Where displayed frames go: into the terminal as block-glyph cells, or,
# headless, into FNV-1a digests (one per frame, in the format the headless
# reference build prints, or one for the whole run).
from __future__ import annotations

import os
import sys

from typing import Final

from tpy import int32, int64

from .glyphs import BRAILLE, HALF, OCTANT, QUAD, SEXTANT

W: Final[int32] = 320
H: Final[int32] = 200
PAGE_SIZE: Final[int32] = W * H
FNV_OFFSET: Final[int64] = 2166136261
FNV_PRIME: Final[int64] = 16777619

MODE_TERMINAL: Final[int32] = 0
MODE_DIGESTS: Final[int32] = 1
MODE_SUMMARY: Final[int32] = 2
MODE_COMPARE: Final[int32] = 3

# Cell layouts: how many pixels one terminal cell shows, and with which glyphs.
RENDER_HALF: Final[int32] = 0
RENDER_QUAD: Final[int32] = 1
RENDER_SEXTANT: Final[int32] = 2
RENDER_OCTANT: Final[int32] = 3
RENDER_BRAILLE: Final[int32] = 4
RENDER_NAMES = ["half", "quad", "sextant", "octant", "braille"]


def frame_digest(pixels: bytearray, base: int32, palette: list[int32]) -> int64:
    h = FNV_OFFSET
    for i in range(base, base + PAGE_SIZE):
        h = ((h ^ int64(pixels[i])) * FNV_PRIME) & 0xFFFFFFFF
    for rgb in palette:
        for shift in range(16, -1, -8):
            h = ((h ^ int64((rgb >> shift) & 0xFF)) * FNV_PRIME) & 0xFFFFFFFF
    return h


def _sgr_color(layer: int32, rgb: int32) -> str:
    return f"\x1b[{layer};2;{(rgb >> 16) & 0xFF};{(rgb >> 8) & 0xFF};{rgb & 0xFF}m"


def _glyph(render: int32, mask: int32) -> str:
    if render == RENDER_HALF:
        return HALF[mask]
    if render == RENDER_QUAD:
        return QUAD[mask]
    if render == RENDER_SEXTANT:
        return SEXTANT[mask]
    if render == RENDER_OCTANT:
        return OCTANT[mask]
    return BRAILLE[mask]


def _color_distance(a: int32, b: int32) -> int32:
    dr = ((a >> 16) & 0xFF) - ((b >> 16) & 0xFF)
    dg = ((a >> 8) & 0xFF) - ((b >> 8) & 0xFF)
    db = (a & 0xFF) - (b & 0xFF)
    return 2 * dr * dr + 4 * dg * dg + 3 * db * db


def _popcount(v: int32) -> int32:
    n = 0
    while v:
        n += v & 1
        v >>= 1
    return n


class Cells:
    """Draws a frame as terminal cells of `cw` x `ch` pixels, each one glyph
    in a foreground and a background color. The frame is first reduced to
    the pixel grid the terminal fits, keeping the most common color of each
    block of source pixels (averaging would invent colors the flat-shaded
    art never has). A cell with more than two colors gets the pair that
    represents its pixels best. Only cells that changed are redrawn."""

    render: int32
    cw: int32
    ch: int32
    cols: int32
    rows: int32
    left: int32
    top: int32
    # Source pixel boundaries of each column and row of the reduced grid.
    xs: list[int32]
    ys: list[int32]
    grid: list[int32]
    counts: list[int32]
    # Weighted squared RGB distance between palette entries i and j at i * 16 + j.
    dist: list[int32]
    px: list[int32]
    colors: list[int32]
    # What each cell was last drawn with; a mask of -1 means unknown.
    shown_mask: list[int32]
    shown_fg: list[int32]
    shown_bg: list[int32]
    # The colors the terminal is set to while a frame is being written.
    cur_fg: int32
    cur_bg: int32

    def __init__(self, render: int32) -> None:
        self.render = render
        self.cw = 1 if render == RENDER_HALF else 2
        self.ch = 2
        if render == RENDER_SEXTANT:
            self.ch = 3
        elif render == RENDER_OCTANT or render == RENDER_BRAILLE:
            self.ch = 4
        self.cols = 0
        self.rows = 0
        self.left = 0
        self.top = 0
        self.xs = []
        self.ys = []
        self.grid = []
        self.counts = [0] * 16
        self.dist = [0] * 256
        self.px = [0] * 8
        self.colors = [0] * 8
        self.shown_mask = []
        self.shown_fg = []
        self.shown_bg = []
        self.cur_fg = -1
        self.cur_bg = -1

    def fit(self, term_cols: int32, term_rows: int32) -> bool:
        """Sizes the image to the terminal, centered. False if unchanged.
        A terminal cell is about twice as tall as wide, so keeping the
        frame's shape takes 5 rows per 16 columns whatever the layout."""
        cols = min(term_cols, term_rows * 16 // 5, W // self.cw)
        rows = cols * 5 // 16
        if rows * self.ch > H:
            rows = H // self.ch
            cols = min(cols, rows * 16 // 5)
        left = (term_cols - cols) // 2
        top = (term_rows - rows) // 2
        if cols == self.cols and rows == self.rows and left == self.left and top == self.top:
            return False
        self.cols = cols
        self.rows = rows
        self.left = left
        self.top = top
        width = cols * self.cw
        height = rows * self.ch
        self.xs = []
        for i in range(width + 1):
            self.xs.append(i * W // width)
        self.ys = []
        for j in range(height + 1):
            self.ys.append(j * H // height)
        self.grid = [0] * (width * height)
        self.shown_mask = [-1] * (cols * rows)
        self.shown_fg = [0] * (cols * rows)
        self.shown_bg = [0] * (cols * rows)
        return True

    def _reduce(self, pixels: bytearray, base: int32) -> None:
        width = self.cols * self.cw
        for ty in range(self.rows * self.ch):
            y0 = self.ys[ty]
            y1 = self.ys[ty + 1]
            for tx in range(width):
                x0 = self.xs[tx]
                x1 = self.xs[tx + 1]
                if x1 - x0 == 1 and y1 - y0 == 1:
                    self.grid[ty * width + tx] = int32(pixels[base + y0 * W + x0])
                    continue
                for c in range(16):
                    self.counts[c] = 0
                best = 0
                best_count = 0
                for y in range(y0, y1):
                    row = base + y * W
                    for x in range(x0, x1):
                        c = int32(pixels[row + x])
                        n = self.counts[c] + 1
                        self.counts[c] = n
                        if n > best_count:
                            best_count = n
                            best = c
                self.grid[ty * width + tx] = best

    def _fit_cell(self, n: int32) -> tuple[int32, int32, int32]:
        """The (mask, fg, bg) palette indices that best show the cell's `n`
        pixels in `px`: exact for two colors or fewer, otherwise the pair
        with the least total distance, each pixel taking the nearer one."""
        k = 0
        for i in range(n):
            c = self.px[i]
            seen = False
            for j in range(k):
                if self.colors[j] == c:
                    seen = True
            if not seen:
                self.colors[k] = c
                k += 1
        if k == 1:
            return (0, self.colors[0], self.colors[0])
        fg = self.colors[1]
        bg = self.colors[0]
        if k > 2:
            best_err = -1
            for a in range(k):
                for b in range(a + 1, k):
                    ca = self.colors[a]
                    cb = self.colors[b]
                    err = 0
                    for i in range(n):
                        p = self.px[i] * 16
                        err += min(self.dist[p + ca], self.dist[p + cb])
                    if best_err < 0 or err < best_err:
                        best_err = err
                        fg = cb
                        bg = ca
        mask = 0
        for i in range(n):
            p = self.px[i] * 16
            if self.dist[p + fg] < self.dist[p + bg]:
                mask |= 1 << i
        return (mask, fg, bg)

    def _prepare(self, pixels: bytearray, base: int32, palette: list[int32]) -> None:
        self._reduce(pixels, base)
        for i in range(16):
            for j in range(16):
                self.dist[i * 16 + j] = _color_distance(palette[i], palette[j])
        self.cur_fg = -1
        self.cur_bg = -1

    def _cell(self, r: int32, c: int32, palette: list[int32]) -> tuple[int32, int32, int32]:
        """The cell's (mask, fg, bg), fg and bg as RGB, in one canonical
        form per look: the first pixel in the background for solid glyphs,
        and for braille the dots in the minority color."""
        n = self.cw * self.ch
        full = (1 << n) - 1
        width = self.cols * self.cw
        i = 0
        for dy in range(self.ch):
            row = (r * self.ch + dy) * width + c * self.cw
            for dx in range(self.cw):
                self.px[i] = self.grid[row + dx]
                i += 1
        mask, fgi, bgi = self._fit_cell(n)
        fg = palette[fgi]
        bg = palette[bgi]
        if mask == 0 or fg == bg:
            return (0, bg, bg)
        # Every glyph but braille's is a solid shape, so a cell drawn with
        # the colors swapped and the mask inverted looks the same.
        if self.render != RENDER_BRAILLE:
            if mask & 1:
                return (mask ^ full, bg, fg)
        elif _popcount(mask) * 2 > n:
            return (mask ^ full, bg, fg)
        return (mask, fg, bg)

    def _emit(self, parts: list[str], mask: int32, fg: int32, bg: int32) -> None:
        if self.render != RENDER_BRAILLE and mask != 0:
            # Draw it the way round that needs fewer color changes.
            keep = int32(fg != self.cur_fg) + int32(bg != self.cur_bg)
            swap = int32(bg != self.cur_fg) + int32(fg != self.cur_bg)
            if swap < keep:
                mask ^= (1 << (self.cw * self.ch)) - 1
                t = fg
                fg = bg
                bg = t
        if mask != 0 and fg != self.cur_fg:
            parts.append(_sgr_color(38, fg))
            self.cur_fg = fg
        if bg != self.cur_bg:
            parts.append(_sgr_color(48, bg))
            self.cur_bg = bg
        parts.append(_glyph(self.render, mask))

    def draw(self, pixels: bytearray, base: int32, palette: list[int32]) -> str:
        """The escape sequences that update the screen to this frame."""
        self._prepare(pixels, base, palette)
        parts: list[str] = []
        for r in range(self.rows):
            # Whether the cursor already sits on this cell.
            placed = False
            for c in range(self.cols):
                mask, fg, bg = self._cell(r, c, palette)
                cell = r * self.cols + c
                if self.shown_mask[cell] == mask and self.shown_fg[cell] == fg \
                        and self.shown_bg[cell] == bg:
                    placed = False
                    continue
                self.shown_mask[cell] = mask
                self.shown_fg[cell] = fg
                self.shown_bg[cell] = bg
                if not placed:
                    parts.append(f"\x1b[{self.top + r + 1};{self.left + c + 1}H")
                    placed = True
                self._emit(parts, mask, fg, bg)
        return "".join(parts)

    def lines(self, pixels: bytearray, base: int32, palette: list[int32]) -> str:
        """The whole frame as lines of text, for printing in place."""
        self._prepare(pixels, base, palette)
        parts: list[str] = []
        for r in range(self.rows):
            parts.append(" " * self.left)
            for c in range(self.cols):
                mask, fg, bg = self._cell(r, c, palette)
                self._emit(parts, mask, fg, bg)
            parts.append("\x1b[0m\n")
            self.cur_fg = -1
            self.cur_bg = -1
        return "".join(parts)


def _terminal_size() -> tuple[int32, int32]:
    try:
        size = os.get_terminal_size(1)
        return (int32(size.columns), int32(size.lines))
    except OSError:
        return (160, 50)


class Screen:
    mode: int32
    frames: int32
    digest: int64
    cells: Cells
    # Compare mode: the frame to keep, and the copy of it once reached.
    compare_frame: int32
    done: bool
    kept: bytearray
    kept_palette: list[int32]

    def __init__(self, mode: int32, render: int32, compare_frame: int32) -> None:
        self.mode = mode
        self.frames = 0
        self.digest = FNV_OFFSET
        self.cells = Cells(render)
        self.compare_frame = compare_frame
        self.done = False
        self.kept = bytearray()
        self.kept_palette = [0] * 16

    def set_render(self, render: int32) -> None:
        self.cells = Cells(render)

    def begin(self) -> None:
        if self.mode == MODE_TERMINAL:
            # The alternate screen, so the shell's screen comes back on exit.
            sys.stdout.write("\x1b[?1049h\x1b[?25l\x1b[2J")

    def present(self, pixels: bytearray, base: int32, palette: list[int32],
                now: int32) -> None:
        """Shows the page at `base` in `pixels`, one palette index per byte."""
        if self.mode == MODE_DIGESTS:
            print(f"{self.frames} {now} {frame_digest(pixels, base, palette):08x}")
        elif self.mode == MODE_SUMMARY:
            d = frame_digest(pixels, base, palette)
            self.digest = ((self.digest ^ d) * FNV_PRIME) & 0xFFFFFFFF
        elif self.mode == MODE_COMPARE:
            if self.frames == self.compare_frame:
                for i in range(PAGE_SIZE):
                    self.kept.append(pixels[base + i])
                for i in range(16):
                    self.kept_palette[i] = palette[i]
                self.done = True
        else:
            cols, rows = _terminal_size()
            if self.cells.fit(cols, rows):
                sys.stdout.write("\x1b[0m\x1b[2J")
            sys.stdout.write(self.cells.draw(pixels, base, palette))
            sys.stdout.flush()
        self.frames += 1

    def end(self) -> None:
        if self.mode == MODE_TERMINAL:
            sys.stdout.write("\x1b[0m\x1b[?25h\x1b[?1049l")
            sys.stdout.flush()
        elif self.mode == MODE_SUMMARY:
            print(f"{self.frames} frames, digest {self.digest:08x}")
        elif self.mode == MODE_COMPARE:
            self._print_comparison()

    def _print_comparison(self) -> None:
        """Prints the kept frame once per cell layout, one under another,
        each as big as the terminal allows."""
        if not self.done:
            print(f"the intro has only {self.frames} frames")
            return
        cols, rows = _terminal_size()
        for render in range(len(RENDER_NAMES)):
            cells = Cells(render)
            cells.fit(cols, rows - 1)
            print(f"--render {RENDER_NAMES[render]}, frame {self.compare_frame}")
            sys.stdout.write(cells.lines(self.kept, 0, self.kept_palette))
        sys.stdout.flush()
