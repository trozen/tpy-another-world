# tpy-another-world

The Another World (Out of This World) engine, ported to TurboPython: the
bytecode VM, the resource loader with its ByteKiller decompressor, and the
polygon rasterizer. The picture is drawn in the terminal with block glyphs
and 24-bit color. This first iteration plays the intro.

No game data is included. You need the original DOS release's `MEMLIST.BIN`
and `BANK01` to `BANK0D` files.

## Run

From a TurboPython checkout:

```bash
uv run tpy path/to/aw.py --data DIR        # play the intro in the terminal
uv run tpy path/to/aw.py --data DIR | cat  # headless: frame count + digest
uv run tpy path/to/aw.py --data DIR --digests  # one digest per frame
```

The image is scaled to fit the terminal and centered. `--render` picks how
many pixels one terminal cell shows:

| `--render` | Pixels per cell | Notes |
|---|---|---|
| `half` (default) | 1x2 | half blocks; every cell exact |
| `quad` | 2x2 | quadrants |
| `sextant` | 2x3 | needs a font with Unicode 13 |
| `octant` | 2x4 | needs a font with Unicode 16 (most fonts do not have it yet) |
| `braille` | 2x4 | dots; one-color cells are drawn solid |

A cell shows two colors; a cell with more gets the pair that represents its
pixels best. The frame is first reduced to the grid the terminal fits,
keeping the most common color of each block of pixels. The terminal needs
24-bit color.

When the output is not a terminal, or with `--digests`, the game runs on a
virtual clock: 1 ms per engine frame, plus every pause the bytecode asks for.
That makes a run instant and repeatable.

## Status

- Every intro frame (2614, pixels and palette) is identical to the reference
  interpreter's under the same virtual clock, with text drawing disabled on
  both sides.
- Not implemented: text (the font and string table are not in the data files),
  sound and music playback (the music sequencer runs silently, only for the
  timing marks the bytecode waits on), input, and the game parts after the
  intro.

## Layout

| File | What |
|---|---|
| `aw.py` | entry point |
| `another_world/main.py` | command line and the engine loop |
| `another_world/resource.py` | MEMLIST.BIN, the banks, ByteKiller, per-part loading |
| `another_world/vm.py` | the 64-thread bytecode VM |
| `another_world/video.py` | pages, polygon filling, page copy and flip |
| `another_world/music.py` | the silent music sequencer |
| `another_world/clock.py` | wall or virtual game clock |
| `another_world/screen.py` | terminal output and frame digests |
| `another_world/glyphs.py` | the glyph for every pixel pattern of each cell layout |

## License

GPL-2.0, see `LICENSE`. This is a port of Fabien Sanglard's
[Another-World-Bytecode-Interpreter](https://github.com/fabiensanglard/Another-World-Bytecode-Interpreter),
itself based on Gregory Montoir's `raw`, both under the GPL.
Another World is by Eric Chahi.
