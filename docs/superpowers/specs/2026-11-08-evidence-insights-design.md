# Evidence applicability and research insights

Extend the current owner-based single-machine workbench, without adding an agent
runtime, central research registry or distributed scheduler. The user requested
all six proposed increments: evidence applicability, comparisons, history search,
agent evaluation, change-impact previews and a self-contained public demo.

## Evidence contract

An optional step `evidence_context` contains exactly `data_sha256`,
`strategy_sha256`, `universe_sha256`, `as_of`, `sample_start`, `sample_end`.
Fingerprints are lowercase SHA-256; as_of is timezone-aware; dates are ISO.
Owner checks may add `scope` (the same six fields), `assessed_at`, `valid_until`.
Only typed allowlisted metadata is stored/projected; private locators are absent.

Market `scope.as_of` and sample dates are distinct from assessment wall-clock
freshness. A retrospective assessment is allowed, but its scope must match the
requested historical cutoff; it cannot manufacture availability evidence. Scope
requires matching data/strategy/universe and as_of, with sample coverage including
the requested sample. Freshness requires assessed_at <= now < valid_until.
Promotion always remains unknown at the coordinator.

Legacy workflows retain existing unscoped gates. A step explicitly selecting
scoped evidence refuses missing, invalid, future, expired or mismatched proof
before dispatch. A current expiry also blocks a legacy gate when the owner
supplied temporal metadata. Original recorded owner status remains available;
current applicability is evaluated separately and never rewrites a historical
research decision. Completed work is not silently re-executed or relabeled.

## Insights and history

Comparison uses stored plans internally but returns only approved identities,
revisions, request/pin digests, budgets, evidence and observations. It aligns steps
by stable ID and states missing financial metrics and causal limitations.
Impact previews scan all workflows, find directly changed identities and DAG
successors, and propose fresh plans/approval review. They never submit or rerun.

Research exports a read-only versioned snapshot from its existing registry and
campaign records. Stable opaque IDs and source digests preserve provenance.
Infrastructure failure is distinct from negative economic evidence. Optional
owner-curated annotations support topics and revisit conditions; no private raw
hypotheses, free-form logs or reproduction paths are copied into public source.
The coordinator imports snapshots as a replaceable projection, not authority.

## Evaluation and public experience

A fixed versioned trace-evaluation suite checks exact tool handles/artifacts,
budget, evidence, recovery identity and intervention. Missing usage stays unknown.
Reference traces test only the harness; even recorded traces have unverified
provenance unless separately established. No model invocation is added.

The public installed package provides a synthetic owner and one-command demo in
a new external directory. It runs without private repositories, credentials or
network. It creates two comparable engineering workflows and explicit unresolved
research gates. The private workbench adds comparison/history/impact/evaluation
views behind the existing token; Pages stays synthetic. Machine contracts remain
language-neutral; UI copy uses English/Chinese catalogs.

## Acceptance and deployment

Meaningful fail-first tests, full configured-owner regression, browser checks,
installed-wheel demo and independent review. Merge Research provider before its
consumer. Retain current source/release/data; publish only this dedicated private
read-only workbench after backup and bounded readiness checks. No paid model
calls, external messages, production cutover or authoritative data changes.
