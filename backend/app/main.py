"""Sunrise FastAPI application."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.api.trading import router as trading_router
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.db.session import get_engine
from app.db.upgrade import ensure_schema

setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Idempotent schema creation + additive upgrades for existing deployments.
    await ensure_schema(get_engine())
    yield


app = FastAPI(title="Sunrise", version="0.2.0", lifespan=lifespan)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["GET", "HEAD", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Admin-Token"],
)

app.include_router(router)
app.include_router(trading_router)


@app.get("/")
async def root():
    return {"service": "sunrise", "version": app.version, "docs": "/docs"}
