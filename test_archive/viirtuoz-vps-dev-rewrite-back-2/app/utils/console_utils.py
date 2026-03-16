"""
Replace ``subprocess.run(["kubectl", ...])`` calls with native K8s Python API.

The old ``vm_details_routes.py`` shelled out to ``kubectl`` to:
  1. Find the virt-launcher pod for a VM
  2. Read ``guest-console-log`` container logs to detect cloud-init completion

This module provides the same functionality via the Kubernetes Python client,
wrapped with ``run_sync`` so callers can ``await`` from async context.
"""

from __future__ import annotations

import logging
from typing import Tuple

from app.config import FRONTEND_STUB_MODE
from app.utils.async_helpers import run_sync
from app.utils.k8s_utils import get_core_api

logger = logging.getLogger(__name__)


def _find_launcher_pod_name(namespace: str, vm_name: str) -> str | None:
    """Return the virt-launcher pod name for *vm_name*, or ``None``."""
    if FRONTEND_STUB_MODE:
        return None
    core = get_core_api()
    try:
        pods = core.list_namespaced_pod(
            namespace=namespace,
            label_selector=f"kubevirt.io/domain={vm_name}",
            limit=1,
        )
        if pods.items:
            return pods.items[0].metadata.name
    except Exception as exc:
        logger.debug("Could not find launcher pod for %s: %s", vm_name, exc)
    return None


def _read_guest_console_log(
    namespace: str,
    pod_name: str,
    tail_lines: int = 100,
) -> str:
    """Read the last *tail_lines* lines from the ``guest-console-log`` container."""
    core = get_core_api()
    try:
        return core.read_namespaced_pod_log(
            name=pod_name,
            namespace=namespace,
            container="guest-console-log",
            tail_lines=tail_lines,
        ) or ""
    except Exception as exc:
        logger.debug("Could not read guest-console-log for %s: %s", pod_name, exc)
        return ""


def _detect_cloudinit_finished(console_log: str, is_windows: bool) -> bool:
    """Parse console log output and return whether cloud-init / Cloudbase-Init completed."""
    if not console_log:
        return False

    if is_windows:
        return any(marker in console_log for marker in (
            "Cloudbase-Init complete",
            "Execution of Cloudbase-Init is done",
            "Cloudbase-Init finished",
        ))

    return "Cloud-init v." in console_log and "finished at" in console_log


def get_cloudinit_status_sync(
    namespace: str,
    vm_name: str,
    is_windows: bool = False,
) -> Tuple[bool, str | None]:
    """Synchronous helper that checks cloud-init/cloudbase-init completion.

    Returns ``(finished: bool, console_log: str | None)``.
    """
    pod_name = _find_launcher_pod_name(namespace, vm_name)
    if not pod_name:
        return False, None
    log_text = _read_guest_console_log(namespace, pod_name)
    finished = _detect_cloudinit_finished(log_text, is_windows)
    return finished, log_text


async def get_cloudinit_status(
    namespace: str,
    vm_name: str,
    is_windows: bool = False,
) -> Tuple[bool, str | None]:
    """Async wrapper — calls the sync helper off the event loop."""
    return await run_sync(get_cloudinit_status_sync, namespace, vm_name, is_windows)
