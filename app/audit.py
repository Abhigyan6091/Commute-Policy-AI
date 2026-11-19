"""Audit logging to SQLite."""
import time
import sqlite3
from typing import Optional

def log_event(
    db_path: str,
    event_type: str,
    company_id: str,
    user_id: str,
    details: Optional[str] = None,
) -> None:
    """Append an audit event. Fire-and-forget — never raises."""
    try:
        conn = sqlite3.connect(db_path, timeout=5)
        try:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS audit_log
                   (id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT, company_id TEXT, user_id TEXT,
                    details TEXT, created_at INTEGER)"""
            )
            conn.execute(
                """INSERT INTO audit_log
                   (event_type, company_id, user_id, details, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (event_type, company_id, user_id, details, int(time.time()))
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass  # audit failure must never break the main flow
