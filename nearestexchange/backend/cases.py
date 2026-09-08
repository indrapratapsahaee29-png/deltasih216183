"""In-session LEA case register. Not a durable case-management system."""

from __future__ import annotations

from collections import deque
from threading import Lock
from typing import Any

_LOCK = Lock()
_CASES: deque[dict[str, Any]] = deque(maxlen=40)


def record(result: dict[str, Any]) -> dict[str, Any]:
    attr = result.get("attribution") or {}
    exch = result.get("exchange") or {}
    row = {
        "complaint_id": attr.get("complaint_id"),
        "address": result.get("address"),
        "chain": result.get("chain"),
        "crime_label": attr.get("crime_label"),
        "pattern_label": attr.get("pattern_label"),
        "found": bool(result.get("found")),
        "hops": result.get("hops"),
        "risk": result.get("risk"),
        "vasp": exch.get("exchange") if result.get("found") else None,
        "alert": (attr.get("alert") or {}).get("code"),
        "traced_at": result.get("traced_at"),
    }
    with _LOCK:
        _CASES.appendleft(row)
        items = list(_CASES)
    return {"case": row, "register": items, "stats": _stats(items)}


def list_cases() -> dict[str, Any]:
    with _LOCK:
        items = list(_CASES)
    return {"register": items, "stats": _stats(items)}


def _stats(items: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(items)
    found = sum(1 for c in items if c.get("found"))
    high = sum(1 for c in items if c.get("risk") == "high")
    medium = sum(1 for c in items if c.get("risk") == "medium")
    return {
        "cases": n,
        "vasp_hits": found,
        "high": high,
        "medium": medium,
        "low": n - high - medium,
    }
