"""Reference layers (Phase 9): storage + the spatial "zone context" query.

Zone context answers, per detection: which active reference zones does this footprint lie in
(or within the layer's buffer of), and by how much. It is computed on read, never stored, so
uploading or editing a layer immediately applies to every detection.
"""

import json
import uuid
from dataclasses import dataclass
from datetime import date
from typing import Any

from geoalchemy2 import Geography
from sqlalchemy import Select, cast, func, select, text
from sqlalchemy.orm import Session

from app.db.models import Detection, ReferenceFeature, ReferenceLayer
from app.repositories.base import geojson_to_multipolygon, to_db

# Zone factors (design decision D74): how much a hit raises the priority.
# "inside" = footprint mostly within the zone; "buffer" = touches only the buffer ring.
_INSIDE_FRACTION = 0.5


@dataclass(frozen=True)
class ZoneHit:
    layer_id: uuid.UUID
    layer_name: str
    kind: str
    feature_name: str | None
    inside_fraction: float  # 0..1 of the detection footprint inside the zone itself
    distance_m: float  # 0 when overlapping the zone; else distance to its edge
    buffer_m: int
    source: str | None
    source_date: date | None

    @property
    def relation(self) -> str:
        if self.inside_fraction >= _INSIDE_FRACTION:
            return "inside"
        if self.inside_fraction > 0:
            return "partly_inside"
        return "within_buffer"


class ReferenceRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # --- layers -------------------------------------------------------------------------
    def list_layers(self) -> list[ReferenceLayer]:
        return list(
            self.db.scalars(
                select(ReferenceLayer).order_by(ReferenceLayer.created_at.desc(), ReferenceLayer.id)
            )
        )

    def get(self, layer_id: uuid.UUID) -> ReferenceLayer | None:
        return self.db.get(ReferenceLayer, layer_id)

    def create(
        self,
        *,
        name: str,
        kind: str,
        features: list[dict[str, Any]],
        source: str | None,
        source_date: date | None,
        notes: str | None,
        buffer_m: int,
        created_by: uuid.UUID | None,
    ) -> tuple[ReferenceLayer, list[tuple[int, str]]]:
        """Insert a layer and its (validated) features. Returns (layer, skipped[(index, why)])."""
        layer = ReferenceLayer(
            name=name,
            kind=kind,
            source=source,
            source_date=source_date,
            notes=notes,
            buffer_m=buffer_m,
            created_by=created_by,
        )
        self.db.add(layer)
        self.db.flush()
        skipped: list[tuple[int, str]] = []
        n = 0
        for i, f in enumerate(features):
            try:
                g = geojson_to_multipolygon(f.get("geometry") or {})
            except ValueError as exc:
                skipped.append((i, str(exc)))
                continue
            props = {k: v for k, v in (f.get("properties") or {}).items() if _jsonable(v)}
            fname = _feature_name(props)
            self.db.add(ReferenceFeature(layer_id=layer.id, name=fname, props=props, geom=to_db(g)))
            n += 1
        layer.feature_count = n
        self.db.flush()
        return layer, skipped

    def delete(self, layer: ReferenceLayer) -> None:
        self.db.delete(layer)
        self.db.flush()

    def features_geojson(self, layer: ReferenceLayer, simplify_deg: float = 0.0) -> dict[str, Any]:
        """FeatureCollection for the map overlay (optionally simplified for big layers)."""
        geom: Any = ReferenceFeature.geom
        if simplify_deg > 0:
            geom = func.ST_SimplifyPreserveTopology(geom, simplify_deg)
        q = select(
            ReferenceFeature.id, ReferenceFeature.name, func.ST_AsGeoJSON(geom).label("g")
        ).where(ReferenceFeature.layer_id == layer.id)
        feats = [
            {
                "type": "Feature",
                "id": str(fid),
                "geometry": json.loads(g),
                "properties": {"name": name, "layer_id": str(layer.id), "kind": layer.kind},
            }
            for fid, name, g in self.db.execute(q)
        ]
        return {"type": "FeatureCollection", "features": feats}

    def bounds(self, layer: ReferenceLayer) -> list[float] | None:
        row = self.db.execute(
            select(func.ST_Extent(ReferenceFeature.geom)).where(
                ReferenceFeature.layer_id == layer.id
            )
        ).scalar()
        if not row:
            return None
        # BOX(minx miny,maxx maxy)
        a, b = str(row)[4:-1].split(",")
        minx, miny = (float(v) for v in a.split())
        maxx, maxy = (float(v) for v in b.split())
        return [minx, miny, maxx, maxy]

    # --- zone context -------------------------------------------------------------------
    def zone_hits(self, det: Detection) -> list[ZoneHit]:
        """All active-layer features that overlap the detection or lie within the layer buffer."""
        dg = cast(Detection.geom, Geography)
        fg = cast(ReferenceFeature.geom, Geography)
        # Fraction of the detection footprint inside the zone (geodesic areas).
        inter_area = func.ST_Area(
            cast(func.ST_Intersection(Detection.geom, ReferenceFeature.geom), Geography)
        )
        det_area = func.ST_Area(dg)
        q = (
            select(
                ReferenceLayer.id,
                ReferenceLayer.name,
                ReferenceLayer.kind,
                ReferenceFeature.name,
                (inter_area / func.nullif(det_area, 0)).label("frac"),
                func.ST_Distance(dg, fg).label("dist"),
                ReferenceLayer.buffer_m,
                ReferenceLayer.source,
                ReferenceLayer.source_date,
            )
            .select_from(Detection)
            .join(ReferenceLayer, ReferenceLayer.is_active.is_(True))
            .join(
                ReferenceFeature,
                (ReferenceFeature.layer_id == ReferenceLayer.id)
                & func.ST_DWithin(dg, fg, ReferenceLayer.buffer_m),
            )
            .where(Detection.id == det.id, ReferenceLayer.is_active.is_(True))
            .order_by(text("frac DESC NULLS LAST"), text("dist ASC"))
        )
        hits: list[ZoneHit] = []
        for lid, lname, kind, fname, frac, dist, buf, src, sdate in self.db.execute(q):
            hits.append(
                ZoneHit(
                    layer_id=lid,
                    layer_name=lname,
                    kind=kind,
                    feature_name=fname,
                    inside_fraction=float(min(1.0, max(0.0, frac or 0.0))),
                    distance_m=float(dist or 0.0),
                    buffer_m=int(buf),
                    source=src,
                    source_date=sdate,
                )
            )
        # One row per layer is enough for the UI: keep the strongest hit per layer.
        best: dict[uuid.UUID, ZoneHit] = {}
        for h in hits:
            cur = best.get(h.layer_id)
            if cur is None or (h.inside_fraction, -h.distance_m) > (
                cur.inside_fraction,
                -cur.distance_m,
            ):
                best[h.layer_id] = h
        return sorted(best.values(), key=lambda h: (-h.inside_fraction, h.distance_m))

    def zone_hits_bulk(self, detection_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[ZoneHit]]:
        """Same as zone_hits for a page of detections (one query)."""
        if not detection_ids:
            return {}
        dg = cast(Detection.geom, Geography)
        fg = cast(ReferenceFeature.geom, Geography)
        inter_area = func.ST_Area(
            cast(func.ST_Intersection(Detection.geom, ReferenceFeature.geom), Geography)
        )
        q = (
            select(
                Detection.id,
                ReferenceLayer.id,
                ReferenceLayer.name,
                ReferenceLayer.kind,
                ReferenceFeature.name,
                (inter_area / func.nullif(func.ST_Area(dg), 0)).label("frac"),
                func.ST_Distance(dg, fg).label("dist"),
                ReferenceLayer.buffer_m,
                ReferenceLayer.source,
                ReferenceLayer.source_date,
            )
            .select_from(Detection)
            .join(ReferenceLayer, ReferenceLayer.is_active.is_(True))
            .join(
                ReferenceFeature,
                (ReferenceFeature.layer_id == ReferenceLayer.id)
                & func.ST_DWithin(dg, fg, ReferenceLayer.buffer_m),
            )
            .where(Detection.id.in_(detection_ids), ReferenceLayer.is_active.is_(True))
        )
        best: dict[tuple[uuid.UUID, uuid.UUID], ZoneHit] = {}
        for did, lid, lname, kind, fname, frac, dist, buf, src, sdate in self.db.execute(q):
            h = ZoneHit(
                layer_id=lid,
                layer_name=lname,
                kind=kind,
                feature_name=fname,
                inside_fraction=float(min(1.0, max(0.0, frac or 0.0))),
                distance_m=float(dist or 0.0),
                buffer_m=int(buf),
                source=src,
                source_date=sdate,
            )
            key = (did, lid)
            cur = best.get(key)
            if cur is None or (h.inside_fraction, -h.distance_m) > (
                cur.inside_fraction,
                -cur.distance_m,
            ):
                best[key] = h
        out: dict[uuid.UUID, list[ZoneHit]] = {d: [] for d in detection_ids}
        for (did, _), h in best.items():
            out[did].append(h)
        for v in out.values():
            v.sort(key=lambda h: (-h.inside_fraction, h.distance_m))
        return out

    def detection_ids_in_zones(self) -> Select[tuple[uuid.UUID]]:
        """Subquery of detection ids touching any active zone (for the list filter)."""
        dg = cast(Detection.geom, Geography)
        fg = cast(ReferenceFeature.geom, Geography)
        return (
            select(Detection.id)
            .select_from(Detection)
            .join(ReferenceLayer, ReferenceLayer.is_active.is_(True))
            .join(
                ReferenceFeature,
                (ReferenceFeature.layer_id == ReferenceLayer.id)
                & func.ST_DWithin(dg, fg, ReferenceLayer.buffer_m),
            )
            .where(ReferenceLayer.is_active.is_(True))
            .distinct()
        )


def _jsonable(v: Any) -> bool:
    return isinstance(v, str | int | float | bool) or v is None


def _feature_name(props: dict[str, Any]) -> str | None:
    for k in ("name", "NAME", "Name", "title", "label", "LABEL", "zone", "ZONE", "class"):
        v = props.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()[:200]
    return None
