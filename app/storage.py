"""基于本地 SQLite 的规划结果持久化。

容器启动时（FastAPI lifespan）自动建库建表，结果保存在
``PLAN_DB_PATH`` 环境变量指定的文件（默认 ``/data/plans.db``）。
"""

import json
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any, Optional


_SCHEMA = """
CREATE TABLE IF NOT EXISTS plans (
    id          TEXT PRIMARY KEY,
    status      TEXT NOT NULL CHECK (status IN ('completed', 'failed')),
    request     TEXT NOT NULL,
    result      TEXT,
    error_code  TEXT,
    error_message TEXT,
    created_at  TEXT NOT NULL
);
"""


class JobStore:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        import os

        parent = os.path.dirname(os.path.abspath(self.db_path))
        os.makedirs(parent, exist_ok=True)
        with self._lock, self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(_SCHEMA)

    def save(
        self,
        job_id: str,
        status: str,
        request: dict,
        result: Optional[dict] = None,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO plans (id, status, request, result, error_code, "
                "error_message, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    job_id,
                    status,
                    json.dumps(request, ensure_ascii=False),
                    json.dumps(result, ensure_ascii=False) if result is not None else None,
                    error_code,
                    error_message,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    def get(self, job_id: str) -> Optional[dict[str, Any]]:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM plans WHERE id = ?", (job_id,)
            ).fetchone()
        if row is None:
            return None
        return {
            "id": row["id"],
            "status": row["status"],
            "request": json.loads(row["request"]),
            "result": json.loads(row["result"]) if row["result"] else None,
            "error": (
                {"code": row["error_code"], "message": row["error_message"]}
                if row["error_code"] is not None
                else None
            ),
            "created_at": row["created_at"],
        }

    def count(self) -> int:
        with self._lock, self._connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM plans").fetchone()[0])
