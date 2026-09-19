"""Metrics for detections against a hand-labelled set (techspec §5.3, task 1.10).

Labels are GeoJSON features with `label` in {"real", "not_real", "unsure"} and `kind` in
{"detection", "missed"}. Matching is geometric (IoU or containment), so the same label file can
score detections produced with different thresholds.

Conventions (documented so the numbers are reproducible):
- A detection is a TRUE POSITIVE if it matches a `real` label, FALSE POSITIVE if it matches a
  `not_real` label or matches nothing. Detections matching only `unsure` labels are excluded
  from precision (reported separately).
- Match = IoU >= iou_min OR the smaller geometry is >= 50 % covered by the larger one (a small
  detection inside a big labelled site still counts).
- Recall = matched real labels / all real labels (both `detection` and `missed` kinds).
"""

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry

Label = str  # "real" | "not_real" | "unsure"


@dataclass(frozen=True)
class LabelledSite:
    geom: BaseGeometry
    label: Label
    note: str = ""


@dataclass
class ClassMetrics:
    tp: int = 0
    fp: int = 0
    unsure: int = 0

    @property
    def precision(self) -> float | None:
        n = self.tp + self.fp
        return None if n == 0 else self.tp / n


@dataclass
class Evaluation:
    per_class: dict[str, ClassMetrics] = field(default_factory=dict)
    real_total: int = 0
    real_matched: int = 0
    unmatched_detections: int = 0

    @property
    def recall(self) -> float | None:
        return None if self.real_total == 0 else self.real_matched / self.real_total

    def overall(self, classes: tuple[str, ...] = ("high", "medium", "low")) -> ClassMetrics:
        m = ClassMetrics()
        for c in classes:
            if c in self.per_class:
                m.tp += self.per_class[c].tp
                m.fp += self.per_class[c].fp
                m.unsure += self.per_class[c].unsure
        return m

    def summary(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for c, m in self.per_class.items():
            out[c] = {"tp": m.tp, "fp": m.fp, "unsure": m.unsure, "precision": m.precision}
        o = self.overall()
        out["all"] = {"tp": o.tp, "fp": o.fp, "unsure": o.unsure, "precision": o.precision}
        out["recall"] = self.recall
        out["real_total"] = self.real_total
        out["unmatched_detections"] = self.unmatched_detections
        return out


def load_labels(fc: dict[str, Any]) -> list[LabelledSite]:
    sites = []
    for f in fc["features"]:
        p = f.get("properties", {})
        lab = str(p.get("label", "unsure")).replace(" ", "_")
        if lab not in ("real", "not_real", "unsure"):
            raise ValueError(f"unknown label {lab!r}")
        sites.append(LabelledSite(shape(f["geometry"]), lab, str(p.get("note", ""))))
    return sites


def matches(a: BaseGeometry, b: BaseGeometry, iou_min: float = 0.3) -> bool:
    if not a.intersects(b):
        return False
    inter = a.intersection(b).area
    union = a.union(b).area
    if union > 0 and inter / union >= iou_min:
        return True
    smaller = min(a.area, b.area)
    return bool(smaller > 0 and inter / smaller >= 0.5)


def evaluate(
    detections: list[tuple[BaseGeometry, str]],
    labels: list[LabelledSite],
    iou_min: float = 0.3,
) -> Evaluation:
    """detections: (geometry in the SAME CRS as labels, confidence class)."""
    ev = Evaluation()
    ev.real_total = sum(1 for s in labels if s.label == "real")
    matched_real: set[int] = set()
    for geom, conf in detections:
        m = ev.per_class.setdefault(conf, ClassMetrics())
        hit: Counter[str] = Counter()
        for i, s in enumerate(labels):
            if matches(geom, s.geom, iou_min):
                hit[s.label] += 1
                if s.label == "real":
                    matched_real.add(i)
        if hit["real"]:
            m.tp += 1
        elif hit["not_real"]:
            m.fp += 1
        elif hit["unsure"]:
            m.unsure += 1
        else:
            m.fp += 1
            ev.unmatched_detections += 1
    ev.real_matched = len(matched_real)
    return ev
