# Development

Notes for working on the engine; the [README](../README.md) is for playing.

## Headless runs

When the output is not a terminal, or with `--digests`, the game runs on a
virtual clock: 1 ms per engine frame, plus every pause the bytecode asks for.
That makes a run instant and repeatable. `tpy aw.py DIR | cat` prints the
frame count and a digest, `--digests` one digest per frame; `--part` picks
the game part to start in and `--frames N` stops after N frames.
`--wav FILE` writes the sound and music to a WAV file; in a headless run it
follows the virtual clock too, so it sounds the same every time.

## Status

- Frames without input are identical to the reference interpreter's under
  the same virtual clock, pixels and palette: the first 20000 from the intro
  on, and the first 3000 from each of several start parts. For the Amiga
  release the reference was given the same resource list and start values;
  for the 20th Anniversary Edition the reference is rawgl, with its own
  rendering changes turned off (palette fix-ups, sprite masks, and its
  polygon scan start and one-pixel shapes, which differ from the original
  engine). The one difference left is the continue screen after a death,
  which here shows each release's own checkpoint code: the references show
  the DOS codes on the Amiga and a blank screen on the 20th Anniversary
  Edition.
- French Amiga data is recognized, but its text is drawn in English.
- The font, and for DOS and Amiga the string table, come from the DOS
  executable, which the data files do not include; `another_world/text.py`
  carries them. The 20th Anniversary Edition's strings are read from its
  `TXT/` files.
- Sound and music play through the first of `pw-play`, `paplay` or
  `aplay` that works (`--mute` turns them off). The 20th Anniversary Edition
  plays its original sound effects (`WGZ/original/`) and its recordings of
  the original's intro and ending music (`OGG/original/`), or with
  `--remastered-audio` its remastered sound effects and ambient music. A
  recording needs `pw-play` or `paplay`, and `--wav` leaves it out.
- Not implemented: saving.

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
| `another_world/codes.py` | the password screen's checkpoint codes, read from its bytecode, and typing one |
| `another_world/vm.py` | the 64-thread bytecode VM |
| `another_world/video.py` | pages, polygon filling, page copy and flip |
| `another_world/music.py` | the music sequencer, which plays the notes and passes on the marks the bytecode waits on |
| `another_world/sound.py` | the mixer: eight voices of 8-bit samples and 8- or 16-bit WAV sounds |
| `another_world/wav.py` | the WAV writer of `--wav` |
| `another_world/audio.py` | live sound, piped into a system audio player |
| `another_world/keyboard.py` | raw terminal input, held keys |
| `another_world/text.py` | the font and the English strings |
| `another_world/clock.py` | wall or virtual game clock |
| `another_world/screen.py` | terminal output and frame digests |
| `another_world/glyphs.py` | the glyph for every pixel pattern of each cell layout |
