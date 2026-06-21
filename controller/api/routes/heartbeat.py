from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
import datetime

from db.database import get_db
from db.models import Node

router = APIRouter()

class HeartbeatRequest(BaseModel):
    node_id: str
    hostname: str
    uptime_seconds: int
    agent_version: str
    cpu_usage_percent: float
    memory_usage_percent: float
    disk_usage: dict

@router.post("/heartbeat")
async def receive_heartbeat(
    request: HeartbeatRequest,
    x_node_id: str = Header(...),
    x_timestamp: str = Header(...),
    x_signature: str = Header(...),
    db: AsyncSession = Depends(get_db)
):
    node = await db.get(Node, request.node_id)
    if not node:
        node = Node(
            id=request.node_id,
            hostname=request.hostname,
            agent_version=request.agent_version,
            last_heartbeat=datetime.datetime.utcnow()
        )
        db.add(node)
    else:
        node.hostname = request.hostname
        node.agent_version = request.agent_version
        node.last_heartbeat = datetime.datetime.utcnow()
        
    await db.commit()
    return {"status": "success"}
