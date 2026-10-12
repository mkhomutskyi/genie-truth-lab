"""Apply one approved serialized-space update to an existing Genie Agent."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", required=True)
    parser.add_argument("--space-id", required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--schema", required=True)
    args = parser.parse_args()

    serialized = (
        args.config.read_text(encoding="utf-8")
        .replace("${catalog}", args.catalog)
        .replace("${schema}", args.schema)
    )
    config = json.loads(serialized)
    compact = json.dumps(config, separators=(",", ":"), ensure_ascii=False)
    payload = json.dumps({"serialized_space": compact}, separators=(",", ":"))
    result = subprocess.run(
        [
            "databricks",
            "genie",
            "update-space",
            args.space_id,
            "--json",
            payload,
            "--profile",
            args.profile,
            "--output",
            "json",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    digest = hashlib.sha256(
        json.dumps(config, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    print(json.dumps({"updated": True, "config_sha256": digest}, indent=2))


if __name__ == "__main__":
    main()
