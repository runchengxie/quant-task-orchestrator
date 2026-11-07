# Setup and synthetic quickstart

Use Python 3.12+ on Linux. Install the package into an isolated environment with
`python -m pip install .`, or use `PYTHONPATH=src python -m quant_task_orchestrator`
from a checkout without installing dependencies. Build tooling is pinned in
`pyproject.toml`; the runtime itself has no external dependencies.

1. Install an immutable reviewed `quant-backtest-runtime` release and its required
   engine/legacy adapter. Use the owner's synthetic input generator and isolated
   database instructions. Initialize that owner database explicitly; lookup is a
   read-only operation and cannot create it. No production database is needed.
2. Copy `examples/config.json` into your private project configuration directory.
   Replace placeholders with your immutable CLI and task-local synthetic input,
   result and database paths. If required, include `--python-executable` and
   `--engine-executable` in the fixed command. `queue=true` requires the separate
   owner scheduler; use `queue=false` only with a dedicated immediate-mode database.
3. Set `TASK_CONFIG`, `TASK_WORKFLOW`, `TASK_PLAN`, and `TASK_DATABASE` to explicit
   absolute paths outside the repository; copy `examples/workflow.json` as the
   synthetic workflow. Keep plans private, since they contain source locators.

```sh
quant-task plan --workflow "$TASK_WORKFLOW" --config "$TASK_CONFIG" --output "$TASK_PLAN"
quant-task --database "$TASK_DATABASE" submit --plan "$TASK_PLAN"
```

Read the returned `workflow_id` and `plan_sha256`. Review the scope and owner plan
before explicitly approving. Set `WORKFLOW_ID` and `PLAN_SHA256` to those values.

```sh
quant-task --database "$TASK_DATABASE" approve "$WORKFLOW_ID" \
  --plan-sha256 "$PLAN_SHA256" --allow-kind runtime --operator local-operator
quant-task --database "$TASK_DATABASE" run --interval 5
```

In another terminal:

```sh
quant-task --database "$TASK_DATABASE" tui
quant-task --database "$TASK_DATABASE" inspect "$WORKFLOW_ID"
quant-task --database "$TASK_DATABASE" serve-api --host 127.0.0.1 --port 8787
```

TUI: arrows scroll, `q` exits, automatic read-only refresh every second. For a
noninteractive snapshot use `tui --once`. `tick WORKFLOW_ID` performs a single
coordinator pass. `events WORKFLOW_ID --after SEQUENCE` reads the next ledger page.

## Research campaign adapter

Install the reviewed private Research owner in an immutable environment. Register
its fixed campaign CLI, frozen operator config and existing proposal ID using the
shape in [contracts](contracts.md). Add `--allow-kind research` when approving a
mixed workflow. No Research repository import is required here. This adapter
reconciles existing work; starting a native model session, approving a hypothesis
or recording a conclusion stays in Research.

## Pages preview

```sh
python -m http.server 8891 --bind 127.0.0.1 --directory site
```

Open `http://127.0.0.1:8891/`. The static page needs no build step or credentials.
Language selection persists in local browser storage when available. Simulated
workflow controls and filtering work offline. Publishing uploads only `site/`.
