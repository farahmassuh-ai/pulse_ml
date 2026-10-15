"""Step 3: export the labelled historical rows and split them by time.

Run from the repo root:  python3 src/make_splits.py

- Rows: source = 'historical' AND late IS NOT NULL (API rows have no label yet).
- Columns: serving-safe features + the label. Nothing derived from `actual`.
- Split by service_date: every month before the latest one -> train,
  days 1-15 of the latest month -> validation, day 16 to the end -> test.
- Writes data/splits/{train,val,test}.parquet, then checks the time order.
Freeze the result with:  dvc add data/splits/train.parquet data/splits/val.parquet data/splits/test.parquet
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

import pandas as pd

from db import get_conn

ROOT = Path(__file__).resolve().parent.parent
SPLIT_DIR = ROOT / "data" / "splits"

EXPORT_SQL = """
    SELECT service_date, route_id, direction_id, stop_id, time_point_id,
           scheduled, scheduled_headway, point_type, standard_type, time_point_order,
           late
    FROM stop_events
    WHERE source = 'historical' AND late IS NOT NULL
"""


def export_rows() -> pd.DataFrame:
    """Stream the rows out of Postgres with COPY (much faster than row-by-row)."""
    buffer = io.BytesIO()
    with get_conn() as conn, conn.cursor() as cur:
        with cur.copy(f"COPY ({EXPORT_SQL}) TO STDOUT WITH (FORMAT CSV, HEADER)") as copy:
            for chunk in copy:
                buffer.write(chunk)
    buffer.seek(0)
    df = pd.read_csv(buffer, dtype={"route_id": str, "direction_id": str, "stop_id": str,
                                    "time_point_id": str, "point_type": str,
                                    "standard_type": str})
    return prepare(df)


def prepare(df: pd.DataFrame) -> pd.DataFrame:
    """Types + calendar features derived from `scheduled` (known before the trip)."""
    df = df.copy()
    df["service_date"] = pd.to_datetime(df["service_date"])
    df["scheduled"] = pd.to_datetime(df["scheduled"])
    df["scheduled_headway"] = pd.to_numeric(df["scheduled_headway"]).astype("Int64")
    df["time_point_order"] = pd.to_numeric(df["time_point_order"]).astype("Int64")
    if df["late"].dtype == object:
        df["late"] = df["late"].map({"t": True, "f": False, True: True, False: False})
    df["late"] = df["late"].astype(bool)
    df["day_of_week"] = df["scheduled"].dt.dayofweek          # 0 = Monday
    df["hour"] = df["scheduled"].dt.hour
    df["minute_of_day"] = df["scheduled"].dt.hour * 60 + df["scheduled"].dt.minute
    return df.sort_values(["scheduled", "route_id", "stop_id"]).reset_index(drop=True)


def split_by_time(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Earlier months -> train; latest month days 1-15 -> val; day 16+ -> test."""
    month = df["service_date"].dt.to_period("M")
    last = month.max()
    in_last = month == last
    day = df["service_date"].dt.day
    splits = {
        "train": df[month < last],
        "val": df[in_last & (day <= 15)],
        "test": df[in_last & (day >= 16)],
    }
    for name, part in splits.items():
        if part.empty:
            raise ValueError(f"{name} split is empty: need at least two months of data")
    return {name: part.reset_index(drop=True) for name, part in splits.items()}


def check_order(splits: dict[str, pd.DataFrame]) -> None:
    """No overlap in time: everything in train happens before val, val before test."""
    for earlier, later in [("train", "val"), ("val", "test")]:
        end = splits[earlier]["scheduled"].max()
        start = splits[later]["scheduled"].min()
        if not end < start:
            raise AssertionError(f"{earlier} ends at {end}, after {later} starts at {start}")
        print(f"  {earlier} ends {end}  <  {later} starts {start}")


def main() -> int:
    print("Exporting labelled historical rows ...")
    df = export_rows()
    splits = split_by_time(df)
    print("Checking time order:")
    check_order(splits)

    SPLIT_DIR.mkdir(parents=True, exist_ok=True)
    print("\nsplit   rows        dates                     late rate")
    for name, part in splits.items():
        part.to_parquet(SPLIT_DIR / f"{name}.parquet", index=False)
        first, last = part["service_date"].min().date(), part["service_date"].max().date()
        print(f"{name:<6}  {len(part):>10,}  {first} .. {last}  {part['late'].mean():.1%}")
    print(f"\nWrote {SPLIT_DIR.relative_to(ROOT)}/{{train,val,test}}.parquet")
    return 0


if __name__ == "__main__":
    sys.exit(main())
