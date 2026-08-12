from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy import event
from config.settings import settings

engine = create_async_engine(
    settings.db_url,
    echo=False,
    # aiosqlite 连接级 busy_timeout（秒）：锁竞争时最多等待 30s，避免瞬时 "database is locked"
    connect_args={"timeout": 30},
)

@event.listens_for(engine.sync_engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    """每个连接统一设置 SQLite 行为：
    - WAL: 读写并发不互斥，大幅降低锁冲突（此前 rollback-journal 模式下读写互相阻塞）
    - busy_timeout: 兜底锁等待，与 connect_args timeout 一致
    """
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.close()

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

Base = declarative_base()

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
