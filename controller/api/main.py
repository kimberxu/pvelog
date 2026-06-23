from fastapi import FastAPI
from api.routes import log_ingest, heartbeat, config, analysis
from api.middleware.auth import PSKAuthMiddleware
from db.database import engine, Base
from scheduler.tasks import periodic_inspection, cleanup_old_data
import asyncio
import logging

class EndpointFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return record.getMessage().find("/api/v1/heartbeat") == -1

from config.settings import settings

# Configure root logger with timestamps
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

# Suppress verbose debug logs from third-party libraries
logging.getLogger("aiosqlite").setLevel(logging.INFO)
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

# Route uvicorn loggers to root logger
for logger_name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
    logger = logging.getLogger(logger_name)
    logger.handlers.clear()
    logger.propagate = True
    if logger_name == "uvicorn.access":
        logger.addFilter(EndpointFilter())

app = FastAPI(title="PVE AIOps Controller")

app.add_middleware(PSKAuthMiddleware)

from sqlalchemy import text

@app.on_event("startup")
async def startup_event():
    # Initialize DB schema
    async with engine.begin() as conn:
        # Auto-migrate: add agent_url to nodes if missing
        try:
            await conn.execute(text("ALTER TABLE nodes ADD COLUMN agent_url VARCHAR(255)"))
        except Exception:
            pass
            
        # Auto-migrate: add created_at to analysis_records if missing
        try:
            await conn.execute(text("ALTER TABLE analysis_records ADD COLUMN created_at DATETIME DEFAULT CURRENT_TIMESTAMP"))
        except Exception:
            pass
            
        await conn.run_sync(Base.metadata.create_all)
    # Start periodic inspection
    asyncio.create_task(periodic_inspection())
    # Start cleanup task
    asyncio.create_task(cleanup_old_data())

app.include_router(log_ingest.router, prefix="/api/v1", tags=["Logs"])
app.include_router(heartbeat.router, prefix="/api/v1", tags=["Heartbeat"])
app.include_router(config.router, prefix="/api/v1", tags=["Config"])
app.include_router(analysis.router, prefix="/api/v1", tags=["Analysis"])
