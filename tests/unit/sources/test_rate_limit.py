"""Unit tests for rate_oracle.sources.rate_limit."""

from datetime import UTC, datetime
from email.utils import format_datetime

import pytest

from rate_oracle.sources.rate_limit import MAX_RETRY_AFTER, RateLimitedError, parse_retry_after

DEFAULT = 63.0
NOW = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)


class TestRateLimitedError:
    def test_is_oserror_and_carries_retry_after(self):
        err = RateLimitedError(120.0)
        assert isinstance(err, OSError)
        assert err.retry_after == 120.0


class TestParseRetryAfter:
    def test_integer_seconds(self):
        assert parse_retry_after("120", DEFAULT) == 120.0

    def test_integer_seconds_with_whitespace(self):
        assert parse_retry_after(" 30 ", DEFAULT) == 30.0

    def test_http_date(self):
        header = format_datetime(datetime(2025, 1, 1, 12, 2, 0, tzinfo=UTC), usegmt=True)
        assert parse_retry_after(header, DEFAULT, now=NOW) == 120.0

    def test_http_date_in_past_falls_back(self):
        header = format_datetime(datetime(2025, 1, 1, 11, 0, 0, tzinfo=UTC), usegmt=True)
        assert parse_retry_after(header, DEFAULT, now=NOW) == DEFAULT

    @pytest.mark.parametrize("value", [None, "", "   "])
    def test_missing_falls_back(self, value):
        assert parse_retry_after(value, DEFAULT) == DEFAULT

    @pytest.mark.parametrize("value", ["soon", "12.5s", "Not, a date"])
    def test_garbage_falls_back(self, value):
        assert parse_retry_after(value, DEFAULT) == DEFAULT

    def test_negative_falls_back(self):
        assert parse_retry_after("-5", DEFAULT) == DEFAULT

    def test_capped_at_max(self):
        assert parse_retry_after("999999", DEFAULT) == MAX_RETRY_AFTER
