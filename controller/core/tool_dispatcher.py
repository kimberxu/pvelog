import httpx
import uuid
import hmac
import hashlib
import json
import time
from config.settings import settings
from core.tool_validator import validate_tool_call
from db.database import AsyncSessionLocal
from db.models import AuditLog

class ToolDispatcher:
    async def dispatch(self, node_id: str, agent_url: str, action: str, params: dict) -> dict:
        validated_params = validate_tool_call(action, params)
        
        request_id = str(uuid.uuid4())
        payload = {
            "request_id": request_id,
            "action": action,
            "params": validated_params.model_dump(),
            "timeout_seconds": 30
        }
        
        body_bytes = json.dumps(payload).encode()
        sign_payload = request_id.encode() + body_bytes
        
        signature = hmac.new(
            settings.psk_secret.encode(),
            sign_payload,
            hashlib.sha256
        ).hexdigest()
        
        headers = {
            "Content-Type": "application/json",
            "X-Request-ID": request_id,
            "X-Signature": signature
        }
        
        start_time = time.time()
        status = "error"
        result_summary = ""
        duration = 0
        
        try:
            async with httpx.AsyncClient(timeout=35.0) as client:
                resp = await client.post(
                    f"{agent_url}/api/v1/execute",
                    headers=headers,
                    content=body_bytes
                )
                resp.raise_for_status()
                data = resp.json()
                status = data.get("status", "unknown")
                result_summary = json.dumps(data.get("result", {}))
                duration = int((time.time() - start_time) * 1000)
                
                await self._log_audit(request_id, node_id, action, params, status, result_summary, duration)
                
                return data
        except Exception as e:
            duration = int((time.time() - start_time) * 1000)
            result_summary = str(e)
            await self._log_audit(request_id, node_id, action, params, status, result_summary, duration)
            raise e

    async def _log_audit(self, request_id, node_id, action, params, status, summary, duration):
        async with AsyncSessionLocal() as session:
            log = AuditLog(
                event_type="TOOL_CALL",
                request_id=request_id,
                node_id=node_id,
                action=action,
                params=params,
                result_status=status,
                result_summary=summary[:2000], # truncate if too long
                duration_ms=duration,
                triggered_by="langgraph_analyzer"
            )
            session.add(log)
            await session.commit()

tool_dispatcher = ToolDispatcher()
