"""Local filesystem photo storage.

Swap this module for Azure Blob Storage later - callers only depend on save_photo / paths.
"""

import base64
import re
import uuid
from pathlib import Path

from app.config import UPLOAD_DIR

_DATA_URL_RE = re.compile(r"^data:image/(png|jpeg|jpg|webp);base64,(.+)$", re.IGNORECASE | re.DOTALL)


def ensure_upload_dir() -> Path:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    return UPLOAD_DIR


def save_photo(*, booking_id: int, phase: str, angle: str, data_url: str) -> str:
    """Persist a camera capture and return a relative path under /uploads."""
    match = _DATA_URL_RE.match(data_url.strip())
    if not match:
        raise ValueError("Photo must be a valid image data URL from camera capture")

    ext = match.group(1).lower()
    if ext == "jpg":
        ext = "jpeg"
    raw = base64.b64decode(match.group(2))
    if len(raw) < 100:
        raise ValueError("Photo data is too small to be a valid capture")

    booking_dir = ensure_upload_dir() / f"booking_{booking_id}" / phase
    booking_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{angle}_{uuid.uuid4().hex[:10]}.{ext}"
    path = booking_dir / filename
    path.write_bytes(raw)

    # Store path relative to project uploads root
    return f"booking_{booking_id}/{phase}/{filename}"
