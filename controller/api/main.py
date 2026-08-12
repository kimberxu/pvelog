from fastapi import FastAPI
from contextlib import asynccontextmanager
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

from sqlalchemy import text

logger = logging.getLogger(__name__)

async def _column_exists(conn, table: str, column: str) -> bool:
    """检查 SQLite 表是否已存在某列（幂等迁移用）。"""
    result = await conn.execute(text(f"PRAGMA table_info({table})"))
    rows = result.fetchall()
    return any(row[1] == column for row in rows)

# 幂等迁移清单：表名 -> 缺失时补充的列及其 DDL
SCHEMA_MIGRATIONS = {
    "nodes": [
        ("agent_url", "ALTER TABLE nodes ADD COLUMN agent_url VARCHAR(255)"),
        ("cpu_usage_percent", "ALTER TABLE nodes ADD COLUMN cpu_usage_percent FLOAT"),
        ("memory_usage_percent", "ALTER TABLE nodes ADD COLUMN memory_usage_percent FLOAT"),
        ("disk_usage", "ALTER TABLE nodes ADD COLUMN disk_usage JSON"),
    ],
    "analysis_records": [
        # SQLite 限制：ADD COLUMN 不允许非恒定默认值（DEFAULT CURRENT_TIMESTAMP 会报错），
        # 先加可空列，再回填旧数据；新行由 ORM server_default 填充
        ("created_at", None),
    ],
}

_background_tasks: list[asyncio.Task] = []

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 初始化 DB schema。整体容错：任何 DB 异常只记日志，绝不阻塞应用启动。
    # 注：WAL 与 busy_timeout 已由 db/database.py 引擎级统一配置（每个连接生效）。
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

            # 幂等迁移：仅当列缺失时补列
            for table, columns in SCHEMA_MIGRATIONS.items():
                for column, ddl in columns:
                    if await _column_exists(conn, table, column):
                        continue
                    if ddl:
                        await conn.execute(text(ddl))
                        logger.info(f"[Startup] Migrated: {table}.{column}")
                    elif table == "analysis_records" and column == "created_at":
                        await conn.execute(text("ALTER TABLE analysis_records ADD COLUMN created_at DATETIME"))
                        await conn.execute(text("UPDATE analysis_records SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL"))
                        logger.info("[Startup] Migrated: analysis_records.created_at")

        logger.info("[Startup] DB schema ready")
    except Exception as e:
        logger.error(f"[Startup] DB initialization failed (continuing): {e}", exc_info=True)

    # Start periodic inspection
    _background_tasks.append(asyncio.create_task(periodic_inspection()))
    # Start cleanup task
    _background_tasks.append(asyncio.create_task(cleanup_old_data()))
    # Start daily report loop
    _background_tasks.append(asyncio.create_task(daily_report_loop()))
    try:
        yield
    finally:
        # 优雅关闭：取消后台任务，避免事件循环残留
        logger.info("[Shutdown] Cancelling background tasks")
        for task in _background_tasks:
            task.cancel()
        await asyncio.gather(*_background_tasks, return_exceptions=True)

app = FastAPI(title="PVE AIOps Controller", lifespan=lifespan)

app.add_middleware(PSKAuthMiddleware)

app.include_router(log_ingest.router, prefix="/api/v1", tags=["Logs"])
app.include_router(heartbeat.router, prefix="/api/v1", tags=["Heartbeat"])
app.include_router(config.router, prefix="/api/v1", tags=["Config"])
app.include_router(analysis.router, prefix="/api/v1", tags=["Analysis"])
