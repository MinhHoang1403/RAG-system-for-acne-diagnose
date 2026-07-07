"""
src/agent/nodes/retrieve.py
===========================
LangGraph nodes for processing input and retrieving context.
"""

import logging

import os
from src.agent.llm.provider import generate_llm_response
from src.agent.state import ClinicalState
from src.database.retriever import HybridRetriever

logger = logging.getLogger(__name__)


async def normalize_question_node(state: ClinicalState) -> dict:
    """Normalize the user's question (e.g., lowercasing, stripping)."""
    question = state.get("user_question", "").strip()
    logger.debug(f"Normalizing question: {question}")
    
    # Simple normalization for Phase 2 (can be upgraded to LLM rewriting later)
    normalized = question.lower()
    
    return {"normalized_question": normalized}


async def rewrite_question_node(state: ClinicalState) -> dict:
    """Rewrite question based on conversation history for multi-turn context."""
    normalized = state.get("normalized_question", "")
    history = state.get("conversation_history", [])
    
    if not history:
        return {
            "standalone_question": normalized,
            "use_history_context": False,
        }

    explicit_primary_entities = [
        "benzoyl peroxide",
        "bp",
        "adapalene",
        "adapalen",
        "clindamycin",
        "erythromycin",
        "isotretinoin",
        "retinoid",
        "tretinoin",
        "tazarotene",
        "trifarotene",
    ]
    if any(entity in normalized for entity in explicit_primary_entities):
        return {
            "standalone_question": normalized,
            "use_history_context": False,
        }
        
    ambiguous_keywords = [
        "nó", "loại đó", "cái đó", "thuốc đó", "vậy còn", "như trên", "còn cái này", "vậy",
        "nhắc lại", "tình trạng da", "tuổi của tôi", "bắt đầu chăm sóc", "chăm sóc như thế nào",
        "có cần", "kháng sinh không", "uống kháng sinh", "routine",
    ]
    needs_rewrite = any(kw in normalized for kw in ambiguous_keywords)
    
    if not needs_rewrite:
        return {
            "standalone_question": normalized,
            "use_history_context": any(
                kw in normalized for kw in [
                    "vậy", "nhắc lại", "tình trạng da", "tuổi của tôi", "bắt đầu chăm sóc",
                    "chăm sóc như thế nào", "có cần", "kháng sinh không", "uống kháng sinh",
                    "routine",
                ]
            ),
        }
        
    logger.info("Question contains ambiguous keywords, attempting rewrite based on history.")
    
    # Format history for prompt
    history_text = "\n".join([f"{msg['role'].capitalize()}: {msg['content']}" for msg in history])
    prompt = f"""
Dựa vào lịch sử hội thoại dưới đây, hãy viết lại câu hỏi cuối cùng của người dùng thành một câu hỏi độc lập (standalone question) đầy đủ ngữ cảnh.
Chỉ trả về câu hỏi đã được viết lại, không thêm bất kỳ thông tin nào khác, không trả lời câu hỏi. Giữ nguyên ngôn ngữ tiếng Việt.

Lịch sử hội thoại:
{history_text}

Câu hỏi hiện tại của người dùng:
User: {state.get('user_question', '')}

Câu hỏi độc lập:
"""
    try:
        llm_provider = state.get("llm_provider", "gemini")
        llm_model = state.get("llm_model")
        allow_model_fallback = state.get("allow_model_fallback", True)
        
        response_data = await generate_llm_response(
            prompt=prompt,
            provider=llm_provider,
            model=llm_model,
            temperature=0.0,
            allow_fallback=allow_model_fallback,
            use_sync=False
        )
        
        rewritten = response_data["text"].strip()
        logger.info(f"Rewrote question to: {rewritten}")
        return {
            "standalone_question": rewritten,
            "use_history_context": True,
        }
    except Exception as e:
        logger.error(f"Failed to rewrite question, using original. Error: {e}")
        return {
            "standalone_question": normalized,
            "use_history_context": True,
        }


async def extract_symptoms_node(state: ClinicalState) -> dict:
    """Extract symptoms and patient profile from the question."""
    question = state.get("standalone_question") or state.get("normalized_question", "")
    question = question.lower()
    
    # Phase 2 basic rule-based extraction (can be upgraded to LLM extraction)
    symptoms = []
    if "mụn viêm" in question or "sẩn viêm" in question:
        symptoms.append("mụn viêm")
    if "đỏ" in question:
        symptoms.append("đỏ")
    if "má" in question:
        symptoms.append("má")
    if "mụn mủ" in question:
        symptoms.append("mụn mủ")
    if "sẹo" in question:
        symptoms.append("sẹo")
        
    logger.debug(f"Extracted symptoms: {symptoms}")
    
    # Empty patient profile for now
    patient_profile = {}
    
    return {
        "symptoms": symptoms,
        "patient_profile": patient_profile
    }


async def retrieve_context_node(state: ClinicalState) -> dict:
    """Retrieve context using the HybridRetriever."""
    query = state.get("standalone_question") or state.get("normalized_question", "")
    
    if not query:
        return {
            "vector_contexts": [],
            "graph_facts": [],
            "sources": [],
            "errors": state.get("errors", []) + ["Empty query for retrieval."]
        }
        
    logger.info(f"Retrieving context for query: {query}")
    
    retriever = HybridRetriever()
    try:
        result = await retriever.retrieve(query, top_k=5)
        return {
            "vector_contexts": result.vector_contexts,
            "graph_facts": result.graph_facts,
            "sources": result.sources,
            "retrieval_trace": result.metadata.get("retrieval_trace"),
        }
    except Exception as e:
        logger.error(f"Retrieval error: {e}")
        return {
            "errors": state.get("errors", []) + [f"Retrieval failed: {str(e)}"]
        }
    finally:
        await retriever.close()
