"""GFS Vehicle Management System - FastAPI entrypoint."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.config import UPLOAD_DIR
from app.database import init_db
from app.routes import admin, auth, bookings, vehicles
from app.services.deadlines import deadline_loop
from app.services.storage import ensure_upload_dir

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    ensure_upload_dir()
    stop = asyncio.Event()
    task = asyncio.create_task(deadline_loop(stop))
    logger.info("GFS Vehicle Management prototype started")
    yield
    stop.set()
    await task


app = FastAPI(
    title="GFS Vehicle Management System",
    description="Local prototype for Group Forensic Services pool vehicles",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(auth.router)
app.include_router(vehicles.router)
app.include_router(bookings.router)
app.include_router(admin.router)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")


def _page(name: str) -> FileResponse:
    path = STATIC_DIR / name
    if not path.exists():
        return FileResponse(STATIC_DIR / "login.html")
    return FileResponse(path)


@app.get("/")
def root():
    return RedirectResponse(url="/login.html")


@app.get("/login.html")
def login_page():
    return _page("login.html")


@app.get("/app/{page_name}")
def app_pages(page_name: str):
    return _page(f"app/{page_name}")


@app.get("/admin/{page_name}")
def admin_pages(page_name: str, request: Request):
    # HTML is public; API enforces Manager/Admin. Frontend also redirects Employees away.
    return _page(f"admin/{page_name}")
