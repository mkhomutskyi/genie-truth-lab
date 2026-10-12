"""Summarize repeated native scores and separate business-correctness reviews."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


NATIVE_PASS = "GOOD"
BUSINESS_STATUSES = {"PASS", "SAFE_CLARIFICATION", "FAIL", "PENDING"}
CONDITIONS = ("baseline", "treatment", "treatment-optimized")


def rate(passed: int, total: int) -> float | None:
    return round(passed / total, 4) if total else None


def summarize_slice(rows: list[dict[str, Any]]) -> dict[str, Any]:
    native_passes = sum(row["assessment"] == NATIVE_PASS for row in rows)
    business_rows = [
        row for row in rows if row["business_review"]["status"] != "PENDING"
    ]
    business_passes = sum(
        row["business_review"]["status"] == "PASS" for row in business_rows
    )
    safe_clarifications = sum(
        row["business_review"]["status"] == "SAFE_CLARIFICATION"
        for row in business_rows
    )
    return {
        "native": {
            "passed": native_passes,
            "total": len(rows),
            "rate": rate(native_passes, len(rows)),
            "assessment_counts": dict(
                sorted(Counter(row["assessment"] for row in rows).items())
            ),
        },
        "mixed_review": {
            "classified": len(business_rows),
            "pending": len(rows) - len(business_rows),
            "passed": business_passes,
            "safe_clarifications": safe_clarifications,
            "failed": len(business_rows) - business_passes - safe_clarifications,
            "pass_rate_among_classified": rate(business_passes, len(business_rows)),
            "manual_native_failure_reviews": sum(
                row["business_review"].get("review_method")
                == "MANUAL_NATIVE_FAILURE_REVIEW"
                for row in business_rows
            ),
            "automated_sql_guardrails": sum(
                row["business_review"].get("review_method")
                == "AUTOMATED_SQL_GUARDRAIL"
                for row in business_rows
            ),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reviews", type=Path)
    parser.add_argument("--allow-partial", action="store_true")
    args = parser.parse_args()

    runs = []
    for path in sorted(args.input_dir.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        key = (payload["condition"], payload["repetition"])
        runs.append((key, payload, path))

    full_expected = {
        (condition, repetition)
        for condition in CONDITIONS
        for repetition in (1, 2, 3)
    }
    observed = {key for key, _, _ in runs}
    if len(observed) != len(runs):
        raise ValueError("Duplicate condition and repetition files found")
    unknown_conditions = {condition for condition, _ in observed} - set(CONDITIONS)
    if unknown_conditions:
        raise ValueError(f"Unknown conditions: {sorted(unknown_conditions)}")
    observed_conditions = {condition for condition, _ in observed}
    complete_observed_conditions = {
        (condition, repetition)
        for condition in observed_conditions
        for repetition in (1, 2, 3)
    }
    if not args.allow_partial and observed != complete_observed_conditions:
        raise ValueError(
            "Each observed condition requires repetitions 1, 2, and 3; "
            f"expected {sorted(complete_observed_conditions)}, found {sorted(observed)}"
        )

    review_lookup: dict[tuple[str, int, str], dict[str, str]] = {}
    if args.reviews:
        review_payload = json.loads(args.reviews.read_text(encoding="utf-8"))
        for review in review_payload["reviews"]:
            key = (
                review["condition"],
                review["repetition"],
                review["prompt_id"],
            )
            if key in review_lookup:
                raise ValueError(f"Duplicate business review {key}")
            review_lookup[key] = {
                "status": review["status"],
                "notes": review["notes"],
                "review_method": review.get("review_method", "UNSPECIFIED"),
            }

    rows = []
    for (condition, repetition), payload, path in runs:
        if payload["summary"]["status"] != "DONE":
            raise ValueError(f"{path} is not complete")
        for question in payload["questions"]:
            review = review_lookup.get(
                (condition, repetition, question["prompt_id"]),
                {
                    **question["business_review"],
                    "review_method": question["business_review"].get(
                        "review_method", "UNSPECIFIED"
                    ),
                },
            )
            business_status = review["status"]
            if business_status not in BUSINESS_STATUSES:
                raise ValueError(
                    f"{path}: invalid business review status {business_status}"
                )
            rows.append(
                {
                    "condition": condition,
                    "repetition": repetition,
                    **{**question, "business_review": review},
                }
            )

    by_condition = {
        condition: summarize_slice(
            [row for row in rows if row["condition"] == condition]
        )
        for condition in CONDITIONS
        if any(row["condition"] == condition for row in rows)
    }
    by_condition_and_cohort = {}
    by_condition_and_split = {}
    for condition in by_condition:
        by_condition_and_cohort[condition] = {
            cohort: summarize_slice(
                [
                    row
                    for row in rows
                    if row["condition"] == condition and row["cohort"] == cohort
                ]
            )
            for cohort in ("control", "treatment")
        }
        by_condition_and_split[condition] = {
            split: summarize_slice(
                [
                    row
                    for row in rows
                    if row["condition"] == condition and row["split"] == split
                ]
            )
            for split in ("development", "holdout")
        }

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(row["condition"], row["prompt_id"])].append(row)

    stability = {}
    for condition in by_condition:
        prompt_results = []
        for (row_condition, prompt_id), prompt_rows in grouped.items():
            if row_condition != condition:
                continue
            native_passes = sum(
                row["assessment"] == NATIVE_PASS for row in prompt_rows
            )
            prompt_results.append(
                {
                    "prompt_id": prompt_id,
                    "family_id": prompt_rows[0]["family_id"],
                    "cohort": prompt_rows[0]["cohort"],
                    "split": prompt_rows[0]["split"],
                    "passes": native_passes,
                    "runs": len(prompt_rows),
                }
            )
        complete_prompts = [
            result for result in prompt_results if result["runs"] == 3
        ]
        stability[condition] = {
            "prompts": sorted(prompt_results, key=lambda item: item["prompt_id"]),
            "three_of_three": sum(
                result["passes"] == 3 for result in complete_prompts
            ),
            "two_or_more_of_three": sum(
                result["passes"] >= 2 for result in complete_prompts
            ),
            "complete_prompt_count": len(complete_prompts),
        }

    baseline_treatment_rate = (
        by_condition_and_cohort.get("baseline", {})
        .get("treatment", {})
        .get("native", {})
        .get("rate")
    )
    treatment_treatment_rate = (
        by_condition_and_cohort.get("treatment", {})
        .get("treatment", {})
        .get("native", {})
        .get("rate")
    )
    treatment_improvement = (
        round(treatment_treatment_rate - baseline_treatment_rate, 4)
        if baseline_treatment_rate is not None
        and treatment_treatment_rate is not None
        else None
    )

    summary = {
        "schema_version": 1,
        "run_count": len(runs),
        "question_run_count": len(rows),
        "by_condition": by_condition,
        "by_condition_and_cohort": by_condition_and_cohort,
        "by_condition_and_split": by_condition_and_split,
        "stability": stability,
        "evidence_status": (
            "COMPLETE"
            if runs
            and observed == full_expected
            and all(
                row["business_review"]["status"] != "PENDING" for row in rows
            )
            else "INCOMPLETE"
        ),
        "declared_target": {
            "treatment_prompt_improvement_threshold": 0.25,
            "observed_treatment_prompt_improvement": treatment_improvement,
            "threshold_met": (
                treatment_improvement >= 0.25
                if treatment_improvement is not None
                else None
            ),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Summarized {len(runs)} runs and {len(rows)} question-runs")


if __name__ == "__main__":
    main()
