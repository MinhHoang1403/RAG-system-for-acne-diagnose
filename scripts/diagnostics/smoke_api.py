#!/usr/bin/env python3
"""
scripts/diagnostics/smoke_api.py
===================
Tests the FastAPI endpoints.

Make sure the server is running on port 8000 before executing this script.
"""

import httpx
import json
import sys

API_URL = "http://127.0.0.1:8000"

def test_health():
    print(f"Testing GET {API_URL}/health")
    try:
        response = httpx.get(f"{API_URL}/health", timeout=5.0)
        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        assert response.status_code == 200
        print("✅ Health check passed!\n")
    except Exception as e:
        print(f"❌ Health check failed: {e}\n")
        sys.exit(1)


def test_chat():
    print(f"Testing POST {API_URL}/chat")
    payload = {
        "message": "Tôi bị mụn viêm đỏ ở má, có nên dùng benzoyl peroxide không?"
    }
    print(f"Payload: {json.dumps(payload, indent=2)}")
    
    try:
        # Increase timeout for LLM generation
        response = httpx.post(
            f"{API_URL}/chat", 
            json=payload, 
            timeout=60.0
        )
        print(f"Status: {response.status_code}")
        if response.status_code != 200:
            print(f"Error Response: {response.text}")
            sys.exit(1)
            
        data = response.json()
        
        print("\n✅ Chat request successful!")
        print("="*60)
        print(f"🤔 EXTRACTED SYMPTOMS: {data.get('symptoms')}")
        print(f"🚨 SAFETY FLAGS: {data.get('safety_flags')}")
        print(f"📚 SOURCES: {data.get('sources')}")
        print(f"⚙️ METADATA: {data.get('metadata')}")
        print(f"🔗 GRAPH FACTS COUNT: {len(data.get('graph_facts', []))}")
        print("\n🤖 ANSWER:")
        print(data.get('answer'))
        print("="*60)
        
    except Exception as e:
        print(f"❌ Chat check failed: {e}\n")
        sys.exit(1)

if __name__ == "__main__":
    test_health()
    test_chat()
