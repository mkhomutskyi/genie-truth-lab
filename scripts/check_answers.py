"""Execute the checked SQL answers and save a reproducible evidence snapshot."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from databricks_sql import execute_sql

ROOT = Path(__file__).resolve().parents[1]
SQL_PATH = ROOT / "sql" / "02_gold_answers.sql"
OUTPUT_PATH = ROOT / "local" / "checked-answers.json"
QUERY_IDS = (
    "monthly-booking-volume",
    "monthly-gross-booked-value",
    "booking-status-mix",
    "property-gross-booked-value",
    "average-stay-length",
    "booked-property-type-mix",
)


def load_statements() -> list[str]:
    sql_without_comments = "\n".join(
        line
        for line in SQL_PATH.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("--")
    )
    statements = [
        statement.strip()
        for statement in sql_without_comments.split(";")
        if statement.strip()
    ]
    if len(statements) != len(QUERY_IDS):
        raise ValueError(
            f"Expected {len(QUERY_IDS)} SQL statements, found {len(statements)}"
        )
    return statements


def canonical_hash(rows: list[dict[str, Any]]) -> str:
    payload = json.dumps(
        rows, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--profile",
        required=True,
        help="Local Databricks CLI profile. It is never written to the snapshot.",
    )
    parser.add_argument(
        "--warehouse-id",
        required=True,
        help="ID of an existing SQL warehouse. The script creates no compute.",
    )
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    args = parser.parse_args()

    results = []
    for query_id, statement in zip(QUERY_IDS, load_statements(), strict=True):
        rows = execute_sql(args.profile, args.warehouse_id, statement)
        if len(rows) > 5_000:
            raise ValueError(f"{query_id} exceeds the 5,000-row benchmark limit")
        results.append(
            {
                "query_id": query_id,
                "sql": statement,
                "row_count": len(rows),
                "sha256": canonical_hash(rows),
                "rows": rows,
            }
        )
        print(f"{query_id}: {len(rows)} rows")

    snapshot = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "samples.wanderbricks",
        "queries": results,
    }
    output_path = args.output.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Saved {output_path}")


if __name__ == "__main__":
    main()
