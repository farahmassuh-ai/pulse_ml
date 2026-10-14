import pandas as pd

from transform import (add_delay_and_label, drop_duplicate_keys, parse_wallclock,
                       transform_historical)


def _raw(**overrides):
    row = {
        "service_date": "2026-04-01", "route_id": "01", "direction_id": "Inbound",
        "half_trip_id": "70391179", "stop_id": "64", "time_point_id": "nubn",
        "time_point_order": "1", "point_type": "Endpoint", "standard_type": "Headway",
        "scheduled": "1900-01-01T17:18:00Z", "actual": "1900-01-01T17:24:49Z",
        "scheduled_headway": None, "headway": None,
    }
    row.update(overrides)
    return row


def test_file_times_move_onto_service_date_and_keep_wall_clock():
    day = pd.Series(pd.to_datetime(["2026-04-01"]))
    out = parse_wallclock(pd.Series(["1900-01-01T17:18:00Z"]), day)
    assert out[0] == pd.Timestamp("2026-04-01 17:18:00")     # 'Z' ignored, not converted


def test_after_midnight_lands_on_next_day():
    day = pd.Series(pd.to_datetime(["2026-04-30"]))
    out = parse_wallclock(pd.Series(["1900-01-02T00:20:00Z"]), day)
    assert out[0] == pd.Timestamp("2026-05-01 00:20:00")


def test_api_offsets_keep_local_clock_in_summer_and_winter():
    day = pd.Series(pd.to_datetime(["2026-09-07", "2026-12-07"]))
    out = parse_wallclock(pd.Series(["2026-09-07T18:00:00-04:00", "2026-12-07T18:00:00-05:00"]), day)
    assert list(out) == [pd.Timestamp("2026-09-07 18:00"), pd.Timestamp("2026-12-07 18:00")]


def test_garbage_time_becomes_nat():
    day = pd.Series(pd.to_datetime(["2026-04-01"]))
    assert pd.isna(parse_wallclock(pd.Series(["N/A"]), day)[0])


def test_delay_and_late_label():
    df = transform_historical(pd.DataFrame([
        _raw(actual="1900-01-01T17:21:00Z"),   # exactly 3 min -> not late
        _raw(actual="1900-01-01T17:21:01Z"),   # just over 3 min -> late
        _raw(actual=None),                     # no actual -> unknown
    ], dtype="string"))
    assert df["delay_min"].iloc[0] == 3.0
    assert df["late"].iloc[0] == False  # noqa: E712
    assert df["late"].iloc[1] == True   # noqa: E712
    assert pd.isna(df["late"].iloc[2]) and pd.isna(df["delay_min"].iloc[2])


def test_delay_across_midnight():
    df = transform_historical(pd.DataFrame([
        _raw(scheduled="1900-01-01T23:58:00Z", actual="1900-01-02T00:03:00Z"),
    ], dtype="string"))
    assert df["delay_min"].iloc[0] == 5.0


def test_duplicate_key_keeps_row_with_actual():
    df = transform_historical(pd.DataFrame([
        _raw(half_trip_id="1", actual=None),
        _raw(half_trip_id="2", actual="1900-01-01T17:20:00Z"),
    ], dtype="string"))
    kept, dropped = drop_duplicate_keys(df)
    assert dropped == 1
    assert kept["half_trip_id"].iloc[0] == "2"


def test_label_is_null_without_actual_even_with_api_shape():
    df = pd.DataFrame({"scheduled": [pd.Timestamp("2026-10-14 08:00")], "actual": [pd.NaT]})
    out = add_delay_and_label(df)
    assert pd.isna(out["late"].iloc[0])
