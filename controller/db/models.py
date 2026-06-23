from sqlalchemy import Column, String, Integer, Float, DateTime, Boolean, JSON, func
from db.database import Base

class Node(Base):
    __tablename__ = "nodes"
    id = Column(String(64), primary_key=True, index=True)
    hostname = Column(String(255))
    agent_version = Column(String(64))
    agent_url = Column(String(255), nullable=True)
    last_heartbeat = Column(DateTime)
    last_log_cursor = Column(String(255))
    is_online = Column(Boolean, default=True)

class LogBatch(Base):
    __tablename__ = "log_batches"
    batch_id = Column(String(36), primary_key=True)
    node_id = Column(String(64))
    entry_count = Column(Integer)
    filtered_count = Column(Integer)
    received_at = Column(DateTime, server_default=func.now())
    analyzed = Column(Boolean, default=False)
    analysis_id = Column(String(36), nullable=True)

class LogEntry(Base):
    __tablename__ = "log_entries"
    id = Column(Integer, primary_key=True, autoincrement=True)
    batch_id = Column(String(36), index=True)
    node_id = Column(String(64), index=True)
    timestamp = Column(String(64))
    priority = Column(Integer)
    unit = Column(String(255))
    message = Column(String)
    received_at = Column(DateTime, server_default=func.now())

class AnalysisRecord(Base):
    __tablename__ = "analysis_records"
    id = Column(String(36), primary_key=True)
    node_id = Column(String(64))
    severity = Column(String(64))
    report = Column(String)
    tool_calls_count = Column(Integer)
    llm_tokens_used = Column(Integer)
    alert_sent = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, server_default=func.now())
    event_type = Column(String(64))
    request_id = Column(String(36))
    node_id = Column(String(64))
    action = Column(String(128))
    params = Column(JSON)
    result_status = Column(String(64))
    result_summary = Column(String)
    duration_ms = Column(Integer)
    triggered_by = Column(String(64))
