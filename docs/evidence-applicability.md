# Evidence applicability

[简体中文](evidence-applicability.zh-CN.md)

A recorded `verified` check is not a universal permission. A successor can opt into
scope-aware admission by adding `evidence_context` next to `requires_evidence`:

```json
{"data_sha256":"<64 hex>","strategy_sha256":"<64 hex>","universe_sha256":"<64 hex>","as_of":"2020-12-31T16:00:00Z","sample_start":"2020-01-01","sample_end":"2020-12-31"}
```

An Owner check contains its existing `status`, `source`, `evidence_sha256`, plus
`scope` with those six fields, `assessed_at` and `valid_until`. All fields are
required for scoped reuse. Hashes are opaque identities; no private paths or
universe constituents are projected. Unknown or malformed scope cannot qualify.

The requested data/strategy/universe and market `as_of` must match; the Owner's
sample interval must cover the request. The proof must have an identity and be
current: `assessed_at <= now < valid_until`. Both assessment timestamps require
UTC. Historical market time is separate: a later audit can establish evidence
about an earlier cutoff, but this coordinator never infers historical availability.
Only the relevant Owner's validated checks can establish that claim.

Scoped source attribution must match the exporting adapter's Owner. A Runtime
source string cannot impersonate Research. Data/Research can attest PIT;
Runtime/Research can attest execution semantics; Research owns independent review
and economic conclusions. The coordinator always leaves promotion unknown.
Delegated attestations require a separately verified owner envelope, not a string.

The public check keeps the recorded Owner status and adds `applicability` with
`code` and `usable`. It preserves only typed scope/time metadata. Invalid explicit
observations fail closed rather than falling back to a generic verified Runtime
baseline. Views recompute freshness; a cached applicability result is not trusted.

Before a new dispatch, the scheduler evaluates the requested checks against the
step context. Missing scope, identity mismatch, incomplete coverage, expired or
future-dated assessments block admission. Previously completed steps keep their
historical state; expiration does not cancel independent jobs or rewrite results.
Fresh evidence and a new reviewed plan are needed to change a pre-dispatch block.

Legacy workflows without an evidence context remain compatible. `LEGACY_UNSCOPED`
means no scoped certification; it is not a freshness guarantee. If a legacy check
supplies validity metadata, invalid or expired metadata still blocks reuse. New
research that needs scope guarantees must explicitly request them. The current
legacy owner protocols do not automatically acquire new scope metadata.

The installed offline demo includes explicitly synthetic fresh/expired checks to
illustrate presentation. They establish neither PIT nor financial research truth.
