"""Zone context → priority (Phase 9, decision D74).

Priority combines *how sure we are that the land changed* (detection confidence) with *whether
that land is somewhere building is not expected* (reference-zone hit). It never says "illegal":
a zone hit means "check this first", and the layer source/date is carried along so a reviewer
can cite it.

    critical  high confidence AND footprint mostly inside a zone
    high      high confidence touching a zone (partly / buffer), or medium confidence mostly inside
    elevated  any other zone hit (medium touching, low inside/touching)
    normal    no active zone within reach
"""

from dataclasses import dataclass

from app.db.enums import ConfidenceClass
from app.repositories.reference import ZoneHit

PRIORITY_ORDER = ("critical", "high", "elevated", "normal")

_RANK = {ConfidenceClass.high: 2, ConfidenceClass.medium: 1, ConfidenceClass.low: 0}


@dataclass(frozen=True)
class ZoneContext:
    priority: str
    hits: list[ZoneHit]
    summary: str  # one line for lists, alerts and PDFs


def zone_context(confidence: ConfidenceClass, hits: list[ZoneHit]) -> ZoneContext:
    if not hits:
        return ZoneContext("normal", [], "No reference zone nearby")
    top = hits[0]
    inside = top.relation == "inside"
    r = _RANK[confidence]
    if r == 2 and inside:
        pr = "critical"
    elif (r == 2) or (r == 1 and inside):
        pr = "high"
    else:
        pr = "elevated"
    return ZoneContext(
        pr, hits, describe(top) + (f" (+{len(hits) - 1} more)" if len(hits) > 1 else "")
    )


def describe(h: ZoneHit) -> str:
    who = h.layer_name if not h.feature_name else f"{h.feature_name} ({h.layer_name})"
    if h.relation == "inside":
        return f"{round(h.inside_fraction * 100)} % inside {who}"
    if h.relation == "partly_inside":
        return f"{round(h.inside_fraction * 100)} % inside {who}"
    return f"{round(h.distance_m)} m from {who} (within {h.buffer_m} m buffer)"
