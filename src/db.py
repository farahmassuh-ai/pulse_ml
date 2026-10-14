"""Everything that talks to PostgreSQL.

Credentials come from environment variables (loaded from .env), never from code.
"""
from __future__ import annotations

import os
import math
from datetime import date, datetime

import numpy as np
import pandas as pd
import psycopg
from dotenv import load_dotenv

load_dotenv()

# Columns written by the pipeline, in INSERT order. `source` is passed separately.
LOAD_COLUMNS = [
    "service_date", "route_id", "direction_id", "half_trip_id", "stop_id",
    "time_point_id", "time_point_order", "point_type", "standard_type",
    "scheduled", "scheduled_headway", "actual", "delay_min", "late",
]

INSERT_SQL = f"""
    INSERT INTO stop_events ({", ".join(LOAD_COLUMNS)}, source)
    VALUES ({", ".join(["%s"] * (len(LOAD_COLUMNS) + 1))})
    ON CONFLICT DO NOTHING
"""

CHUNK_SIZE = 50_000


def get_conn(dbname=None, autocommit=False):
    return psycopg.connect(
        host=os.environ["TRANSIT_DB_HOST"],
        port=os.environ.get("TRANSIT_DB_PORT", "5432"),
        dbname=dbname or os.environ["TRANSIT_DB_NAME"],
        user=os.environ["TRANSIT_DB_USER"],
        password=os.environ["TRANSIT_DB_PASSWORD"],
        autocommit=autocommit,
    )


def _to_python(value):
    """Convert pandas/numpy values to plain Python types psycopg can send."""
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return None if np.isnan(value) else float(value)
    return value


def to_rows(df: pd.DataFrame, source: str) -> list[tuple]:
    """DataFrame -> list of tuples in LOAD_COLUMNS order, plus the source."""
    columns = [df[c].astype(object).tolist() for c in LOAD_COLUMNS]
    return [tuple(_to_python(v) for v in values) + (source,) for values in zip(*columns)]


def query(sql: str, params=None) -> list[tuple]:
    """Run a SELECT and return all rows."""
    with get_conn() as conn:
        return conn.execute(sql, params).fetchall()


def count_rows(conn, source=None) -> int:
    if source is None:
        return conn.execute("SELECT COUNT(*) FROM stop_events").fetchone()[0]
    return conn.execute(
        "SELECT COUNT(*) FROM stop_events WHERE source = %s", (source,)
    ).fetchone()[0]


def insert_stop_events(df: pd.DataFrame, source: str) -> int:
    """Insert rows; duplicates are skipped by the UNIQUE key.

    Returns how many rows were actually new (rows in the table after - before).
    Each chunk is its own transaction, so a crash halfway keeps the finished
    chunks, and a rerun fills in the rest without duplicating anything.
    """
    if source not in ("historical", "api"):
        raise ValueError(f"unknown source {source!r}")
    with get_conn() as conn:
        before = count_rows(conn, source)
        for start in range(0, len(df), CHUNK_SIZE):
            rows = to_rows(df.iloc[start:start + CHUNK_SIZE], source)
            with conn.cursor() as cur:
                cur.executemany(INSERT_SQL, rows)
            conn.commit()
        after = count_rows(conn, source)
    return after - before
