"""
Thin async wrappers for running synchronous Kubernetes SDK calls
off the event loop via ``asyncio.to_thread``.
"""

from __future__ import annotations

import asyncio
from functools import partial
from typing import Any, Callable, TypeVar

T = TypeVar("T")


async def run_sync(func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Run a blocking function in a thread-pool executor.

    This keeps the event loop free while the synchronous ``kubernetes``
    client makes HTTP calls to the API server.

    Usage::

        from app.utils.k8s_utils import start_virtual_machine
        ok = await run_sync(start_virtual_machine, namespace, vm_name)
    """
    if kwargs:
        func = partial(func, **kwargs)
    return await asyncio.to_thread(func, *args)
