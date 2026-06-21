from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
import datetime

from db.database import get_db
from db.models import LogBatch, Node

router = APIRouter()

class LogEntry(BaseModel):
    timestamp: str
    priority: int
    unit: str
    message: str

class LogPushRequest(BaseModel):
    node_id: str
    hostname: str
    batch_id: str
    since_cursor: str
    entries: List[LogEntry]
    entry_count: int
    filtered_count: int
    agent_version: str

@router.post("/logs")
async def ingest_logs(
    request: LogPushRequest,
    x_node_id: str = Header(...),
    x_timestamp: str = Header(...),
    x_signature: str = Header(...),
    db: AsyncSession = Depends(get_db)
):
    # Check or create node
    node = await db.get(Node, request.node_id)
    if not node:
        node = Node(
            id=request.node_id, 
            hostname=request.hostname,
            agent_version=request.agent_version,
            last_heartbeat=datetime.datetime.utcnow(),
            last_log_cursor=request.since_cursor
        )
        db.add(node)
    else:
        node.last_log_cursor = request.since_cursor
        node.last_heartbeat = datetime.datetime.utcnow()
        
    # Create batch record
    batch = LogBatch(
        batch_id=request.batch_id,
        node_id=request.node_id,
        entry_count=request.entry_count,
        filtered_count=request.filtered_count
    )
    db.add(batch)
    
    await db.commit()
    return {"status": "success", "batch_id": request.batch_id}
