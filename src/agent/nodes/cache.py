"""
src/agent/nodes/cache.py
========================
LangGraph nodes for Exact Normalized Answer Caching.
"""

import logging
from typing import Any

from src.agent.state import ClinicalState
from src.cache.semantic_cache import (
    normalize_question,
    is_cacheable_question,
    infer_cache_intent,
    get_exact_cache,
    set_answer_cache
)

logger = logging.getLogger(__name__)

async def cache_lookup_node(state: ClinicalState) -> dict[str, Any]:
    """
    Checks if the question has a cached answer.
    Must run AFTER rewrite_question and domain_guard.
    """
    logger.info("Executing cache_lookup_node...")
    
    # Decide which question string to use for cache key
    # Use standalone_question ONLY for multi-turn follow-ups with vague references
    # Use user_question for clear, direct questions to ensure cache key consistency
    user_question = state.get("user_question", "")
    standalone_question = state.get("standalone_question")
    history = state.get("conversation_history", [])
    
    # Detect if the question is a vague follow-up (uses pronouns/references)
    vague_markers = ["loại đó", "nó ", "cái đó", "hoạt chất đó", "thuốc đó", "sản phẩm đó", "vậy ", "thì sao"]
    is_vague_followup = (
        history 
        and len(history) > 0
        and any(marker in user_question.lower() for marker in vague_markers)
    )
    
    if is_vague_followup and standalone_question and standalone_question.strip():
        target_question = standalone_question
        cache_key_source = "standalone_question"
    else:
        target_question = user_question
        cache_key_source = "user_question"
    
    logger.info(f"Cache key source: {cache_key_source} -> '{target_question[:80]}...'")
    normalized = normalize_question(target_question)
    guard_status = "in_domain" if state.get("is_in_domain") else "out_of_domain"
    intent = infer_cache_intent(target_question, guard_status)
    
    # Check if we should bypass cache completely
    if state.get("bypass_cache"):
        logger.info("Cache BYPASSED due to request flag.")
        return {
            "cache_checked": False,
            "cache_hit": False,
            "cache_reason": "bypassed",
            "normalized_question": normalized,
            "cache_intent": intent,
        }

    if history:
        logger.info("Cache SKIPPED: conversation history present.")
        return {
            "cache_checked": True,
            "cache_hit": False,
            "cache_reason": "history_present",
            "normalized_question": normalized,
            "cache_intent": intent,
        }
        
    # Check if cacheable
    history = state.get("conversation_history", [])
    
    is_cacheable, reason = is_cacheable_question(target_question, history, guard_status)
    
    if not is_cacheable:
        logger.info(f"Question not cacheable. Reason: {reason}")
        return {
            "cache_checked": True,
            "cache_hit": False,
            "cache_reason": reason,
            "normalized_question": normalized,
            "cache_intent": intent,
        }
        
    # Attempt to retrieve from Redis
    cached_data = await get_exact_cache(
        normalized,
        intent=intent,
        provider=state.get("llm_provider") or "gemini",
        model=state.get("llm_model") or "unknown",
    )
    
    if cached_data:
        import os
        meta = cached_data.get("metadata", {})
        expected_version = os.getenv("CACHE_ANSWER_VERSION", "v2")
        
        if not meta.get("quality_passed") or meta.get("answer_version") != expected_version:
            logger.info("Cache entry invalid or missing quality metadata. Treating as MISS.")
            return {
                "cache_checked": True,
                "cache_hit": False,
                "cache_reason": "invalid_cache_metadata",
                "normalized_question": normalized,
                "cache_intent": intent,
            }
            
        logger.info("Cache HIT with valid quality metadata!")
        
        # We need to construct metadata properly
        
        # Let's populate the state
        return {
            "cache_checked": True,
            "cache_hit": True,
            "cache_reason": "hit",
            "cache_intent": intent,
            "cached_answer": cached_data.get("answer", ""),
            "cached_sources": cached_data.get("sources", []),
            "cache_metadata": cached_data.get("metadata", {}),
            "normalized_question": normalized,
            
            # Since it's a hit, we bypass LLM generation
            "final_answer": cached_data.get("answer", ""),
            "sources": cached_data.get("sources", []),
            "actual_provider": "cache",
            "actual_model": cached_data.get("model_name", "unknown")
        }
    else:
        logger.info("Cache MISS!")
        return {
            "cache_checked": True,
            "cache_hit": False,
            "cache_reason": "miss",
            "normalized_question": normalized,
            "cache_intent": intent,
        }


async def cache_store_node(state: ClinicalState) -> dict[str, Any]:
    """
    Stores the generated answer into the cache.
    Must run AFTER generate_answer_node.
    """
    logger.info("Executing cache_store_node...")
    
    # Only store if cache was missed and we generated a valid answer
    if state.get("cache_hit"):
        logger.info("Cache store SKIPPED: cache_hit is True")
        return {}
    
    # Skip cache store if bypass requested
    if state.get("bypass_cache"):
        logger.info("Cache store BYPASSED due to request flag.")
        return {}

    if state.get("conversation_history"):
        logger.info("Cache store SKIPPED: conversation history present.")
        return {}
        
    # Check if it was deemed cacheable in the lookup phase
    if state.get("cache_reason") not in ["miss", None]:
        logger.info(f"Cache store SKIPPED: cache_reason={state.get('cache_reason')}")
        return {}
        
    if not state.get("is_in_domain"):
        logger.info("Cache store SKIPPED: not in domain")
        return {}

    if state.get("use_history_context"):
        logger.info("Cache store SKIPPED: history context enabled")
        return {}

    if any(
        marker in (state.get("user_question") or "").lower()
        for marker in [
            "giả vờ bạn là bác sĩ",
            "giả vờ là bác sĩ",
            "pretend you are a doctor",
            "kê đơn",
            "kê thuốc",
            "toa thuốc",
        ]
    ):
        logger.info("Cache store SKIPPED: unsafe prompt/prescription request")
        return {}
        
    if state.get("errors") or state.get("llm_fallback"):
        logger.info(f"Cache store SKIPPED: errors={state.get('errors')}, llm_fallback={state.get('llm_fallback')}")
        return {}
        
    # Use final_answer (post-processed by finalize_response_node) instead of draft_answer
    answer = state.get("final_answer", "")
    sources = state.get("sources", [])
    
    # --- QUALITY GATE ---
    if not answer:
        logger.info("Quality Gate Failed: Empty answer")
        return {}
        
    import os
    min_chars = int(os.getenv("CACHE_MIN_ANSWER_CHARS", "350"))
    if len(answer) < min_chars:
        logger.info(f"Quality Gate Failed: Answer too short ({len(answer)} < {min_chars})")
        return {}
        
    answer_lower = answer.lower()
    
    if state.get("llm_fallback") or state.get("llm_fallback_used"):
        logger.info(f"Quality Gate Failed: Answer is a fallback (llm_fallback={state.get('llm_fallback')}, llm_fallback_used={state.get('llm_fallback_used')})")
        return {}
        
    if state.get("fallback_provider") == "rule_based" or state.get("guardrail") == "in_domain_fallback":
        logger.info(f"Quality Gate Failed: rule_based/in_domain_fallback (fallback_provider={state.get('fallback_provider')}, guardrail={state.get('guardrail')})")
        return {}
        
    generic_phrases = [
        "dựa trên các thông tin bạn cung cấp, đây là những lưu ý chăm sóc da cơ bản",
        "giữ vệ sinh da sạch sẽ",
        "sử dụng kem dưỡng ẩm phù hợp"
    ]
    has_generic = any(phrase in answer_lower for phrase in generic_phrases)
    if has_generic and state.get("actual_provider") != "cache":
        # Check if the fallback answer actually mentions the key entities from the question
        target_question = state.get("standalone_question")
        if not target_question or not target_question.strip():
            target_question = state.get("user_question", "")
        question_lower = target_question.lower()
        key_entities = ["benzoyl peroxide", "retinoid", "adapalene", "clindamycin", "isotretinoin"]
        mentioned_entities = [entity for entity in key_entities if entity in question_lower]
        if mentioned_entities:
            # If the question had entities but the answer uses generic fallback without addressing them, do not cache
            if not any(entity in answer_lower for entity in mentioned_entities):
                logger.info("Quality Gate Failed: Answer is generic and misses key entities.")
                return {}
                
    # Check if answer contains entities from the question if required
    require_entity_check = os.getenv("CACHE_REQUIRED_ENTITY_CHECK", "true").lower() == "true"
    if require_entity_check:
        key_entities = ["benzoyl peroxide", "retinoid", "adapalene", "clindamycin", "isotretinoin"]
        target_question = state.get("standalone_question")
        if not target_question or not target_question.strip():
            target_question = state.get("user_question", "")
        question_lower = target_question.lower()
        
        for entity in key_entities:
            if entity in question_lower and entity not in answer_lower:
                logger.info(f"Quality Gate Failed: Missing required entity '{entity}' in answer.")
                return {}
                
    # Check if sources are empty but in-domain
    if not sources and state.get("is_in_domain"):
        logger.info(f"Quality Gate Failed: No sources for in-domain question. sources={sources}")
        return {}
    
    # Check for residual dosage/frequency patterns that shouldn't be cached
    import re
    user_question = (state.get("user_question") or "").lower()
    dosage_query_keywords = ["cách dùng", "dùng thế nào", "tần suất", "bôi mấy lần", "liều", "bao lâu", "mấy lần", "dùng sao"]
    user_asked_dosage = any(kw in user_question for kw in dosage_query_keywords)
    
    if not user_asked_dosage:
        unsafe_dosage_patterns = [
            r"\d+-\d+ lần/tuần",
            r"\d+ lần/ngày",
            r"bôi sau khi dưỡng ẩm",
            r"dùng kem dưỡng ẩm trước khi bôi",
        ]
        for pat in unsafe_dosage_patterns:
            if re.search(pat, answer_lower):
                logger.info(f"Quality Gate Failed: Answer contains dosage pattern '{pat}' but user didn't ask about dosage.")
                return {}
    # --- END QUALITY GATE ---
    
    # Use same cache key logic as cache_lookup_node
    raw_question = state.get("user_question", "")
    standalone_q = state.get("standalone_question")
    store_history = state.get("conversation_history", [])
    
    vague_markers = ["loại đó", "nó ", "cái đó", "hoạt chất đó", "thuốc đó", "sản phẩm đó", "vậy ", "thì sao"]
    is_vague_followup = (
        store_history 
        and len(store_history) > 0
        and any(marker in raw_question.lower() for marker in vague_markers)
    )
    
    if is_vague_followup and standalone_q and standalone_q.strip():
        target_question = standalone_q
    else:
        target_question = raw_question
        
    normalized = normalize_question(target_question)
    guard_status = "in_domain" if state.get("is_in_domain") else "out_of_domain"
    intent = infer_cache_intent(target_question, guard_status)
    
    # Build metadata to store
    metadata = {
        "provider": state.get("actual_provider"),
        "model": state.get("actual_model"),
        "retrieval": "hybrid_qdrant_neo4j" if state.get("sources") else "skipped",
        "quality_checked": True,
        "quality_passed": True,
        "quality_reason": "passed_all_gates",
        "answer_version": os.getenv("CACHE_ANSWER_VERSION", "v2"),
        "raw_question": raw_question,
        "standalone_question": standalone_q or "",
        "cache_key_question": target_question,
        "normalized_question": normalized,
        "cache_intent": intent,
    }
    
    # Store it
    logger.info(f"Storing cache: key_source={'standalone' if is_vague_followup else 'user'}, normalized='{normalized[:60]}...'")
    await set_answer_cache(
        normalized_question=normalized,
        standalone_question=target_question,
        answer=answer,
        sources=sources,
        metadata=metadata,
        intent=intent,
        provider=state.get("actual_provider") or state.get("llm_provider") or "gemini",
        model=state.get("actual_model") or state.get("llm_model") or "unknown",
    )
    
    return {}
