"""Shared HTTP 429 handling for rate sources."""

from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

# Upper bound for server-supplied Retry-After values, so a bogus or hostile
# header cannot silence a source for hours.
MAX_RETRY_AFTER = 600.0


class RateLimitedError(OSError):
    """Raised on HTTP 429; carries how long (seconds) the caller should back off."""

    def __init__(self, retry_after: float, message: str = "Rate limited"):
        super().__init__(f"{message} (retry after {retry_after:.0f}s)")
        self.retry_after = retry_after


def parse_retry_after(value: str | None, default: float, *, now: datetime | None = None) -> float:
    """Parse a Retry-After header (delta-seconds or HTTP-date) into seconds.

    Missing, invalid, or negative values (including dates in the past) yield `default`.
    The result is capped at MAX_RETRY_AFTER.
    """
    seconds = _parse_seconds(value, now or datetime.now(UTC))
    if seconds is None or seconds < 0:
        return min(default, MAX_RETRY_AFTER)
    return min(seconds, MAX_RETRY_AFTER)


def _parse_seconds(value: str | None, now: datetime) -> float | None:
    if value is None or not value.strip():
        return None
    value = value.strip()
    if value.isascii() and value.isdigit():
        return float(value)
    if value.startswith("-") and value[1:].isdigit():
        return -float(value[1:])
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return (when - now).total_seconds()
