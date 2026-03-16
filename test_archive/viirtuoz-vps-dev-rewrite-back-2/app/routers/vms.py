"""
VM CRUD and lifecycle routes: create, start/stop/restart, delete, pause/unpause.

Replaces the old ``routes/vm_routes.py``.
"""

from __future__ import annotations

import logging
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse

from app.auth.dependencies import (
    SessionUser,
    _get_db,
    get_current_namespace,
    get_current_user,
    require_owner,
)
from app.config import (
    NVIDIA_DRIVER_VERSIONS,
    NVIDIA_GPU_RESOURCES_CUSTOM_DRIVER,
    settings,
)
from app.database import DB
from app.models import VMEventType
from app.schemas import CreateVMRequest, VMActionResponse, VMNameAvailability
from app.utils.async_helpers import run_sync
from app.utils.k8s_utils import (
    create_cloud_init_secret,
    create_data_volume,
    create_virtual_machine,
    delete_data_volume,
    delete_secret,
    delete_virtual_machine,
    ensure_namespace,
    get_vm_details,
    pause_virtual_machine,
    restart_virtual_machine,
    start_virtual_machine,
    stop_virtual_machine,
    unpause_virtual_machine,
    update_secret_owner,
    vm_exists_in_namespace,
)
from app.utils.vm_utils import (
    generate_cloud_init_userdata,
    generate_vm_manifest,
    get_default_username_for_image,
    sanitize_cloud_init_field,
    validate_ssh_key,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["vms"])


async def _require_positive_balance(
    request: Request, user: SessionUser,
) -> None:
    """Reject the request if billing is enabled and the user has no funds.

    Admins are exempt.
    """
    if not settings.BILLING_ENABLED or user.is_admin:
        return
    db = _get_db(request)
    if not db:
        return
    bal = await db.users.get_balance(user.user_id)
    if bal is None:
        return
    current_balance, _ = bal
    if current_balance <= 0:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Insufficient balance to perform this action",
        )


async def _set_running_safe(
    request: Request, namespace: str, vm_name: str, running: bool,
) -> None:
    """Best-effort update of the DB running state."""
    try:
        db = _get_db(request)
        if db:
            await db.vm_records.set_running(namespace, vm_name, running)
    except Exception as exc:
        logger.warning("set_running(%s/%s, %s) failed: %s", namespace, vm_name, running, exc)


# ---------------------------------------------------------------------------
# Create VM
# ---------------------------------------------------------------------------

@router.post("/{username}/create-vm")
async def create_vm(
    request: Request,
    username: str,
    user: SessionUser = Depends(require_owner),
    user_ns: str = Depends(get_current_namespace),
):
    await _require_positive_balance(request, user)

    form = await request.form()
    raw = dict(form)

    if "sshkey" in raw:
        raw["ssh_key"] = raw.pop("sshkey")
    raw.pop("nvidia_custom_driver_installer_type", None)

    for key in ("package_update", "ssh_pwauth"):
        if key in raw:
            raw[key] = raw[key] in ("true", "on", "1", True)

    for key in ("gpu_model", "hostname", "username", "ssh_key", "password",
                "additional_packages", "nvidia_driver_version", "custom_cloudinit"):
        if key in raw and raw[key] == "":
            raw[key] = None

    body = CreateVMRequest(**raw)
    db = _get_db(request)

    is_windows_installer = body.image == "windows-installer"
    is_windows_golden = body.image == "windows-golden-image"

    # --- Cloud-init / Windows parameters ---
    if not is_windows_installer and not is_windows_golden:
        hostname = sanitize_cloud_init_field(body.hostname or body.name, "hostname")
        vm_username = body.username
        if not vm_username:
            vm_username = get_default_username_for_image(body.image)
        vm_username = sanitize_cloud_init_field(vm_username, "username")

        ssh_key = body.ssh_key or ""
        password = body.password or ""
        ssh_pwauth = "true" if body.ssh_pwauth else "false"
        package_update = "true" if body.package_update else "false"
        custom_cloudinit = body.custom_cloudinit or ""

        if not custom_cloudinit:
            has_ssh = bool(ssh_key.strip())
            has_password = ssh_pwauth == "true" and bool(password)
            if not has_ssh and not has_password:
                raise HTTPException(400, "SSH key or password (with ssh_pwauth) required")

        if ssh_key:
            ok, err = validate_ssh_key(ssh_key)
            if not ok:
                raise HTTPException(400, f"SSH key validation: {err}")

        nvidia_driver_version = body.nvidia_driver_version or settings.DEFAULT_NVIDIA_DRIVER
        if (
            body.gpu > 0
            and nvidia_driver_version
            and nvidia_driver_version not in NVIDIA_DRIVER_VERSIONS
        ):
            nvidia_driver_version = settings.DEFAULT_NVIDIA_DRIVER

        import re
        packages_list = None
        if body.additional_packages:
            packages_list = []
            for pkg in body.additional_packages.split():
                pkg = pkg.strip()
                if pkg and re.match(r"^[a-zA-Z0-9._-]+$", pkg):
                    packages_list.append(pkg)
                elif pkg:
                    raise HTTPException(400, f"Invalid package name: {pkg}")

    elif is_windows_installer:
        vm_username = "Administrator"
        hostname = body.name
        ssh_key = None
        password = None
        ssh_pwauth = "false"
        package_update = "false"
        packages_list = None
        custom_cloudinit = None
        nvidia_driver_version = None
    else:
        hostname = sanitize_cloud_init_field(body.hostname or body.name, "hostname")
        vm_username = sanitize_cloud_init_field(body.username or "Administrator", "username")
        password = body.password
        if not password:
            raise HTTPException(400, "Password required for Windows VM")
        ssh_key = None
        ssh_pwauth = "false"
        package_update = "false"
        packages_list = None
        custom_cloudinit = None
        nvidia_driver_version = None

    # --- Ensure namespace ---
    ns_ok = await run_sync(ensure_namespace, user_ns)
    if not ns_ok:
        raise HTTPException(500, f"Failed to ensure namespace: {user_ns}")

    try:
        from app.utils.network_policy_utils import ensure_namespace_network_policy
        await run_sync(ensure_namespace_network_policy, user_ns)
    except Exception as e:
        logger.warning("NetworkPolicy setup failed for %s: %s", user_ns, e)

    gpu_node_selector = (
        {"node-role.kubernetes.io/kubevirt": ""} if body.gpu > 0 else None
    )
    gpu_model = body.gpu_model if body.gpu > 0 else None

    # --- Windows installer flow ---
    if is_windows_installer:
        from app.utils.windows_utils import generate_windows_installer_vm_manifest

        manifest = generate_windows_installer_vm_manifest(
            vm_name=body.name, namespace=user_ns,
            cpu=body.cpu, memory=body.memory, storage=body.storage,
            gpu_model=gpu_model, gpu_count=body.gpu,
            gpu_node_selector=gpu_node_selector,
        )
        ok, err, vm_obj = await run_sync(create_virtual_machine, user_ns, manifest)
        if not ok:
            raise HTTPException(500, f"Windows VM creation failed: {err}")

        await _log_vm_created(db, user, body, user_ns, "windows-installer")
        return RedirectResponse(
            url=f"/{user.username}/vm/{body.name}", status_code=303,
        )

    # --- Windows golden image flow ---
    if is_windows_golden:
        from app.utils.windows_utils import (
            generate_cloudbase_init_userdata,
            generate_windows_vm_from_golden_image,
        )

        cloudbase_userdata = generate_cloudbase_init_userdata(
            hostname=hostname, username=vm_username, password=password,
        )
        secret_name = f"{body.name}-cloudinit"

        ok, err = await run_sync(
            create_cloud_init_secret, user_ns, secret_name, cloudbase_userdata, None,
        )
        if not ok and "уже существует" in err:
            await run_sync(delete_secret, user_ns, secret_name)
            ok, err = await run_sync(
                create_cloud_init_secret, user_ns, secret_name, cloudbase_userdata, None,
            )
        if not ok:
            raise HTTPException(500, f"Cloudbase-Init secret failed: {err}")

        manifest = generate_windows_vm_from_golden_image(
            vm_name=body.name, namespace=user_ns,
            cpu=body.cpu, memory=body.memory, storage=body.storage,
            secret_name=secret_name,
            golden_image_name=settings.WINDOWS_GOLDEN_IMAGE_NAME,
            golden_image_namespace=settings.WINDOWS_GOLDEN_IMAGE_NAMESPACE,
            gpu_model=gpu_model, gpu_count=body.gpu,
            gpu_node_selector=gpu_node_selector, vm_username=vm_username,
        )
        ok, err, vm_obj = await run_sync(create_virtual_machine, user_ns, manifest)
        if not ok:
            await run_sync(delete_secret, user_ns, secret_name)
            raise HTTPException(500, f"Windows VM creation failed: {err}")

        if vm_obj:
            await run_sync(update_secret_owner, user_ns, secret_name, vm_obj)

        await _log_vm_created(db, user, body, user_ns, "windows-golden")
        return RedirectResponse(
            url=f"/{user.username}/vm/{body.name}", status_code=303,
        )

    # --- Regular Linux VM flow ---
    dv_name = f"{body.name}-rootdisk"
    use_custom_nvidia = (
        body.gpu > 0
        and body.gpu_model in NVIDIA_GPU_RESOURCES_CUSTOM_DRIVER
        and settings.APP_INTERNAL_BASE_URL
    )

    ok, err = await run_sync(
        create_data_volume, user_ns, dv_name, body.image,
        f"{body.storage}Gi" if not str(body.storage).endswith("Gi") else str(body.storage),
        settings.STORAGE_CLASS_NAME,
    )
    if not ok:
        raise HTTPException(500, f"DataVolume creation failed: {err}")

    callback_url = None
    callback_token = None
    if use_custom_nvidia and settings.APP_INTERNAL_BASE_URL:
        callback_token = secrets.token_urlsafe(32)
        base = settings.APP_INTERNAL_BASE_URL.strip().rstrip("/")
        if not base.startswith(("http://", "https://")):
            base = f"http://{base}"
        callback_url = (
            f"{base}/{user.username}/vm/{body.name}/"
            f"{settings.NVIDIA_CUSTOM_DRIVER_CALLBACK_PATH}"
            f"?token={callback_token}&namespace={user_ns}"
        )

    try:
        cloud_init_data = generate_cloud_init_userdata(
            hostname, vm_username, ssh_key, package_update, package_update,
            ssh_pwauth, password, custom_cloudinit,
            packages=packages_list, image_url=body.image,
            gpu_count=body.gpu, nvidia_driver_version=nvidia_driver_version,
            gpu_model=gpu_model,
            nvidia_custom_driver_callback_url=callback_url,
            nvidia_custom_driver_installer_type="run" if use_custom_nvidia else "auto",
        )
    except Exception as e:
        await run_sync(delete_data_volume, user_ns, dv_name)
        raise HTTPException(500, f"Cloud-init generation failed: {e}")

    secret_name = f"{body.name}-cloudinit"
    try:
        manifest = generate_vm_manifest(
            body.name, user_ns, body.cpu, body.memory, dv_name, secret_name,
            gpu_model=gpu_model, gpu_count=body.gpu,
            gpu_node_selector=None, vm_username=vm_username,
            nvidia_custom_driver_callback_token=callback_token,
        )
    except Exception as e:
        await run_sync(delete_data_volume, user_ns, dv_name)
        raise HTTPException(500, f"Manifest generation failed: {e}")

    ok, err, vm_obj = await run_sync(create_virtual_machine, user_ns, manifest)
    if not ok:
        await run_sync(delete_data_volume, user_ns, dv_name)
        raise HTTPException(500, f"VM creation failed: {err}")

    ok, err = await run_sync(
        create_cloud_init_secret, user_ns, secret_name, cloud_init_data, vm_obj,
    )
    if not ok and "уже существует" in err:
        await run_sync(delete_secret, user_ns, secret_name)
        ok, err = await run_sync(
            create_cloud_init_secret, user_ns, secret_name, cloud_init_data, vm_obj,
        )
    if not ok:
        logger.warning("VM created but cloud-init secret failed: %s", err)

    await _log_vm_created(db, user, body, user_ns, "linux")
    return RedirectResponse(
        url=f"/{user.username}/vms", status_code=303,
    )


async def _log_vm_created(
    db: DB | None, user: SessionUser, body: CreateVMRequest, namespace: str, os_type: str,
) -> None:
    if not db:
        return
    try:
        await db.vm_records.create(
            user_id=user.user_id, vm_name=body.name, namespace=namespace,
            cpu=body.cpu, memory_gb=body.memory, storage_gb=body.storage,
            image_url=body.image, gpu_count=body.gpu, gpu_model=body.gpu_model,
            os_type=os_type,
        )
        await db.vm_events.log_event(
            vm_name=body.name, namespace=namespace, user_id=user.user_id,
            event_type=VMEventType.CREATED,
            metadata={"cpu": body.cpu, "memory_gb": body.memory, "gpu": body.gpu},
        )
    except Exception as e:
        logger.warning("DB logging failed for VM create: %s", e)


# ---------------------------------------------------------------------------
# VM name availability check
# ---------------------------------------------------------------------------

@router.get("/{username}/check-vm-name/{vm_name}")
async def check_vm_name(
    username: str,
    vm_name: str,
    user: SessionUser = Depends(require_owner),
    user_ns: str = Depends(get_current_namespace),
) -> VMNameAvailability:
    from app.utils.vm_utils import validate_vm_name

    ok, err = validate_vm_name(vm_name)
    if not ok:
        raise HTTPException(400, err or "Invalid VM name")

    exists = await run_sync(vm_exists_in_namespace, user_ns, vm_name)
    return VMNameAvailability(available=not exists, exists=exists)


# ---------------------------------------------------------------------------
# NVIDIA custom driver callback
# ---------------------------------------------------------------------------

# @router.api_route(
#     "/{username}/vm/{vm_name}/{callback_path}",
#     methods=["POST", "GET"],
# )
# async def nvidia_custom_driver_installed(
#     username: str,
#     vm_name: str,
#     callback_path: str,
#     token: str | None = None,
#     namespace: str | None = None,
# ):
#     if callback_path != settings.NVIDIA_CUSTOM_DRIVER_CALLBACK_PATH:
#         raise HTTPException(404)
#     if not token or not namespace:
#         raise HTTPException(400, "Missing token or namespace")
#     if not namespace[0].isalpha():
#         raise HTTPException(400, "Namespace must start with a letter")
#     if "_" in namespace:
#         raise HTTPException(400, "Namespace must not contain underscores")
#     if not namespace.startswith(f"{settings.K8S_NAMESPACE_PREFIX or 'kv'}-"):
#         raise HTTPException(403, "Invalid namespace")

#     vm = await run_sync(get_vm_details, namespace, vm_name)
#     if not vm:
#         raise HTTPException(404, "VM not found")

#     ann = (
#         vm.get("spec", {})
#         .get("template", {})
#         .get("metadata", {})
#         .get("annotations", {})
#     )
#     expected = ann.get(settings.NVIDIA_CUSTOM_DRIVER_ANNOTATION_TOKEN_KEY)
#     if not expected or token != expected:
#         raise HTTPException(403, "Invalid token")

#     logger.info("Custom driver callback OK for %s/%s", namespace, vm_name)
#     return {"success": True}


# ---------------------------------------------------------------------------
# Lifecycle: start / stop / restart / delete / pause / unpause / metrics
# ---------------------------------------------------------------------------

@router.post("/{username}/vm/{vm_name}/start")
async def start_vm(
    request: Request,
    username: str,
    vm_name: str,
    user: SessionUser = Depends(require_owner),
    user_ns: str = Depends(get_current_namespace),
) -> VMActionResponse:
    await _require_positive_balance(request, user)

    ok = await run_sync(start_virtual_machine, user_ns, vm_name)
    if not ok:
        raise HTTPException(500, "Failed to start VM")
    await _set_running_safe(request, user_ns, vm_name, True)
    await _log_lifecycle(request, user, user_ns, vm_name, VMEventType.STARTED)
    return VMActionResponse(success=True, message=f"VM {vm_name} starting")


@router.post("/{username}/vm/{vm_name}/stop")
async def stop_vm(
    request: Request,
    username: str,
    vm_name: str,
    user: SessionUser = Depends(require_owner),
    user_ns: str = Depends(get_current_namespace),
) -> VMActionResponse:
    ok = await run_sync(stop_virtual_machine, user_ns, vm_name)
    if not ok:
        raise HTTPException(500, "Failed to stop VM")
    await _set_running_safe(request, user_ns, vm_name, False)
    await _log_lifecycle(request, user, user_ns, vm_name, VMEventType.STOPPED)
    return VMActionResponse(success=True, message=f"VM {vm_name} stopping")


@router.post("/{username}/vm/{vm_name}/restart")
async def restart_vm(
    request: Request,
    username: str,
    vm_name: str,
    user: SessionUser = Depends(require_owner),
    user_ns: str = Depends(get_current_namespace),
) -> VMActionResponse:
    ok = await run_sync(restart_virtual_machine, user_ns, vm_name)
    if not ok:
        raise HTTPException(500, "Failed to restart VM (must be running)")
    await _set_running_safe(request, user_ns, vm_name, True)
    await _log_lifecycle(request, user, user_ns, vm_name, VMEventType.RESTARTED)
    return VMActionResponse(success=True, message=f"VM {vm_name} restarting")


@router.post("/{username}/vm/{vm_name}/delete")
async def delete_vm_route(
    request: Request,
    username: str,
    vm_name: str,
    user: SessionUser = Depends(require_owner),
    user_ns: str = Depends(get_current_namespace),
) -> VMActionResponse:
    ok = await run_sync(delete_virtual_machine, user_ns, vm_name)
    if not ok:
        raise HTTPException(500, "Failed to delete VM")

    try:
        from app.utils.service_utils import delete_vm_service
        await run_sync(delete_vm_service, user_ns, vm_name)
    except Exception as e:
        logger.warning("Service cleanup failed for %s: %s", vm_name, e)

    try:
        db = _get_db(request)
        if db:
            await db.vm_records.set_running(user_ns, vm_name, False)
            await db.vm_records.mark_deleted(user_ns, vm_name)
    except Exception:
        pass
    await _log_lifecycle(request, user, user_ns, vm_name, VMEventType.DELETED)
    return VMActionResponse(success=True, message=f"VM {vm_name} deleted")


@router.post("/{username}/vm/{vm_name}/pause")
async def pause_vm(
    request: Request,
    username: str,
    vm_name: str,
    user: SessionUser = Depends(require_owner),
    user_ns: str = Depends(get_current_namespace),
) -> VMActionResponse:
    ok = await run_sync(pause_virtual_machine, user_ns, vm_name)
    if not ok:
        raise HTTPException(500, "Failed to pause VM (must be running)")
    await _set_running_safe(request, user_ns, vm_name, False)
    await _log_lifecycle(request, user, user_ns, vm_name, VMEventType.PAUSED)
    return VMActionResponse(success=True, message=f"VM {vm_name} pausing")


@router.post("/{username}/vm/{vm_name}/unpause")
async def unpause_vm(
    request: Request,
    username: str,
    vm_name: str,
    user: SessionUser = Depends(require_owner),
    user_ns: str = Depends(get_current_namespace),
) -> VMActionResponse:
    await _require_positive_balance(request, user)

    ok = await run_sync(unpause_virtual_machine, user_ns, vm_name)
    if not ok:
        raise HTTPException(500, "Failed to unpause VM (must be paused)")
    await _set_running_safe(request, user_ns, vm_name, True)
    await _log_lifecycle(request, user, user_ns, vm_name, VMEventType.UNPAUSED)
    return VMActionResponse(success=True, message=f"VM {vm_name} unpausing")


@router.get("/{username}/vm/{vm_name}/metrics")
async def get_vm_metrics(
    username: str,
    vm_name: str,
    user: SessionUser = Depends(require_owner),
    user_ns: str = Depends(get_current_namespace),
):
    from app.utils.k8s_utils import get_vmi_metrics

    metrics = await run_sync(get_vmi_metrics, user_ns, vm_name)
    return {"success": True, "metrics": metrics}


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

async def _log_lifecycle(
    request: Request,
    user: SessionUser,
    namespace: str,
    vm_name: str,
    event_type: VMEventType,
) -> None:
    try:
        db = _get_db(request)
        if not db:
            return
        await db.vm_events.log_event(
            vm_name=vm_name, namespace=namespace,
            user_id=user.user_id, event_type=event_type,
        )
    except Exception as e:
        logger.debug("Event logging failed: %s", e)
