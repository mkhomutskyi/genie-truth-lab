"""Small SQL Statements API helper using the public Databricks CLI."""

from __future__ import annotations

import json
import subprocess
import time
from typing import Any


def cli(profile: str, *args: str, output_json: bool = False) -> Any:
    command = ["databricks", *args, "--profile", profile]
    if output_json:
        command.extend(["--output", "json"])
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return json.loads(result.stdout) if output_json else result.stdout.strip()


def execute_sql(
    profile: str,
    warehouse_id: str,
    statement: str,
) -> list[dict[str, Any]]:
    response = cli(
        profile,
        "api",
        "post",
        "/api/2.0/sql/statements",
        "--json",
        json.dumps(
            {
                "warehouse_id": warehouse_id,
                "statement": statement,
                "wait_timeout": "50s",
                "on_wait_timeout": "CONTINUE",
                "disposition": "INLINE",
                "format": "JSON_ARRAY",
            },
            separators=(",", ":"),
        ),
        output_json=True,
    )
    while response.get("status", {}).get("state") in {"PENDING", "RUNNING"}:
        time.sleep(2)
        response = cli(
            profile,
            "api",
            "get",
            f"/api/2.0/sql/statements/{response['statement_id']}",
            output_json=True,
        )
    if response.get("status", {}).get("state") != "SUCCEEDED":
        raise RuntimeError(
            json.dumps(response.get("status", {}), indent=2, ensure_ascii=False)
        )

    columns = response.get("manifest", {}).get("schema", {}).get("columns", [])
    names = [column["name"] for column in columns]
    data = response.get("result", {}).get("data_array", [])
    if response.get("result", {}).get("next_chunk_index") is not None:
        raise RuntimeError(
            "SQL result exceeded the inline response. Narrow the query before retrying."
        )
    return [dict(zip(names, row, strict=True)) for row in data]
