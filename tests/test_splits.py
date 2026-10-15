import pandas as pd
import pytest

from make_splits import check_order, prepare, split_by_time


def _rows(dates_and_times):
    return prepare(pd.DataFrame({
        "service_date": [d for d, _ in dates_and_times],
        "route_id": "01", "direction_id": "Inbound", "stop_id": "64", "time_point_id": "nubn",
        "scheduled": [t for _, t in dates_and_times],
        "scheduled_headway": None, "point_type": "Midpoint", "standard_type": "Schedule",
        "time_point_order": 1, "late": "t",
    }))


def test_split_uses_last_month_halves():
    df = _rows([("2026-04-10", "2026-04-10 08:00"), ("2026-05-31", "2026-06-01 00:30"),
                ("2026-06-15", "2026-06-15 09:00"), ("2026-06-16", "2026-06-16 09:00")])
    s = split_by_time(df)
    assert len(s["train"]) == 2 and len(s["val"]) == 1 and len(s["test"]) == 1
    check_order(s)   # the after-midnight May 31 trip still ends before June 1 service


def test_overlap_is_caught():
    df = _rows([("2026-05-31", "2026-06-01 09:00"), ("2026-06-01", "2026-06-01 08:00"),
                ("2026-06-20", "2026-06-20 08:00")])
    with pytest.raises(AssertionError):
        check_order(split_by_time(df))


def test_calendar_features_come_from_scheduled():
    df = _rows([("2026-06-15", "2026-06-15 17:45")])
    row = df.iloc[0]
    assert (row["day_of_week"], row["hour"], row["minute_of_day"]) == (0, 17, 17 * 60 + 45)
    assert bool(row["late"]) is True


def test_one_month_is_not_enough():
    df = _rows([("2026-06-01", "2026-06-01 08:00"), ("2026-06-20", "2026-06-20 08:00")])
    with pytest.raises(ValueError):
        split_by_time(df)
