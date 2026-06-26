import asyncio
import os
import sys
from dotenv import load_dotenv

load_dotenv()

# Thêm thư mục gốc vào sys.path để import
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.agent.graph import run_clinical_agent

async def run_test(name, message):
    print(f"\n=== Test: {name} ===")
    print(f"User: {message}")
    result = await run_clinical_agent(message=message)
    
    print("Is in domain:", result.get("is_in_domain"))
    print("Guardrail status:", result.get("guardrail"))
    print("Standalone question:", result.get("standalone_question"))
    print("Answer:", result.get("answer"))

async def main():
    await run_test("A. Out-of-domain 1", "Thời tiết hôm nay thế nào?")
    await asyncio.sleep(4)
    await run_test("B. Out-of-domain 2", "Tôi tên gì?")
    await asyncio.sleep(4)
    await run_test("C. Mụn đầu đen", "Tôi bị mụn đầu đen thì nên chăm sóc như thế nào?")
    await asyncio.sleep(4)
    
    print("\n=== Test: D. Multi-turn ===")
    print("User 1: Tôi bị mụn viêm đỏ ở má, có nên dùng benzoyl peroxide không?")
    r1 = await run_clinical_agent(message="Tôi bị mụn viêm đỏ ở má, có nên dùng benzoyl peroxide không?")
    print("Answer 1:", r1.get("answer"))
    await asyncio.sleep(4)
    
    history = [{"role": "user", "content": "Tôi bị mụn viêm đỏ ở má, có nên dùng benzoyl peroxide không?"},
               {"role": "assistant", "content": r1.get("answer", "")}]
    
    print("User 2: Vậy loại đó có tác dụng phụ gì?")
    r2 = await run_clinical_agent(message="Vậy loại đó có tác dụng phụ gì?", conversation_history=history)
    print("Standalone question 2:", r2.get("standalone_question"))
    print("Answer 2:", r2.get("answer"))

if __name__ == "__main__":
    asyncio.run(main())
