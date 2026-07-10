import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import async_engine, sync_engine
from app.core.logging_config import configure_logging
from app.telemetry.tracing import configure_tracing
from app.api.routes import health, ingest, records
from app.api.routes import metrics as metrics_route

configure_logging(settings.log_level)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("startup complete")
    yield
    await async_engine.dispose()
    logger.info("shutdown complete")


app = FastAPI(title="PHI De-identification Pipeline", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://bganguly.github.io"],
    allow_origin_regex=r"https?://localhost(:\d+)?",
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

configure_tracing(app, sync_engine, settings.otlp_endpoint)

app.include_router(health.router)
app.include_router(ingest.router)
app.include_router(records.router)
app.include_router(metrics_route.router)
