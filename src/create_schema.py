"""Create the database (if missing) and the stop_events table from schema.sql.

Run from the repo root:  python src/create_schema.py
Safe to run again: existing database and table are left alone.
"""
import os
from pathlib import Path

from psycopg import sql

from db import get_conn

DB_NAME = os.environ["TRANSIT_DB_NAME"]
SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schema.sql"

# CREATE DATABASE can't run inside a transaction, so autocommit=True,
# connected to the built-in "postgres" maintenance database.
with get_conn(dbname="postgres", autocommit=True) as conn:
    exists = conn.execute(
        "SELECT 1 FROM pg_database WHERE datname = %s", (DB_NAME,)
    ).fetchone()
    if exists:
        print(f"Database '{DB_NAME}' already exists")
    else:
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(DB_NAME)))
        print(f"Created database '{DB_NAME}'")

with get_conn() as conn:
    conn.execute(SCHEMA_PATH.read_text())
    table = conn.execute("SELECT to_regclass('public.stop_events')").fetchone()[0]
    print(f"schema.sql applied, table found: {table}")
