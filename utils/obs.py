"""Structured logging for per-tenant observability.

In the shared multi-tenant model there's no per-org Cloud Run service to group
by — so to "see focuschainlabs vs sn_realtors" in GCP, the signal has to come
from the logs. Cloud Logging parses a single-line JSON object on stdout into
`jsonPayload`, so emitting {"event":…, "organization_id":…} makes per-org log
filters, log-based metrics, and dashboards possible.

    from utils import obs
    obs.log_event("inbound_message", organization_id="sn_realtors", action="created")

→ Logs Explorer: jsonPayload.event="inbound_message" AND jsonPayload.organization_id="sn_realtors"

Cheap, dependency-free, and never raises — safe on hot paths.
"""

from __future__ import annotations

import json
import sys
from typing import Any


def log_event(
    event: str,
    *,
    organization_id: str | None = None,
    severity: str = "INFO",
    **fields: Any,
) -> None:
    """Emit one structured log line for Cloud Logging (jsonPayload)."""
    payload: dict[str, Any] = {"event": event, "severity": severity}
    if organization_id:
        payload["organization_id"] = organization_id
    for k, v in fields.items():
        if v is not None:
            payload[k] = v
    try:
        sys.stdout.write(json.dumps(payload, default=str) + "\n")
    except Exception:  # noqa: BLE001 - logging must never break the caller
        pass
