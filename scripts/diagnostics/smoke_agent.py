#!/usr/bin/env python3
"""
scripts/diagnostics/smoke_agent.py
=====================

Run::

    python scripts/diagnostics/smoke_agent.py "Tôi bị mụn viêm đỏ ở má, có nên dùng benzoyl peroxide không?"

Tests the basic LangGraph workflow for Phase 2.
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

# Bootstrap paths
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env", override=False)
except ImportError:
    pass

logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(name)s - %(message)s")


async def main():
    if len(sys.argv) > 1:
        question = " ".join(sys.argv[1:])
    else:
        question = "Tôi bị mụn viêm đỏ ở má, có nên dùng benzoyl peroxide không?"
        
    print("="*70)
    print(f"🤔 QUESTION: {question}")
    print("="*70)
    
    from src.agent.main import run_clinical_agent
    
    # Run the graph
    print("⏳ Running agent workflow...")
    result = await run_clinical_agent(message=question)
    
    print("\n✅ WORKFLOW COMPLETED!")
    print("="*70)
    print("📋 EXTRACTED SYMPTOMS:")
    print(f"  {result.get('symptoms', [])}")
    
    print("\n🚨 SAFETY FLAGS:")
    flags = result.get("safety_flags", [])
    if flags:
        for f in flags:
            print(f"  - {f}")
    else:
        print("  None")
        
    print("\n🔗 TOP GRAPH FACTS (Extracted from Retrieval):")
    facts = result.get("graph_facts", [])
    if facts:
        for i, fact in enumerate(facts[:5], 1):
            entity = fact.get("entity", "")
            etype = fact.get("entity_type", "")
            rel = fact.get("relationship", "")
            related = fact.get("related_entity", "")
            rtype = fact.get("related_type", "")
            
            if rel and related:
                print(f"  {i}. ({etype}:{entity}) -[{rel}]-> ({rtype}:{related})")
            else:
                desc = fact.get("description", "")
                if desc:
                    print(f"  {i}. ({etype}:{entity}) - {desc[:60]}...")
    else:
        print("  None")
        
    print("\n📚 SOURCES:")
    sources = result.get("sources", [])
    if sources:
        for s in sources:
            print(f"  - {s}")
    else:
        print("  None")
        
    print("\n🤖 FINAL ANSWER:")
    print(result.get("answer", ""))
    print("="*70)
    
    errors = result.get("errors", [])
    if errors:
        print(f"\n❌ ERRORS: {errors}")


if __name__ == "__main__":
    asyncio.run(main())
