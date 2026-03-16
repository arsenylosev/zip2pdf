"""
Background billing loop: compute VM costs, deduct from user balances,
stop VMs for users with insufficient funds.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal

from app.config import VMPricing
from app.database import DB
from app.models import VMEventType, VMRecord
from app.utils.async_helpers import run_sync

logger = logging.getLogger(__name__)


async def billing_tick(db: DB, pricing: VMPricing) -> list[int]:
    """One billing pass over all users.

    Returns user_ids whose VMs must be force-stopped (insufficient funds).
    """
    now = datetime.now(timezone.utc)
    kill_user_ids: list[int] = []

    billable_vms = await db.vm_records.get_all_billable()
    if not billable_vms:
        return kill_user_ids

    by_user: dict[int, list[VMRecord]] = {}
    for vm in billable_vms:
        by_user.setdefault(vm.user_id, []).append(vm)

    admin_ids = await _get_admin_ids(db)

    for user_id, vms in by_user.items():
        if user_id in admin_ids:
            for vm in vms:
                await db.vm_records.update_last_billed(vm.id, now)
            continue

        total_cost = Decimal("0")

        for vm in vms:
            minutes = _compute_billable_minutes(vm, now)
            if minutes > 0:
                vm_cost = pricing.cost_per_minute(
                    vm.cpu, vm.memory_gb, vm.gpu_count, vm.gpu_model,
                )
                total_cost += vm_cost * minutes

        if total_cost <= 0:
            continue

        bal = await db.users.get_balance(user_id)
        if bal is None:
            continue
        current_balance, version = bal

        try:
            new_balance, _ = await db.users.update_balance(
                user_id, -total_cost, version,
            )
        except ValueError:
            kill_user_ids.append(user_id)
            continue

        for vm in vms:
            billed_at = now if vm.is_running else (vm.last_stopped_at or now)
            await db.vm_records.update_last_billed(vm.id, billed_at)

        try:
            await db.balance_snapshots.create(user_id, "main", new_balance)
        except Exception as exc:
            logger.warning("Balance snapshot failed for user %d: %s", user_id, exc)

    return kill_user_ids


def _compute_billable_minutes(vm: VMRecord, now: datetime) -> Decimal:
    """Compute billable minutes for a VM since it was last billed."""
    if vm.is_running:
        candidates = [t for t in (vm.last_started_at, vm.last_billed_at) if t is not None]
        start = max(candidates) if candidates else vm.created_at
        elapsed = (now - start).total_seconds()
    elif vm.last_stopped_at and (
        not vm.last_billed_at or vm.last_stopped_at > vm.last_billed_at
    ):
        candidates = [t for t in (vm.last_started_at, vm.last_billed_at) if t is not None]
        start = max(candidates) if candidates else vm.created_at
        elapsed = (vm.last_stopped_at - start).total_seconds()
    else:
        return Decimal("0")

    if elapsed <= 0:
        return Decimal("0")
    return Decimal(str(elapsed)) / 60


async def _get_admin_ids(db: DB) -> set[int]:
    users = await db.users.list_all(include_inactive=False)
    return {u.id for u in users if u.is_admin}


async def stop_all_user_vms(db: DB, user_id: int) -> int:
    """Stop all running VMs for a user (billing enforcement).

    Returns number of VMs stopped.
    """
    from app.utils.k8s_utils import stop_virtual_machine

    active_vms = await db.vm_records.get_active_for_user(user_id)
    stopped = 0

    for vm in active_vms:
        if not vm.is_running:
            continue
        try:
            ok = await run_sync(stop_virtual_machine, vm.namespace, vm.vm_name)
            if ok:
                await db.vm_records.set_running(vm.namespace, vm.vm_name, False)
                stopped += 1
            else:
                logger.warning(
                    "Failed to stop VM %s/%s for billing enforcement",
                    vm.namespace, vm.vm_name,
                )
        except Exception as exc:
            logger.error(
                "Error stopping VM %s/%s for billing: %s",
                vm.namespace, vm.vm_name, exc,
            )

        try:
            await db.vm_events.log_event(
                vm_name=vm.vm_name,
                namespace=vm.namespace,
                user_id=user_id,
                event_type=VMEventType.BILLING_STOPPED,
                metadata={"reason": "insufficient_funds"},
            )
        except Exception as exc:
            logger.warning("Failed to log BILLING_STOPPED event: %s", exc)

    return stopped
