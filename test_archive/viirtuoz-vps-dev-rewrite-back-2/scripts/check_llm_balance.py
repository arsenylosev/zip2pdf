#!/usr/bin/env python3
"""Check LLM balance for a user in auth-service. Usage: python -m scripts.check_llm_balance <username>"""

import asyncio
import sys
from pathlib import Path

# Ensure project root in path (for direct run: python scripts/check_llm_balance.py)
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from app.services.llm_auth_client import LLMAuthClient


async def main():
    username = sys.argv[1] if len(sys.argv) > 1 else "ops"
    client = LLMAuthClient()
    if not client.available():
        print("LLM auth-service not configured (LLM_AUTH_SERVICE_URL, LLM_AUTH_ADMIN_TOKEN)")
        sys.exit(1)
    uid = await client.get_user_id(username)
    if not uid:
        print(f"User '{username}' not found in auth-service")
        sys.exit(1)
    balance = await client.get_balance(uid)
    print(f"{username}: user_id={uid}, llm_balance={balance}")


if __name__ == "__main__":
    asyncio.run(main())
