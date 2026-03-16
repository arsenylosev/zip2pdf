"""One-shot bootstrap: ensure DB schema and create the initial admin user."""

import asyncio
import logging
import sys

import bcrypt

from app.config import settings
from app.database import create_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


async def bootstrap() -> None:
    if not settings.DATABASE_URL:
        logger.info("DATABASE_URL not set — skipping bootstrap")
        return

    async with create_db(settings.DATABASE_URL) as db:
        if not settings.ADMIN_USERNAME or not settings.ADMIN_PASSWORD:
            logger.info("ADMIN_USERNAME/ADMIN_PASSWORD not set — skipping admin creation")
            return

        existing = await db.users.get_by_username(settings.ADMIN_USERNAME)
        if existing:
            logger.info("Admin user '%s' already exists (id=%s)", existing.username, existing.id)
            return

        pw_hash = bcrypt.hashpw(
            settings.ADMIN_PASSWORD.encode("utf-8"),
            bcrypt.gensalt(),
        ).decode("utf-8")

        admin = await db.users.create_user(
            settings.ADMIN_USERNAME,
            pw_hash,
            role="admin",
        )
        logger.info("Created bootstrap admin: %s (id=%s)", admin.username, admin.id)


if __name__ == "__main__":
    asyncio.run(bootstrap())
