"""Resolve file-backed service paths with an optional runtime override."""

from __future__ import annotations

import os
from pathlib import Path


def resolve_data_dir(default: Path) -> Path:
    """Return the configured data directory or the service's existing default."""

    override = os.getenv("OPENPOKE_DATA_DIR", "").strip()
    return Path(override).expanduser().resolve() if override else default


__all__ = ["resolve_data_dir"]
