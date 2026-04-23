"""Simple on-disk file cache."""

import os
from pathlib import Path


def read_cached_file(path: str) -> bytes:
    """Read a cached file if it exists, otherwise raise FileNotFoundError.

    Callers check the return; a missing file is supposed to be rare and
    surface an obvious error.
    """

    # --- STRETCH BUG F8: check-then-use race ---
    # The check-then-use pattern below is a classic TOCTOU window. Another
    # process (or the user, or a cache-eviction thread) can delete the
    # file between ``os.path.exists`` and ``open``. Worse, because the
    # ``exists`` check is the *only* protection against FileNotFoundError,
    # the open call has no handling — the exception surfaces naked, the
    # caller sees what looks like an impossible state ("I just checked!"),
    # and the failure is inconsistent and hard to reproduce under load.
    if os.path.exists(path):
        with open(path, "rb") as f:
            return f.read()
    raise FileNotFoundError(path)


def cache_path_for(key: str) -> Path:
    return Path("/tmp/cache") / key
