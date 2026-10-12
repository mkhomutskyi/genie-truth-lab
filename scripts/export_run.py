"""Export one completed Genie evaluation to a local run file."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "benchmarks" / "manifest.json"
SOURCE_PROFILE_PATH = ROOT / "local" / "source-profile.json"
GOLD_ANSWERS_PATH = ROOT / "local" / "checked-answers.json"
METRIC_VIEW_PATH = ROOT / "deploy" / "booking_metrics.metric_view.sql"


def file_sha256(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def cli(profile: str, *args: str) -> dict[str, Any]:
    result = subprocess.run(
        ["databricks", *args, "--profile", profile, "--output", "json"],
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return json.loads(result.stdout)


def redact_text(value: str, catalog: str, schema: str) -> str:
    return (
        value.replace(f"`{catalog}`.`{schema}`", "`${catalog}`.`${schema}`")
        .replace(f"{catalog}.{schema}", "${catalog}.${schema}")
        .replace(catalog, "${catalog}")
        .replace(schema, "${schema}")
    )


def compact_response(
    responses: list[dict[str, Any]] | None, catalog: str, schema: str
) -> list[dict[str, Any]]:
    compact = []
    for item in responses or []:
        execution = item.get("sql_execution_result", {})
        manifest = execution.get("manifest", {})
        status = execution.get("status", {})
        compact.append(
            {
                "response_type": item.get("response_type"),
                "response": redact_text(item.get("response", ""), catalog, schema),
                "execution": {
                    "state": status.get("state"),
                    "row_count": manifest.get("total_row_count"),
                    "truncated": manifest.get("truncated"),
                },
            }
        )
    return compact


def prompt_metadata() -> dict[str, dict[str, str]]:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    metadata = {}
    for family in manifest["families"]:
        for prompt in family["prompts"]:
            metadata[prompt["text"]] = {
                "prompt_id": prompt["id"],
                "family_id": family["id"],
                "cohort": family["cohort"],
                "split": prompt["split"],
            }
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", required=True)
    parser.add_argument("--space-id", required=True)
    parser.add_argument("--eval-run-id", required=True)
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--schema", required=True)
    parser.add_argument(
        "--workspace-type",
        required=True,
        help="Public label such as 'Free Edition' or 'existing Databricks sandbox'.",
    )
    parser.add_argument(
        "--condition",
        choices=("baseline", "treatment", "treatment-optimized"),
        required=True,
    )
    parser.add_argument("--repetition", type=int, choices=(1, 2, 3), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-profile", type=Path, default=SOURCE_PROFILE_PATH)
    parser.add_argument("--checked-answers", type=Path, default=GOLD_ANSWERS_PATH)
    args = parser.parse_args()
    if not args.checked_answers.is_file():
        parser.error("Run scripts/check_answers.py first, or provide --checked-answers.")

    run = cli(
        args.profile,
        "genie",
        "genie-get-eval-run",
        args.space_id,
        args.eval_run_id,
    )
    if run.get("eval_run_status") != "DONE":
        raise SystemExit(f"Evaluation is not complete: {run.get('eval_run_status')}")

    space = cli(
        args.profile,
        "genie",
        "get-space",
        args.space_id,
        "--include-serialized-space",
    )
    serialized = json.loads(space["serialized_space"])
    config_sha256 = hashlib.sha256(
        json.dumps(serialized, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()

    metadata = prompt_metadata()
    listing = cli(
        args.profile,
        "genie",
        "genie-list-eval-results",
        args.space_id,
        args.eval_run_id,
        "--page-size",
        "100",
    )
    questions: list[dict[str, Any]] = []
    for item in listing["eval_results"]:
        question = item["question"]
        if question not in metadata:
            raise ValueError(f"Evaluation returned an unknown question: {question}")
        detail = cli(
            args.profile,
            "genie",
            "genie-get-eval-result-details",
            args.space_id,
            args.eval_run_id,
            item["result_id"],
        )
        questions.append(
            {
                **metadata[question],
                "question": question,
                "assessment": detail.get("assessment"),
                "actual_response": compact_response(
                    detail.get("actual_response"), args.catalog, args.schema
                ),
                "expected_response": compact_response(
                    detail.get("expected_response"), args.catalog, args.schema
                ),
                "business_review": {"status": "PENDING", "notes": ""},
            }
        )

    created = datetime.fromtimestamp(
        int(run["created_timestamp"]) / 1000,
        tz=timezone.utc,
    ).isoformat()
    evidence = {
        "schema_version": 1,
        "created_at_utc": created,
        "mode": "Chat",
        "condition": args.condition,
        "repetition": args.repetition,
        "agent_config_sha256": config_sha256,
        "provenance": {
            "product_date": created[:10],
            "workspace_type": args.workspace_type,
            "source_profile_file_sha256": file_sha256(args.source_profile),
            "gold_answers_file_sha256": file_sha256(args.checked_answers),
            "metric_view_definition_file_sha256": file_sha256(METRIC_VIEW_PATH),
            "benchmark_manifest_file_sha256": file_sha256(MANIFEST_PATH),
            "public_agent_template_file_sha256": file_sha256(
                ROOT / "agents" / f"{args.condition}.serialized_space.json"
            ),
            "live_agent_config_sha256": config_sha256,
            "live_hash_note": (
                "Hash of the server-serialized live configuration. It differs "
                "from the public template because the server normalizes "
                "configuration and treatment placeholders are resolved."
            ),
        },
        "summary": {
            "questions": run["num_questions"],
            "correct": run["num_correct"],
            "needs_review": run["num_needs_review"],
            "status": run["eval_run_status"],
        },
        "questions": sorted(questions, key=lambda item: item["prompt_id"]),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(evidence, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Exported {len(questions)} redacted results to {args.output}")


if __name__ == "__main__":
    main()
