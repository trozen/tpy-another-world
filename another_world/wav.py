# A WAV file of 16-bit mono samples, written as they come; the sizes in its
# header are filled in when it is closed, unless it is a pipe.
from __future__ import annotations

import os

from tpy import int32, int64

HEADER_SIZE = 44


def _le16(v: int32) -> bytes:
    return bytes([v & 0xFF, (v >> 8) & 0xFF])


def _le32(v: int64) -> bytes:
    return bytes([int32(v & 0xFF), int32((v >> 8) & 0xFF), int32((v >> 16) & 0xFF),
                  int32((v >> 24) & 0xFF)])


def _header(rate: int32, data_size: int64) -> bytes:
    return (b"RIFF" + _le32(int64(36) + data_size) + b"WAVEfmt " + _le32(16)
            + _le16(1) + _le16(1)  # PCM, mono
            + _le32(rate) + _le32(int64(rate) * 2) + _le16(2) + _le16(16)
            + b"data" + _le32(data_size))


class WavWriter:
    fd: int64
    rate: int32
    size: int64

    def __init__(self, path: str, rate: int32) -> None:
        self.fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
        self.rate = rate
        self.size = 0
        os.write(self.fd, _header(rate, 0))

    def write(self, samples: bytes) -> None:
        if len(samples) > 0:
            os.write(self.fd, samples)
            self.size += int64(len(samples))

    def close(self) -> None:
        try:
            # A pipe cannot seek: its reader gets the header with sizes of 0.
            try:
                os.lseek(self.fd, 0, os.SEEK_SET)
            except OSError:
                return
            os.write(self.fd, _header(self.rate, self.size))
        finally:
            os.close(self.fd)
