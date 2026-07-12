"""
scripts/diagnostics/smoke_redis_cache.py
===========================
Tests the Redis Semantic Answer Cache.
"""

import httpx
import time
import sys

API_URL = "http://127.0.0.1:8000"
OLLAMA_MODEL = "qwen3:8b"

def test_redis_cache():
    print("--- Testing Redis Semantic Cache ---")
    
    # 1. Health check
    try:
        health = httpx.get(f"{API_URL}/health").json()
        print(f"Health: {health}")
        if health.get("redis") != "ok":
            print("Redis is not available! Skipping cache tests.")
            return
    except Exception as e:
        print(f"Could not connect to API: {e}")
        return

    import random
    unique_id = random.randint(1000, 9999)
    question = f"Tác dụng phụ của benzoyl peroxide là gì? (Test {unique_id})"
    
    # 2. First request -> Cache Miss
    print("\n--- 1. First Request (Expected Miss) ---")
    payload1 = {
        "message": question,
        "llm_provider": "ollama",
        "llm_model": OLLAMA_MODEL,
        "allow_model_fallback": False
    }
    
    t0 = time.time()
    res1 = httpx.post(f"{API_URL}/chat", json=payload1, timeout=60).json()
    t1 = time.time()
    
    meta1 = res1.get("metadata", {})
    cache_meta1 = meta1.get("cache", {})
    
    print(f"Answer: {res1.get('answer', '')[:100]}...")
    print(f"Cache Checked: {cache_meta1.get('checked')}")
    print(f"Cache Hit: {cache_meta1.get('hit')} (Reason: {cache_meta1.get('reason')})")
    print(f"Time taken: {t1 - t0:.2f}s")
    
    if cache_meta1.get("hit"):
        print("FAIL: Expected miss but got hit!")
    else:
        print("PASS: Cache Miss.")

    # 3. Second request -> Cache Hit
    print("\n--- 2. Second Request (Expected Hit) ---")
    
    t0 = time.time()
    res2 = httpx.post(f"{API_URL}/chat", json=payload1, timeout=60).json()
    t1 = time.time()
    
    meta2 = res2.get("metadata", {})
    cache_meta2 = meta2.get("cache", {})
    
    print(f"Answer: {res2.get('answer', '')[:100]}...")
    print(f"Cache Checked: {cache_meta2.get('checked')}")
    print(f"Cache Hit: {cache_meta2.get('hit')} (Reason: {cache_meta2.get('reason')})")
    print(f"Cached Provider: {meta2.get('cached_from_provider')} | Cached Model: {meta2.get('cached_from_model')}")
    print(f"Time taken: {t1 - t0:.2f}s")
    
    if cache_meta2.get("hit") and cache_meta2.get("quality_passed"):
        print(f"PASS: Cache Hit with quality_passed=true, answer_version={cache_meta2.get('answer_version')}")
    elif cache_meta2.get("hit"):
        print(f"FAIL: Cache Hit but missing quality_passed metadata! cache_meta={cache_meta2}")
    else:
        print(f"FAIL: Expected hit but got miss! reason={cache_meta2.get('reason')}")

    # 4. Personal question -> Skip Cache
    print("\n--- 3. Personal Question (Expected Skip) ---")
    payload_personal = {
        "message": "Tôi đang mang thai và bị mụn viêm, có dùng benzoyl peroxide được không?",
        "llm_provider": "ollama",
        "llm_model": OLLAMA_MODEL,
        "session_id": str(unique_id)
    }
    res3 = httpx.post(f"{API_URL}/chat", json=payload_personal, timeout=60).json()
    cache_meta3 = res3.get("metadata", {}).get("cache", {})
    print(f"Answer: {res3.get('answer', '')[:100]}...")
    print(f"Cache Hit: {cache_meta3.get('hit')} (Reason: {cache_meta3.get('reason')})")
    if cache_meta3.get("hit") == False and cache_meta3.get("reason") == "contains_personal_context":
        print("PASS: Personal context skipped.")
    else:
        print("FAIL: Did not skip personal context properly.")

    # 5. Out of domain -> Skip Cache
    print("\n--- 4. Out of Domain Question (Expected Skip) ---")
    payload_ood = {
        "message": "Thời tiết hôm nay thế nào?",
        "llm_provider": "ollama",
        "llm_model": OLLAMA_MODEL,
        "session_id": str(unique_id)
    }
    res4 = httpx.post(f"{API_URL}/chat", json=payload_ood, timeout=60).json()
    cache_meta4 = res4.get("metadata", {}).get("cache", {})
    print(f"Answer: {res4.get('answer', '')[:100]}...")
    print(f"Cache Hit: {cache_meta4.get('hit')} (Reason: {cache_meta4.get('reason')})")
    if cache_meta4.get("hit") == False and cache_meta4.get("reason") in ["out_of_domain", "skipped"]:
        print("PASS: Out of domain skipped.")
    else:
        print("FAIL: Did not skip OOD properly.")

    # 6. Short Answer -> Skip Cache
    print("\n--- 5. Short Answer Quality Gate (Expected Miss -> No Cache Store) ---")
    payload_short = {
        "message": "Chỉ trả lời đúng 1 chữ: Có",
        "llm_provider": "ollama",
        "llm_model": OLLAMA_MODEL,
        "session_id": str(unique_id)
    }
    httpx.post(f"{API_URL}/chat", json=payload_short, timeout=60)
    
    # Try again, should miss because it shouldn't have been stored
    res6 = httpx.post(f"{API_URL}/chat", json=payload_short, timeout=60).json()
    cache_meta6 = res6.get("metadata", {}).get("cache", {})
    print(f"Answer: {res6.get('answer', '')[:100]}...")
    print(f"Cache Hit: {cache_meta6.get('hit')} (Reason: {cache_meta6.get('reason')})")
    if cache_meta6.get("hit") == False:
        print("PASS: Short answer not cached.")
    else:
        print("FAIL: Short answer was incorrectly cached.")

    print("\nAll caching tests completed.")

if __name__ == "__main__":
    test_redis_cache()
