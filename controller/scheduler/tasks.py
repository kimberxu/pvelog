import asyncio
import logging
from db.database import AsyncSessionLocal
from db.models import Node
from sqlalchemy import select
from config.settings import settings

logger = logging.getLogger(__name__)

async def periodic_inspection():
    while True:
        await asyncio.sleep(settings.inspect_interval_sec)
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(select(Node))
                nodes = result.scalars().all()
                for node in nodes:
                    logger.info(f"[Scheduler] Triggering periodic inspection for Node: {node.id}")
                    # In a real system, this will trigger the log aggregation and LangGraph workflow
        except Exception as e:
            logger.error(f"[Scheduler] Error during inspection: {e}")
