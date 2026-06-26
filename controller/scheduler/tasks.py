import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from db.database import AsyncSessionLocal
from db.models import Node, LogBatch, LogEntry, AnalysisRecord, AuditLog
from sqlalchemy import select, delete
from config.settings import settings
from core.analyzer import analyzer
from core.alert_manager import alert_manager
from core.log_filter import log_filter

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
                    
                    if log_filter.is_all_routine(entries):
                        logger.info(f"[Scheduler] All {len(entries)} logs for Node {node.id} are routine. Skipping LLM analysis.")
                        final_state = {
                            "iterations": 0,
                            "tokens_used": 0,
                            "final_report": "No anomalies detected. All logs are routine background tasks or expected statuses.",
                            "severity": "INFO"
                        }
                    else:
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

async def generate_daily_report():
    try:
        local_now = datetime.now().astimezone()
        start_local = local_now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
        end_local = start_local + timedelta(days=1, microseconds=-1)
        start_utc = start_local.astimezone(timezone.utc).replace(tzinfo=None)
        end_utc = end_local.astimezone(timezone.utc).replace(tzinfo=None)

        async with AsyncSessionLocal() as session:
            # Nodes
            nodes_result = await session.execute(select(Node))
            nodes = nodes_result.scalars().all()
            
            # Analysis Records
            analysis_result = await session.execute(
                select(AnalysisRecord).where(
                    AnalysisRecord.created_at >= start_utc,
                    AnalysisRecord.created_at <= end_utc
                )
            )
            records = analysis_result.scalars().all()
            
            # Audit Logs
            audit_result = await session.execute(
                select(AuditLog).where(
                    AuditLog.timestamp >= start_utc,
                    AuditLog.timestamp <= end_utc
                )
            )
            audit_logs = audit_result.scalars().all()

            # Aggregate nodes
            node_lines = []
            for n in nodes:
                status = "在线" if n.is_online else "离线"
                node_lines.append(f"- [{n.id}] {n.hostname} | 状态: {status} | 版本: {n.agent_version} | 上次心跳: {n.last_heartbeat}")

            # Aggregate analysis
            severity_counts_per_node = {}
            total_tokens = 0
            total_llm_calls = 0
            for r in records:
                node_id = r.node_id
                if node_id not in severity_counts_per_node:
                    severity_counts_per_node[node_id] = {}
                severity_counts_per_node[node_id][r.severity] = severity_counts_per_node[node_id].get(r.severity, 0) + 1
                total_tokens += (r.llm_tokens_used or 0)
                total_llm_calls += (r.tool_calls_count or 0)
                
            analysis_lines = []
            if not severity_counts_per_node:
                analysis_lines.append("- 无记录")
            else:
                for node_id, counts in severity_counts_per_node.items():
                    analysis_lines.append(f"- 节点 [{node_id}]:")
                    for k, v in counts.items():
                        analysis_lines.append(f"  * {k}: {v}次")
                
            # Aggregate audit
            api_calls = len(audit_logs)
            success_calls = sum(1 for a in audit_logs if a.result_status and a.result_status.lower() == "success")
            failed_calls = api_calls - success_calls

            date_str = start_local.strftime("%Y-%m-%d")
            report = f"""【PVE AIOps】每日运行状态汇报 ({date_str})

1. PVE 节点状态
=========================
{chr(10).join(node_lines) if node_lines else "- 无节点"}

2. 日志分析汇总
=========================
总分析次数: {len(records)}
严重程度分布:
{chr(10).join(analysis_lines)}

3. 资源与调用消耗
=========================
LLM API 调用次数 (总计): {total_llm_calls}
分析工具调用总计: {api_calls} (成功: {success_calls}, 失败: {failed_calls})
消耗总 Token 数: {total_tokens:,}

---
本邮件由 PVE AIOps Controller 自动生成。
"""
            from services.email_service import send_email
            send_email(f"[PVE AIOps] 每日运行状态汇报 ({date_str})", report)
            logger.info(f"[Scheduler] Daily report generated and sent for {date_str}")
    except Exception as e:
        logger.error(f"[Scheduler] Error generating daily report: {e}", exc_info=True)

async def daily_report_loop():
    while True:
        try:
            local_now = datetime.now().astimezone()
            target = local_now.replace(hour=8, minute=40, second=0, microsecond=0)
            if local_now >= target:
                target += timedelta(days=1)
            
            sleep_seconds = (target - local_now).total_seconds()
            logger.info(f"[Scheduler] Daily report loop sleeping for {sleep_seconds} seconds until {target}")
            await asyncio.sleep(sleep_seconds)
            
            await generate_daily_report()
        except Exception as e:
            logger.error(f"[Scheduler] Error in daily_report_loop: {e}", exc_info=True)
            await asyncio.sleep(60)
