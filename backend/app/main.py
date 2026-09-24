"""Sunrise FastAPI application."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.routes import router
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.models.models import Base
from app.db.session import get_engine

setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ensure schema exists (idempotent; full seeding via `python -m app.seed`)
    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # create_all skips indexes when the table already exists, so ensure the
        # notification idempotency index explicitly for existing deployments.
        await conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_notifications_once "
                "ON notifications (event_id, channel, (COALESCE(user_id, -1)))"
            )
        )
    yield


app = FastAPI(title="Sunrise", version="0.1.0", lifespan=lifespan)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # public read API; mutations gated by ADMIN_TOKEN
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/")
async def root():
    return {"service": "sunrise", "docs": "/docs"}
