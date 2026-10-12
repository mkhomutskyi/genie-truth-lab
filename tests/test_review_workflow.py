from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def write_run(
    path: Path,
    *,
    condition: str = "baseline",
    repetition: int = 1,
    status: str = "PENDING",
) -> None:
    payload = {
        "condition": condition,
        "repetition": repetition,
        "summary": {"status": "DONE"},
        "questions": [
            {
                "prompt_id": "family-dev-01",
                "family_id": "family",
                "cohort": "control",
                "split": "development",
                "assessment": "GOOD",
                "business_review": {"status": status, "notes": ""},
            }
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def run_script(name: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / name), *args],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_review_template_contains_every_question_run(tmp_path: Path) -> None:
    input_dir = tmp_path / "runs"
    input_dir.mkdir()
    write_run(input_dir / "run-2.json", repetition=2)
    write_run(input_dir / "run-1.json", repetition=1)
    output = tmp_path / "reviews.json"

    result = run_script(
        "create_review.py",
        "--input-dir",
        str(input_dir),
        "--output",
        str(output),
    )

    assert result.returncode == 0, result.stderr
    ledger = json.loads(output.read_text(encoding="utf-8"))
    assert [review["repetition"] for review in ledger["reviews"]] == [1, 2]
    assert all(review["status"] == "PENDING" for review in ledger["reviews"])
    assert all(review["native_assessment"] == "GOOD" for review in ledger["reviews"])


def test_review_template_rejects_duplicate_question_runs(tmp_path: Path) -> None:
    input_dir = tmp_path / "runs"
    input_dir.mkdir()
    write_run(input_dir / "first.json")
    write_run(input_dir / "duplicate.json")

    result = run_script(
        "create_review.py",
        "--input-dir",
        str(input_dir),
        "--output",
        str(tmp_path / "reviews.json"),
    )

    assert result.returncode != 0
    assert "Duplicate question-run" in result.stderr


def test_summary_accepts_three_runs_for_each_observed_condition(
    tmp_path: Path,
) -> None:
    input_dir = tmp_path / "runs"
    input_dir.mkdir()
    for condition in ("baseline", "treatment"):
        for repetition in (1, 2, 3):
            write_run(
                input_dir / f"{condition}-{repetition}.json",
                condition=condition,
                repetition=repetition,
                status="PASS",
            )
    output = tmp_path / "summary.json"

    result = run_script(
        "summarize_evaluations.py",
        "--input-dir",
        str(input_dir),
        "--output",
        str(output),
    )

    assert result.returncode == 0, result.stderr
    summary = json.loads(output.read_text(encoding="utf-8"))
    assert summary["run_count"] == 6
    assert summary["evidence_status"] == "INCOMPLETE"


@pytest.mark.parametrize(
    ("review_status", "passed", "safe", "failed"),
    [
        ("PASS", 1, 0, 0),
        ("SAFE_CLARIFICATION", 0, 1, 0),
        ("FAIL", 0, 0, 1),
    ],
)
def test_summary_uses_external_business_review(
    tmp_path: Path,
    review_status: str,
    passed: int,
    safe: int,
    failed: int,
) -> None:
    input_dir = tmp_path / "runs"
    input_dir.mkdir()
    write_run(input_dir / "run.json")
    reviews = tmp_path / "reviews.json"
    reviews.write_text(
        json.dumps(
            {
                "reviews": [
                    {
                        "condition": "baseline",
                        "repetition": 1,
                        "prompt_id": "family-dev-01",
                        "status": review_status,
                        "notes": "Reviewed independently.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "summary.json"

    result = run_script(
        "summarize_evaluations.py",
        "--input-dir",
        str(input_dir),
        "--reviews",
        str(reviews),
        "--output",
        str(output),
        "--allow-partial",
    )

    assert result.returncode == 0, result.stderr
    mixed_review = json.loads(output.read_text(encoding="utf-8"))["by_condition"][
        "baseline"
    ]["mixed_review"]
    assert mixed_review == {
        "classified": 1,
        "pending": 0,
        "passed": passed,
        "safe_clarifications": safe,
        "failed": failed,
        "pass_rate_among_classified": float(passed),
        "manual_native_failure_reviews": 0,
        "automated_sql_guardrails": 0,
    }
