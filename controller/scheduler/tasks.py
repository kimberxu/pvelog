import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from db.database import AsyncSessionLocal
from db.models import Node, LogBatch, LogEntry, AnalysisRecord, AuditLog
from sqlalchemy import select, delete, text
from config.settings import settings
from core.analyzer import analyzer
from core.alert_manager import alert_manager
from core.log_filter import log_filter
from services.report_chart import SEVERITY_COLORS, SEVERITY_ORDER

logger = logging.getLogger(__name__)

def format_log_entries(entries):
    lines = []
    for e in entries:
        lines.append(f"[{e.timestamp}] <{e.priority}> {e.unit}: {e.message}")
    return "\n".join(lines)

async def _inspect_node(node_id: str, agent_url: str):
    """分析单个节点的未处理日志。每个节点独立 session，供 asyncio.gather 并行调用。"""
    async with AsyncSessionLocal() as session:
        unanalyzed = (await session.execute(
            select(LogBatch).where(
                LogBatch.node_id == node_id,
                LogBatch.analyzed == False
            )
        )).scalars().all()

        if not unanalyzed:
            logger.info(f"[Scheduler] Node {node_id}: no new logs to analyze, skipping")
            return

        batch_ids = [b.batch_id for b in unanalyzed]
        entries = (await session.execute(
            select(LogEntry).where(LogEntry.batch_id.in_(batch_ids))
        )).scalars().all()

        if not entries:
            for batch in unanalyzed:
                batch.analyzed = True
            await session.commit()
            return

        logs_text = format_log_entries(entries)
        logger.info(f"[Scheduler] Analyzing {len(entries)} logs for Node: {node_id}")

        if log_filter.is_all_routine(entries):
            logger.info(f"[Scheduler] All {len(entries)} logs for Node {node_id} are routine. Skipping LLM analysis.")
            final_state = {
                "iterations": 0,
                "tokens_used": 0,
                "final_report": "No anomalies detected. All logs are routine background tasks or expected statuses.",
                "severity": "INFO"
            }
        else:
            state = {
                "logs": logs_text,
                "node_id": node_id,
                "agent_url": agent_url,
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
            node_id=node_id,
            severity=severity,
            report=report,
            tool_calls_count=final_state.get("iterations", 0),
            llm_tokens_used=final_state.get("tokens_used", 0),
            alert_sent=False
        )

        if severity in ["ERROR", "CRITICAL"]:
            # 冷却检查基于 DB 最近告警记录（持久化，重启不丢）
            cooldown_start = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=alert_manager.cooldown_minutes)
            recent_alert = (await session.execute(
                select(AnalysisRecord).where(
                    AnalysisRecord.node_id == node_id,
                    AnalysisRecord.alert_sent == True,
                    AnalysisRecord.created_at >= cooldown_start
                ).limit(1)
            )).scalars().first()
            if not recent_alert:
                await asyncio.to_thread(alert_manager.send_alert, node_id, report, severity)
                record.alert_sent = True

        session.add(record)

        for batch in unanalyzed:
            batch.analyzed = True
            batch.analysis_id = analysis_id

        await session.commit()

async def periodic_inspection():
    while True:
        await asyncio.sleep(settings.inspect_interval_sec)
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(select(Node))
                nodes = result.scalars().all()

            # 并行分析各节点（每节点独立 session，互不阻塞）；失败只记日志不影响其他节点
            tasks = [
                _inspect_node(node.id, node.agent_url)
                for node in nodes
                if node.agent_url
            ]
            if not nodes:
                logger.warning("[Scheduler] No nodes registered, skipping inspection")
            for node in nodes:
                if not node.agent_url:
                    logger.warning(f"[Scheduler] Node {node.id} has no agent_url, skipping analysis.")
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=False)
        except Exception as e:
            logger.error(f"[Scheduler] Error during inspection: {e}", exc_info=True)

async def cleanup_old_data():
    while True:
        await asyncio.sleep(86400) # 24 hours
        try:
            cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=7)
            async with AsyncSessionLocal() as session:
                await session.execute(
                    delete(LogEntry).where(LogEntry.received_at < cutoff)
                )
                await session.execute(
                    delete(LogBatch).where(LogBatch.received_at < cutoff, LogBatch.analyzed == True)
                )
                await session.commit()
                logger.info(f"[Scheduler] Cleanup completed. Removed logs older than {cutoff}")

                # WAL checkpoint：合并 WAL 回主库，避免 -wal 文件无限增长
                try:
                    await session.execute(text("PRAGMA wal_checkpoint(TRUNCATE)"))
                except Exception as e:
                    logger.warning(f"[Scheduler] wal_checkpoint failed: {e}")

            # 每周日执行 VACUUM，回收删除释放的磁盘空间（SQLite 删除后文件不会自动缩小）
            if datetime.now(timezone.utc).weekday() == 6:
                try:
                    async with AsyncSessionLocal() as session:
                        await session.execute(text("VACUUM"))
                    logger.info("[Scheduler] VACUUM completed")
                except Exception as e:
                    logger.error(f"[Scheduler] VACUUM failed: {e}", exc_info=True)
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
                
            # Aggregate audit
            api_calls = len(audit_logs)
            success_calls = sum(1 for a in audit_logs if a.result_status and a.result_status.lower() == "success")
            failed_calls = api_calls - success_calls

            date_str = start_local.strftime("%Y-%m-%d")

            # 生成图表
            from services.report_chart import generate_charts
            charts = generate_charts(severity_counts_per_node, api_calls, success_calls, failed_calls)

            # 构造 HTML 邮件正文
            node_rows = "".join(
                f"""<tr style="border-bottom:1px solid #e0e0e0;">
<td style="padding:6px 10px;font-size:13px;">{n.id}</td>
<td style="padding:6px 10px;font-size:13px;">{n.hostname}</td>
<td style="padding:6px 10px;font-size:13px;color:{'#4caf50' if n.is_online else '#f44336'};font-weight:bold;">{'在线' if n.is_online else '离线'}</td>
<td style="padding:6px 10px;font-size:13px;">{n.agent_version}</td>
<td style="padding:6px 10px;font-size:13px;">{n.last_heartbeat or '-'}</td>
</tr>"""
                for n in nodes
            ) if nodes else "<tr><td colspan='5' style='padding:12px;color:#999;text-align:center;'>无节点</td></tr>"

            # 严重程度 HTML 汇总
            sev_items = []
            for node_id, counts in severity_counts_per_node.items():
                badges = "".join(
                    f"""<span style="display:inline-block;padding:1px 8px;margin:1px 2px;border-radius:3px;
font-size:12px;color:#fff;background:{SEVERITY_COLORS.get(k, '#999')};">{k}: {v}次</span>"""
                    for k, v in sorted(counts.items(), key=lambda x: list(SEVERITY_ORDER).index(x[0]) if x[0] in SEVERITY_ORDER else 99)
                )
                sev_items.append(f"<div style='margin:4px 0;'><b>节点 [{node_id}]:</b> {badges}</div>")
            sev_html = "".join(sev_items) if sev_items else "<div style='color:#999;'>无记录</div>"

            # 图表嵌入 HTML
            charts_html = ""
            if "chart_severity" in charts:
                charts_html += f"""<div style="text-align:center;margin:15px 0;">
<img src="cid:chart_severity" style="max-width:100%;height:auto;border:1px solid #e0e0e0;border-radius:4px;">
</div>"""
            if "chart_api" in charts:
                charts_html += f"""<div style="text-align:center;margin:15px 0;">
<img src="cid:chart_api" style="max-width:100%;height:auto;border:1px solid #e0e0e0;border-radius:4px;">
</div>"""

            html_body = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:'Noto Sans CJK SC','Microsoft YaHei',sans-serif;color:#333;max-width:720px;margin:0 auto;padding:20px;">

<h2 style="color:#1565c0;border-bottom:2px solid #1565c0;padding-bottom:8px;">PVE AIOps 每日运行状态汇报 ({date_str})</h2>

<h3 style="color:#37474f;margin-top:20px;">1. PVE 节点状态</h3>
<table style="border-collapse:collapse;width:100%;margin:8px 0;border-radius:4px;overflow:hidden;">
<thead>
<tr style="background:#1565c0;color:#fff;">
<th style="padding:6px 10px;text-align:left;font-size:13px;">节点</th>
<th style="padding:6px 10px;text-align:left;font-size:13px;">主机名</th>
<th style="padding:6px 10px;text-align:left;font-size:13px;">状态</th>
<th style="padding:6px 10px;text-align:left;font-size:13px;">版本</th>
<th style="padding:6px 10px;text-align:left;font-size:13px;">上次心跳</th>
</tr>
</thead>
<tbody>
{node_rows}
</tbody>
</table>

<h3 style="color:#37474f;margin-top:25px;">2. 日志分析汇总</h3>
<div style="background:#f5f5f5;padding:12px 16px;border-radius:4px;margin:8px 0;">
<div style="margin:4px 0;font-size:14px;">总分析次数: <b>{len(records)}</b></div>
<div style="margin:4px 0;font-size:14px;">严重程度分布:</div>
{sev_html}
</div>

{charts_html}

<h3 style="color:#37474f;margin-top:25px;">3. 资源与调用消耗</h3>
<table style="border-collapse:collapse;width:100%;margin:8px 0;font-size:14px;">
<tr><td style="padding:4px 12px;color:#666;width:180px;">LLM API 调用次数</td><td style="padding:4px 12px;font-weight:bold;">{total_llm_calls}</td></tr>
<tr><td style="padding:4px 12px;color:#666;">分析工具调用</td><td style="padding:4px 12px;font-weight:bold;">{api_calls} (成功: {success_calls}, 失败: {failed_calls})</td></tr>
<tr><td style="padding:4px 12px;color:#666;">消耗总 Token 数</td><td style="padding:4px 12px;font-weight:bold;">{total_tokens:,}</td></tr>
</table>

<div style="margin-top:25px;padding-top:12px;border-top:1px solid #e0e0e0;color:#999;font-size:12px;text-align:center;">
本邮件由 PVE AIOps Controller 自动生成。
</div>
</body>
</html>"""

            from services.email_service import send_html_email
            await asyncio.to_thread(
                send_html_email,
                f"[PVE AIOps] 每日运行状态汇报 ({date_str})",
                html_body,
                images=charts if charts else None,
            )
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
