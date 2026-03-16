"""
PostgreSQL-backed persistence via raw asyncpg (no ORM).

Pattern follows the ``db_ops.py`` approach: a shared ``asyncpg.Pool`` is created
once at app startup (inside the FastAPI *lifespan*) and closed on shutdown.
Each DB class receives the pool and acquires connections per-operation.

Usage (inside FastAPI lifespan)::

    async with create_db(settings.DATABASE_URL) as db:
        app.state.db = db
        yield
"""

from __future__ import annotations

import json
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from decimal import Decimal

import asyncpg

from app.models import User, UserRole, VMEvent, VMEventType, VMRecord
from app.models import LLMApiKey, LLMApiKeyStatus, LLMUsageLog

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# UserDB
# ---------------------------------------------------------------------------

class UserDB:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def ensure_schema(self) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT DEFAULT 'user' NOT NULL,
                    is_active BOOLEAN DEFAULT TRUE,
                    balance NUMERIC(18,9) DEFAULT 0 NOT NULL,
                    balance_version INTEGER DEFAULT 0 NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_users_username
                ON users(username)
            """)
            # Migration: add columns if missing (existing DBs)
            await conn.execute("""
                DO $$
                BEGIN
                  IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name='users' AND column_name='role'
                  ) THEN
                    ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'user' NOT NULL;
                  END IF;
                  IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name='users' AND column_name='balance'
                  ) THEN
                    ALTER TABLE users ADD COLUMN balance NUMERIC(18,9) DEFAULT 0 NOT NULL;
                  END IF;
                  IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name='users' AND column_name='balance_version'
                  ) THEN
                    ALTER TABLE users ADD COLUMN balance_version INTEGER DEFAULT 0 NOT NULL;
                  END IF;
                END $$;
            """)

    async def create_user(
        self,
        username: str,
        password_hash: str,
        role: str = UserRole.USER.value,
    ) -> User:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                INSERT INTO users (username, password_hash, role)
                VALUES ($1, $2, $3)
                RETURNING *
            """, username, password_hash, role)
            return User.from_row(row)

    async def get_by_username(self, username: str) -> User | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM users WHERE username = $1", username,
            )
            return User.from_row(row) if row else None

    async def get_by_id(self, user_id: int) -> User | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM users WHERE id = $1", user_id,
            )
            return User.from_row(row) if row else None

    async def deactivate(self, user_id: int) -> bool:
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE users SET is_active = FALSE WHERE id = $1", user_id,
            )
            return result == "UPDATE 1"

    async def list_all(self, include_inactive: bool = False) -> list[User]:
        async with self.pool.acquire() as conn:
            if include_inactive:
                rows = await conn.fetch("SELECT * FROM users ORDER BY username")
            else:
                rows = await conn.fetch(
                    "SELECT * FROM users WHERE is_active = TRUE ORDER BY username"
                )
            return [User.from_row(r) for r in rows]

    async def set_role(self, user_id: int, role: str) -> bool:
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE users SET role = $1 WHERE id = $2", role, user_id,
            )
            return result == "UPDATE 1"

    async def get_balance(self, user_id: int) -> tuple[Decimal, int] | None:
        """Return (balance, balance_version) or None if user not found."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT balance, balance_version FROM users WHERE id = $1", user_id,
            )
            if not row:
                return None
            return Decimal(str(row["balance"])), row["balance_version"]

    async def update_balance(
        self,
        user_id: int,
        amount: Decimal,
        expected_version: int,
    ) -> tuple[Decimal, int]:
        """Atomic balance update with optimistic locking.

        Returns (new_balance, new_version).
        Raises ValueError on version mismatch or insufficient funds.
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                UPDATE users
                SET balance = balance + $1,
                    balance_version = balance_version + 1
                WHERE id = $2 AND balance_version = $3
                RETURNING balance, balance_version
            """, amount, user_id, expected_version)
            if not row:
                raise ValueError("Balance update failed: version mismatch or user not found")
            new_balance = Decimal(str(row["balance"]))
            if new_balance < 0:
                # Rollback: the UPDATE already committed the negative balance,
                # so revert it immediately.
                await conn.fetchrow("""
                    UPDATE users
                    SET balance = balance - $1,
                        balance_version = balance_version + 1
                    WHERE id = $2
                    RETURNING balance, balance_version
                """, amount, user_id)
                raise ValueError("Insufficient funds")
            return new_balance, row["balance_version"]


# ---------------------------------------------------------------------------
# BalanceSnapshotDB
# ---------------------------------------------------------------------------

class BalanceSnapshotDB:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def ensure_schema(self) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS balance_snapshots (
                    id BIGSERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id) NOT NULL,
                    source TEXT NOT NULL CHECK (source IN ('main', 'llm')),
                    balance NUMERIC(18,9) NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_balance_snapshots_user_source_created
                ON balance_snapshots(user_id, source, created_at DESC)
            """)

    async def create(
        self,
        user_id: int,
        source: str,
        balance: Decimal | float | int,
    ) -> None:
        if source not in {"main", "llm"}:
            raise ValueError("Invalid balance snapshot source")
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO balance_snapshots (user_id, source, balance)
                VALUES ($1, $2, $3)
            """, user_id, source, Decimal(str(balance)))

    async def summary_llm_spend(
        self,
        days: int = 30,
        user_id: int | None = None,
    ) -> dict:
        """Aggregate LLM spend from balance snapshots.

        Spend is calculated as sum of negative balance deltas only:
        max(prev_balance - current_balance, 0).
        Positive deltas (top-ups/transfers-in) are ignored.
        """
        async with self.pool.acquire() as conn:
            per_user_rows = await conn.fetch("""
                WITH window_start AS (
                    SELECT NOW() - ($1::int || ' days')::interval AS ts
                ),
                relevant AS (
                    SELECT bs.user_id, u.username, bs.created_at, bs.balance
                    FROM balance_snapshots bs
                    JOIN users u ON u.id = bs.user_id
                    WHERE bs.source = 'llm'
                      AND ($2::int IS NULL OR bs.user_id = $2)
                      AND (
                        bs.created_at >= (SELECT ts FROM window_start)
                        OR bs.created_at = (
                            SELECT MAX(bs2.created_at)
                            FROM balance_snapshots bs2
                            WHERE bs2.user_id = bs.user_id
                              AND bs2.source = 'llm'
                              AND bs2.created_at < (SELECT ts FROM window_start)
                        )
                      )
                ),
                deltas AS (
                    SELECT
                        user_id,
                        username,
                        created_at,
                        balance,
                        LAG(balance) OVER (PARTITION BY user_id ORDER BY created_at) AS prev_balance
                    FROM relevant
                ),
                spend_by_user AS (
                    SELECT
                        user_id,
                        SUM(
                            GREATEST(
                                COALESCE(prev_balance, balance) - balance,
                                0
                            )
                        ) AS total_spent
                    FROM deltas
                    WHERE created_at >= (SELECT ts FROM window_start)
                    GROUP BY user_id
                )
                SELECT
                    u.username,
                    COALESCE(s.total_spent, 0) AS total_cost
                FROM users u
                LEFT JOIN spend_by_user s ON s.user_id = u.id
                WHERE ($2::int IS NULL OR u.id = $2)
                ORDER BY total_cost DESC, u.username ASC
            """, days, user_id)

            per_day_rows = await conn.fetch("""
                WITH window_start AS (
                    SELECT NOW() - ($1::int || ' days')::interval AS ts
                ),
                relevant AS (
                    SELECT bs.user_id, bs.created_at, bs.balance
                    FROM balance_snapshots bs
                    WHERE bs.source = 'llm'
                      AND ($2::int IS NULL OR bs.user_id = $2)
                      AND (
                        bs.created_at >= (SELECT ts FROM window_start)
                        OR bs.created_at = (
                            SELECT MAX(bs2.created_at)
                            FROM balance_snapshots bs2
                            WHERE bs2.user_id = bs.user_id
                              AND bs2.source = 'llm'
                              AND bs2.created_at < (SELECT ts FROM window_start)
                        )
                      )
                ),
                deltas AS (
                    SELECT
                        user_id,
                        created_at,
                        balance,
                        LAG(balance) OVER (PARTITION BY user_id ORDER BY created_at) AS prev_balance
                    FROM relevant
                )
                SELECT
                    to_char(date_trunc('day', created_at), 'YYYY-MM-DD') AS day,
                    SUM(
                        GREATEST(
                            COALESCE(prev_balance, balance) - balance,
                            0
                        )
                    ) AS total_cost
                FROM deltas
                WHERE created_at >= (SELECT ts FROM window_start)
                GROUP BY day
                ORDER BY day ASC
            """, days, user_id)

            per_user_vm_rows = await conn.fetch("""
                WITH window_start AS (
                    SELECT NOW() - ($1::int || ' days')::interval AS ts
                ),
                relevant AS (
                    SELECT bs.user_id, u.username, bs.created_at, bs.balance
                    FROM balance_snapshots bs
                    JOIN users u ON u.id = bs.user_id
                    WHERE bs.source = 'main'
                      AND ($2::int IS NULL OR bs.user_id = $2)
                      AND (
                        bs.created_at >= (SELECT ts FROM window_start)
                        OR bs.created_at = (
                            SELECT MAX(bs2.created_at)
                            FROM balance_snapshots bs2
                            WHERE bs2.user_id = bs.user_id
                              AND bs2.source = 'main'
                              AND bs2.created_at < (SELECT ts FROM window_start)
                        )
                      )
                ),
                deltas AS (
                    SELECT
                        user_id,
                        username,
                        created_at,
                        balance,
                        LAG(balance) OVER (PARTITION BY user_id ORDER BY created_at) AS prev_balance
                    FROM relevant
                ),
                spend_by_user AS (
                    SELECT
                        user_id,
                        SUM(
                            GREATEST(
                                COALESCE(prev_balance, balance) - balance,
                                0
                            )
                        ) AS total_spent
                    FROM deltas
                    WHERE created_at >= (SELECT ts FROM window_start)
                    GROUP BY user_id
                )
                SELECT
                    u.username,
                    COALESCE(s.total_spent, 0) AS total_cost
                FROM users u
                LEFT JOIN spend_by_user s ON s.user_id = u.id
                WHERE ($2::int IS NULL OR u.id = $2)
                ORDER BY total_cost DESC, u.username ASC
            """, days, user_id)

            per_day_vm_rows = await conn.fetch("""
                WITH window_start AS (
                    SELECT NOW() - ($1::int || ' days')::interval AS ts
                ),
                relevant AS (
                    SELECT bs.user_id, bs.created_at, bs.balance
                    FROM balance_snapshots bs
                    WHERE bs.source = 'main'
                      AND ($2::int IS NULL OR bs.user_id = $2)
                      AND (
                        bs.created_at >= (SELECT ts FROM window_start)
                        OR bs.created_at = (
                            SELECT MAX(bs2.created_at)
                            FROM balance_snapshots bs2
                            WHERE bs2.user_id = bs.user_id
                              AND bs2.source = 'main'
                              AND bs2.created_at < (SELECT ts FROM window_start)
                        )
                      )
                ),
                deltas AS (
                    SELECT
                        user_id,
                        created_at,
                        balance,
                        LAG(balance) OVER (PARTITION BY user_id ORDER BY created_at) AS prev_balance
                    FROM relevant
                )
                SELECT
                    to_char(date_trunc('day', created_at), 'YYYY-MM-DD') AS day,
                    SUM(
                        GREATEST(
                            COALESCE(prev_balance, balance) - balance,
                            0
                        )
                    ) AS total_cost
                FROM deltas
                WHERE created_at >= (SELECT ts FROM window_start)
                GROUP BY day
                ORDER BY day ASC
            """, days, user_id)

        total_cost = sum(Decimal(str(r["total_cost"] or 0)) for r in per_user_rows)
        total_vm_cost = sum(Decimal(str(r["total_cost"] or 0)) for r in per_user_vm_rows)
        vm_by_user = {str(r["username"]): float(r["total_cost"] or 0) for r in per_user_vm_rows}
        vm_by_day = {str(r["day"]): float(r["total_cost"] or 0) for r in per_day_vm_rows}

        return {
            "days": days,
            "total_cost": float(total_cost),
            "total_vm_cost": float(total_vm_cost),
            "total_tokens": 0,
            "per_user": [
                {
                    "username": r["username"],
                    "total_cost": float(r["total_cost"] or 0),
                    "vm_total_cost": vm_by_user.get(str(r["username"]), 0.0),
                }
                for r in per_user_rows
            ],
            "per_model": [],
            "per_day": [
                {
                    "day": r["day"],
                    "total_cost": float(r["total_cost"] or 0),
                    "vm_total_cost": vm_by_day.get(str(r["day"]), 0.0),
                    "total_tokens": 0,
                }
                for r in per_day_rows
            ],
        }


# ---------------------------------------------------------------------------
# VMRecordDB
# ---------------------------------------------------------------------------

class VMRecordDB:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def ensure_schema(self) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS vm_records (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id),
                    vm_name TEXT NOT NULL,
                    namespace TEXT NOT NULL,
                    cpu INTEGER NOT NULL,
                    memory_gb DOUBLE PRECISION NOT NULL,
                    storage_gb DOUBLE PRECISION NOT NULL,
                    gpu_count INTEGER DEFAULT 0,
                    gpu_model TEXT,
                    image_url TEXT NOT NULL,
                    os_type TEXT DEFAULT 'linux',
                    is_running BOOLEAN DEFAULT FALSE NOT NULL,
                    last_started_at TIMESTAMPTZ,
                    last_stopped_at TIMESTAMPTZ,
                    last_billed_at TIMESTAMPTZ,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    deleted_at TIMESTAMPTZ
                )
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_vm_records_user_id
                ON vm_records(user_id)
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_vm_records_namespace
                ON vm_records(namespace, vm_name)
            """)
            # Migration: add billing columns if missing (existing DBs)
            await conn.execute("""
                DO $$
                BEGIN
                  IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name='vm_records' AND column_name='is_running'
                  ) THEN
                    ALTER TABLE vm_records ADD COLUMN is_running BOOLEAN DEFAULT FALSE NOT NULL;
                    ALTER TABLE vm_records ADD COLUMN last_started_at TIMESTAMPTZ;
                    ALTER TABLE vm_records ADD COLUMN last_stopped_at TIMESTAMPTZ;
                    ALTER TABLE vm_records ADD COLUMN last_billed_at TIMESTAMPTZ;
                    -- Bill forward only: existing active VMs start billing from now
                    UPDATE vm_records SET last_billed_at = NOW()
                      WHERE deleted_at IS NULL;
                  END IF;
                END $$;
            """)

    async def create(
        self,
        user_id: int,
        vm_name: str,
        namespace: str,
        cpu: int,
        memory_gb: float,
        storage_gb: float,
        image_url: str,
        gpu_count: int = 0,
        gpu_model: str | None = None,
        os_type: str = "linux",
    ) -> VMRecord:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                INSERT INTO vm_records
                    (user_id, vm_name, namespace, cpu, memory_gb, storage_gb,
                     gpu_count, gpu_model, image_url, os_type,
                     is_running, last_started_at)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10, TRUE, NOW())
                RETURNING *
            """, user_id, vm_name, namespace, cpu, memory_gb, storage_gb,
                gpu_count, gpu_model, image_url, os_type)
            return VMRecord.from_row(row)

    async def mark_deleted(self, namespace: str, vm_name: str) -> bool:
        async with self.pool.acquire() as conn:
            result = await conn.execute("""
                UPDATE vm_records SET deleted_at = NOW()
                WHERE namespace = $1 AND vm_name = $2 AND deleted_at IS NULL
            """, namespace, vm_name)
            return "UPDATE" in result

    async def get_active_for_user(self, user_id: int) -> list[VMRecord]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT * FROM vm_records
                WHERE user_id = $1 AND deleted_at IS NULL
                ORDER BY created_at DESC
            """, user_id)
            return [VMRecord.from_row(r) for r in rows]

    async def get_by_name(self, namespace: str, vm_name: str) -> VMRecord | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT * FROM vm_records
                WHERE namespace = $1 AND vm_name = $2 AND deleted_at IS NULL
            """, namespace, vm_name)
            return VMRecord.from_row(row) if row else None

    async def set_running(self, namespace: str, vm_name: str, running: bool) -> bool:
        """Update the running state and the corresponding timestamp."""
        async with self.pool.acquire() as conn:
            if running:
                result = await conn.execute("""
                    UPDATE vm_records
                    SET is_running = TRUE, last_started_at = NOW()
                    WHERE namespace = $1 AND vm_name = $2 AND deleted_at IS NULL
                """, namespace, vm_name)
            else:
                result = await conn.execute("""
                    UPDATE vm_records
                    SET is_running = FALSE, last_stopped_at = NOW()
                    WHERE namespace = $1 AND vm_name = $2 AND deleted_at IS NULL
                """, namespace, vm_name)
            return "UPDATE" in result

    async def get_all_billable(self) -> list[VMRecord]:
        """Return VMs that need billing: running, or stopped after last bill (anti-gaming)."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT * FROM vm_records
                WHERE deleted_at IS NULL
                  AND (
                    is_running = TRUE
                    OR (
                      last_stopped_at IS NOT NULL
                      AND (last_billed_at IS NULL OR last_stopped_at > last_billed_at)
                    )
                  )
            """)
            return [VMRecord.from_row(r) for r in rows]

    async def update_last_billed(self, vm_id: int, billed_at: datetime) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE vm_records SET last_billed_at = $1 WHERE id = $2
            """, billed_at, vm_id)


# ---------------------------------------------------------------------------
# VMEventDB (append-only event log)
# ---------------------------------------------------------------------------

class VMEventDB:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def ensure_schema(self) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS vm_events (
                    event_id TEXT PRIMARY KEY,
                    vm_name TEXT NOT NULL,
                    namespace TEXT NOT NULL,
                    user_id INTEGER REFERENCES users(id),
                    event_type TEXT NOT NULL,
                    metadata JSONB DEFAULT '{}',
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_vm_events_vm
                ON vm_events(namespace, vm_name)
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_vm_events_created
                ON vm_events(created_at DESC)
            """)

    async def log_event(
        self,
        vm_name: str,
        namespace: str,
        user_id: int,
        event_type: VMEventType,
        metadata: dict | None = None,
    ) -> VMEvent:
        async with self.pool.acquire() as conn:
            event_id = str(uuid.uuid4())
            row = await conn.fetchrow("""
                INSERT INTO vm_events
                    (event_id, vm_name, namespace, user_id, event_type, metadata)
                VALUES ($1,$2,$3,$4,$5,$6)
                RETURNING *
            """, event_id, vm_name, namespace, user_id,
                event_type.value, json.dumps(metadata or {}))
            return VMEvent.from_row(row)

    async def get_events(
        self,
        namespace: str,
        vm_name: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[VMEvent]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT * FROM vm_events
                WHERE namespace = $1 AND vm_name = $2
                ORDER BY created_at DESC
                LIMIT $3 OFFSET $4
            """, namespace, vm_name, limit, offset)
            return [VMEvent.from_row(r) for r in rows]

    async def get_user_events(
        self,
        user_id: int,
        limit: int = 100,
    ) -> list[VMEvent]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT * FROM vm_events
                WHERE user_id = $1
                ORDER BY created_at DESC
                LIMIT $2
            """, user_id, limit)
            return [VMEvent.from_row(r) for r in rows]


# ---------------------------------------------------------------------------
# LLMApiKeyDB
# ---------------------------------------------------------------------------

class LLMApiKeyDB:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def ensure_schema(self) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS llm_api_keys (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id) NOT NULL,
                    external_ref TEXT NOT NULL,
                    token_masked TEXT NOT NULL,
                    token_ciphertext TEXT NOT NULL,
                    status TEXT DEFAULT 'active' NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    revoked_at TIMESTAMPTZ,
                    last_used_at TIMESTAMPTZ
                )
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_llm_api_keys_user
                ON llm_api_keys(user_id)
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_llm_api_keys_status
                ON llm_api_keys(status)
            """)

    async def list_for_user(self, user_id: int) -> list[LLMApiKey]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT * FROM llm_api_keys
                WHERE user_id = $1
                ORDER BY created_at DESC
            """, user_id)
            return [LLMApiKey.from_row(r) for r in rows]

    async def count_active_for_user(self, user_id: int) -> int:
        async with self.pool.acquire() as conn:
            return int(
                await conn.fetchval(
                    "SELECT COUNT(*) FROM llm_api_keys WHERE user_id = $1 AND status = 'active'",
                    user_id,
                )
            )

    async def create(
        self,
        user_id: int,
        external_ref: str,
        token_masked: str,
        token_ciphertext: str,
    ) -> LLMApiKey:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                INSERT INTO llm_api_keys (user_id, external_ref, token_masked, token_ciphertext, status)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING *
            """, user_id, external_ref, token_masked, token_ciphertext, LLMApiKeyStatus.ACTIVE.value)
            return LLMApiKey.from_row(row)

    async def get_by_id_for_user(self, user_id: int, key_id: int) -> LLMApiKey | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT * FROM llm_api_keys
                WHERE user_id = $1 AND id = $2
            """, user_id, key_id)
            return LLMApiKey.from_row(row) if row else None

    async def mark_revoked(self, user_id: int, key_id: int) -> bool:
        async with self.pool.acquire() as conn:
            result = await conn.execute("""
                UPDATE llm_api_keys
                SET status = $1, revoked_at = NOW()
                WHERE user_id = $2 AND id = $3 AND status = $4
            """, LLMApiKeyStatus.REVOKED.value, user_id, key_id, LLMApiKeyStatus.ACTIVE.value)
            return result == "UPDATE 1"

    async def touch_last_used(self, key_id: int) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE llm_api_keys SET last_used_at = NOW() WHERE id = $1",
                key_id,
            )


# ---------------------------------------------------------------------------
# LLMUsageLogDB
# ---------------------------------------------------------------------------

class LLMUsageLogDB:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def ensure_schema(self) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS llm_usage_logs (
                    id BIGSERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id) NOT NULL,
                    model TEXT NOT NULL,
                    provider TEXT,
                    prompt_tokens INTEGER DEFAULT 0 NOT NULL,
                    completion_tokens INTEGER DEFAULT 0 NOT NULL,
                    total_tokens INTEGER DEFAULT 0 NOT NULL,
                    estimated_cost NUMERIC(18,9) DEFAULT 0 NOT NULL,
                    currency TEXT DEFAULT 'USD' NOT NULL,
                    request_id TEXT,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_llm_usage_logs_user_created
                ON llm_usage_logs(user_id, created_at DESC)
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_llm_usage_logs_created
                ON llm_usage_logs(created_at DESC)
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_llm_usage_logs_request_id
                ON llm_usage_logs(request_id)
            """)

    async def create(
        self,
        user_id: int,
        model: str,
        provider: str | None,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
        estimated_cost: Decimal,
        currency: str = "USD",
        request_id: str | None = None,
    ) -> LLMUsageLog:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                INSERT INTO llm_usage_logs
                (user_id, model, provider, prompt_tokens, completion_tokens, total_tokens, estimated_cost, currency, request_id)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
                RETURNING *
            """, user_id, model, provider, prompt_tokens, completion_tokens, total_tokens, estimated_cost, currency, request_id)
            return LLMUsageLog.from_row(row)

    async def summary(
        self,
        days: int = 30,
    ) -> dict:
        async with self.pool.acquire() as conn:
            per_user_rows = await conn.fetch("""
                SELECT u.username, COALESCE(SUM(l.estimated_cost), 0) AS total_cost
                FROM llm_usage_logs l
                JOIN users u ON u.id = l.user_id
                WHERE l.created_at >= NOW() - ($1::int || ' days')::interval
                GROUP BY u.username
                ORDER BY total_cost DESC
            """, days)
            per_model_rows = await conn.fetch("""
                SELECT model, COALESCE(SUM(estimated_cost), 0) AS total_cost, SUM(total_tokens) AS total_tokens
                FROM llm_usage_logs
                WHERE created_at >= NOW() - ($1::int || ' days')::interval
                GROUP BY model
                ORDER BY total_cost DESC
            """, days)
            per_day_rows = await conn.fetch("""
                SELECT to_char(date_trunc('day', created_at), 'YYYY-MM-DD') AS day,
                       COALESCE(SUM(estimated_cost), 0) AS total_cost,
                       SUM(total_tokens) AS total_tokens
                FROM llm_usage_logs
                WHERE created_at >= NOW() - ($1::int || ' days')::interval
                GROUP BY day
                ORDER BY day ASC
            """, days)
            total_cost = await conn.fetchval("""
                SELECT COALESCE(SUM(estimated_cost), 0)
                FROM llm_usage_logs
                WHERE created_at >= NOW() - ($1::int || ' days')::interval
            """, days)
            total_tokens = await conn.fetchval("""
                SELECT COALESCE(SUM(total_tokens), 0)
                FROM llm_usage_logs
                WHERE created_at >= NOW() - ($1::int || ' days')::interval
            """, days)

        return {
            "days": days,
            "total_cost": float(total_cost or 0),
            "total_tokens": int(total_tokens or 0),
            "per_user": [
                {"username": r["username"], "total_cost": float(r["total_cost"])}
                for r in per_user_rows
            ],
            "per_model": [
                {
                    "model": r["model"],
                    "total_cost": float(r["total_cost"]),
                    "total_tokens": int(r["total_tokens"] or 0),
                }
                for r in per_model_rows
            ],
            "per_day": [
                {
                    "day": r["day"],
                    "total_cost": float(r["total_cost"]),
                    "total_tokens": int(r["total_tokens"] or 0),
                }
                for r in per_day_rows
            ],
        }


# ---------------------------------------------------------------------------
# BalanceOperationDB (admin-initiated balance mutations ledger)
# ---------------------------------------------------------------------------

class BalanceOperationDB:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def ensure_schema(self) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS balance_operations (
                    id BIGSERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id) NOT NULL,
                    source TEXT NOT NULL CHECK (source IN ('main', 'llm')),
                    amount NUMERIC(18,9) NOT NULL,
                    op_type TEXT NOT NULL CHECK (op_type IN ('topup', 'transfer_in', 'transfer_out')),
                    admin_username TEXT,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_balance_operations_user_source
                ON balance_operations(user_id, source, created_at DESC)
            """)

    async def create(
        self,
        user_id: int,
        source: str,
        amount: Decimal,
        op_type: str,
        admin_username: str | None = None,
    ) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO balance_operations (user_id, source, amount, op_type, admin_username)
                VALUES ($1, $2, $3, $4, $5)
            """, user_id, source, amount, op_type, admin_username)

    async def get_cumulative(self, user_id: int, source: str) -> Decimal:
        """Net admin-initiated change: SUM of all amounts for this user+source."""
        async with self.pool.acquire() as conn:
            val = await conn.fetchval("""
                SELECT COALESCE(SUM(amount), 0)
                FROM balance_operations
                WHERE user_id = $1 AND source = $2
            """, user_id, source)
            return Decimal(str(val))

    async def get_total_deposited(self, user_id: int, source: str) -> Decimal:
        """Total positive inflows only (top-ups + transfers in)."""
        async with self.pool.acquire() as conn:
            val = await conn.fetchval("""
                SELECT COALESCE(SUM(amount), 0)
                FROM balance_operations
                WHERE user_id = $1 AND source = $2 AND amount > 0
            """, user_id, source)
            return Decimal(str(val))

    async def list_for_user(
        self,
        user_id: int,
        source: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        async with self.pool.acquire() as conn:
            if source:
                rows = await conn.fetch("""
                    SELECT * FROM balance_operations
                    WHERE user_id = $1 AND source = $2
                    ORDER BY created_at DESC
                    LIMIT $3
                """, user_id, source, limit)
            else:
                rows = await conn.fetch("""
                    SELECT * FROM balance_operations
                    WHERE user_id = $1
                    ORDER BY created_at DESC
                    LIMIT $2
                """, user_id, limit)
            return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Aggregated DB handle
# ---------------------------------------------------------------------------

class DB:
    """Convenience container holding all sub-DBs and the pool."""

    def __init__(
        self,
        pool: asyncpg.Pool,
        users: UserDB,
        vm_records: VMRecordDB,
        vm_events: VMEventDB,
        balance_snapshots: BalanceSnapshotDB,
        balance_operations: BalanceOperationDB,
        llm_api_keys: LLMApiKeyDB,
        llm_usage_logs: LLMUsageLogDB,
    ):
        self.pool = pool
        self.users = users
        self.vm_records = vm_records
        self.vm_events = vm_events
        self.balance_snapshots = balance_snapshots
        self.balance_operations = balance_operations
        self.llm_api_keys = llm_api_keys
        self.llm_usage_logs = llm_usage_logs


@asynccontextmanager
async def create_db(dsn: str, **pool_kwargs):
    """Create the shared connection pool and initialise all schemas.

    Yields a :class:`DB` instance.  The pool is closed on exit.
    """
    pool = await asyncpg.create_pool(dsn, **pool_kwargs)

    users = UserDB(pool)
    vm_records = VMRecordDB(pool)
    vm_events = VMEventDB(pool)
    balance_snapshots = BalanceSnapshotDB(pool)
    balance_operations = BalanceOperationDB(pool)
    llm_api_keys = LLMApiKeyDB(pool)
    llm_usage_logs = LLMUsageLogDB(pool)

    await users.ensure_schema()
    await vm_records.ensure_schema()
    await vm_events.ensure_schema()
    await balance_snapshots.ensure_schema()
    await balance_operations.ensure_schema()
    await llm_api_keys.ensure_schema()
    await llm_usage_logs.ensure_schema()

    try:
        yield DB(
            pool=pool,
            users=users,
            vm_records=vm_records,
            vm_events=vm_events,
            balance_snapshots=balance_snapshots,
            balance_operations=balance_operations,
            llm_api_keys=llm_api_keys,
            llm_usage_logs=llm_usage_logs,
        )
    finally:
        await pool.close()
