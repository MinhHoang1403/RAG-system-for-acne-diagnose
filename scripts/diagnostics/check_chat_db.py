import asyncio
import os
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

async def main():
    engine = create_async_engine('postgresql+asyncpg://user:password@localhost:5433/acne_agent_db')
    async with engine.begin() as conn:
        print('--- SESSIONS ---')
        s = await conn.execute(text('SELECT * FROM chat_sessions'))
        for r in s: print(dict(r._mapping))
        print('--- MESSAGES ---')
        m = await conn.execute(text('SELECT * FROM chat_messages'))
        for r in m: print(dict(r._mapping))
    await engine.dispose()
asyncio.run(main())
