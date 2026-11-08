# Reading the research workbench

[简体中文](workflow-concepts.zh-CN.md)

Start with the selected workflow's execution state, research qualification and
recorded next action. Use **View step evidence and recovery** to inspect the
relevant step. This navigation reads existing records; it does not approve,
rerun or cancel anything. Missing evidence is shown only when actually recorded;
missing fields remain unknown.

| UI term | Purpose | Authority boundary |
| --- | --- | --- |
| Responsible systems | Explains which project owns data, execution, research review or reporting | Runtime confirms execution; Research judges admission and conclusions; coordination does not override either |
| Capability library | Describes reusable tasks, input/output contracts and exact versions | Listed does not mean installed, enabled or authorized; capabilities do not schedule themselves |
| Workflow timeline | Shows important plan, approval, assignment and state changes | An event is a record, not proof of economic validity; detailed program output belongs in run logs |

A responsible system is a project/service, not necessarily a person. Execution
identity, exact revisions and hashes remain separate technical facts. The UI
maps only known adapter kinds to system names and leaves unknown kinds unknown.
Known events have localized summaries; unknown events retain a neutral summary
and an expandable original code. Recorded action codes remain stable in APIs
and persisted data. Suggested next steps never grant new authority.

Financial comparison and observation coverage have separate contracts:
[declared financial results](economic-results.md) and
[read-only shadow observations](shadow-observations.md). Successful computation,
matching file digests and a sufficient observation window each establish different
facts; none alone validates a research conclusion or authorizes promotion.
