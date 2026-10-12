"""Create a blank business-review ledger for a new set of run exports."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    reviews: list[dict[str, Any]] = []
    seen = set()
    for path in sorted(args.input_dir.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for question in payload["questions"]:
            key = (
                payload["condition"],
                payload["repetition"],
                question["prompt_id"],
            )
            if key in seen:
                raise ValueError(f"Duplicate question-run: {key}")
            seen.add(key)
            reviews.append(
                {
                    "condition": payload["condition"],
                    "repetition": payload["repetition"],
                    "prompt_id": question["prompt_id"],
                    "native_assessment": question["assessment"],
                    "status": "PENDING",
                    "notes": "",
                }
            )

    ledger = {
        "schema_version": 1,
        "rubric": {
            "PASS": "Correctly fulfills the business request for the declared contract.",
            "SAFE_CLARIFICATION": (
                "Avoids an unsupported assumption but does not complete the request."
            ),
            "FAIL": "Uses incorrect semantics, grain, filters, units, or results.",
            "PENDING": "Not reviewed yet.",
        },
        "reviews": sorted(
            reviews,
            key=lambda item: (
                item["condition"],
                item["repetition"],
                item["prompt_id"],
            ),
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(ledger, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Created {len(reviews)} pending business reviews")


if __name__ == "__main__":
    main()
