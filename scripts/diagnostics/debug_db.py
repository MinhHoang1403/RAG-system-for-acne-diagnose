import asyncio
import os
import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

async def main():
    url = os.getenv("DATABASE_URL")
    print(f"DB URL: {url}")
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        r = await conn.execute(text("SELECT count(*) FROM chat_sessions"))
        print(f"chat_sessions: {r.scalar()}")
        r2 = await conn.execute(text("SELECT count(*) FROM chat_messages"))
        print(f"chat_messages: {r2.scalar()}")
        
        # Test repo functions
        from src.database.repositories import chat_history as repo
        from src.database.connection import AsyncSessionLocal
        
    await engine.dispose()
    
    # Test with actual session
    session = AsyncSessionLocal()
    try:
        async with session.begin():
            result = await repo.create_or_update_session(
                session=session,
                session_id="test-dbg-001",
                title="Debug Test Session",
            )
            print(f"create_or_update_session: {result}")
            
            msg = await repo.save_message(
                session=session,
                session_id="test-dbg-001",
                role="user",
                content="Hello test",
            )
            print(f"save_message (user): {msg}")
            
            msg2 = await repo.save_message(
                session=session,
                session_id="test-dbg-001",
                role="assistant",
                content="Hello response",
            )
            print(f"save_message (assistant): {msg2}")
            
            sessions = await repo.get_sessions(session=session)
            print(f"get_sessions: {len(sessions)} sessions")
            for s in sessions:
                print(f"  - {s['id']}: {s['title']}")
            
            msgs = await repo.get_messages(session=session, session_id="test-dbg-001")
            print(f"get_messages: {len(msgs)} messages")
            
            # Cleanup
            await session.execute(text("DELETE FROM chat_messages WHERE session_id = 'test-dbg-001'"))
            await session.execute(text("DELETE FROM chat_sessions WHERE id = 'test-dbg-001'"))
        
        print("\n✅ All DB operations successful!")
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await session.close()

asyncio.run(main())
