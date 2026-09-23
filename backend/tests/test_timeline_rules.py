"""Phase 9.3: timeline helpers (offline)."""

from datetime import date
from types import SimpleNamespace

from app.services.timeline import month_range, onset


def test_month_range_wraps_years() -> None:
    ms = month_range(date(2026, 2, 17), 4)
    assert ms == [date(2025, 11, 1), date(2025, 12, 1), date(2026, 1, 1), date(2026, 2, 1)]


def _rows(vals: list[float | None]) -> list:  # type: ignore[type-arg]
    return [
        SimpleNamespace(
            month=date(2024, 1 + i % 12, 1) if i < 12 else date(2025, i - 11, 1), built_frac=v
        )
        for i, v in enumerate(vals)
    ]


def test_onset_needs_a_sustained_step() -> None:
    # flat, one blip, then a real step that holds
    vals = [0.05, 0.06, 0.05, 0.30, 0.05, 0.06, 0.25, 0.27, 0.26]
    assert onset(_rows(vals)) == date(2024, 7, 1)
    # gaps (None) are ignored, not treated as zero
    vals2 = [0.05, None, 0.06, None, 0.05, 0.22, 0.24]
    assert onset(_rows(vals2)) == date(2024, 6, 1)
    assert onset(_rows([0.05, 0.05, 0.06, 0.05])) is None
