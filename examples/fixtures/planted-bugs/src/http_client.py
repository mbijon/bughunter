"""HTTP client with a primary/backup fallback."""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _fetch_from_primary(url: str) -> dict[str, Any]:
    raise ConnectionError("primary unreachable")


def _fetch_from_backup(url: str) -> dict[str, Any]:
    raise TimeoutError("backup timed out")


def fetch_with_fallback(url: str) -> dict[str, Any]:
    """Fetch from primary, fall back to backup on any primary failure."""

    # --- BUG F7: retry/fallback that masks the original error class ---
    # Two problems layered together:
    #   1. The broad ``except Exception`` captures the primary's error
    #      but we never log it or wrap it. The root cause is silently
    #      discarded.
    #   2. If the backup *also* fails, the caller sees a TimeoutError
    #      (the backup's error class) and has no idea the primary had a
    #      ConnectionError — which is a materially different class of
    #      failure and would drive different ops response (DNS vs load).
    try:
        return _fetch_from_primary(url)
    except Exception:
        return _fetch_from_backup(url)
