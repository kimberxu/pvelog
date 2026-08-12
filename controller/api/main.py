from fastapi import FastAPI
from api.routes import log_ingest, heartbeat, config, analysis
from api.middleware.auth import PSKAuthMiddleware
from db.database import engine, Base
from scheduler.tasks import periodic_inspection, cleanup_old_data, daily_report_loop
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

logger = logging.getLogger(__name__)

async def _column_exists(conn, table: str, column: str) -> bool:
    """检查 SQLite 表是否已存在某列（幂等迁移用）。"""
    result = await conn.execute(text(f"PRAGMA table_info({table})"))
    rows = result.fetchall()
    return any(row[1] == column for row in rows)

@app.on_event("startup")
async def startup_event():
    # 初始化 DB schema。整体容错：任何 DB 异常只记日志，绝不阻塞应用启动。
    # 注：WAL 与 busy_timeout 已由 db/database.py 引擎级统一配置（每个连接生效）。
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

            # 幂等迁移：仅当列缺失时补列，不再依赖 try/except 吞异常
            if not await _column_exists(conn, "nodes", "agent_url"):
                await conn.execute(text("ALTER TABLE nodes ADD COLUMN agent_url VARCHAR(255)"))
                logger.info("[Startup] Migrated: nodes.agent_url")

            if not await _column_exists(conn, "analysis_records", "created_at"):
                # SQLite 限制：ADD COLUMN 不允许非恒定默认值（DEFAULT CURRENT_TIMESTAMP 会报错），
                # 先加可空列，再回填旧数据；新行由 ORM server_default 填充
                await conn.execute(text("ALTER TABLE analysis_records ADD COLUMN created_at DATETIME"))
                await conn.execute(text("UPDATE analysis_records SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL"))
                logger.info("[Startup] Migrated: analysis_records.created_at")

        logger.info("[Startup] DB schema ready")
    except Exception as e:
        logger.error(f"[Startup] DB initialization failed (continuing): {e}", exc_info=True)
    # Start periodic inspection
    asyncio.create_task(periodic_inspection())
    # Start cleanup task
    asyncio.create_task(cleanup_old_data())
    # Start daily report loop
    asyncio.create_task(daily_report_loop())

app.include_router(log_ingest.router, prefix="/api/v1", tags=["Logs"])
app.include_router(heartbeat.router, prefix="/api/v1", tags=["Heartbeat"])
app.include_router(config.router, prefix="/api/v1", tags=["Config"])
app.include_router(analysis.router, prefix="/api/v1", tags=["Analysis"])
