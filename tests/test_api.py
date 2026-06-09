import io
import zipfile

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_usage_endpoint(sample_db):
    res = client.get("/api/usage", params={"db_path": str(sample_db)})
    assert res.status_code == 200
    body = res.json()
    assert body["viewmodels"]["overview"]["cards"]["message_count"] == 4


def test_usage_missing_db():
    res = client.get("/api/usage", params={"db_path": "/no/such/file.db"})
    assert res.status_code == 404


def test_session_detail(sample_db):
    res = client.get("/api/sessions/ses_a", params={"db_path": str(sample_db)})
    assert res.status_code == 200
    assert res.json()["viewmodels"]["overview"]["cards"]["message_count"] == 2


def test_export_csv_zip(sample_db):
    res = client.get("/api/export/csv", params={"db_path": str(sample_db)})
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/zip"
    zf = zipfile.ZipFile(io.BytesIO(res.content))
    names = set(zf.namelist())
    assert {"summary.csv", "by_model.csv", "by_session.csv", "by_day.csv", "raw_messages_with_tokens.csv"} <= names
    # utf-8-sig BOM
    assert zf.read("summary.csv").startswith(b"\xef\xbb\xbf")


def test_export_report_html(sample_db):
    res = client.get("/api/export/report", params={"db_path": str(sample_db), "download": False})
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    assert "OpenCode Token" in res.text


def test_export_session_report(sample_db):
    res = client.get("/api/export/report", params={"db_path": str(sample_db), "session_id": "ses_a", "download": False})
    assert res.status_code == 200
    assert "单会话" in res.text


def test_export_multi_session_report(sample_db):
    # repeated session_id params -> combined report
    res = client.get(
        "/api/export/report",
        params=[("db_path", str(sample_db)), ("session_id", "ses_a"), ("session_id", "ses_b"), ("download", "false")],
    )
    assert res.status_code == 200
    assert "多会话" in res.text
    assert "2 个会话" in res.text


def test_export_multi_session_404_when_all_unknown(sample_db):
    res = client.get(
        "/api/export/report",
        params=[("db_path", str(sample_db)), ("session_id", "nope-1"), ("session_id", "nope-2")],
    )
    assert res.status_code == 404


def test_upload_flow(sample_db):
    with open(sample_db, "rb") as fh:
        res = client.post("/api/upload", files={"file": ("opencode.db", fh, "application/octet-stream")})
    assert res.status_code == 200
    token = res.json()["token"]
    res2 = client.get("/api/usage", params={"token": token})
    assert res2.status_code == 200
    assert res2.json()["viewmodels"]["overview"]["cards"]["message_count"] == 4


def test_upload_rejects_non_db(tmp_path):
    bad = tmp_path / "bad.db"
    bad.write_bytes(b"not a sqlite file")
    with open(bad, "rb") as fh:
        res = client.post("/api/upload", files={"file": ("bad.db", fh, "application/octet-stream")})
    assert res.status_code == 400


def test_stream_uploaded_db_handles_multichunk():
    """Streaming writes are size-independent: a payload larger than one chunk
    is written correctly without any 200MB-style cap."""
    import io

    from app.config import UPLOAD_CHUNK_BYTES, resolve_db_path, stream_uploaded_db

    payload = b"x" * (UPLOAD_CHUNK_BYTES * 2 + 123)  # spans 3 chunks
    token, size = stream_uploaded_db(io.BytesIO(payload))
    assert size == len(payload)
    path = resolve_db_path(token=token)
    assert path.stat().st_size == len(payload)


def test_stream_uploaded_db_rejects_empty():
    import io

    import pytest as _pytest

    from app.config import stream_uploaded_db

    with _pytest.raises(ValueError):
        stream_uploaded_db(io.BytesIO(b""))


def test_cleanup_removes_idle_and_keeps_recent():
    import io
    import os
    import time

    from app import config

    old_token, _ = config.stream_uploaded_db(io.BytesIO(b"old-db-content"))
    new_token, _ = config.stream_uploaded_db(io.BytesIO(b"new-db-content"))
    old_path = config.UPLOAD_DIR / f"{old_token}.db"
    new_path = config.UPLOAD_DIR / f"{new_token}.db"

    # Age the "old" file well past the TTL.
    stale = time.time() - (config.UPLOAD_TTL_SECONDS + 3600)
    os.utime(old_path, (stale, stale))

    removed = config.cleanup_old_uploads()
    assert removed >= 1
    assert not old_path.exists()
    assert new_path.exists()


def test_access_refreshes_idle_ttl():
    import io
    import os
    import time

    from app import config

    token, _ = config.stream_uploaded_db(io.BytesIO(b"content"))
    path = config.UPLOAD_DIR / f"{token}.db"
    # Make it look stale, then access by token -> mtime refreshed -> survives.
    stale = time.time() - (config.UPLOAD_TTL_SECONDS + 3600)
    os.utime(path, (stale, stale))

    config.resolve_db_path(token=token)  # touches mtime
    removed = config.cleanup_old_uploads()
    assert path.exists()
    _ = removed
