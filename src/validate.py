"""Boundary checks: data earns its way into the database by passing these."""
from __future__ import annotations

import pandas as pd

from transform import DELAY_MAX_OK, DELAY_MIN_OK

# The canonical stop_events fields plus the extra file columns the splits need.
EXPECTED_COLUMNS = {
    "service_date", "route_id", "direction_id", "stop_id",
    "scheduled", "actual", "point_type",
    "half_trip_id", "time_point_id", "time_point_order",
    "standard_type", "scheduled_headway",
}
KNOWN_DIRECTIONS = {"Inbound", "Outbound"}


def check_schema(df: pd.DataFrame, expected=EXPECTED_COLUMNS) -> None:
    """Halt policy: a missing column means the provider changed its format."""
    missing = set(expected) - set(df.columns)
    if missing:
        raise ValueError(f"Upstream schema changed! Missing: {sorted(missing)}")


def check_rows(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Quarantine policy: returns (good_rows, rejected_rows with a `reason`).

    Runs on transformed rows (timestamps parsed, delay computed).
    A missing actual is NOT an error: the label is simply unknown.
    """
    reason = pd.Series(pd.NA, index=df.index, dtype="string")

    def flag(mask, text):
        nonlocal reason
        reason = reason.mask(reason.isna() & mask.fillna(True).astype(bool), text)

    flag(df["service_date"].isna(), "service_date not a date")
    flag(df["scheduled"].isna(), "scheduled not a timestamp")
    for col in ["route_id", "stop_id"]:
        flag(df[col].isna() | (df[col] == ""), f"{col} empty")
    flag(~df["direction_id"].isin(KNOWN_DIRECTIONS), "direction_id unknown")
    has_actual = df["actual"].notna()
    out_of_range = has_actual & ((df["delay_min"] < DELAY_MIN_OK) | (df["delay_min"] > DELAY_MAX_OK))
    flag(out_of_range, f"delay outside [{DELAY_MIN_OK}, +{DELAY_MAX_OK}] min")

    bad = reason.notna()
    return df[~bad], df[bad].assign(reason=reason[bad])


def check_batch(count: int, reference_counts, min_ratio: float = 0.5):
    """Flag policy: returns a warning string if `count` collapsed, else None.

    Compares against the median of comparable earlier counts (same kind of day).
    """
    reference = [c for c in reference_counts if c]
    if not reference:
        return None
    median = float(pd.Series(reference).median())
    if count < min_ratio * median:
        return f"row count {count:,} is below {min_ratio:.0%} of the usual {median:,.0f}"
    return None
