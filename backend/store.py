from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .models import AnalysisStatus


class Store:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = self.root / "xishizhibei.sqlite3"
        with sqlite3.connect(self.db) as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS analyses (id TEXT PRIMARY KEY, status TEXT, progress INTEGER, message TEXT, payload TEXT, updated_at TEXT)")

    def create(self, analysis_id: str, payload: dict[str, Any]) -> None:
        self.update(analysis_id, AnalysisStatus.VALIDATING, 5, "正在校验数据", payload)

    def update(self, analysis_id: str, status: AnalysisStatus, progress: int, message: str, payload: dict[str, Any] | None = None) -> None:
        with sqlite3.connect(self.db) as conn:
            conn.execute(
                "INSERT INTO analyses(id,status,progress,message,payload,updated_at) VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET status=excluded.status,progress=excluded.progress,message=excluded.message,payload=excluded.payload,updated_at=excluded.updated_at",
                (analysis_id, status.value, progress, message, json.dumps(payload or {}, ensure_ascii=False), datetime.now(UTC).isoformat()),
            )

    def get(self, analysis_id: str) -> dict[str, Any] | None:
        with sqlite3.connect(self.db) as conn:
            row = conn.execute("SELECT status,progress,message,payload,updated_at FROM analyses WHERE id=?", (analysis_id,)).fetchone()
        if not row:
            return None
        return {"status": row[0], "progress": row[1], "message": row[2], **json.loads(row[3]), "updated_at": row[4]}
