"""
HTTP client for the LLM auth-service admin API.

Bridges viirtuoz-vps user accounts to the LLM billing system.
The auth-service uses UUIDs for user IDs; viirtuoz-vps uses integers.
The shared key between the two systems is ``username``.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_TIMEOUT = 10


class LLMAuthClient:
    """Thin wrapper around the LLM auth-service admin endpoints."""

    def _headers(self) -> dict[str, str]:
        return {"X-Cudo-Admin": f"Bearer {settings.LLM_AUTH_ADMIN_TOKEN}"}

    @property
    def _base(self) -> str:
        return settings.LLM_AUTH_SERVICE_URL.rstrip("/")

    def available(self) -> bool:
        return bool(settings.LLM_AUTH_SERVICE_URL and settings.LLM_AUTH_ADMIN_TOKEN)

    # ------------------------------------------------------------------
    # User lookup / registration
    # ------------------------------------------------------------------

    async def get_user_id(self, username: str) -> str | None:
        """Resolve a VPS username to an auth-service UUID."""
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
                r = await c.post(
                    f"{self._base}/get-user-id",
                    json={"username": username},
                    headers=self._headers(),
                )
                if r.status_code == 200:
                    return r.json()["user_id"]
        except httpx.HTTPError as exc:
            logger.warning("LLM auth-service get_user_id failed: %s", exc)
        return None

    async def ensure_user(self, username: str) -> str | None:
        """Register the user in auth-service if absent, return their UUID."""
        uid = await self.get_user_id(username)
        if uid:
            return uid
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
                r = await c.post(
                    f"{self._base}/register",
                    json={"username": username},
                    headers=self._headers(),
                )
                if r.status_code == 200:
                    return str(r.json().get("id"))
        except httpx.HTTPError as exc:
            logger.warning("LLM auth-service register failed: %s", exc)
        return await self.get_user_id(username)

    async def verify_token_owner(self, token: str) -> str | None:
        """Verify SK token via auth-service and return the auth-service user_id it belongs to.
        Returns None if token is invalid or auth-service is unavailable.
        """
        if not self.available():
            return None
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
                r = await c.get(
                    f"{self._base}/verify-token",
                    params={"token": token},
                    headers=self._headers(),
                )
                if r.status_code == 200:
                    return str(r.json().get("user_id", "")) or None
        except httpx.HTTPError as exc:
            logger.warning("LLM auth-service verify_token failed: %s", exc)
        return None

    # ------------------------------------------------------------------
    # Balance operations
    # ------------------------------------------------------------------

    async def get_balance(self, llm_user_id: str) -> float | None:
        """Get the current LLM balance (uses the amount=0 trick)."""
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
                r = await c.post(
                    f"{self._base}/balance/increase-by-id",
                    json={"user_id": llm_user_id, "amount": "0"},
                    headers=self._headers(),
                )
                if r.status_code == 200:
                    raw = r.json().get("balance")
                    if raw is None:
                        return None
                    return float(raw)
        except httpx.HTTPError as exc:
            logger.warning("LLM auth-service get_balance failed: %s", exc)
        return None

    def create_token_available(self) -> bool:
        """Whether create-token is available (auth-service configured)."""
        return self.available()

    async def create_token(self, username: str) -> str | None:
        """Backward-compatible shortcut that returns only token value."""
        data = await self.create_token_details(username)
        return data.get("token") if data else None

    async def create_token_details(self, username: str) -> dict[str, str] | None:
        """Create SK token and return token + external reference for storage."""
        if not self.available():
            return None
        llm_uid = await self.ensure_user(username)
        if not llm_uid:
            return None
        url = f"{self._base}/generate-token-by-id"
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
                r = await c.post(url, params={"user_id": llm_uid}, headers=self._headers())
                if r.status_code != 200:
                    logger.warning(
                        "auth-service generate-token-by-id %s: HTTP %d – %s",
                        username, r.status_code, r.text,
                    )
                    return None
                data = r.json()
                token = data.get("access_token")
                if not token:
                    return None
                external_ref = (
                    data.get("token_id")
                    or data.get("id")
                    or data.get("token_ref")
                    or str(token)
                )
                return {"token": str(token), "external_ref": str(external_ref)}
        except httpx.HTTPError as exc:
            logger.warning("auth-service create_token failed: %s", exc)
            return None

    async def adjust_balance(self, llm_user_id: str, amount: Decimal) -> float | None:
        """Increase (positive) or decrease (negative) the LLM balance.

        Returns the new balance, or None on failure.
        """
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
                r = await c.post(
                    f"{self._base}/balance/increase-by-id",
                    json={"user_id": llm_user_id, "amount": str(amount)},
                    headers=self._headers(),
                )
                if r.status_code == 200:
                    return r.json()["balance"]
                logger.warning(
                    "LLM auth-service adjust_balance %s: HTTP %d – %s",
                    llm_user_id, r.status_code, r.text,
                )
        except httpx.HTTPError as exc:
            logger.warning("LLM auth-service adjust_balance failed: %s", exc)
        return None
