"""Admin router: user management, VM control, and balance management (admin only)."""

from __future__ import annotations

import logging
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from app.templating import Jinja2Templates

from app.auth.dependencies import SessionUser, get_user_namespace, require_admin
from app.config import settings
from app.schemas import (
    BalanceTransferRequest,
    BalanceUpdateRequest,
    CreateUserRequest,
    SetRoleRequest,
    UserPublic,
)
from app.services.llm_auth_client import LLMAuthClient
from app.utils.async_helpers import run_sync
from app.utils.k8s_utils import (
    delete_virtual_machine,
    list_vms_in_namespace,
    stop_virtual_machine,
)
from app.utils.service_utils import get_vm_allocated_ip

logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin"], prefix="/admin")
templates = Jinja2Templates(directory="app/templates")


@router.get("", include_in_schema=False)
async def admin_page(
    request: Request,
    user: SessionUser = Depends(require_admin),
):
    """Admin dashboard - redirect to users list."""
    return HTMLResponse("<script>location.href='/admin/users';</script>")


def _stub_users(current_username: str) -> list:
    """Stub user list when DB unavailable (e.g. stub mode)."""
    return [
        {"id": 1, "username": current_username, "role": "admin", "is_active": True, "main_balance": None, "llm_balance": None},
    ]


@router.get("/users", include_in_schema=False)
async def admin_users_page(
    request: Request,
    user: SessionUser = Depends(require_admin),
):
    """User management page."""
    db = getattr(request.app.state, "db", None)
    if not db:
        if settings.FRONTEND_STUB_MODE:
            user_list = _stub_users(user.username)
        else:
            raise HTTPException(503, "Database not available")
    else:
        users = await db.users.list_all(include_inactive=True)
        llm_client = LLMAuthClient()
        llm_available = llm_client.available()

        user_list = []
        for u in users:
            entry = {
                "id": u.id,
                "username": u.username,
                "role": u.role,
                "is_active": u.is_active,
                "main_balance": float(u.balance),
                "llm_balance": None,
            }
            if llm_available:
                llm_uid = await llm_client.get_user_id(u.username)
                if llm_uid:
                    entry["llm_balance"] = await llm_client.get_balance(llm_uid)
            user_list.append(entry)

    return templates.TemplateResponse("admin_users.html", {
        "request": request,
        "username": user.username,
        "namespace": user.namespace,
        "is_admin": user.is_admin,
        "users": user_list,
        "has_db": db is not None,
    })


@router.get("/llm-spend", include_in_schema=False)
async def admin_llm_spend_page(
    request: Request,
    user: SessionUser = Depends(require_admin),
):
    """Admin spend dashboard page."""
    db = getattr(request.app.state, "db", None)
    summary = {
        "days": 30,
        "total_cost": 0.0,
        "total_vm_cost": 0.0,
        "total_tokens": 0,
        "per_user": [],
        "per_model": [],
        "per_day": [],
    }
    if db:
        if hasattr(db, "balance_snapshots"):
            summary = await db.balance_snapshots.summary_llm_spend(days=30)
        elif hasattr(db, "llm_usage_logs"):
            summary = await db.llm_usage_logs.summary(days=30)
    return templates.TemplateResponse("admin_llm_spend.html", {
        "request": request,
        "username": user.username,
        "namespace": user.namespace,
        "is_admin": user.is_admin,
        "page": "spend",
        "summary": summary,
        "spend_title": "Расходы",
        "spend_api_url": "/admin/api/llm-spend/summary",
        "spend_is_user_view": False,
    })


@router.get("/api/users")
async def list_users(
    request: Request,
    user: SessionUser = Depends(require_admin),
):
    """List all users with main and LLM balances."""
    db = getattr(request.app.state, "db", None)
    if not db:
        if settings.FRONTEND_STUB_MODE:
            return {"users": _stub_users(user.username)}
        raise HTTPException(503, "Database not available")

    users = await db.users.list_all(include_inactive=True)
    llm_client = LLMAuthClient()
    llm_available = llm_client.available()

    result = []
    for u in users:
        entry: dict = {
            "id": u.id,
            "username": u.username,
            "role": u.role,
            "is_active": u.is_active,
            "main_balance": float(u.balance),
            "llm_balance": None,
            "llm_user_id": None,
        }
        if llm_available:
            llm_uid = await llm_client.get_user_id(u.username)
            if llm_uid:
                entry["llm_user_id"] = llm_uid
                entry["llm_balance"] = await llm_client.get_balance(llm_uid)
        result.append(entry)

    return {"users": result}


@router.get("/api/llm-spend/summary")
async def admin_llm_spend_summary(
    request: Request,
    days: int = Query(default=30, ge=1, le=365),
    user: SessionUser = Depends(require_admin),
):
    """Return aggregated LLM spend stats for admin dashboard."""
    db = getattr(request.app.state, "db", None)
    if not db:
        raise HTTPException(503, "Database not available")
    if hasattr(db, "balance_snapshots"):
        return await db.balance_snapshots.summary_llm_spend(days=days)
    if hasattr(db, "llm_usage_logs"):
        return await db.llm_usage_logs.summary(days=days)
    return {
        "days": days,
        "total_cost": 0.0,
        "total_vm_cost": 0.0,
        "total_tokens": 0,
        "per_user": [],
        "per_model": [],
        "per_day": [],
    }


@router.post("/api/users")
async def create_user(
    request: Request,
    body: CreateUserRequest,
    user: SessionUser = Depends(require_admin),
):
    """Create new user. Rejects if username already exists in viirtuoz or in LLM auth-service."""
    import bcrypt

    db = getattr(request.app.state, "db", None)
    if not db:
        raise HTTPException(503, "Database not available")

    existing = await db.users.get_by_username(body.username)
    if existing:
        raise HTTPException(400, "Username already exists")

    llm_client = LLMAuthClient()
    if llm_client.available():
        existing_llm_uid = await llm_client.get_user_id(body.username)
        if existing_llm_uid:
            raise HTTPException(
                400,
                "User with this username already exists in the system (LLM auth)",
            )

    pw_hash = bcrypt.hashpw(body.password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    new_user = await db.users.create_user(body.username, pw_hash, role=body.role)
    logger.info("Admin %s created user %s (role=%s)", user.username, new_user.username, new_user.role)
    return {"id": new_user.id, "username": new_user.username, "role": new_user.role}


@router.patch("/api/users/{user_id}/role")
async def set_user_role(
    request: Request,
    user_id: int,
    body: SetRoleRequest,
    user: SessionUser = Depends(require_admin),
):
    """Change user role."""
    db = getattr(request.app.state, "db", None)
    if not db:
        raise HTTPException(503, "Database not available")

    target = await db.users.get_by_id(user_id)
    if not target:
        raise HTTPException(404, "User not found")

    if target.id == user.user_id and body.role != "admin":
        raise HTTPException(400, "Cannot demote yourself")

    ok = await db.users.set_role(user_id, body.role)
    if not ok:
        raise HTTPException(500, "Failed to update role")
    return {"username": target.username, "role": body.role}


@router.post("/api/users/{user_id}/deactivate")
async def deactivate_user(
    request: Request,
    user_id: int,
    user: SessionUser = Depends(require_admin),
):
    """Deactivate user."""
    db = getattr(request.app.state, "db", None)
    if not db:
        raise HTTPException(503, "Database not available")

    if user_id == user.user_id:
        raise HTTPException(400, "Cannot deactivate yourself")

    target = await db.users.get_by_id(user_id)
    if not target:
        raise HTTPException(404, "User not found")

    ok = await db.users.deactivate(user_id)
    if not ok:
        raise HTTPException(500, "Failed to deactivate")
    return {"username": target.username, "deactivated": True}


# ---------------------------------------------------------------------------
# Admin VM management
# ---------------------------------------------------------------------------

async def _get_target_user_or_stub(db, user_id: int, current_user: SessionUser):
    """Get target user from DB, or use current user in stub mode."""
    if db:
        target = await db.users.get_by_id(user_id)
        if target:
            return target.username, target.id
    if settings.FRONTEND_STUB_MODE and user_id == current_user.user_id:
        return current_user.username, current_user.user_id
    return None, None


@router.get("/api/users/{user_id}/vms")
async def list_user_vms(
    request: Request,
    user_id: int,
    user: SessionUser = Depends(require_admin),
):
    """List VMs for a user (admin only)."""
    db = getattr(request.app.state, "db", None)
    target_username, target_id = await _get_target_user_or_stub(db, user_id, user)
    if not target_username:
        raise HTTPException(404, "User not found")

    try:
        namespace = get_user_namespace(target_username, target_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    vms_raw = await run_sync(list_vms_in_namespace, namespace)

    vm_list = []
    for vm in vms_raw:
        vm_name = vm.get("metadata", {}).get("name", "Unknown")
        if vm.get("datavolume_status"):
            vm_status = vm["datavolume_status"]
            running = False
        elif vm.get("status", {}).get("printableStatus"):
            vm_status = vm["status"]["printableStatus"]
            running = vm_status == "Running"
        else:
            vm_status = "Unknown"
            running = False

        spec = vm.get("spec", {}).get("template", {}).get("spec", {})
        domain = spec.get("domain", {})
        cpu = domain.get("cpu", {}).get("cores")
        memory = domain.get("resources", {}).get("requests", {}).get("memory")

        gpu_devices = domain.get("devices", {}).get("gpus", [])
        gpu_count = len(gpu_devices)
        gpu_model = gpu_devices[0].get("deviceName", "") if gpu_devices else None

        allocated_ip = await run_sync(get_vm_allocated_ip, namespace, vm_name)

        vm_list.append({
            "name": vm_name,
            "status": vm_status,
            "running": running,
            "cpu": cpu,
            "memory": memory,
            "gpu_count": gpu_count,
            "gpu_model": gpu_model,
            "allocated_ip": allocated_ip,
        })

    return {
        "success": True,
        "vms": vm_list,
        "username": target_username,
        "namespace": namespace,
        "stub_mode": settings.FRONTEND_STUB_MODE,
    }


@router.post("/api/users/{user_id}/vm/{vm_name}/stop")
async def admin_stop_vm(
    request: Request,
    user_id: int,
    vm_name: str,
    user: SessionUser = Depends(require_admin),
):
    """Stop user's VM (admin only)."""
    db = getattr(request.app.state, "db", None)
    target_username, target_id = await _get_target_user_or_stub(db, user_id, user)
    if not target_username:
        raise HTTPException(404, "User not found")

    try:
        namespace = get_user_namespace(target_username, target_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    ok = await run_sync(stop_virtual_machine, namespace, vm_name)
    if not ok:
        raise HTTPException(500, "Failed to stop VM")

    if db:
        try:
            await db.vm_records.set_running(namespace, vm_name, False)
        except Exception:
            pass

    logger.info("Admin %s stopped VM %s for user %s", user.username, vm_name, target_username)
    return {"success": True, "message": f"VM {vm_name} stopping"}


@router.post("/api/users/{user_id}/vm/{vm_name}/delete")
async def admin_delete_vm(
    request: Request,
    user_id: int,
    vm_name: str,
    user: SessionUser = Depends(require_admin),
):
    """Delete user's VM (admin only)."""
    db = getattr(request.app.state, "db", None)
    target_username, target_id = await _get_target_user_or_stub(db, user_id, user)
    if not target_username:
        raise HTTPException(404, "User not found")

    try:
        namespace = get_user_namespace(target_username, target_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    ok = await run_sync(delete_virtual_machine, namespace, vm_name)
    if not ok:
        raise HTTPException(500, "Failed to delete VM")

    try:
        from app.utils.service_utils import delete_vm_service
        await run_sync(delete_vm_service, namespace, vm_name)
    except Exception as e:
        logger.warning("Service cleanup failed for %s: %s", vm_name, e)

    if db:
        try:
            await db.vm_records.set_running(namespace, vm_name, False)
            await db.vm_records.mark_deleted(namespace, vm_name)
        except Exception:
            pass

    logger.info("Admin %s deleted VM %s for user %s", user.username, vm_name, target_username)
    return {"success": True, "message": f"VM {vm_name} deleted"}


# ---------------------------------------------------------------------------
# Balance management
# ---------------------------------------------------------------------------

def _require_db(request: Request):
    db = getattr(request.app.state, "db", None)
    if not db:
        raise HTTPException(503, "Database not available")
    return db


async def _snapshot_balance(db, user_id: int, source: str, balance: Decimal | float | int) -> None:
    """Best-effort balance snapshot for dashboard analytics."""
    snapshots = getattr(db, "balance_snapshots", None)
    if not snapshots:
        return
    try:
        await snapshots.create(user_id=user_id, source=source, balance=balance)
    except Exception as exc:
        logger.warning(
            "Failed to write %s balance snapshot for user %s: %s",
            source,
            user_id,
            exc,
        )


async def _log_balance_op(
    db, user_id: int, source: str, amount: Decimal, op_type: str, admin_username: str,
) -> None:
    """Best-effort ledger entry for an admin balance mutation."""
    ops = getattr(db, "balance_operations", None)
    if not ops:
        return
    try:
        await ops.create(
            user_id=user_id, source=source, amount=amount,
            op_type=op_type, admin_username=admin_username,
        )
    except Exception as exc:
        logger.warning(
            "Failed to log %s balance operation for user %s: %s",
            source, user_id, exc,
        )


@router.get("/api/users/{user_id}/balance")
async def get_user_balance(
    request: Request,
    user_id: int,
    admin: SessionUser = Depends(require_admin),
):
    """Get both main and LLM balances for a user, plus cumulative admin-administered totals."""
    db = _require_db(request)
    target = await db.users.get_by_id(user_id)
    if not target:
        raise HTTPException(404, "User not found")

    result: dict = {
        "username": target.username,
        "main_balance": float(target.balance),
        "llm_balance": None,
        "llm_user_id": None,
        "main_total_administered": 0.0,
        "llm_total_administered": 0.0,
    }

    ops = getattr(db, "balance_operations", None)
    if ops:
        result["main_total_administered"] = float(
            await ops.get_cumulative(user_id, "main")
        )
        result["llm_total_administered"] = float(
            await ops.get_cumulative(user_id, "llm")
        )

    llm_client = LLMAuthClient()
    if llm_client.available():
        llm_uid = await llm_client.get_user_id(target.username)
        if llm_uid:
            result["llm_user_id"] = llm_uid
            result["llm_balance"] = await llm_client.get_balance(llm_uid)

    result["create_token_available"] = llm_client.create_token_available()
    return result


@router.post("/api/users/{user_id}/llm-token")
async def create_llm_token(
    request: Request,
    user_id: int,
    admin: SessionUser = Depends(require_admin),
):
    """Create SK token for user via auth-service. Returns token (show once)."""
    db = _require_db(request)
    target = await db.users.get_by_id(user_id)
    if not target:
        raise HTTPException(404, "User not found")
    llm_client = LLMAuthClient()
    if not llm_client.available():
        raise HTTPException(503, "LLM auth-service not configured")
    token = await llm_client.create_token(target.username)
    if not token:
        raise HTTPException(502, "Auth-service create-token failed")
    return {"sk_token": token, "username": target.username}


@router.post("/api/users/{user_id}/balance/main")
async def topup_main_balance(
    request: Request,
    user_id: int,
    body: BalanceUpdateRequest,
    admin: SessionUser = Depends(require_admin),
):
    """Admin top-up of a user's main (VM) balance."""
    db = _require_db(request)
    bal = await db.users.get_balance(user_id)
    if bal is None:
        raise HTTPException(404, "User not found")

    current_balance, version = bal
    amount = Decimal(str(body.amount))
    try:
        new_balance, _ = await db.users.update_balance(user_id, amount, version)
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    await _snapshot_balance(db, user_id, "main", new_balance)
    await _log_balance_op(db, user_id, "main", amount, "topup", admin.username)

    logger.info(
        "Admin %s topped up main balance for user %d: +%s (now %s)",
        admin.username, user_id, amount, new_balance,
    )
    return {"main_balance": float(new_balance)}


@router.post("/api/users/{user_id}/balance/llm")
async def topup_llm_balance(
    request: Request,
    user_id: int,
    body: BalanceUpdateRequest,
    admin: SessionUser = Depends(require_admin),
):
    """Admin top-up of a user's LLM balance (calls auth-service)."""
    db = _require_db(request)
    target = await db.users.get_by_id(user_id)
    if not target:
        raise HTTPException(404, "User not found")

    llm_client = LLMAuthClient()
    if not llm_client.available():
        raise HTTPException(503, "LLM auth-service not configured")

    llm_uid = await llm_client.ensure_user(target.username)
    if not llm_uid:
        raise HTTPException(502, "Could not resolve user in LLM auth-service")

    amount = Decimal(str(body.amount))
    new_llm = await llm_client.adjust_balance(llm_uid, amount)
    if new_llm is None:
        raise HTTPException(502, "LLM auth-service balance update failed")

    await _snapshot_balance(db, user_id, "llm", new_llm)
    await _log_balance_op(db, user_id, "llm", amount, "topup", admin.username)

    logger.info(
        "Admin %s topped up LLM balance for user %s: +%s (now %s)",
        admin.username, target.username, amount, new_llm,
    )
    return {"llm_balance": new_llm}


@router.post("/api/users/{user_id}/balance/transfer")
async def transfer_balance(
    request: Request,
    user_id: int,
    body: BalanceTransferRequest,
    admin: SessionUser = Depends(require_admin),
):
    """Transfer funds between main and LLM balances.

    Set ``transfer_all: true`` to move the entire source balance.
    Deducts from source first, then credits destination.
    Rolls back on failure to avoid creating money out of thin air.
    """
    db = _require_db(request)
    target = await db.users.get_by_id(user_id)
    if not target:
        raise HTTPException(404, "User not found")

    llm_client = LLMAuthClient()
    if not llm_client.available():
        raise HTTPException(503, "LLM auth-service not configured")

    llm_uid = await llm_client.ensure_user(target.username)
    if not llm_uid:
        raise HTTPException(502, "Could not resolve user in LLM auth-service")

    if body.source == "main" and body.target == "llm":
        bal = await db.users.get_balance(user_id)
        if bal is None:
            raise HTTPException(404, "User not found")
        current_balance, version = bal

        amount = current_balance if body.transfer_all else Decimal(str(body.amount))
        if amount <= 0:
            raise HTTPException(400, "Nothing to transfer")
        if current_balance < amount:
            raise HTTPException(400, "Insufficient main balance")

        try:
            new_main, new_version = await db.users.update_balance(user_id, -amount, version)
        except ValueError as exc:
            raise HTTPException(400, str(exc))

        new_llm = await llm_client.adjust_balance(llm_uid, amount)
        if new_llm is None:
            await db.users.update_balance(user_id, amount, new_version)
            raise HTTPException(502, "LLM auth-service unreachable – transfer rolled back")

        logger.info(
            "Admin %s transferred %s from main->llm for user %s",
            admin.username, amount, target.username,
        )
        await _snapshot_balance(db, user_id, "main", new_main)
        await _snapshot_balance(db, user_id, "llm", new_llm)
        await _log_balance_op(db, user_id, "main", -amount, "transfer_out", admin.username)
        await _log_balance_op(db, user_id, "llm", amount, "transfer_in", admin.username)
        return {"main_balance": float(new_main), "llm_balance": new_llm}

    elif body.source == "llm" and body.target == "main":
        current_llm = await llm_client.get_balance(llm_uid)
        if current_llm is None:
            raise HTTPException(502, "Could not read LLM balance")

        amount = Decimal(str(current_llm)) if body.transfer_all else Decimal(str(body.amount))
        if amount <= 0:
            raise HTTPException(400, "Nothing to transfer")
        if current_llm < float(amount):
            raise HTTPException(400, "Insufficient LLM balance")

        new_llm = await llm_client.adjust_balance(llm_uid, -amount)
        if new_llm is None:
            raise HTTPException(502, "LLM auth-service deduction failed")

        bal = await db.users.get_balance(user_id)
        if bal is None:
            await llm_client.adjust_balance(llm_uid, amount)
            raise HTTPException(404, "User not found")
        _, version = bal

        try:
            new_main, _ = await db.users.update_balance(user_id, amount, version)
        except ValueError:
            await llm_client.adjust_balance(llm_uid, amount)
            raise HTTPException(500, "Local balance update failed – transfer rolled back")

        logger.info(
            "Admin %s transferred %s from llm->main for user %s",
            admin.username, amount, target.username,
        )
        await _snapshot_balance(db, user_id, "llm", new_llm)
        await _snapshot_balance(db, user_id, "main", new_main)
        await _log_balance_op(db, user_id, "llm", -amount, "transfer_out", admin.username)
        await _log_balance_op(db, user_id, "main", amount, "transfer_in", admin.username)
        return {"main_balance": float(new_main), "llm_balance": new_llm}

    raise HTTPException(400, "Invalid transfer direction")
