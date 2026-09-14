"""SQLite persistence for saved analyses. Stores each AnalysisRecord as JSON."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from schemas.analysis_models import AnalysisRecord

DB_PATH = Path(__file__).parent / "deallens.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS analyses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    acquirer_name TEXT NOT NULL,
    target_name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    data TEXT NOT NULL
);
"""


def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute(SCHEMA)
    conn.commit()
    return conn


def save_analysis(record: AnalysisRecord, db_path: Path = DB_PATH) -> int:
    conn = get_connection(db_path)
    payload = record.model_dump_json()
    if record.id is None:
        cur = conn.execute(
            "INSERT INTO analyses (acquirer_name, target_name, created_at, data) VALUES (?, ?, ?, ?)",
            (record.transaction.acquirer_name, record.transaction.target_name, record.created_at.isoformat(), payload),
        )
        conn.commit()
        new_id = cur.lastrowid
        conn.close()
        return new_id
    conn.execute(
        "UPDATE analyses SET acquirer_name=?, target_name=?, data=? WHERE id=?",
        (record.transaction.acquirer_name, record.transaction.target_name, payload, record.id),
    )
    conn.commit()
    conn.close()
    return record.id


def load_analysis(analysis_id: int, db_path: Path = DB_PATH) -> AnalysisRecord | None:
    conn = get_connection(db_path)
    row = conn.execute("SELECT data FROM analyses WHERE id=?", (analysis_id,)).fetchone()
    conn.close()
    if row is None:
        return None
    return AnalysisRecord.model_validate(json.loads(row[0]))


def list_analyses(db_path: Path = DB_PATH) -> list[dict]:
    conn = get_connection(db_path)
    rows = conn.execute(
        "SELECT id, acquirer_name, target_name, created_at FROM analyses ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [{"id": r[0], "acquirer_name": r[1], "target_name": r[2], "created_at": r[3]} for r in rows]


def delete_analysis(analysis_id: int, db_path: Path = DB_PATH) -> None:
    conn = get_connection(db_path)
    conn.execute("DELETE FROM analyses WHERE id=?", (analysis_id,))
    conn.commit()
    conn.close()
