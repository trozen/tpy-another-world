# The benchmark's engine driver, the same program under every runner: the
# TPy build (`tpy -L . -b bench/core.py`), CPython, PyPy, Nuitka, mypyc and
# Shedskin (whose build rewrites this file like the engine).
#
# Usage: core.py DIR BATCHES
#
# Runs the scenes below BATCHES times over, each from a fresh VM. A scene
# starts its game part and runs untimed up to its first timed frame (its
# resources are loaded by then), then runs on to its end frame inside the
# timer. Nothing is drawn or digested while timed; after the timer, a
# digest of the state the scene ended in (the four pages, the palette, the
# variables, the clock) keeps the work observable and is checked against
# the scene's `state`, the digest of the DOS data's run. Each scene prints
#     end SCENE BATCH NANOSECONDS STATE
# and a scene that ends in another state fails the run (exit status 1)
# after naming it; after an engine change, those messages hold the new
# digests.
from __future__ import annotations

import sys
import time

from typing import Final

from tpy import int32, int64

from another_world.clock import Clock
from another_world.controls import Input
from another_world.resource import Resources
from another_world.screen import MODE_COUNT, RENDER_HALF, Screen
from another_world.vm import VM

FNV_OFFSET: Final[int64] = 2166136261
FNV_PRIME: Final[int64] = 16777619

class Scene:
    """A game part's frames from `first` (the first timed one) to `end`,
    and the digest of the state they end in."""

    name: str
    part: int32
    first: int32
    end: int32
    state: int64

    def __init__(self, name: str, part: int32, first: int32, end: int32,
                 state: int64) -> None:
        self.name = name
        self.part = part
        self.first = first
        self.end = end
        self.state = state


# The frame ranges change picture on nearly every frame and load no
# resources; see docs/DEVELOPMENT.md "Benchmark" for how they were chosen.
SCENES: list[Scene] = [
    Scene("intro", 16001, 600, 1400, 0x8FE22FBF),
    Scene("jail", 16003, 100, 500, 0x19B21F62),
    Scene("arena", 16005, 62, 322, 0xF9B51DF0),
]


def run_until(vm: VM, inp: Input, frames: int32) -> None:
    """The engine loop of a headless `aw.py --frames` run."""
    while not vm.screen.done and vm.screen.frames < frames:
        vm.apply_requests()
        vm.update_input(inp)
        vm.run_frame()
        vm.mixer.take()


def mix(h: int64, v: int64) -> int64:
    return ((h ^ v) * FNV_PRIME) & 0xFFFFFFFF


def state_digest(vm: VM) -> int64:
    h = FNV_OFFSET
    for i in range(len(vm.video.mem)):
        h = mix(h, int64(vm.video.mem[i]))
    for i in range(len(vm.video.palette)):
        h = mix(h, int64(vm.video.palette[i]))
    for i in range(len(vm.vars)):
        h = mix(h, int64(vm.vars[i] & 0xFFFF))
    h = mix(h, int64(vm.video.front))
    h = mix(h, int64(vm.video.back))
    h = mix(h, int64(vm.video.work))
    h = mix(h, int64(vm.clock.now()))
    return mix(h, int64(vm.screen.frames))


def run_scene(data: str, part: int32, first: int32, end: int32) -> tuple[int64, int64]:
    """(nanoseconds of the timed frames, digest of the end state)."""
    vm = VM(Resources(data), Clock(True), Screen(MODE_COUNT, RENDER_HALF, -1), 0)
    inp = Input()
    vm.init_for_part(part)
    run_until(vm, inp, first)
    loads = vm.res.loads
    start = time.perf_counter_ns()
    run_until(vm, inp, end)
    elapsed = time.perf_counter_ns() - start
    if vm.res.loads != loads:
        raise RuntimeError(f"part {part} read resources between frames {first} and {end}")
    if vm.screen.frames != end:
        raise RuntimeError(f"part {part} stopped at frame {vm.screen.frames} of {end}")
    return (elapsed, state_digest(vm))


def main() -> int32:
    if len(sys.argv) != 3:
        print("usage: core.py DIR BATCHES", file=sys.stderr)
        return 2
    data = sys.argv[1]
    batches = int32(int(sys.argv[2]))
    status = 0
    for batch in range(1, batches + 1):
        for scene in SCENES:
            ns, state = run_scene(data, scene.part, scene.first, scene.end)
            print(f"end {scene.name} {batch} {ns} {state:08x}")
            if state != scene.state:
                print(f"core.py: {scene.name} batch {batch} ended in state {state:08x}, "
                      f"not {scene.state:08x}", file=sys.stderr)
                status = 1
    return status


if __name__ == "__main__":
    sys.exit(main())
