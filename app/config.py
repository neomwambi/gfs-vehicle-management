"""Application settings. Tune windows here without touching business logic."""

from __future__ import annotations

import os
from pathlib import Path

# Base paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = BASE_DIR / "uploads"
DATABASE_URL = f"sqlite:///{(DATA_DIR / 'gfs_vehicles.db').as_posix()}"


def _load_dotenv() -> None:
    """Load KEY=VALUE pairs from .env if present (no extra dependency)."""
    path = BASE_DIR / ".env"
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv()

# Trip window (hours). Shared by check-out and check-in deadlines.
TRIP_WINDOW_HOURS = 1

# Deadline scanner interval (seconds)
DEADLINE_CHECK_INTERVAL_SECONDS = 60

# Photo requirements
REQUIRED_PHOTO_ANGLES = ("front", "back", "left", "right", "odometer")
REQUIRED_PHOTO_COUNT = len(REQUIRED_PHOTO_ANGLES)

# Branding (Standard Bank-aligned blues)
BRAND_PRIMARY = "#0033A0"
BRAND_ACCENT = "#0072CE"
BRAND_NAVY = "#001F5B"

# Session
SESSION_HEADER = "X-Session-Token"
SESSION_COOKIE = "gfs_session"
