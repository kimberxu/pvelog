from fastapi import FastAPI
from api.routes import log_ingest, heartbeat
from api.middleware.auth import PSKAuthMiddleware
from db.database import engine, Base
from scheduler.tasks import periodic_inspection
import asyncio
import logging

logging.basicConfig(level=logging.INFO)

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
