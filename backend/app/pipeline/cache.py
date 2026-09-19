"""Windowed-raster cache under DATA_DIR/cache (techspec §11). Keys are hashes we generate."""

import hashlib
import json
import logging
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)


class RasterCache:
    def __init__(self, root: Path) -> None:
        self.root = root

    def key(
        self, scene_id: str, bands: list[str], crs: str, bounds: tuple[float, ...], res: float
    ) -> str:
        payload = json.dumps(
            {
                "scene": scene_id,
                "bands": bands,
                "crs": crs,
                "bounds": [round(b, 3) for b in bounds],
                "res": res,
            },
            sort_keys=True,
        )
        return hashlib.sha1(payload.encode()).hexdigest()

    def path(self, key: str) -> Path:
        return self.root / key[:2] / f"{key}.npz"

    def get(self, key: str) -> np.ndarray | None:
        p = self.path(key)
        if not p.exists():
            return None
        with np.load(p) as z:
            return np.asarray(z["data"])

    def put(self, key: str, data: np.ndarray) -> None:
        p = self.path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp.npz")
        np.savez_compressed(tmp, data=data)
        tmp.replace(p)  # atomic on the same filesystem
        logger.debug("cache put %s %s", key[:10], data.shape)
