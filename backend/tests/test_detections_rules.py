"""Offline checks for Phase 5 rules: file path guard (5.3) and transition table (5.2)."""

from pathlib import Path

import pytest
from fastapi import HTTPException

from app.api.files import resolve_file
from app.db.enums import DetectionStatus
from app.schemas.detections import ADMIN_ONLY_TRANSITIONS, TRANSITIONS


def test_resolve_file_only_serves_allowed_roots(tmp_path: Path) -> None:
    (tmp_path / "evidence" / "s" / "d").mkdir(parents=True)
    (tmp_path / "evidence" / "s" / "d" / "before_rgb.png").write_bytes(b"x")
    (tmp_path / "secret.png").write_bytes(b"x")
    (tmp_path / "evidence" / "notes.txt").write_text("x")

    assert resolve_file(tmp_path, "evidence/s/d/before_rgb.png").name == "before_rgb.png"
    for bad in (
        "secret.png",
        "../secret.png",
        "evidence/../secret.png",
        "evidence/notes.txt",  # extension not allowed
        "evidence/s/d/missing.png",
        "reports",
        "",
        "/etc/passwd",
    ):
        with pytest.raises(HTTPException) as exc:
            resolve_file(tmp_path, bad)
        assert exc.value.status_code == 404


def test_transition_table_matches_appflow() -> None:
    S = DetectionStatus  # noqa: N806
    assert TRANSITIONS[S.new] == {S.confirmed, S.dismissed, S.field_visit}
    assert TRANSITIONS[S.field_visit] == {S.confirmed, S.dismissed}
    assert TRANSITIONS[S.confirmed] == {S.dismissed}
    assert TRANSITIONS[S.dismissed] == {S.new}
    assert ADMIN_ONLY_TRANSITIONS == {(S.dismissed, S.new)}
    # nothing may jump straight from confirmed back to new or field_visit
    assert S.new not in TRANSITIONS[S.confirmed] and S.field_visit not in TRANSITIONS[S.confirmed]
