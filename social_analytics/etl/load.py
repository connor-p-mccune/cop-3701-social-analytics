"""Load the CSV files in data/ into Oracle.

The load runs as a single transaction. Existing rows are deleted (children
first), new rows are batch-inserted (parents first), row counts are checked
against the CSVs, and the HASHTAG_DAILY_STATS rollup is rebuilt before
anything is committed. A failed load leaves the previous data untouched.

Usage:
    python -m social_analytics load [--data-dir data]
"""

from __future__ import annotations

import argparse
import csv
import time
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import oracledb

from ..config import DATA_DIR
from ..db import connect
from .preprocess import CSV_HEADERS, TIMESTAMP_FORMAT

BATCH_SIZE = 5_000

# CSV_HEADERS lists tables parents-first, which is the insert order.
LOAD_ORDER = list(CSV_HEADERS)


def convert(column: str, value: str):
    """Convert a CSV string to the Python type bound for its column."""
    if value == "":
        return None
    if column.endswith("_id"):
        return int(value)
    if column.endswith("_at"):
        return datetime.strptime(value, TIMESTAMP_FORMAT)
    if column == "score":
        return Decimal(value)
    return value


def read_rows(path: Path, expected_header: list[str]) -> list[tuple]:
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        header = next(reader)
        if header != expected_header:
            raise ValueError(f"{path.name}: expected columns {expected_header}, found {header}")
        return [tuple(convert(c, v) for c, v in zip(header, row, strict=True)) for row in reader]


def insert_rows(cursor: oracledb.Cursor, table: str, columns: list[str], rows: list[tuple]):
    binds = ", ".join(f":{i}" for i in range(1, len(columns) + 1))
    sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({binds})"
    for start in range(0, len(rows), BATCH_SIZE):
        cursor.executemany(sql, rows[start : start + BATCH_SIZE])


def load(conn: oracledb.Connection, data_dir: Path = DATA_DIR) -> dict[str, int]:
    """Replace all table contents with the CSVs in `data_dir`; return row counts."""
    tables = {name: read_rows(data_dir / f"{name}.csv", CSV_HEADERS[name]) for name in LOAD_ORDER}
    counts: dict[str, int] = {}
    with conn.cursor() as cursor:
        for name in reversed(LOAD_ORDER):
            cursor.execute(f"DELETE FROM {name}")
        for name in LOAD_ORDER:
            insert_rows(cursor, name, CSV_HEADERS[name], tables[name])
            cursor.execute(f"SELECT COUNT(*) FROM {name}")
            (counts[name],) = cursor.fetchone()
            expected = len(tables[name])
            if counts[name] != expected:
                raise RuntimeError(f"{name}: inserted {counts[name]} rows, CSV has {expected}")

        cursor.callproc("refresh_hashtag_stats")
        cursor.execute("SELECT COUNT(*) FROM hashtag_daily_stats")
        (counts["hashtag_daily_stats"],) = cursor.fetchone()
    conn.commit()

    # Refresh optimizer statistics so execution plans reflect the new data.
    # DBMS_STATS commits implicitly, so it runs after the load transaction.
    with conn.cursor() as cursor:
        cursor.callproc("dbms_stats.gather_schema_stats", [conn.username.upper()])
    return counts


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m social_analytics load",
        description="Replace the database contents with the CSV files in data/.",
    )
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    args = parser.parse_args(argv)

    started = time.perf_counter()
    with connect() as conn:
        counts = load(conn, args.data_dir)
    for name, count in counts.items():
        print(f"{name:>19}: {count:>7,} rows")
    print(f"Loaded in {time.perf_counter() - started:.1f}s")
