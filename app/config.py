import os
import sqlite3
import tempfile
import time
import uuid
from pathlib import Path
from typing import BinaryIO


def default_db_path() -> Path:
    return Path.home() / ".local" / "share" / "opencode" / "opencode.db"


UPLOAD_DIR = Path(tempfile.gettempdir()) / "opencode_usage_uploads"

# Chunk size for streaming large uploads to disk (8 MB).
UPLOAD_CHUNK_BYTES = 8 * 1024 * 1024

# Uploaded temp DBs are deleted after this many seconds of inactivity.
# Access (querying by token) refreshes the file's mtime, so a DB in active
# use is never purged — only idle leftovers are. Configurable via env var.
UPLOAD_TTL_SECONDS = int(os.environ.get("OPENCODE_UPLOAD_TTL_SECONDS", str(6 * 3600)))


def _ensure_upload_dir() -> Path:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    return UPLOAD_DIR


def cleanup_old_uploads(ttl_seconds: int | None = None) -> int:
    """Delete uploaded *.db temp files idle longer than the TTL.

    "Idle" is measured by mtime, which is refreshed each time the file is
    accessed via its token (see resolve_db_path). Returns the count removed.
    """
    ttl = UPLOAD_TTL_SECONDS if ttl_seconds is None else ttl_seconds
    if not UPLOAD_DIR.exists():
        return 0
    cutoff = time.time() - max(ttl, 0)
    removed = 0
    for path in UPLOAD_DIR.glob("*.db"):
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink(missing_ok=True)
                removed += 1
        except OSError:
            pass
    return removed


def save_uploaded_db(data: bytes) -> str:
    """Persist an uploaded opencode.db to a temp dir; return its token."""
    _ensure_upload_dir()
    token = uuid.uuid4().hex
    target = UPLOAD_DIR / f"{token}.db"
    target.write_bytes(data)
    return token


def stream_uploaded_db(source: BinaryIO) -> tuple[str, int]:
    """Stream an uploaded file object to disk in chunks; return (token, byte_size).

    Avoids loading the whole file into memory, so arbitrarily large opencode.db
    files can be uploaded. Raises ValueError if the upload is empty.
    """
    _ensure_upload_dir()
    token = uuid.uuid4().hex
    target = UPLOAD_DIR / f"{token}.db"
    try:
        source.seek(0)
    except (OSError, AttributeError):
        pass
    written = 0
    with target.open("wb") as out:
        while True:
            chunk = source.read(UPLOAD_CHUNK_BYTES)
            if not chunk:
                break
            out.write(chunk)
            written += len(chunk)
    if written == 0:
        target.unlink(missing_ok=True)
        raise ValueError("上传文件为空")
    # Opportunistically sweep idle leftovers whenever a new file lands.
    cleanup_old_uploads()
    return token, written


def resolve_db_path(db_path: str | None = None, token: str | None = None) -> Path:
    """Resolve the effective db path from (upload token | explicit path | default)."""
    if token:
        candidate = UPLOAD_DIR / f"{token}.db"
        if not candidate.exists():
            raise FileNotFoundError("上传的数据库已过期或不存在，请重新上传")
        # Refresh mtime so an actively-used upload slides past its idle TTL.
        try:
            os.utime(candidate, None)
        except OSError:
            pass
        return candidate
    if db_path:
        candidate = Path(db_path).expanduser()
        if not candidate.exists():
            raise FileNotFoundError(f"数据库不存在：{candidate}")
        return candidate
    candidate = default_db_path()
    if not candidate.exists():
        raise FileNotFoundError(f"默认数据库不存在：{candidate}")
    return candidate


def looks_like_opencode_db(path: Path) -> bool:
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            return "message" in names
        finally:
            conn.close()
    except sqlite3.Error:
        return False
