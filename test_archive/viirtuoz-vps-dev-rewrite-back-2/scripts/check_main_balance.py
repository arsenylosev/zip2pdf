#!/usr/bin/env python3
"""Check main (PostgreSQL) balance for a user. Usage: python -m scripts.check_main_balance <username>"""

import asyncio
import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from app.config import settings
from app.database import create_db


async def main():
    username = sys.argv[1] if len(sys.argv) > 1 else "ops"
    if not settings.DATABASE_URL:
        print("DATABASE_URL not configured")
        sys.exit(1)
    async with create_db(settings.DATABASE_URL) as db:
        user = await db.users.get_by_username(username)
        if not user:
            print(f"User '{username}' not found")
            sys.exit(1)
        bal, ver = await db.users.get_balance(user.id) or (None, None)
        print(f"{username}: id={user.id}, main_balance={bal}, balance_version={ver}")


if __name__ == "__main__":
    asyncio.run(main())
