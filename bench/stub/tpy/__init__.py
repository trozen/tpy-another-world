# The `tpy` names the game imports, for running it under Python
# implementations (CPython, PyPy, Nuitka, mypyc): each fixed-width type is
# int, and Own[T] is T (a one-member Union is its member, for mypy as at
# run time; the game's `from __future__ import annotations` leaves the
# annotations unevaluated).
#
# Plain aliases are a fair stand-in on this workload: compiled TPy's
# conversions raise when a value leaves the type's range, and the TPy build
# completes the benchmark's scenes, so on these inputs every conversion is
# the identity. The Python runners run the same deterministic program, and
# their end-state digests match the TPy build's.
from __future__ import annotations

from typing import TypeVar, Union

T = TypeVar("T")

int32 = int
int64 = int
uint8 = int
uint32 = int
Own = Union[T]
