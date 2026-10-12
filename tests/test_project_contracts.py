from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VALIDATOR_PATH = ROOT / "scripts" / "check_workload.py"
SPEC = importlib.util.spec_from_file_location("validate_project", VALIDATOR_PATH)
assert SPEC and SPEC.loader
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


def test_manifest_contract() -> None:
    manifest = VALIDATOR.load_json(ROOT / "benchmarks" / "manifest.json")
    assert VALIDATOR.validate_manifest(manifest) == []


def test_experiment_contract() -> None:
    contract = VALIDATOR.load_json(ROOT / "config" / "experiment-contract.json")
    assert VALIDATOR.validate_contract(contract) == []


def test_agent_configs_match_benchmark_contract() -> None:
    manifest = VALIDATOR.load_json(ROOT / "benchmarks" / "manifest.json")
    baseline = VALIDATOR.load_json(
        ROOT / "agents" / "baseline.serialized_space.json"
    )
    treatment = VALIDATOR.load_json(
        ROOT / "agents" / "treatment.serialized_space.json"
    )
    assert VALIDATOR.validate_agent_configs(manifest, baseline, treatment) == []
    optimized = VALIDATOR.load_json(
        ROOT / "agents" / "treatment-optimized.serialized_space.json"
    )
    assert VALIDATOR.validate_agent_configs(manifest, baseline, optimized) == []








def test_validator_rejects_mutating_sql() -> None:
    manifest = VALIDATOR.load_json(ROOT / "benchmarks" / "manifest.json")
    manifest["families"][0]["expected_sql"] = "DROP TABLE samples.wanderbricks.bookings"
    errors = VALIDATOR.validate_manifest(manifest)
    assert any("forbidden keyword" in error for error in errors)


def test_validator_rejects_holdout_leakage_shape() -> None:
    manifest = VALIDATOR.load_json(ROOT / "benchmarks" / "manifest.json")
    manifest["families"][0]["prompts"][0]["split"] = "holdout"
    errors = VALIDATOR.validate_manifest(manifest)
    assert any("2 development and 2 holdout" in error for error in errors)


def test_validator_rejects_revenue_relabeling() -> None:
    contract = VALIDATOR.load_json(ROOT / "config" / "experiment-contract.json")
    contract["conditions"]["treatment"]["measure"]["definition"] = (
        "Revenue from bookings."
    )
    errors = VALIDATOR.validate_contract(contract)
    assert any("must not relabel" in error for error in errors)
