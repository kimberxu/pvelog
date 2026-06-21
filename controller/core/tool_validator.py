from pydantic import BaseModel, field_validator
from typing import Dict, Any, Type
import re

class DiagnosePingParams(BaseModel):
    target_ip: str

    @field_validator('target_ip')
    def validate_ip(cls, v):
        if not re.match(r"^(10\.|192\.168\.|172\.(1[6-9]|2[0-9]|3[0-1])\.)", v):
            raise ValueError("Target IP must be a private network IP.")
        return v

class DiagnoseSmartParams(BaseModel):
    device: str
    
    @field_validator('device')
    def validate_device(cls, v):
        if not re.match(r"^(sd[a-z]|nvme[0-9]n[0-9]|vd[a-z])$", v):
            raise ValueError("Invalid device name.")
        return v

class GetDetailedJournalParams(BaseModel):
    service: str
    minutes: int

    @field_validator('minutes')
    def validate_minutes(cls, v):
        if not (1 <= v <= 60):
            raise ValueError("Minutes must be between 1 and 60.")
        return v

class CheckServiceStatusParams(BaseModel):
    service: str

    @field_validator('service')
    def validate_service(cls, v):
        allowed = ["corosync", "pveproxy", "ceph-mon", "pvedaemon", "pve-cluster"]
        if v not in allowed:
            raise ValueError(f"Service {v} is not allowed.")
        return v

ACTION_SCHEMAS: Dict[str, Type[BaseModel]] = {
    "diagnose_ping": DiagnosePingParams,
    "diagnose_smart": DiagnoseSmartParams,
    "get_detailed_journal": GetDetailedJournalParams,
    "check_service_status": CheckServiceStatusParams,
}

def validate_tool_call(action: str, params: Dict[str, Any]) -> BaseModel:
    if action not in ACTION_SCHEMAS:
        raise ValueError(f"Action {action} is not permitted.")
    schema = ACTION_SCHEMAS[action]
    return schema(**params)
