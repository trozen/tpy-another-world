# The command line and the engine loop.
from __future__ import annotations

import os
import sys
from argparse import ArgumentParser

from tpy import int32

from .clock import Clock
from .resource import PART_INTRO, Resources
from .screen import MODE_COMPARE, MODE_DIGESTS, MODE_SUMMARY, MODE_TERMINAL, RENDER_NAMES, Screen
from .vm import VM


def main() -> int32:
    parser = ArgumentParser(description="Plays the Another World intro in the terminal.")
    parser.add_argument("--data", default="data",
                        help="directory with MEMLIST.BIN and the BANKxx files")
    parser.add_argument("--digests", action="store_true",
                        help="print a digest of every frame instead of drawing")
    parser.add_argument("--render", default="half",
                        choices=["half", "quad", "sextant", "octant", "braille"],
                        help="cell glyphs: half blocks (1x2 pixels a cell), quadrants (2x2), "
                        "sextants (2x3), octants (2x4, needs a font with Unicode 16) or braille (2x4)")
    parser.add_argument("--compare", type=int, default=-1, metavar="FRAME",
                        help="print frame FRAME once with every --render option, then quit")
    parser.add_argument("--seed", type=int, default=0, help="the game's random seed")
    args = parser.parse_args()

    # Headless runs use a virtual clock, so they finish at once and repeat.
    mode = MODE_TERMINAL
    if args.compare >= 0:
        mode = MODE_COMPARE
    elif args.digests:
        mode = MODE_DIGESTS
    elif not os.isatty(1):
        mode = MODE_SUMMARY
    res = Resources(args.data)
    clock = Clock(mode != MODE_TERMINAL)
    screen = Screen(mode, int32(RENDER_NAMES.index(args.render)), int32(args.compare))
    vm = VM(res, clock, screen, int32(args.seed))
    vm.screen.begin()
    vm.init_for_part(PART_INTRO)
    while (vm.res.requested_part == 0 or vm.res.requested_part == PART_INTRO) \
            and not vm.screen.done:
        vm.apply_requests()
        vm.update_input()
        vm.run_frame()
    vm.screen.end()
    return 0
