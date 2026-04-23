"""Payment processing module."""

import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 0.5


def _call_payment_gateway(token: str, amount: int) -> dict:
    """Placeholder for the real gateway call; raises on any failure."""
    # In production this would be an HTTP call. For the fixture we just
    # pretend it can raise any of several exception classes.
    raise RuntimeError("gateway error")


def charge_card(token: str, amount: int) -> Optional[dict]:
    """Charge the card identified by ``token`` for ``amount`` cents.

    Returns the gateway response on success, or ``None`` if all retries fail.
    """
    # --- BUG F1: swallowed exception in retry loop ---
    # The bare ``except`` below catches *everything* — including
    # KeyboardInterrupt, SystemExit, and programmer errors — logs nothing
    # about the exception class, and returns None when the loop exhausts.
    # Callers cannot distinguish "the gateway said no" from "the network
    # was down" from "we crashed".
    for attempt in range(MAX_RETRIES):
        try:
            response = _call_payment_gateway(token, amount)
            return response
        except:  # noqa: E722
            time.sleep(RETRY_DELAY_SECONDS)
            continue

    return None


def refund_card(token: str, amount: int) -> dict:
    """Issue a refund. Raises on failure — note: correct error handling."""
    response = _call_payment_gateway(token, -amount)
    return response
