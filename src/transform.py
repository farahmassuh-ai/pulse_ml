"""Raw MBTA records -> the stop_events shape. Pure pandas, no database."""
from __future__ import annotations

import pandas as pd

LATE_THRESHOLD_MIN = 3      # late = more than 3 minutes behind schedule
DELAY_MIN_OK = -30          # delays outside [-30, +120] minutes are data errors
DELAY_MAX_OK = 120

KEY = ["service_date", "route_id", "direction_id", "stop_id", "scheduled"]

_DUMMY_DAY = pd.Timestamp("1900-01-01")


def parse_wallclock(values: pd.Series, service_date: pd.Series) -> pd.Series:
    """Parse MBTA timestamps as Boston wall-clock time, without a time zone.

    Two formats exist:
      files: '1900-01-01T17:18:00Z'      -> fake date, the 'Z' is decorative
      API:   '2026-09-07T17:18:00-04:00' -> real date with an offset
    Both keep the first 19 characters (the local clock time); the offset or 'Z'
    is dropped. Dummy 1900 dates are moved onto the real service date, so
    '1900-01-02T00:20' becomes 00:20 on the day after service_date.
    Unparseable values become NaT.
    """
    text = values.astype("string").str.slice(0, 19)
    ts = pd.to_datetime(text, format="%Y-%m-%dT%H:%M:%S", errors="coerce")
    is_dummy = ts.dt.year == 1900
    moved = service_date + (ts - _DUMMY_DAY)
    return ts.where(~is_dummy, moved)


def add_delay_and_label(df: pd.DataFrame) -> pd.DataFrame:
    """delay_min = actual - scheduled (minutes); late = delay_min > 3, NULL if no actual."""
    df = df.copy()
    df["delay_min"] = (df["actual"] - df["scheduled"]).dt.total_seconds() / 60
    df["late"] = (
        (df["delay_min"] > LATE_THRESHOLD_MIN)
        .astype("boolean")
        .mask(df["actual"].isna())
    )
    return df


def transform_historical(raw: pd.DataFrame) -> pd.DataFrame:
    """One raw monthly file (all columns read as strings) -> stop_events columns."""
    df = pd.DataFrame(index=raw.index)
    service_date = pd.to_datetime(raw["service_date"], format="%Y-%m-%d", errors="coerce")
    df["service_date"] = service_date
    for col in ["route_id", "direction_id", "half_trip_id", "stop_id",
                "time_point_id", "point_type", "standard_type"]:
        df[col] = raw[col].astype("string").str.strip()
    df["time_point_order"] = pd.to_numeric(raw["time_point_order"], errors="coerce").astype("Int64")
    df["scheduled_headway"] = pd.to_numeric(raw["scheduled_headway"], errors="coerce").astype("Int64")
    df["scheduled"] = parse_wallclock(raw["scheduled"], service_date)
    df["actual"] = parse_wallclock(raw["actual"], service_date)
    return add_delay_and_label(df)


def finalize_dates(df: pd.DataFrame) -> pd.DataFrame:
    """service_date as a plain date for the DATE column."""
    df = df.copy()
    df["service_date"] = df["service_date"].dt.date
    return df


def drop_duplicate_keys(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Keep one row per stop_events key, preferring the row that has an actual.

    The raw files are not perfectly unique on the key (two trips can share a
    stop and scheduled minute). The database would keep whichever row arrived
    first; sorting first makes that choice deterministic and sensible.
    """
    ordered = df.assign(_no_actual=df["actual"].isna()).sort_values(
        KEY + ["_no_actual", "time_point_order", "half_trip_id"], kind="stable"
    )
    deduped = ordered.drop_duplicates(KEY, keep="first").drop(columns="_no_actual")
    return deduped, len(df) - len(deduped)
