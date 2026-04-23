"""Small pure utility functions. No bugs intentionally planted here."""


def clamp(value: int, low: int, high: int) -> int:
    """Clamp ``value`` to the inclusive range [low, high]."""
    if low > high:
        raise ValueError("low must be <= high")
    return max(low, min(value, high))


def chunks(items: list, size: int) -> list[list]:
    """Split ``items`` into lists of ``size``, with the tail possibly shorter."""
    if size <= 0:
        raise ValueError("size must be positive")
    return [items[i : i + size] for i in range(0, len(items), size)]


def is_non_empty(value: object) -> bool:
    """True iff ``value`` is not None and not an empty string/list/dict."""
    if value is None:
        return False
    if isinstance(value, (str, list, dict, tuple, set)):
        return len(value) > 0
    return True
