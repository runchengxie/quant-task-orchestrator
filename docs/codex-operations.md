# Codex and operations increment

[简体中文](codex-operations.zh-CN.md)

Use the Research Owner's `strategy_app.codex_task` interface for bounded agent
turns. The coordinator never invokes model commands directly. Each workflow
freezes its action, exact session and prior receipt for resume, executable and
prompt hashes, and cumulative wall/turn budgets. Polling does not resume tasks.
Owner loss requires operator reconciliation; unknown usage remains unknown.
The token ceiling is an admission check, not a hard live token or dollar limit.

The initial provider is Linux-only and tool-free: shell, web, MCP and additional
agents are disabled. This supports lifecycle qualification, not autonomous
research computation. Adding research tools requires another explicit contract.
Cancellation affects the Codex turn; it does not cancel separate Runtime jobs.
Public views contain allowlisted counters and identities, never prompts or paths.

Live qualification used Codex CLI 0.167.0 within two sessions, three admission
calls and ten minutes. One initial attempt failed closed on an obsolete setting,
which was removed. One turn completed and reported token counters. A second turn
was admitted to that exact session and cancelled before launch. A completed live
resumed turn remains unverified. No financial conclusion follows from this test.

Raw observation verification checks the expected root manifest, sealed children
and file bytes through the data Owner. Content integrity does not establish
historical point-in-time availability or make an unmaterialized study ready.

The [operations commands](operations-next.md) provide a durable event inbox,
local notification outbox, immutable Skill text installation, staged wheel
releases, backup and health checks. Notifications stay local. Staging does not
install or activate a service. Production schedule migration and external message
transport remain separate deployment work.

For private local access, run `serve-api --token-file "$GUI_TOKEN_FILE"` with an
owner-only regular token file containing 32–256 URL-safe characters. The GUI
keeps the token only in memory, clears the password input, and forgets it on
reload or disconnect. APIs require the bearer header; query-string tokens are
rejected. Binding remains loopback-only and HTTP mutation remains disabled.
GitHub Pages continues to serve synthetic data without credentials or live APIs.

## Validation of this increment

The coordinator suite ran 91 tests: 89 passed and two optional report-owner
checks were not configured. Installed Go Runtime submission/recovery, data Owner
contracts and retained native-session inspection were enabled with isolated
synthetic inputs. Separate actual raw-observation and Codex-receipt adapter
checks passed without additional model calls. Ruff, compilation and frontend
syntax checks passed. Browser acceptance covered SQLite polling, pagination,
English/Chinese UI, memory-only authentication and delayed responses after logout.

The data provider is merged in PR [#183](https://github.com/runchengxie/quant-market-data-platform/pull/183)
(`e576ef761665145b4a9aa3811da028904d320587`); its full gate passed 2,280 tests
with one skip. The Research lifecycle provider is merged in PR
[#651](https://github.com/runchengxie/quant-research/pull/651)
(`dad0511564c204591edf259f1fde5afa124eadc7`); 42 relevant tests passed.
Independent review added regressions for expired admission and logout races.

Remaining work includes research-capable Agent tools, a completed live resume,
normalized PIT materialization and qualified study acceptance, external
notification transport, and deliberate production scheduler cutover. The current
operations tools stage and inspect these changes; they do not imply adoption.

Authentication regression was checked both ways: disabling the response epoch
check made the delayed-response browser test fail; restoring it passed.
