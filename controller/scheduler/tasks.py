import asyncio
import logging
import uuid
from datetime import datetime, timedelta
from db.database import AsyncSessionLocal
from db.models import Node, LogBatch, LogEntry, AnalysisRecord
from sqlalchemy import select, delete
from config.settings import settings
from core.analyzer import analyzer
from core.alert_manager import alert_manager

logger = logging.getLogger(__name__)

def format_log_entries(entries):
    lines = []
    for e in entries:
        lines.append(f"[{e.timestamp}] <{e.priority}> {e.unit}: {e.message}")
    return "\n".join(lines)

async def periodic_inspection():
    while True:
        await asyncio.sleep(settings.inspect_interval_sec)
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(select(Node))
                nodes = result.scalars().all()
                for node in nodes:
                    if not node.agent_url:
                        logger.warning(f"[Scheduler] Node {node.id} has no agent_url, skipping analysis.")
                        continue
                        
                    unanalyzed = (await session.execute(
                        select(LogBatch).where(
                            LogBatch.node_id == node.id,
                            LogBatch.analyzed == False
                        )
                    )).scalars().all()
                    
                    if not unanalyzed:
                        logger.info(f"[Scheduler] Node {node.id}: no new logs to analyze, skipping")
                        continue
                        
                    batch_ids = [b.batch_id for b in unanalyzed]
                    entries = (await session.execute(
                        select(LogEntry).where(LogEntry.batch_id.in_(batch_ids))
                    )).scalars().all()
                    
                    if not entries:
                        for batch in unanalyzed:
                            batch.analyzed = True
                        await session.commit()
                        continue
                        
                    logs_text = format_log_entries(entries)
                    logger.info(f"[Scheduler] Analyzing {len(entries)} logs for Node: {node.id}")
                    
                    state = {
                        "logs": logs_text,
                        "node_id": node.id,
                        "agent_url": node.agent_url,
                        "iterations": 0,
                        "messages": [],
                        "final_report": "",
                        "severity": ""
                    }
                    
                    final_state = await analyzer.ainvoke(state)
                    
                    report = final_state.get("final_report", "No report generated.")
                    severity = final_state.get("severity", "WARNING")
                    
                    analysis_id = str(uuid.uuid4())
                    record = AnalysisRecord(
                        id=analysis_id,
                        node_id=node.id,
                        severity=severity,
                        report=report,
                        tool_calls_count=final_state.get("iterations", 0),
                        llm_tokens_used=final_state.get("tokens_used", 0),
                        alert_sent=False
                    )
                    
                    if alert_manager.should_alert(node.id, severity):
                        alert_manager.send_alert(node.id, report, severity)
                        record.alert_sent = True
                        
                    session.add(record)
                    
                    for batch in unanalyzed:
                        batch.analyzed = True
                        batch.analysis_id = analysis_id
                        
                    await session.commit()
        except Exception as e:
            logger.error(f"[Scheduler] Error during inspection: {e}", exc_info=True)

async def cleanup_old_data():
    while True:
        await asyncio.sleep(86400) # 24 hours
        try:
            cutoff = datetime.utcnow() - timedelta(days=7)
            async with AsyncSessionLocal() as session:
                await session.execute(
                    delete(LogEntry).where(LogEntry.received_at < cutoff)
                )
                await session.execute(
                    delete(LogBatch).where(LogBatch.received_at < cutoff, LogBatch.analyzed == True)
                )
                await session.commit()
                logger.info(f"[Scheduler] Cleanup completed. Removed logs older than {cutoff}")
        except Exception as e:
            logger.error(f"[Scheduler] Error during cleanup: {e}", exc_info=True)
