# Comparing declared financial results

[简体中文](economic-results.zh-CN.md)

Use `compare-results` only with explicit `quant.economic_result.v1` receipts and
exact file digests. The supplied examples are **synthetic**, not exported real
studies. The private Research Owner now exports selected retained historical results through
its standalone `research_economic_export.py`; unsupported basis remains null.
The existing workflow comparison remains an engineering comparison and does not
silently consume these files or claim investment performance.

```sh
quant-task compare-results \
  --before examples/economic-results/before.json --before-sha256 BEFORE_FILE_SHA256 \
  --after examples/economic-results/after.json --after-sha256 AFTER_FILE_SHA256
```

Replace both pins with SHA-256 of the corresponding file bytes. No database,
Owner process, model, network or execution permission is needed. The command
reads at most 1 MiB per regular file, rejects symlink components, verifies the
same bytes it parses, and rejects extra fields, duplicate JSON keys and nonfinite
metrics. The Python functions are `load_result(path, expected_sha256)` and
`compare_results(before, after)` in `quant_task_orchestrator.economic_results`.

## Required declaration

Each envelope contains exactly: `schema`, `owner` (`quant-research`),
`source_revision` (40 lowercase hex), `result_id` and `report_sha256` (64 lowercase
hex), `evidence_class` (`synthetic`, `historical_mechanism`, `research`),
`execution_status` (`succeeded`, `failed`, `unknown`), `admission_status`
(`blocked`, `not_assessed`, `owner_declared`), `basis` and `metrics`.
Opaque IDs and digests replace paths, symbols, policy parameters and raw reports.

`basis` has exactly these keys; any unknown value is `null`:

| Fields | Meaning |
| --- | --- |
| `data_sha256`, `universe_sha256`, `benchmark_sha256` | Exact dataset, eligible universe and comparison benchmark definitions |
| `cost_model_sha256`, `execution_semantics_sha256` | All non-treatment cost/valuation/execution assumptions |
| `metric_definitions_sha256` | Metric calculation, annualization and units |
| `sample_start`, `sample_end` | Ordered ISO dates |
| `time_zone`, `currency`, `return_frequency` | IANA zone, three uppercase currency letters, daily/weekly/monthly |
| `history_visibility` | seen/holdout/prospective; this is an Owner declaration, not independently verified |

Two results are comparable only when all basis values are present and exactly
match, both executions succeeded, evidence classes match and at least one metric
pair is known. Two matching `null` values still block. Assumption fingerprints
must cover all non-treatment differences, including initial capital, price
adjustment, market calendar, fees, taxes, impact, liquidity and treatment of open
inventory where relevant. Equality of opaque hashes cannot prove those definitions
are complete; the producer and independent reviewer remain responsible.

`metrics` contains exactly `total_return`, `annualized_return`, `max_drawdown`,
`annualized_volatility`, `sharpe`, `turnover`. Values are finite numbers with
absolute value at most 1e12, or `null`. Returns use ratios (0.02 means 2%) and cannot
be below -1. Drawdown is a positive loss fraction from 0 through 1. Volatility and
turnover are nonnegative ratios; Sharpe can be negative. Unknown values never
become zero. The output delta is after minus before; a positive drawdown delta
means a larger loss, not improvement. A 0.02 return delta is two percentage points,
not a relative return or geometric excess return.

## Authority and remaining work

Output `quant.economic_comparison.v1` says `not_comparable` with stable reasons
when basis is missing or different; it emits no metric deltas in that case.
Comparable declarations provide arithmetic only. `provenance_verified`,
`research_validated`, `promotion_authorized` and `causal_attribution` remain false.
`owner` and admission fields are declarations; anyone can write a matching
string. A pinned file proves byte identity, not who produced it or whether its
claims are true. `report_sha256` is a declared reference, not a verified artifact
read by this command. No input can grant research or execution authority.

The current Owner adapter exports the metric-definition and available input
fingerprints. Further provider work must supply demonstrated universe, benchmark
and complete assumptions plus an Owner verification receipt. Existing
within-study paired calculations do not by themselves supply this cross-study
contract. Real historical mechanism results can remain formally blocked even
when retained artifact hashes and paired arithmetic pass read-only verification.

## Explicit cache and GUI

Export a single Owner object with its `--single` mode, save it outside source,
then import exactly those bytes:

```sh
quant-task --database "$TASK_DATABASE" economic-import --file "$RESULT_JSON" --sha256 "$RESULT_SHA256"
quant-task --database "$TASK_DATABASE" economic-results --limit 100 --offset 0
quant-task --database "$TASK_DATABASE" economic-compare BEFORE_FILE_SHA256 AFTER_FILE_SHA256
```

Imports add only a bounded result cache; they do not change workflow state,
approvals or evidence. Queries verify the original cached bytes against the
external file pin each time and never reopen Owner files or invoke an Owner.
An old read-only database with no cache returns an empty list without migration.

The live **Declared financial results** panel lists imported receipts and supports
load-more pagination while preserving selected pins. It shows admitted sample
and source fingerprints in details, observed scalar declarations, missing metrics
as unknown, and comparison reasons. Not-comparable pairs retain individual
declarations but no calculated deltas. Synthetic offline demos seed two marked
example receipts. No private receipts are published to Pages.

Routes: `GET /v1/economic-results?limit=100&offset=0` returns
`quant.economic_result_list.v1` with results, total and next_offset;
`GET /v1/economic-compare?before=SHA256&after=SHA256` compares two imported pins.
Both share the existing loopback/authentication/read-only boundary.
