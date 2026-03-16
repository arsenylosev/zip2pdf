"""Tiny NDJSON logger for agent debug sessions."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

DEBUG_LOG_PATH = Path("/home/ubuntu/.cursor/debug-54c5fc.log")


def write_debug_log(
    *,
    run_id: str,
    hypothesis_id: str,
    location: str,
    message: str,
    data: dict[str, Any],
) -> None:
    payload = {
        "sessionId": "54c5fc",
        "runId": run_id,
        "hypothesisId": hypothesis_id,
        "location": location,
        "message": message,
        "data": data,
        "timestamp": int(time.time() * 1000),
    }
    try:
        with DEBUG_LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        # Never break app flow because of debug instrumentation.
        pass
