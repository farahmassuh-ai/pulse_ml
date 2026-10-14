"""Step 2: append today's planned bus service from the MBTA API to stop_events.

Run from the repo root:
    python src/pull_daily.py                    # today's service (Boston time)
    python src/pull_daily.py --date 2026-10-15  # a specific date in the current timetable

1. Routes = the distinct route_ids in the historical rows, translated to API ids.
2. One GET /schedules request per route, inside the rate limit.
3. Each record mapped into the files' vocabulary (route, direction word, stop).
4. Only timepoint stops kept: (route, direction, stop) combinations that appear
   in the historical rows, which also supply time_point_id / order / point_type.
5. actual, delay_min and late stay NULL; source = 'api'. Insert, log one verdict line.
Safe to rerun: a second run on the same day inserts 0 rows.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests

from db import insert_stop_events, query
from mbta_api import (bus_route_lookup, get_json, schedules_to_records,
                      seconds_between_requests, to_api_route)
from transform import drop_duplicate_keys, finalize_dates, parse_wallclock
from validate import check_batch, check_rows

ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / "logs"
BOSTON = ZoneInfo("America/New_York")

TIMEPOINTS_SQL = """
    SELECT DISTINCT ON (route_id, direction_id, stop_id)
           route_id, direction_id, stop_id, time_point_id, time_point_order, point_type
    FROM (
        SELECT route_id, direction_id, stop_id, time_point_id, time_point_order,
               point_type, COUNT(*) AS n
        FROM stop_events
        WHERE source = 'historical'
        GROUP BY 1, 2, 3, 4, 5, 6
    ) t
    ORDER BY route_id, direction_id, stop_id, n DESC
"""

SAME_WEEKDAY_COUNTS_SQL = """
    SELECT service_date, COUNT(*)
    FROM stop_events
    WHERE source = 'historical' AND EXTRACT(ISODOW FROM service_date) = %s
    GROUP BY service_date
"""


def setup_logging():
    LOG_DIR.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M",
        handlers=[logging.FileHandler(LOG_DIR / "pull_daily.log"), logging.StreamHandler()],
    )


def fetch_records(file_routes, service_date: date, session) -> tuple[list[dict], dict]:
    lookup = bus_route_lookup(session=session)
    pause = seconds_between_requests()
    records, unknown, no_service = [], [], []
    for file_route in file_routes:
        route = to_api_route(file_route, lookup)
        if route is None:
            unknown.append(file_route)
            continue
        time.sleep(pause)
        payload = get_json("/schedules", {"filter[route]": route["id"],
                                          "filter[date]": service_date.isoformat()},
                           session=session)
        found = schedules_to_records(payload["data"], file_route, route["direction_names"])
        if not found:
            no_service.append(file_route)
        records.extend(found)
    return records, {"unknown": unknown, "no_service": no_service}


def to_stop_events(records: list[dict], timepoints: pd.DataFrame, service_date: date):
    """API records -> stop_events rows, timepoint stops only."""
    df = pd.DataFrame(records, columns=["route_id", "direction_id", "stop_id",
                                        "half_trip_id", "scheduled_raw"])
    kept = df.merge(timepoints, on=["route_id", "direction_id", "stop_id"], how="inner")
    day = pd.Series(pd.Timestamp(service_date), index=kept.index)
    kept["service_date"] = day
    kept["scheduled"] = parse_wallclock(kept["scheduled_raw"], day)
    kept["actual"] = pd.NaT
    kept["delay_min"] = float("nan")
    kept["late"] = pd.array([pd.NA] * len(kept), dtype="boolean")
    kept["standard_type"] = None
    kept["scheduled_headway"] = pd.array([pd.NA] * len(kept), dtype="Int64")
    return kept.drop(columns="scheduled_raw")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--date", type=date.fromisoformat,
                        default=datetime.now(BOSTON).date(),
                        help="service date YYYY-MM-DD (default: today in Boston)")
    service_date = parser.parse_args(argv).date
    setup_logging()

    try:
        file_routes = [r for (r,) in query(
            "SELECT DISTINCT route_id FROM stop_events WHERE source = 'historical' ORDER BY 1")]
        if not file_routes:
            raise RuntimeError("no historical rows yet: run src/load_historical.py first")
        timepoints = pd.DataFrame(query(TIMEPOINTS_SQL), columns=[
            "route_id", "direction_id", "stop_id", "time_point_id", "time_point_order", "point_type"])
        timepoints["time_point_order"] = timepoints["time_point_order"].astype("Int64")

        with requests.Session() as session:
            records, skipped = fetch_records(file_routes, service_date, session)

        rows = to_stop_events(records, timepoints, service_date)
        good, rejected = check_rows(rows)
        good, duplicates = drop_duplicate_keys(good)
        inserted = insert_stop_events(finalize_dates(good), source="api")

        same_weekday = [n for (_, n) in query(SAME_WEEKDAY_COUNTS_SQL, (service_date.isoweekday(),))]
        warning = check_batch(len(good), same_weekday)
    except Exception:
        logging.exception("FAILED %s: nothing new is guaranteed loaded; rerun is safe", service_date)
        return 1

    requested = len(file_routes) - len(skipped["unknown"])
    logging.info(
        "%s %s (%s): routes requested %s/%s, fetched %s, timepoint rows kept %s, "
        "rejected %s, duplicate keys %s, inserted %s",
        "WARN" if warning else "OK", service_date, service_date.strftime("%A"),
        requested, len(file_routes), f"{len(records):,}", f"{len(rows):,}",
        len(rejected), duplicates, f"{inserted:,}",
    )
    if skipped["unknown"]:
        logging.info("routes the API doesn't know: %s", ", ".join(skipped["unknown"]))
    if skipped["no_service"]:
        logging.info("routes with no service on %s: %s", service_date, ", ".join(skipped["no_service"]))
    if warning:
        logging.warning("batch check: %s (same weekday in historical data)", warning)
    return 0


if __name__ == "__main__":
    sys.exit(main())
