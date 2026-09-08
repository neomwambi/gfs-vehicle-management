"""UTC+2 calendar-day rules for availability and immediate bookings."""

from datetime import datetime

import pytest

from app.services.vehicles import _mark_dates_for_hold, free_from_after_return
from app.timeutil import align_immediate_start, local_date


def test_return_before_midday_sast_opens_afternoon_same_day():
    # 11:00 SAST = 09:00 UTC → free from 12:00 SAST (10:00 UTC) same day
    end = datetime(2026, 9, 9, 9, 0, 0)
    assert free_from_after_return(end) == datetime(2026, 9, 9, 10, 0, 0)


def test_return_at_midday_sast_rolls_to_next_local_day():
    # 12:00 SAST = 10:00 UTC → next local day 00:00 SAST (22:00 UTC)
    end = datetime(2026, 9, 9, 10, 0, 0)
    assert free_from_after_return(end) == datetime(2026, 9, 9, 22, 0, 0)


def test_return_after_utc_midday_but_before_sast_midday():
    # 11:30 UTC is 13:30 SAST — afternoon is already closed locally
    end = datetime(2026, 9, 9, 11, 30, 0)
    assert free_from_after_return(end) == datetime(2026, 9, 9, 22, 0, 0)


def test_hold_spanning_utc_midnight_uses_sast_dates():
    unavailable: set[str] = set()
    afternoon_only: set[str] = set()
    # 00:00–10:00 SAST on 9 Sep (22:00 UTC 8 Sep → 08:00 UTC 9 Sep)
    start = datetime(2026, 9, 8, 22, 0, 0)
    end = datetime(2026, 9, 9, 8, 0, 0)
    _mark_dates_for_hold(start, end, unavailable=unavailable, afternoon_only=afternoon_only)
    assert unavailable == set()
    assert afternoon_only == {"2026-09-09"}


def test_full_day_hold_greys_sast_date_not_utc_date():
    unavailable: set[str] = set()
    afternoon_only: set[str] = set()
    # Out from 00:00 SAST through midday 9 Sep → next local day is fully free
    start = datetime(2026, 9, 8, 22, 0, 0)
    end = datetime(2026, 9, 9, 10, 0, 0)
    _mark_dates_for_hold(start, end, unavailable=unavailable, afternoon_only=afternoon_only)
    assert unavailable == {"2026-09-09"}
    assert afternoon_only == set()


def test_immediate_start_after_local_midnight_before_utc_midnight_is_today():
    # 01:00 SAST on 10 Sep = 23:00 UTC on 9 Sep
    now = datetime(2026, 9, 9, 23, 0, 0)
    # Driver picks 08:00 SAST the same local morning = 06:00 UTC 10 Sep
    start = datetime(2026, 9, 10, 6, 0, 0)
    assert local_date(now).isoformat() == "2026-09-10"
    assert align_immediate_start(start, now) == start


def test_immediate_start_future_local_day_rejected():
    now = datetime(2026, 9, 9, 10, 0, 0)  # 12:00 SAST 9 Sep
    start = datetime(2026, 9, 10, 6, 0, 0)  # 08:00 SAST 10 Sep
    with pytest.raises(ValueError, match="today"):
        align_immediate_start(start, now)


def test_immediate_start_past_local_day_clamped_to_today():
    now = datetime(2026, 9, 10, 6, 0, 0)  # 08:00 SAST 10 Sep
    start = datetime(2026, 9, 9, 6, 0, 0)  # 08:00 SAST 9 Sep
    assert align_immediate_start(start, now) == datetime(2026, 9, 10, 6, 0, 0)
