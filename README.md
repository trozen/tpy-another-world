# tpy-another-world

The Another World (Out of This World) engine, ported to TurboPython: the
bytecode VM, the resource loader with its ByteKiller decompressor, and the
polygon rasterizer. The picture is drawn in the terminal with block glyphs
and 24-bit color, and the game is played with the keyboard.

## Getting the game

You can get the game on GOG:
[Another World 20th Anniversary Edition](https://www.gog.com/en/game/another_world_20th_anniversary_edition),
which also includes the Amiga version. No game data is included here; if
you play it with this port, please buy it and support its makers.

The game reads three releases; point `DIR` on the command line at one of
them:

- **20th Anniversary Edition** (GOG): the install directory, or its
  `game/` directory. The game runs its original 320x200 pictures and the
  English text of the edition; the remastered HD pictures, sounds and
  music are not used.
- **DOS**: the directory with `MEMLIST.BIN` and `BANK01` to `BANK0D`.
- **Amiga**, which the GOG edition includes as a zip of two floppy images:
  the directory with the two `.adf` files from the unzipped archive, or
  with the `bankNN` files on them.

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
| space, enter | action: kick, shoot, or run with an arrow; skips the intro |
| c | the password screen, to start a level by its code |
| p | pause |
| letters, backspace | type on the password screen |
| Ctrl-C | quit |

## Terminal

For the best experience, run the game in Ghostty with `-8`.

Use a terminal with the
[kitty keyboard protocol](https://sw.kovidgoyal.net/kitty/keyboard-protocol/):
Ghostty, kitty, WezTerm, foot or Alacritty. Only such terminals report key
releases, and the game needs to know how long a key is held; in others,
such as GNOME Terminal, a key counts as held while it repeats, so a tap
lasts about half a second. The terminal also needs 24-bit color; the
picture is scaled to fit the window.

Use `-8` where the terminal can show it, `-2` (the default) elsewhere. `-8`
draws 2x4 pixels a cell, the sharpest picture, with octant characters
(Unicode 16) that most fonts lack; `-6` needs sextants (Unicode 13).
Ghostty draws these characters itself, whatever the font; `-2` works with
any font.

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
  on, and the first 3000 from each of several start parts. For the Amiga
  release the reference was given the same resource list and start values;
  for the 20th Anniversary Edition the reference is rawgl, with its own
  rendering changes turned off (palette fix-ups, sprite masks, and its
  polygon scan start and one-pixel shapes, which differ from the original
  engine).
- French Amiga data is recognized, but its text is drawn in English.
- The font, and for DOS and Amiga the string table, come from the DOS
  executable, which the data files do not include; `another_world/text.py`
  carries them. The 20th Anniversary Edition's strings are read from its
  `TXT/` files.
- Not implemented: sound and music playback (the music sequencer runs
  silently, only for the timing marks the bytecode waits on), and saving.

## Layout

| File | What |
|---|---|
| `aw.py` | entry point |
| `another_world/main.py` | command line and the engine loop |
| `another_world/resource.py` | release detection, the resource list DOS and Amiga share, per-part loading |
| `another_world/releases/dos.py` | MEMLIST.BIN and the DOS start values |
| `another_world/releases/amiga.py` | the Amiga banks, resource list and start values |
| `another_world/releases/anniversary.py` | the 20th Anniversary files (DAT, BMP backgrounds, TXT strings) and start values |
| `another_world/releases/adf.py` | files on Amiga floppy images |
| `another_world/releases/amiga_memlist.py` | the Amiga release's resource list, from rawgl |
| `another_world/releases/anniversary_strings.py` | the 20th Anniversary string ids and fallback strings, from rawgl |
| `another_world/releases/bytekiller.py` | the ByteKiller unpacker of the DOS and Amiga banks |
| `another_world/releases/memlist.py`, `files.py` | resource list entries; case-insensitive file lookup |
| `another_world/binary.py` | big-endian integers |
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
itself based on Gregory Montoir's `raw`, both under the GPL. The Amiga
resource list and start values come from Montoir's
[rawgl](https://github.com/cyxx/rawgl).
Another World is by Eric Chahi.
