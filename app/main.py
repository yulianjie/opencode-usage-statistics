from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import router as api_router
from app.config import cleanup_old_uploads

STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Sweep idle uploaded temp DBs left over from previous runs on startup.
    cleanup_old_uploads()
    yield


app = FastAPI(title="OpenCode Token 分析", version="0.1.0", lifespan=lifespan)
app.include_router(api_router)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def index():
    return FileResponse(str(STATIC_DIR / "index.html"))
