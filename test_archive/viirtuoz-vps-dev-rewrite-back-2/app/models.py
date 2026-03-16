"""
Pydantic domain models for persistence (users, VM records, VM events).

These are *not* request/response schemas — see ``schemas.py`` for those.
They mirror the DB rows and are returned by the DB layer.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

import asyncpg
from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class UserRole(str, Enum):
    ADMIN = "admin"
    USER = "user"


class VMEventType(str, Enum):
    CREATED = "created"
    STARTED = "started"
    STOPPED = "stopped"
    RESTARTED = "restarted"
    PAUSED = "paused"
    UNPAUSED = "unpaused"
    DELETED = "deleted"
    ERROR = "error"
    BILLING_STOPPED = "billing_stopped"


class LLMApiKeyStatus(str, Enum):
    ACTIVE = "active"
    REVOKED = "revoked"


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------

class User(BaseModel):
    id: int
    username: str
    password_hash: str
    role: str = "user"
    is_active: bool = True
    balance: Decimal = Decimal("0")
    balance_version: int = 0
    created_at: datetime

    @property
    def is_admin(self) -> bool:
        return self.role == UserRole.ADMIN.value

    @classmethod
    def from_row(cls, row: asyncpg.Record) -> User:
        return cls(
            id=row["id"],
            username=row["username"],
            password_hash=row["password_hash"],
            role=row.get("role", "user"),
            is_active=row["is_active"],
            balance=Decimal(str(row["balance"])) if row.get("balance") is not None else Decimal("0"),
            balance_version=row.get("balance_version", 0),
            created_at=row["created_at"],
        )


# ---------------------------------------------------------------------------
# VM record (audit / metadata persisted alongside K8s objects)
# ---------------------------------------------------------------------------

class VMRecord(BaseModel):
    id: int
    user_id: int
    vm_name: str
    namespace: str
    cpu: int
    memory_gb: float
    storage_gb: float
    gpu_count: int = 0
    gpu_model: str | None = None
    image_url: str
    os_type: str = "linux"
    is_running: bool = False
    last_started_at: datetime | None = None
    last_stopped_at: datetime | None = None
    last_billed_at: datetime | None = None
    created_at: datetime
    deleted_at: datetime | None = None

    @classmethod
    def from_row(cls, row: asyncpg.Record) -> VMRecord:
        return cls(
            id=row["id"],
            user_id=row["user_id"],
            vm_name=row["vm_name"],
            namespace=row["namespace"],
            cpu=row["cpu"],
            memory_gb=row["memory_gb"],
            storage_gb=row["storage_gb"],
            gpu_count=row["gpu_count"],
            gpu_model=row["gpu_model"],
            image_url=row["image_url"],
            os_type=row["os_type"],
            is_running=row.get("is_running", False),
            last_started_at=row.get("last_started_at"),
            last_stopped_at=row.get("last_stopped_at"),
            last_billed_at=row.get("last_billed_at"),
            created_at=row["created_at"],
            deleted_at=row["deleted_at"],
        )


# ---------------------------------------------------------------------------
# VM event log (append-only)
# ---------------------------------------------------------------------------

class VMEvent(BaseModel):
    event_id: str
    vm_name: str
    namespace: str
    user_id: int
    event_type: VMEventType
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

    @field_validator("metadata", mode="before")
    @classmethod
    def _parse_metadata(cls, v: Any) -> Any:
        if isinstance(v, str):
            import json
            return json.loads(v)
        return v

    @classmethod
    def from_row(cls, row: asyncpg.Record) -> VMEvent:
        return cls(
            event_id=row["event_id"],
            vm_name=row["vm_name"],
            namespace=row["namespace"],
            user_id=row["user_id"],
            event_type=VMEventType(row["event_type"]),
            metadata=row["metadata"] if row["metadata"] else {},
            created_at=row["created_at"],
        )


# ---------------------------------------------------------------------------
# LLM API keys (stored masked + encrypted)
# ---------------------------------------------------------------------------

class LLMApiKey(BaseModel):
    id: int
    user_id: int
    external_ref: str
    token_masked: str
    token_ciphertext: str
    status: LLMApiKeyStatus = LLMApiKeyStatus.ACTIVE
    created_at: datetime
    revoked_at: datetime | None = None
    last_used_at: datetime | None = None

    @property
    def is_active(self) -> bool:
        return self.status == LLMApiKeyStatus.ACTIVE

    @classmethod
    def from_row(cls, row: asyncpg.Record) -> "LLMApiKey":
        return cls(
            id=row["id"],
            user_id=row["user_id"],
            external_ref=row["external_ref"],
            token_masked=row["token_masked"],
            token_ciphertext=row["token_ciphertext"],
            status=LLMApiKeyStatus(row["status"]),
            created_at=row["created_at"],
            revoked_at=row["revoked_at"],
            last_used_at=row["last_used_at"],
        )


# ---------------------------------------------------------------------------
# LLM usage log (spend analytics source)
# ---------------------------------------------------------------------------

class LLMUsageLog(BaseModel):
    id: int
    user_id: int
    model: str
    provider: str | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost: Decimal = Decimal("0")
    currency: str = "USD"
    request_id: str | None = None
    created_at: datetime

    @classmethod
    def from_row(cls, row: asyncpg.Record) -> "LLMUsageLog":
        return cls(
            id=row["id"],
            user_id=row["user_id"],
            model=row["model"],
            provider=row["provider"],
            prompt_tokens=row["prompt_tokens"],
            completion_tokens=row["completion_tokens"],
            total_tokens=row["total_tokens"],
            estimated_cost=Decimal(str(row["estimated_cost"])),
            currency=row["currency"],
            request_id=row["request_id"],
            created_at=row["created_at"],
        )


# ---------------------------------------------------------------------------
# Balance operation ledger (admin-initiated mutations)
# ---------------------------------------------------------------------------

class BalanceOperation(BaseModel):
    id: int
    user_id: int
    source: str
    amount: Decimal
    op_type: str
    admin_username: str | None = None
    created_at: datetime

    @classmethod
    def from_row(cls, row: asyncpg.Record) -> "BalanceOperation":
        return cls(
            id=row["id"],
            user_id=row["user_id"],
            source=row["source"],
            amount=Decimal(str(row["amount"])),
            op_type=row["op_type"],
            admin_username=row["admin_username"],
            created_at=row["created_at"],
        )
