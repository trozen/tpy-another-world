# The music sequencer, silent: it steps through a module's patterns on the
# game clock only for the marks the bytecode synchronizes with.
from __future__ import annotations

from tpy import int32

from .resource import be16
from .video import s16

MARK_NOTE = 0xFFFD


def _event_delay(delay: int32) -> int32:
    return (delay * 60 // 7050) & 0xFFFF


class Music:
    module: bytes
    playing: bool
    delay: int32
    next_event: int32
    order: int32
    num_orders: int32
    pos: int32
    # The last mark reached, for the VM to copy into its mark variable.
    mark: int32
    mark_pending: bool

    def __init__(self) -> None:
        self.module = b""
        self.playing = False
        self.delay = 0
        self.next_event = 0
        self.order = 0
        self.num_orders = 0
        self.pos = 0
        self.mark = 0
        self.mark_pending = False

    def load(self, module: bytes, delay: int32, order: int32) -> None:
        self.module = module
        self.order = order
        self.num_orders = be16(module, 0x3E)
        if delay == 0:
            delay = be16(module, 0)
        self.delay = _event_delay(delay)

    def start(self, now: int32) -> None:
        self.pos = 0
        self.playing = True
        self.next_event = now + self.delay

    def set_delay(self, delay: int32) -> None:
        self.delay = _event_delay(delay)

    def stop(self) -> None:
        self.playing = False

    def update(self, now: int32) -> None:
        """Runs every pattern row that has come due by `now`."""
        while self.playing and self.next_event <= now:
            self._step()
            if self.delay == 0:
                self.playing = False
            self.next_event += self.delay

    def _step(self) -> None:
        pattern = int32(self.module[0x40 + self.order])
        p = 0xC0 + self.pos + pattern * 1024
        for _ in range(4):
            if be16(self.module, p) == MARK_NOTE:
                self.mark = s16(be16(self.module, p + 2))
                self.mark_pending = True
            p += 4
        self.pos += 16
        if self.pos >= 1024:
            self.pos = 0
            self.order = (self.order + 1) & 0xFF
            if self.order == self.num_orders:
                self.playing = False
