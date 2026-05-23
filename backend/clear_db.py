"""One-shot script: delete all rows from every table (keep structure)."""
import os, sys

# Allow running from repo root or inside the container
sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import text
from app.config.database import engine

TABLES = [
    "notifications",
    "alerts",
    "ergonomic_records",
    "incidents",
    "cameras",
    "system_config",
    "users",
]

with engine.connect() as conn:
    conn.execute(text("SET session_replication_role = 'replica';"))  # disable FK checks
    for table in TABLES:
        result = conn.execute(text(f"DELETE FROM {table}"))
        print(f"[clear_db] Deleted {result.rowcount} rows from '{table}'")
    conn.execute(text("SET session_replication_role = 'origin';"))   # re-enable FK checks
    conn.commit()

print("[clear_db] Done — all rows removed, tables intact.")
