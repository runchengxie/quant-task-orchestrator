# Workflow comparison and change impact

[简体中文](insights.zh-CN.md)

Use `compare_workflows(store, before_id, after_id)` to inspect engineering
changes. It returns `quant.workflow_comparison.v1`, matching steps by their
stable id. Each row has `id`, `status` (`unchanged`, `changed`, `added`, or
`removed`), `changed_fields`, and `before`/`after` projections. A renamed step
appears removed and added; the comparison does not guess identity.

The projection includes adapter kind, exact owner revision, owner plan and
request hashes, distinct pinned content hashes, selected Skill revisions and
hashes, dependencies, allowed budgets, evidence, evidence context and observed
usage. It excludes source paths, commands, prompts and raw plans. Unknown or
invalid negative usage stays `null`; model cost stays `null`. Pin summaries
compare content hashes without revealing file names or locations.

`economic_comparison.status` is always `unavailable`: Owners have not exported
comparable economic metrics. Engineering changes, evidence changes and token
usage cannot establish economic causality or investment performance. Scope
context can explain differences in inputs; it does not supply economic results.
Context is emitted only when the complete shape, exact hashes, UTC timestamp and
ordered ISO sample dates validate. Invalid context is projected as an empty object.
The response includes these comparison limits.

Use `impact_preview(store, proposal)` with this strict input:

```json
{
  "schema": "quant.change_proposal.v1",
  "kind": "owner_revision",
  "previous": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "next": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  "target": "worker"
}
```

`kind` is `owner_revision`, `skill_revision`, or `pinned_input`. `previous` and
`next` must differ and be exact lowercase hexadecimal hashes: 40 characters for
owner/Skill revisions, 64 for pinned inputs. Optional `target` is an adapter id
for owner revisions and pinned inputs, or a Skill id for Skill revisions. Omit it
to find all matching references. Unknown fields and malformed shapes are rejected.
A valid hash with no stored references returns no affected workflows.

The `quant.change_impact.v1` response lists each affected workflow's
`direct_steps`, transitive `downstream_steps`, `required_new_plan: true`, and
`approval_review: true`. Cyclic or missing dependencies fail closed. The preview
never changes approvals or plans and never executes or reruns a step. It does
not verify that a proposed new revision exists or is compatible.

The scan pages through **all stored workflows**, including completed workflows;
it is not limited to the first 100. `scan` reports scope, count, truncation and
consistency. The scan uses one SQLite read snapshot (`sqlite_read_snapshot`), so concurrent
commits cannot shift pages or introduce duplicate/missing source workflows. A
nested savepoint preserves any caller transaction; preview never commits it. No production database or Owner
process is required for the synthetic tests.
