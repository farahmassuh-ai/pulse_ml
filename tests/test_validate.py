import pandas as pd
import pytest

from transform import transform_historical
from validate import check_batch, check_rows, check_schema
from test_transform import _raw


def test_missing_column_halts():
    with pytest.raises(ValueError, match="actual"):
        check_schema(pd.DataFrame([_raw()]).drop(columns="actual"))


def test_schema_ok_with_extra_columns():
    check_schema(pd.DataFrame([_raw()]))   # 'headway' is extra and fine


def test_rows_out_of_delay_window_are_quarantined_with_reason():
    df = transform_historical(pd.DataFrame([
        _raw(),                                                   # good
        _raw(stop_id="65", actual="1900-01-01T19:30:00Z"),        # +132 min
        _raw(stop_id="66", actual="1900-01-01T16:40:00Z"),        # -38 min
        _raw(stop_id="67", actual=None),                          # no actual: kept
        _raw(stop_id="68", direction_id="Sideways"),
        _raw(stop_id="69", scheduled="garbage"),
    ], dtype="string"))
    good, rejected = check_rows(df)
    assert list(good["stop_id"]) == ["64", "67"]
    assert len(rejected) == 4
    assert rejected["reason"].str.contains("delay").sum() == 2
    assert set(rejected["reason"]) >= {"direction_id unknown", "scheduled not a timestamp"}


def test_delay_window_edges_are_kept():
    df = transform_historical(pd.DataFrame([
        _raw(actual="1900-01-01T16:48:00Z"),                     # exactly -30
        _raw(stop_id="65", actual="1900-01-01T19:18:00Z"),        # exactly +120
    ], dtype="string"))
    good, rejected = check_rows(df)
    assert len(good) == 2 and len(rejected) == 0


def test_batch_collapse_is_flagged():
    assert check_batch(10_000, [80_000, 82_000, 79_000]) is not None
    assert check_batch(78_000, [80_000, 82_000, 79_000]) is None
    assert check_batch(5, []) is None
