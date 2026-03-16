# Billing feature planning for virtual machines
_Exported on 2/26/2026 at 18:23:34 GMT+3 from Cursor (2.5.20)_

---

**User**

@viirtuoz-vps/app/routers @viirtuoz-vps/app/database.py 

I want you to help me with planning for a feature
It does not involve k8s (almost) so lets do it here right now
1. I want to do billing for vms (lets base cost linearly depending on the resources used 
like cpu, memory, gpu usage, gpu type etc) So we have like a data object with that info and we would have a method for per minute billing 

2. We would have some background process that would track usage and subtract money from the main user balance 
3. When there are no money in the main balance we stop all vms 
4. We track costs atomically so we do it once for all users and if there is not enough money we return smth like stop all vms now!!
And we kill them in the main loop

5. I would also like to have a separate table in db where we would track all of the increases of the balance. I was asked to just track cumulative costs for 2 balances and the easiest way to do that sort of reliably right now is to track how much money we added to the current user 

if you have questions lets discuss (but prioritize them) I cannot handle too many questions at once 

---

**Cursor**

Let me explore the existing codebase first to understand the current data model and architecture before we plan.

Let me also look at the models and VM-related routers to understand the full picture.

Let me also check how the admin router handles balance and look at the schemas.

Good, now I have a solid picture of the codebase. Here's the plan, followed by a couple focused questions.

---

## Plan

### 1. VM Cost Calculator (`app/services/vm_billing.py`)

A pure data/logic module. No DB, no k8s -- just pricing math.

```python
from dataclasses import dataclass
from decimal import Decimal

@dataclass
class VMCostSpec:
    cpu: int
    memory_gb: float
    gpu_count: int
    gpu_model: str | None

    def cost_per_minute(self, pricing: "VMPricing") -> Decimal:
        cost = Decimal(str(self.cpu)) * pricing.cpu_per_minute
        cost += Decimal(str(self.memory_gb)) * pricing.memory_gb_per_minute
        if self.gpu_count > 0 and self.gpu_model:
            gpu_rate = pricing.gpu_rates.get(self.gpu_model, pricing.gpu_default_per_minute)
            cost += Decimal(str(self.gpu_count)) * gpu_rate
        return cost

@dataclass
class VMPricing:
    cpu_per_minute: Decimal
    memory_gb_per_minute: Decimal
    gpu_default_per_minute: Decimal
    gpu_rates: dict[str, Decimal]   # gpu_model -> rate per GPU per minute
```

`VMCostSpec` can be trivially constructed from an existing `VMRecord` or from live k8s VM spec data. The pricing config would come from settings/env vars.

### 2. Background billing loop (in lifespan)

A new `asyncio.Task` launched during the FastAPI lifespan, inside the `async with create_db(...)` block. Rough shape:

```
every BILLING_INTERVAL_SECONDS (e.g. 60):
  1. Fetch all active (non-deleted) VMRecords, grouped by user_id
  2. For each user_id:
     a. Sum cost_per_minute for all their *running* VMs
     b. Multiply by minutes_elapsed (time since last successful tick for this user)
     c. Try to deduct from balance via update_balance()
     d. If insufficient funds → add to kill_list
  3. For each user in kill_list:
     → stop all their VMs via k8s
     → log event (VMEventType, maybe a new BILLING_STOPPED type)
  4. Snapshot balances
```

Key detail: the loop keeps a `last_billed_at: dict[int, datetime]` in memory to compute the actual elapsed interval per user, so if a tick takes longer than 60s or is skipped, we bill correctly for the real elapsed time.

### 3. Insufficient balance → stop VMs

Handled inside step 2d/3 above. The `update_balance` method already rolls back on negative balance and raises `ValueError("Insufficient funds")`. When we catch that:
- We add the user to the kill list
- After processing all users, we iterate the kill list and call `stop_virtual_machine` for each VM
- We log a new event type like `VMEventType.BILLING_STOPPED`

This matches your point 4 -- one pass over all users, collect the kill list, then act on it.

### 4. DB changes

**4a. New table: `balance_topups`**

Tracks every deposit/increase to either balance. One row per top-up event.

```sql
CREATE TABLE IF NOT EXISTS balance_topups (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('main', 'llm')),
    amount NUMERIC(18,9) NOT NULL,
    admin_username TEXT,          -- who performed the top-up (nullable for system)
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

This gets a corresponding `BalanceTopupDB` class with `create()` and `get_cumulative(user_id, source)` methods. The `topup_main_balance` and `topup_llm_balance` admin endpoints would write to this table alongside the existing balance update.

**4b. New `VMEventType` entry**

Add `BILLING_STOPPED = "billing_stopped"` to the enum so we can distinguish "admin stopped the VM" from "billing killed it."

### 5. Where things live (file layout)

| What | Where |
|---|---|
| `VMCostSpec`, `VMPricing` | `app/services/vm_billing.py` |
| `BalanceTopupDB` | `app/database.py` (new class, wired into `DB`) |
| Billing background task | `app/services/billing_loop.py` |
| Task startup | `app/main.py` lifespan (create task, cancel on shutdown) |
| Pricing config values | `app/config.py` / env vars |

The routers don't change much -- the admin top-up endpoints just gain one extra `await db.balance_topups.create(...)` call.

---

## Questions (2, most critical first)

**Q1 -- Billing only running VMs or also paused/stopped?**
Right now `VMRecord` has `deleted_at` but no "running/stopped" status column. The live status comes from k8s. Should we:
- (a) Query k8s for actual running status each billing tick (accurate but adds k8s API calls every minute), or
- (b) Only bill VMs that are in `vm_records` and not deleted, i.e. bill for the existence of a VM regardless of whether it's running? (simpler, like cloud providers billing for allocated resources)

This is the single biggest design fork.

**Q2 -- Pricing values: where should they come from?**
Simplest option is env vars / `settings` (like `VM_BILLING_CPU_PER_MINUTE=0.001`). Alternative is a DB table so an admin can change prices without redeploying. Which do you prefer for now?

---

**User**

q1: Only running (we can also track when was stopped so the user could not run vm for lets say 30s and get away with that) 
q2: for now we will add an extra class in config.py with some defaults (this is an MVP mostly)

---

**Cursor**

Let me quickly check how your config is structured so I can make the pricing config part concrete.

Good. Here's the refined, complete plan with both answers baked in.

---

## Refined Plan

### A. Pricing config -- add to `config.py`

A simple dict in `Settings` that env vars can override, plus a helper dataclass for typed access:

```python
from decimal import Decimal
from dataclasses import dataclass, field

@dataclass
class VMPricing:
    cpu_per_minute: Decimal = Decimal("0.001")
    memory_gb_per_minute: Decimal = Decimal("0.0005")
    gpu_default_per_minute: Decimal = Decimal("0.01")
    gpu_rates: dict[str, Decimal] = field(default_factory=dict)

    def cost_per_minute(self, cpu: int, memory_gb: float, gpu_count: int, gpu_model: str | None) -> Decimal:
        cost = Decimal(str(cpu)) * self.cpu_per_minute
        cost += Decimal(str(memory_gb)) * self.memory_gb_per_minute
        if gpu_count > 0 and gpu_model:
            rate = self.gpu_rates.get(gpu_model, self.gpu_default_per_minute)
            cost += Decimal(str(gpu_count)) * rate
        return cost
```

In `Settings`, add env-overridable fields:

```python
# inside class Settings:
BILLING_ENABLED: bool = False
BILLING_INTERVAL_SECONDS: int = 60
BILLING_CPU_PER_MINUTE: str = "0.001"
BILLING_MEMORY_GB_PER_MINUTE: str = "0.0005"
BILLING_GPU_DEFAULT_PER_MINUTE: str = "0.01"
BILLING_GPU_RATES: str = ""  # JSON like {"nvidia.com/A100": "0.05"}
```

Then construct `VMPricing` from settings at startup. `BILLING_ENABLED = False` by default so existing deployments aren't affected.

### B. DB schema changes

**B1. New columns on `vm_records`** -- tracked by the lifecycle endpoints, consumed by the billing loop:

```sql
ALTER TABLE vm_records
  ADD COLUMN is_running BOOLEAN DEFAULT FALSE NOT NULL,
  ADD COLUMN last_started_at TIMESTAMPTZ,
  ADD COLUMN last_stopped_at TIMESTAMPTZ,
  ADD COLUMN last_billed_at TIMESTAMPTZ;
```

Added via the usual `DO $$ ... IF NOT EXISTS ...` migration block in `VMRecordDB.ensure_schema()`.

**B2. New methods on `VMRecordDB`**:

- `set_running(namespace, vm_name, running: bool)` -- sets `is_running` and the corresponding timestamp
- `get_all_billable()` -- returns all non-deleted VMs where either `is_running = TRUE` or `last_stopped_at > last_billed_at` (the anti-gaming query)
- `update_last_billed(vm_id, billed_at)` -- stamps `last_billed_at` after deduction

**B3. New table `balance_topups`**:

```sql
CREATE TABLE IF NOT EXISTS balance_topups (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('main', 'llm')),
    amount NUMERIC(18,9) NOT NULL,
    admin_username TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_balance_topups_user
    ON balance_topups(user_id, source, created_at DESC);
```

New `BalanceTopupDB` class with:
- `create(user_id, source, amount, admin_username)`
- `get_cumulative(user_id, source)` -- `SELECT COALESCE(SUM(amount), 0) ...`
- `list_for_user(user_id, source, limit)` -- recent top-up history

**B4. New event type**: `BILLING_STOPPED = "billing_stopped"` in `VMEventType`.

### C. Lifecycle endpoint changes (the anti-gaming part)

In `vms.py`, after each successful k8s call, also update the DB running state:

| Endpoint | DB update |
|---|---|
| `create_vm` (already calls `_log_vm_created`) | `set_running(ns, name, True)` |
| `start_vm` / `restart_vm` / `unpause_vm` | `set_running(ns, name, True)` |
| `stop_vm` / `pause_vm` | `set_running(ns, name, False)` |
| `delete_vm` | `set_running(ns, name, False)`, then `mark_deleted` (already there) |

Same for the `admin_stop_vm` / `admin_delete_vm` in `admin.py`.

This way the billing loop never needs to query k8s -- it relies entirely on DB state.

### D. Billing loop (`app/services/billing_loop.py`)

```python
async def billing_tick(db: DB, pricing: VMPricing) -> list[int]:
    """One billing pass. Returns user_ids whose VMs should be killed."""
    now = datetime.now(timezone.utc)
    kill_user_ids: list[int] = []

    billable_vms = await db.vm_records.get_all_billable()

    # Group by user_id
    by_user: dict[int, list[VMRecord]] = {}
    for vm in billable_vms:
        by_user.setdefault(vm.user_id, []).append(vm)

    for user_id, vms in by_user.items():
        total_cost = Decimal("0")

        for vm in vms:
            if vm.is_running:
                start = max(filter(None, [vm.last_started_at, vm.last_billed_at])) or vm.created_at
                minutes = Decimal(str((now - start).total_seconds())) / 60
            elif vm.last_stopped_at and (not vm.last_billed_at or vm.last_stopped_at > vm.last_billed_at):
                start = max(filter(None, [vm.last_started_at, vm.last_billed_at])) or vm.created_at
                minutes = Decimal(str((vm.last_stopped_at - start).total_seconds())) / 60
            else:
                minutes = Decimal("0")

            if minutes > 0:
                total_cost += pricing.cost_per_minute(vm.cpu, vm.memory_gb, vm.gpu_count, vm.gpu_model) * minutes

        if total_cost <= 0:
            continue

        # Try to deduct
        bal = await db.users.get_balance(user_id)
        if bal is None:
            continue
        current_balance, version = bal

        try:
            new_balance, _ = await db.users.update_balance(user_id, -total_cost, version)
        except ValueError:
            kill_user_ids.append(user_id)
            continue

        # Stamp all VMs as billed
        for vm in vms:
            billed_at = now if vm.is_running else vm.last_stopped_at
            await db.vm_records.update_last_billed(vm.id, billed_at)

        # Snapshot
        await db.balance_snapshots.create(user_id, "main", new_balance)

    return kill_user_ids
```

Key properties:
- One pass over all users -- the "atomic" batch you described
- Returns a kill list; the caller (the loop in lifespan) handles stopping
- VMs stopped briefly between ticks still get billed because `last_stopped_at > last_billed_at`
- No k8s API calls inside billing

### E. Background task in lifespan (`app/main.py`)

Started inside the `async with create_db(...)` block:

```python
async def _billing_worker(app: FastAPI):
    from app.services.billing_loop import billing_tick
    pricing = build_vm_pricing(settings)  # construct VMPricing from settings

    while True:
        await asyncio.sleep(settings.BILLING_INTERVAL_SECONDS)
        try:
            db = app.state.db
            kill_list = await billing_tick(db, pricing)
            for user_id in kill_list:
                await _stop_all_user_vms(db, user_id)  # stop via k8s + log BILLING_STOPPED events
        except Exception:
            logger.exception("Billing tick failed")
```

`_stop_all_user_vms` fetches active VM records for that user, calls `stop_virtual_machine` for each, logs `BILLING_STOPPED` events, and sets `is_running = False`.

The task is created with `asyncio.create_task()` and cancelled in the lifespan teardown, gated behind `if settings.BILLING_ENABLED`.

### F. Admin top-up changes

The existing `topup_main_balance` and `topup_llm_balance` endpoints get one extra line each:

```python
await db.balance_topups.create(user_id, "main", amount, admin.username)
```

Same for transfers that add to a balance.

### G. Summary of all files touched

| File | Change |
|---|---|
| `app/config.py` | `VMPricing` dataclass, `BILLING_*` settings fields, `build_vm_pricing()` helper |
| `app/models.py` | Add `is_running`, `last_started_at`, `last_stopped_at`, `last_billed_at` to `VMRecord`; add `BILLING_STOPPED` to `VMEventType` |
| `app/database.py` | Migration columns on `vm_records`; new methods `set_running`, `get_all_billable`, `update_last_billed`; new `BalanceTopupDB` class; wire into `DB` |
| `app/services/billing_loop.py` | **New file** -- `billing_tick()` + `_stop_all_user_vms()` |
| `app/main.py` | Launch `_billing_worker` task in lifespan (guarded by `BILLING_ENABLED`) |
| `app/routers/vms.py` | Call `db.vm_records.set_running(...)` in lifecycle endpoints |
| `app/routers/admin.py` | Same for admin stop/delete; add `balance_topups.create()` in top-up endpoints |
| `app/schemas.py` | (optional) response schema for billing status if you want an API for it |

That's the full scope. Does this look right, or do you want to adjust anything before we start implementing?

---

**User**

maybe you have some other questions
I would also ask you to use pydantic only and not python dataclasses

---

**Cursor**

Good call on Pydantic -- consistent with everything else in the codebase. `VMPricing` becomes a `BaseModel` (or a frozen one) instead of a dataclass.

A few more questions, grouped by priority:

**1. What should happen to already-running VMs when billing is first enabled?**

Every existing VM will have `last_started_at = NULL` and `last_billed_at = NULL`. When the billing loop first sees them, it needs a starting point. The safest option: on migration, set `last_billed_at = NOW()` for all currently active VMs so we only bill forward from deployment, not retroactively from `created_at`. Sound right?

**2. Should the billing kill stop VMs or delete them?**

The plan currently says "stop all VMs" when a user runs out of funds. Stopped VMs still occupy storage. Do you want:
- (a) Stop only (user can top up and start again) -- this is what I assumed
- (b) Stop, then delete after some grace period

**3. Should admins be exempt from billing?**

Right now the billing loop would process all users equally. Should users with `role = "admin"` skip billing entirely?

---

**User**

1. Lets use last_billed_at = NOW() sounds reasonable
2. I think we should stop everything for some time. Deleting everything would be too cruel
3. Well we can exempt them, that would be nice 
Any other questions?

---

**Cursor**

Two more, then I think we're complete:

**1. Should we prevent users from starting a VM if their balance is already zero/negative?**

Right now `start_vm` doesn't check balance at all. It would be odd to let someone start a VM only for the billing loop to kill it 60 seconds later. I'd suggest adding a balance check in the `create_vm` and `start_vm` endpoints -- reject with a clear error if `balance <= 0`. Worth doing in the MVP?

**2. For the `balance_topups` tracking -- should LLM balance transfers also be recorded?**

Currently there are three ways money enters a balance:
- Admin tops up main balance (`topup_main_balance`)
- Admin tops up LLM balance (`topup_llm_balance`)
- Admin transfers between main and LLM (`transfer_balance`)

For the "track cumulative deposits" requirement, should we log all three? A transfer from main to LLM would be a negative row on `main` and a positive row on `llm` (or do we only care about external money coming in, ignoring transfers between the two)?

---

**User**

1. We should deny that method
2. We care about all net positive inflows (i guess it is the right term)
So when we add stuff we log it, when we transfer we should also track it (even though it does not change the total amount of money in the system) 
the goal is to have a valid amount of money spent in the end 

---

**Cursor**

Clear. That makes the accounting straightforward: `total_spent = cumulative_topups - current_balance` for each source.

I think we've covered everything. Here's the final consolidated plan with all decisions locked in:

---

## Final Plan -- VM Billing MVP

### Decisions summary

| Decision | Answer |
|---|---|
| Bill running VMs only | Yes, track start/stop times to prevent gaming |
| Pricing config | Pydantic model in `config.py`, env-overridable |
| Existing VMs on first deploy | `last_billed_at = NOW()` migration, bill forward only |
| Insufficient funds | Stop all VMs (not delete) |
| Admins | Exempt from billing |
| VM start/create with zero balance | Denied with error |
| Topup tracking | Log all net-positive inflows per balance (top-ups + receiving side of transfers) |

### Files and changes

**1. `app/config.py`** -- new `VMPricing` Pydantic model + `BILLING_*` settings

```python
class VMPricing(BaseModel):
    model_config = ConfigDict(frozen=True)
    cpu_per_minute: Decimal = Decimal("0.001")
    memory_gb_per_minute: Decimal = Decimal("0.0005")
    gpu_default_per_minute: Decimal = Decimal("0.01")
    gpu_rates: dict[str, Decimal] = {}

    def cost_per_minute(self, cpu, memory_gb, gpu_count, gpu_model) -> Decimal: ...
```

Settings fields: `BILLING_ENABLED`, `BILLING_INTERVAL_SECONDS`, `BILLING_CPU_PER_MINUTE`, `BILLING_MEMORY_GB_PER_MINUTE`, `BILLING_GPU_DEFAULT_PER_MINUTE`, `BILLING_GPU_RATES`.

**2. `app/models.py`**
- `VMRecord`: add `is_running`, `last_started_at`, `last_stopped_at`, `last_billed_at`
- `VMEventType`: add `BILLING_STOPPED = "billing_stopped"`

**3. `app/database.py`**
- `VMRecordDB`: migration for new columns (with `last_billed_at = NOW()` for existing active VMs); new methods `set_running()`, `get_all_billable()`, `update_last_billed()`
- New `BalanceTopupDB` class with `create()`, `get_cumulative()`, `list_for_user()`
- Wire `BalanceTopupDB` into `DB` aggregate + `create_db()`

**4. `app/services/billing_loop.py`** -- **new file**
- `billing_tick(db, pricing)` -- one pass over all users: compute costs, deduct, return kill list
- `stop_all_user_vms(db, user_id)` -- stop via k8s, log `BILLING_STOPPED` events, set `is_running = False`
- Admin users (`role = 'admin'`) skipped entirely

**5. `app/main.py`**
- Launch `_billing_worker` asyncio task inside lifespan, guarded by `settings.BILLING_ENABLED`
- Cancel on shutdown

**6. `app/routers/vms.py`**
- `create_vm` / `start_vm` / `unpause_vm`: check `balance > 0` (skip for admins), reject otherwise
- All lifecycle endpoints: call `db.vm_records.set_running(ns, name, True/False)` after k8s success

**7. `app/routers/admin.py`**
- `admin_stop_vm` / `admin_delete_vm`: call `set_running(ns, name, False)`
- `topup_main_balance`: add `db.balance_topups.create(user_id, "main", amount, admin.username)`
- `topup_llm_balance`: add `db.balance_topups.create(user_id, "llm", amount, admin.username)`
- `transfer_balance`: log positive inflow on receiving side -- main-to-llm logs `("llm", amount)`, llm-to-main logs `("main", amount)`

---

That's the complete scope. When you're ready to implement, switch to Agent mode and we can start working through it file by file.

---

**User**

Topup tracking
well if we remove money with transfers we should also track it I think
so we should track all operations where we add/remove money ourselves from the balance

---

**Cursor**

Right, that makes more sense -- track every explicit admin-initiated balance mutation, not just the positive side. So `balance_topups` becomes more of a `balance_ledger` / `balance_operations` table. Every row is "an admin did this to this balance."

Here's what gets logged:

| Operation | Row on `main` | Row on `llm` |
|---|---|---|
| Admin tops up main +100 | `+100` | -- |
| Admin tops up LLM +50 | -- | `+50` |
| Transfer main -> LLM (80) | `-80` | `+80` |
| Transfer LLM -> main (30) | `+30` | `-30` |

Then for each balance:
- `total_deposited = SUM(amount) WHERE amount > 0`
- `total_withdrawn_by_admin = SUM(amount) WHERE amount < 0` (transfers out)
- `total_spent_by_system = total_deposited + total_withdrawn_by_admin - current_balance`

That gives you a complete picture: how much money went in, how much was moved around by admins, and how much was consumed by VM billing / LLM usage.

The table name should probably reflect this broader role -- `balance_operations` instead of `balance_topups`:

```sql
CREATE TABLE IF NOT EXISTS balance_operations (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('main', 'llm')),
    amount NUMERIC(18,9) NOT NULL,       -- positive = deposit, negative = withdrawal/transfer-out
    op_type TEXT NOT NULL CHECK (op_type IN ('topup', 'transfer_in', 'transfer_out')),
    admin_username TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

The `op_type` column lets you filter/report on the nature of the operation separately from the sign of the amount. Want to keep it, or is just the signed `amount` enough for the MVP?

---

**User**

op_type is great I think

---

**Cursor**

Good. Updated the plan -- the table is now `balance_operations` with the `op_type` column. Here's the final version of that piece:

**Table**: `balance_operations`

```sql
CREATE TABLE IF NOT EXISTS balance_operations (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('main', 'llm')),
    amount NUMERIC(18,9) NOT NULL,
    op_type TEXT NOT NULL CHECK (op_type IN ('topup', 'transfer_in', 'transfer_out')),
    admin_username TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

**What gets logged where in the code**:

| Endpoint | Calls |
|---|---|
| `topup_main_balance` | `create(user_id, "main", +amount, "topup", admin)` |
| `topup_llm_balance` | `create(user_id, "llm", +amount, "topup", admin)` |
| `transfer_balance` main->llm | `create(user_id, "main", -amount, "transfer_out", admin)` + `create(user_id, "llm", +amount, "transfer_in", admin)` |
| `transfer_balance` llm->main | `create(user_id, "llm", -amount, "transfer_out", admin)` + `create(user_id, "main", +amount, "transfer_in", admin)` |

**DB class methods**:
- `create(user_id, source, amount, op_type, admin_username)`
- `get_cumulative(user_id, source)` -- `SUM(amount)` for total net admin-initiated change
- `get_total_deposited(user_id, source)` -- `SUM(amount) WHERE amount > 0`
- `list_for_user(user_id, source, limit)` -- recent history

Everything else in the plan stays the same. Ready to implement whenever you switch to Agent mode.

---

**User**

do you remember that cumulative comes from summing the balance in the top_up/balance table and then subtracting balance from the @viirtuoz-vps/app/database.py:41-52 
This way we can certanly say how much money we have spent

---

**Cursor**

Yes, exactly. The accounting is:

```
total_spent = SUM(amount) from balance_operations  −  current balance from users table
```

`SUM(amount)` from `balance_operations` captures the net result of all admin actions (topups, transfers in, transfers out). The only thing that silently erodes the balance without touching that table is system consumption (VM billing, LLM usage). So the difference between the two is precisely what was spent.

For both balances:
- `spent_on_vms = SUM(amount WHERE source='main') - users.balance`
- `spent_on_llm = SUM(amount WHERE source='llm') - llm_balance`

That's why we don't need to log billing deductions in `balance_operations` -- they're captured implicitly by the gap. The table only needs admin-initiated mutations, which is exactly what we have.

So `get_cumulative(user_id, source)` is the key method -- just `SELECT COALESCE(SUM(amount), 0) FROM balance_operations WHERE user_id = $1 AND source = $2`. The `get_total_deposited` (positive-only sum) method I mentioned earlier is still useful for reporting ("how much total money was put in") but not required for the spent calculation. I'll keep it as a convenience but `get_cumulative` is the one that matters.

---

**User**

eh I am still scared
We do not really have a reliable way to track the vm params right? 

---

**Cursor**

That's a valid concern. There are two separate risks here:

**Risk 1: VM resource specs (cpu, memory, gpu) in `vm_records` could be wrong.**

This one is actually low risk. KubeVirt VMs can't hot-resize -- you can't change CPU/memory on a running VM without deleting and recreating it. So the specs stored at creation time in `vm_records` should stay accurate for the lifetime of that VM. Nobody is going to `kubectl edit` a VM's CPU count while it runs.

**Risk 2: `is_running` state drifts from k8s reality.**

This is the real scary one. It can happen if:
- Someone uses `kubectl` to start/stop a VM, bypassing our API entirely
- The app crashes between the k8s call succeeding and the DB write
- K8s auto-restarts a VM (e.g., after node reboot with `RerunOnFailure` strategy)
- A stop call fails silently on k8s but we mark it stopped in DB

If `is_running` says `False` but the VM is actually running, we're giving away free compute. If it says `True` but the VM is stopped, we're charging for nothing.

**The fix: a reconciliation step inside the billing loop.**

Before computing costs each tick, query k8s for the actual set of running VMIs across all namespaces (one `list` call, not per-VM), and reconcile against `vm_records.is_running`. Something like:

```
1. List all running VMIs from k8s (single API call)
2. For each vm_record where is_running=True but NOT in k8s running set → set_running(False)
3. For each vm_record where is_running=False but IS in k8s running set → set_running(True)
4. Now proceed with billing using the corrected DB state
```

This gives you the best of both worlds:
- DB state is the billing source of truth (with anti-gaming timestamps)
- But it's corrected against k8s reality every tick, so drift never persists longer than one billing interval

The k8s call is cheap -- listing VMIs across namespaces is one API call, not one per VM. And it only happens once per billing tick (every 60s), not on every request.

Want to add this reconciliation step to the plan?

---

**User**

No we do not really have a proper object for this 
So it is more like 
VM stats object -> goes to a fucntions that uses its data to calc costs
And how do we do that vm stats object?

---

**Cursor**

Ah, I see the concern now. You're saying: forget `vm_records` as a billing source -- the real truth of what resources a VM has lives in k8s. So the "VM stats object" should be parsed from the actual k8s VM spec.

You already do this parsing in multiple places. For example in `vm_details.py`:

```96:103:viirtuoz-vps/app/routers/vm_details.py
    spec = vm.get("spec", {}).get("template", {}).get("spec", {})
    domain = spec.get("domain", {})
    resources = domain.get("resources", {}).get("requests", {})
    cpu = domain.get("cpu", {}).get("cores", "N/A")
    memory = resources.get("memory", "N/A")

    gpu_devices = domain.get("devices", {}).get("gpus", [])
    gpu_count = len(gpu_devices)
```

And again in `admin.py` lines 302-309 with the same pattern.

So the approach is:

**1. A Pydantic model for billable VM resources:**

```python
class VMBillingSpec(BaseModel):
    vm_name: str
    namespace: str
    user_id: int | None
    cpu: int
    memory_gb: float
    gpu_count: int
    gpu_model: str | None
```

**2. A parser function that builds it from the k8s VM dict:**

```python
def vm_billing_spec_from_k8s(vm: dict, user_id: int | None = None) -> VMBillingSpec:
    meta = vm.get("metadata", {})
    spec = vm.get("spec", {}).get("template", {}).get("spec", {})
    domain = spec.get("domain", {})

    cpu = domain.get("cpu", {}).get("cores", 1)
    memory_raw = domain.get("resources", {}).get("requests", {}).get("memory", "1Gi")
    memory_gb = _parse_memory_to_gb(memory_raw)  # "8Gi" -> 8.0, "512Mi" -> 0.5

    gpu_devices = domain.get("devices", {}).get("gpus", [])

    return VMBillingSpec(
        vm_name=meta.get("name", ""),
        namespace=meta.get("namespace", ""),
        user_id=user_id,
        cpu=int(cpu),
        memory_gb=memory_gb,
        gpu_count=len(gpu_devices),
        gpu_model=gpu_devices[0].get("deviceName") if gpu_devices else None,
    )
```

**3. The billing tick flow becomes:**

```
1. List all VMs from k8s (VM objects exist even when stopped - they have the full spec)
2. List all running VMIs from k8s (tells us what's actually running)
3. For each VM:
   a. Parse → VMBillingSpec (resource truth from k8s)
   b. Check if it has a running VMI → currently running
   c. Cross-reference with DB is_running/last_stopped_at for anti-gaming
4. Feed each VMBillingSpec into pricing.cost_per_minute()
5. Aggregate per user, deduct, kill list, etc.
```

The key insight: **k8s is the source of truth for resource specs, DB is only the source of truth for billing timestamps** (`last_billed_at`, `last_stopped_at` for anti-gaming). We stop pretending `vm_records` is the billing data source.

The `user_id` linkage (which k8s doesn't know about) comes from matching `(namespace, vm_name)` against `vm_records`. We still need that join, but only for the user mapping -- not for the resource numbers.

Does that address the concern?

---

**User**

so we use k8s as a source of truth here and db as a helper?

---

**Cursor**

Yes, exactly. The split is:

**K8s = source of truth for:**
- What VMs exist
- What resources each VM has (cpu, memory, gpu)
- Whether a VM is currently running (VMI exists or not)

**DB = helper for:**
- Mapping VMs to users (`vm_records` gives us `namespace + vm_name → user_id`)
- Billing timestamps (`last_billed_at`, `last_stopped_at` for anti-gaming)
- Money (`users.balance`, `balance_operations`)

The billing tick reads the real world from k8s, joins it with the accounting data from DB, computes costs, and updates the DB.

This means if someone creates a VM via `kubectl` outside the app, we just won't bill it (no `vm_records` entry = no `user_id` = skip). That's fine -- there's no way to bill something we can't attribute to a user. And if someone edits a VM's CPU via `kubectl`, we'll bill the actual resources because we read from k8s, not from our stale DB copy.

The only fragile part is the anti-gaming timestamps, and even those self-correct: if `is_running` in DB drifts from k8s reality, the reconciliation step (comparing VMI list against DB state) fixes it every tick. Worst case, one billing interval of inaccuracy.

