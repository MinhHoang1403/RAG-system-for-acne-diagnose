import asyncio
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

load_dotenv(PROJECT_ROOT / ".env", override=False)


def _mask_url(url: str) -> str:
    parts = urlsplit(url)
    if "@" not in parts.netloc:
        return url
    host = parts.netloc.rsplit("@", 1)[1]
    return urlunsplit((parts.scheme, f"***:***@{host}", parts.path, parts.query, parts.fragment))


async def main():
    url = os.getenv("DATABASE_URL", "postgresql+asyncpg://user:password@localhost:5433/acne_agent_db")
    print(f"DB URL: {_mask_url(url)}")
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        print('--- SESSIONS ---')
        s = await conn.execute(text('SELECT * FROM chat_sessions'))
        for r in s: print(dict(r._mapping))
        print('--- MESSAGES ---')
        m = await conn.execute(text('SELECT * FROM chat_messages'))
        for r in m: print(dict(r._mapping))
    await engine.dispose()
asyncio.run(main())
