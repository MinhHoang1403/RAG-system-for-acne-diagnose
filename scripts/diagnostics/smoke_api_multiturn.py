import asyncio
import httpx

async def main():
    api_url = "http://127.0.0.1:8000/chat"
    
    print("=== API Test 1: First question ===")
    payload1 = {
        "message": "Tôi bị mụn viêm đỏ ở má, có nên dùng benzoyl peroxide không?"
    }
    
    async with httpx.AsyncClient() as client:
        resp1 = await client.post(api_url, json=payload1, timeout=60.0)
        data1 = resp1.json()
        print(f"Status: {resp1.status_code}")
        answer1 = data1.get("answer", "")
        print(f"Answer 1: {answer1[:200]}...")
        
        print("\n\n=== API Test 2: Follow-up ===")
        payload2 = {
            "message": "Vậy loại đó có tác dụng phụ gì?",
            "conversation_history": [
                {"role": "user", "content": payload1["message"]},
                {"role": "assistant", "content": answer1}
            ]
        }
        
        resp2 = await client.post(api_url, json=payload2, timeout=60.0)
        data2 = resp2.json()
        print(f"Status: {resp2.status_code}")
        print(f"Answer 2:\n{data2.get('answer')}")

if __name__ == "__main__":
    asyncio.run(main())
