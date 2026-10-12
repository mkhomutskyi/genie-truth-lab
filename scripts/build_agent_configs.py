"""Build deterministic baseline and treatment Genie Agent configurations."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "benchmarks" / "manifest.json"
OUTPUT_DIR = ROOT / "agents"
ID_NAMESPACE = uuid.UUID("56fb5c3b-5f41-5ec2-81c0-c807ba0b7b31")

TEXT_INSTRUCTIONS = """## PURPOSE
- Answer questions about booking activity in the public Wanderbricks sample data.
- The audience understands basic travel and lodging terms.

## DISAMBIGUATION
- If a user asks for revenue without defining the booking status or accounting treatment, ask which definition they mean. Do not assume a booking amount is recognized revenue.

## DATA QUALITY NOTES
- The source does not declare a currency for monetary values.
- One booking row has a negative total_amount value.

## CONSTRAINTS
- Never label a monetary result as USD or another currency unless the user supplies that context.

## Instructions you must follow when providing summaries
- State the filters and date range used when they are not obvious from the question."""


def stable_id(name: str) -> str:
    return uuid.uuid5(ID_NAMESPACE, name).hex


def benchmark_questions(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    questions = []
    for family in manifest["families"]:
        for prompt in family["prompts"]:
            questions.append(
                {
                    "id": stable_id(f"benchmark:{prompt['id']}"),
                    "question": [prompt["text"]],
                    "answer": [
                        {
                            "format": "SQL",
                            "content": [family["expected_sql"]],
                        }
                    ],
                }
            )
    return sorted(questions, key=lambda item: item["id"])


def baseline_config(benchmarks: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "version": 2,
        "data_sources": {
            "tables": [
                {
                    "identifier": "samples.wanderbricks.bookings",
                    "column_configs": sorted(
                        [
                            {
                                "column_name": "check_in",
                                "description": ["Scheduled check-in date."],
                                "synonyms": ["arrival date", "stay start"],
                            },
                            {
                                "column_name": "check_out",
                                "description": ["Scheduled check-out date."],
                                "synonyms": ["departure date", "stay end"],
                            },
                            {
                                "column_name": "created_at",
                                "exclude": True,
                            },
                            {
                                "column_name": "guests_count",
                                "exclude": True,
                            },
                            {
                                "column_name": "property_id",
                                "description": [
                                    "Property identifier used to join bookings to properties."
                                ],
                                "synonyms": ["listing ID"],
                            },
                            {
                                "column_name": "status",
                                "description": [
                                    "Current booking status: pending, confirmed, cancelled, or completed."
                                ],
                                "synonyms": ["booking status", "reservation status"],
                                "enable_format_assistance": True,
                                "enable_entity_matching": True,
                            },
                            {
                                "column_name": "total_amount",
                                "description": [
                                    "Amount stored on the booking record. The source declares no currency."
                                ],
                                "synonyms": ["booking amount"],
                            },
                            {
                                "column_name": "updated_at",
                                "exclude": True,
                            },
                            {
                                "column_name": "user_id",
                                "exclude": True,
                            },
                        ],
                        key=lambda item: item["column_name"],
                    ),
                },
                {
                    "identifier": "samples.wanderbricks.properties",
                    "column_configs": sorted(
                        [
                            {"column_name": "base_price", "exclude": True},
                            {"column_name": "bathrooms", "exclude": True},
                            {"column_name": "bedrooms", "exclude": True},
                            {"column_name": "created_at", "exclude": True},
                            {"column_name": "description", "exclude": True},
                            {"column_name": "destination_id", "exclude": True},
                            {"column_name": "host_id", "exclude": True},
                            {"column_name": "max_guests", "exclude": True},
                            {
                                "column_name": "property_id",
                                "description": [
                                    "Unique property identifier; one row per property."
                                ],
                                "synonyms": ["listing ID"],
                            },
                            {"column_name": "property_latitude", "exclude": True},
                            {"column_name": "property_longitude", "exclude": True},
                            {
                                "column_name": "property_type",
                                "description": ["Category of the property listing."],
                                "synonyms": ["listing type", "property category"],
                                "enable_format_assistance": True,
                                "enable_entity_matching": True,
                            },
                            {
                                "column_name": "title",
                                "description": ["Public title of the property listing."],
                                "synonyms": ["property name", "listing title"],
                            },
                        ],
                        key=lambda item: item["column_name"],
                    ),
                },
            ]
        },
        "instructions": {
            "join_specs": [
                {
                    "id": stable_id("join:bookings-properties"),
                    "left": {
                        "identifier": "samples.wanderbricks.bookings",
                        "alias": "bookings",
                    },
                    "right": {
                        "identifier": "samples.wanderbricks.properties",
                        "alias": "properties",
                    },
                    "sql": [
                        "`bookings`.`property_id` = `properties`.`property_id`",
                        "--rt=FROM_RELATIONSHIP_TYPE_MANY_TO_ONE--",
                    ],
                }
            ],
            "text_instructions": [
                {
                    "id": stable_id("instruction:shared"),
                    "content": [TEXT_INSTRUCTIONS],
                }
            ],
        },
        "benchmarks": {"questions": benchmarks},
    }


def treatment_config(benchmarks: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "version": 2,
        "data_sources": {
            "metric_views": [
                {
                    "identifier": (
                        "${catalog}.${schema}.genie_truth_lab_booking_metrics"
                    ),
                    "column_configs": [
                        {
                            "column_name": "Average Stay Nights",
                            "description": [
                                "Average number of nights between check-in and check-out across booking records."
                            ],
                            "synonyms": [
                                "average stay length",
                                "mean nights",
                                "average nights",
                            ],
                        },
                        {
                            "column_name": "Booked Property Count",
                            "description": [
                                "Distinct properties that appear in at least one booking record."
                            ],
                            "synonyms": [
                                "booked listing count",
                                "unique booked properties",
                            ],
                        },
                        {
                            "column_name": "Booking Count",
                            "description": [
                                "Count of booking records, including every status unless the query filters status."
                            ],
                            "synonyms": [
                                "booking volume",
                                "reservation count",
                                "number of bookings",
                            ],
                        },
                        {
                            "column_name": "Booking Month",
                            "description": [
                                "Calendar month of the booking check-in date."
                            ],
                            "synonyms": ["check-in month", "stay month"],
                        },
                        {
                            "column_name": "Booking Status",
                            "description": [
                                "Current booking status: pending, confirmed, cancelled, or completed."
                            ],
                            "synonyms": ["status", "reservation status"],
                            "enable_format_assistance": True,
                            "enable_entity_matching": True,
                        },
                        {
                            "column_name": "Gross Booked Value",
                            "description": [
                                "Sum of total_amount across booking records. This is booked value, not recognized revenue or payment receipts. The source declares no currency."
                            ],
                            "synonyms": [
                                "GBV",
                                "booking value",
                                "total booking value",
                                "gross booking value",
                            ],
                        },
                        {
                            "column_name": "Property ID",
                            "description": [
                                "Unique property identifier recorded on a booking."
                            ],
                            "synonyms": ["listing ID"],
                        },
                        {
                            "column_name": "Property Title",
                            "description": ["Public title of the property listing."],
                            "synonyms": [
                                "property name",
                                "listing",
                                "listing title",
                            ],
                        },
                        {
                            "column_name": "Property Type",
                            "description": ["Category of the property listing."],
                            "synonyms": ["listing type", "property category"],
                            "enable_format_assistance": True,
                            "enable_entity_matching": True,
                        },
                    ],
                }
            ]
        },
        "instructions": {
            "text_instructions": [
                {
                    "id": stable_id("instruction:shared"),
                    "content": [TEXT_INSTRUCTIONS],
                }
            ]
        },
        "benchmarks": {"questions": benchmarks},
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    benchmarks = benchmark_questions(manifest)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    write_json(OUTPUT_DIR / "baseline.serialized_space.json", baseline_config(benchmarks))
    treatment = treatment_config(benchmarks)
    write_json(
        OUTPUT_DIR / "treatment.serialized_space.json",
        treatment,
    )
    optimized = treatment_config(benchmarks)
    optimized_columns = optimized["data_sources"]["metric_views"][0]["column_configs"]
    for column in optimized_columns:
        if column["column_name"] == "Property ID":
            column["description"] = [
                "Unique property grain. Always include and group by Property ID when a question asks for each property or listing."
            ]
            column["synonyms"] = ["listing ID", "property ID", "listing"]
        elif column["column_name"] == "Property Title":
            column["description"] = [
                "Non-unique display label. Never group or rank listings by Property Title alone; include Property ID."
            ]
            column["synonyms"] = ["property name", "listing title"]
    write_json(
        OUTPUT_DIR / "treatment-optimized.serialized_space.json",
        optimized,
    )
    print(f"Built three Agent configurations with {len(benchmarks)} benchmarks each")


if __name__ == "__main__":
    main()
