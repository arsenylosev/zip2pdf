"""
VM billing helpers: resource spec model and k8s-to-spec parser.

The billing loop uses these to compute per-minute costs from live k8s state.
"""

from __future__ import annotations

import re
from pydantic import BaseModel


class VMBillingSpec(BaseModel):
    """Billable resource snapshot for a single VM, parsed from k8s."""
    vm_name: str
    namespace: str
    user_id: int | None = None
    cpu: int
    memory_gb: float
    gpu_count: int = 0
    gpu_model: str | None = None


_MEM_PATTERN = re.compile(r"^(\d+(?:\.\d+)?)\s*(Gi|Mi|Ki|G|M|K|Ti)?$", re.IGNORECASE)


def parse_memory_to_gb(raw: str | int | float) -> float:
    """Convert a k8s memory string to GB.  '8Gi' -> 8.0, '512Mi' -> 0.5, etc."""
    if isinstance(raw, (int, float)):
        return float(raw)
    raw = str(raw).strip()
    m = _MEM_PATTERN.match(raw)
    if not m:
        return 0.0
    value = float(m.group(1))
    unit = (m.group(2) or "").upper()
    multipliers = {
        "GI": 1.0, "G": 1.0,
        "MI": 1.0 / 1024, "M": 1.0 / 1024,
        "KI": 1.0 / (1024 * 1024), "K": 1.0 / (1024 * 1024),
        "TI": 1024.0,
    }
    return value * multipliers.get(unit, 1.0)


def vm_billing_spec_from_k8s(
    vm: dict,
    user_id: int | None = None,
) -> VMBillingSpec:
    """Build a VMBillingSpec from a raw k8s VirtualMachine dict."""
    meta = vm.get("metadata", {})
    spec = vm.get("spec", {}).get("template", {}).get("spec", {})
    domain = spec.get("domain", {})

    cpu = domain.get("cpu", {}).get("cores", 1)
    memory_raw = domain.get("resources", {}).get("requests", {}).get("memory", "0Gi")
    memory_gb = parse_memory_to_gb(memory_raw)

    gpu_devices = domain.get("devices", {}).get("gpus", [])

    return VMBillingSpec(
        vm_name=meta.get("name", ""),
        namespace=meta.get("namespace", ""),
        user_id=user_id,
        cpu=int(cpu) if cpu != "N/A" else 0,
        memory_gb=memory_gb,
        gpu_count=len(gpu_devices),
        gpu_model=gpu_devices[0].get("deviceName") if gpu_devices else None,
    )
