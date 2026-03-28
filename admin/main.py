"""
admin/main.py — FastAPI application entry point for the admin dashboard.

Exposes:
  GET  /admin/stats          — real-time system metrics
  GET  /admin/config         — current runtime configuration
  POST /admin/config/update  — update runtime configuration
  GET  /                     — HTML dashboard (served from admin/static/)

Run with:
  python -m admin.main
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from admin.database import mongodb, redis_client
from admin.routes.config_routes import router as config_router
from admin.routes.stats import router as stats_router
from config.app_config import app_config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Connecting to Redis and MongoDB…")
    await redis_client.connect()
    await mongodb.connect()
    logger.info("Admin dashboard ready.")
    yield
    await redis_client.disconnect()
    await mongodb.disconnect()


app = FastAPI(
    title=f"{app_config.brand_name} Bot — Admin Dashboard",
    description=f"Real-time control panel for the Telegram {app_config.brand_name} Bot backend.",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url=None,
    lifespan=lifespan,
)


# ─── API routes ───────────────────────────────────────────────────────────────

app.include_router(stats_router, prefix="/admin")
app.include_router(config_router, prefix="/admin")


# ─── Static dashboard ─────────────────────────────────────────────────────────

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", include_in_schema=False)
async def dashboard() -> FileResponse:
    return FileResponse(str(STATIC_DIR / "index.html"))


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run("admin.main:app", host="0.0.0.0", port=8000, reload=False)
