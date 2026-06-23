import httpx
import json
import asyncio
import time
from typing import Dict, Any, List
from config.settings import settings
import logging

logger = logging.getLogger(__name__)

class LLMClient:
    def __init__(self):
        self.base_url = settings.llm_base_url
        self.api_key = settings.llm_api_key
        self.model = settings.llm_model
        
    async def chat_completion(self, messages: List[Dict[str, str]], tools: List[Dict[str, Any]] = None, max_retries: int = 3) -> Dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model,
            "messages": messages
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
            
        logger.info(f"Sending request to LLM (model: {self.model})")
        start_time = time.time()
        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(
                        f"{self.base_url}/chat/completions",
                        headers=headers,
                        json=payload
                    )
                    response.raise_for_status()
                    result = response.json()
                    elapsed = time.time() - start_time
                    logger.info(f"LLM request succeeded in {elapsed:.2f}s")
                    logger.debug(f"LLM Response: {json.dumps(result, ensure_ascii=False)}")
                    return result
            except httpx.HTTPError as e:
                logger.warning(f"LLM request attempt {attempt + 1} failed: {e}")
                if attempt == max_retries - 1:
                    logger.error(f"LLM request failed after {max_retries} attempts: {e}")
                    raise e
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
        return {}

llm_client = LLMClient()

