"""
DataVolume storage management routes.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from app.auth.dependencies import SessionUser, get_current_namespace, require_owner
from app.utils.async_helpers import run_sync
from app.utils.k8s_utils import delete_data_volume, get_custom_api

logger = logging.getLogger(__name__)

router = APIRouter(tags=["storage"])


@router.get("/{username}/api/datavolumes")
async def get_user_datavolumes(
    username: str,
    user: SessionUser = Depends(require_owner),
    user_ns: str = Depends(get_current_namespace),
):
    api = get_custom_api()

    dv_response = await run_sync(
        api.list_namespaced_custom_object,
        "cdi.kubevirt.io", "v1beta1", user_ns, "datavolumes",
    )
    dvs = dv_response.get("items", [])

    vm_response = await run_sync(
        api.list_namespaced_custom_object,
        "kubevirt.io", "v1", user_ns, "virtualmachines",
    )
    vms = vm_response.get("items", [])

    vm_disks_map: dict[str, str] = {}
    for vm in vms:
        for vol in (
            vm.get("spec", {}).get("template", {}).get("spec", {}).get("volumes", [])
        ):
            if "persistentVolumeClaim" in vol:
                claim = vol["persistentVolumeClaim"]["claimName"]
                vm_disks_map[claim] = vm["metadata"]["name"]

    result = []
    for dv in dvs:
        phase = dv.get("status", {}).get("phase", "Unknown")
        progress = dv.get("status", {}).get("progress", "N/A")
        pvc_name = dv["metadata"]["name"]
        result.append({
            "name": dv["metadata"]["name"],
            "phase": phase,
            "progress": progress,
            "size": dv["spec"]["pvc"]["resources"]["requests"]["storage"],
            "pvc_name": pvc_name,
            "vm_name": vm_disks_map.get(pvc_name),
        })
    return result


@router.delete("/{username}/api/datavolumes/{name}")
async def delete_user_datavolume(
    username: str,
    name: str,
    user: SessionUser = Depends(require_owner),
    user_ns: str = Depends(get_current_namespace),
):
    ok, err = await run_sync(delete_data_volume, user_ns, name)
    if not ok:
        raise HTTPException(500, err)
    return {"success": True}
