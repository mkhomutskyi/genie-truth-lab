"""Validate the local Genie Truth Lab experiment contracts."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "benchmarks" / "manifest.json"
CONTRACT = ROOT / "config" / "experiment-contract.json"
BASELINE_AGENT = ROOT / "agents" / "baseline.serialized_space.json"
TREATMENT_AGENT = ROOT / "agents" / "treatment.serialized_space.json"
OPTIMIZED_AGENT = ROOT / "agents" / "treatment-optimized.serialized_space.json"

ALLOWED_SOURCES = {
    "samples.wanderbricks.bookings",
    "samples.wanderbricks.properties",
}
FORBIDDEN_SQL = re.compile(
    r"\b(?:ALTER|COPY|CREATE|DELETE|DROP|GRANT|INSERT|MERGE|OPTIMIZE|"
    r"REVOKE|TRUNCATE|UPDATE|VACUUM)\b",
    re.IGNORECASE,
)
SOURCE_PATTERN = re.compile(r"\bsamples\.wanderbricks\.[a-z_]+\b", re.IGNORECASE)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_manifest(manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    families = manifest.get("families", [])
    if len(families) != 6:
        errors.append(f"expected 6 benchmark families, found {len(families)}")

    family_ids: list[str] = []
    prompt_ids: list[str] = []
    prompt_texts: list[str] = []
    cohort_counts = {"control": 0, "treatment": 0}

    for family in families:
        family_id = family.get("id", "")
        family_ids.append(family_id)
        cohort = family.get("cohort")
        if cohort not in cohort_counts:
            errors.append(f"{family_id}: invalid cohort {cohort!r}")
        else:
            cohort_counts[cohort] += 1

        sql = family.get("expected_sql", "")
        if not sql.lstrip().upper().startswith(("SELECT", "WITH")):
            errors.append(f"{family_id}: gold SQL is not a read-only query")
        if FORBIDDEN_SQL.search(sql):
            errors.append(f"{family_id}: gold SQL contains a forbidden keyword")

        referenced_sources = {source.lower() for source in SOURCE_PATTERN.findall(sql)}
        unknown_sources = referenced_sources - {source.lower() for source in ALLOWED_SOURCES}
        if unknown_sources:
            errors.append(
                f"{family_id}: SQL references sources outside the allowlist: "
                f"{sorted(unknown_sources)}"
            )

        prompts = family.get("prompts", [])
        if len(prompts) != 4:
            errors.append(f"{family_id}: expected 4 prompts, found {len(prompts)}")
        splits = [prompt.get("split") for prompt in prompts]
        if splits.count("development") != 2 or splits.count("holdout") != 2:
            errors.append(
                f"{family_id}: expected 2 development and 2 holdout prompts"
            )
        for prompt in prompts:
            prompt_ids.append(prompt.get("id", ""))
            prompt_texts.append(prompt.get("text", "").strip().casefold())

    if len(family_ids) != len(set(family_ids)):
        errors.append("benchmark family IDs are not unique")
    if len(prompt_ids) != len(set(prompt_ids)):
        errors.append("benchmark prompt IDs are not unique")
    if len(prompt_texts) != len(set(prompt_texts)):
        errors.append("benchmark prompt texts are not unique")
    if len(prompt_ids) != 24:
        errors.append(f"expected 24 prompts, found {len(prompt_ids)}")
    if cohort_counts != {"control": 4, "treatment": 2}:
        errors.append(f"unexpected family cohort counts: {cohort_counts}")

    return errors


def validate_contract(contract: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    sources = set(contract.get("sources", []))
    if sources != ALLOWED_SOURCES:
        errors.append(
            "experiment sources must exactly match the two approved sample sources"
        )

    measure = (
        contract.get("conditions", {})
        .get("treatment", {})
        .get("measure", {})
    )
    if measure.get("name") != "Gross Booked Value":
        errors.append("treatment measure name must be Gross Booked Value")
    definition = measure.get("definition", "").casefold()
    if "revenue" in definition:
        errors.append("the measure definition must not relabel booked value as revenue")

    boundaries = " ".join(measure.get("boundaries", [])).casefold()
    for required in ("revenue", "currency", "status"):
        if required not in boundaries:
            errors.append(f"treatment boundaries must mention {required}")

    return errors


def normalize_sql(sql: str) -> str:
    return " ".join(sql.split()).rstrip(";")


def validate_agent_configs(
    manifest: dict[str, Any],
    baseline: dict[str, Any],
    treatment: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    expected_by_question = {
        prompt["text"]: normalize_sql(family["expected_sql"])
        for family in manifest["families"]
        for prompt in family["prompts"]
    }
    instruction_payloads = []

    for condition, config in (("baseline", baseline), ("treatment", treatment)):
        if config.get("version") != 2:
            errors.append(f"{condition}: serialized-space version must be 2")
        questions = config.get("benchmarks", {}).get("questions", [])
        if len(questions) != 24:
            errors.append(f"{condition}: expected 24 embedded benchmarks")
        ids = [question.get("id", "") for question in questions]
        if ids != sorted(ids):
            errors.append(f"{condition}: benchmark IDs are not sorted")
        if len(ids) != len(set(ids)):
            errors.append(f"{condition}: benchmark IDs are not unique")
        for question in questions:
            text_values = question.get("question", [])
            if len(text_values) != 1 or text_values[0] not in expected_by_question:
                errors.append(f"{condition}: unknown benchmark question {text_values!r}")
                continue
            answers = question.get("answer", [])
            content = answers[0].get("content", []) if answers else []
            if len(content) != 1 or normalize_sql(content[0]) != expected_by_question[
                text_values[0]
            ]:
                errors.append(f"{condition}: benchmark SQL drift for {text_values[0]}")

        instructions = config.get("instructions", {})
        if instructions.get("example_question_sqls"):
            errors.append(f"{condition}: example SQL would leak benchmark patterns")
        text_instructions = instructions.get("text_instructions", [])
        if len(text_instructions) != 1:
            errors.append(f"{condition}: expected exactly one text-instruction block")
        else:
            instruction_payloads.append(text_instructions[0].get("content"))

    baseline_tables = baseline.get("data_sources", {}).get("tables", [])
    if [table.get("identifier") for table in baseline_tables] != sorted(ALLOWED_SOURCES):
        errors.append("baseline: data sources do not match the approved raw tables")
    treatment_views = treatment.get("data_sources", {}).get("metric_views", [])
    if len(treatment_views) != 1 or treatment_views[0].get("identifier") != (
        "${catalog}.${schema}.genie_truth_lab_booking_metrics"
    ):
        errors.append("treatment: expected the single templated booking Metric View")
    if len(instruction_payloads) == 2 and instruction_payloads[0] != instruction_payloads[1]:
        errors.append("baseline and treatment text instructions must be identical")

    return errors








def main() -> None:
    manifest = load_json(MANIFEST)
    errors = [
        *validate_manifest(manifest),
        *validate_contract(load_json(CONTRACT)),
        *validate_agent_configs(
            manifest,
            load_json(BASELINE_AGENT),
            load_json(TREATMENT_AGENT),
        ),
        *validate_agent_configs(
            manifest,
            load_json(BASELINE_AGENT),
            load_json(OPTIMIZED_AGENT),
        ),
    ]
    if errors:
        print("PROJECT VALIDATION FAILED")
        for error in errors:
            print(f" - {error}")
        raise SystemExit(1)
    print("OK: Genie Truth Lab contracts passed local validation")


if __name__ == "__main__":
    main()
