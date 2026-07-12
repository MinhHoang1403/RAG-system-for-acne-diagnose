"""
src/agent/llm/provider.py
=========================
Abstraction for LLM providers (Gemini, Ollama) with fallback support.
"""

import asyncio
import os
import logging
from typing import Optional

from src.agent.llm.ollama_client import generate_ollama_response, list_ollama_models
from src.agent.text_encoding import repair_mojibake
from src.integrations.google_genai import generate_text_async, generate_text_sync
from src.quality.safe_fallback import sanitize_fallback_reason
from src.resilience.budget import DeadlineBudget
from src.resilience.circuit_breaker import CircuitBreaker, InMemoryCircuitStateStore
from src.resilience.contracts import RuntimeResilienceSettings, runtime_resilience_settings_from_env
from src.resilience.exceptions import (
    CircuitOpenError,
    PermanentProviderError,
    RuntimeResilienceError,
)
from src.resilience.provider import call_provider_with_resilience
from src.resilience.retry import RetryPolicy

logger = logging.getLogger(__name__)

DEFAULT_GEMINI_MODEL = "gemini-3.5-flash"
DEFAULT_OLLAMA_MODEL = "qwen3:8b"

_CIRCUIT_STORE = InMemoryCircuitStateStore()
_CIRCUIT_BREAKER = CircuitBreaker(runtime_resilience_settings_from_env(), store=_CIRCUIT_STORE)


def _refresh_circuit_breaker(settings: RuntimeResilienceSettings) -> CircuitBreaker:
    global _CIRCUIT_BREAKER
    _CIRCUIT_BREAKER = CircuitBreaker(settings, store=_CIRCUIT_STORE)
    return _CIRCUIT_BREAKER


def _retry_policy(settings: RuntimeResilienceSettings) -> RetryPolicy:
    return RetryPolicy(
        max_retries=settings.llm_max_retries,
        base_delay_seconds=settings.llm_retry_base_delay_seconds,
        max_delay_seconds=settings.llm_retry_max_delay_seconds,
    )


def _resolve_model(provider: str, model: Optional[str]) -> tuple[str, str]:
    provider = (provider or "gemini").lower()
    if provider == "local":
        provider = "ollama"
    if provider == "gemini":
        resolved = model or os.getenv("GOOGLE_MODEL", DEFAULT_GEMINI_MODEL)
        if resolved == "gemini-1.5-flash":
            resolved = DEFAULT_GEMINI_MODEL
        return provider, resolved
    if provider == "ollama":
        configured_model = os.getenv("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL)
        resolved = model or configured_model
        if ":" not in resolved:
            resolved = f"{resolved}:latest"
        return provider, resolved
    return provider, model or ""


def _safe_error_text(exc: BaseException) -> str:
    return sanitize_fallback_reason(exc)


async def _call_gemini(
    prompt: str,
    system_prompt: Optional[str],
    model_name: str,
    temperature: float,
    request_timeout: float | None = None,
) -> str:
    """Helper to call Gemini API using the Google GenAI SDK."""
    return await generate_text_async(
        prompt=prompt,
        system_prompt=system_prompt,
        model_name=model_name,
        temperature=temperature,
        request_timeout=request_timeout,
    )

async def _call_gemini_sync(
    prompt: str,
    system_prompt: Optional[str],
    model_name: str,
    temperature: float,
    request_timeout: float | None = None,
) -> str:
    """Helper to call Gemini API synchronously through the Google GenAI SDK."""
    def _generate_sync() -> str:
        return generate_text_sync(
            prompt=prompt,
            system_prompt=system_prompt,
            model_name=model_name,
            temperature=temperature,
            request_timeout=request_timeout,
        )

    if request_timeout and request_timeout > 0:
        async with asyncio.timeout(request_timeout):
            return await asyncio.to_thread(_generate_sync)
    return await asyncio.to_thread(_generate_sync)


async def _call_provider_once(
    *,
    provider: str,
    model: str,
    prompt: str,
    system_prompt: Optional[str],
    temperature: float,
    use_sync: bool,
    request_timeout: float,
) -> str:
    if provider == "gemini":
        logger.info("Calling Gemini (%s)...", model)
        if use_sync:
            return repair_mojibake(
                await _call_gemini_sync(prompt, system_prompt, model, temperature, request_timeout)
            )
        return repair_mojibake(
            await _call_gemini(prompt, system_prompt, model, temperature, request_timeout)
        )

    if provider == "ollama":
        logger.info("Calling Ollama (%s)...", model)
        return repair_mojibake(
            await generate_ollama_response(
                model,
                system_prompt,
                prompt,
                temperature,
                request_timeout=request_timeout,
            )
        )

    raise ValueError(f"Unknown provider: {provider}")


async def _call_provider_resilient(
    *,
    provider: str,
    model: str,
    prompt: str,
    system_prompt: Optional[str],
    temperature: float,
    use_sync: bool,
    budget: DeadlineBudget,
    settings: RuntimeResilienceSettings,
) -> tuple[str, dict]:
    timeout_seconds = (
        settings.gemini_timeout_seconds
        if provider == "gemini"
        else settings.ollama_timeout_seconds
    )

    async def operation(effective_timeout: float) -> str:
        return await _call_provider_once(
            provider=provider,
            model=model,
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            use_sync=use_sync,
            request_timeout=effective_timeout,
        )

    return await call_provider_with_resilience(
        provider_name=provider,
        operation=operation,
        budget=budget,
        timeout_seconds=timeout_seconds,
        retry_policy=_retry_policy(settings),
        circuit_breaker=_refresh_circuit_breaker(settings),
    )

async def generate_llm_response(
    prompt: str,
    system_prompt: Optional[str] = None,
    provider: str = "gemini",
    model: Optional[str] = None,
    temperature: float = 0.2,
    allow_fallback: bool = True,
    use_sync: bool = False,
    budget: DeadlineBudget | None = None,
    resilience_settings: RuntimeResilienceSettings | None = None,
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
    settings = resilience_settings or runtime_resilience_settings_from_env()
    budget = budget or DeadlineBudget.from_timeout(settings.agent_total_timeout_seconds)
    provider, model = _resolve_model(provider or "gemini", model)
    
    result = {
        "text": "",
        "provider": provider,
        "model": model,
        "fallback_used": False,
        "fallback_provider": None,
        "fallback_model": None,
        "error": None,
        "resilience": None,
    }
    
    try:
        # 1. Try primary provider
        text, resilience_meta = await _call_provider_resilient(
            provider=provider,
            model=model,
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            use_sync=use_sync,
            budget=budget,
            settings=settings,
        )
        result["text"] = text
        result["resilience"] = resilience_meta
        return result
            
    except asyncio.CancelledError:
        raise
    except PermanentProviderError as e:
        error_text = _safe_error_text(e)
        logger.warning("Primary LLM (%s/%s) failed permanently: %s", provider, model, error_text)
        result["error"] = error_text
        raise
    except CircuitOpenError as e:
        error_text = _safe_error_text(e)
        logger.warning("Primary LLM circuit is open (%s/%s): %s", provider, model, error_text)
        if not allow_fallback:
            result["error"] = error_text
            raise
        primary_error = e
    except RuntimeResilienceError as e:
        error_text = _safe_error_text(e)
        logger.warning("Primary LLM (%s/%s) failed: %s", provider, model, error_text)
        if not allow_fallback:
            result["error"] = error_text
            raise
        primary_error = e
    except Exception as e:
        error_text = _safe_error_text(e)
        logger.warning("Primary LLM (%s/%s) failed: %s", provider, model, error_text)
        
        # 2. Try Fallback
        if not allow_fallback:
            logger.error("Fallback is disabled. Failing.")
            result["error"] = error_text
            raise e

        primary_error = e

    try:
        logger.info("Attempting fallback...")
        
        if provider == "gemini":
            # Fallback to Ollama
            available_models = await list_ollama_models(timeout_seconds=min(5.0, budget.remaining_seconds()))
            fallback_model = None
            configured_model = os.getenv("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL)
            configured_model = (
                configured_model
                if ":" in configured_model
                else f"{configured_model}:latest"
            )
            if configured_model in available_models:
                fallback_model = configured_model
            elif DEFAULT_OLLAMA_MODEL in available_models:
                fallback_model = DEFAULT_OLLAMA_MODEL
            elif "qwen3:latest" in available_models:
                fallback_model = "qwen3:latest"
            elif "qwen2.5:latest" in available_models:
                fallback_model = "qwen2.5:latest"
                
            if fallback_model:
                try:
                    logger.info("Fallback to Ollama (%s)...", fallback_model)
                    text, resilience_meta = await _call_provider_resilient(
                        provider="ollama",
                        model=fallback_model,
                        prompt=prompt,
                        system_prompt=system_prompt,
                        temperature=temperature,
                        use_sync=use_sync,
                        budget=budget,
                        settings=settings,
                    )
                    result["text"] = text
                    result["resilience"] = resilience_meta
                    result["fallback_used"] = True
                    result["fallback_provider"] = "ollama"
                    result["fallback_model"] = fallback_model
                    return result
                except Exception as fb_err:
                    primary_text = _safe_error_text(primary_error)
                    fallback_text = _safe_error_text(fb_err)
                    logger.error("Fallback Ollama also failed: %s", fallback_text)
                    if isinstance(fb_err, RuntimeResilienceError):
                        raise fb_err
                    result["error"] = f"Primary ({primary_text}) and Fallback ({fallback_text}) both failed."
                    raise Exception(result["error"])
            else:
                logger.error("No suitable Ollama models available for fallback.")
                result["error"] = _safe_error_text(primary_error)
                raise primary_error
                
        elif provider == "ollama":
            # Fallback to Gemini
            fallback_model = os.getenv("GOOGLE_MODEL", DEFAULT_GEMINI_MODEL)
            if fallback_model == "gemini-1.5-flash":
                fallback_model = DEFAULT_GEMINI_MODEL
                
            try:
                logger.info("Fallback to Gemini (%s)...", fallback_model)
                text, resilience_meta = await _call_provider_resilient(
                    provider="gemini",
                    model=fallback_model,
                    prompt=prompt,
                    system_prompt=system_prompt,
                    temperature=temperature,
                    use_sync=use_sync,
                    budget=budget,
                    settings=settings,
                )
                result["text"] = text
                result["resilience"] = resilience_meta
                result["fallback_used"] = True
                result["fallback_provider"] = "gemini"
                result["fallback_model"] = fallback_model
                return result
            except Exception as fb_err:
                primary_text = _safe_error_text(primary_error)
                fallback_text = _safe_error_text(fb_err)
                logger.error("Fallback Gemini also failed: %s", fallback_text)
                if isinstance(fb_err, RuntimeResilienceError):
                    raise fb_err
                result["error"] = f"Primary ({primary_text}) and Fallback ({fallback_text}) both failed."
                raise Exception(result["error"])
    except asyncio.CancelledError:
        raise
    raise primary_error
