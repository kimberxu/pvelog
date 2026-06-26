from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
import datetime

from db.database import get_db
from db.models import AnalysisRecord
from pydantic import BaseModel
from scheduler.tasks import generate_daily_report

router = APIRouter()

class AnalysisRecordSchema(BaseModel):
    id: str
    node_id: str
    severity: str
    report: str
    tool_calls_count: int
    llm_tokens_used: int
    alert_sent: bool
    created_at: datetime.datetime

    class Config:
        from_attributes = True

@router.get("/analysis", response_model=List[AnalysisRecordSchema])
async def list_analysis_records(
    node_id: Optional[str] = None,
    limit: int = 20,
    db: AsyncSession = Depends(get_db)
):
    """
    Get a list of recent analysis records.
    """
    query = select(AnalysisRecord)
    if node_id:
        query = query.where(AnalysisRecord.node_id == node_id)
    query = query.order_by(AnalysisRecord.created_at.desc()).limit(limit)
    
    result = await db.execute(query)
    records = result.scalars().all()
    return records

@router.get("/analysis/{analysis_id}", response_model=AnalysisRecordSchema)
async def get_analysis_record(
    analysis_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Get details of a specific analysis record.
    """
    record = await db.get(AnalysisRecord, analysis_id)
    if not record:
        raise HTTPException(status_code=404, detail="Analysis record not found")
    return record

@router.post("/analysis/daily-report")
async def trigger_daily_report():
    """
    手动触发生成并发送每日报告（便于调试和确认）。
    """
    await generate_daily_report()
    return {"status": "success", "message": "每日报告已成功生成并发送"}
