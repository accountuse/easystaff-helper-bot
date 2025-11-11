"""
Utility functions for date/time and numeric formatting.

- format_datetime: timezone-aware datetime formatting for user display.
- trunc2: truncate decimals to 2 places without rounding (financial-style display).
- trunc2_str: string presentation helper for trunc2 with fixed 2 decimals.
"""

import logging
from typing import Optional, Union
from datetime import datetime
from decimal import Decimal, ROUND_DOWN
from config.settings import Settings

logger = logging.getLogger(__name__)


def format_datetime(
    dt_str: Optional[str],
    fmt: str = "%d.%m.%Y %H:%M:%S %Z",
    default: str = "unknown date"
) -> str:
    """
    Format ISO datetime string to server timezone for display.

    - Accepts ISO-8601 with or without timezone; also handles 'Z' suffix (UTC).
    - If input is naive (no tzinfo), it is interpreted in server timezone.
    - If input is aware, it is converted to server timezone.
    """
    if not dt_str:
        return default
    try:
        tz = Settings.SERVER_TZ

        # Normalize 'Z' (Zulu/UTC) suffix to '+00:00' for fromisoformat compatibility
        s = dt_str.strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"

        dt = datetime.fromisoformat(s)

        # Attach/convert timezone
        if dt.tzinfo is None:
            # pytz-style timezone (has .localize) vs zoneinfo (no .localize)
            if hasattr(tz, "localize"):
                dt = tz.localize(dt)  # pytz
            else:
                dt = dt.replace(tzinfo=tz)  # zoneinfo: interpret as server TZ
        else:
            dt = dt.astimezone(tz)

        return dt.strftime(fmt)
    except Exception as e:
        logger.debug(f"Failed to parse/format datetime '{dt_str}': {e}")
        return default


NumberLike = Union[float, int, str, Decimal]


def trunc2(x: NumberLike) -> float:
    """
    Truncate a numeric value to 2 decimal places without rounding.

    Uses Decimal.quantize with ROUND_DOWN to avoid rounding up the last digit,
    e.g., 1342.455 -> 1342.45 and 10.999 -> 10.99. Converts via str to avoid
    binary float artifacts. Accepts float|int|str|Decimal.

    Returns a float suitable for formatting with ':.2f'.
    """
    d = Decimal(str(x)).quantize(Decimal("0.00"), rounding=ROUND_DOWN)
    val = float(d)
    # Normalize negative zero to plain zero for prettier display
    if val == 0.0:
        val = 0.0
    return val


def trunc2_str(x: NumberLike) -> str:
    """
    Truncate to 2 decimals without rounding and return a string with exactly 2 decimals.

    Example:
      trunc2_str(1342.455) -> "1342.45"
      trunc2_str("10.9")   -> "10.90"
    """
    return f"{trunc2(x):.2f}"
