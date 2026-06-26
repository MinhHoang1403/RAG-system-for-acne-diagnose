"""
src/agent/llm/provider.py
=========================
Abstraction for LLM providers (Gemini, Ollama) with fallback support.
"""

import os
import logging
import google.generativeai as genai
from typing import Optional

from src.agent.llm.ollama_client import generate_ollama_response, list_ollama_models

logger = logging.getLogger(__name__)

async def _call_gemini(prompt: str, system_prompt: Optional[str], model_name: str, temperature: float) -> str:
    """Helper to call Gemini API."""
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY is not set.")
    genai.configure(api_key=api_key)
    
    # In genai, system instructions can be set on the model instantiation in newer SDKs, 
    # but the prompt template in acne-agent-system already includes everything in `prompt`.
    # If system_prompt is provided, we just prepend it.
    final_prompt = prompt
    if system_prompt:
        final_prompt = f"{system_prompt}\n\n{prompt}"
        
    model = genai.GenerativeModel(model_name)
    response = await model.generate_content_async(
        final_prompt,
        generation_config=genai.GenerationConfig(temperature=temperature)
    )
    return response.text

async def _call_gemini_sync(prompt: str, system_prompt: Optional[str], model_name: str, temperature: float) -> str:
    """Helper to call Gemini API synchronously."""
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY is not set.")
    genai.configure(api_key=api_key)
    
    final_prompt = prompt
    if system_prompt:
        final_prompt = f"{system_prompt}\n\n{prompt}"
        
    model = genai.GenerativeModel(model_name)
    response = model.generate_content(
        final_prompt,
        generation_config=genai.GenerationConfig(temperature=temperature)
    )
    return response.text

async def generate_llm_response(
    prompt: str,
    system_prompt: Optional[str] = None,
    provider: str = "gemini",
    model: Optional[str] = None,
    temperature: float = 0.2,
    allow_fallback: bool = True,
    use_sync: bool = False
) -> dict:
    """
    Generate LLM response with automatic fallback logic.
    Returns:
        dict: {
            "text": str,
            "provider": str,
            "model": str,
            "fallback_used": bool,
            "fallback_provider": str | None,
            "fallback_model": str | None,
            "error": str | None
        }
    """
    provider = provider or "gemini"
    
    # Resolve default models
    if provider == "gemini":
        model = model or os.getenv("GOOGLE_MODEL", "gemini-2.5-flash")
        if model == "gemini-1.5-flash":
            model = "gemini-2.5-flash"
    elif provider == "ollama":
        configured_model = os.getenv("OLLAMA_MODEL", "qwen2.5")
        model = model or (
            configured_model if ":" in configured_model else f"{configured_model}:latest"
        )
        
    result = {
        "text": "",
        "provider": provider,
        "model": model,
        "fallback_used": False,
        "fallback_provider": None,
        "fallback_model": None,
        "error": None
    }
    
    try:
        # 1. Try primary provider
        if provider == "gemini":
            logger.info(f"Calling Gemini ({model})...")
            if use_sync:
                result["text"] = await _call_gemini_sync(prompt, system_prompt, model, temperature) # wrapper is still async
            else:
                result["text"] = await _call_gemini(prompt, system_prompt, model, temperature)
            return result
            
        elif provider == "ollama":
            logger.info(f"Calling Ollama ({model})...")
            result["text"] = await generate_ollama_response(model, system_prompt, prompt, temperature)
            return result
            
        else:
            raise ValueError(f"Unknown provider: {provider}")
            
    except Exception as e:
        logger.warning(f"Primary LLM ({provider}/{model}) failed: {e}")
        
        # 2. Try Fallback
        if not allow_fallback:
            logger.error("Fallback is disabled. Failing.")
            result["error"] = str(e)
            raise e
            
        logger.info("Attempting fallback...")
        
        if provider == "gemini":
            # Fallback to Ollama
            available_models = await list_ollama_models()
            fallback_model = None
            configured_model = os.getenv("OLLAMA_MODEL", "qwen2.5")
            configured_model = (
                configured_model
                if ":" in configured_model
                else f"{configured_model}:latest"
            )
            if configured_model in available_models:
                fallback_model = configured_model
            elif "qwen2.5:latest" in available_models:
                fallback_model = "qwen2.5:latest"
            elif "qwen3:latest" in available_models:
                fallback_model = "qwen3:latest"
                
            if fallback_model:
                try:
                    logger.info(f"Fallback to Ollama ({fallback_model})...")
                    text = await generate_ollama_response(fallback_model, system_prompt, prompt, temperature)
                    result["text"] = text
                    result["fallback_used"] = True
                    result["fallback_provider"] = "ollama"
                    result["fallback_model"] = fallback_model
                    return result
                except Exception as fb_err:
                    logger.error(f"Fallback Ollama also failed: {fb_err}")
                    result["error"] = f"Primary ({e}) and Fallback ({fb_err}) both failed."
                    raise Exception(result["error"])
            else:
                logger.error("No suitable Ollama models available for fallback.")
                result["error"] = str(e)
                raise e
                
        elif provider == "ollama":
            # Fallback to Gemini
            fallback_model = os.getenv("GOOGLE_MODEL", "gemini-2.5-flash")
            if fallback_model == "gemini-1.5-flash":
                fallback_model = "gemini-2.5-flash"
                
            try:
                logger.info(f"Fallback to Gemini ({fallback_model})...")
                if use_sync:
                    text = await _call_gemini_sync(prompt, system_prompt, fallback_model, temperature)
                else:
                    text = await _call_gemini(prompt, system_prompt, fallback_model, temperature)
                result["text"] = text
                result["fallback_used"] = True
                result["fallback_provider"] = "gemini"
                result["fallback_model"] = fallback_model
                return result
            except Exception as fb_err:
                logger.error(f"Fallback Gemini also failed: {fb_err}")
                result["error"] = f"Primary ({e}) and Fallback ({fb_err}) both failed."
                raise Exception(result["error"])
