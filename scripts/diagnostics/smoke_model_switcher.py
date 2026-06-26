"""
scripts/diagnostics/smoke_model_switcher.py
==============================
Test the Model Switcher logic.
"""

import httpx
import asyncio

async def test_models_endpoint():
    print("Testing GET /models...")
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            resp = await client.get("http://127.0.0.1:8000/models")
            resp.raise_for_status()
            data = resp.json()
            models = data.get("models", [])
            print(f"Got {len(models)} models.")
            for m in models:
                print(f"- {m['provider']}/{m['model']} (Available: {m['available']})")
            
            return {f"{m['provider']}/{m['model']}": m['available'] for m in models}
        except Exception as e:
            print(f"GET /models failed: {e}")
            return {}

async def test_chat_endpoint(provider, model, fallback, query, conversation_history=None):
    print(f"\nTesting POST /chat with {provider}/{model} (fallback={fallback})...")
    print(f"Query: {query}")
    payload = {
        "message": query,
        "llm_provider": provider,
        "llm_model": model,
        "allow_model_fallback": fallback,
        "bypass_cache": True
    }
    if conversation_history:
        payload["conversation_history"] = conversation_history
        
    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            resp = await client.post("http://127.0.0.1:8000/chat", json=payload)
            resp.raise_for_status()
            data = resp.json()
            meta = data.get("metadata", {})
            cache_meta = meta.get("cache", {})
            print("Answer:", data.get("answer")[:200].replace('\n', ' '), "...")
            print(f"Metadata -> Provider: {meta.get('provider')}, Model: {meta.get('model')}")
            print(f"Fallback Used: {meta.get('fallback_used')}, Fallback Provider: {meta.get('fallback_provider')}")
            print(f"Bypass Cache: {cache_meta.get('reason') == 'bypassed'}, Cache Hit: {cache_meta.get('hit')}, Cache Reason: {cache_meta.get('reason')}")
            if meta.get('guardrail'):
                print(f"Guardrail: {meta.get('guardrail')}")
            return data
        except Exception as e:
            print(f"POST /chat failed: {e}")
            return None

async def main():
    print("Starting tests...")
    
    try:
        async with httpx.AsyncClient() as client:
            await client.get("http://127.0.0.1:8000/health")
    except Exception:
        print("Backend is not running at http://127.0.0.1:8000. Please start the server first.")
        return
        
    availability = await test_models_endpoint()
    
    base_query = "Tôi bị mụn viêm đỏ ở má, có nên dùng benzoyl peroxide không?"
    
    # 2. Test Gemini
    resp1 = await test_chat_endpoint("gemini", "gemini-2.5-flash", False, query=base_query)
    
    # 3. Test Qwen2.5
    if availability.get("ollama/qwen2.5:latest"):
        await test_chat_endpoint("ollama", "qwen2.5:latest", False, query=base_query)
    else:
        print("\nSkipping Qwen2.5 test because it's marked unavailable in /models.")

    # 4. Test Qwen3
    if availability.get("ollama/qwen3:latest"):
        await test_chat_endpoint("ollama", "qwen3:latest", False, query=base_query)
    else:
        print("\nSkipping Qwen3 test because it's marked unavailable in /models.")
        
    # 5. Test Guardrail
    await test_chat_endpoint("gemini", "gemini-2.5-flash", False, query="Thời tiết hôm nay thế nào?")
    
    # 6. Test Multi-turn
    print("\n--- Testing Multi-turn ---")
    if resp1:
        history = [
            {"role": "user", "content": base_query},
            {"role": "assistant", "content": resp1.get("answer", "")}
        ]
        await test_chat_endpoint("gemini", "gemini-2.5-flash", False, query="Vậy loại đó có tác dụng phụ gì?", conversation_history=history)
    else:
        print("Skipping Multi-turn test because the first Gemini call failed.")

    print("\nTests complete.")

if __name__ == "__main__":
    asyncio.run(main())
