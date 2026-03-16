"""
VM details page, VM info API, and service (port) management.

Replaces ``routes/vm_details_routes.py``.  The old subprocess-based
cloud-init status check has been replaced with ``console_utils``.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from app.templating import Jinja2Templates

from app.auth.dependencies import SessionUser, get_current_namespace, require_owner
from app.config import JUNIPER_EXTERNAL_IP, settings
from app.schemas import CreateServiceRequest, ServicePortInfo, VMInfoResponse
from app.utils.async_helpers import run_sync
from app.utils.console_utils import get_cloudinit_status
from app.utils.k8s_utils import (
    get_custom_api,
    get_datavolume_status_for_vm,
    get_vm_details,
    get_vm_username,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["vm-details"])

templates = Jinja2Templates(directory="app/templates")


# ---------------------------------------------------------------------------
# VM Details page (SSR)
# ---------------------------------------------------------------------------

@router.get("/{username}/vm/{vm_name}", include_in_schema=False)
async def vm_details_page(
    request: Request,
    username: str,
    vm_name: str,
    user: SessionUser = Depends(require_owner),
    user_ns: str = Depends(get_current_namespace),
):
    vm = await run_sync(get_vm_details, user_ns, vm_name)
    vm_os = (
        vm.get("metadata", {}).get("labels", {}).get("vm.kubevirt.io/os", "linux")
        if vm else "linux"
    )
    llm_model_display = (
        settings.LLM_MODEL.split("/")[-1] if "/" in settings.LLM_MODEL else settings.LLM_MODEL
    )
    return templates.TemplateResponse("vm_details.html", {
        "request": request,
        "username": username,
        "namespace": user_ns,
        "is_admin": user.is_admin,
        "vm_name": vm_name,
        "vm_os": vm_os,
        "llm_model": llm_model_display,
    })


# ---------------------------------------------------------------------------
# VM Info JSON API
# ---------------------------------------------------------------------------

@router.get("/{username}/vm/{vm_name}/info")
async def vm_info(
    username: str,
    vm_name: str,
    user: SessionUser = Depends(require_owner),
    user_ns: str = Depends(get_current_namespace),
):
    vm = await run_sync(get_vm_details, user_ns, vm_name)
    if not vm:
        raise HTTPException(404, "VM not found")

    from app.utils.service_utils import get_vm_ssh_service

    ssh_exists, ssh_node_port = await run_sync(get_vm_ssh_service, user_ns, vm_name)

    vm_status = vm.get("status", {}).get("printableStatus", "Unknown")

    dv_status = await run_sync(get_datavolume_status_for_vm, user_ns, vm)
    if dv_status:
        vm_status = "Provisioning"
    elif vm_status in ("WaitingForVolumeBinding", "WaitingForDataVolume"):
        vm_status = "Provisioning"

    running = vm_status.lower() == "running"

    spec = vm.get("spec", {}).get("template", {}).get("spec", {})
    domain = spec.get("domain", {})
    resources = domain.get("resources", {}).get("requests", {})
    cpu = domain.get("cpu", {}).get("cores", "N/A")
    memory = resources.get("memory", "N/A")

    gpu_devices = domain.get("devices", {}).get("gpus", [])
    gpu_count = len(gpu_devices)
    gpu_model = gpu_devices[0].get("deviceName", "Unknown") if gpu_devices else None

    volumes = spec.get("volumes", [])
    disks_info = []
    for vol in volumes:
        if "dataVolume" in vol:
            disks_info.append(vol["dataVolume"]["name"])
        elif "persistentVolumeClaim" in vol:
            disks_info.append(vol["persistentVolumeClaim"]["claimName"])
    storage = ", ".join(disks_info) if disks_info else "N/A"

    # Cloud-init status (replaces the old subprocess.run kubectl calls)
    cloudinit_status = None
    cloudinit_message = ""

    if running:
        try:
            api = get_custom_api()
            vmi = await run_sync(
                api.get_namespaced_custom_object,
                "kubevirt.io", "v1", user_ns, "virtualmachineinstances", vm_name,
            )
            conditions = vmi.get("status", {}).get("conditions", [])
            agent_connected = any(
                c.get("type") == "AgentConnected" and c.get("status") == "True"
                for c in conditions
            )
            vm_ready = any(
                c.get("type") == "Ready" and c.get("status") == "True"
                for c in conditions
            )

            vm_os_type = (
                vm.get("metadata", {}).get("labels", {}).get("vm.kubevirt.io/os", "linux")
            )
            is_windows = "windows" in vm_os_type.lower()

            finished, _ = await get_cloudinit_status(user_ns, vm_name, is_windows)

            if finished:
                cloudinit_status = "completed"
                cloudinit_message = "Готова к работе"
            elif agent_connected:
                cloudinit_status = "running"
                cloudinit_message = "Инициализация..."
            elif vm_ready:
                cloudinit_status = "running"
                cloudinit_message = "Загрузка..."
        except Exception as e:
            logger.debug("Could not get VMI conditions: %s", e)

    vm_user = "ubuntu"
    if ssh_exists:
        vm_user = await run_sync(get_vm_username, user_ns, vm_name)

    from app.utils.service_utils import get_vm_allocated_ip

    allocated_ip = await run_sync(get_vm_allocated_ip, user_ns, vm_name)

    result: dict = {
        "success": True,
        "status": vm_status,
        "cpu": str(cpu),
        "memory": memory,
        "storage": storage,
        "running": running,
        "cloudinit_status": cloudinit_status,
        "cloudinit_message": cloudinit_message,
        "datavolume_status": dv_status,
        "allocated_ip": allocated_ip,
        "ssh_service": {
            "exists": ssh_exists,
            "node_port": ssh_node_port,
            "public_ip": allocated_ip if ssh_exists else JUNIPER_EXTERNAL_IP,
            "command": (
                f"ssh {vm_user}@{allocated_ip} -p {ssh_node_port}"
                if ssh_exists and allocated_ip else None
            ),
        },
    }
    if gpu_count > 0:
        result["gpu_count"] = gpu_count
        result["gpu_model"] = gpu_model

    return result


# ---------------------------------------------------------------------------
# SSH service shortcut
# ---------------------------------------------------------------------------

@router.post("/{username}/vm/{vm_name}/ssh-service")
async def create_ssh_service(
    username: str,
    vm_name: str,
    user: SessionUser = Depends(require_owner),
    user_ns: str = Depends(get_current_namespace),
):
    from app.utils.k8s_utils import get_vm_username
    from app.utils.service_utils import add_port_to_vm_service, get_vm_allocated_ip

    vm_user = await run_sync(get_vm_username, user_ns, vm_name)
    ok, message, assigned = await run_sync(
        add_port_to_vm_service, user_ns, vm_name, 22, "ssh", None,
    )
    if not ok:
        raise HTTPException(400, message)

    allocated_ip = await run_sync(get_vm_allocated_ip, user_ns, vm_name)
    public_ip = allocated_ip or JUNIPER_EXTERNAL_IP

    return {
        "message": message,
        "nodePort": assigned,
        "publicIp": public_ip,
        "sshCommand": f"ssh {vm_user}@{public_ip} -p {assigned}",
    }


@router.delete("/{username}/vm/{vm_name}/ssh-service")
async def delete_ssh_service(
    username: str,
    vm_name: str,
    user: SessionUser = Depends(require_owner),
    user_ns: str = Depends(get_current_namespace),
):
    from app.utils.service_utils import remove_port_from_vm_service

    ok, msg = await run_sync(remove_port_from_vm_service, user_ns, vm_name, 22)
    if not ok:
        raise HTTPException(400, msg)
    return {"message": msg}


# ---------------------------------------------------------------------------
# Generic service / port management
# ---------------------------------------------------------------------------

@router.get("/{username}/vm/{vm_name}/services")
async def list_services(
    username: str,
    vm_name: str,
    user: SessionUser = Depends(require_owner),
    user_ns: str = Depends(get_current_namespace),
):
    from app.utils.k8s_utils import get_vm_username
    from app.utils.service_utils import get_vm_allocated_ip, list_vm_services

    services = await run_sync(list_vm_services, user_ns, vm_name)
    allocated_ip = await run_sync(get_vm_allocated_ip, user_ns, vm_name)
    public_ip = allocated_ip or JUNIPER_EXTERNAL_IP

    for svc in services:
        if svc.get("name") == "ssh" and svc.get("nodePort"):
            vm_user = await run_sync(get_vm_username, user_ns, vm_name)
            svc["ssh_command"] = f"ssh {vm_user}@{public_ip} -p {svc['nodePort']}"

    return {"services": services}


@router.post("/{username}/vm/{vm_name}/services")
async def create_service(
    username: str,
    vm_name: str,
    body: CreateServiceRequest,
    user: SessionUser = Depends(require_owner),
    user_ns: str = Depends(get_current_namespace),
):
    from app.utils.service_utils import add_port_to_vm_service, get_vm_allocated_ip

    ok, msg, assigned = await run_sync(
        add_port_to_vm_service, user_ns, vm_name, body.port, body.type,
    )
    if not ok:
        raise HTTPException(400, msg)

    allocated_ip = await run_sync(get_vm_allocated_ip, user_ns, vm_name)
    public_ip = allocated_ip or JUNIPER_EXTERNAL_IP

    return {
        "message": msg,
        "port": assigned,
        "nodePort": assigned,
        "target_port": body.port,
        "type": body.type,
        "public_ip": public_ip,
    }


@router.delete("/{username}/vm/{vm_name}/services/{service_type}")
async def delete_service(
    username: str,
    vm_name: str,
    service_type: str,
    user: SessionUser = Depends(require_owner),
    user_ns: str = Depends(get_current_namespace),
):
    from app.utils.service_utils import list_vm_services, remove_port_from_vm_service

    ports = await run_sync(list_vm_services, user_ns, vm_name)
    target_port = None
    for p in ports:
        if p["name"] == service_type:
            target_port = p["port"]
            break
    if target_port is None:
        raise HTTPException(404, f"Port type '{service_type}' not found")

    ok, msg = await run_sync(remove_port_from_vm_service, user_ns, vm_name, target_port)
    if not ok:
        raise HTTPException(400, msg)
    return {"message": msg}
