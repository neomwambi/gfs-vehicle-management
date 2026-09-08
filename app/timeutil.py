"""Calendar-day helpers in the app business timezone (UTC+2).

SQLite stores naive UTC. Convert to APP_TIMEZONE before taking .date() / midday.
"""

from __future__ import annotations

from datetime import date, datetime, time, timezone

from app.config import APP_TIMEZONE

UTC = timezone.utc


def as_utc(dt: datetime) -> datetime:
    """Treat naive datetimes as UTC (storage convention)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def to_local(dt: datetime) -> datetime:
    return as_utc(dt).astimezone(APP_TIMEZONE)


def local_date(dt: datetime) -> date:
    return to_local(dt).date()


def combine_local(d: date, t: time) -> datetime:
    """Local wall clock → naive UTC for SQLite storage and comparisons."""
    return datetime.combine(d, t, tzinfo=APP_TIMEZONE).astimezone(UTC).replace(tzinfo=None)


def align_immediate_start(start: datetime, now: datetime) -> datetime:
    """
    Immediate bookings must start on the current local calendar day.
    start/now are naive UTC (or timezone-aware).
    Raises ValueError if start falls on a future local day.
    If start is a past local day, keep the local time and move it to today.
    """
    start_day = local_date(start)
    today = local_date(now)
    if start_day > today:
        raise ValueError("Immediate start must be today")
    if start_day < today:
        return combine_local(today, to_local(start).time())
    if start.tzinfo is not None:
        return as_utc(start).replace(tzinfo=None)
    return start
