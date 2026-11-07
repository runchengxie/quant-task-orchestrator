# quant-task-orchestrator

Public, strategy-neutral coordination only. Runtime owns workers and result
publication; Research owns admission, economic evidence and promotion. Never
import private research source, copy strategy configuration, or change production
schedules to test an adapter. Examples and the Pages demo use synthetic data.

Use task branches and isolated worktrees. Keep retained databases, logs and output
under the configured project data root, outside the source tree. Private adapter
configuration belongs under CONFIG_ROOT/projects/quant-task-orchestrator/.

Validate with `python -m unittest discover -s tests -v`,
`python -m compileall -q src`, and `git diff --check`. Run installed Runtime
acceptance when changing its adapter; document unavailable integration checks.
Frontend: `node --check site/app.js` and the documented browser smoke test.
Do not bypass GitHub checks or hooks. Preserve existing task worktrees.
