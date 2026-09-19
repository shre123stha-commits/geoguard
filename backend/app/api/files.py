"""Protected file serving for evidence thumbnails and reports (techspec §6, task 5.3).

Files live under DATA_DIR; only the `evidence/` and `reports/` subtrees are exposed, the
resolved path must stay inside them (no traversal), and a valid session is required.
"""

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.api.deps import ActiveUser, SettingsDep

router = APIRouter(prefix="/files", tags=["files"])
logger = logging.getLogger(__name__)

ALLOWED_ROOTS = ("evidence", "reports")
MEDIA = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".pdf": "application/pdf",
}


def resolve_file(data_dir: Path, rel: str) -> Path:
    """Map a stored relative path to a real file or raise 404 (never reveal why)."""
    parts = Path(rel).parts
    if not parts or parts[0] not in ALLOWED_ROOTS or any(p in ("..", "") for p in parts):
        raise HTTPException(status_code=404, detail="File not found")
    base = data_dir.resolve() / parts[0]
    target = (data_dir / rel).resolve()
    if base not in target.parents or target.suffix.lower() not in MEDIA or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return target


@router.get("/{path:path}")
def get_file(path: str, _: ActiveUser, settings: SettingsDep) -> FileResponse:
    target = resolve_file(settings.data_dir, path)
    return FileResponse(
        target,
        media_type=MEDIA[target.suffix.lower()],
        headers={"Cache-Control": "private, max-age=3600"},
    )
