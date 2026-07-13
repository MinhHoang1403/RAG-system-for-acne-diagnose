import asyncio
import os
import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
from dotenv import load_dotenv
load_dotenv()
from src.api.app import _persist_chat_to_db


def _diagnostic_writes_enabled() -> bool:
    return os.getenv("ALLOW_DIAGNOSTIC_WRITES", "").strip().lower() in {"1", "true", "yes"}


async def test():
    if not _diagnostic_writes_enabled():
        print("Skipping manual chat persistence. Set ALLOW_DIAGNOSTIC_WRITES=true to enable it.")
        return
    try:
        await _persist_chat_to_db(
            session_id='test-123',
            user_id=None,
            user_message='Hello',
            assistant_answer='Hi',
            sources=['a'],
            symptoms=['b'],
            safety_flags=['c'],
            graph_facts=[{'entity': 'X', 'relationship': 'Y', 'related_entity': 'Z'}],
            db_metadata={'model': 'test'}
        )
        print('SUCCESS')
    except Exception as e:
        print('ERROR:', e)
        import traceback
        traceback.print_exc()

asyncio.run(test())
