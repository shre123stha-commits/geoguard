"""Phase 9.2: review-insight maths (pure, offline)."""

from types import SimpleNamespace

from app.db.enums import ConfidenceClass, DetectionStatus
from app.services import insights


def _d(status: str, conf: str, bui: float, sar: float, reason: str | None = None):  # type: ignore[no-untyped-def]
    hist = [SimpleNamespace(reason_code=reason)] if reason else []
    return SimpleNamespace(
        status=DetectionStatus(status),
        confidence=ConfidenceClass(conf),
        d_bui_mean=bui,
        d_sigma_vv_mean=sar,
        history=hist,
    )


def test_too_few_labels_gives_note_only() -> None:
    rows = [_d("confirmed", "high", 0.3, 4.0)] * 3
    ins = insights.compute(rows, 0.15, 2.5)  # type: ignore[arg-type]
    assert ins.suggestions == [] and "appear after" in ins.note
    assert ins.by_class[0].precision == 1.0 and ins.by_class[1].precision is None


def test_suggests_raising_bui_when_dismissed_sit_low() -> None:
    conf = [_d("confirmed", "high", 0.30 + i * 0.01, 3.0) for i in range(8)]
    dis = [_d("dismissed", "medium", 0.16 + i * 0.005, 3.0, "bare_soil") for i in range(8)]
    ins = insights.compute(conf + dis, 0.15, 2.5)  # type: ignore[arg-type]
    assert ins.reviewed == 16 and ins.dismiss_reasons == {"bare_soil": 8}
    bui = next(s for s in ins.suggestions if s.param == "t_bui")
    assert bui.suggested > 0.15 and bui.keeps_confirmed == 8 and bui.drops_dismissed == 8
    assert "kept 8/8 confirmed" in bui.text
    # SAR values don't separate the two groups → no SAR suggestion
    assert all(s.param != "t_sar_db" for s in ins.suggestions)


def test_no_suggestion_when_already_separated() -> None:
    conf = [_d("confirmed", "high", 0.30, 4.0) for _ in range(6)]
    dis = [_d("dismissed", "low", 0.05, 1.0) for _ in range(6)]  # already below thresholds
    ins = insights.compute(conf + dis, 0.15, 2.5)  # type: ignore[arg-type]
    assert ins.suggestions == [] and "already separate" in ins.note
