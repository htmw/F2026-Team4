"""Disk cache helpers.

Every cached file stores the *key* it was fetched for (query text, bbox, ...).
A cache hit requires the key to match, so changing the city, bbox or query can
never silently reuse another run's data.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import UTC, datetime
from pathlib import Path


def slugify(text: str) -> str:
    """Filesystem-safe slug. Non-Latin names fall back to a hash so they never collide."""
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
    if slug:
        return slug
    return "city-" + hashlib.sha1(text.strip().lower().encode("utf-8")).hexdigest()[:10]


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def write_json(path: Path, obj, *, indent: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=indent), encoding="utf-8")


def load_cached(path: Path, key: dict) -> dict | None:
    """Return the cached wrapper if it exists and was fetched for exactly this key."""
    if not path.exists():
        return None
    try:
        wrapper = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if wrapper.get("key") != key:
        return None
    return wrapper


def store(path: Path, key: dict, payload, **extra) -> dict:
    wrapper = {"key": key, "fetched_at": utc_now_iso(), **extra, "payload": payload}
    write_json(path, wrapper)
    return wrapper
