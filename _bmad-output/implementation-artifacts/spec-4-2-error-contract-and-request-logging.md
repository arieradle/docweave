---
title: 'Error contract and request logging'
type: 'feature'
created: '2026-11-01'
status: 'draft'
baseline_commit: 'cd5c12665210c90e70229a728c76326a8c6e0bfe'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-4-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Error mapping (1.5) and the transport's `finally` (1.2) exist, but nothing proves every AD-15 class maps correctly, every path that can fail goes through the one mapper, or that an administrator can see what a request did. There is no per-request log line (FR-14, AD-12, AD-15).

**Approach:** Extend `adapter/errors.py` and the shared request path in `api.py`; don't add a second mapper. Count each request's numbers in a small stats object that the transport creates and passes to the adapter and executor. In the `finally` block, after the rollback and the deferred error flush, write one `frappe.logger("docweave")` line with those numbers and the codes returned.

## Boundaries & Constraints

**Always:**
- `adapter/errors.py` stays the only exception mapper. Check `DoesNotExistError` before `ValidationError` (it is a subclass). `DoesNotExistError` and `PermissionError` give `NOT_FOUND`. `ValidationError` and its subclasses give `VALIDATION`, with the class name plus a sanitized message. A `DocWeaveError` keeps its own code. Anything else gives `INTERNAL` with a fixed generic message.
- Every path that can fail goes through the mapper: the adapter load, the schema build, and the transport's catch-all from 1.2, which no longer calls `frappe.log_error` inline.
- An `INTERNAL` entry is a standard traceback with no locals, written only in the `finally`, after `frappe.db.rollback()`, through `frappe.log_error(title, message, defer_insert=True)`. A failed schema build is logged this way too.
- Every request to `graphql` or `sdl` that reaches DocWeave code writes exactly one line, including 400 and 403. It has the endpoint, HTTP status, duration in ms, query count, candidates scanned, cost and the codes returned with counts. It never has a field value, filter value, variable, query text, cursor, document name or exception message.
- A failure while logging never changes the response.
- The 1.2 statuses are unchanged: 200 for GraphQL results including errors, 400 malformed, 403 gate.

**Never:**
- No new error codes; the nine stay in `core`. No log line from GETs or guests that Frappe refuses before DocWeave runs.
- No metrics backend, no Settings fields, and no change to the AD-1 allowlist beyond what the query-count question decides.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Map `DoesNotExistError` / `PermissionError` | raised in the adapter | `NOT_FOUND`, same body for both | N/A |
| Map `ValidationError`, `LinkValidationError`, `MandatoryError` | raised in the adapter | `VALIDATION`; message starts with the class name | N/A |
| Map `KeyError`, `QueryTimeoutError` | raised in the adapter | `INTERNAL`, generic message, no traceback or class name in the body | one deferred Error Log, no locals |
| Locals | the failing frame holds a local `secret="S3CR3T"`; developer mode on | Error Log text lacks `S3CR3T` | N/A |
| Rollback first | the adapter wrote a row, then raised | the row is gone, the Error Log entry exists after `save_to_db()` | N/A |
| Build fails | `build_schema` raises | `INTERNAL`; one deferred Error Log | N/A |
| Log line | list query with a filter, `after` cursor, masked field | one line with `scanned`, `cost`, `codes=MASKED:n`; no filter value, cursor, name or field value in it | N/A |
| Gate failure / malformed body | 403 / 400 | one line with that status and code | N/A |
| Logger raises | handler throws | response unchanged | swallowed |

</frozen-after-approval>

## Open Questions

- **Query count.** Frappe v16 keeps no per-request query counter, and wrapping `frappe.db.sql` touches a name AD-1 bans everywhere. Options: wrap `frappe.db.sql` on the request's own `frappe.db` instance in one adapter module, restored in the `finally` (exact, includes hook queries; AD-1 is amended through correct-course to allow that one module) / count only DocWeave's own adapter calls (`_authorized_query` runs and document loads), named `adapter_calls` (no spine change, but the number isn't a real query count and misses hook queries).
- **Log level.** Frappe sets loggers to ERROR in production (WARNING under the dev server), so an INFO line is dropped by default. Options: set the `docweave` logger to INFO on first use (the line always appears, in `logs/docweave.log`, rotating at 100 KB × 20 files) / log at INFO and leave Frappe's level alone (no line in production until an admin raises the level) / log at WARNING (always shown, but every request looks like a warning).
- **Sanitized `VALIDATION` message.** Frappe's messages can echo values (for example a Link name). Options: the class name plus Frappe's message with HTML stripped, truncated to 200 characters (actionable; may echo a value the caller sent or can see) / the class name plus a fixed message per class (leaks nothing; less actionable).
- **User in the log line.** Options: include `frappe.session.user` (admins can trace a caller; the user's email is in the log) / leave it out (matches the spine's list exactly).
- Depends on 1.2 question "Guest and GET refusals": those requests get no log line.

## Code Map

- `docweave/adapter/errors.py` (created in 1.5) -- `map_exception(exc) -> DocWeaveError`, the `ContextVar` of deferred entries, `take_deferred()`. Extend; it stays the only mapper.
- `docweave/api.py` (created in 1.2; shared helper from 4.1) -- body parsing (400), `_gate` (403), the catch-all (`INTERNAL`), the `finally` (rollback, `message_log` clear, deferred flush). Add the stats object and the log line here.
- `docweave/core/types.py` (created in 1.2, extended in 1.5) -- `ErrorCode`, `DocWeaveError`. Add a mutable `RequestStats(queries=0, candidates_scanned=0, cost=None)`; core still imports nothing.
- `docweave/adapter/frappe_v16.py` (1.5) -- `FrappeV16Adapter(user, settings)`. It gains an optional `stats`. Candidates scanned come from the scan loop promised by 2.3 (spec not yet written).
- `docweave/execution/executor.py` (1.3, 1.5) -- records `estimate_cost(plan)` from `execution/rules.py` (promised by 2.4, spec not yet written) into `stats.cost`.
- `docweave/schema/cache.py` (1.4) -- on a failed build, `map_exception` records the deferred entry in addition to 1.4's logger line.
- `~/frappe-bench/apps/frappe/frappe/exceptions.py:24-45` -- the class hierarchy. `utils/error.py:38-99` -- `log_error` stores a given `message` instead of calling `get_traceback`; tests flush with `frappe.deferred_insert.save_to_db()`.
- `~/frappe-bench/apps/frappe/frappe/utils/logger.py:12,67-80` -- logger name `docweave-<site>`, `propagate=False`, default level ERROR (WARNING under the dev server). Tests capture with `assertLogs(f"docweave-{frappe.local.site}")`.

## Tasks & Acceptance

**Execution:**
- [ ] `docweave/core/types.py` -- `RequestStats`.
- [ ] `docweave/adapter/errors.py` -- check order, sanitizer per the third question, and an `INTERNAL` message that never echoes the exception.
- [ ] `docweave/adapter/frappe_v16.py`, `docweave/execution/executor.py`, `docweave/schema/cache.py` -- fill `RequestStats`; route the build failure through the mapper.
- [ ] `docweave/api.py` -- one `RequestStats` per request, codes collected from the response body (`extensions.code`) and gate refusals, the log line written last in the `finally`, inside its own `try`.
- [ ] `docweave/tests/test_errors.py`, `docweave/tests/test_request_log.py` -- the matrix: one test per mapped class, locals, rollback before flush, a body scan for `Traceback` and paths, and log lines checked against a sentinel field value, a cursor and a document name.

**Acceptance Criteria:**
- Given any request that reaches DocWeave, when it completes, then exactly one `docweave` log line is written.
- Given the package, when `test_boundaries.py` runs, then it passes under whichever rule the query-count question chooses.

## Design Notes

Line format, `key=value` pairs, codes sorted: `endpoint=graphql status=200 ms=41 queries=9 scanned=180 cost=420 codes=MASKED:2,NOT_FOUND:1`. `scanned` and `cost` are `0` and `-` when the request never reached them.

## Verification

**Commands:**
- `cd ~/frappe-bench && bench --site dev.localhost run-tests --app docweave` -- expected: all pass.
- Manual: POST a list query, then `tail -1 ~/frappe-bench/sites/dev.localhost/logs/docweave.log` -- expected: one line in the format above.

## Implementation Notes

## Spec Change Log

## Review Triage Log
