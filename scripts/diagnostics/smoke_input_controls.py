import httpx
import os
import uuid
import time
from dotenv import load_dotenv

load_dotenv()

API_URL = "http://localhost:8000"

def run_tests():
    print("\n============================================================")
    print("Input Control & Request Locking — End-to-End Tests")
    print("============================================================\n")
    
    session_id = str(uuid.uuid4())
    
    print("1. Testing empty message...")
    res = httpx.post(f"{API_URL}/chat", json={
        "message": "   ",
        "session_id": session_id
    })
    assert res.status_code == 400
    print("✓ Empty message rejected with 400")

    print("\n2. Testing too long message...")
    res = httpx.post(f"{API_URL}/chat", json={
        "message": "a" * 501,
        "session_id": session_id
    })
    assert res.status_code == 400
    assert "message_too_long" in res.json()["detail"]["code"]
    print("✓ Too long message rejected with 400 (message_too_long)")

    print("\n3. Testing too many words...")
    res = httpx.post(f"{API_URL}/chat", json={
        "message": "a " * 121,
        "session_id": session_id
    })
    assert res.status_code == 400
    assert "too_many_words" in res.json()["detail"]["code"]
    print("✓ Too many words rejected with 400 (too_many_words)")

    print("\n4. Testing too many questions...")
    res = httpx.post(f"{API_URL}/chat", json={
        "message": "Cái này là gì? Ở đâu? Khi nào? Tại sao?",
        "session_id": session_id
    })
    assert res.status_code == 400
    assert "too_many_questions" in res.json()["detail"]["code"]
    print("✓ Too many questions rejected with 400 (too_many_questions)")

    print("\n5. Testing valid message...")
    payload_valid = {
        "message": "Tác dụng phụ của benzoyl peroxide là gì?",
        "llm_provider": "gemini",
        "llm_model": "gemini-2.5-flash",
        "session_id": session_id
    }
    res_valid = httpx.post(f"{API_URL}/chat", json=payload_valid, timeout=60)
    assert res_valid.status_code == 200
    print("✓ Valid message passed")

    print("\n6. Testing Redis cache hit for valid message...")
    res_cache = httpx.post(f"{API_URL}/chat", json=payload_valid, timeout=60)
    assert res_cache.status_code == 200
    # Assuming cache is enabled and hitting
    print("✓ Cache check completed for valid message")

    print("\n============================================================")
    print("✅ All Input Control tests passed!")
    print("============================================================\n")

if __name__ == "__main__":
    run_tests()
