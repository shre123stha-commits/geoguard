"""Offline unit tests for cron parsing and window rules (task 4.6)."""

from datetime import UTC, date, datetime

import pytest

from app.services.scheduler import CronError, compute_windows, next_run, parse_cron


def test_presets_and_next_run() -> None:
    after = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)  # a Saturday
    nxt = next_run("weekly", after)
    assert nxt == datetime(2026, 9, 21, 2, 0, tzinfo=UTC)  # Monday 02:00 UTC
    assert next_run("monthly", after) == datetime(2026, 10, 1, 2, 0, tzinfo=UTC)
    assert next_run("*/15 * * * *", after) == datetime(2026, 9, 19, 12, 15, tzinfo=UTC)
    # standard cron numbering: 0/7 = Sunday, 5 = Friday
    assert next_run("0 6 * * 0", after) == datetime(2026, 9, 20, 6, 0, tzinfo=UTC)
    assert next_run("0 6 * * 5", after) == datetime(2026, 9, 25, 6, 0, tzinfo=UTC)
    assert next_run("0 6 * * fri", after) == datetime(2026, 9, 25, 6, 0, tzinfo=UTC)


@pytest.mark.parametrize("bad", ["", "* * *", "61 * * * *", "0 2 * * 8"])
def test_bad_cron_rejected(bad: str) -> None:
    with pytest.raises(CronError):
        parse_cron(bad)


def test_windows_same_season_previous_year() -> None:
    w = compute_windows({}, 30, today=date(2026, 3, 31))
    assert w.current == (date(2026, 3, 2), date(2026, 3, 31))
    assert w.baseline == (date(2025, 3, 2), date(2025, 3, 31))


def test_windows_years_back_and_leap_day() -> None:
    w = compute_windows(
        {"mode": "years_back", "years": 3, "window_days": 60}, 30, date(2028, 2, 29)
    )
    assert w.baseline == (date(2024, 12, 31), date(2025, 2, 28))


def test_windows_fixed_and_invalid() -> None:
    w = compute_windows(
        {"mode": "fixed", "baseline_start": "2020-01-15", "baseline_end": "2020-03-31"},
        30,
        date(2026, 3, 31),
    )
    assert w.baseline == (date(2020, 1, 15), date(2020, 3, 31))
    with pytest.raises(ValueError):
        compute_windows(
            {"mode": "fixed", "baseline_start": "2026-03-20", "baseline_end": "2026-03-25"},
            30,
            date(2026, 3, 31),
        )
