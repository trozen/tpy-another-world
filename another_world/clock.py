# Game time in milliseconds: the wall clock, or a virtual one that only moves
# when the engine says so (1 ms per frame, plus every sleep), which makes a
# run repeatable.
from __future__ import annotations

import time

from tpy import int32


class Clock:
    virtual: bool
    t: int32
    start: float

    def __init__(self, virtual: bool) -> None:
        self.virtual = virtual
        self.t = 0
        self.start = time.monotonic()

    def now(self) -> int32:
        if self.virtual:
            return self.t
        return int32((time.monotonic() - self.start) * 1000.0)

    def tick(self) -> None:
        if self.virtual:
            self.t += 1

    def sleep(self, ms: int32) -> None:
        if self.virtual:
            self.t += ms
        else:
            time.sleep(ms / 1000)
