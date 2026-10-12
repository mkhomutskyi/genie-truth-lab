# Try the Genie Truth Lab

Use the built-in simulated Wanderbricks data and your own sandbox. The original scores are historical; record and review your own results rather than expecting the same percentages.

## 1. Prepare

You need a [Databricks Free Edition](https://docs.databricks.com/aws/en/getting-started/free-edition) account or another Unity Catalog workspace, an existing SQL warehouse you can use, and a writable catalog/schema for the metric view. Free Edition is for non-commercial use and is [quota-limited](https://docs.databricks.com/aws/en/getting-started/free-edition-limitations). Feature availability can vary.

Confirm the sample is available in the SQL editor:

```sql
SELECT COUNT(*) FROM samples.wanderbricks.bookings;
SELECT COUNT(*) FROM samples.wanderbricks.properties;
```

For CLI setup, install Python 3.11 or later, [uv](https://docs.astral.sh/uv/), and the [Databricks CLI](https://docs.databricks.com/aws/en/dev-tools/cli/install). Authenticate with a local profile and select an existing warehouse. Do not commit credentials or workspace outputs.

```bash
uv sync --frozen --dev
uv run python scripts/build_agent_configs.py
uv run python scripts/check_workload.py
uv run pytest -q
```

Commands below use placeholders; replace them with your own values. All generated files go under `local/`, which is ignored by Git. The setup helpers create Agents and a metric view, not a warehouse or catalog. Review the metric-view definition before deployment.

## 2. Check the workload

[benchmarks/manifest.json](../benchmarks/manifest.json) contains six business intents, 24 prompts, and checked SQL. [config/experiment-contract.json](../config/experiment-contract.json) defines the semantic boundaries. Gross Booked Value is the sum of booking amounts for the rows requested; it is not recognized revenue. Apply a status filter only when requested, and do not assert a currency without source metadata.

Execute and record the checked SQL in your own workspace:

```bash
uv run python scripts/check_answers.py --profile <PROFILE> --warehouse-id <WAREHOUSE_ID>
```

This creates `local/checked-answers.json`. [sql/01_profile_sources.sql](../sql/01_profile_sources.sql) provides optional source-profile queries. If you save a profile as JSON, pass its path with `--source-profile` when exporting runs; otherwise that optional provenance hash is null.

## 3. Create the raw-table Agent

```bash
uv run python scripts/create_agent.py --condition baseline --profile <PROFILE> --warehouse-id <WAREHOUSE_ID> --parent-path /Workspace/Users/<YOUR_USER>/genie_truth_lab --state-output local/baseline-agent.json
```

The configuration includes bookings and properties, a many-to-one join on Property ID, reviewed metadata, and the fixed benchmarks. It supplies no benchmark questions as example SQL.

### Browser-only alternative

Create an Agent in the workspace, select the existing warehouse, and add `samples.wanderbricks.bookings` and `samples.wanderbricks.properties`. Copy the join, column metadata, exclusions, and text instructions from [agents/baseline.serialized_space.json](../agents/baseline.serialized_space.json). Add the prompts and checked SQL from the manifest.

Use [Databricks' setup guidance](https://docs.databricks.com/aws/en/genie-agents/set-up). If native benchmarks are unavailable, ask each prompt in a fresh conversation and compare the rows with the checked SQL. Keep manual results separate from native benchmark scores.

## 4. Run three Chat-mode evaluations

Start a native evaluation and copy its returned run ID:

```bash
databricks genie genie-create-eval-run <AGENT_ID> --json '{}' --output json --profile <PROFILE>
databricks genie genie-get-eval-run <AGENT_ID> <EVAL_RUN_ID> --output json --profile <PROFILE>
```

After the status is `DONE`, export it:

```bash
uv run python scripts/export_run.py --profile <PROFILE> --space-id <AGENT_ID> --eval-run-id <EVAL_RUN_ID> --catalog <CATALOG> --schema <SCHEMA> --workspace-type "Free Edition" --condition baseline --repetition 1 --output local/runs/baseline-run-1.json
```

The API retains the older `space_id` name. Run three complete evaluations using repetitions 1, 2, and 3, exporting each promptly. Record your actual workspace type. See [Databricks' testing guidance](https://docs.databricks.com/aws/en/genie-agents/monitor) for the current benchmark experience.

## 5. Add governed metrics and repeat

```bash
uv run python scripts/create_metric_view.py --profile <PROFILE> --warehouse-id <WAREHOUSE_ID> --catalog <CATALOG> --schema <SCHEMA> --output local/metric-view-check.json
uv run python scripts/create_agent.py --condition treatment --profile <PROFILE> --warehouse-id <WAREHOUSE_ID> --catalog <CATALOG> --schema <SCHEMA> --parent-path /Workspace/Users/<YOUR_USER>/genie_truth_lab --state-output local/treatment-agent.json
```

The metric-view helper refuses to replace an existing object of the same name. If metric views are unavailable, you can try the baseline; a regular SQL view is not the same treatment.

Run and export three complete evaluations for `treatment`, keeping the same prompts and checked SQL. If quota limits stop compute, wait for the reset and record the interruption.

## 6. Apply the property-grain configuration

To reproduce the published metadata change:

```bash
uv run python scripts/update_agent.py --profile <PROFILE> --space-id <TREATMENT_AGENT_ID> --config agents/treatment-optimized.serialized_space.json --catalog <CATALOG> --schema <SCHEMA>
```

Run and export three more evaluations under `treatment-optimized`. Keep reserved wording fixed. The published fix was selected after a development failure; do not describe it as a preplanned independent test.

## 7. Review and summarize your results

```bash
uv run python scripts/create_review.py --input-dir local/runs --output local/reviews.json
uv run python scripts/summarize_evaluations.py --input-dir local/runs --reviews local/reviews.json --output local/summary.json
```

Before the summary command, replace every `PENDING` review with `PASS`, `SAFE_CLARIFICATION`, or `FAIL` and explain each non-pass. Inspect meaning, filters, dates, property grain, units, and joins. Native `GOOD` does not establish business correctness by itself.

The complete three-configuration experiment contains nine runs and 216 question-runs. A native pass rate measures result matching on this fixed workload. Keep it separate from human review and from claims about new intents or production readiness. See [the historical results and limits](../RESULTS.md).
