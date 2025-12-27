from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class FileEntry:
    name: str
    size_bytes: int
    modified_at: str


def safe_filename(name: str) -> str:
    """Return a filename with any directory components removed."""
    return Path(name).name


def list_files(folder: Path) -> list[FileEntry]:
    if not folder.exists():
        return []

    entries: list[FileEntry] = []
    for p in sorted(folder.iterdir(), key=lambda x: x.name.lower()):
        if not p.is_file():
            continue
        st = p.stat()
        modified = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat()
        entries.append(FileEntry(name=p.name, size_bytes=st.st_size, modified_at=modified))
    return entries


def tail_text(path: Path, max_lines: int = 200) -> str:
    if not path.exists():
        return ""

    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return ""

    if len(lines) > max_lines:
        lines = lines[-max_lines:]
    return "\n".join(lines)
