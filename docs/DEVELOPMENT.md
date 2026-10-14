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

## Running under Python

The same source runs under Python 3.12 or newer, with the benchmark's
stand-in for TurboPython's `tpy` module on the path (see
[Fairness](#fairness)):

```bash
PYTHONPATH=bench/stub python3 aw.py DIR
```

## Benchmark

`bench/` times the engine (the bytecode VM, the polygon rasterizer, page
fills and copies, the music sequencer) under TPy and under other ways of
running the same Python source.

### What is timed

`bench/core.py` is the one driver every runner times. It runs a batch of
three scenes of the DOS release, each from a fresh VM:

| Scene | Part | Untimed frames | Timed frames | Timed frames that change the picture |
|---|---|---:|---:|---:|
| intro | 16001 | 0-599 | 600-1399 | 757 of 800 |
| jail | 16003 | 0-99 | 100-499 | 391 of 400 |
| arena | 16005 | 0-61 | 62-321 | 260 of 260 |

A batch is 1460 timed frames. The ranges come from per-frame digests
and counts of VM bytes fetched, pixels filled and polygons drawn, and
skip stretches where the picture stands still. Arena ends at frame 321:
with no input, the DOS arena's picture is still from frame 322 on. Jail
is VM-heavy, arena raster-heavy, the intro mixed. A scene loads all its
resources in its first frames; the engine counts resource reads, and
core.py fails if one happens inside the timer.

`time.perf_counter_ns()` brackets the engine loop of the timed frames
only. Interpreter start-up, imports, reading the data, building the VM,
the untimed frames and the end-state digest stay outside the timer.
Nothing is drawn or hashed per frame. After the timer, core.py hashes the
state each scene ends in: the four video pages, the palette, the 256
variables, the page indices, the frame count and the clock. Thread and
music state are not in the digest. core.py checks it against the scene's
digest, and a scene that ends in another state fails the run.

`bench.py run` starts every runner once per round, in an order rotated by
one place each round, for 5 rounds; each process runs 10 batches. A
process's time is the median of its batches 4-10; the table gives the
median over the 5 processes, with the smallest and largest in brackets,
and "vs TPy (slower)" divides medians.

### Fairness

- Every runner runs the same engine source, `another_world/`, unchanged.
- The Python runners (CPython, PyPy, Nuitka, mypyc) import `bench/stub`
  as `tpy`: each fixed-width type is `int`, and `Own[T]` is `T`. That is
  sound here because TPy's conversions raise when a value leaves the type's
  range, and the TPy build completes the scenes, so every conversion on
  these inputs is the identity. The runs are deterministic, and every
  runner's end-state digests match.
- mypyc compiles only the modules core.py reaches (mypy rejects an
  annotation in one it does not reach).
- The Shedskin build (`bench/shedskin/build.py`) compiles a copy of the
  sources rewritten only where Shedskin's language stops: `match` as
  if/elif chains, f-strings with format specs as `%` formats, relative
  imports made absolute, `int32(x)` as `int32(int(x))`, the `__future__`
  import dropped and `gzip.open` replaced by a stub. Its own `tpy` stub
  (`bench/shedskin/stubs/tpy.py`) has the fixed-width types as identity
  functions.
- Shedskin needs the bytearray slice-assignment fix of
  [shedskin#1418](https://github.com/shedskin/shedskin/pull/1418), in its
  main branch since commit 765a4053, until a release has it. Released
  0.9.14 converts the whole buffer on every slice assignment: one batch
  takes 751 s (released Shedskin 0.9.14, Amiga data, 2026-10-14).

### Runners

| Runner | Build |
|---|---|
| TPy | 0.7.0.dev0, `tpy -b`, its release build, with g++ 14.2; bounds, integer overflow and conversion checks stay on, elided only where the compiler proves them |
| CPython 3.14 | 3.14.2, uv's python-build-standalone build |
| PyPy 3.11 | PyPy 7.3.20, uv's build, with its JIT |
| Nuitka | Nuitka 4.2.2 on CPython 3.14, in its default accelerated mode, with `--follow-imports` and its default release flags; the build checks that every engine module is compiled |
| mypyc | mypy 2.4.0 on CPython 3.14, opt level 3; the modules load as extensions |
| Shedskin -O3 | Shedskin 1.0-pre with the fix above, g++ 14.2 with `-O3 -std=c++20 -march=native` from build.py's flags file; index bounds checks and negative-index normalisation on |
| Shedskin -O3 --nobounds --nowrap (unchecked) | the same, translated with `--nobounds --nowrap`: neither check, a different safety contract |

### Results

Measured 2026-10-14:

AMD Ryzen 9 5950X 16-Core Processor, Linux 7.0.0-34-generic, pinned to CPU 11; tpy 0.7.0.dev0 (v0.6.2-105-g5cf80fc2c0), CPython 3.14.2, PyPy 7.3.20, Nuitka 4.2.2, mypy 2.4.0, Shedskin 1.0-pre (765a4053) with g++-14 (Ubuntu 14.2.0-4ubuntu2~24.04.1) 14.2.0.

5 processes x 10 batches; a process's batch time is the median of its batches 4-10; median [min-max] over the processes.

| runner | ms per batch | vs TPy (slower) |
|---|---:|---:|
| TPy | 34.7 ms [34.2 ms-36.4 ms] | 1.0x |
| CPython 3.14 | 870 ms [869 ms-883 ms] | 25.1x |
| PyPy 3.11 | 93.5 ms [93.4 ms-94.1 ms] | 2.7x |
| Nuitka (CPython 3.14) | 1265 ms [1257 ms-1286 ms] | 36.5x |
| mypyc (CPython 3.14) | 203 ms [201 ms-204 ms] | 5.8x |
| Shedskin -O3 | 52.6 ms [52.4 ms-53.3 ms] | 1.5x |
| Shedskin -O3 --nobounds --nowrap (unchecked) | 51.7 ms [51.4 ms-52.4 ms] | 1.5x |

### Reproducing

The benchmark uses the files of the original 1991 MS-DOS release, listed
below with their sizes and SHA-256; the GOG edition does not include
them. They go in `data/pc`.

| File | Size | SHA-256 |
|---|---:|---|
| `BANK01` | 209250 | `bd71f3aaf04fbe974c68608fe2cc9fb2debb84b7d8c47fb9e05cf2010979cfaf` |
| `BANK02` | 77608 | `be14b7fdceb96437f7606c31c89ce3ebadd2140778b70d2de38c1a935fad13ca` |
| `BANK03` | 95348 | `f1daf50eda4c58f49d4273560221bf429b2646eca8b7d9290d5bf5086b9e00af` |
| `BANK04` | 58524 | `c61c189527b337f5c318fa2c952b2369343d8fbc1d60c46a0e169b2f3433631d` |
| `BANK05` | 15100 | `f1476710be4770670f01d37763c094026e386673a76bb52e1405a3802d83c177` |
| `BANK06` | 44034 | `6e4a6c7a07b14ad2a069aa2bef7da9c3d7b1e02e4d47b63c604a56de0980c01d` |
| `BANK07` | 98528 | `db1567e7595ccb851bb45a076081edc51fe12489eeeb8447b5cab2cc1a0e8cf2` |
| `BANK08` | 123656 | `7024c5f4d19b64f0fe0613375615f78a19dcdb4dfd780bd1df73c8795eea64bf` |
| `BANK09` | 7396 | `d3bf36bf5e0bc285c751b2e72c030d6382df8ba7d6e0585878c92e208463a803` |
| `BANK0A` | 200120 | `c107f19ee3b8c235d9bb9218ded06ddce9a6d602e1171da32e520e2b3711223a` |
| `BANK0B` | 46296 | `572bf7674c94eea7dcc2631cd50ad2864f42a8f3a02c39fb31bf5db06a18809d` |
| `BANK0C` | 18864 | `4234ac40cf09fa3527c6d3042ffc702f00125a87b60725cadeabed5e3da49448` |
| `BANK0D` | 157396 | `f5ab06e685714ca1a01cac03715ee139b398887215eaf02dbd6fdd3a9a900bb1` |
| `MEMLIST.BIN` | 2940 | `67a83bd7353d45643549e2faba8e567aae4814b259486319996f8bd48dea1a88` |

The tools go in one directory, VENVS, which `--venvs` names (default
`__tpyc__/bench/venvs` in the repository, which git ignores):

    uv python install 3.14 pypy3.11
    uv venv -p 3.14 VENVS/venv-nuitka && VIRTUAL_ENV=VENVS/venv-nuitka uv pip install nuitka==4.2.2
    uv venv -p 3.14 VENVS/venv-mypyc && VIRTUAL_ENV=VENVS/venv-mypyc uv pip install mypy==2.4.0 setuptools
    git clone https://github.com/shedskin/shedskin SHEDSKIN && git -C SHEDSKIN checkout 765a4053
    uv venv VENVS/ssvenv && VIRTUAL_ENV=VENVS/ssvenv uv pip install -e SHEDSKIN

Shedskin is installed editable from the clone: its build reads the
clone's commit for the table. It also needs the Boehm GC headers
(`libgc-dev`) and g++-14 (`build --cxx` names another C++ compiler).
TPY_CHECKOUT is a TPy source checkout at or after commit 5cf80fc2c0,
which has bytearray slice assignment (the 0.6 releases on PyPI do not).
Then:

    python3 bench/bench.py --venvs VENVS build --tpy "uv run --project TPY_CHECKOUT tpy" --shedskin VENVS/ssvenv/bin/shedskin
    python3 bench/bench.py --venvs VENVS run --cpu 11

`build` takes `--only` (some of `tpy,shedskin,nuitka,mypyc`) and records
each build's source hash and tool version; `run` refuses a build whose
sources changed since. `run` takes `--processes` (default 5), `--batches`
(10), `--steady-from` (4), `--cpu N` to pin every process to one CPU (no
pinning by default) and `--runners` (some of `tpy, cpython, pypy, nuitka,
mypyc, shedskin, shedskin-unchecked`). It prints the table and writes the
raw samples to `__tpyc__/bench/results/`, which git ignores.

### Caveats

- TPy builds for generic x86-64; Shedskin builds with `-march=native` and
  without LTO, its defaults (`-flto` gave it 76.5 -> 64.5 ms a batch in a
  profiling run on the Amiga data, 2026-10-14).
- The engine's bulk byte work is slice assignment, which CPython runs in
  C. With byte loops in its place, CPython 3.14 is 62x TPy (6190 ms
  against 99.6 ms; Amiga data, 2026-10-10, a different stub).
- Nuitka is slower than CPython 3.14 with every module compiled and its
  release flags: its code is slower than this CPython's interpreter on
  bytearray stores, int arithmetic and method calls (micro-probe,
  2026-10-14).
- Most of the gap between Shedskin and TPy is allocating the
  `bytes([c]) * n` and slice-read temporaries of each polygon span (Boehm
  GC against malloc, out-of-line runtime calls); TPy pays for those
  temporaries too, and TODO.md in the TPy repository tracks removing them.
- The batch weights three scenes of one engine and is no general score of
  any tool; compile time is not measured.

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
- Sound and music play through the first of `pw-play`, `paplay`, `aplay`
  or SoX's `play` that works (`--mute` turns them off). The 20th
  Anniversary Edition plays its original sound effects (`WGZ/original/`)
  and its recordings of the original's intro and ending music
  (`OGG/original/`), or with `--remastered-audio` its remastered sound
  effects and ambient music. A recording needs `pw-play`, `paplay` or
  `play`, and `--wav` leaves it out.
- Not implemented: saving.

## Layout

| File | What |
|---|---|
| `aw.py` | entry point |
| `bench/` | the benchmark: `core.py` (the timed driver), `bench.py` (`build`, `run`), `stub/` (the `tpy` stub the Python runners use), `shedskin/` (the Shedskin build) |
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
| `another_world/controls.py` | what the engine reads of the controls each frame |
| `another_world/keyboard.py` | raw terminal input, held keys |
| `another_world/text.py` | the font and the English strings |
| `another_world/clock.py` | wall or virtual game clock |
| `another_world/screen.py` | terminal output and frame digests |
| `another_world/glyphs.py` | the glyph for every pixel pattern of each cell layout |
