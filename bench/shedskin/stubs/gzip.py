# Shedskin has no gzip; only the 20th Anniversary Edition's files are
# gzipped, so this build reads the DOS and Amiga data only. build.py turns
# the game's `gzip.open` into `gzip.gzopen`: Shedskin takes no module
# function named like a builtin.


def gzopen(path: str):
    if path != "":
        raise OSError(path + ": gzip is not available in the Shedskin build")
    # Never reached; it gives the result the type of a file `with` takes.
    return open(path, "rb")
