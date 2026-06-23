from fastapi import FastAPI
from api.routes import log_ingest, heartbeat, config
from api.middleware.auth import PSKAuthMiddleware
from db.database import engine, Base
from scheduler.tasks import periodic_inspection
import asyncio
import logging

# Configure root logger with timestamps
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

# Route uvicorn loggers to root logger
for logger_name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
    logger = logging.getLogger(logger_name)
    logger.handlers.clear()
    logger.propagate = True

app = FastAPI(title="PVE AIOps Controller")

app.add_middleware(PSKAuthMiddleware)

@app.on_event("startup")
async def startup_event():
    # Initialize DB schema
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # Start periodic inspection
    asyncio.create_task(periodic_inspection())

app.include_router(log_ingest.router, prefix="/api/v1", tags=["Logs"])
app.include_router(heartbeat.router, prefix="/api/v1", tags=["Heartbeat"])
app.include_router(config.router, prefix="/api/v1", tags=["Config"])
