# tpy-another-world

The Another World (Out of This World) engine, ported to TurboPython: the
bytecode VM, the resource loader with its ByteKiller decompressor, and the
polygon rasterizer. The picture is drawn in the terminal with block glyphs
and 24-bit color, and the game is played with the keyboard.

## Getting the game

No game data is included. Another World is still sold, as the
[20th Anniversary Edition on GOG](https://www.gog.com/en/game/another_world_20th_anniversary_edition);
if you play it here, please buy it there and support its makers.

This port reads the original DOS release's files, `MEMLIST.BIN` and
`BANK01` to `BANK0D`. The 20th Anniversary Edition does not include them
(it ships its own remastered data, plus the Amiga version), and reading
either of those is not implemented yet.

## Run

The game runs on [TurboPython](https://tpy-lang.org), which compiles it to
C++ on the first run:

```bash
uv tool install tpy-lang   # or: pip install tpy-lang
tpy aw.py DIR -8           # DIR holds the game data
```

`-8` gives the sharpest picture, but needs a terminal that can show it:
see [Terminal](#terminal). The keys are below; `tpy aw.py` without arguments
prints them with all the options.

## Keys

| Key | Action |
|---|---|
| left, right | walk; run with space held |
| up | jump |
| down | crouch |
| space, enter | action: kick, shoot, or run with an arrow |
| c | the password screen, to start a level by its code |
| p | pause |
| letters, backspace | type on the password screen |
| Esc, Ctrl-C | quit |

## Terminal

The game needs to know how long a key is held, and only terminals with the
[kitty keyboard protocol](https://sw.kovidgoyal.net/kitty/keyboard-protocol/)
report key releases: Ghostty, kitty, WezTerm, foot and Alacritty. In
others, such as GNOME Terminal, a key counts as held while it repeats, so a
tap lasts about half a second. The terminal also needs 24-bit color; the
picture is scaled to fit the window.

The picture is drawn with block characters. The default, `-2`, works with
any font. The sharper modes need characters most fonts lack: `-6` needs
sextants (Unicode 13) and `-8` octants (Unicode 16). Ghostty draws these
characters itself, so there `-8` works and looks best.

For the best experience, run the game in Ghostty with `-8`.

## Render modes

The image is scaled to fit the terminal and centered. The mode picks how
many pixels one terminal cell shows: `-2`, `-4`, `-6` and `-8` by that count,
or `-r` (`--render`) by name.

| Option | Pixels per cell | Notes |
|---|---|---|
| `-2`, `-r half` (default) | 1x2 | half blocks; every cell exact |
| `-4`, `-r quad` | 2x2 | quadrants |
| `-6`, `-r sextant` | 2x3 | needs sextants (Unicode 13) in the font, or Ghostty |
| `-8`, `-r octant` | 2x4 | needs octants (Unicode 16) in the font, or Ghostty |
| `-r braille` | 2x4 | dots; one-color cells are drawn solid |

A cell shows two colors; a cell with more gets the pair that represents its
pixels best. The frame is first reduced to the grid the terminal fits,
keeping the most common color of each block of pixels.

## Headless runs

When the output is not a terminal, or with `--digests`, the game runs on a
virtual clock: 1 ms per engine frame, plus every pause the bytecode asks for.
That makes a run instant and repeatable. `tpy aw.py DIR | cat` prints the
frame count and a digest, `--digests` one digest per frame; `--part` picks
the game part to start in and `--frames N` stops after N frames.

## Status

- Frames without input are identical to the reference interpreter's under
  the same virtual clock, pixels and palette: the first 20000 from the intro
  on, and the first 3000 from each of several start parts (16001, 16002,
  16003, 16005 and 16009).
- The font and the string table come from the DOS executable, which the data
  files do not include; `another_world/text.py` carries them.
- Not implemented: sound and music playback (the music sequencer runs
  silently, only for the timing marks the bytecode waits on), and saving.

## Layout

| File | What |
|---|---|
| `aw.py` | entry point |
| `another_world/main.py` | command line and the engine loop |
| `another_world/resource.py` | MEMLIST.BIN, the banks, ByteKiller, per-part loading |
| `another_world/vm.py` | the 64-thread bytecode VM |
| `another_world/video.py` | pages, polygon filling, page copy and flip |
| `another_world/music.py` | the silent music sequencer |
| `another_world/keyboard.py` | raw terminal input, held keys |
| `another_world/text.py` | the font and the English strings |
| `another_world/clock.py` | wall or virtual game clock |
| `another_world/screen.py` | terminal output and frame digests |
| `another_world/glyphs.py` | the glyph for every pixel pattern of each cell layout |

## License

GPL-2.0, see `LICENSE`. This is a port of Fabien Sanglard's
[Another-World-Bytecode-Interpreter](https://github.com/fabiensanglard/Another-World-Bytecode-Interpreter),
itself based on Gregory Montoir's `raw`, both under the GPL.
Another World is by Eric Chahi.
