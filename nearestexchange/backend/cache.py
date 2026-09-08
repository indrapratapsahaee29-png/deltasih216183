"""SQLite cache for trace results. Avoids re-hitting public chain APIs."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).resolve().parent / "trace_cache.db"
TTL_SECONDS = 60 * 60  # 1 hour

_lock = threading.Lock()
_initialized = False


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS traces (
            cache_key TEXT PRIMARY KEY,
            payload TEXT NOT NULL,
            created_at REAL NOT NULL
        )
        """
    )
    return conn


def _db() -> sqlite3.Connection:
    global _initialized
    conn = _connect()
    _initialized = True
    return conn


def cache_key(chain: str, address: str) -> str:
    return f"{chain}:{address}"


def get(key: str) -> dict[str, Any] | None:
    now = time.time()
    with _lock:
        conn = _db()
        row = conn.execute(
            "SELECT payload, created_at FROM traces WHERE cache_key = ?",
            (key,),
        ).fetchone()
        if not row:
            conn.close()
            return None
        payload, created_at = row
        if now - created_at > TTL_SECONDS:
            conn.execute("DELETE FROM traces WHERE cache_key = ?", (key,))
            conn.commit()
            conn.close()
            return None
        conn.close()
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return None
    data["cached"] = True
    return data


def put(key: str, payload: dict[str, Any]) -> None:
    blob = json.dumps(payload, ensure_ascii=False)
    with _lock:
        conn = _db()
        conn.execute(
            """
            INSERT OR REPLACE INTO traces (cache_key, payload, created_at)
            VALUES (?, ?, ?)
            """,
            (key, blob, time.time()),
        )
        conn.commit()
        conn.close()


def clear() -> None:
    with _lock:
        conn = _db()
        conn.execute("DELETE FROM traces")
        conn.commit()
        conn.close()
