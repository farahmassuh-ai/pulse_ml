"""Step 1: load the MBTA Bus Arrival/Departure monthly CSVs into stop_events.

Run from the repo root:
    python src/load_historical.py                 # every CSV in data/raw/
    python src/load_historical.py data/raw/X.csv  # specific files

Per file: check schema -> transform -> check rows (rejects quarantined to
data/rejects/) -> check daily counts -> drop duplicate keys -> insert.
Safe to rerun: rows already in the table are skipped by ON CONFLICT DO NOTHING.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import pandas as pd

from db import insert_stop_events
from transform import drop_duplicate_keys, finalize_dates, transform_historical
from validate import check_batch, check_rows, check_schema

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
REJECT_DIR = ROOT / "data" / "rejects"
LOG_DIR = ROOT / "logs"


def setup_logging():
    LOG_DIR.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M",
        handlers=[logging.FileHandler(LOG_DIR / "load_historical.log"),
                  logging.StreamHandler()],
    )


def day_kind(dates: pd.Series) -> pd.Series:
    dow = dates.dt.dayofweek
    return dow.map(lambda d: "Saturday" if d == 5 else "Sunday" if d == 6 else "weekday")


def warn_on_low_days(df: pd.DataFrame, name: str) -> None:
    """Batch check: a day far below the usual count for its kind of day."""
    counts = df.groupby("service_date").size()
    kinds = day_kind(pd.Series(counts.index, index=counts.index))
    for day, count in counts.items():
        same_kind = counts[(kinds == kinds[day]) & (counts.index != day)]
        warning = check_batch(count, same_kind.tolist())
        if warning:
            logging.warning("%s %s: %s", name, day.date(), warning)


def load_file(path: Path) -> dict:
    raw = pd.read_csv(path, dtype=str)
    check_schema(raw)

    df = transform_historical(raw)
    good, rejected = check_rows(df)
    if len(rejected):
        REJECT_DIR.mkdir(parents=True, exist_ok=True)
        rejected.to_csv(REJECT_DIR / f"{path.stem}_rejects.csv", index=False)

    warn_on_low_days(good, path.name)
    good, duplicates = drop_duplicate_keys(good)
    inserted = insert_stop_events(finalize_dates(good), source="historical")

    stats = {
        "file": path.name,
        "raw_rows": len(raw),
        "rejected": len(rejected),
        "duplicate_keys": duplicates,
        "clean_rows": len(good),
        "no_actual": int(good["actual"].isna().sum()),
        "inserted": inserted,
    }
    reasons = rejected["reason"].value_counts().to_dict() if len(rejected) else {}
    logging.info(
        "OK %s: raw %s, rejected %s %s, duplicate keys %s, clean %s "
        "(no actual %s), inserted %s",
        stats["file"], f"{len(raw):,}", f"{len(rejected):,}", reasons,
        f"{duplicates:,}", f"{len(good):,}", f"{stats['no_actual']:,}", f"{inserted:,}",
    )
    return stats


def main(argv):
    setup_logging()
    files = [Path(a) for a in argv] or sorted(RAW_DIR.glob("*.csv"))
    if not files:
        logging.error("No CSV files found in %s", RAW_DIR)
        return 1
    totals = {"raw_rows": 0, "rejected": 0, "duplicate_keys": 0, "clean_rows": 0, "inserted": 0}
    for path in files:
        try:
            stats = load_file(path)
        except Exception:
            logging.exception("FAILED %s: stopped here; fix the cause and rerun "
                              "(rows already loaded are skipped)", path.name)
            return 1
        for k in totals:
            totals[k] += stats[k]
    logging.info("DONE %s file(s): %s", len(files), {k: f"{v:,}" for k, v in totals.items()})
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
