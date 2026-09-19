"""Evaluation metrics on synthetic geometries (offline)."""

import pytest
from shapely.geometry import box

from app.pipeline.evaluate import LabelledSite, evaluate, load_labels, matches


def test_matches_iou_and_containment() -> None:
    a = box(0, 0, 10, 10)
    assert matches(a, box(0, 0, 10, 10))
    assert matches(a, box(5, 0, 15, 10), iou_min=0.3)  # IoU 1/3
    assert not matches(a, box(8, 0, 18, 10), iou_min=0.3)  # IoU 2/18, 20 % of smaller
    assert matches(a, box(2, 2, 5, 5))  # small box fully inside -> containment rule
    assert not matches(a, box(20, 20, 30, 30))


def test_precision_recall_by_class() -> None:
    labels = [
        LabelledSite(box(0, 0, 10, 10), "real"),
        LabelledSite(box(20, 0, 30, 10), "real"),
        LabelledSite(box(40, 0, 50, 10), "not_real"),
        LabelledSite(box(60, 0, 70, 10), "unsure"),
        LabelledSite(box(80, 0, 90, 10), "real"),  # missed: no detection here
    ]
    dets = [
        (box(0, 0, 10, 10), "high"),  # tp
        (box(20, 0, 30, 10), "high"),  # tp
        (box(40, 0, 50, 10), "medium"),  # fp (labelled not real)
        (box(60, 0, 70, 10), "low"),  # unsure -> excluded
        (box(100, 0, 110, 10), "low"),  # unmatched -> fp
    ]
    ev = evaluate(dets, labels)
    assert ev.per_class["high"].precision == 1.0
    assert ev.per_class["medium"].precision == 0.0
    assert ev.per_class["low"].tp == 0 and ev.per_class["low"].fp == 1
    assert ev.per_class["low"].unsure == 1
    assert ev.overall().precision == pytest.approx(2 / 4)
    assert ev.recall == pytest.approx(2 / 3)
    assert ev.unmatched_detections == 1
    assert ev.summary()["recall"] == pytest.approx(2 / 3)


def test_two_detections_on_one_site_count_site_once_for_recall() -> None:
    labels = [LabelledSite(box(0, 0, 10, 10), "real")]
    dets = [(box(0, 0, 5, 10), "high"), (box(5, 0, 10, 10), "medium")]
    ev = evaluate(dets, labels)
    assert ev.recall == 1.0
    assert ev.overall().tp == 2


def test_load_labels_rejects_unknown() -> None:
    fc = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"label": "maybe"},
                "geometry": {"type": "Point", "coordinates": [0, 0]},
            }
        ],
    }
    with pytest.raises(ValueError):
        load_labels(fc)
    fc["features"][0]["properties"]["label"] = "not real"
    assert load_labels(fc)[0].label == "not_real"
