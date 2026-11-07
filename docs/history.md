# Research history snapshots

[简体中文](history.zh-CN.md)

History is an explicitly imported view of Research records, not a second registry.
The Research exporter reads selected existing SQLite sources in a read transaction
and binds the logical snapshot including committed WAL. It selects allowed columns
only, enforces source/record/artifact bounds and rejects conflicting scoped IDs.
Record identity remains stable when unrelated rows are added.

The versioned `quant.research_history.v1` export includes a stable owner source ID,
exporter revision, opaque record IDs, original machine statuses/decisions,
classification, evidence stage and provenance digests. Private hypotheses, raw
conclusions, error messages, source filenames and specifications are excluded.
Optional owner-curated token annotations provide topics, reason codes and revisit
conditions; missing annotations mean unknown. Infrastructure failure is separate
from a recorded research conclusion. `DISCARDED` alone does not establish economic
invalidity. `owner_recorded` does not mean this consumer verified the evidence.

Import a selected export through the local CLI:

```sh
quant-task --database "$TASK_DATABASE" history-import --file "$OWNER_EXPORT" --sha256 "$EXPORT_SHA256"
quant-task --database "$TASK_DATABASE" history --classification operational_failure
quant-task --database "$TASK_DATABASE" history --q pit --limit 50 --offset 0
```

Import checks exact bytes, strict JSON, schema and digest. Reimport is idempotent;
source databases are never opened by the consumer. Search defaults to the latest
explicitly imported snapshot, not every registry on the machine. Pin
`--snapshot-sha256` for reproducible pagination. The API accepts the equivalent
snapshot pin and exact filters for source kind, status, stage, decision,
classification, evidence stage and annotation tokens. Free text searches only the
exported fields, not original private hypothesis text.

The authenticated read-only GUI provides query, classification and next-page
controls. Empty results do not prove no prior research exists: the selected source
collection, annotation coverage and snapshot freshness limit retrieval. New Owner
records require a fresh explicit export/import. Snapshots remain caches.
