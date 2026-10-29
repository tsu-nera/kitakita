"""JSON cache, track_id and tag metadata."""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

SUNO_ID = re.compile(r"id=([0-9a-fA-F]{8}-[0-9a-fA-F-]{27})")


def cache_dir() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "trackprep"


def track_id(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def cache_path(tid: str) -> Path:
    return cache_dir() / f"{tid}.json"


def load(tid: str) -> dict | None:
    p = cache_path(tid)
    return json.loads(p.read_text()) if p.exists() else None


def save(data: dict) -> Path:
    p = cache_path(data["track_id"])
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=1))
    return p


def _texts(frames) -> list[str]:
    out = []
    for fr in frames:
        t = getattr(fr, "text", fr)
        out.extend(str(x) for x in (t if isinstance(t, list) else [t]))
    return out


def read_metadata(path: str | Path) -> tuple[str, dict]:
    """Return (title, source). Title falls back to the file stem."""
    import mutagen

    title, comments = "", []
    try:
        tags = mutagen.File(str(path)).tags
    except Exception:
        tags = None
    if tags is not None:
        if hasattr(tags, "getall"):  # ID3
            title = " ".join(_texts(tags.getall("TIT2")))
            comments = _texts(tags.getall("COMM"))
        else:  # MP4 / Vorbis style
            title = " ".join(_texts(tags.get("\xa9nam", []) or tags.get("title", [])))
            comments = _texts(tags.get("\xa9cmt", []) or tags.get("comment", []))
    source: dict = {}
    for c in comments:
        m = SUNO_ID.search(c)
        if "made with suno" in c.lower() and m:
            source["suno_id"] = m.group(1)
            break
    return title or Path(path).stem, source
