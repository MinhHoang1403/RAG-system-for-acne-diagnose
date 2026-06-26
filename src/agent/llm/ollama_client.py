"""
src/agent/llm/ollama_client.py
==============================
Client for local Ollama instance.
"""

import logging
import os
import httpx

logger = logging.getLogger(__name__)

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

async def list_ollama_models() -> list[str]:
    """Fetch the list of available models from local Ollama."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
            response.raise_for_status()
            data = response.json()
            models = [model.get("name") for model in data.get("models", [])]
            return models
    except Exception as e:
        logger.warning(f"Could not connect to Ollama to list models: {e}")
        return []

async def generate_ollama_response(model: str, system_prompt: str | None, prompt: str, temperature: float = 0.2) -> str:
    """Generate response from local Ollama model."""
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": temperature
        }
    }

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
            return data.get("message", {}).get("content", "")
    except httpx.ConnectError:
        raise ConnectionError("Model local hiện chưa khả dụng. Hãy mở Ollama rồi thử lại.")
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
             raise ValueError(f"Model Ollama chưa có. Hãy chạy: ollama pull {model.split(':')[0]}")
        raise
