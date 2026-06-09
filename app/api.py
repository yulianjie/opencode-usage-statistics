import io
import zipfile
from datetime import datetime
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, Response

from app.config import (
    default_db_path,
    looks_like_opencode_db,
    resolve_db_path,
    stream_uploaded_db,
)
from app.core.data_loader import load_usage_from_db
from app.core.exporter import build_csv_files
from app.core.pricing import price_loaded_usage
from app.core.report import build_report_html
from app.core.service import scope_datasets_to_sessions
from app.core.viewmodels import build_application_viewmodels

router = APIRouter(prefix="/api")


def _resolve(db_path: str | None, token: str | None):
    try:
        return resolve_db_path(db_path, token)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


def _now_text():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _load(path, session_ids: list[str] | None = None):
    base = load_usage_from_db(path)
    ids = [s for s in (session_ids or []) if s]
    if ids:
        return scope_datasets_to_sessions(base, ids)
    return price_loaded_usage(base)


@router.get("/db/default")
def db_default():
    path = default_db_path()
    return {"path": str(path), "exists": path.exists()}


@router.get("/usage")
def usage(db_path: str | None = Query(None), token: str | None = Query(None)):
    path = _resolve(db_path, token)
    priced = _load(path)
    vm = build_application_viewmodels(priced)
    return JSONResponse({"source": str(path), "viewmodels": vm})


@router.get("/sessions/{session_id}")
def session_detail(session_id: str, db_path: str | None = Query(None), token: str | None = Query(None)):
    path = _resolve(db_path, token)
    priced = _load(path, session_ids=[session_id])
    if not priced["raw_messages"]:
        raise HTTPException(status_code=404, detail="会话不存在或无 token 数据")
    vm = build_application_viewmodels(priced)
    return JSONResponse({"source": str(path), "session_id": session_id, "viewmodels": vm})


@router.post("/upload")
async def upload(file: UploadFile = File(...)):
    # Stream straight to disk in chunks so arbitrarily large opencode.db files
    # can be uploaded without buffering the whole thing in memory.
    try:
        token, size = stream_uploaded_db(file.file)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    path = resolve_db_path(token=token)
    if not looks_like_opencode_db(path):
        raise HTTPException(status_code=400, detail="文件不是有效的 opencode.db（缺少 message 表）")
    return {"token": token, "filename": file.filename, "size": size}


@router.get("/export/csv")
def export_csv(db_path: str | None = Query(None), token: str | None = Query(None)):
    path = _resolve(db_path, token)
    priced = _load(path)
    files = build_csv_files(priced)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    buffer.seek(0)
    headers = {"Content-Disposition": 'attachment; filename="opencode_token_export.zip"'}
    return Response(content=buffer.getvalue(), media_type="application/zip", headers=headers)


@router.get("/export/report", response_class=HTMLResponse)
def export_report(
    db_path: str | None = Query(None),
    token: str | None = Query(None),
    session_id: list[str] | None = Query(None, description="可重复传入以合并多个会话"),
    download: bool = Query(True),
):
    path = _resolve(db_path, token)
    ids = [s for s in (session_id or []) if s]
    priced = _load(path, session_ids=ids)
    if ids and not priced["raw_messages"]:
        raise HTTPException(status_code=404, detail="所选会话不存在或无 token 数据")

    session_rows = priced.get("by_session", [])
    if not ids:
        title = "OpenCode Token 使用分析报告"
        source_label = str(path)
        fname = "opencode_report.html"
    elif len(session_rows) <= 1:
        title = "OpenCode 单会话 Token 分析报告"
        label = session_rows[0].get("session_title") if session_rows else ids[0]
        source_label = f"会话：{label or ids[0]}"
        fname = f"opencode_report_{ids[0]}.html"
    else:
        title = f"OpenCode 多会话 Token 分析报告（{len(session_rows)} 个会话）"
        names = [r.get("session_title") or r.get("session_id") for r in session_rows]
        shown = "、".join(names[:5]) + ("…" if len(names) > 5 else "")
        source_label = f"合并 {len(session_rows)} 个会话：{shown}"
        fname = f"opencode_report_{len(session_rows)}_sessions.html"

    html = build_report_html(priced, title=title, source_label=source_label, generated_at=_now_text())
    headers = {}
    if download:
        headers["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(fname)}"
    return HTMLResponse(content=html, headers=headers)
