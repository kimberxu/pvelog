import hmac
import hashlib
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from config.settings import settings

class PSKAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Only verify specific routes, e.g., /api/v1/logs, /api/v1/heartbeat
        if not request.url.path.startswith("/api/v1/logs") and not request.url.path.startswith("/api/v1/heartbeat"):
            return await call_next(request)
            
        x_node_id = request.headers.get("X-Node-ID")
        x_timestamp = request.headers.get("X-Timestamp")
        x_signature = request.headers.get("X-Signature")
        
        if not all([x_node_id, x_timestamp, x_signature]):
            return JSONResponse(status_code=401, content={"detail": "Missing Auth Headers"})
            
        body = await request.body()
        payload = x_node_id + x_timestamp + body.decode("utf-8")
        
        expected_sig = hmac.new(
            settings.psk_secret.encode(),
            payload.encode(),
            hashlib.sha256
        ).hexdigest()
        
        if not hmac.compare_digest(expected_sig, x_signature):
            return JSONResponse(status_code=401, content={"detail": "Invalid Signature"})
            
        async def receive():
            return {"type": "http.request", "body": body}
        request._receive = receive
        
        response = await call_next(request)
        return response
