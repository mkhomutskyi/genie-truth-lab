"""Create and validate the reviewed Genie Truth Lab Metric View."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from databricks_sql import execute_sql

ROOT = Path(__file__).resolve().parents[1]
DEFINITION_PATH = ROOT / "deploy" / "booking_metrics.metric_view.sql"
VIEW_NAME = "genie_truth_lab_booking_metrics"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", required=True)
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--schema", required=True)
    parser.add_argument(
        "--warehouse-id",
        required=True,
        help="ID of an existing SQL warehouse. The script creates no compute.",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    qualified_name = f"{args.catalog}.{args.schema}.{VIEW_NAME}"
    existing = execute_sql(
        args.profile,
        args.warehouse_id,
        f"SHOW TABLES IN {args.catalog}.{args.schema} LIKE '{VIEW_NAME}'",
    )
    if existing:
        raise SystemExit(f"Refusing to replace existing object: {qualified_name}")

    definition = (
        DEFINITION_PATH.read_text(encoding="utf-8")
        .replace("${catalog}", args.catalog)
        .replace("${schema}", args.schema)
    )
    execute_sql(args.profile, args.warehouse_id, definition)
    rows = execute_sql(
        args.profile,
        args.warehouse_id,
        (
            "SELECT "
            f"MEASURE({VIEW_NAME}.`Booking Count`) AS booking_count, "
            f"MEASURE({VIEW_NAME}.`Gross Booked Value`) AS gross_booked_value, "
            f"MEASURE({VIEW_NAME}.`Average Stay Nights`) AS average_stay_nights, "
            f"MEASURE({VIEW_NAME}.`Booked Property Count`) AS booked_property_count "
            f"FROM {qualified_name}"
        ),
    )
    if len(rows) != 1:
        raise ValueError(f"Expected one validation row, found {len(rows)}")

    evidence = {
        "schema_version": 1,
        "object": "${catalog}.${schema}.genie_truth_lab_booking_metrics",
        "validation_query_result": rows[0],
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(evidence, indent=2) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
