"""LLM chat, keys management and models routes."""

from __future__ import annotations

import json
import logging
import time
import uuid
from decimal import Decimal
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, StreamingResponse
from app.templating import Jinja2Templates

from app.auth.dependencies import SessionUser, get_current_namespace, require_owner
from app.config import settings
from app.debug_log import write_debug_log
from app.schemas import LLMChatRequest
from app.services.llm_auth_client import LLMAuthClient
from app.utils.llm_key_crypto import decrypt_token, encrypt_token, mask_token

logger = logging.getLogger(__name__)

router = APIRouter(tags=["llm"])
templates = Jinja2Templates(directory="app/templates")

# Кэш доступных LLM-моделей (обновляется каждые 5 мин)
_llm_models_cache: tuple[list[dict[str, Any]], float] | None = None
_LLM_MODELS_CACHE_TTL = 300  # 5 минут


async def _fetch_available_llm_models() -> list[dict[str, Any]]:
    """Загрузить список LLM из llm-service /v1/models."""
    base = (settings.LLM_SERVICE_URL or "").rstrip("/")
    if not base:
        logger.warning("available-models: LLM_SERVICE_URL is empty, returning []")
        return []
    shared_token = (settings.LLM_CHAT_SHARED_TOKEN or "").strip()
    headers = {"Authorization": f"Bearer {shared_token}"} if shared_token else None

    async with httpx.AsyncClient(timeout=15) as client:
        try:
            r = await client.get(f"{base}/health", headers=headers)
            logger.info("LLM service %s/health: HTTP %d", base, r.status_code)
        except Exception as e:
            logger.warning("LLM service %s unreachable: %s", base, e)

        try:
            r = await client.get(f"{base}/v1/models", headers=headers)
            if r.status_code != 200:
                logger.warning("LLM /v1/models: HTTP %d %s", r.status_code, r.text[:200])
                return []
            data = r.json()
        except Exception as e:
            logger.warning("LLM /v1/models failed: %s", e)
            return []

    items: list[Any]
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = data.get("data") or data.get("models") or data.get("items") or data.get("results") or []
    else:
        items = []

    result: list[dict[str, Any]] = []
    for m in items:
        if isinstance(m, dict):
            row = dict(m)
            row.setdefault("_source", "llm")
            result.append(row)
    return result


def _llm_service_base() -> str:
    """LLM service base URL without trailing slash."""
    url = (settings.LLM_SERVICE_URL or "").rstrip("/")
    return url


def _require_db(request: Request):
    db = getattr(request.app.state, "db", None)
    if not db:
        raise HTTPException(503, "Database not available")
    return db


def _shared_chat_token() -> str:
    return (settings.LLM_CHAT_SHARED_TOKEN or "").strip()


async def _ensure_first_user_api_key(
    request: Request,
    username: str,
    user: SessionUser,
) -> str | None:
    """Return an active decrypted user key; create the first one if absent."""
    db = getattr(request.app.state, "db", None)
    if not db or not hasattr(db, "llm_api_keys"):
        return None

    secret = (settings.LLM_KEYS_ENCRYPTION_KEY or "").strip()
    if not secret:
        logger.warning("llm-models: LLM_KEYS_ENCRYPTION_KEY is not configured")
        return None

    try:
        keys = await db.llm_api_keys.list_for_user(user.user_id)
        for key in keys:
            if not key.is_active:
                continue
            try:
                return decrypt_token(key.token_ciphertext, secret)
            except Exception as e:
                logger.warning("llm-models: failed to decrypt key %s: %s", key.id, e)

        if settings.LLM_USER_KEYS_MAX > 0:
            active_count = await db.llm_api_keys.count_active_for_user(user.user_id)
            if active_count >= settings.LLM_USER_KEYS_MAX:
                logger.warning(
                    "llm-models: cannot auto-create key, limit reached (%s) for user_id=%s",
                    settings.LLM_USER_KEYS_MAX,
                    user.user_id,
                )
                return None

        llm_client = LLMAuthClient()
        if not llm_client.available():
            logger.warning("llm-models: LLM auth-service not configured")
            return None
        token_data = await llm_client.create_token_details(username)
        if not token_data:
            logger.warning("llm-models: auth-service create-token failed")
            return None

        token_value = token_data["token"]
        external_ref = token_data["external_ref"]
        await db.llm_api_keys.create(
            user_id=user.user_id,
            external_ref=external_ref,
            token_masked=mask_token(token_value),
            token_ciphertext=encrypt_token(token_value, secret),
        )
        return token_value
    except Exception as e:
        logger.warning("llm-models: ensure first key failed: %s", e)
        return None


def _user_message_from_status(status_code: int, body: dict | None) -> str:
    """User-facing message from auth/llm-service status code and response body."""
    if body and isinstance(body.get("error"), dict):
        msg = body["error"].get("message") or body["error"].get("detail")
        code = body["error"].get("code", "")
        if code == "insufficient_balance":
            return "Insufficient balance. Please top up your account."
        if "quota" in (msg or "").lower() or "billing" in (msg or "").lower():
            return "Insufficient balance. Check billing."
    if status_code == 401:
        return "Invalid or expired key. Check your token."
    if status_code == 403:
        return "Access denied. Check account status."
    if status_code == 402:
        return "Insufficient balance. Please top up your account."
    if status_code == 429:
        return "Rate limit exceeded or insufficient funds."
    if status_code >= 500:
        return "LLM server error. Try again later."
    return "LLM access error."


@router.get("/{username}/llm", include_in_schema=False)
async def llm_chat_page(
    request: Request,
    username: str,
    user: SessionUser = Depends(require_owner),
    user_ns: str = Depends(get_current_namespace),
):
    # region agent log
    write_debug_log(
        run_id="run1",
        hypothesis_id="H1",
        location="app/routers/llm.py:llm_chat_page",
        message="llm page route hit",
        data={"method": request.method, "path": request.url.path, "username": username},
    )
    # endregion
    llm_display = settings.LLM_MODEL.split("/")[-1] if "/" in settings.LLM_MODEL else settings.LLM_MODEL
    return templates.TemplateResponse("llm_chat.html", {
        "request": request,
        "username": username,
        "namespace": user_ns,
        "is_admin": user.is_admin,
        "page": "llm",
        "llm_model": llm_display,
        "llm_default_model": settings.LLM_MODEL,
    })


@router.get("/{username}/llm/chat", include_in_schema=False)
async def llm_chat_page_alias(
    request: Request,
    username: str,
    user: SessionUser = Depends(require_owner),
    user_ns: str = Depends(get_current_namespace),
):
    # region agent log
    write_debug_log(
        run_id="post-fix",
        hypothesis_id="H1",
        location="app/routers/llm.py:llm_chat_page_alias",
        message="llm chat alias route hit, redirecting",
        data={"method": request.method, "path": request.url.path, "username": username},
    )
    # endregion
    return RedirectResponse(url=f"/{username}/llm", status_code=307)


@router.get("/{username}/api/llm/available-models", include_in_schema=False)
async def get_available_llm_models(
    user: SessionUser = Depends(require_owner),
):
    """Список доступных LLM из llm-service /v1/models (кэш 5 мин)."""
    global _llm_models_cache
    now = time.monotonic()
    if _llm_models_cache is not None:
        cached, cached_at = _llm_models_cache
        if now - cached_at < _LLM_MODELS_CACHE_TTL:
            return {"models": cached, "cached": True}
    models = await _fetch_available_llm_models()
    logger.info("available-models: fetched %d models (LLM_SERVICE_URL=%s)", len(models), settings.LLM_SERVICE_URL or "(empty)")
    _llm_models_cache = (models, now)
    return {"models": models, "cached": False}


@router.get("/{username}/llm/models", include_in_schema=False)
async def llm_models_page(
    request: Request,
    username: str,
    user: SessionUser = Depends(require_owner),
    user_ns: str = Depends(get_current_namespace),
):
    """Страница «Доступные модели»."""
    llm_example_api_key = await _ensure_first_user_api_key(request, username, user)
    return templates.TemplateResponse("llm_models.html", {
        "request": request,
        "username": username,
        "namespace": user_ns,
        "is_admin": user.is_admin,
        "page": "llm",
        "llm_example_api_key": llm_example_api_key or "",
    })


@router.get("/{username}/llm/keys", include_in_schema=False)
async def llm_keys_page(
    request: Request,
    username: str,
    user: SessionUser = Depends(require_owner),
    user_ns: str = Depends(get_current_namespace),
):
    """Страница «Ключи API»."""
    return templates.TemplateResponse("llm_keys.html", {
        "request": request,
        "username": username,
        "namespace": user_ns,
        "is_admin": user.is_admin,
        "page": "llm",
        "llm_user_keys_max": settings.LLM_USER_KEYS_MAX,
    })


@router.get("/{username}/llm/status", include_in_schema=False)
async def llm_status(user: SessionUser = Depends(require_owner)):
    """Compatibility endpoint: chat always uses shared token."""
    return {"sk_mode": False, "connected": True, "create_token_available": True}


@router.get("/{username}/api/llm/keys", include_in_schema=False)
async def llm_keys_list(
    request: Request,
    user: SessionUser = Depends(require_owner),
):
    db = _require_db(request)
    keys = await db.llm_api_keys.list_for_user(user.user_id)
    return {
        "keys": [
            {
                "id": k.id,
                "external_ref": k.external_ref,
                "token_masked": k.token_masked,
                "status": k.status.value,
                "created_at": k.created_at.isoformat(),
                "revoked_at": k.revoked_at.isoformat() if k.revoked_at else None,
                "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
            }
            for k in keys
        ],
        "max_keys": settings.LLM_USER_KEYS_MAX,
    }


@router.post("/{username}/api/llm/keys", include_in_schema=False)
async def llm_keys_create(
    request: Request,
    username: str,
    user: SessionUser = Depends(require_owner),
):
    db = _require_db(request)
    if settings.LLM_USER_KEYS_MAX > 0:
        active_count = await db.llm_api_keys.count_active_for_user(user.user_id)
        if active_count >= settings.LLM_USER_KEYS_MAX:
            raise HTTPException(400, f"API keys limit reached ({settings.LLM_USER_KEYS_MAX})")

    llm_client = LLMAuthClient()
    if not llm_client.available():
        raise HTTPException(503, "LLM auth-service not configured")
    token_data = await llm_client.create_token_details(username)
    if not token_data:
        raise HTTPException(502, "Auth-service create-token failed")
    token_value = token_data["token"]
    external_ref = token_data["external_ref"]

    secret = (settings.LLM_KEYS_ENCRYPTION_KEY or "").strip()
    if not secret:
        raise HTTPException(503, "LLM_KEYS_ENCRYPTION_KEY is not configured")

    row = await db.llm_api_keys.create(
        user_id=user.user_id,
        external_ref=external_ref,
        token_masked=mask_token(token_value),
        token_ciphertext=encrypt_token(token_value, secret),
    )
    return {
        "id": row.id,
        "token": token_value,  # show once to user
        "token_masked": row.token_masked,
        "status": row.status.value,
        "created_at": row.created_at.isoformat(),
    }


@router.get("/{username}/api/llm/keys/{key_id}/reveal", include_in_schema=False)
async def llm_keys_reveal(
    request: Request,
    key_id: int,
    user: SessionUser = Depends(require_owner),
):
    """Показать полный ключ (расшифровка из БД). Только владелец."""
    db = _require_db(request)
    key = await db.llm_api_keys.get_by_id_for_user(user.user_id, key_id)
    if not key:
        raise HTTPException(404, "Key not found")
    if not key.is_active:
        raise HTTPException(400, "Cannot reveal revoked key")
    secret = (settings.LLM_KEYS_ENCRYPTION_KEY or "").strip()
    if not secret:
        raise HTTPException(503, "LLM_KEYS_ENCRYPTION_KEY is not configured")
    try:
        token = decrypt_token(key.token_ciphertext, secret)
    except Exception as e:
        logger.warning("llm_keys_reveal decrypt failed: %s", e)
        raise HTTPException(500, "Failed to decrypt key")
    return {"token": token}


@router.post("/{username}/llm/chat")
async def llm_chat_api(
    request: Request,
    username: str,
    body: LLMChatRequest,
    user: SessionUser = Depends(require_owner),
):
    # region agent log
    write_debug_log(
        run_id="run1",
        hypothesis_id="H3",
        location="app/routers/llm.py:llm_chat_api",
        message="llm chat api route hit",
        data={
            "method": request.method,
            "path": request.url.path,
            "username": username,
            "messages_count": len(body.messages),
            "model": body.model or "",
        },
    )
    # endregion
    system_message = {
        "role": "system",
        "content": (
            "Ты AI-ассистент платформы виртуализации Вииртуоз.\n"
            "Отвечай на русском языке, если пользователь не попросит иначе.\n"
            "Можешь помочь с виртуализацией, Linux, DevOps, Kubernetes.\n"
            "Форматируй ответы с использованием Markdown."
        ),
    }
    full_messages = [system_message] + body.messages

    base_url = _llm_service_base()
    request_id = str(uuid.uuid4())

    async def generate():
        api_url: str
        auth_header: str
        provider = "llm-service"
        if base_url:
            token = _shared_chat_token()
            if not token:
                yield f"data: {json.dumps({'error': 'LLM_CHAT_SHARED_TOKEN is not configured'})}\n\n"
                return
            api_url = f"{base_url}/v1/chat/completions"
            auth_header = f"Bearer {token}"
        else:
            token = _shared_chat_token()
            if not token:
                if settings.FRONTEND_STUB_MODE:
                    yield f"data: {json.dumps({'content': '⚠️ **Stub Mode**: LLM chat token is missing.'})}\n\n"
                    yield "data: [DONE]\n\n"
                    return
                yield f"data: {json.dumps({'error': 'LLM_CHAT_SHARED_TOKEN is not configured'})}\n\n"
                return
            api_url = settings.LLM_API_URL
            auth_header = f"Bearer {token}"
            provider = "legacy-llm-api"

        model_id = (body.model or "").strip() or settings.LLM_MODEL
        if not model_id:
            model_id = "gpt-4o-mini"  # fallback if no default

        prompt_tokens = 0
        completion_tokens = 0
        total_tokens = 0
        estimated_cost = Decimal("0")

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                payload = {
                    "model": model_id,
                    "messages": full_messages,
                    "stream": True,
                    "stream_options": {"include_usage": True},
                }
                if body.temperature is not None:
                    payload["temperature"] = body.temperature
                if body.max_tokens is not None:
                    payload["max_tokens"] = body.max_tokens

                async with client.stream(
                    "POST",
                    api_url,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": auth_header,
                    },
                    json=payload,
                ) as resp:
                    if resp.status_code != 200:
                        try:
                            err_body = json.loads(await resp.aread())
                        except Exception:
                            err_body = None
                        msg = _user_message_from_status(resp.status_code, err_body)
                        yield f"data: {json.dumps({'error': msg})}\n\n"
                        return

                    async for line in resp.aiter_lines():
                        if not line:
                            continue
                        if line.startswith("data: "):
                            data_part = line[6:]
                            if data_part.strip() == "[DONE]":
                                yield "data: [DONE]\n\n"
                                break
                            try:
                                chunk = json.loads(data_part)
                                usage = chunk.get("usage") or {}
                                if usage:
                                    prompt_tokens = int(usage.get("prompt_tokens") or prompt_tokens or 0)
                                    completion_tokens = int(usage.get("completion_tokens") or completion_tokens or 0)
                                    total_tokens = int(usage.get("total_tokens") or total_tokens or 0)
                                    raw_cost = usage.get("estimated_cost")
                                    if raw_cost is None:
                                        raw_cost = usage.get("cost")
                                    if raw_cost is not None:
                                        estimated_cost = Decimal(str(raw_cost))
                                choices = chunk.get("choices", [])
                                if choices:
                                    content = choices[0].get("delta", {}).get("content", "")
                                    if content:
                                        yield f"data: {json.dumps({'content': content})}\n\n"
                            except json.JSONDecodeError:
                                continue
            db = getattr(request.app.state, "db", None)
            if db and hasattr(db, "llm_usage_logs"):
                await db.llm_usage_logs.create(
                    user_id=user.user_id,
                    model=model_id,
                    provider=provider,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                    estimated_cost=estimated_cost,
                    currency="USD",
                    request_id=request_id,
                )

        except httpx.TimeoutException:
            logger.error("LLM API timeout: %s", api_url)
            yield f"data: {json.dumps({'error': 'Request timeout'})}\n\n"
        except httpx.ConnectError as e:
            logger.error("LLM API connection error: %s", e)
            if settings.FRONTEND_STUB_MODE and base_url:
                yield f"data: {json.dumps({'content': '⚠️ **Stub Mode**: LLM service unreachable. Check network/DNS or set `LLM_SERVICE_URL` to a reachable endpoint.'})}\n\n"
                yield "data: [DONE]\n\n"
            else:
                yield f"data: {json.dumps({'error': 'LLM service unavailable. Ensure llm-service is running (LLM_SERVICE_URL).'})}\n\n"
        except Exception as e:
            logger.error("LLM API error: %s", e)
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
