# The `tpy` names the game imports, for the Shedskin build: each
# fixed-width type is the identity, as in bench/stub, the stub every other
# Python runner gets, and for the same reason (see its header). They stay
# functions, and build.py wraps their argument in int(), so Shedskin's type
# inference sees one int type where the game also converts floats and
# bools.


def int8(value=0):
    return value


def int16(value=0):
    return value


def int32(value=0):
    return value


def int64(value=0):
    return value


def uint8(value=0):
    return value


def uint16(value=0):
    return value


def uint32(value=0):
    return value


def uint64(value=0):
    return value


class Own:
    """Ownership transfer in TPy; only named in annotations, which Shedskin
    does not read."""

