import asyncio
from db.database import AsyncSessionLocal
from db.models import Node
from sqlalchemy import select
from config.settings import settings

async def periodic_inspection():
    while True:
        await asyncio.sleep(settings.inspect_interval_sec)
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(select(Node))
                nodes = result.scalars().all()
                for node in nodes:
                    print(f"[Scheduler] Triggering periodic inspection for Node: {node.id}")
                    # In a real system, this will trigger the log aggregation and LangGraph workflow
        except Exception as e:
            print(f"[Scheduler] Error during inspection: {e}")
