# Validation and limits

The initial implementation was validated on 2026-11-07. Exact delivery revisions
and remote CI results are recorded in the implementing pull request; local tests
used the complete task worktree, including the final regression fixes.

| Check | Actual result |
| --- | --- |
| Python 3.14.9 complete suite with real Go Runtime enabled | 26 tests passed, zero skipped |
| Python 3.12 complete suite, synthetic owner only | 25 passed, one explicit Runtime integration skip |
| Installed Python Runtime synthetic acceptance | Passed before final review fixes; final Go acceptance below covers the final adapter |
| Installed Go Runtime at `c9493008ad41da4391db38542528a4ccbe385b73` | Plan, submit, coordinator reopen, polling, verified result, duplicate identity and one owner job passed |
| Ruff, compilation, JavaScript syntax, whitespace | Passed |
| Playwright 1.61.0 with installed Chrome | Desktop 1440px/mobile 390px, selection, filters, approval/completion simulation, reset, locale persistence; no page errors or horizontal overflow |
| Source distribution and wheel | Both built successfully outside the repository |
| Independent review | Five important findings received; all fixed with fail-first regression cases |

The complete suite also covers malformed graphs, approval mismatch, changed request
bytes, Skill hash tampering, lost responses, pre-dispatch crashes, conflicting
Runtime keys, wrong result fingerprints, cancellation, failed parallel branches,
more than 100 workflows, and public-projection redaction. The API test binds a
random loopback port and verifies reads and rejected writes.

The real test creates only synthetic input and fresh temporary databases, uses
an already installed immutable Runtime, and never touches its production database
or service. The Go acceptance uses its stateless legacy adapter for a synthetic
v2 request; it is not an independent Rust financial semantic evaluation.

## Reproduce

```sh
PYTHONPATH=src python -m unittest discover -s tests -v
ruff check src tests
ruff format --check src tests
python -m compileall -q src
node --check site/app.js
node --check site/locales.js
node --check site/demo-data.js
git diff --check
```

For installed Runtime acceptance, explicitly set `QUANT_RUNTIME_CLI`,
`QUANT_RUNTIME_PYTHON`, `QUANT_RUNTIME_EXAMPLE` to the installed executable,
its Python and its synthetic `scripts/create_example.py`. For Go with the legacy
v2 fixture, set `QUANT_RUNTIME_ADAPTER_PYTHON` as well. All test databases use
unique temporary directories. No local credential or deployment paths belong in
a public validation record.

```sh
PYTHONPATH=src python -m unittest discover -s tests -p test_runtime_integration.py -v
python -m pip install playwright==1.61.0
python -m playwright install chromium
python tests/browser_smoke.py
```

`QUANT_BROWSER_EXECUTABLE` can select an existing installed Chrome instead of the
Playwright-managed executable. Screenshots are temporary artifacts, not source.

## Unvalidated and deferred

No actual private Research campaign, paid model, production task, real data
pipeline, economic hypothesis, PIT assertion or live trade was executed. The
Research adapter has synthetic protocol acceptance and was checked against the
owner's current CLI contract; this does not establish real-study acceptance.
The Skill catalog verifies source locks but does not install or run capabilities.
The Pages demo is browser-local simulation, not an authenticated live GUI. Data,
reports and multi-agent session adapters remain later extensions. No production
schedules were migrated and no availability/load or multi-host test was claimed.
