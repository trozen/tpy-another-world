# The command line and the engine loop.
from __future__ import annotations

import argparse
import os
import sys
from argparse import ArgumentParser

from tpy import int32

from .clock import Clock
from .keyboard import Input, Keyboard
from .resource import GAME_PART_FIRST, GAME_PART_LAST, PART_INTRO, Resources
from .screen import MODE_COMPARE, MODE_DIGESTS, MODE_SUMMARY, MODE_TERMINAL, RENDER_NAMES, Screen
from .vm import VM


def main() -> int32:
    parser = ArgumentParser(
        prog="aw.py", formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Plays Another World in the terminal.\n"
        "\n"
        "game data:\n"
        "  You can get the game on GOG: Another World 20th Anniversary\n"
        "  Edition, which also includes the Amiga version.\n"
        "\n"
        "  Point DIR at one of these releases:\n"
        "  20th Anniversary   the install directory, or its game/ directory\n"
        "  DOS                the directory with MEMLIST.BIN and BANK01 to BANK0D\n"
        "  Amiga              the directory with the two .adf floppy images from\n"
        "                     the unzipped archive, or with the bankNN files on\n"
        "                     them\n"
        "\n"
        "keys:\n"
        "  left, right   walk; run with space held\n"
        "  up            jump\n"
        "  down          crouch\n"
        "  space, enter  action: kick, shoot, or run with an arrow; skips the intro\n"
        "  c             the password screen, to start a level by its code\n"
        "  p             pause\n"
        "  Ctrl-C        quit\n"
        "\n"
        "terminal:\n"
        "  For the best experience, run the game in Ghostty with -8.\n"
        "\n"
        "  Use a terminal with the kitty keyboard protocol: Ghostty, kitty,\n"
        "  WezTerm, foot or Alacritty. Only such terminals report key releases,\n"
        "  and the game needs to know how long a key is held; in others, such as\n"
        "  GNOME Terminal, a key counts as held while it repeats, so a tap lasts\n"
        "  about half a second. The terminal also needs 24-bit color; the picture\n"
        "  is scaled to fit the window.\n"
        "\n"
        "  Use -8 where the terminal can show it, -2 (the default) elsewhere.\n"
        "  -8 draws 2x4 pixels a cell, the sharpest picture, with octant\n"
        "  characters (Unicode 16) that most fonts lack; -6 needs sextants\n"
        "  (Unicode 13). Ghostty draws these characters itself, whatever the\n"
        "  font; -2 works with any font.")
    parser.add_argument("data", metavar="DIR", help="the game data (see game data above)")
    parser.add_argument("--part", type=int, default=16001,
                        help="the game part to start in, from 16000 (the copy protection, "
                        "DOS and Amiga only) to 16009 (the password screen); 16001 is the intro")
    parser.add_argument("--frames", type=int, default=0, metavar="N",
                        help="stop after N frames; a run that is not in a terminal otherwise "
                        "stops when its first part ends")
    parser.add_argument("--digests", action="store_true",
                        help="print a digest of every frame instead of drawing")
    parser.add_argument("-2", dest="half", action="store_true",
                        help="half blocks, 1x2 pixels a cell (the default)")
    parser.add_argument("-4", dest="quad", action="store_true",
                        help="quadrants, 2x2 pixels a cell")
    parser.add_argument("-6", dest="sextant", action="store_true",
                        help="sextants, 2x3 pixels a cell")
    parser.add_argument("-8", dest="octant", action="store_true",
                        help="octants, 2x4 pixels a cell: the sharpest")
    parser.add_argument("-r", "--render", default="",
                        choices=["half", "quad", "sextant", "octant", "braille"],
                        metavar="MODE",
                        help="the cell glyphs by name: half, quad, sextant, octant (as "
                        "-2 to -8) or braille (2x4 dots)")
    parser.add_argument("--compare", type=int, default=-1, metavar="FRAME",
                        help="print frame FRAME once with every --render option, then quit")
    parser.add_argument("--seed", type=int, default=0, help="the game's random seed")
    # A bare run shows the help, like --help.
    argv: list[str] = []
    for arg in sys.argv[1:]:
        argv.append(arg)
    if len(argv) == 0:
        argv.append("--help")
    args = parser.parse_args(argv)
    part = int32(args.part)
    if part < GAME_PART_FIRST or part > GAME_PART_LAST:
        print(f"aw.py: error: --part must be between {GAME_PART_FIRST} and {GAME_PART_LAST}",
              file=sys.stderr)
        return 2

    # Headless runs use a virtual clock, so they finish at once and repeat.
    mode = MODE_TERMINAL
    if args.compare >= 0:
        mode = MODE_COMPARE
    elif args.digests:
        mode = MODE_DIGESTS
    elif not os.isatty(1):
        mode = MODE_SUMMARY
    clock = Clock(mode != MODE_TERMINAL)
    render = args.render
    picked = 0 if render == "" else 1
    for name, on in [("half", args.half), ("quad", args.quad),
                     ("sextant", args.sextant), ("octant", args.octant)]:
        if on:
            render = name
            picked += 1
    if picked > 1:
        print("aw.py: error: choose one of -2, -4, -6, -8 and -r", file=sys.stderr)
        return 2
    if render == "":
        render = "half"
    screen = Screen(mode, int32(RENDER_NAMES.index(render)), int32(args.compare))
    try:
        vm = VM(Resources(args.data), clock, screen, int32(args.seed))
    except (OSError, ValueError) as e:
        print(f"aw.py: error: {e}", file=sys.stderr)
        return 1
    if part == GAME_PART_FIRST and not vm.res.has_protection:
        print("aw.py: error: the 20th Anniversary Edition has no copy protection part (16000)",
              file=sys.stderr)
        return 2
    keyboard = Keyboard(mode == MODE_TERMINAL)
    inp = Input()
    max_frames = int32(args.frames)
    stop_after_part = mode != MODE_TERMINAL and max_frames == 0
    vm.screen.begin()
    keyboard.begin()
    # Missing or damaged data can surface at any part start; the message is
    # printed once the terminal is restored.
    failure = ""
    try:
        vm.init_for_part(part)
        while not vm.screen.done and not inp.quit:
            if max_frames > 0 and vm.screen.frames >= max_frames:
                break
            if stop_after_part and vm.res.requested_part != 0 \
                    and vm.res.requested_part != part:
                break
            vm.apply_requests()
            keyboard.poll(inp, vm.clock.now())
            vm.update_input(inp)
            if inp.pause:
                inp.pause = False
                current = vm.res.current_part
                # The original ignores pause during the protection and the
                # intro; the password screen needs the letter p.
                if current != GAME_PART_FIRST and current != PART_INTRO \
                        and current != GAME_PART_LAST:
                    wait_for_unpause(keyboard, inp, vm.clock)
            vm.run_frame()
    except (OSError, ValueError) as e:
        failure = str(e)
    finally:
        keyboard.end()
        vm.screen.end()
    if failure != "":
        print(f"aw.py: error: {failure}", file=sys.stderr)
        return 1
    return 0


def wait_for_unpause(keyboard: Keyboard, inp: Input, clock: Clock) -> None:
    while not inp.pause and not inp.quit:
        clock.sleep(50)
        keyboard.poll(inp, clock.now())
    inp.pause = False
