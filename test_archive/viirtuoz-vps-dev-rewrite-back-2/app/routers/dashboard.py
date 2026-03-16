"""
Dashboard page and VM list API.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from app.templating import Jinja2Templates

from app.auth.dependencies import SessionUser, get_current_namespace, get_current_user, require_owner
from app.config import (
    NVIDIA_DRIVER_VERSIONS,
    NVIDIA_GPU_RESOURCES_CUSTOM_DRIVER,
    settings,
)
from app.schemas import BalanceTransferRequest
from app.services.llm_auth_client import LLMAuthClient
from app.utils.async_helpers import run_sync
from app.utils.k8s_utils import discover_gpu_resources, list_vms_in_namespace
from app.utils.vm_utils import format_gpu_display_name, resolve_gpu_resource_name

logger = logging.getLogger(__name__)

router = APIRouter(tags=["dashboard"])

templates = Jinja2Templates(directory="app/templates")


def _require_db(request: Request):
    db = getattr(request.app.state, "db", None)
    if not db:
        raise HTTPException(503, "Database not available")
    return db


async def _snapshot_balance(db, user_id: int, source: str, balance: Decimal | float | int) -> None:
    """Best-effort balance snapshot for analytics."""
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
    db, user_id: int, source: str, amount: Decimal, op_type: str, actor_username: str,
) -> None:
    """Best-effort ledger entry for user/admin balance mutation."""
    ops = getattr(db, "balance_operations", None)
    if not ops:
        return
    try:
        await ops.create(
            user_id=user_id,
            source=source,
            amount=amount,
            op_type=op_type,
            admin_username=actor_username,
        )
    except Exception as exc:
        logger.warning(
            "Failed to log %s balance operation for user %s: %s",
            source,
            user_id,
            exc,
        )


@router.get("/", include_in_schema=False)
async def index():
    return RedirectResponse(url="/login")


@router.get("/dashboard", include_in_schema=False)
async def dashboard_redirect(request: Request):
    username = request.session.get("username")
    if username:
        return RedirectResponse(url=f"/{username}/dashboard")
    return RedirectResponse(url="/login")


@router.get("/{username}/api/balance", include_in_schema=False)
async def get_my_balance(
    request: Request,
    username: str,
    user: SessionUser = Depends(require_owner),
):
    """Return current user's main and LLM balance (for sidebar display)."""
    db = getattr(request.app.state, "db", None)
    main_balance = None
    if db:
        target = await db.users.get_by_username(username)
        if target:
            bal = await db.users.get_balance(target.id)
            if bal:
                main_balance = float(bal[0])
    llm_balance = None
    llm_client = LLMAuthClient()
    if llm_client.available():
        llm_uid = await llm_client.get_user_id(username)
        if llm_uid:
            llm_balance = await llm_client.get_balance(llm_uid)
            if llm_balance is not None:
                llm_balance = float(llm_balance)
    return {"main_balance": main_balance, "llm_balance": llm_balance}


@router.post("/{username}/api/balance/transfer", include_in_schema=False)
async def transfer_my_balance(
    request: Request,
    username: str,
    body: BalanceTransferRequest,
    user: SessionUser = Depends(require_owner),
):
    """Transfer funds between own main and LLM balances."""
    db = _require_db(request)
    target = await db.users.get_by_id(user.user_id)
    if not target:
        raise HTTPException(404, "User not found")

    llm_client = LLMAuthClient()
    if not llm_client.available():
        raise HTTPException(503, "LLM auth-service not configured")

    llm_uid = await llm_client.ensure_user(username)
    if not llm_uid:
        raise HTTPException(502, "Could not resolve user in LLM auth-service")

    if body.source == "main" and body.target == "llm":
        bal = await db.users.get_balance(user.user_id)
        if bal is None:
            raise HTTPException(404, "User not found")
        current_balance, version = bal

        amount = current_balance if body.transfer_all else Decimal(str(body.amount))
        if amount <= 0:
            raise HTTPException(400, "Nothing to transfer")
        if current_balance < amount:
            raise HTTPException(400, "Insufficient main balance")

        try:
            new_main, new_version = await db.users.update_balance(user.user_id, -amount, version)
        except ValueError as exc:
            raise HTTPException(400, str(exc))

        new_llm = await llm_client.adjust_balance(llm_uid, amount)
        if new_llm is None:
            await db.users.update_balance(user.user_id, amount, new_version)
            raise HTTPException(502, "LLM auth-service unreachable – transfer rolled back")

        await _snapshot_balance(db, user.user_id, "main", new_main)
        await _snapshot_balance(db, user.user_id, "llm", new_llm)
        await _log_balance_op(db, user.user_id, "main", -amount, "transfer_out", user.username)
        await _log_balance_op(db, user.user_id, "llm", amount, "transfer_in", user.username)
        return {"main_balance": float(new_main), "llm_balance": new_llm}

    if body.source == "llm" and body.target == "main":
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

        bal = await db.users.get_balance(user.user_id)
        if bal is None:
            await llm_client.adjust_balance(llm_uid, amount)
            raise HTTPException(404, "User not found")
        _, version = bal

        try:
            new_main, _ = await db.users.update_balance(user.user_id, amount, version)
        except ValueError:
            await llm_client.adjust_balance(llm_uid, amount)
            raise HTTPException(500, "Local balance update failed – transfer rolled back")

        await _snapshot_balance(db, user.user_id, "llm", new_llm)
        await _snapshot_balance(db, user.user_id, "main", new_main)
        await _log_balance_op(db, user.user_id, "llm", -amount, "transfer_out", user.username)
        await _log_balance_op(db, user.user_id, "main", amount, "transfer_in", user.username)
        return {"main_balance": float(new_main), "llm_balance": new_llm}

    raise HTTPException(400, "Invalid transfer direction")


@router.get("/{username}/dashboard", include_in_schema=False)
async def dashboard(
    request: Request,
    username: str,
    user: SessionUser = Depends(get_current_user),
    user_ns: str = Depends(get_current_namespace),
):
    if user.username != username:
        return RedirectResponse(url="/login")

    return templates.TemplateResponse("dashboard_home.html", {
        "request": request,
        "username": user.username,
        "namespace": user_ns,
        "is_admin": user.is_admin,
        "page": "dashboard",
    })


@router.get("/{username}/vms", include_in_schema=False)
async def vms_page(
    request: Request,
    username: str,
    user: SessionUser = Depends(get_current_user),
    user_ns: str = Depends(get_current_namespace),
):
    if user.username != username:
        return RedirectResponse(url="/login")

    vms = await run_sync(list_vms_in_namespace, user_ns)

    discovered = await run_sync(discover_gpu_resources)
    default_gpu = resolve_gpu_resource_name()
    gpu_resources = sorted(
        set(discovered or [default_gpu])
        | set(NVIDIA_GPU_RESOURCES_CUSTOM_DRIVER)
    ) or [default_gpu]
    gpu_labels = {res: format_gpu_display_name(res) for res in gpu_resources}
    if default_gpu not in gpu_labels:
        gpu_labels[default_gpu] = format_gpu_display_name(default_gpu)

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "username": user.username,
        "namespace": user_ns,
        "is_admin": user.is_admin,
        "page": "vms",
        "vms": vms,
        "gpu_resources": gpu_resources,
        "gpu_resources_custom_driver": NVIDIA_GPU_RESOURCES_CUSTOM_DRIVER,
        "default_gpu_resource": default_gpu,
        "gpu_labels": gpu_labels,
        "nvidia_driver_versions": NVIDIA_DRIVER_VERSIONS,
        "default_nvidia_driver": settings.DEFAULT_NVIDIA_DRIVER,
        "max_cpu_cores": settings.MAX_CPU_CORES,
        "max_memory_gb": settings.MAX_MEMORY_GB,
        "max_storage_gb": settings.MAX_STORAGE_GB,
        "max_gpu_count": settings.MAX_GPU_COUNT,
    })


@router.get("/{username}/dashboard/vms")
async def get_dashboard_vms(
    username: str,
    user: SessionUser = Depends(get_current_user),
    user_ns: str = Depends(get_current_namespace),
):
    if user.username != username:
        return {"error": "Unauthorized"}, 401

    vms_raw = await run_sync(list_vms_in_namespace, user_ns)

    from app.utils.service_utils import get_vm_allocated_ip

    vm_list = []
    for vm in vms_raw:
        vm_name = vm.get("metadata", {}).get("name", "Unknown")

        dv_st = vm.get("datavolume_status")
        printable = vm.get("status", {}).get("printableStatus") or ""
        if dv_st:
            vm_status = "Provisioning"
            running = False
        elif printable in ("WaitingForVolumeBinding", "WaitingForDataVolume"):
            vm_status = "Provisioning"
            running = False
        elif printable:
            vm_status = printable
            running = vm_status == "Running"
        else:
            vm_status = "Unknown"
            running = False

        spec = vm.get("spec", {}).get("template", {}).get("spec", {})
        domain = spec.get("domain", {})
        resources = domain.get("resources", {}).get("requests", {})
        cpu = domain.get("cpu", {}).get("cores")
        memory = resources.get("memory")

        gpu_devices = domain.get("devices", {}).get("gpus", [])
        gpu_count = len(gpu_devices)
        gpu_model = gpu_devices[0].get("deviceName", "") if gpu_devices else None

        vm_data: dict = {
            "name": vm_name,
            "status": vm_status,
            "running": running,
            "cpu": cpu,
            "memory": memory,
        }
        if gpu_count > 0:
            vm_data["gpu_count"] = gpu_count
            vm_data["gpu_model"] = gpu_model

        vm_os_type = (
            vm.get("metadata", {}).get("labels", {}).get("vm.kubevirt.io/os", "linux")
        )
        vm_data["os"] = vm_os_type

        allocated_ip = await run_sync(get_vm_allocated_ip, user_ns, vm_name)
        if allocated_ip:
            vm_data["allocated_ip"] = allocated_ip

        vm_list.append(vm_data)

    return {"success": True, "vms": vm_list, "stub_mode": settings.FRONTEND_STUB_MODE}


@router.get("/{username}/spend", include_in_schema=False)
async def my_spend_page(
    request: Request,
    username: str,
    user: SessionUser = Depends(require_owner),
):
    """User spend dashboard (own data only)."""
    db = getattr(request.app.state, "db", None)
    summary = {
        "days": 30,
        "total_cost": 0.0,
        "total_vm_cost": 0.0,
        "total_tokens": 0,
        "per_user": [{"username": user.username, "total_cost": 0.0, "vm_total_cost": 0.0}],
        "per_model": [],
        "per_day": [],
    }
    if db:
        if hasattr(db, "balance_snapshots"):
            summary = await db.balance_snapshots.summary_llm_spend(days=30, user_id=user.user_id)
        elif hasattr(db, "llm_usage_logs"):
            legacy = await db.llm_usage_logs.summary(days=30)
            own = next((r for r in legacy.get("per_user", []) if r.get("username") == user.username), None)
            summary = {
                "days": 30,
                "total_cost": float((own or {}).get("total_cost", 0.0)),
                "total_vm_cost": 0.0,
                "total_tokens": 0,
                "per_user": [{
                    "username": user.username,
                    "total_cost": float((own or {}).get("total_cost", 0.0)),
                    "vm_total_cost": 0.0,
                }],
                "per_model": [],
                "per_day": [],
            }
    return templates.TemplateResponse("admin_llm_spend.html", {
        "request": request,
        "username": user.username,
        "namespace": user.namespace,
        "is_admin": user.is_admin,
        "page": "spend",
        "summary": summary,
        "spend_title": "Расходы",
        "spend_api_url": f"/{user.username}/api/spend/summary",
        "spend_is_user_view": True,
    })


@router.get("/{username}/api/spend/summary", include_in_schema=False)
async def my_spend_summary(
    request: Request,
    username: str,
    days: int = Query(default=30, ge=1, le=365),
    user: SessionUser = Depends(require_owner),
):
    """Return user spend summary (own data only)."""
    db = getattr(request.app.state, "db", None)
    if not db:
        raise HTTPException(503, "Database not available")
    if hasattr(db, "balance_snapshots"):
        return await db.balance_snapshots.summary_llm_spend(days=days, user_id=user.user_id)
    if hasattr(db, "llm_usage_logs"):
        legacy = await db.llm_usage_logs.summary(days=days)
        own = next((r for r in legacy.get("per_user", []) if r.get("username") == user.username), None)
        return {
            "days": days,
            "total_cost": float((own or {}).get("total_cost", 0.0)),
            "total_vm_cost": 0.0,
            "total_tokens": 0,
            "per_user": [{
                "username": user.username,
                "total_cost": float((own or {}).get("total_cost", 0.0)),
                "vm_total_cost": 0.0,
            }],
            "per_model": [],
            "per_day": [],
        }
    return {
        "days": days,
        "total_cost": 0.0,
        "total_vm_cost": 0.0,
        "total_tokens": 0,
        "per_user": [],
        "per_model": [],
        "per_day": [],
    }
