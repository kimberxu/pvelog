from fastapi import APIRouter
from pydantic import BaseModel
from typing import List
from config.settings import settings

router = APIRouter()

class ConfigResponse(BaseModel):
    filter_patterns: List[str]

@router.get("/config", response_model=ConfigResponse)
async def get_config():
    return ConfigResponse(
        filter_patterns=settings.filter_patterns
    )
