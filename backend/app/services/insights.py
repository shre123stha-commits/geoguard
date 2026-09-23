"""Review insights (Phase 9.2): what your confirm/dismiss decisions say about the thresholds.

Every review is a free label. This module turns the reviewed detections into (a) a precision
read-out per confidence class and (b) a suggested `t_bui` / `t_sar_db` that would have kept the
confirmed ones while dropping the most dismissed ones. Suggestions are advisory: nothing is
changed automatically, and fewer than MIN_LABELS reviews yields no suggestion at all.
"""

from dataclasses import dataclass, field

from app.db.enums import ConfidenceClass, DetectionStatus
from app.db.models import Detection

MIN_LABELS = 10  # below this the numbers are noise
GRID_BUI = [round(0.10 + 0.01 * i, 2) for i in range(0, 21)]  # 0.10 … 0.30
GRID_SAR = [round(1.5 + 0.25 * i, 2) for i in range(0, 11)]  # 1.5 … 4.0 dB


@dataclass
class ClassStat:
    confidence: str
    confirmed: int = 0
    dismissed: int = 0

    @property
    def precision(self) -> float | None:
        n = self.confirmed + self.dismissed
        return None if n == 0 else self.confirmed / n


@dataclass
class Suggestion:
    param: str
    current: float
    suggested: float
    keeps_confirmed: int
    drops_dismissed: int
    of_confirmed: int
    of_dismissed: int
    text: str


@dataclass
class Insights:
    reviewed: int
    confirmed: int
    dismissed: int
    by_class: list[ClassStat]
    dismiss_reasons: dict[str, int]
    suggestions: list[Suggestion] = field(default_factory=list)
    note: str = ""


def compute(rows: list[Detection], current_t_bui: float, current_t_sar: float) -> Insights:
    conf = [d for d in rows if d.status == DetectionStatus.confirmed]
    dis = [d for d in rows if d.status == DetectionStatus.dismissed]
    by_class = []
    for c in (ConfidenceClass.high, ConfidenceClass.medium, ConfidenceClass.low):
        cs = ClassStat(c.value)
        cs.confirmed = sum(1 for d in conf if d.confidence == c)
        cs.dismissed = sum(1 for d in dis if d.confidence == c)
        by_class.append(cs)
    reasons: dict[str, int] = {}
    for d in dis:
        last = d.history[-1] if d.history else None
        key = (last.reason_code if last and last.reason_code else "unspecified") or "unspecified"
        reasons[key] = reasons.get(key, 0) + 1
    ins = Insights(len(rows), len(conf), len(dis), by_class, reasons)
    if len(rows) < MIN_LABELS:
        ins.note = (
            f"{len(rows)} reviewed so far — suggestions appear after {MIN_LABELS}. "
            "Keep confirming and dismissing; every decision sharpens this."
        )
        return ins
    s = _suggest("t_bui", current_t_bui, GRID_BUI, conf, dis, "d_bui_mean")
    if s:
        ins.suggestions.append(s)
    s = _suggest("t_sar_db", current_t_sar, GRID_SAR, conf, dis, "d_sigma_vv_mean")
    if s:
        ins.suggestions.append(s)
    if not ins.suggestions:
        ins.note = "Current thresholds already separate your confirmed and dismissed sites well."
    return ins


def _suggest(
    name: str,
    current: float,
    grid: list[float],
    conf: list[Detection],
    dis: list[Detection],
    attr: str,
) -> Suggestion | None:
    """Pick the threshold that keeps ≥ 95 % of confirmed sites and drops the most dismissed."""
    cv = [getattr(d, attr) for d in conf if getattr(d, attr) is not None]
    dv = [getattr(d, attr) for d in dis if getattr(d, attr) is not None]
    if len(cv) < 3 or len(dv) < 3:
        return None
    best: tuple[float, int, int] | None = None
    for t in grid:
        keep = sum(1 for v in cv if v >= t)
        drop = sum(1 for v in dv if v < t)
        if keep < 0.95 * len(cv):
            continue
        if (
            best is None
            or drop > best[2]
            or (drop == best[2] and abs(t - current) < abs(best[0] - current))
        ):
            best = (t, keep, drop)
    if best is None:
        return None
    t, keep, drop = best
    cur_drop = sum(1 for v in dv if v < current)
    if abs(t - current) < 1e-9 or drop <= cur_drop:
        return None
    unit = " dB" if name == "t_sar_db" else ""
    return Suggestion(
        param=name,
        current=current,
        suggested=t,
        keeps_confirmed=keep,
        drops_dismissed=drop,
        of_confirmed=len(cv),
        of_dismissed=len(dv),
        text=(
            f"Raising {name} from {current:g}{unit} to {t:g}{unit} would have kept "
            f"{keep}/{len(cv)} confirmed sites and removed {drop}/{len(dv)} dismissed ones "
            f"(currently {cur_drop}/{len(dv)})."
        ),
    )
