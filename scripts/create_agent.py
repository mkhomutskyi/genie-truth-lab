"""Create one reviewed Genie Truth Lab Agent in an approved workspace."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
AGENT_DIR = ROOT / "agents"


def run_cli(profile: str, *args: str, output_json: bool = False) -> Any:
    command = ["databricks", *args, "--profile", profile]
    if output_json:
        command.extend(["--output", "json"])
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    if output_json:
        return json.loads(result.stdout)
    return result.stdout.strip()


def load_config(condition: str, catalog: str | None, schema: str | None) -> str:
    path = AGENT_DIR / f"{condition}.serialized_space.json"
    serialized = path.read_text(encoding="utf-8")
    if condition == "treatment":
        if not catalog or not schema:
            raise ValueError("Treatment creation requires --catalog and --schema")
        serialized = serialized.replace("${catalog}", catalog).replace(
            "${schema}", schema
        )
    config = json.loads(serialized)
    return json.dumps(config, ensure_ascii=False, separators=(",", ":"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--condition", choices=("baseline", "treatment"), required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--parent-path", required=True)
    parser.add_argument("--catalog")
    parser.add_argument("--schema")
    parser.add_argument(
        "--warehouse-id",
        required=True,
        help="ID of an existing SQL warehouse. The script creates no compute.",
    )
    parser.add_argument("--state-output", type=Path)
    args = parser.parse_args()

    titles = {
        "baseline": "Genie Truth Lab - Raw Tables",
        "treatment": "Genie Truth Lab - Metric View",
    }
    descriptions = {
        "baseline": (
            "Controlled raw-table baseline for the Wanderbricks accuracy experiment."
        ),
        "treatment": (
            "Controlled Metric View treatment for the Wanderbricks accuracy experiment."
        ),
    }
    run_cli(args.profile, "workspace", "mkdirs", args.parent_path)
    payload = {
        "warehouse_id": args.warehouse_id,
        "title": titles[args.condition],
        "description": descriptions[args.condition],
        "parent_path": args.parent_path,
        "serialized_space": load_config(
            args.condition,
            args.catalog,
            args.schema,
        ),
    }
    created = run_cli(
        args.profile,
        "genie",
        "create-space",
        "--json",
        json.dumps(payload, separators=(",", ":")),
        output_json=True,
    )
    state = {
        "condition": args.condition,
        "title": titles[args.condition],
        "space_id": created["space_id"],
    }
    if args.state_output:
        args.state_output.parent.mkdir(parents=True, exist_ok=True)
        args.state_output.write_text(
            json.dumps(state, indent=2) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(state, indent=2))


if __name__ == "__main__":
    main()
